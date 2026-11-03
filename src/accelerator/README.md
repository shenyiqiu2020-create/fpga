# EfficientAD PE40 125 MHz 卷积后处理重叠版

状态：31 组 C 测试、31 组 C/RTL 对照、125 MHz 时序和两张图完整模型板测均已通过。58 个阶段 CRC 与最终分数全部一致。

板测核耗时约 1.484 秒/图；含自检总耗时约 2.028 秒/图。DSP 203、BRAM36 57、LUT 25,750、FF 33,207。此目录是唯一交付的计算核版本；早期版本只留下说明当前结论所需的测量数据，未保留旧工程。详细证据见 results.md 和 generated/overlap_results.json。

本目录可独立重建当前 PE40/SIMD8、125 MHz 后处理重叠版。模型、INT8/Q30 参数和测试 golden 保持已验证身份；不依赖交付目录中的旧 PE40/PE32 工程。

## 修改

hls/efficientad_engine.cpp 中，每行卷积划分为 mac_row 和 emit_row 两个 DATAFLOW 任务。
mac_row 保持 PE40、SIMD8、乘加 II=1；emit_row 保持四路重定标、原 ReLU/池化及输出格式。
任务之间用 1280-bit、深度 4 的 LUTRAM FIFO 传递一个输出位置的 40 路 INT32 累加值。
池化行状态仅由 emit_row 拥有；每行结束后，调用者才更新卷积行缓存。
Resize、权重加载顺序、PS 评分和时钟不变。

## 使用

- Vivado 工程：_build/vivado/ea_full.xpr（完整构建成功后生成）。
- HLS 源码：hls/efficientad_engine.cpp、efficientad_engine.h；构建脚本 scripts/build_hls.tcl。
- 新硬件平台：generated/ax7021_efficientad_full.xsa。
- Vitis 应用源文件：runtime/；匹配的预编译程序 generated/efficientad_full.elf。
- build_overlap.cmd：从源码重新做 C 测试、综合、打包、31 组 C/RTL 联合仿真、Vivado 实现和应用编译；不会自动下载开发板。
- run_overlap.cmd：验证完成后，通过指定 Digilent JTAG 临时下载 bit 和 ELF；不写 Flash。
- read_profile.cmd：通过 JTAG 读取运行状态、频率和逐层计时，不占用 COM11。
- 成功板测后运行 python scripts/summarize_overlap.py 生成比较报告。

构建使用 D:/amd/2025.2 和现有 D:/ddca/experiments/fpga_amd/vitis_workspace/ax7021_conv1_platform 的 Cortex-A9 BSP；不会修改该平台。
目标 xc7z020clg484-2，PL 125 MHz、ARM 约 666.667 MHz。

## 验证来源

generated/baseline_board_profile.json 和 baseline_kernel_summary.json 来自上一版已验证 PE40 125 MHz。
测试覆盖原 27 组和 4 组 PE40 非整组输出通道场景。generated/frozen_inputs_sha256.json 固定模型、量化与原测试资产。
DATAFLOW 的 HLS IP 导出自动加入仅用于仿真的死锁检测代码；scripts/sync_export_rtl.py 严格检查允许的附加代码，并让 C/RTL 仿真和 Vivado 使用完全相同的打包 RTL 文件。
原始综合/打包日志保留；第一次导出审计拒绝了工具新增的死锁检测模块，修正审计后重新打包成功见 logs/hls_package.log。

两张内置调试图的 CRC 和分数一致性用于部署验证，不等于独立 INT8 精度评估，也不代表实时相机或开机自启动。
