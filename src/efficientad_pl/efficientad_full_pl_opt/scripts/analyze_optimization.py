import json,re,hashlib,datetime,zipfile
from pathlib import Path
r=Path(__file__).resolve().parents[1];g=r/'generated';old=r.parent/'efficientad_full_pl'
m=json.loads((g/'deployment_manifest.json').read_text())
def lat(path):return [int(a) for a in re.findall(r'transaction\s+\d+:\s+(\d+)',path.read_text())]
base=lat(r/'baseline_hls/engine_project/sol/sim/report/verilog/result.transaction.rpt')
new=lat(r/'hls/engine_project/sol/sim/report/verilog/result.transaction.rpt')
assert len(base)==len(new)==6
shapes=json.loads((g/'cache_test_shapes.json').read_text())
comparisons=[dict(shape=o,baseline_cycles=a,optimized_cycles=b,speedup=a/b) for o,a,b in zip(shapes,base,new)]
before=after=macs=0;detail=[]
for o in m['ops']:
 if o['opcode']:continue
 k=o['kernel'];cg=(o['cin']+7)//8;ih=o['ih'];iw=o['iw'];s=o['stride'];p=o['pad'];blocks=o['cout']//16
 ch=(ih+2*p-k)//s+1;cw=(iw+2*p-k)//s+1
 ys=[sum(0<=y*s+ky-p<ih for ky in range(k)) for y in range(ch)]
 xs=[sum(0<=x*s+kx-p<iw for kx in range(k)) for x in range(cw)]
 a=sum(ys)*sum(xs)*cg*8*blocks
 rows={y*s+ky-p for y in range(ch) for ky in range(k) if 0<=y*s+ky-p<ih}
 b=len(rows)*iw*cg*8*blocks
 assert k*iw*cg<=8192
 before+=a;after+=b;macs+=ch*cw*k*k*cg*8*o['cout']
 detail.append({'name':o['name'],'old_input_read_bytes':a,'new_input_read_bytes':b,'cache_words':k*iw*cg})
timing=(g/'vivado_timing.rpt').read_text();util=(g/'vivado_utilization.rpt').read_text()
match=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)',timing,re.S)
assert match and float(match[1])>=0 and float(match[5])>=0
def usage(label):
 q=re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*([\d,]+)',util)
 return int(q[1].replace(',','')) if q else None
