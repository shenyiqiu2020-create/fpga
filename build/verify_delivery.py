"""Audit the contest package without reprogramming the board."""
from pathlib import Path
import hashlib,json,re,sys,os
r=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(r/'skill/golden_checks'))
from check_manifest import verify
from read_timing import parse
ignored=('build/work/','src/accelerator/_build/','src/accelerator/hls/engine_project/','.git/')
bad=[]
for base,dirs,files in os.walk(r):
 dirs[:]=[n for n in dirs if n!='__pycache__' and not any((Path(base)/n).relative_to(r).as_posix()+'/'==x for x in ignored)]
 for n in files:
  p=Path(base)/n;rel=p.relative_to(r).as_posix()
  for name in p.relative_to(r).parts:
   if name not in ('README.md','.gitignore','.gitattributes') and not re.fullmatch(r'[a-z0-9_-]+(?:\.[a-z0-9_-]+)*',name):bad.append(rel);break
assert not bad,('Invalid submission names',bad[:30])
assert all((r/d).is_dir() for d in ('src','sim','build','board','data','skill','report'))
hw=json.loads((r/'board/evidence/hardware_validation.json').read_text())
for n,h in hw['artifacts'].items():assert hashlib.sha256((r/'board'/n).read_bytes()).hexdigest()==h,n
layout=json.loads((r/'board/demo_layout.json').read_text());assert hashlib.sha256((r/'board/efficientad_demo.elf').read_bytes()).hexdigest()==layout['elf_sha256']
manifest=json.loads((r/'src/accelerator/generated/deployment_manifest.json').read_text())
for n,h in manifest['source_hashes'].items():assert hashlib.sha256((r/'data/models'/n).read_bytes()).hexdigest()==h,n
timing=parse(r/'build/reports/vivado_timing.rpt');assert timing['setup_met'] and timing['hold_met']
model_match=json.loads((r/'sim/results/demo_board/validation.json').read_text());assert model_match['status']=='UPLOADED_IMAGES_AND_FULL_MAP_BOARD_VERIFIED'
ui=json.loads((r/'sim/results/frontend_validation.json').read_text());assert ui['status']=='FRONTEND_FPGA_AND_REFERENCE_E2E_PASSED' and not ui['javascript_errors']
acc=json.loads((r/'sim/results/received_accuracy/metrics.json').read_text())
assert acc['records']==284 and acc['unique_image_hashes']==224
assert acc['board']['count']==75 and acc['board']['max_map_abs_error']<=.00002
sha=r/'data/submission_manifest.json'
if sha.exists():
 v=verify(r,json.loads(sha.read_text()));assert v['status']=='PASS',v['failures'][:10]
out={'status':'PASS','filename_audit':'PASS','required_directories':'PASS','verified_firmware_and_model_hashes':'PASS','routed_setup_hold':'PASS','uploaded_image_board_test':'PASS','frontend_browser_e2e':'PASS',
     'received_crop_evaluation':'284 records, 4 retrospective sets; 75 actual FPGA full-map matches',
     'remaining_items':['Collect new unseen physical objects for a blind test; expanded normal false positives remain unresolved','Official AMD one-page English poster template not supplied','Team identities, board revision, registration and final scoring rules require team confirmation','Camera and screen recording require user permission and physical filming check']}
print(json.dumps(out,indent=2))
