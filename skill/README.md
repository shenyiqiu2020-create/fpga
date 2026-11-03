# 可复用 FPGA 验证与优化 Skill

本目录包含一套可独立复制到其他工程的 Agent Skill：**`fpga-accelerator-validation`**。它把数值参考、源码与 RTL/IP 的身份、布线时序、板端内存一致性和性能口径连成可核对的流程。适用于卷积、点积、图像处理、信号处理等计算核，不要求使用本项目的模型、开发板、地址或并行度。

## 文件结构

```text
skill/
├─ README.md
└─ fpga-accelerator-validation/
   ├─ SKILL.md
   ├─ agents/openai.yaml
   ├─ scripts/
   │  ├─ check_manifest.py
   │  ├─ read_timing.py
   │  └─ compare_tensors.py
   ├─ references/
   │  ├─ validation_workflow.md
   │  ├─ hls_optimization.md
   │  ├─ failure_patterns.md
   │  ├─ project_example.md
   │  └─ sources.md
   └─ assets/
      ├─ validation_record.md
      └─ measurement_example.json
```

入口遵循 Agent Skills 的 `SKILL.md` + YAML 元数据约定。执行路径和核心约束放在入口；更细的数值、HLS、失败处理和项目案例按需读取。没有安装其他网上 Skill，也没有自动引入其权限或依赖。

## 给 AI 使用

将整个 `fpga-accelerator-validation/` 文件夹复制到目标工具支持的 Skill 目录；保留文件夹名及 `SKILL.md` 大小写。例如支持 Codex 仓库级技能的环境可使用 `.agents/skills/fpga-accelerator-validation/`。本仓库按比赛目录要求把可提交源文件放在 `skill/` 中，未额外复制一份隐藏版本。

也可以不安装，直接让 AI 读取这里的 `SKILL.md`：

> 使用 $fpga-accelerator-validation，按 skill/fpga-accelerator-validation/SKILL.md 检查这个 HLS 核。用户报告源码已改但板端输出没变。先核对参考、实际导入 RTL 和 bit/ELF 身份，再决定要重跑哪一步。

> 使用这个 Skill 优化现有算子，保持算法和定点规则不变。先看逐阶段计时和时序关键路径，选择一次可归因的改动，交付数值、RTL、时序与板测证据以及资源代价。

> 使用这个 Skill 整理交付证据。板卡当前不在身边：完成可执行检查，将尚未执行的板测写清楚，不使用旧截图证明新版本。

## 不依赖 AI 也能使用

Python 3.9+ 可运行清单和 Vivado 时序检查；张量比较另外需要 NumPy。所有脚本提供 `--help`，以参数取得路径，默认不修改输入。

从当前项目根目录运行：

```text
python skill/fpga-accelerator-validation/scripts/check_manifest.py data/submission_manifest.json --root .
python skill/fpga-accelerator-validation/scripts/read_timing.py build/reports/vivado_timing.rpt
python skill/fpga-accelerator-validation/scripts/compare_tensors.py expected.npy actual.npy
python skill/fpga-accelerator-validation/scripts/compare_tensors.py expected.bin actual.bin --dtype int32
python sim/test_delivery_tools.py
python sim/test_skill_tools.py
```

换工程时只替换根目录、清单、报告与待比较文件。`.npy` 自带 shape/dtype；原始二进制必须明确元素类型，使用小端。脚本支持 INT8/16/32、对应无符号类型和 FP32/64；64-bit 整数暂不支持，以避免误差统计中的精度歧义。

| 脚本 | 输入与输出 | 通过条件 | 能力边界 |
|---|---|---|---|
| `check_manifest.py` | 相对路径/SHA256/可选 bytes；JSON 结果 | 非空清单所有记录有效，文件身份一致 | 不证明 golden 独立或来源可信 |
| `read_timing.py` | Vivado timing summary；slack 与时钟 JSON | WNS/WHS 非负，格式和时钟表可解析 | 不检查时序约束完整性、CDC、板上频率 |
| `compare_tensors.py` | 两个同 shape/dtype 张量；误差/索引/哈希 JSON | 整数精确；浮点满足显式容差；无非有限值 | 不替代测试覆盖或识别准确率 |

统一返回码：0 通过、1 对照失败、2 输入/格式/读取错误。张量比较的整数默认精确；浮点容差必须由算法要求指定，不为让测试通过而调宽。

## 通用方法与本项目效果

- 通用部分：先建立数据契约，再追踪产物身份，按改动范围选择 C/RTL、时序和真实板测，使用同口径性能数据。
- 案例部分：`references/project_example.md` 单独登记本项目的 PE40/125 MHz、31 组回归和 75 张板端完整响应对照，避免这些参数污染通用流程。
- 工程效果：后处理与乘加重叠后，本项目核调用由约 1.787 s/图降为 1.484 s/图，DSP/BRAM 不增；这不是技能对其他模型或板卡的性能承诺。
- 验证证据：`sim/results/delivery_tools_validation.json`、`sim/results/skill_tools_validation.json` 和主项目原始报告。新脚本包含异常输入与故意不一致的负例检查，不能只验证“成功路径”。
- 精度边界：当前扩批正常件误报问题仍在；与 INT8 参考一致不能当作现场识别可靠性已解决。

## 来源、维护与失效条件

目录和写作方式参考 [Agent Skills 规范](https://agentskills.io/specification)、[OpenAI skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md) 与 [Anthropic webapp-testing](https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md)。流程正文与三个脚本由本项目经验重写；参考范围、访问日期和许可边界记录在 `references/sources.md`。

工具报告格式变化、目标板更换、量化/接口改变、参考来源不清或数据集泄漏时，应重新核实契约及相应证据。技能不会自动重训、重标定、写 Flash 或发布仓库；这些动作只在用户任务范围内执行。本包没有 PYNQ Overlay，也不声明已取得 PYNQ Skill 加分。
