from pathlib import Path
import zipfile,hashlib,json
r=Path(__file__).resolve().parents[1];paths=[]
for part in ('generated','runtime','app_sources','scripts','experiments','hls/vendor','hls/engine_project/sol/impl/ip','hls/engine_project/sol/syn/verilog','hls/engine_project/sol/syn/report','hls/engine_project/sol/sim/report'):
 paths.extend(p for p in (r/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
paths.extend(p for p in (r/'hls').iterdir() if p.is_file() and p.suffix in ('.h','.cpp'))
paths.extend((r/'logs').glob('*.log'))
for name in ('README.md','results.md','run_overlap.cmd','read_profile.cmd','build_overlap.cmd'):paths.append(r/name)
out=r.parent/'efficientad_full_pl_overlap125.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(set(paths)):z.write(p,str(Path(r.name)/p.relative_to(r)))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
info={'file':out.name,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
(r/'bundle_manifest.json').write_text(json.dumps(info,indent=2));print(info)
