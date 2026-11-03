"""Compile only the PS demo, leaving the board-verified PL RTL unchanged."""
from pathlib import Path
import os,subprocess,json,struct,hashlib
r=Path(__file__).resolve().parents[1]
bsp=Path(os.environ.get('EA_BSP','D:/ddca/experiments/fpga_amd/vitis_workspace/ax7021_conv1_platform/export/ax7021_conv1_platform/sw/standalone_ps7_cortexa9_0'))
gcc=os.environ.get('EA_GCC','D:/amd/2025.2/Vitis/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')
out=r/'board/efficientad_demo.elf'
subprocess.run([gcc,'-O2','-DSDT','-specs='+str(bsp/'Xilinx.spec'),'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-Wall','-Wextra',
 '-I'+str(bsp/'include'),'-I'+str(r/'src/accelerator/runtime'),'-I'+str(r/'src/accelerator/generated'),str(r/'src/ps_demo/main.c'),
 '-Wl,-T,'+str(r/'src/accelerator/runtime/lscript.ld'),'-L'+str(bsp/'lib'),'-Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lgcc,-lc,-lm,--end-group','-o',str(out)],check=True)
d=out.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',d);sections=[struct.unpack_from('<IIIIIIIIII',d,h[6]+i*h[11]) for i in range(h[12])];syms={}
for sec in sections:
 if sec[1]!=2:continue
 st=sections[sec[6]];strings=d[st[4]:st[4]+st[5]]
 for p in range(sec[4],sec[4]+sec[5],sec[9]):
  n,v,z,_,_,_=struct.unpack_from('<IIIBBH',d,p);n=strings[n:strings.find(b'\0',n)].decode(errors='replace')
  if n in ('DemoControl','DemoInput','DemoFused','DemoTimes','ea_blob'):syms[n]={'address':v,'bytes':z}
assert len(syms)==5
(r/'board/demo_layout.json').write_text(json.dumps({'symbols':syms,'elf_sha256':hashlib.sha256(d).hexdigest(),'kernel_bit_sha256':hashlib.sha256((r/'board/efficientad_full.bit').read_bytes()).hexdigest()},indent=2))
(r/'board/demo_addresses.tcl').write_text('\n'.join('set %s 0x%08X'%(k,v['address']) for k,v in syms.items())+'\n')
print(syms)
