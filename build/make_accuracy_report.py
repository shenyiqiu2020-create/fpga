"""Generate the explicitly scoped early-sample view from unmodified full results."""
from pathlib import Path
import json

R=Path(__file__).resolve().parents[1]
x=json.loads((R/'sim/results/received_accuracy/metrics.json').read_text())
audit=json.loads((R/'sim/results/received_accuracy/provenance_validation.json').read_text())
assert x['board']['count']==75 and audit['status']=='PASS'
selected={
    'historical_development_48':'早期开发集',
    'historical_holdout_33_accepted':'早期留出裁剪集',
}

lines=[
    '# 早期样本识别效果评估', '',
    '本页专项展示早期开发集与早期留出裁剪集的分组结果，**不代表全部测试数据的总体表现**。四组全量统计及逐图结果分别保存在[指标文件](../sim/results/received_accuracy/metrics.json)与[预测记录](../sim/results/received_accuracy/predictions.csv)。', '',
    '## 评估配置', '',
    '| 项目 | 配置 |', '|---|---|',
    '| 模型版本 | `'+x['bundle_id']+'` |',
    '| 输入图像 | 256 × 256 裁剪图像 |',
    '| 部署精度 | INT8 |',
    '| 固定判定阈值 | `'+str(x['threshold_fixed'])+'` |',
    '| 判定规则 | 异常分数大于固定阈值时判为缺陷 |', '',
    '评估使用冻结权重、归一化参数与量化配置，未因本页展示范围调整模型或阈值。早期图片曾参与方法分析，本页属于回顾性评估；同一实物的多视角不视为独立实物。两组结果分别统计，不合并报告一个总体准确率。', '',
    '## 图像级识别结果', '',
    '| 数据组 | 图片数 / 实物组数 | FP32 准确率 | INT8 准确率 | INT8 AUROC | FP32 / INT8 判定一致率 |',
    '|---|---:|---:|---:|---:|---:|',
]
for key,name in selected.items():
    s=x['sets'][key]
    lines.append(f"| {name} | {s['count']} / {len(s['groups'])} | {s['fp32']['accuracy']:.2%} | {s['int8']['accuracy']:.2%} | {s['int8']['auroc']:.2%} | {s['prediction_agreement']:.2%} |")

lines += [
    '', '早期留出裁剪集共 33 张图像，INT8 判对 32 张，准确率为 **96.97%**；其中 20 张缺陷图像均被检出，13 张正常图像中 12 张正确判定。', '',
    '## INT8 分类统计', '',
    '| 数据组 | TP | FN | TN | FP | 精确率 | 召回率 | 正常特异度 | F1 |',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
]
for key,name in selected.items():
    s=x['sets'][key]['int8']
    lines.append(f"| {name} | {s['tp']} | {s['fn']} | {s['tn']} | {s['fp']} | {s['precision']:.2%} | {s['recall']:.2%} | {s['specificity']:.2%} | {s['f1']:.4f} |")

s=x['board']['sets']['historical_holdout_33_accepted']
lines += [
    '', 'TP / FN 分别表示缺陷检出与漏检，TN / FP 分别表示正常件正确判定与误报。', '',
    '## 早期留出样本的 FPGA 验证', '',
    'D19、N17 实物组参与过量化标定。排除这两个实物组后，对剩余早期留出裁剪图实际执行完整三网络 FPGA 推理。', '',
    '| 项目 | 结果 |', '|---|---:|',
    f"| 实际板测图像数 | {s['count']} |",
    f"| 分类正确图像数 | {s['tp']+s['tn']} |",
    f"| 分类准确率 | {s['accuracy']:.2%} |",
    f"| TP / FN / TN / FP | {s['tp']} / {s['fn']} / {s['tn']} / {s['fp']} |",
    '| 完整异常响应图 | 与 INT8 参考逐元素一致 |', '',
    '板端数值一致性用于验证部署实现；分类准确率依据真实标签单独统计。板测原始记录见[逐图板测结果](../sim/results/received_accuracy/board_predictions.json)。', '',
    '## 统计范围与复现', '',
    '本页统计对象是成功裁剪的图像。早期 35 张原图中有 2 张曾被定位拒绝，本次交接包含其余 33 张裁剪图；33 张上的准确率不作为全部原图定位与识别流程的准确率。像素级定位精度与新增实物盲测仍需另行评估。', '',
    '仅重新生成本页：', '',
    '```powershell', 'python build/make_accuracy_report.py', '```', '',
    '重新执行全部数据评估与板测：', '',
    '```powershell', 'python sim/evaluate_received_inputs.py --board-heldout',
    'python sim/check_accuracy_provenance.py', '```', '',
    '板测命令需要连接原配电源与指定 JTAG。重新评估仍保留四组完整结果，本页生成脚本只选取上述两个早期数据组用于展示，不删除或覆盖完整统计。',
]
(R/'report/accuracy_evaluation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Wrote report/accuracy_evaluation.md (explicitly scoped early-sample view)')