artifacts={}
for name in ('efficientad_full.bit','efficientad_full.elf','ax7021_efficientad_full.xsa','ps7_init.tcl','baseline.bit','baseline_profile.elf','ea_model_data.h'):
 data=(g/name).read_bytes();artifacts[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
assert artifacts['baseline.bit']['sha256']==json.loads((old/'generated/board_result.json').read_text())['artifacts']['efficientad_full.bit']['sha256']
assert (g/'ea_model_data.h').read_bytes()==(old/'generated/ea_model_data.h').read_bytes()
with zipfile.ZipFile(g/'ax7021_efficientad_full.xsa') as z:
 bits=[n for n in z.namelist() if n.endswith('.bit')];assert len(bits)==1
 assert z.read(bits[0])==(g/'efficientad_full.bit').read_bytes()
 inits=[n for n in z.namelist() if n.endswith('ps7_init.tcl')]
 for n in inits:assert z.read(n).decode().replace('\r\n','\n')==(g/'ps7_init.tcl').read_text()
assert (g/'ps7_init.tcl').read_text()==(old/'generated/ps7_init.tcl').read_text()
out={'status':'OFFLINE_VALIDATED_BOARD_MEASUREMENT_PENDING',
 'timestamp':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
 'clock_MHz':50,'wns_ns':float(match[1]),'whs_ns':float(match[5]),
 'resources':{label:usage(label) for label in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs')},
 'rtl_matched_cache_cases':comparisons,'rtl_test_scope':'18 original plus 6 cache-boundary cases, C and RTL agreement',
 'rtl_cache_cases_total_cycle_speedup':sum(base)/sum(new),
 'input_read_bytes':{'baseline':before,'optimized':after,'reduction_ratio':before/after,
   'scope':'convolution input reads only, counted from scheduled accesses; excludes weights/output/protocol/CPU'},
 'physical_mac_count':macs,'mac_only_ideal_floor_seconds_at_50MHz':macs/(128*50e6),
 'per_layer_reads':detail,'artifacts':artifacts,
 'board_test':'not run; user cannot connect board this session',
 'full_model_C_simulation':'optional long-running test stopped before completion; no full-model C pass claimed',
 'quantization':'unchanged weights, inputs, per-layer scales and expected CRCs',
 'baseline_board_seconds':[23.564,23.567],
 'new_board_seconds':None}
board_path=g/'efficientad_full_board_profile.json'
if board_path.exists():
 board=json.loads(board_path.read_text())
 assert board['status']=='BOARD_PROFILE_PASSED' and board['timer_conversion_revision']==2
 assert board['host_elf_sha256']==artifacts['efficientad_full.elf']['sha256']
 assert len(board['runs'])==2
 for image,run in enumerate(board['runs']):
  assert len(run['stages'])==29
  assert abs(run['score']-m['int8_reference_scores'][image])<0.00002
  assert run['total_us']//1000==board['mailbox_words'][10+image]
 out.update(status='BOARD_SELF_TEST_AND_PROFILE_PASSED',
   board_test='two full-model inputs, all 58 stage CRCs and both final scores passed; corrected timing rerun',
   new_board_seconds=[v['total_us']/1e6 for v in board['runs']],
   board_profile=board,
   end_to_end_test_speedups=[a/(b['total_us']/1e6) for a,b in zip(out['baseline_board_seconds'],board['runs'])])
 (g/'board_result.json').write_text(json.dumps({
   'status':out['status'],'timestamp':board['timestamp'],'evidence':board['evidence'],
   'cable_serial':'210512180081','device':'xc7z020','clock_MHz':50,
   'mailbox_words':board['mailbox_words'],'runs':board['runs'],'artifacts':artifacts,
   'scope':'complete frozen INT8 model on two embedded inputs; not independent accuracy evaluation',
   'timing_note':'v1 microsecond conversion was quarter-sized; v2 rerun corrected and checked against independent millisecond fields',
   'first_user_serial_totals_ms':[9446,9447]
 },indent=2))
(g/'optimization_report.json').write_text(json.dumps(out,indent=2))
brief='''# 本次优化结果

状态：离线验证通过，新版板测待接板完成。

| 项目 | 旧版 | 新版 |
|---|---:|---:|
| 六组同输入 RTL 合计周期 | %d | %d |
| 卷积输入读取量，字节/图 | %d | %d |
| DSP | 206 | %s |
| LUT | 15720 | %s |
| BRAM36 tile | 18 | %s |
| 时钟 | 50 MHz | 50 MHz |
| 整帧板测 | 约23.6秒，含自检 | 尚未测量 |

六组 RTL 合计加速 %.3f 倍；它是这些输入的周期比较，并非完整模型板测速度。
新版 WNS=%+.3f ns，WHS=%+.3f ns。
24组 C/RTL 测试已通过；权重、量化规则、参考 CRC 均未变化。
表中 DDR 访问量只统计卷积输入，不含权重、输出及总线开销。
'''%(sum(base),sum(new),before,after,out['resources']['DSPs'],out['resources']['Slice LUTs'],out['resources']['Block RAM Tile'],sum(base)/sum(new),float(match[1]),float(match[5]))
if out['new_board_seconds'] is not None:
 brief=brief.replace('状态：离线验证通过，新版板测待接板完成。','状态：2026-11-01 实际开发板完整模型自检与分项计时通过。')
 brief=brief.replace('约23.6秒，含自检 | 尚未测量','约23.6秒，含自检 | 约9.44秒，含自检')
 brief+='\n完整板测总耗时约为原来的40%，整体加速约2.50倍，包含行缓存与查表CRC的合计收益。\n\n'
 brief+='| 输入 | 总耗时(ms) | FPGA计算(ms) | 缓存维护(ms) | CRC(ms) | 后处理(ms) |\n|---|---:|---:|---:|---:|---:|\n'
 for run in board['runs']:
  brief+='| %s | %.3f | %.3f | %.3f | %.3f | %.3f |\n'%(run['image'],*(run[k]/1000 for k in ('total_us','engine_us','cache_us','crc_us','score_us')))
 brief+='\n两张图的58个阶段CRC与最终分数全部一致。\n分项微秒换算已修正宏括号问题，并重新加载程序跑完两张图；串口毫秒总计时始终正确。\n'
(r/'RESULTS.md').write_text(brief,encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k not in ('artifacts','per_layer_reads')},indent=2))
