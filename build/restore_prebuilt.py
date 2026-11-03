"""Restore native tool output from the verified IP archive for inspection."""
from pathlib import Path
import zipfile,shutil,subprocess,sys
r=Path(__file__).resolve().parents[1];c=r/'src/accelerator';s=c/'hls/engine_project/sol'
with zipfile.ZipFile(r/'board/efficientad_engine_ip.zip') as z:
    dest=(s/'impl/ip').resolve()
    for n in z.namelist():
        assert (dest/n).resolve().is_relative_to(dest),'Unsafe IP archive path'
    z.extractall(dest)
(s/'syn/verilog').mkdir(parents=True,exist_ok=True)
for p in (s/'impl/ip/hdl/verilog').iterdir():
    if p.suffix in ('.v','.vh'):shutil.copy2(p,s/'syn/verilog'/p.name)
shutil.copytree(r/'sim/results/cosim',s/'sim/report',dirs_exist_ok=True)
subprocess.run([sys.executable,str(c/'scripts/check_rtl.py'),'--require-cosim'],check=True)
print('Restored native generated RTL, IP and passed C/RTL evidence; not a new synthesis run')
