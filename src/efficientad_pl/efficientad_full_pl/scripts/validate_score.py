from pathlib import Path
import ctypes,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
GEN=ROOT/'generated'
manifest=json.loads((GEN/'deployment_manifest.json').read_text())
MODEL=Path(r'C:\Users\sheny\Documents\ChatGPT\fpga\github_fpga\build\work\handoff\received_20261026\tie_mount_20261026_model')
n=np.load(MODEL/'normalization.npz',allow_pickle=False)
features=np.load(GEN/'quantized_features.npz',allow_pickle=False)
dll=ctypes.CDLL(str(ROOT/'_build/native_score.dll'))
fn=dll.ea_compute_score
fn.argtypes=[ctypes.c_void_p]*3+[ctypes.c_float]*3+[ctypes.c_void_p]*4
fn.restype=ctypes.c_float
mean=np.ascontiguousarray(n['teacher_mean'].ravel(),dtype=np.float32)
std=np.ascontiguousarray(n['teacher_std'].ravel(),dtype=np.float32)
quant=np.array([n[k].item() for k in ('q_st_start','q_st_end','q_ae_start','q_ae_end')],np.float32)
ts,ss,aas=map(np.float32,manifest['final_scales'])
scores=[]
for image,name in enumerate(('D19_01','N17_03')):
    t,s,a=[np.ascontiguousarray(features[k][image].transpose(1,2,0)) for k in ('teacher','student','autoencoder')]
    fused=np.empty((56,56),np.float32)
    score=fn(t.ctypes.data,s.ctypes.data,a.ctypes.data,float(ts),float(ss),float(aas),
        mean.ctypes.data,std.ctypes.data,quant.ctypes.data,fused.ctypes.data)
    tn=(t.astype(np.float32)*ts-mean)/std
    d=tn-s[:,:,:384].astype(np.float32)*ss
    da=a.astype(np.float32)*aas-s[:,:,384:].astype(np.float32)*ss
    st=np.sum(d*d,axis=2,dtype=np.float64).astype(np.float32)/np.float32(384)
    ae=np.sum(da*da,axis=2,dtype=np.float64).astype(np.float32)/np.float32(384)
    expected=np.float32(.5)*(np.float32(.1)*(st-quant[0])/(quant[1]-quant[0]))+np.float32(.5)*(np.float32(.1)*(ae-quant[2])/(quant[3]-quant[2]))
    np.testing.assert_allclose(fused,expected,rtol=2e-6,atol=2e-6)
    padded=np.pad(expected,4)
    p=np.clip((np.arange(256,dtype=np.float32)+.5)/4-.5,0,63)
    lo=np.floor(p).astype(int); hi=np.minimum(lo+1,63); w=p-lo.astype(np.float32)
    top=(1-w[None,:])*padded[lo[:,None],lo[None,:]]+w[None,:]*padded[lo[:,None],hi[None,:]]
    bot=(1-w[None,:])*padded[hi[:,None],lo[None,:]]+w[None,:]*padded[hi[:,None],hi[None,:]]
    expected_score=float(np.max((1-w[:,None])*top+w[:,None]*bot))
    assert abs(score-expected_score)<2e-6
    scores.append(score)
    print(name,'quantized score=',score,'predicted=',score>manifest['threshold'],'independent postprocess PASS',flush=True)
    np.save(GEN/(name+'_quantized_fused.npy'),fused,allow_pickle=False)
out='#ifndef EA_EXPECTED_H\n#define EA_EXPECTED_H\nstatic const float ea_expected_scores[2]={'
out+=','.join(format(s,'.9g')+'f' for s in scores)+'};\n#endif\n'
(GEN/'ea_expected.h').write_text(out,encoding='ascii')
manifest['int8_reference_scores']=scores
manifest['int8_reference_predictions']=[s>manifest['threshold'] for s in scores]
(GEN/'deployment_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
