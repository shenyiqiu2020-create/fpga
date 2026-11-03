"""JTAG transport for a persistent board-side complete EfficientAD service."""
from pathlib import Path
import subprocess,os,re,json,struct,hashlib,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def execute(command,work=None,progress=None):
    xsdb=os.environ.get('EA_XSDB','D:/amd/2025.2/Vitis/bin/xsdb.bat')
    args=[xsdb,str(ROOT/'board/demo_service.tcl'),command]
    if work:args.append(str(work.resolve()))
    log=[];start=time.perf_counter()
    tool_work=ROOT/'build/work/demo';tool_work.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(args,cwd=tool_work,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    try:
        for line in proc.stdout:
            log.append(line)
            m=re.search(r'^EA_PROGRESS (\d+)',line)
            if m and progress:progress(min(int(m[1]),28),'PL inference')
        code=proc.wait(timeout=120)
    finally:
        if proc.poll() is None:proc.terminate()
    text=''.join(log)
    if work:(work/'jtag.log').write_text(text,encoding='utf-8')
    else:
        folder=ROOT/'build/work/demo';folder.mkdir(parents=True,exist_ok=True)
        (folder/('last_'+command+'.log')).write_text(text,encoding='utf-8')
    if code:raise RuntimeError('JTAG 操作失败。请检查圆口电源、JTAG USB 和 hw_server。\n'+text[-1200:])
    def values(key):
        m=re.search(r'^'+key+r' (.+)$',text,re.M)
        if not m:raise RuntimeError('No board response: '+key+'\n'+text[-1600:])
        return [int(x,16) if re.search('[a-fA-F]|^0x',x) else int(x) for x in m[1].split()]
    c=values('EA_CONTROL');clocks=values('EA_CLOCK')
    hz=(100/3)*((clocks[0]>>12)&127)/((clocks[1]>>8)&63)/((clocks[1]>>20)&63)
    assert abs(hz-125)<.01,'Unexpected PL clock'
    assert c[0]==0x45414432 and c[13]==1 and c[14]==0x4F563135
    return {'control':c,'clock_mhz':hz,'host_seconds':time.perf_counter()-start,'log':text}

def initialize():
    layout=json.loads((ROOT/'board/demo_layout.json').read_text())
    assert hashlib.sha256((ROOT/'board/efficientad_demo.elf').read_bytes()).hexdigest()==layout['elf_sha256']
    assert hashlib.sha256((ROOT/'board/efficientad_full.bit').read_bytes()).hexdigest()==layout['kernel_bit_sha256']
    return execute('init')

def infer(packed,work,progress=None):
    assert packed.shape==(1,256,256,8) and packed.dtype==np.int8
    packed.tofile(work/'input.bin')
    v=execute('infer',work,progress);c=v['control']
    fused=np.fromfile(work/'fused.bin',dtype='<f4').reshape(1,56,56)
    times=np.fromfile(work/'times.bin',dtype='<u4')
    assert len(times)==29 and np.isfinite(fused).all()
    return {'score':struct.unpack('<f',struct.pack('<I',c[6]))[0],
            'threshold':struct.unpack('<f',struct.pack('<I',c[7]))[0],
            'kernel_ms':c[8]/1000,'board_ms':c[9]/1000,'score_ms':c[10]/1000,
            'host_ms':v['host_seconds']*1000,'fused':fused,'stage_us':times.tolist(),
            'backend':'fpga','clock_mhz':v['clock_mhz'],'request_sequence':c[3]}
