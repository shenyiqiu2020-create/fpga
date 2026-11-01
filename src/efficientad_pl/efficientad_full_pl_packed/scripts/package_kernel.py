from pathlib import Path
import zipfile,hashlib
r=Path(__file__).resolve().parents[1];paths=[]
for part in ('generated','runtime','app_sources','scripts','experiments','hls/vendor','compare_hls/vendor','hls/engine_project/sol/impl/ip'):
 paths.extend(p for p in (r/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for part in ('hls','compare_hls'):
 paths.extend(p for p in (r/part).iterdir() if p.is_file() and p.suffix in ('.h','.cpp'))
for part in ('hls/engine_project/sol/syn/report','compare_hls/engine_project/sol/sim/report'):
 paths.extend((r/part).glob('*.rpt'))
paths.extend((r/'logs').glob('*.log'))
for name in ('README.md','RESULTS.md','RUN_PACKED.cmd','READ_PROFILE.cmd'):paths.append(r/name)
out=r.parent/'efficientad_full_pl_packed.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(set(paths)):z.write(p,str(Path(r.name)/p.relative_to(r)))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print(out,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
