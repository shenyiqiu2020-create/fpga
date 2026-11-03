"""Re-evaluate received retrospective crops with frozen FP32, INT8 and FPGA."""
from pathlib import Path
from collections import Counter
import csv,json,sys,time,hashlib,argparse,subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/model'),str(ROOT/'src/demo'),str(ROOT/'sim')]
from quantized_model import FrozenModel,preprocess
from evaluate_accuracy import metrics
import board_backend

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-heldout',action='store_true')
    args=parser.parse_args()
    inputs=json.loads((ROOT/'data/test_inputs/evaluation_manifest.json').read_text())['images']
    out=ROOT/'sim/results/received_accuracy';out.mkdir(exist_ok=True)
    work=ROOT/'build/work/received_accuracy';work.mkdir(parents=True,exist_ok=True)
    model=FrozenModel();cache={};rows=[];started=time.time()
    for i,item in enumerate(inputs):
        path=ROOT/item['path'];digest=hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest==item['sha256'],path
        if digest not in cache:
            _,x,_=preprocess(path,False)
            fp=model.infer_fp32(x);q=model.infer_int8(x)
            cache[digest]={'fp32_score':fp['scores'][0],'int8_score':q['scores'][0],'map':q['maps'][0]}
        values=cache[digest]
        rows.append({**item,'threshold':model.threshold,'fp32_score':values['fp32_score'],'int8_score':values['int8_score']})
        if (i+1)%10==0 or i+1==len(inputs):
            print(f'REFERENCE {i+1}/{len(inputs)}; unique={len(cache)}; elapsed={time.time()-started:.1f}s',flush=True)
    with (out/'predictions.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    sets={}
    for name in sorted({r['set'] for r in rows}):
        rr=[r for r in rows if r['set']==name]
        filtered=[r for r in rr if not r['calibration_group']]
        sets[name]={'scope':'retrospective comparison; previously seen, not a new blind test','count':len(rr),
                    'groups':sorted({r['object_group'] for r in rr}),
                    'fp32':metrics(rr,'fp32_score'),'int8':metrics(rr,'int8_score'),
                    'fp32_historical_max_abs_score_error':max(abs(r['fp32_score']-r['historical_fp32_score']) for r in rr),
                    'prediction_agreement':sum((r['fp32_score']>model.threshold)==(r['int8_score']>model.threshold) for r in rr)/len(rr),
                    'without_calibration_groups':{'count':len(filtered),'fp32':metrics(filtered,'fp32_score'),'int8':metrics(filtered,'int8_score')},
                    'int8_mistakes':[r for r in rr if (r['int8_score']>model.threshold)!=(r['label']=='defect')]}
    result={'scope':'retrospective_received_crops_NOT_new_blind_test','bundle_id':model.manifest['bundle_id'],
            'threshold_fixed':model.threshold,'device':model.device,'records':len(rows),'unique_image_hashes':len(cache),
            'model_hashes':model.manifest['source_hashes'],'sets':sets,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (out/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if args.board_heldout:
        selected=[r for r in rows if 'holdout' in r['set'] and not r['calibration_group']]
        print('Initializing FPGA for',len(selected),'historical held-out crops (D19/N17 excluded)',flush=True)
        board_backend.initialize();tested=[]
        for i,row in enumerate(selected):
            folder=work/row['sha256'];folder.mkdir(exist_ok=True)
            _,x,_=preprocess(ROOT/row['path'],False)
            actual=board_backend.infer(model.packed_input(x),folder)
            from quantized_model import full_map
            amap=full_map(actual.pop('fused'))[0]
            error=float(np.max(np.abs(amap-cache[row['sha256']]['map'])))
            assert error<=.00002,(row['path'],error)
            assert abs(actual['score']-row['int8_score'])<=.00002
            tested.append({**row,'board_score':actual['score'],'map_max_abs_error':error,
                           'kernel_ms':actual['kernel_ms'],'board_ms':actual['board_ms']})
            (out/'board_predictions.json').write_text(json.dumps(tested,indent=2),encoding='utf-8')
            print(f"FPGA {i+1}/{len(selected)} {row['image']}: score={actual['score']:.6f} map_error={error:.9g}",flush=True)
        result['board']={'status':'ALL_SELECTED_FULL_MAPS_MATCH_INT8_REFERENCE','count':len(tested),
                         'max_map_abs_error':max(r['map_max_abs_error'] for r in tested),'sets':{}}
        for name in sorted({r['set'] for r in tested}):
            rr=[r for r in tested if r['set']==name]
            result['board']['sets'][name]=metrics(rr,'board_score')
        (out/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({n:{k:v[k] for k in ('count','fp32','int8','prediction_agreement')} for n,v in sets.items()},indent=2),flush=True)
    subprocess.run([sys.executable,str(ROOT/'sim/check_accuracy_provenance.py')],check=True)

if __name__=='__main__':main()
