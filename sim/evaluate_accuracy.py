"""Evaluate frozen checkpoints and exact deployed quantization without tuning."""
from pathlib import Path
import argparse,csv,json,sys,hashlib,time
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/model'))
from quantized_model import FrozenModel,preprocess

def independent_inputs(image_root,labels):
    image_root=image_root.resolve()
    assert labels,'Label CSV is empty'
    required={'image','label','object_group','role'}
    assert required.issubset(labels[0]),'Required CSV columns: image,label,object_group,role'
    assert all(r['label'] in ('good','defect') for r in labels),'Labels must be good or defect'
    assert all(r['role'] in ('test','holdout') for r in labels),'Do not mix training/validation images into accuracy results'
    assert all(r['object_group'].strip() for r in labels),'Physical-object group must not be empty'
    assert len({r['image'] for r in labels})==len(labels),'Duplicate images in label CSV'
    excluded=[];paths=[]
    for row in labels:
        # Accept either case in group identifiers; calibration leakage is grouped.
        if row['object_group'].strip().upper() in ('D19','N17'):
            excluded.append(row);continue
        path=(image_root/row['image']).resolve()
        assert path.is_relative_to(image_root),'Image path escapes test directory'
        assert path.is_file(),f'Missing test image: {path}'
        with Image.open(path) as image:
            assert image.size==(256,256),'Use 256x256 crops; record localization rejects separately'
        paths.append((path,row))
    assert paths,'No independent samples remain after calibration-group exclusion'
    return paths,excluded

def metrics(rows,key):
    from sklearn.metrics import confusion_matrix,roc_auc_score,precision_recall_fscore_support,accuracy_score
    y=np.array([int(r['label']=='defect') for r in rows]);s=np.array([r[key] for r in rows]);p=s>rows[0]['threshold']
    tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel()
    pr,re,f1,_=precision_recall_fscore_support(y,p,average='binary',zero_division=0)
    return {'count':len(y),'accuracy':float(accuracy_score(y,p)),'auroc':float(roc_auc_score(y,s)) if len(set(y))==2 else None,'precision':float(pr),'recall':float(re),'specificity':float(tn/(tn+fp)) if tn+fp else None,'f1':float(f1),'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path);p.add_argument('--labels',type=Path);p.add_argument('--output',type=Path,default=ROOT/'sim/results/accuracy');p.add_argument('--device');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    if a.images:
        assert a.labels,'Provide a CSV with image,label,object_group,role columns'
        labels=list(csv.DictReader(a.labels.open(encoding='utf-8-sig')))
        paths,excluded=independent_inputs(a.images,labels)
    else:
        excluded=[]
        paths=[(ROOT/'data/samples'/n,{'label':l,'object_group':g,'role':'bringup_calibration'}) for n,l,g in [('d19_01.png','defect','D19'),('n17_03.png','good','N17')]]
    model=FrozenModel(a.device);rows=[]
    for path,meta in paths:
        _,x,_=preprocess(path,auto_crop=False)
        fp=model.infer_fp32(x);q=model.infer_int8(x,collect_crc=not bool(a.images))
        row={'image':path.name,**meta,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'threshold':model.threshold,'fp32_score':fp['scores'][0],'int8_score':q['scores'][0],'fp32_seconds':fp['elapsed_seconds'],'int8_reference_seconds':q['elapsed_seconds']}
        if not a.images:
            fi=0 if meta['object_group']=='D19' else 1
            assert all(v[0]==o['crc'][fi] for v,o in zip(q['crc'],model.ops)),path
            row['verified_stage_crcs']=29
        np.save(a.output/(path.stem+'_int8_map.npy'),q['maps'][0])
        rows.append(row);print(json.dumps(row),flush=True)
    with (a.output/'predictions.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={'scope':'independent_test' if a.images else 'two_bringup_calibration_images_NOT_accuracy_estimate','excluded_calibration_groups':['D19','N17'],'excluded_rows':excluded,'bundle_id':model.manifest['bundle_id'],'model_hashes':model.manifest['source_hashes'],'threshold_fixed':model.threshold,'device':model.device,'fp32':metrics(rows,'fp32_score'),'deployed_int8_reference':metrics(rows,'int8_score'),'rows':rows,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (a.output/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
