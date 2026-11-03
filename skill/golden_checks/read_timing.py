"""Parse a Vivado timing summary without assuming a particular accelerator."""
import re,json,argparse
from pathlib import Path
def parse(path):
    s=Path(path).read_text()
    m=re.search(r'WNS\(ns\).*?\n\s*-+[^\n]*\n\s*([^\n]+)',s,re.S)
    if not m:raise ValueError('Cannot find timing summary; this is not a supported report')
    v=m[1].split();wns=float(v[0]);whs=float(v[4])
    clocks=re.findall(r'^(\S+)\s+\{[^}]+\}\s+([\d.]+)\s+([\d.]+)\s*$',s,re.M)
    return {'setup_met':wns>=0,'hold_met':whs>=0,'wns_ns':wns,'whs_ns':whs,'clocks':[{'name':x,'period_ns':float(y),'frequency_mhz':float(z)} for x,y,z in clocks]}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);a=p.parse_args();v=parse(a.report);print(json.dumps(v,indent=2));raise SystemExit(0 if v['setup_met'] and v['hold_met'] else 1)
