"""Validate routed 125 MHz hardware and export its matching PS initialization."""
from pathlib import Path
import json,re,zipfile,hashlib,subprocess,sys,xml.etree.ElementTree as E
r=Path(__file__).resolve().parents[1];g=r/'generated'
text=(g/'vivado_timing.rpt').read_text()
m=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+[-\d.]+\s+\d+\s+\d+\s+([-\d.]+)',text,re.S)
assert m,'Cannot find setup/hold timing summary'
wns,whs=map(float,m.groups());assert wns>=0 and whs>=0,('Timing failure',wns,whs)
clock=re.search(r'^clk_fpga_0\s+\{[^}]+\}\s+([\d.]+)\s+([\d.]+)',text,re.M)
assert clock and abs(float(clock[2])-125)<0.01,('Wrong implemented clock',clock)
with zipfile.ZipFile(g/'ax7021_efficientad_full.xsa') as z:
    inits=[n for n in z.namelist() if n.endswith('ps7_init.tcl')]
    assert len(inits)==1
    init=z.read(inits[0]).decode().replace('\r\n','\n')
    bits=[n for n in z.namelist() if n.endswith('.bit')]
    assert len(bits)==1 and z.read(bits[0])==(g/'efficientad_full.bit').read_bytes(),'XSA bit differs'
    hwh=[n for n in z.namelist() if Path(n).name=='design_full.hwh']
    assert len(hwh)==1
    hw=E.fromstring(z.read(hwh[0]))
ps=next(m for m in hw.iter('MODULE') if m.get('INSTANCE')=='ps')
params={p.get('NAME'):p.get('VALUE') for p in ps.iter('PARAMETER')}
assert abs(float(params['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ'])-125)<0.001
before=(g/'baseline_ps7_init.reference.tcl').read_text()
assert before==init,'PS initialization changed from the verified PE32 125 MHz baseline'
(g/'ps7_init.tcl').write_text(init)
subprocess.run([sys.executable,str(r/'scripts/check_rtl.py'),'--vivado','--require-cosim'],check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
runlog=(r/'_build/vivado/ea_full.runs/impl_1/runme.log').read_text()
forced_log=runlog.split('Command: phys_opt_design -force_replication_on_nets',1)[-1]
replication=[]
for m in re.finditer(r'EA_FORCE_CONTROL_REPLICATION: (.+), loads=(\d+)',runlog):
    net=m[1]
    done=re.search(r'Processed net '+re.escape(net)+r'\. Replicated (\d+) times\.',forced_log)
    assert done and int(done[1])>0,('Requested register replication not applied',net)
    replication.append({'net':net,'original_loads':int(m[2]),'replicas_added':int(done[1])})

(g/'physical_replication.json').write_text(json.dumps(replication,indent=2))
out={'status':'ROUTED_TIMING_AND_RTL_VALIDATED','clock_MHz':125,'wns_ns':wns,'whs_ns':whs,
     'control_replication':replication,
     'ps_changes':'PS initialization identical to PE32 125 MHz; ARM, DDR, UART and PL frequencies unchanged',
     'ps_clock_parameters':{k:v for k,v in params.items() if 'FREQ' in k and any(t in k for t in ('CPU','DDR','FPGA0','UART','IO_IO'))},
     'artifacts':{n:sha(g/n) for n in ('efficientad_full.bit','ax7021_efficientad_full.xsa','ps7_init.tcl')}}
(g/'hardware_validation.json').write_text(json.dumps(out,indent=2))
print(out)
