"""Export one frozen complete EfficientAD for the dynamic INT8 PL engine.

The two bring-up fixtures also supply activation ranges. These are functional
checks, not independent accuracy evaluation or a production quantization claim.
Writes only into this new package directory, never into the user's D: projects.
"""
from pathlib import Path
import hashlib,json,struct,zlib
import numpy as np
import torch
import torch.nn.functional as F

ROOT=Path(__file__).resolve().parents[1]
GEN=ROOT/'generated'; GEN.mkdir(exist_ok=True)
MODEL=Path(r'C:\Users\sheny\Documents\ChatGPT\fpga\github_fpga\build\work\handoff\received_20261026\tie_mount_20261026_model')
GOLD=MODEL.parent/'golden'
bundle=json.loads((MODEL/'bundle_manifest.json').read_text())
for name,digest in bundle['sha256'].items():
    assert hashlib.sha256((MODEL/name).read_bytes()).hexdigest()==digest,name
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cudnn.allow_tf32=False
DEVICE='cuda' if torch.cuda.is_available() else 'cpu'
print('Reference device:',DEVICE,flush=True)
names=('teacher','student','autoencoder')
models=[torch.load(MODEL/(n+'_final.pth'),map_location='cpu',weights_only=False).eval().to(DEVICE) for n in names]
fixtures=('D19_01','N17_03')
images=np.stack([np.load(GOLD/f/'input_normalized_chw.npy',allow_pickle=False) for f in fixtures])
assert images.shape==(2,3,256,256)
SX=float(np.float32(0.020787402987480164))
ops=[]; net_begin=[]; net_count=[]; final_scales=[]
with torch.no_grad():
 for net,model in zip(names,models):
    net_begin.append(len(ops)); x=torch.tensor(images,device=DEVICE); i=0; scale=SX
    while i<len(model):
        l=model[i]; inp=list(x.shape); before=scale
        if isinstance(l,torch.nn.Conv2d):
            assert l.groups==1 and l.dilation==(1,1) and l.kernel_size[0]==l.kernel_size[1]
            assert l.stride[0]==l.stride[1] and l.padding[0]==l.padding[1]
            y=l(x); relu=i+1<len(model) and isinstance(model[i+1],torch.nn.ReLU)
            pool=i+2<len(model) and isinstance(model[i+2],torch.nn.AvgPool2d)
            if relu: y=F.relu(y)
            scale=max(float(y.abs().max().item())*1.05/127,1e-10)
            if pool:
                pl=model[i+2]
                assert relu and pl.kernel_size==2 and pl.stride==2 and pl.padding==0 and not pl.ceil_mode
                y=pl(y)
            w=l.weight.detach().cpu().numpy(); b=l.bias.detach().cpu().numpy()
            ws=np.maximum(np.max(np.abs(w),axis=(1,2,3))/np.float32(127),np.float32(1e-12)).astype(np.float64)
            # Trained dead/near-zero channels can still have a nonzero bias.
            # Keep that bias within INT32 without changing ordinary channels.
            ws=np.maximum(ws,np.abs(b.astype(np.float64))/(before*(1<<26)))
            qw=np.clip(np.rint(w/ws[:,None,None,None]),-127,127).astype(np.int8)
            qb=np.rint(b/(before*ws.astype(np.float64))).astype(np.int64)
            mul=np.rint(before*ws.astype(np.float64)/scale*(1<<30)).astype(np.int64)
            assert np.all((mul>=0)&(mul<2**31)),(net,i,float(before),float(scale),int(mul.min()),int(mul.max()))
            bound=l.in_channels*l.kernel_size[0]**2*127*127+np.abs(qb)
            assert np.max(bound)<2**31,(net,i,float(before),float(scale),float(ws.min()),int(np.max(np.abs(qb))))
            op=dict(name=f'{net}.conv{i}',opcode=0,ih=inp[2],iw=inp[3],cin=l.in_channels,cout=l.out_channels,
                kernel=l.kernel_size[0],stride=l.stride[0],pad=l.padding[0],relu=int(relu),pool=int(pool),
                oh=y.shape[2],ow=y.shape[3],input_scale=before,output_scale=scale,
                qw=qw,qb=qb,mul=mul)
            i+=1+int(relu)+int(pool)
        elif isinstance(l,torch.nn.Upsample):
            assert l.mode=='bilinear' and not l.align_corners
            y=l(x)
            op=dict(name=f'{net}.resize{i}',opcode=1,ih=inp[2],iw=inp[3],cin=inp[1],cout=inp[1],kernel=0,
                stride=0,pad=0,relu=0,pool=0,oh=y.shape[2],ow=y.shape[3],input_scale=scale,output_scale=scale)
            i+=1
        elif isinstance(l,torch.nn.Dropout): i+=1; continue
        else: raise ValueError((net,i,l))
        assert op['cin']<=256 and op['cout']%16==0 and op['kernel']**2*((op['cin']+7)//8)<=512
        ops.append(op); x=y
    assert list(x.shape[1:])==([768,56,56] if net=='student' else [384,56,56])
    net_count.append(len(ops)-net_begin[-1]); final_scales.append(scale)
print('Graph:',len(ops),'ops, conv=',sum(o['opcode']==0 for o in ops),'resize=',sum(o['opcode']==1 for o in ops),flush=True)

def coord_axis(n,out):
    f=np.clip((np.arange(out,dtype=np.float64)+.5)*n/out-.5,0,n-1)
    lo=np.floor(f).astype(np.uint64); hi=np.minimum(lo+1,n-1)
    q=np.rint((f-lo)*32768).astype(np.uint64)
    return lo|(hi<<16)|(q<<32)

def pack(x):
    # NCHW int8 -> N,H,W,C padded to eight lanes, little-endian uint64 words.
    hwc=x.transpose(0,2,3,1).copy(); c=x.shape[1]
    if c%8: hwc=np.pad(hwc,((0,0),(0,0),(0,0),(0,8-c%8)))
    return np.ascontiguousarray(hwc).view('<u8').reshape(x.shape[0],-1)

def requant(a,m,relu):
    product=a*m[None,:,None,None]
    out=(np.abs(product)+(1<<29))>>30
    out=np.where(product<0,-out,out)
    if relu: out=np.maximum(out,0)
    return np.clip(out,-127,127).astype(np.int8)

def resize_q(x,op):
    cy=coord_axis(op['ih'],op['oh']); cx=coord_axis(op['iw'],op['ow'])
    y0=(cy&65535).astype(int); y1=((cy>>16)&65535).astype(int); fy=((cy>>32)&65535).astype(np.int64)
    x0=(cx&65535).astype(int); x1=((cx>>16)&65535).astype(int); fx=((cx>>32)&65535).astype(np.int64)
    a=x.astype(np.int64)
    top=a[:,:,y0[:,None],x0[None,:]]*(32768-fx)[None,None,None,:]+a[:,:,y0[:,None],x1[None,:]]*fx[None,None,None,:]
    bot=a[:,:,y1[:,None],x0[None,:]]*(32768-fx)[None,None,None,:]+a[:,:,y1[:,None],x1[None,:]]*fx[None,None,None,:]
    v=top*(32768-fy)[None,None,:,None]+bot*fy[None,None,:,None]
    r=(np.abs(v)+(1<<29))>>30
    return np.clip(np.where(v<0,-r,r),-127,127).astype(np.int8)

def reference(x,op):
    if op['opcode']==1: return resize_q(x,op)
    with torch.no_grad():
        # Integer products/sums are exactly representable by float64 at these bounds.
        result=F.conv2d(torch.tensor(x.astype(np.float64),device=DEVICE),
            torch.tensor(op['qw'].astype(np.float64),device=DEVICE),
            torch.tensor(op['qb'].astype(np.float64),device=DEVICE),stride=op['stride'],padding=op['pad'])
        result=result.cpu().numpy()
    assert np.all(result==np.rint(result)) and np.max(np.abs(result))<2**31
    q=requant(result.astype(np.int64),op['mul'],op['relu'])
    if op['pool']:
        h=q.shape[2]//2; w=q.shape[3]//2
        s=q[:,:,:2*h,:2*w].astype(np.int64).reshape(q.shape[0],q.shape[1],h,2,w,2).sum(axis=(3,5))
        q=np.where(s<0,-((np.abs(s)+2)>>2),(s+2)>>2).astype(np.int8)
    return q

inputq=np.clip(np.rint(images/np.float32(SX)),-127,127).astype(np.int8)
outputs=[]
for ni,net in enumerate(names):
    q=inputq.copy()
    for index in range(net_begin[ni],net_begin[ni]+net_count[ni]):
        op=ops[index]; q=reference(q,op)
        assert tuple(q.shape[1:])==(op['cout'],op['oh'],op['ow'])
        packed=pack(q); op['crc']=[zlib.crc32(v.tobytes()) for v in packed]
        print(index,op['name'],tuple(q.shape),'CRC',*[f'{c:08X}' for c in op['crc']],flush=True)
    outputs.append(q)
np.savez(GEN/'quantized_features.npz',teacher=outputs[0],student=outputs[1],autoencoder=outputs[2])

blob=[]
def append_words(values):
    while len(blob)%8: blob.append(0)
    pos=len(blob); blob.extend(int(v)&0xffffffffffffffff for v in np.asarray(values).ravel()); return pos
for op in ops:
    if op['opcode']==0:
        w=op['qw'].transpose(0,2,3,1).copy(); c=w.shape[-1]
        if c%8: w=np.pad(w,((0,0),(0,0),(0,0),(0,8-c%8)))
        op['wo']=append_words(np.ascontiguousarray(w).view('<u8'))
        op['bo']=append_words(op['qb']); op['mo']=append_words(op['mul']); op['co']=0
    else:
        op['co']=append_words(np.concatenate((coord_axis(op['ih'],op['oh']),coord_axis(op['iw'],op['ow']))))
        op['wo']=op['bo']=op['mo']=0

def emit_u64(name,values):
    lines=[f'static const uint64_t {name}[{len(values)}] __attribute__((aligned(64))) = {{']
    for i in range(0,len(values),4): lines.append(','.join(f'0x{int(v):016x}ULL' for v in values[i:i+4])+',')
    return '\n'.join(lines+['};'])
norm=np.load(MODEL/'normalization.npz',allow_pickle=False)
def f32(v):
    s=format(float(np.float32(v)),'.9g')
    if '.' not in s and 'e' not in s: s+='.0'
    return s+'f'
header='''#ifndef EA_MODEL_DATA_H
#define EA_MODEL_DATA_H
#include <stdint.h>
typedef struct { const char *name; unsigned opcode,ih,iw,cin,cout,kernel,stride,pad,relu,pool,oh,ow,wo,bo,mo,co; float scale; uint32_t crc[2]; } EaOp;
#define EA_OP_COUNT 29U
#define EA_INPUT_WORDS 65536U
#define EA_BUFFER_WORDS 327680U
'''
assert len(ops)==29
header+=emit_u64('ea_blob',blob)+'\n'
packed_input=pack(inputq)
header+='static const uint64_t ea_inputs[2][65536] __attribute__((aligned(64))) = {\n'
for row in packed_input:
    header+='{\n'+'\n'.join(','.join(f'0x{int(v):016x}ULL' for v in row[i:i+4])+',' for i in range(0,len(row),4))+'\n},\n'
header+='};\nstatic const EaOp ea_ops[29] = {\n'
fields=('opcode','ih','iw','cin','cout','kernel','stride','pad','relu','pool','oh','ow','wo','bo','mo','co')
for o in ops:
    header+='{"'+o['name']+'",'+','.join(str(o[f])+'U' for f in fields)+','+f32(o['output_scale'])+',{' + ','.join(f'0x{c:08x}U' for c in o['crc'])+'}},\n'
header+='};\n'
header+='static const unsigned ea_net_begin[3]={'+','.join(map(str,net_begin))+'};\n'
header+='static const unsigned ea_net_count[3]={'+','.join(map(str,net_count))+'};\n'
for key in ('teacher_mean','teacher_std'):
    header+=f'static const float ea_{key}[384]={{'+','.join(f32(v) for v in norm[key].ravel())+'};\n'
for key in ('q_st_start','q_st_end','q_ae_start','q_ae_end'):
    header+=f'static const float ea_{key}='+f32(norm[key].item())+';\n'
threshold=json.loads((MODEL/'summary.json').read_text())['threshold']
header+='static const float ea_threshold='+f32(threshold)+';\n#endif\n'
(GEN/'ea_model_data.h').write_text(header,encoding='ascii')
np.asarray(blob,dtype='<u8').tofile(GEN/'weights.bin')

# Compact C/RTL fixtures: actual model weights and quantizers, representative
# kernels/channel depths/strides/padding plus every resize shape family.
rng=np.random.default_rng(20261029); tests=[]
conv_indices=[0,1,2,3,8,10,13,15,28]
for oi in conv_indices:
    orig=ops[oi]; assert orig['opcode']==0
    op=orig.copy(); op['cout']=16; op['qw']=orig['qw'][:16]; op['qb']=orig['qb'][:16]; op['mul']=orig['mul'][:16]
    op['ih']=op['iw']=16 if oi==0 else max(op['kernel'],7)
    ch=(op['ih']+2*op['pad']-op['kernel'])//op['stride']+1
    op['oh']=op['ow']=ch//2 if op['pool'] else ch
    x=rng.integers(-32,33,(1,op['cin'],op['ih'],op['iw']),dtype=np.int8)
    tests.append((op,x,reference(x,op)))
for oi in [i for i,o in enumerate(ops) if o['opcode']==1]:
    op=ops[oi].copy(); op['cin']=op['cout']=16
    x=rng.integers(-64,65,(1,16,op['ih'],op['iw']),dtype=np.int8)
    tests.append((op,x,reference(x,op)))
testpath=GEN/'engine_tests.bin'
with testpath.open('wb') as f:
    f.write(b'EAT1'+struct.pack('<I',len(tests)))
    for op,x,y in tests:
        memory=[]
        def put(v):
            while len(memory)%8: memory.append(0xD0D0D0D0D0D0D0D0)
            pos=len(memory); memory.extend(int(t)&0xffffffffffffffff for t in np.asarray(v).ravel()); return pos
        src=put(pack(x).ravel()); dst=put(np.full(pack(y).size,0xC0DEC0DEC0DEC0DE,np.uint64))
        if op['opcode']==0:
            w=op['qw'].transpose(0,2,3,1).copy(); c=op['cin']
            if c%8:w=np.pad(w,((0,0),(0,0),(0,0),(0,8-c%8)))
            wo=put(np.ascontiguousarray(w).view('<u8')); bo=put(op['qb']); mo=put(op['mul']); co=0
        else:
            wo=bo=mo=0; co=put(np.concatenate((coord_axis(op['ih'],op['oh']),coord_axis(op['iw'],op['ow']))))
        memory.extend([0xC0DEC0DEC0DEC0DE]*16)
        params=[op['opcode'],src,dst,wo,bo,mo]+[op[k] for k in ('ih','iw','cin','cout','kernel','stride','pad','relu','pool','oh','ow')]+[co]
        assert len(params)==18 and len(memory)<65536
        expected=np.asarray(memory,dtype='<u8'); packed=pack(y).ravel(); expected[dst:dst+packed.size]=packed
        f.write(struct.pack('<19I',*params,len(memory)))
        f.write(np.asarray(memory,dtype='<u8').tobytes()); f.write(expected.tobytes())

clean=[]
for o in ops: clean.append({k:v for k,v in o.items() if k not in ('qw','qb','mul')})
meta=dict(bundle_id=bundle['bundle_id'],source_hashes=bundle['sha256'],networks=list(names),net_begin=net_begin,net_count=net_count,
    ops=clean,input_scale=SX,final_scales=final_scales,threshold=threshold,
    activation_ranges='max abs FP32 activations of D19_01 and N17_03 with 5% margin; bring-up only, NOT independent accuracy evaluation',
    arithmetic='S8S8 symmetric; INT32 bias/acc; Q30 per-channel requant, ties away from zero; pooling rounded ties away; bilinear Q15 coordinates',
    hls_test_count=len(tests),hardware_status='not synthesized or board verified yet')
(GEN/'deployment_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print('Export complete:',len(blob)*8,'weight/parameter bytes;',len(tests),'HLS fixtures',flush=True)
