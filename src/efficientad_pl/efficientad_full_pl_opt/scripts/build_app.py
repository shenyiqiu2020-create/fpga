import os,sys,subprocess,struct,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
bsp=Path(os.environ.get('EA_BSP','D:/ddca/experiments/fpga_amd/vitis_workspace/ax7021_conv1_platform/export/ax7021_conv1_platform/sw/standalone_ps7_cortexa9_0'))
gcc=os.environ.get('EA_ARM_GCC','D:/amd/2025.2/Vitis/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')
baseline='--compare-crc' in sys.argv
name='baseline_profile' if baseline else 'efficientad_full'
out=r/'generated'/f'{name}.elf'
args=[gcc,'-O2','-DSDT','-specs='+str(bsp/'Xilinx.spec'),'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-Wall','-Wextra',
      '-I'+str(bsp/'include'),'-I'+str(r/'runtime'),'-I'+str(r/'generated'),
      '-DEA_COMPARE_CRC='+str(int(baseline)),str(r/'runtime/main.c'),
      '-Wl,-T,'+str(r/'runtime/lscript.ld'),'-L'+str(bsp/'lib'),
      '-Wl,--start-group,-lxilstandalone,-lxiltimer,-lxil,-lgcc,-lc,-lm,--end-group',
      '-o',str(out)]
subprocess.run(args,check=True)
d=out.read_bytes(); h=struct.unpack_from('<16sHHIIIIIHHHHHH',d);off,ent,num=h[6],h[11],h[12]
sections=[struct.unpack_from('<IIIIIIIIII',d,off+i*ent) for i in range(num)]
syms={}
for sec in sections:
    if sec[1]!=2:continue
    st=sections[sec[6]];strings=d[st[4]:st[4]+st[5]]
    for p in range(sec[4],sec[4]+sec[5],sec[9]):
        n,v,z,info,other,idx=struct.unpack_from('<IIIBBH',d,p)
        n=strings[n:strings.find(b'\0',n)].decode(errors='replace')
        if n in ('EaStatus','EaProfile','EaTotals','buffers','ea_blob','ea_inputs'):
            syms[n]={'address':v,'bytes':z}
(r/'generated'/f'{name}_layout.json').write_text(json.dumps(syms,indent=2))
(r/'generated/mailbox.tcl').write_text('set ea_status_address 0x%08X\n'%syms['EaStatus']['address'])
(r/'generated'/f'{name}_addresses.tcl').write_text('\n'.join('set %s 0x%08X'%(k,v['address']) for k,v in syms.items())+'\n')
print(out,syms)
