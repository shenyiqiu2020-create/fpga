# 构建脚本与综合实现报告

对应比赛规则第 3.3.5.1 和 3.3.5.4 节。本目录保存可复现的构建入口、综合报告、实现报告及性能与资源对比。

## 后续应提供

- Vivado/Vitis 的构建脚本、运行命令和所需输入。
- 实际工具版本、目标器件完整型号、顶层模块、约束和 IP 配置。
- LUT、FF、BRAM、DSP 等资源占用、目标与实际时钟频率、时序结果。
- 优化前后的性能和资源对比，注明网络、输入尺寸与数据类型。
- 构建产物的输出位置以及从干净环境重建的方法。

比赛指南推荐 Vivado / Vitis 2026.1 或 2025.2；采用其他版本时需在 `report/` 说明并验证可复现性。

本目录参与 Git 跟踪，不整体忽略。`work/`、`tmp/` 和工具缓存供临时生成文件使用；构建脚本与最终报告应提交。

## 已验证板端构建入口（2026-11-01）

执行`python build/prepare_efficientad_pl.py`，校验固件包并准备忽略目录中的完整工作树；它不会下载程序到硬件。
源码和Vivado/Vitis构建脚本见[板端实现](../src/efficientad_pl/README.md)，最终资源、时序与完整模型板测见[计算核报告](../report/efficientad_pl_kernel_20261101.md)。
Windows + Vivado/Vitis 2025.2，目标xc7z020clg484-2，50 MHz；208 DSP、22429 LUT、49 BRAM36。
固件仅在准备命令解压后位于`build/work/efficientad_pl/efficientad_full_pl_packed/generated`；原始包在`board/efficientad_pl`。
BSP构建的`include/`与`lib/`路径可通过`EA_BSP`指定，交叉编译器通过`EA_ARM_GCC`指定。
