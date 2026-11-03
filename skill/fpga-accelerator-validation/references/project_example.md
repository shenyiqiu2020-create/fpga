# 当前项目的映射示例

本页用于在本仓库执行技能。通用脚本和 `SKILL.md` 不依赖这些数值；移植到其他工程时替换本页映射，不复制默认器件/地址。

## 当前唯一计算核

- 版本：EfficientAD 后处理重叠版，PE40、SIMD8、125 MHz。
- HLS：`src/accelerator/hls/efficientad_engine.cpp` 与 `.h`。
- 数值：固定 bring-up INT8/Q30；Teacher、Student、Autoencoder 共 29 阶段，ARM 调度和评分。
- 模型身份：`src/accelerator/generated/deployment_manifest.json` 与 `data/models/`。
- 回归输入：31 组测试保留尾通道、卷积、池化与 Resize；对应 `pe40_tests.bin` 和 `passed_cosim_identity.json`。
- 最新板端产物：`board/efficientad_full.bit`、`efficientad_demo.elf`、`efficientad_full.elf`、XSA 和 DCP。

## 从仓库根目录执行

```text
python skill/fpga-accelerator-validation/scripts/check_manifest.py data/submission_manifest.json --root .
python skill/fpga-accelerator-validation/scripts/read_timing.py build/reports/vivado_timing.rpt
python sim/test_delivery_tools.py
python sim/test_skill_tools.py
python sim/test_image_library.py
python build/verify_delivery.py
```

`python build/restore_prebuilt.py` 可还原当前 IP 归档并核对 56 个 RTL 模块的身份，不是重新综合。完整重建入口为 `build/rebuild.cmd`，路径和环境说明见根目录 `report/reproduction.md`。模型、计算源码和参数的身份必须维持原验证链；不要以整理文档为由重建或修改黄金参考。

## 最近实际证据

| 证据 | 已有结论 | 限制 |
|---|---|---|
| `sim/results/cosim/` 与 HLS 日志 | 31 组 C/RTL 已通过 | 只覆盖所供测试场景 |
| `build/reports/vivado_timing.rpt` | WNS +0.175 ns、WHS +0.038 ns | 约束与器件不可任意更换 |
| `board/evidence/overlap_results.json` | 核调用约 1.484 s/图 | 单核调用时间，不含主机传输 |
| `sim/results/received_accuracy/` | 75 张 FPGA 完整响应与 INT8 参考一致 | 数值正确不等于识别准确 |
| 同目录四组统计 | 扩批留出 INT8 32/48，正常 0/16 判对 | 回顾性数据，泛化问题未解决 |
| `sim/results/image_library_validation.json` | 284 张图库读取、筛选、选图板测链路验证 | 不是 284 张全部重跑 FPGA |

当前仅保留这一版可构建工程。不同名称的回归输入和性能对比 JSON 是当前验证依赖，不能只按名字带有 `baseline` 或 `packed` 就删除。没有提供另一版完整模型的权重来替换当前冻结包；历史 CSV 的其他模型分数不属于当前板端模型。

## 提炼效果

这套方法帮助发现旧 RTL/IP、时钟未生效和 CPU cache 等跨层问题，并将“仿真通过”“时序通过”“板测一致”“识别有效”分开。后处理重叠的本项目实测由约 1.787 s 降至 1.484 s；这个数字是案例效果，不是技能对任意工程的保证。
