"""Accept only HLS's simulation-only DATAFLOW deadlock instrumentation."""
from pathlib import Path
import hashlib, json, re, shutil
r=Path(__file__).resolve().parents[1]
sol=r/'hls/engine_project/sol';syn=sol/'syn/verilog';pkg=sol/'impl/ip/hdl/verilog'
def canonical(s):
    # Exactly the block emitted by this installed HLS version; no functional
    # RTL changes are ignored. The detector's register is simulation-only use.
    s=re.sub(r'reg find_df_deadlock = 0;\s*// synthesis translate_off\s*`include "[A-Za-z0-9_]+_hls_deadlock_detector\.vh"\s*// synthesis translate_on', '', s)
    return re.sub(r'\s+', '', s)
before={p.name:p for p in syn.glob('*.v')}
after={p.name:p for p in pkg.glob('*.v')}
extra=set(after)-set(before)
assert not set(before)-set(after), 'Export removed a synthesized RTL module'
assert extra in (set(), {'efficientad_engine_hls_deadlock_detection_unit.v'}), ('Unexpected export modules',extra)
changes=[]
for n,p in after.items():
    if n in extra:
        # Instantiated solely from the detector included under translate_off.
        assert all('efficientad_engine_hls_deadlock_detect_unit' not in q.read_text() for q in before.values())
        continue
    a=before[n].read_text();b=p.read_text()
    assert canonical(a)==canonical(b), ('Export changed synthesizable RTL',n)
    if a!=b:changes.append(n)
for p in pkg.iterdir():
    if p.is_file() and p.suffix in ('.v','.vh'):shutil.copy2(p,syn/p.name)
assert all((syn/n).read_bytes()==p.read_bytes() for n,p in after.items())
(r/'generated/export_instrumentation.json').write_text(json.dumps({
    'status':'EXPORTED_RTL_SYNTHESIZABLE_LOGIC_IDENTICAL',
    'simulation_only_changes':changes,
    'simulation_only_added_modules':sorted(extra),
    'RTL_simulation_uses_exact_packaged_files':True,
    'exported_headers':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pkg.glob('*.vh')}
},indent=2))
print('Exported RTL checked; simulation-only instrumentation:', changes)
