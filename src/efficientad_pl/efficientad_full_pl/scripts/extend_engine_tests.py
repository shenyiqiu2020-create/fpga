"""Add multi-output-block checks to the frozen 16 initial fixtures."""
from pathlib import Path
import json,struct
import numpy as np
import torch
import torch.nn.functional as F
root=Path(__file__).resolve().parents[1]; gen=root/'generated'
path=gen/'engine_tests.bin'; content=path.read_bytes()
count=struct.unpack_from('<I',content,4)[0]
if count==18: print('18 fixtures already present'); raise SystemExit(0)
assert count==16
m=json.loads((gen/'deployment_manifest.json').read_text())
blob=np.fromfile(gen/'weights.bin',dtype='<u8')
rng=np.random.default_rng(33819); extra=[]
for oi in (1,13):
 o=m['ops'][oi]; c=o['cin']; k=o['kernel']; cg=(c+7)//8; kw=k*k*cg; cout=32
 ih=iw=max(k,7); ch=(ih+2*o['pad']-k)//o['stride']+1
 oh=ow=ch//2 if o['pool'] else ch
 qw=blob[o['wo']:o['wo']+cout*kw].copy().view(np.int8).reshape(cout,k,k,cg*8)[:,:,:,:c].transpose(0,3,1,2).copy()
 bias=blob[o['bo']:o['bo']+cout].view('<i8').copy(); mul=blob[o['mo']:o['mo']+cout].view('<i8').copy()
 x=rng.integers(-32,33,(1,c,ih,iw),dtype=np.int8)
 a=F.conv2d(torch.from_numpy(x.astype(np.float64)),torch.from_numpy(qw.astype(np.float64)),
    torch.from_numpy(bias.astype(np.float64)),stride=o['stride'],padding=o['pad']).numpy().astype(np.int64)
 p=a*mul[None,:,None,None]; y=(np.abs(p)+(1<<29))>>30; y=np.where(p<0,-y,y)
 if o['relu']: y=np.maximum(y,0)
 y=np.clip(y,-127,127).astype(np.int8)
 if o['pool']:
  ss=y[:,:,:oh*2,:ow*2].astype(np.int64).reshape(1,cout,oh,2,ow,2).sum(axis=(3,5))
  y=np.where(ss<0,-((np.abs(ss)+2)>>2),(ss+2)>>2).astype(np.int8)
 def pack(a):return np.ascontiguousarray(a.transpose(0,2,3,1)).view('<u8').ravel()
 memory=[]
 def put(v):
  while len(memory)%8:memory.append(0xD0D0D0D0D0D0D0D0)
  pos=len(memory);memory.extend(int(t)&0xffffffffffffffff for t in np.asarray(v).ravel());return pos
 src=put(pack(x));dst=put(np.full(pack(y).size,0xC0DEC0DEC0DEC0DE,np.uint64))
 wo=put(blob[o['wo']:o['wo']+cout*kw]);bo=put(bias);mo=put(mul)
 memory.extend([0xC0DEC0DEC0DEC0DE]*16)
 params=[0,src,dst,wo,bo,mo,ih,iw,c,cout,k,o['stride'],o['pad'],o['relu'],o['pool'],oh,ow,0]
 expected=np.asarray(memory,dtype='<u8'); py=pack(y); expected[dst:dst+py.size]=py
 extra.append(struct.pack('<19I',*params,len(memory))+np.asarray(memory,dtype='<u8').tobytes()+expected.tobytes())
path.write_bytes(content[:4]+struct.pack('<I',18)+content[8:]+b''.join(extra))
m['hls_test_count']=18;m['rtl_cosim_cases_passed_before_extension']=16
(gen/'deployment_manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print('Added two Cout=32 fixtures; original 16 fixtures byte-identical.')
