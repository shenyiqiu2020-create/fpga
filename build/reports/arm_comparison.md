# 纯 ARM 与 100 MHz FPGA 完整模型实测对比

状态：两种实现使用完全相同的 INT8/Q30 模型和两张预处理输入。纯 ARM 已通过原 27 组算子测试，
以及两张图共 58 个阶段 CRC 和最终分数检查；测试后已恢复 100 MHz FPGA 加速版，并重新读取其完成状态与计时。

## 完整模型时间

| 图片 | ARM 算子合计 | PL 算子合计 | 算子加速 | ARM 含自检总耗时 | PL 版含自检总耗时 | 完整流程加速 |
|---|---:|---:|---:|---:|---:|---:|
| D19_01 | 32.157 s | 2.319 s | 13.86x | 32.607 s | 2.859 s | 11.40x |
| N17_03 | 32.157 s | 2.319 s | 13.86x | 32.607 s | 2.864 s | 11.39x |

两张平均：ARM 算子 32.157 秒，PL 算子 2.319 秒，算子加速 13.86 倍；
含自检的完整流程分别为 32.607 秒和 2.862 秒，加速 11.39 倍。

## 对比条件

- ARM：Cortex-A9 core 0，实际约 666.667 MHz，单核，I/D 缓存开启。
- CPU 软件使用 NEON 的 4 空间位置 × 2 输出通道分块点积，复用权重与输入；编译为 `-O3 -mfpu=neon`，未使用 fast-math。
- 反汇编确认执行 `vmull.s8`、`vpadal.s16`。纯 ARM 算子不写 PL 控制寄存器，也不调用 FPGA 或 DMA。
- PL：100 MHz、每拍 256 个 INT8 MAC；22 个卷积及 ReLU/平均池化、7 个 Resize 在 PL 执行，评分仍在同一 ARM 核执行。
- ARM 与 PL 使用同一组权重、输入、INT8/Q30 舍入、裁剪、池化、Resize 和评分算法。
- 算子时间只统计算子调用，CPU 的分块打包和池化也在其中；不含逐层 CRC、串口日志或最终评分。
- 含自检总耗时包含逐层 CRC、评分、特征复制、串口日志、调度，以及 PL 版所需的缓存维护；它不是去掉自检后的生产推理延迟。
- 模型和输入预先驻留 DDR；两种计时均不包含 JTAG 下载、图像采集、解码及离线输入预处理。
- 这是当前单核 NEON C 实现的板测结果，不代表双核或其他高度调优软件库的性能上限。
- 两张图用于一致性与计时，不构成独立 INT8 精度评估。

## 逐层平均

| 算子 | ARM | PL | ARM时间/PL时间 |
|---|---:|---:|---:|
| teacher.conv0 | 1247.120 ms | 139.036 ms | 8.97x |
| teacher.conv3 | 6106.772 ms | 377.288 ms | 16.19x |
| teacher.conv6 | 1593.844 ms | 110.024 ms | 14.49x |
| teacher.conv8 | 4068.052 ms | 234.828 ms | 17.32x |
| student.conv0 | 1218.947 ms | 139.036 ms | 8.77x |
| student.conv3 | 6099.653 ms | 377.287 ms | 16.17x |
| student.conv6 | 1593.233 ms | 110.022 ms | 14.48x |
| student.conv8 | 8137.229 ms | 469.656 ms | 17.33x |
| autoencoder.conv0 | 77.221 ms | 14.433 ms | 5.35x |
| autoencoder.conv2 | 52.687 ms | 6.189 ms | 8.51x |
| autoencoder.conv4 | 26.589 ms | 3.251 ms | 8.18x |
| autoencoder.conv6 | 13.351 ms | 1.383 ms | 9.66x |
| autoencoder.conv8 | 3.363 ms | 0.476 ms | 7.06x |
| autoencoder.conv10 | 0.878 ms | 0.433 ms | 2.03x |
| autoencoder.resize11 | 0.046 ms | 0.068 ms | 0.69x |
| autoencoder.conv12 | 0.846 ms | 0.227 ms | 3.74x |
| autoencoder.resize15 | 0.319 ms | 0.475 ms | 0.67x |
| autoencoder.conv16 | 4.353 ms | 0.507 ms | 8.59x |
| autoencoder.resize19 | 1.121 ms | 1.647 ms | 0.68x |
| autoencoder.conv20 | 13.220 ms | 1.240 ms | 10.66x |
| autoencoder.resize23 | 5.101 ms | 7.484 ms | 0.68x |
| autoencoder.conv24 | 56.403 ms | 4.671 ms | 12.08x |
| autoencoder.resize27 | 19.790 ms | 28.947 ms | 0.68x |
| autoencoder.conv28 | 211.061 ms | 16.938 ms | 12.46x |
| autoencoder.resize31 | 80.468 ms | 117.889 ms | 0.68x |
| autoencoder.conv32 | 845.237 ms | 66.832 ms | 12.65x |
| autoencoder.resize35 | 16.331 ms | 22.936 ms | 0.71x |
| autoencoder.conv36 | 91.540 ms | 9.455 ms | 9.68x |
| autoencoder.conv38 | 572.378 ms | 56.725 ms | 10.09x |

主要卷积在 PL 上明显更快；本实现中部分 Resize 在 ARM 上更快，说明完整模型不能按某一个小算子的倍率外推。
原始计时、时钟、缓存标志、CRC、源文件哈希和固件哈希见 `generated/cpu_vs_pl.json` 与两份板测 profile JSON。
