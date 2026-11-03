"""Check relative artifact paths and SHA256 identities for any project."""
from pathlib import Path
import argparse,hashlib,json,sys

def verify(root,manifest):
    root=Path(root).resolve();failures=[]
    for record in manifest['artifacts']:
        p=(root/record['path']).resolve()
        if not p.is_relative_to(root):failures.append({'path':record['path'],'error':'outside_root'});continue
        if not p.is_file():failures.append({'path':record['path'],'error':'missing'});continue
        actual=hashlib.sha256(p.read_bytes()).hexdigest()
        if actual!=record['sha256']:failures.append({'path':record['path'],'error':'hash_mismatch','actual':actual})
    return {'status':'PASS' if not failures else 'FAIL','checked':len(manifest['artifacts']),'failures':failures}

def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    result=verify(a.root,json.loads(a.manifest.read_text(encoding='utf-8')))
    if a.output:a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
