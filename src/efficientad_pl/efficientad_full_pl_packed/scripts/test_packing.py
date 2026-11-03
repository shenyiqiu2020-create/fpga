"""Exhaustive signed INT8 proof of the 25x8 packed multiply arithmetic."""
from pathlib import Path
import numpy as np,json,time
r=Path(__file__).resolve().parents[1]
v=np.arange(-128,128,dtype=np.int64)
w0=v[:,None];w1=v[None,:];packed=(w1<<16)+w0
assert packed.min()>=-(1<<24) and packed.max()<(1<<24)
start=time.perf_counter();count=0
for x in v:
 p=packed*x;low=(p&65535);low=np.where(low>=32768,low-65536,low)
 high=(p>>16)+(low<0)
 assert np.array_equal(low,np.broadcast_to(w0*x,low.shape))
 assert np.array_equal(high,np.broadcast_to(w1*x,high.shape))
 count+=256*256
out={'status':'PASS','signed_int8_triples_checked':count,
     'formula':'P=((w1<<16)+w0)*x; low=signed16(P); high=(P>>16)+(low<0)',
     'host_seconds':time.perf_counter()-start,'not_RTL_validation':True}
(r/'generated/packing_arithmetic_test.json').write_text(json.dumps(out,indent=2))
print(out)
