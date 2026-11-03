"""Archive deployable artifacts and sources, omitting transient Vivado/HLS DBs."""
from pathlib import Path
import zipfile,hashlib
r=Path(__file__).resolve().parents[1]
paths=[]
for part in ('generated','runtime','app_sources','scripts','hls/vendor','baseline_hls/vendor','hls/engine_project/sol/impl/ip'):
 paths.extend(p for p in (r/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for part in ('hls','baseline_hls'):
 paths.extend(p for p in (r/part).iterdir() if p.is_file() and p.suffix in ('.cpp','.h'))
for name in ('README.md','RESULTS.md','RUN_OPTIMIZED.cmd','READ_PROFILE.cmd','RUN_BASELINE_PROFILE.cmd'):
 paths.append(r/name)
for name in ('hls_all.log','cache_verify.log','baseline_compare.log','vivado_console.log','efficientad_full_board_profile.log','deploy_profile_v2.log'):
 paths.append(r/'logs'/name)
for part in ('hls/engine_project/sol/syn/report','baseline_hls/engine_project/sol/sim/report'):
 paths.extend(p for p in (r/part).glob('*.rpt') if p.is_file())
out=r.parent/'efficientad_full_pl_optimized.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(set(paths)):
  if p.name.startswith('board_profile_v1'):continue
  z.write(p,str(Path(r.name)/p.relative_to(r)))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print(out,out.stat().st_size,hashlib.sha256(out.read_bytes()).hexdigest())
