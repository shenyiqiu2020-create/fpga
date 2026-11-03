"""Reject label leaks and invalid independent-evaluation inputs before inference."""
from pathlib import Path
import json,sys,tempfile
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from evaluate_accuracy import independent_inputs

def rejected(fn):
    try:fn()
    except AssertionError:return
    raise AssertionError('Invalid evaluation input was accepted')

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    Image.new('RGB',(256,256)).save(root/'valid.png')
    row={'image':'valid.png','label':'good','object_group':'N20','role':'holdout'}
    paths,excluded=independent_inputs(root,[row,dict(row,image='unused.png',object_group='d19')])
    assert len(paths)==1 and len(excluded)==1
    rejected(lambda:independent_inputs(root,[dict(row,object_group='')]))
    rejected(lambda:independent_inputs(root,[dict(row,role='train')]))
    rejected(lambda:independent_inputs(root,[row,row]))
    rejected(lambda:independent_inputs(root,[dict(row,image='../outside.png')]))
    Image.new('RGB',(400,300)).save(root/'raw.png')
    rejected(lambda:independent_inputs(root,[dict(row,image='raw.png')]))
result={'status':'PASS','checks':['case_insensitive_calibration_group_excluded','missing_group_rejected','training_role_rejected','duplicate_rejected','path_escape_rejected','uncropped_image_rejected']}
out=Path(__file__).resolve().parent/'results/accuracy_input_validation.json'
out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print('PASS: 6 independent-evaluation input checks')
