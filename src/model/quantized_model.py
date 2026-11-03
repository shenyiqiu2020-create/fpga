"""Frozen FP32 and bit-exact INT8 operator reference; never recalibrates."""
from pathlib import Path
import hashlib,json,re,zlib,time
import numpy as np
from PIL import Image,ImageOps
import torch
import torch.nn.functional as F

ROOT=Path(__file__).resolve().parents[2]
GEN=ROOT/'src/accelerator/generated'
MODEL=ROOT/'data/models'

def preprocess(path,auto_crop=True):
    with Image.open(path) as im: image=ImageOps.exif_transpose(im).convert('RGB')
    crop_record=None
    if auto_crop and image.size!=(256,256):
        from tie_mount_crop import crop_mount
        image,crop_record=crop_mount(Path(path),size=256)
    image=image.resize((256,256),Image.Resampling.BILINEAR)
    rgb=np.asarray(image,dtype=np.uint8)
    x=rgb.astype(np.float32)/np.float32(255.)
    x=(x-np.asarray([.485,.456,.406],np.float32))/np.asarray([.229,.224,.225],np.float32)
    return rgb,np.ascontiguousarray(x.transpose(2,0,1))[None],crop_record

def full_map(fused):
    x=torch.from_numpy(np.ascontiguousarray(fused[:,None].astype(np.float32)))
    return F.interpolate(F.pad(x,(4,4,4,4)),(256,256),mode='bilinear',align_corners=False)[:,0].numpy()

