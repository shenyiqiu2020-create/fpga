"""Real board test of uploaded images; not a statistical accuracy estimate."""
from pathlib import Path
import sys,json,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/model'),str(ROOT/'src/demo')]
from quantized_model import FrozenModel,preprocess,full_map
import board_backend
out=ROOT/'sim/results/demo_board';out.mkdir(parents=True,exist_ok=True)
print('Initializing verified PL bitstream and new PS transport service',flush=True)
v=board_backend.initialize();(out/'initialization.log').write_text(v['log'])
m=FrozenModel();rows=[]
for name in ('d19_01','n17_03'):
    work=out/name;work.mkdir(exist_ok=True)
    _,x,_=preprocess(ROOT/'data/samples'/(name+'.png'),False)
    q=m.infer_int8(x)
    z=board_backend.infer(m.packed_input(x),work)
    board_map=full_map(z.pop('fused'))[0]
    error=float(np.max(np.abs(board_map-q['maps'][0])))
    assert abs(z['score']-q['scores'][0])<=.00002,(name,z['score'],q['scores'][0])
    assert error<=.00002,(name,error)
    assert (z['score']>z['threshold'])==(name=='d19_01')
    np.save(work/'board_map.npy',board_map)
    row={'image':name,**z,'map_max_abs_error':error,'reference_score':q['scores'][0]}
    rows.append(row);print(json.dumps(row),flush=True)
(out/'validation.json').write_text(json.dumps({'status':'UPLOADED_IMAGES_AND_FULL_MAP_BOARD_VERIFIED','images':rows,'scope':'2 calibration images; not independent accuracy evaluation','timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')},indent=2))
