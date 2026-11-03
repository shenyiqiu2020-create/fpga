from pathlib import Path
import json,re,hashlib,datetime
r=Path(__file__).resolve().parents[1];g=r/'generated'
read=lambda n:json.loads((g/n).read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
hw=read('hardware_validation.json');rtl=read('rtl_integrity.json')
new=read('efficientad_full_board_profile.json');old=read('baseline_board_profile.json')
base=read('baseline_kernel_summary.json')
assert new['status']=='BOARD_PROFILE_PASSED' and abs(new['board_clock_MHz']-125)<.01
assert abs(new['ARM_clock_MHz']-666.666667)<.01
assert rtl['matches_passed_RTL_simulation'] and rtl['vivado_import_matches']
assert sha(g/'efficientad_full.elf')==new['host_elf_sha256']
assert all(sha(g/n)==v for n,v in hw['artifacts'].items())
assert all(sha(g/n)==v for n,v in read('frozen_inputs_sha256.json').items())
source=(r/'hls/efficientad_engine.cpp').read_text()
assert 'PE=40, SIMD=8, MAX_KWORDS=512' in source and '#pragma HLS DATAFLOW' in source
line=source[:source.index('for(ap_uint<10> z=0;z<kw;++z)')].count('\n')+1
log=(r/'logs/hls_prepare.log').read_text()
assert re.search(r"Pipelining result.*Final II = 1,.*loop 'VITIS_LOOP_"+str(line)+r'_',log),'MAC II changed'
assert 'EFFICIENTAD ENGINE TEST PASSED: 31 cases.' in log
assert 'WARNING: [HLS 200-871]' not in log,'Unresolved HLS timing warning'
text=(g/'vivado_utilization.rpt').read_text();resources={}
for name in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):
 m=re.search(r'\|\s*'+re.escape(name)+r'\*?\s*\|\s*([\d,]+)',text)
 assert m,('Missing resource',name)
 resources[name]=int(m[1].replace(',',''))
comparisons=[]
for a,b in zip(old['runs'],new['runs']):
 assert a['image']==b['image'] and a['score']==b['score']
 assert [s['crc'] for s in a['stages']]==[s['crc'] for s in b['stages']]
 comparisons.append({'image':b['image'],'old_engine_us':a['engine_us'],'new_engine_us':b['engine_us'],
  'old_total_us':a['total_us'],'new_total_us':b['total_us'],
  'engine_speedup':a['engine_us']/b['engine_us'],'total_speedup':a['total_us']/b['total_us'],
  'score':b['score'],'predicted_defect':b['predicted_defect'],
  'stages':[{'name':y['name'],'old_engine_us':x['engine_us'],'new_engine_us':y['engine_us'],
    'speedup':x['engine_us']/max(1,y['engine_us']),'crc':y['crc']} for x,y in zip(a['stages'],b['stages'])]})
reduction=1-sum(v['new_engine_us'] for v in comparisons)/sum(v['old_engine_us'] for v in comparisons)
out={'status':'BOARD_FULL_MODEL_OVERLAP125_PROFILE_PASSED',
 'timestamp':datetime.datetime.now().astimezone().isoformat(),
 'architecture':{'PE':40,'SIMD':8,'INT8_MAC_per_cycle':320,'requant_lanes':4,'MAC_II':1,
  'clock_MHz':125,'AXI_address_bits':32,'postprocessing_overlap':'per-row DATAFLOW, 1280-bit FIFO depth 4'},
 'wns_ns':hw['wns_ns'],'whs_ns':hw['whs_ns'],'resources':resources,'baseline_resources':base['resources'],
 'model_and_quantization_unchanged':True,'validation':{'C_cases':31,'RTL_cases':31,'board_images':2,'board_stage_CRCs':58},
 'board_clock_MHz':new['board_clock_MHz'],'ARM_clock_MHz':new['ARM_clock_MHz'],
 'comparison':comparisons,'engine_time_reduction_fraction':reduction,
 'artifacts':{n:{'sha256':sha(g/n),'bytes':(g/n).stat().st_size} for n in ('efficientad_full.bit','efficientad_full.elf','ax7021_efficientad_full.xsa','ps7_init.tcl','ea_model_data.h','ea_expected.h')}}
(g/'overlap_results.json').write_text(json.dumps(out,indent=2))
rows='\n'.join('| %s | %.3f s | %.3f s | %.3fx | %.3f s | %.3f s |'%(v['image'],v['old_engine_us']/1e6,v['new_engine_us']/1e6,v['engine_speedup'],v['old_total_us']/1e6,v['new_total_us']/1e6) for v in comparisons)
details='\n'.join('| %s | %.3f ms | %.3f ms | %.3fx |'%(v['name'],v['old_engine_us']/1000,v['new_engine_us']/1000,v['speedup']) for v in comparisons[0]['stages'])
rr='\n'.join('| %s | %d | %d |'%(n,base['resources'][n],resources[n]) for n in resources)
report=f"""# PE40 125 MHz 卷积后处理重叠版实测

新 RTL 已通过 31 组 C 测试、31 组 C/RTL 对照、125 MHz 布线后时序与实际开发板两张图检查。
PE40、SIMD8、四路重定标、频率、模型和 INT8/Q30 参数保持不变；仅调整卷积阶段调度。

| 图片 | 原 PE40 核耗时 | 重叠版核耗时 | 加速 | 原含自检总耗时 | 新含自检总耗时 |
|---|---:|---:|---:|---:|---:|
{rows}

平均核耗时减少 {reduction*100:.1f}%。WNS={hw['wns_ns']:+.3f} ns，WHS={hw['whs_ns']:+.3f} ns。

| 资源 | 原 PE40 | 重叠版 |
|---|---:|---:|
{rr}

## 实现与验证

- 每行拆分成 MAC 生产者与重定标/池化/DDR 写回消费者，通过 1280-bit、深度 4 的 FIFO 传递 40 路 INT32 累加结果。
- 两阶段在同一行的不同输出位置之间重叠；每行结束排空 FIFO 后再更新行缓存。权重加载、行缓存和输出顺序保留。
- ReLU、Q30 舍入、饱和、2x2 池化、Resize 算法与模型完全不变。乘加 II=1，四路重定标没有复制。
- 31 组 supplied vectors 的 C/RTL 对照通过；两张图的 58 个阶段 CRC 与原 golden、两个最终分数逐项一致。
- 核 125 MHz、ARM 约 666.667 MHz，PS 初始化与原版完全相同。临时 JTAG 下载，无 Flash 写入。
- 综合、打包、通过 C/RTL 仿真的 RTL 与 Vivado 导入文件哈希一致。原 PE40、PE32 与 D: 工程保留。
- 总耗时仍包含 CRC 自检、缓存维护、PS 评分、复制和串口输出；两张图不构成独立量化精度评估。

## 逐层核耗时（第一张图）

| 阶段 | 原 PE40 | 重叠版 | 时间比 |
|---|---:|---:|---:|
{details}
"""
(r/'results.md').write_text(report,encoding='utf-8')
print(json.dumps({'status':out['status'],'resources':resources,'engine_time_reduction':reduction,
 'runs':[{k:v[k] for k in ('image','old_engine_us','new_engine_us','old_total_us','new_total_us')} for v in comparisons]},indent=2))