class FrozenModel:
    def __init__(self,device=None):
        self.device=device or ('cuda' if torch.cuda.is_available() else 'cpu')
        torch.set_num_threads(4)
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        self.manifest=json.loads((GEN/'deployment_manifest.json').read_text())
        self.threshold=float(self.manifest['threshold'])
        hashes=self.manifest['source_hashes']
        for name,digest in hashes.items():
            assert hashlib.sha256((MODEL/name).read_bytes()).hexdigest()==digest,name
        text=(GEN/'ea_model_data.h').read_text()
        blob=text.split('static const uint64_t ea_blob[',1)[1].split('};',1)[0]
        self.blob=np.array([int(v,16) for v in re.findall(r'0x([0-9a-fA-F]{16})ULL',blob)],dtype='<u8')
        assert self.blob.nbytes==8139584
        self.ops=[]
        for o in self.manifest['ops']:
            op=dict(o)
            if o['opcode']==0:
                cpad=(o['cin']+7)//8*8
                n=o['cout']*o['kernel']**2*cpad//8
                w=self.blob[o['wo']:o['wo']+n].view(np.int8).reshape(o['cout'],o['kernel'],o['kernel'],cpad)[...,:o['cin']].transpose(0,3,1,2).copy()
                b=self.blob[o['bo']:o['bo']+o['cout']].astype(np.uint32).view(np.int32)
                m=self.blob[o['mo']:o['mo']+o['cout']].astype(np.uint32).view(np.int32)
                op['weight']=torch.tensor(w,dtype=torch.float64,device=self.device)
                op['bias']=torch.tensor(b,dtype=torch.float64,device=self.device)
                op['mult']=torch.tensor(m.astype(np.int64),device=self.device)[None,:,None,None]
            else:
                cy=self.blob[o['co']:o['co']+o['oh']]
                cx=self.blob[o['co']+o['oh']:o['co']+o['oh']+o['ow']]
                op['axes']=[torch.tensor(a.astype(np.int64),device=self.device) for a in (cy&65535,(cy>>16)&65535,(cy>>32)&65535,cx&65535,(cx>>16)&65535,(cx>>32)&65535)]
            self.ops.append(op)
        with np.load(MODEL/'normalization.npz') as n:self.norm={k:n[k].copy() for k in n.files}
        self.fp_models=None

    def packed_input(self,normalized):
        q=np.clip(np.rint(normalized/np.float32(self.manifest['input_scale'])),-127,127).astype(np.int8)
        return np.pad(q.transpose(0,2,3,1),((0,0),(0,0),(0,0),(0,5))).copy()

    def score_quantized(self,features):
        t,s,a=[v.astype(np.float32)*np.float32(scale) for v,scale in zip(features,self.manifest['final_scales'])]
        t=(t-self.norm['teacher_mean'])/self.norm['teacher_std']
        st=np.square(t-s[:,:384],dtype=np.float32).astype(np.float64).mean(axis=1).astype(np.float32)
        ae=np.square(a-s[:,384:],dtype=np.float32).astype(np.float64).mean(axis=1).astype(np.float32)
        st=np.float32(.1)*(st-np.float32(self.norm['q_st_start'].item()))/np.float32((self.norm['q_st_end']-self.norm['q_st_start']).item())
        ae=np.float32(.1)*(ae-np.float32(self.norm['q_ae_start'].item()))/np.float32((self.norm['q_ae_end']-self.norm['q_ae_start']).item())
        return full_map(np.float32(.5)*st+np.float32(.5)*ae)

    @torch.no_grad()
    def infer_int8(self,normalized,progress=None,collect_crc=False):
        start=time.perf_counter();features=[];crcs=[]
        q=np.clip(np.rint(normalized/np.float32(self.manifest['input_scale'])),-127,127).astype(np.int8)
        for ni in range(3):
            x=torch.tensor(q,device=self.device,dtype=torch.int64)
            begin=self.manifest['net_begin'][ni]
            for oi in range(begin,begin+self.manifest['net_count'][ni]):
                op=self.ops[oi]
                if progress:progress(oi,op['name'])
                if op['opcode']==0:
                    v=F.conv2d(x.double(),op['weight'],op['bias'],stride=op['stride'],padding=op['pad']).to(torch.int64)
                    v=v*op['mult'];x=(v.abs()+(1<<29))>>30
                    x=torch.where(v<0,-x,x)
                    x=x.clamp(0 if op['relu'] else -127,127)
                    if op['pool']:
                        h,w=x.shape[2]//2,x.shape[3]//2
                        v=x[:,:,:2*h,:2*w].reshape(x.shape[0],x.shape[1],h,2,w,2).sum(dim=(3,5))
                        x=torch.where(v<0,-((v.abs()+2)>>2),(v+2)>>2)
                else:
                    y0,y1,fy,x0,x1,fx=op['axes']
                    top=x[:,:,y0[:,None],x0[None,:]]*(32768-fx)[None,None,None,:]+x[:,:,y0[:,None],x1[None,:]]*fx[None,None,None,:]
                    bot=x[:,:,y1[:,None],x0[None,:]]*(32768-fx)[None,None,None,:]+x[:,:,y1[:,None],x1[None,:]]*fx[None,None,None,:]
                    v=top*(32768-fy)[None,None,:,None]+bot*fy[None,None,:,None]
                    rounded=(v.abs()+(1<<29))>>30
                    x=torch.where(v<0,-rounded,rounded).clamp(-127,127)
                if collect_crc:
                    a=x.to(torch.int8).cpu().numpy()
                    crcs.append([zlib.crc32(np.ascontiguousarray(v.transpose(1,2,0)).tobytes()) for v in a])
            features.append(x.to(torch.int8).cpu().numpy())
        maps=self.score_quantized(features)
        return {'scores':maps.max(axis=(1,2)).tolist(),'maps':maps,'crc':crcs,'elapsed_seconds':time.perf_counter()-start,'device':self.device,'backend':'int8_reference'}

    @torch.no_grad()
    def infer_fp32(self,normalized):
        start=time.perf_counter()
        if self.fp_models is None:
            self.fp_models=[torch.load(MODEL/(n+'_final.pth'),map_location='cpu',weights_only=False).eval().to(self.device) for n in ('teacher','student','autoencoder')]
        x=torch.tensor(normalized,dtype=torch.float32,device=self.device)
        t,s,a=[m(x) for m in self.fp_models]
        n={k:torch.tensor(v,device=self.device) for k,v in self.norm.items()}
        t=(t-n['teacher_mean'])/n['teacher_std']
        st=(t-s[:,:384]).square().mean(dim=1)
        ae=(a-s[:,384:]).square().mean(dim=1)
        fused=.5*(.1*(st-n['q_st_start'])/(n['q_st_end']-n['q_st_start']))+.5*(.1*(ae-n['q_ae_start'])/(n['q_ae_end']-n['q_ae_start']))
        maps=full_map(fused.cpu().numpy())
        return {'scores':maps.max(axis=(1,2)).tolist(),'maps':maps,'elapsed_seconds':time.perf_counter()-start,'device':self.device,'backend':'fp32_reference'}
