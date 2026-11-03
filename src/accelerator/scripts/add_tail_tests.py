"""Append PE40 block/tail cases using the existing independent Torch INT64 reference scheme."""
from pathlib import Path
import json,struct,hashlib
import numpy as np
import torch
import torch.nn.functional as F
r=Path(__file__).resolve().parents[1];g=r/'generated'
original=(g/'packed_tests.bin').read_bytes();assert original[:4]==b'EAT1'
count=struct.unpack_from('<I',original,4)[0];assert count==27
rng=np.random.default_rng(20261102)
cases=[(5,7,8,48,3,1,1,0),(7,7,8,80,3,1,0,0),(7,9,8,128,3,1,1,1),(3,3,8,256,3,1,0,0)]
extra=[];description=[]
for ih,iw,cin,cout,k,stride,pad,pool in cases:
 cg=cin//8;ch=(ih+2*pad-k)//stride+1;cw=(iw+2*pad-k)//stride+1
 oh,ow=(ch//2,cw//2) if pool else (ch,cw)
 x=rng.integers(-127,128,(1,cin,ih,iw),dtype=np.int8)
 w=rng.integers(-15,16,(cout,cin,k,k),dtype=np.int8)
 bias=rng.integers(-300,301,cout,dtype=np.int64);mul=rng.integers(1<<19,1<<22,cout,dtype=np.int64)
 a=F.conv2d(torch.from_numpy(x.astype(np.float64)),torch.from_numpy(w.astype(np.float64)),torch.from_numpy(bias.astype(np.float64)),stride=stride,padding=pad).numpy().astype(np.int64)
 p=a*mul[None,:,None,None];y=np.where(p<0,-((np.abs(p)+(1<<29))>>30),(p+(1<<29))>>30)
 relu=int(pool);y=np.clip(np.maximum(y,0) if relu else y,-127,127).astype(np.int8)
 if pool:
  v=y[:,:,:oh*2,:ow*2].astype(np.int64).reshape(1,cout,oh,2,ow,2).sum(axis=(3,5))
  y=np.where(v<0,-((np.abs(v)+2)>>2),(v+2)>>2).astype(np.int8)
 def pack(a):return np.ascontiguousarray(a.transpose(0,2,3,1)).view('<u8').ravel()
 memory=[]
 def put(a):
  while len(memory)%8:memory.append(0xBAD0BAD0BAD0BAD0)
  off=len(memory);memory.extend(int(t)&0xffffffffffffffff for t in np.asarray(a).ravel());return off
 src=put(pack(x));dst=put(np.full(pack(y).size,0xC0DEC0DEC0DEC0DE,np.uint64))
 wo=put(np.ascontiguousarray(w.transpose(0,2,3,1)).view('<u8'));bo=put(bias);mo=put(mul)
 memory.extend([0xBAD0BAD0BAD0BAD0]*8);assert len(memory)<=65536
 expected=np.array(memory,dtype='<u8');py=pack(y);expected[dst:dst+py.size]=py
 args=[0,src,dst,wo,bo,mo,ih,iw,cin,cout,k,stride,pad,relu,pool,oh,ow,0]
 extra.append(struct.pack('<19I',*args,len(memory))+np.array(memory,dtype='<u8').tobytes()+expected.tobytes())
 description.append(dict(zip(('ih','iw','cin','cout','kernel','stride','pad','pool'),(ih,iw,cin,cout,k,stride,pad,pool))))
out=original[:4]+struct.pack('<I',count+len(extra))+original[8:]+b''.join(extra)
(g/'pe40_tests.bin').write_bytes(out)
manifest={'cases':31,'original_cases':27,'added_shapes':description,'sha256':hashlib.sha256(out).hexdigest(),'source_original_sha256':hashlib.sha256(original).hexdigest(),'golden':'Torch FP64 convolution over exact integer inputs followed by original INT64 Q30 and pool rounding'}
(g/'pe40_tests_manifest.json').write_text(json.dumps(manifest,indent=2));print(manifest)
