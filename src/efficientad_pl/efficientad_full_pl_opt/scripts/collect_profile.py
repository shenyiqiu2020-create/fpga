"""Read the running board's flushed mailbox; never claims the serial port."""
import json,re,subprocess,struct,sys,datetime,hashlib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
name='baseline_profile' if '--baseline' in sys.argv else 'efficientad_full'
def parse(text,key):
 m=re.search(r'^'+key+r' (.+)$',text,re.M)
 if not m:raise RuntimeError('Cannot read '+key+'; inspect JTAG connection/log')
 return [int(x,16) if re.search('[a-fA-F]|^0x',x) else int(x) for x in m[1].split()]
cmd=['D:/amd/2025.2/Vitis/bin/xsdb.bat',str(r/'scripts/read_profile.tcl'),name]
result=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(r/'logs'/f'{name}_board_profile.log').write_text(result.stdout)
s=parse(result.stdout,'EA_STATUS');t=parse(result.stdout,'EA_TOTALS');p=parse(result.stdout,'EA_PROFILE')
if s[0]!=0x45414631 or s[1]!=4 or s[5]!=0:
 raise SystemExit('Test has not completed successfully: '+str(s))
m=json.loads((r/'generated/deployment_manifest.json').read_text())
runs=[]
for run in range(4 if name=='baseline_profile' else 2):
 v=t[run*8:run*8+8];stages=[]
 # Milliseconds use a separately parenthesized denominator. Reject the old
 # quarter-us conversion rather than silently publishing inconsistent units.
 if name!='baseline_profile' or run>=2:
  assert v[0]//1000==s[10+run%2], 'Inconsistent microsecond/millisecond units; rebuild the corrected application'
 for oi,o in enumerate(m['ops']):
  z=p[(run*29+oi)*5:(run*29+oi+1)*5]
  assert z[3]==z[4]==o['crc'][run%2],(run,oi,z)
  stages.append({'name':o['name'],'engine_us':z[0],'cache_us':z[1],'crc_us':z[2],'crc':z[3]})
 runs.append({'image':('D19_01','N17_03')[run%2],
              'crc_mode':'bitwise' if name=='baseline_profile' and run<2 else 'table',
              **dict(zip(('total_us','engine_us','cache_us','crc_us','score_us','copy_us'),v[:6])),
              'score':struct.unpack('<f',struct.pack('<I',v[6]))[0],
              'predicted_defect':bool(v[7]),'stages':stages})
 assert abs(runs[-1]['score']-m['int8_reference_scores'][run%2])<0.00002
 assert runs[-1]['predicted_defect']==m['int8_reference_predictions'][run%2]
out={'status':'BOARD_PROFILE_PASSED','application':name,
     'timestamp':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
     'evidence':'completed test mailbox and per-stage timing read from DDR over JTAG',
     'timer_conversion_revision':2,'mailbox_words':s,
     'host_elf_sha256':hashlib.sha256((r/'generated'/f'{name}.elf').read_bytes()).hexdigest(),
     'runs':runs}
(r/'generated'/f'{name}_board_profile.json').write_text(json.dumps(out,indent=2))
for v in runs:print(v['image'],v['crc_mode'],{k:v[k] for k in ('total_us','engine_us','cache_us','crc_us','score_us','score')})
