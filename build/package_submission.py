"""Build a clean contest archive and an auditable SHA256 file manifest."""
from pathlib import Path
import os,json,hashlib,zipfile,time,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED=('build/work/','build/tmp/','src/accelerator/_build/','src/accelerator/hls/engine_project/',
          '.git/','data/private_archive/','data/legacy_original/')
OUTPUTS={'data/submission_manifest.json','build/efficientad_submission.zip','build/submission_archive.sha256'}

def files():
    for base,dirs,names in os.walk(ROOT):
        dirs[:]=sorted(n for n in dirs if n!='__pycache__' and not any((Path(base)/n).relative_to(ROOT).as_posix()+'/'==x for x in EXCLUDED))
        for name in sorted(names):
            p=Path(base)/name;rel=p.relative_to(ROOT).as_posix()
            if rel in OUTPUTS or p.suffix=='.pyc':continue
            assert not p.is_symlink(),'Symlinks must be resolved before packaging'
            yield p,rel

def main():
    entries=[{'path':rel,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,rel in files()]
    manifest=ROOT/'data/submission_manifest.json'
    manifest.write_text(json.dumps({'created':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'scope':'public contest artifacts; local archives, registration screenshot and caches excluded',
        'artifacts':entries},indent=2),encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'build/verify_delivery.py')],check=True)
    out=ROOT/'build/efficientad_submission.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,rel in files():z.write(p,rel)
        z.write(manifest,'data/submission_manifest.json')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(entries)+1
        for item in entries:
            assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256'],item['path']
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    (ROOT/'build/submission_archive.sha256').write_text(digest+'  efficientad_submission.zip\n',encoding='ascii')
    print(json.dumps({'status':'PASS','files':len(entries),'archive_bytes':out.stat().st_size,'archive_sha256':digest},indent=2))

if __name__=='__main__':main()
