"""Positive and negative checks of the reusable evidence validators."""
from pathlib import Path
import sys,json,hashlib,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skill/golden_checks'))
from check_manifest import verify
from read_timing import parse
r=ROOT/'build/work/tool_tests';r.mkdir(parents=True,exist_ok=True)
p=r/'fixture.txt';p.write_bytes(b'known golden data')
m={'artifacts':[{'path':'fixture.txt','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}
assert verify(r,m)['status']=='PASS'
p.write_bytes(b'changed data');assert verify(r,m)['status']=='FAIL'
assert verify(r,{'artifacts':[{'path':'../escape','sha256':'0'*64}]})['failures'][0]['error']=='outside_root'
v=parse(ROOT/'build/reports/vivado_timing.rpt');assert v['setup_met'] and v['hold_met'] and v['wns_ns']==.175
bad=(ROOT/'build/reports/vivado_timing.rpt').read_text().replace('0.175','-0.175')
q=r/'negative_timing.rpt';q.write_text(bad);assert not parse(q)['setup_met']
(ROOT/'sim/results/delivery_tools_validation.json').write_text(json.dumps({'status':'PASS','checks':['matching_hash_passes','changed_hash_rejected','path_escape_rejected','valid_timing_passes','negative_slack_rejected']},indent=2))
print('PASS: 5 reusable-validator checks')
