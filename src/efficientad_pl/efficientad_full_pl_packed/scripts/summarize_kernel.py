from pathlib import Path
import json,re,hashlib,datetime,zipfile
r=Path(__file__).resolve().parents[1];g=r/'generated';old=r.parent/'efficientad_full_pl_opt'
integrity=json.loads((g/'rtl_integrity.json').read_text())
assert integrity['matches_passed_RTL_simulation'] and integrity['vivado_import_matches']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lat(p):return [int(a) for a in re.findall(r'transaction\s+\d+:\s+(\d+)',p.read_text())]
oldlat=lat(r/'compare_hls/engine_project/sol/sim/report/verilog/result.transaction.rpt')
newlat=lat(g/'final_compute_latency.rpt')
assert len(oldlat)==3 and len(newlat)==20
shapes=json.loads((g/'packed_test_shapes.json').read_text())
comparisons=[{'shape':o,'PE16_cycles':a,'PE32_Q4_cycles':b,'speedup':a/b} for o,a,b in zip(shapes,oldlat,newlat[-3:])]
assert '27 cases' in (r/'hls/engine_project/sol/csim/report/efficientad_engine_csim.log').read_text()
assert 'co-simulation finished: PASS' in (r/'logs/hls_packed_q4_cosim.log').read_text()
assert '24 cases' in (r/'logs/hls_packed.log').read_text()
assert 'PASS' in (r/'experiments/packed_scalar/rtl_24.rpt').read_text() or 'Pass' in (r/'experiments/packed_scalar/rtl_24.rpt').read_text()
timing=(g/'vivado_timing.rpt').read_text();util=(g/'vivado_utilization.rpt').read_text()
v=re.search(r'WNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+(\d+)\s+([-\d.]+)',timing,re.S)
assert v and float(v[1])>=0 and float(v[5])>=0
def use(label):return int(re.search(r'\|\s*'+re.escape(label)+r'\s*\|\s*([\d,]+)',util)[1].replace(',',''))
artifacts={n:{'bytes':(g/n).stat().st_size,'sha256':sha(g/n)} for n in ('efficientad_full.bit','efficientad_full.elf','ax7021_efficientad_full.xsa','ea_model_data.h','ps7_init.tcl')}
assert sha(g/'ea_model_data.h')==sha(old/'generated/ea_model_data.h')
for n in ('mac.hpp','utils.hpp'):
 assert sha(r/'hls/vendor/finn-hlslib'/n)==sha(old/'hls/vendor/finn-hlslib'/n)
assert (g/'ps7_init.tcl').read_text()==(old/'generated/ps7_init.tcl').read_text()
with zipfile.ZipFile(g/'ax7021_efficientad_full.xsa') as z:
 bits=[n for n in z.namelist() if n.endswith('.bit')];assert len(bits)==1
 assert z.read(bits[0])==(g/'efficientad_full.bit').read_bytes()
 for n in z.namelist():
  if n.endswith('ps7_init.tcl'):assert z.read(n).decode().replace('\r\n','\n')==(g/'ps7_init.tcl').read_text()
baseline=json.loads((old/'generated/efficientad_full_board_profile.json').read_text())
assert baseline['timer_conversion_revision']==2
baseline_elf=old/'generated/efficientad_full.elf'
if baseline_elf.exists():assert baseline['host_elf_sha256']==sha(baseline_elf)
manifest=json.loads((g/'deployment_manifest.json').read_text())
out={'status':'OFFLINE_VALIDATED_BOARD_PENDING','timestamp':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
     'architecture':{'PE':32,'SIMD':8,'INT8_MAC_per_cycle':256,'requant_lanes':4,'clock_MHz':50},
     'wns_ns':float(v[1]),'whs_ns':float(v[5]),'resources':{k:use(k) for k in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs')},
     'validation':{'C_cases':27,'final_convolution_RTL_cases':20,'prior_unchanged_resize_RTL_cases':7,'packing_triples':16777216},
     'RTL_integrity':integrity,
     'RTL_comparisons':comparisons,'RTL_three_case_speedup':sum(oldlat)/sum(newlat[-3:]),
     'artifacts':artifacts,'baseline_profile':baseline,'baseline_ELF_rechecked':baseline_elf.exists(),'board_profile':None}
lines=['# DSP 打包计算核结果','', '旧PE16核与新PE32/Q4核均保持50 MHz、相同INT8模型、查表CRC自检。','',
       '| 代表测试 | 旧核周期 | 新核周期 | 加速 |','|---|---:|---:|---:|']
for i,o in enumerate(comparisons):lines.append('| %d | %d | %d | %.3fx |'%(i+1,o['PE16_cycles'],o['PE32_Q4_cycles'],o['speedup']))
lines+=['',f"WNS={float(v[1]):+.3f} ns，WHS={float(v[5]):+.3f} ns。",'资源：'+str(out['resources']),'']
if (g/'efficientad_full_board_profile.json').exists():
 p=json.loads((g/'efficientad_full_board_profile.json').read_text())
 assert p['status']=='BOARD_PROFILE_PASSED' and p['timer_conversion_revision']==2 and p['mailbox_words'][16]==0x50414334
 assert p['host_elf_sha256']==artifacts['efficientad_full.elf']['sha256']
 assert len(p['runs'])==2
 for i,b in enumerate(p['runs']):
  assert len(b['stages'])==29 and abs(b['score']-manifest['int8_reference_scores'][i])<0.00002
 out['status']='BOARD_FULL_MODEL_AND_PROFILE_PASSED';out['board_profile']=p
 out['end_to_end_speedups']=[a['total_us']/b['total_us'] for a,b in zip(baseline['runs'],p['runs'])]
 out['engine_speedups']=[a['engine_us']/b['engine_us'] for a,b in zip(baseline['runs'],p['runs'])]
 out['per_layer_comparison']=[{'name':a['name'],'PE16_us':a['engine_us'],'PE32_Q4_us':b['engine_us'],'speedup':a['engine_us']/b['engine_us']} for a,b in zip(baseline['runs'][0]['stages'],p['runs'][0]['stages'])]
 lines+=['## 板测','', '两张图的58个阶段CRC及最终分数全部通过。','',
         '| 输入 | 旧核计算(ms) | 新核计算(ms) | 旧总耗时(ms) | 新总耗时(ms) | 总加速 |','|---|---:|---:|---:|---:|---:|']
 for a,b in zip(baseline['runs'],p['runs']):
  lines.append('| %s | %.3f | %.3f | %.3f | %.3f | %.3fx |'%(b['image'],a['engine_us']/1000,b['engine_us']/1000,a['total_us']/1000,b['total_us']/1000,a['total_us']/b['total_us']))
 (g/'board_result.json').write_text(json.dumps({'status':out['status'],'profile':p,'artifacts':artifacts,'scope':'two embedded bring-up images, no independent accuracy claim'},indent=2))
else:lines.append('尚未上板，不能将RTL周期加速当成整帧速度。')
(g/'kernel_optimization.json').write_text(json.dumps(out,indent=2))
(r/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('\n'.join(lines))
