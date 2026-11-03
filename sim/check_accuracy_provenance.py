"""Check the matching historical model column; never change predictions."""
from pathlib import Path
import csv,json
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'sim/results/received_accuracy'
manifest=json.loads((ROOT/'data/test_inputs/evaluation_manifest.json').read_text())
expected={r['path']:r for r in manifest['images']}
rows=list(csv.DictReader((out/'predictions.csv').open(encoding='utf-8')))
for row in rows:
    source=expected[row['path']]
    assert source['sha256']==row['sha256']
    row['historical_fp32_score']=source['historical_fp32_score']
    row['historical_score_column']=source['historical_score_column']
    assert abs(float(row['fp32_score'])-source['historical_fp32_score'])<2e-6,row['path']
with (out/'predictions.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
board_path=out/'board_predictions.json'
if board_path.exists():
    board_rows=json.loads(board_path.read_text())
    for row in board_rows:
        source=expected[row['path']]
        assert source['sha256']==row['sha256']
        row['historical_fp32_score']=source['historical_fp32_score']
        row['historical_score_column']=source['historical_score_column']
    board_path.write_text(json.dumps(board_rows,indent=2),encoding='utf-8')
result=json.loads((out/'metrics.json').read_text())
for name,stats in result['sets'].items():
    rr=[r for r in rows if r['set']==name]
    stats['fp32_historical_max_abs_score_error']=max(abs(float(r['fp32_score'])-r['historical_fp32_score']) for r in rr)
    stats['historical_score_column']=rr[0]['historical_score_column']
    for mistake in stats['int8_mistakes']:
        source=expected[mistake['path']]
        mistake['historical_fp32_score']=source['historical_fp32_score']
        mistake['historical_score_column']=source['historical_score_column']
(out/'metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
audit={'status':'PASS','rows':len(rows),'max_matching_model_score_error':max(s['fp32_historical_max_abs_score_error'] for s in result['sets'].values()),
       'selection':'Expanded CSV old_score matches current bundle; historical CSV new_score matches current bundle',
       'predictions_modified':False,'threshold_modified':False,'weights_modified':False}
(out/'provenance_validation.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
print(json.dumps(audit,indent=2))
