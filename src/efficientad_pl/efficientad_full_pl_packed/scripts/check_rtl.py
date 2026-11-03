"""Reject stale HLS export caches before a Vivado build or deployment."""
from pathlib import Path
import hashlib,json,sys,re
r=Path(__file__).resolve().parents[1];sol=r/'hls/engine_project/sol'
syn={p.name:p for p in (sol/'syn/verilog').glob('*.v')}
pkg={p.name:p for p in (sol/'impl/ip/hdl/verilog').glob('*.v')}
assert syn and pkg,'RTL not generated/packaged'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
bad=[n for n,p in pkg.items() if n not in syn or sha(p)!=sha(syn[n])]
assert not bad,'STALE_OR_CHANGED_PACKAGED_RTL: '+str(bad)
assert syn.keys()==pkg.keys(),('Different RTL file sets',syn.keys()-pkg.keys(),pkg.keys()-syn.keys())
loop='efficientad_engine_conv_layer_Pipeline_VITIS_LOOP_141_16.v'
count=(pkg[loop].read_text()).count('efficientad_engine_requant grp_requant_')
assert count==4,('Expected four requantizer instances',count)
out={'status':'SYNTHESIZED_AND_PACKAGED_RTL_IDENTICAL','files':len(pkg),'requantizer_instances':count,
     'rtl_sha256':{n:sha(p) for n,p in pkg.items()}}
reference=json.loads((r/'generated/verified_q4_rtl_hashes.json').read_text())
assert set(pkg)<=set(reference),'Final RTL contains an unverified module'
assert all(out['rtl_sha256'][n]==reference[n] for n in pkg),'Final RTL differs from the RTL/C-equivalence build'
# A fresh solution drops one unused helper left by the preceding scalar build.
# Permit removal only after proving none of the retained modules reference it.
removed=set(reference)-set(pkg)
retained='\n'.join(p.read_text() for p in pkg.values())
for n in removed:
 original=(r/'experiments/verified_q4_rtl'/n).read_text()
 modules=re.findall(r'\bmodule\s+(\w+)',original)
 assert modules and all(not re.search(r'\b'+re.escape(m)+r'\b',retained) for m in modules),('Removed referenced RTL',n)
out['unused_prior_helpers_omitted']=sorted(removed)
out['matches_passed_RTL_simulation']=True
if '--vivado' in sys.argv:
 active=list((r/'_build/vivado/ea_full.gen/sources_1/bd/design_full/ipshared').rglob(loop))
 assert len(active)==1 and sha(active[0])==sha(pkg[loop]),'Vivado imported stale RTL'
 active_dir=active[0].parent
 assert all((active_dir/n).exists() and sha(active_dir/n)==sha(p) for n,p in pkg.items()),'Vivado RTL file set differs from verified package'
 out['vivado_import_matches']=True
(r/'generated/rtl_integrity.json').write_text(json.dumps(out,indent=2))
print(out['status'],out['files'],'modules, Q lanes',count,'Vivado checked','--vivado' in sys.argv)
