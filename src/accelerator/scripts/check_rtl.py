"""Check freshly synthesized PE40 RTL against its own C/RTL simulation."""
from pathlib import Path
import hashlib,json,sys,re
r=Path(__file__).resolve().parents[1];sol=r/'hls/engine_project/sol'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
syn={p.name:p for p in (sol/'syn/verilog').glob('*') if p.suffix in ('.v','.vh')}
pkg={p.name:p for p in (sol/'impl/ip/hdl/verilog').glob('*') if p.suffix in ('.v','.vh')}
assert syn and syn.keys()==pkg.keys(),'Missing/different packaged RTL file set'
hashes={n:sha(p) for n,p in syn.items()}
assert all(sha(pkg[n])==v for n,v in hashes.items()),'Stale exported RTL'
lanes=sum(p.read_text().count('efficientad_engine_requant grp_requant_') for p in syn.values())
assert lanes==4,('Expected four requantizers',lanes)
assert re.search(r'C_M_AXI_DDR_ADDR_WIDTH\s*=\s*32\s*;',syn['efficientad_engine.v'].read_text()),'AXI master must use 32-bit byte addresses'
frozen=json.loads((r/'generated/frozen_inputs_sha256.json').read_text())
assert all(sha(r/'generated'/n)==v for n,v in frozen.items()),'Model/quantization/test inputs changed'
extra=json.loads((r/'generated/pe40_tests_manifest.json').read_text())
assert extra['cases']==31 and sha(r/'generated/pe40_tests.bin')==extra['sha256']
assert extra['source_original_sha256']==sha(r/'generated/packed_tests.bin')
sources={str(p.relative_to(r)):sha(p) for p in (r/'hls').rglob('*') if p.is_file() and 'engine_project' not in p.parts and p.suffix in ('.h','.hpp','.cpp')}
reference=r/'generated/passed_cosim_identity.json'
if '--record-cosim' in sys.argv:
 report=sol/'sim/report/efficientad_engine_cosim.rpt';log=r/'logs/hls_cosim.log'
 assert re.search(r'Verilog\s*\|\s*Pass',report.read_text()),'RTL co-simulation did not pass'
 assert 'EFFICIENTAD ENGINE TEST PASSED: 31 cases.' in log.read_text(),'Expected all 31 tests'
 assert 'C/RTL co-simulation finished: PASS' in log.read_text(),'Incomplete RTL simulation'
 reference.write_text(json.dumps({'rtl':hashes,'sources':sources,'report_sha256':sha(report),'log_sha256':sha(log),'cases':31},indent=2))
out={'status':'SYNTHESIZED_AND_PACKAGED_RTL_IDENTICAL','files':len(pkg),'verilog_modules':sum(p.suffix=='.v' for p in pkg.values()),'requantizer_instances':lanes,'rtl_sha256':hashes,'model_inputs_unchanged':True,'matches_passed_RTL_simulation':False}
if reference.exists():
 ref=json.loads(reference.read_text())
 assert ref['rtl']==hashes and ref['sources']==sources,'RTL/source changed since passing simulation'
 assert sha(sol/'sim/report/efficientad_engine_cosim.rpt')==ref['report_sha256']
 assert sha(r/'logs/hls_cosim.log')==ref['log_sha256']
 out['matches_passed_RTL_simulation']=True
if '--require-cosim' in sys.argv:assert out['matches_passed_RTL_simulation']
if '--vivado' in sys.argv:
 active=list((r/'_build/vivado/ea_full.gen/sources_1/bd/design_full/ipshared').rglob('efficientad_engine.v'))
 assert len(active)==1,'Expected one imported kernel'
 assert all((active[0].parent/n).is_file() and sha(active[0].parent/n)==v for n,v in hashes.items()),'Stale Vivado RTL'
 out['vivado_import_matches']=True
(r/'generated/rtl_integrity.json').write_text(json.dumps(out,indent=2))
print(out['status'],len(pkg),'modules; cosim verified:',out['matches_passed_RTL_simulation'])
