"""Local-only presentation UI with explicit FPGA and software backends."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,base64,csv,hashlib,io,json,mimetypes,re,sys,threading,time,uuid,webbrowser
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];STATIC=Path(__file__).parent/'static'
sys.path.insert(0,str(ROOT/'src/model'))
from quantized_model import FrozenModel,preprocess,full_map
import board_backend
from image_library import ImageLibrary
LIBRARY=ImageLibrary(ROOT)
WORK=ROOT/'build/work/demo';WORK.mkdir(parents=True,exist_ok=True)
STATE={'connected':False,'busy':False,'jobs':{},'history':[]};LOCK=threading.Lock();MODEL=None

def model():
    global MODEL
    if MODEL is None:MODEL=FrozenModel()
    return MODEL

def pictures(rgb,amap,threshold,work):
    a=np.clip(amap/max(threshold*3,1e-6),0,1)
    stops=np.array([[9,28,66],[19,94,150],[23,179,173],[246,206,75],[248,78,65]],np.float32)
    t=a*4;i=np.minimum(t.astype(int),3);f=(t-i)[...,None]
    heat=np.clip(stops[i]*(1-f)+stops[i+1]*f,0,255).astype(np.uint8)
    alpha=(a*.65)[...,None];overlay=np.clip(rgb*(1-alpha)+heat*alpha,0,255).astype(np.uint8)
    for name,img in [('input',rgb),('heatmap',heat),('overlay',overlay)]:Image.fromarray(img).save(work/(name+'.png'))

def process(jid,payload):
    j=STATE['jobs'][jid];work=WORK/jid;work.mkdir()
    start=time.perf_counter()
    try:
        j.update(status='running',message='准备图像',stage=0)
        provenance={}
        if payload.get('test_image'):
            key=payload['test_image'];src=LIBRARY.source(key)
            if src is None:raise ValueError('测试图片不存在，请刷新图片库')
            item=LIBRARY.by_id[key];label=item['name']
            provenance={'test_image_id':key,'dataset':item['set'],
                        'ground_truth':item['label'],'object_group':item['object_group']}
        elif payload.get('sample') in ('d19_01','n17_03'):
            src=ROOT/'data/samples'/(payload['sample']+'.png');label=payload['sample']
        else:
            raw=base64.b64decode(payload['image'].split(',')[-1],validate=True)
            if len(raw)>10*1024*1024:raise ValueError('图片不能超过 10 MB')
            src=work/'uploaded_image.png'
            with Image.open(io.BytesIO(raw)) as im:
                if im.width*im.height>24000000:raise ValueError('图片尺寸过大')
                im.convert('RGB').save(src)
            label=str(payload.get('name','uploaded image'))[:120]
        rgb,x,crop=preprocess(src,bool(payload.get('auto_crop',True)))
        m=model();backend=payload.get('backend','fpga')
        def progress(oi,name):j.update(stage=oi+1,message=name)
        if backend=='fpga':
            if not STATE['connected']:raise ValueError('请先初始化 FPGA 开发板')
            v=board_backend.infer(m.packed_input(x),work,progress)
            amap=full_map(v.pop('fused'))[0];score=v['score'];threshold=v['threshold']
            assert abs(float(amap.max())-score)<=.00002,'Board score/map mismatch'
            details=v
        elif backend in ('int8_reference','fp32_reference'):
            v=m.infer_int8(x,progress) if backend=='int8_reference' else m.infer_fp32(x)
            amap=v['maps'][0];score=v['scores'][0];threshold=m.threshold
            details={'backend':backend,'reference_ms':v['elapsed_seconds']*1000,'device':v['device']}
        else:raise ValueError('Unknown backend')
        pictures(rgb,amap,threshold,work);np.save(work/'anomaly_map.npy',amap)
        result={'id':jid,'name':label,'score':score,'threshold':threshold,'defect':bool(score>threshold),
                'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),'request_ms':(time.perf_counter()-start)*1000,
                'input_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'crop':crop,
                'bundle_id':m.manifest['bundle_id'],**details,**provenance}
        (work/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        STATE['history'].insert(0,result);j.update(status='done',stage=29,message='检测完成',result=result)
    except Exception as e:
        j.update(status='error',message=str(e));(work/'error.txt').write_text(str(e),encoding='utf-8')
    finally:STATE['busy']=False;LOCK.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,body,status=200,ctype='application/json; charset=utf-8'):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/api/status':return self.reply({'connected':STATE['connected'],'busy':STATE['busy'],'history':STATE['history'][:30]})
        if path=='/api/test-images':return self.reply(LIBRARY.public)
        m=re.fullmatch(r'/test-images/([a-f0-9]{20})\.png',path)
        if m:
            p=LIBRARY.source(m[1])
            return self.reply(p.read_bytes(),ctype='image/png') if p else self.reply({'error':'Not found'},404)
        if path=='/api/evidence':
            return self.reply({'hardware':json.loads((ROOT/'board/evidence/overlap_results.json').read_text()),
                              'historical_accuracy':json.loads((ROOT/'sim/results/historical_metrics.json').read_text()),
                              'received_accuracy':json.loads((ROOT/'sim/results/received_accuracy/metrics.json').read_text())})
        if path.startswith('/api/jobs/'):
            v=STATE['jobs'].get(path.rsplit('/',1)[-1]);return self.reply(v or {'error':'Not found'},200 if v else 404)
        if path=='/api/export':
            out=io.StringIO();fields=['timestamp','name','backend','score','threshold','defect','kernel_ms','board_ms','request_ms','input_sha256','dataset','ground_truth','object_group','test_image_id'];w=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(STATE['history']);return self.reply(('\ufeff'+out.getvalue()).encode('utf-8'),ctype='text/csv; charset=utf-8')
        m=re.fullmatch(r'/results/([a-f0-9]{32})/(input|heatmap|overlay)\.png',path)
        if m:
            p=WORK/m[1]/(m[2]+'.png')
            return self.reply(p.read_bytes(),ctype='image/png') if p.exists() else self.reply({'error':'Not found'},404)
        m=re.fullmatch(r'/samples/(d19_01|n17_03)\.png',path)
        if m:return self.reply((ROOT/'data/samples'/(m[1]+'.png')).read_bytes(),ctype='image/png')
        p=STATIC/('index.html' if path=='/' else path.lstrip('/'))
        if p.resolve().is_relative_to(STATIC.resolve()) and p.is_file():return self.reply(p.read_bytes(),ctype=mimetypes.guess_type(p)[0] or 'application/octet-stream')
        self.reply({'error':'Not found'},404)
    def do_POST(self):
        host=self.headers.get('Host','');origin=self.headers.get('Origin')
        if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}') or (origin and origin not in ('http://'+host,)):
            return self.reply({'error':'Local origin required'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<15*1024*1024:return self.reply({'error':'Invalid request size'},413)
            payload=json.loads(self.rfile.read(size))
        except Exception:return self.reply({'error':'Invalid JSON'},400)
        if self.path=='/api/connect':
            if not LOCK.acquire(False):return self.reply({'error':'已有任务运行'},409)
            STATE['busy']=True
            try:
                v=board_backend.initialize();STATE['connected']=True
                return self.reply({'connected':True,'clock_mhz':v['clock_mhz']})
            except Exception as e:STATE['connected']=False;return self.reply({'error':str(e)},503)
            finally:STATE['busy']=False;LOCK.release()
        if self.path=='/api/jobs':
            if 'test_image' in payload and (not isinstance(payload['test_image'],str) or payload['test_image'] not in LIBRARY.by_id):
                return self.reply({'error':'测试图片不存在，请刷新图片库'},400)
            if not LOCK.acquire(False):return self.reply({'error':'请等待当前任务完成'},409)
            STATE['busy']=True;jid=uuid.uuid4().hex
            STATE['jobs'][jid]={'id':jid,'status':'queued','message':'排队中','stage':0}
            threading.Thread(target=process,args=(jid,payload),daemon=True).start()
            return self.reply({'id':jid},202)
        self.reply({'error':'Not found'},404)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--open',action='store_true');a=p.parse_args()
    srv=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
    print('EfficientAD demo: http://127.0.0.1:'+str(a.port),flush=True)
    if a.open:webbrowser.open('http://127.0.0.1:'+str(a.port))
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
    finally:srv.server_close()
if __name__=='__main__':main()
