---
name: fpga-accelerator-validation
description: Validate and optimize FPGA accelerators using artifact identity, numerical golden outputs, HLS and RTL evidence, routed timing, and comparable board measurements. Use for HLS/RTL kernel bring-up, stale IP diagnosis, DMA or cache correctness, and evidence-backed performance changes. Supports different kernels and boards; model training or accuracy tuning alone is outside this workflow.
license: MIT
metadata:
  author: Yiqiu Shen
  version: "1.0"
---

# FPGA Accelerator Validation

把一个已有或正在移植的计算核推进到“可复现、可核对、可解释收益”的状态。根据用户任务选择下面的路线，不要求每次重跑全部工具链。

## 先确定任务和契约

读取实际源码、接口、构建入口和最近的原始报告，提取：

- 运算与输入输出：shape、布局、位宽、符号、定点比例、舍入、饱和、边界行为。
- 硬件与软件：器件、时钟、AXI 地址与数据宽度、DMA 长度、缓存维护、驱动与工具版本。
- 当前证据：参考输出如何产生、哪一份源码生成了哪些 RTL/IP/bit/ELF、最近一次真实通过的阶段。
- 本次目标：修复、正确性验证、提速或资源下降，以及不可改变的数值与接口条件。

优先从本地文件取得参数。只对缺失且会影响下一步的参数询问用户；板卡暂不可用时继续完成不依赖板卡的工作。

## 选择路线

| 用户任务 | 执行方式 | 按需读取 |
|---|---|---|
| 修改源码后结果没变、怀疑旧 IP | 追踪源码→综合→导出→Vivado 导入→板端产物；先找到身份断点 | [验证流程](references/validation_workflow.md) 的“身份链” |
| 数值不一致、DMA 超时、仿真挂起 | 找首个出错阶段，检查数据契约、握手和缓存；保留最小失败输入 | [失败模式](references/failure_patterns.md) |
| 计算核太慢、资源不够、想提频 | 建立同口径基线，定位占时阶段，选择一次可测量的改动 | [HLS 优化](references/hls_optimization.md) |
| 需要交付、复现实验或说明完成度 | 校验工件、核对最高已通过阶段，输出证据表与复现入口 | [验证流程](references/validation_workflow.md) |
| 在本仓库使用这套方法 | 将通用步骤映射到当前工程文件；示例数值不能当成另一板卡的默认值 | [本项目映射](references/project_example.md) |

## 验证顺序与停止条件

1. **冻结参考。** 确认参考输出来自独立运算定义或已审计的实现；记录源码、参数和输入身份。哈希一致不代表参考本身正确。
2. **先验证数值。** 改变调度时保留位宽、舍入和饱和语义。整数运算默认逐元素精确相等；浮点容差来自算法契约，不能为了让失败消失而增大。
3. **检查 HLS/RTL。** 根据改变范围选 C 测试、综合与 C/RTL。DATAFLOW/FIFO、复位或接口时序改变时，C 测试不足以验证背压和死锁。只记录确实执行的测试范围。
4. **核对实际产物。** 导出的 IP、综合 RTL、通过仿真的 RTL 与 Vivado 实际导入的 RTL 必须能追溯到同一份源码。发现差异先解释或重新构建，不靠版本号判断。
5. **检查实现时序。** 用布线后 setup/hold 和实际约束评价提频。HLS 估计频率、BD 校验成功、生成 bitstream 均不能替代时序通过。
6. **执行板级核对。** 用户任务已授权板测时，核对目标、固件、寄存器与输入输出；处理 CPU cache/DMA 一致性。先做数值对照，再计时。
7. **解释收益。** 同输入、同精度和同计时口径比较；同时说明 LUT/FF/BRAM/DSP、带宽和时钟代价。板测缺失时写“尚未板测”，不要外推板上加速比。

任何阶段失败，保留原始错误和最小复现，修正后重跑受影响的阶段。不要把失败的下游验证写成已完成。普通源码修改不隐含重训模型、变更量化、写 Flash 或 Git push 的授权。

## 可直接调用的脚本

先运行脚本的 `--help`。脚本从参数取得工程路径，不依赖这个仓库的模型名、器件或磁盘目录。

```text
python scripts/check_manifest.py manifest.json --root /path/to/project
python scripts/read_timing.py routed_timing.rpt
python scripts/compare_tensors.py expected.npy actual.npy
python scripts/compare_tensors.py expected.bin actual.bin --dtype int32
python scripts/compare_tensors.py expected.npy actual.npy --atol 0.00001 --rtol 0
```

- `check_manifest.py`：检查相对路径、SHA256、可选文件大小和重复记录；越界路径、缺失文件及内容变化返回失败。清单结构见 [验证流程](references/validation_workflow.md)。
- `read_timing.py`：解析 Vivado timing summary 的 WNS/WHS 和时钟表；负 slack 返回失败。它不判断约束是否完整或跨时钟设计是否正确。
- `compare_tensors.py`：比较 `.npy` 或指定类型的小端原始二进制，输出误差、首批不一致索引和 SHA256。需要 NumPy；默认精确比较，拒绝非有限值。

返回码：`0` 为检查通过，`1` 为检查失败，`2` 为输入、格式或读取错误。脚本不负责下载固件或自动修改待测文件。

## 输出约定

以 [验证记录模板](assets/validation_record.md) 为起点，按实际任务删去不相关项。至少交付：

- 改了什么、为什么改，以及仍保持的运算/接口约束。
- 实际执行到哪一阶段、覆盖哪些输入；对应源码/产物哈希与原始日志位置。
- 数值对照结论；有性能数据时提供相同计时范围、重复次数、缓存状态和资源/频率。
- 未通过或尚未执行的环节，以及一条可复现的下一步命令。

机器可读记录可采用 [测量记录示例](assets/measurement_example.json)。字段和数值为格式示例，不是测量结果。

## 使用示例

> 使用 $fpga-accelerator-validation。这个 AXI 点积核改成 BRAM 后 RTL 仿真通过，但板上结果偶发不一致。先核对构建产物身份、输入布局和缓存维护，定位最早出现差异的位置，不改变定点规则。

> 使用 $fpga-accelerator-validation。优化一个已有的图像卷积核，模型、量化和接口不变。先读取逐层计时与实现报告，再选择一项优化，分别报告数值、时序、资源和真实板测状态。

格式参考与原创内容边界见 [来源说明](references/sources.md)。此技能不限定 EfficientAD、Zynq-7020、固定并行度或某个工具版本；具体参数始终来自待处理工程。
