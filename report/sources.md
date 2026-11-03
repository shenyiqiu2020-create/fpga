# 来源和复用边界

1. 团队提供的 `data/contest/amd_contest_2026.pdf`，AMD 2026 选题指南，第 3.3 节与第六节，作为本次交付规则来源。
2. Batzner K, Heckler L, König R. EfficientAD Accurate Visual Anomaly Detection at Millisecond Level Latencies. WACV 2024, 128-138。原论文的教师学生特征差分与自动编码器用于解释算法来源，不把论文 GPU 延迟当作本板性能。https://openaccess.thecvf.com/content/WACV2024/html/Batzner_EfficientAD_Accurate_Visual_Anomaly_Detection_at_Millisecond-Level_Latencies_WACV_2024_paper.html
3. 非官方 EfficientAD 候选实现：`https://github.com/nelson1425/EfficientAD`，本机核对提交 `fcab5146f84ae17597044ad5ddf1656ccf805401`，Apache 2.0；源码快照在 `src/model/upstream/`。权重来自队友冻结包，五个模型/校准文件按交接清单核验，不声称本次重新训练。
4. Xilinx FINN HLS Library，`https://github.com/Xilinx/finn-hlslib/blob/master/mac.hpp`，BSD 3 Clause。本工程只复用冻结的 `mac.hpp`、`utils.hpp` 中的乘法资源选择辅助，不是直接使用完整 FINN 编译器、现成 DPU 或完整预生成 CNN。冻结文件及许可证在 `src/accelerator/hls/vendor/finn-hlslib/`，身份由清单固定。
5. AMD Vitis HLS User Guide UG1399，2025.2，DATAFLOW 指令说明：https://docs.amd.com/r/2025.2-English/ug1399-vitis-hls/pragma-HLS-dataflow 。用于说明任务重叠的工具机制，具体资源、时序与速度由本队实测报告支持。
6. AMD 工具自带 PS7、AXI SmartConnect、Processor System Reset、XL Constant 及 standalone BSP 按工具许可使用；不把这些现成 IP 声称为本队原创。自有控制、缓存、量化、数据打包、PS 程序与演示前后端在源码中单独提供。

本次公开资料核对日期为 2026 年 11 月 2 日。本地统计、源代码和硬件实测优先以交付 JSON、原始日志及 SHA256 为准；第三方网页不能证明本队的识别准确率或板级性能。
