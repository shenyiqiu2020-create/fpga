"""Write the accuracy appendix from actual fresh inference and board evidence."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
x=json.loads((R/'sim/results/received_accuracy/metrics.json').read_text())
audit=json.loads((R/'sim/results/received_accuracy/provenance_validation.json').read_text())
assert x['board']['count']==75 and audit['status']=='PASS'
names={'historical_development_48':'早期开发','historical_holdout_33_accepted':'早期留出裁剪',
       'expanded_development_155':'扩批开发','expanded_holdout_48':'扩批留出'}
lines=['# 模型识别精度实测','',
 '本次使用冻结包 `'+x['bundle_id']+'`，不改权重、归一化、量化或阈值。阈值固定为 `'+str(x['threshold_fixed'])+'`，分数大于阈值判异常。',
 '', '## 数据及防混用','',
 '用户新提供四组284张256×256裁剪图，逐图核对原交接清单SHA256，得到224种图片文件哈希。图片、标签和来源在 `data/test_inputs/`；不同组存在重复或不同裁剪版本，不能直接合并报告总体准确率。交接说明明确这些图片已参与方法排查，本次是回顾性复测，不是新的独立盲测。',
 '', '扩批CSV中的 `old_score/old_threshold` 对应当前冻结模型，`new_score` 是另一模型；早期CSV则由 `new_score/new_threshold` 对应当前模型。逐图FP32重跑与相应历史模型分数最大误差为 '+str(audit['max_matching_model_score_error'])+'。',
 '', '## 重新运行 FP32 与部署 INT8 参考','',
 '| 数据组 | 图片/实物组数 | FP32 准确率 | INT8 准确率 | INT8 AUROC | FP32/INT8判定一致 |',
 '|---|---:|---:|---:|---:|---:|']
for key,name in names.items():
    s=x['sets'][key]
    lines.append(f"| {name} | {s['count']} / {len(s['groups'])} | {s['fp32']['accuracy']:.2%} | {s['int8']['accuracy']:.2%} | {s['int8']['auroc']:.2%} | {s['prediction_agreement']:.2%} |")
lines+=['','| INT8 数据组 | TP | FN | TN | FP | 精确率 | 召回率 | 正常特异度 | F1 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for key,name in names.items():
    s=x['sets'][key]['int8']
    lines.append(f"| {name} | {s['tp']} | {s['fn']} | {s['tn']} | {s['fp']} | {s['precision']:.2%} | {s['recall']:.2%} | {s['specificity']:.2%} | {s['f1']:.4f} |")
lines+=['','扩批留出48张包含32张缺陷、16张正常：INT8将16张正常全部误报。FP32同组也误报15张正常，仅判对33/48。当前模型的扩批误报问题不能只归因于INT8；也不能只展示早期96.97%的较好数字。','','## 实际 FPGA 测试','',
 '排除量化标定实物D19、N17的全部照片，对两组留出中剩余75张实际上传并执行完整三网络。每张256×256异常响应图与整数参考逐点比较，最大绝对误差为 '+str(x['board']['max_map_abs_error'])+'。板端准确率如下：','',
 '| 板端子集 | 数量 | 判对 | 准确率 | TP/FN/TN/FP |','|---|---:|---:|---:|---|']
for key,s in x['board']['sets'].items():
    lines.append(f"| {names[key]}（排除标定组） | {s['count']} | {s['tp']+s['tn']} | {s['accuracy']:.2%} | {s['tp']}/{s['fn']}/{s['tn']}/{s['fp']} |")
lines+=['', '硬件与量化参考一致表示实现数值正确，不代表识别准确率100%。板测逐图分数、耗时与图像误差见 `sim/results/received_accuracy/board_predictions.json`。',
 '', '## 定位与统计边界','',
 '本次输入已经裁剪，不能用其验证原图定位器。早期35张原图中2张曾被定位拒绝，当前只交接33张成功裁剪图，失败原图已不在交接包；拒绝统计继续明确标为历史记录。历史全流程自动正确处理为32/35=91.43%，不能把32/33=96.97%写成全35张准确率。',
 '', '同一实物存在多个视角，图像条目不等于独立实物数量。D19/N17曾用于INT8量化标定，不能用于估计独立量化准确率。缺少像素掩膜标注，未评估像素定位准确率、像素AUROC或IoU。',
 '', '## 复现','', '```powershell','python sim/evaluate_received_inputs.py --board-heldout','python sim/check_accuracy_provenance.py','```','',
 '命令会重新运行，板测须接通原配电源与指定JTAG线缆。只需查看既有结果时读取JSON/CSV即可。新盲测另用 `sim/evaluate_accuracy.py` 并按实物组隔离训练、验证与标定数据；不得对同一回顾测试集调参后再称盲测。',
 '', '当前工作优先是排查扩批正常误报，在独立验证集上校准后，再采集未见实物盲测；这次没有为改善报表而改动模型或阈值。']
(R/'report/accuracy_evaluation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Wrote report/accuracy_evaluation.md')
