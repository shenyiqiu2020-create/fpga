"""Compile the actual runtime CRC functions, compare both paths with zlib."""
from pathlib import Path
import os,subprocess,ctypes,zlib,json,time
r=Path(__file__).resolve().parents[1];work=r/'_build/native';work.mkdir(parents=True,exist_ok=True)
s=(r/'runtime/main.c').read_text()
def function(start):
 p=s.index(start);q=s.index('{',p);depth=1;j=q+1
 while depth:
  depth+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[p:j]
src='#include <stdint.h>\nstatic uint32_t crc_table[256];static unsigned fast_crc;\n'
src+=function('static void init_crc')+'\n'+function('static uint32_t crc_bytes')
src+='\n__declspec(dllexport) uint32_t check_crc(const void *p,unsigned n,unsigned fast) {init_crc();fast_crc=fast;return crc_bytes(p,n);}\n'
(work/'crc.c').write_text(src)
base=Path('D:/amd/2025.2/Vitis');clang=base/'win64/tools/clang-16/bin/clang.exe';link=clang.with_name('lld-link.exe')
env=os.environ.copy();env['PATH']=';'.join(str(base/p) for p in ('lib/win64.o','bin/unwrapped/win64.o','win64/lib','win64/tools/clang-16/bin'))+';'+env['PATH']
subprocess.run([str(clang),'--target=x86_64-pc-windows-msvc','-O2','-ffreestanding','-fno-stack-protector','-fno-builtin','-c',str(work/'crc.c'),'-o',str(work/'crc.obj')],env=env,check=True)
subprocess.run([str(link),'/dll','/noentry','/nodefaultlib','/machine:x64','/out:'+str(work/'crc.dll'),str(work/'crc.obj')],env=env,check=True)
lib=ctypes.CDLL(str(work/'crc.dll'));f=lib.check_crc;f.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint];f.restype=ctypes.c_uint32
tests=[b'',b'123456789',bytes(range(256)),bytes(range(256))*65536]
results=[]
for b in tests:
 expected=zlib.crc32(b);times=[]
 for fast in (0,1):
  begin=time.perf_counter();actual=f(b,len(b),fast);times.append(time.perf_counter()-begin)
  assert actual==expected,(len(b),fast,hex(actual),hex(expected))
 results.append({'bytes':len(b),'crc':hex(expected),'slow_host_seconds':times[0],'table_host_seconds':times[1]})
(r/'generated/crc_validation.json').write_text(json.dumps({'status':'PASS','host_timing_only':True,'cases':results},indent=2))
print('Both actual C CRC paths match independent zlib, including 16 MiB:',results[-1])
