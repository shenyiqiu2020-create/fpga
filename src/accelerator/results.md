# PE40 125 MHz 卷积后处理重叠版实测

新 RTL 已通过 31 组 C 测试、31 组 C/RTL 对照、125 MHz 布线后时序与实际开发板两张图检查。
PE40、SIMD8、四路重定标、频率、模型和 INT8/Q30 参数保持不变；仅调整卷积阶段调度。

| 图片 | 原 PE40 核耗时 | 重叠版核耗时 | 加速 | 原含自检总耗时 | 新含自检总耗时 |
|---|---:|---:|---:|---:|---:|
| D19_01 | 1.787 s | 1.484 s | 1.205x | 2.333 s | 2.028 s |
| N17_03 | 1.787 s | 1.484 s | 1.205x | 2.330 s | 2.027 s |

平均核耗时减少 17.0%。WNS=+0.175 ns，WHS=+0.038 ns。

| 资源 | 原 PE40 | 重叠版 |
|---|---:|---:|
| Slice LUTs | 23599 | 25750 |
| Slice Registers | 27105 | 33207 |
| Block RAM Tile | 57 | 57 |
| DSPs | 203 | 203 |

## 实现与验证

- 每行拆分成 MAC 生产者与重定标/池化/DDR 写回消费者，通过 1280-bit、深度 4 的 FIFO 传递 40 路 INT32 累加结果。
- 两阶段在同一行的不同输出位置之间重叠；每行结束排空 FIFO 后再更新行缓存。权重加载、行缓存和输出顺序保留。
- ReLU、Q30 舍入、饱和、2x2 池化、Resize 算法与模型完全不变。乘加 II=1，四路重定标没有复制。
- 31 组 supplied vectors 的 C/RTL 对照通过；两张图的 58 个阶段 CRC 与原 golden、两个最终分数逐项一致。
- 核 125 MHz、ARM 约 666.667 MHz，PS 初始化与原版完全相同。临时 JTAG 下载，无 Flash 写入。
- 综合、打包、通过 C/RTL 仿真的 RTL 与 Vivado 导入文件哈希一致。原 PE40、PE32 与 D: 工程保留。
- 总耗时仍包含 CRC 自检、缓存维护、PS 评分、复制和串口输出；两张图不构成独立量化精度评估。

## 逐层核耗时（第一张图）

| 阶段 | 原 PE40 | 重叠版 | 时间比 |
|---|---:|---:|---:|
| teacher.conv0 | 132.240 ms | 87.960 ms | 1.503x |
| teacher.conv3 | 273.649 ms | 243.180 ms | 1.125x |
| teacher.conv6 | 83.306 ms | 66.833 ms | 1.246x |
| teacher.conv8 | 165.178 ms | 143.720 ms | 1.149x |
| student.conv0 | 132.240 ms | 87.960 ms | 1.503x |
| student.conv3 | 273.650 ms | 243.180 ms | 1.125x |
| student.conv6 | 83.307 ms | 66.831 ms | 1.247x |
| student.conv8 | 331.026 ms | 287.463 ms | 1.152x |
| autoencoder.conv0 | 12.616 ms | 9.367 ms | 1.347x |
| autoencoder.conv2 | 5.231 ms | 3.203 ms | 1.633x |
| autoencoder.conv4 | 2.977 ms | 1.901 ms | 1.566x |
| autoencoder.conv6 | 1.223 ms | 0.929 ms | 1.316x |
| autoencoder.conv8 | 0.429 ms | 0.360 ms | 1.192x |
| autoencoder.conv10 | 0.427 ms | 0.425 ms | 1.005x |
| autoencoder.resize11 | 0.059 ms | 0.060 ms | 0.983x |
| autoencoder.conv12 | 0.210 ms | 0.196 ms | 1.071x |
| autoencoder.resize15 | 0.416 ms | 0.417 ms | 0.998x |
| autoencoder.conv16 | 0.459 ms | 0.371 ms | 1.237x |
| autoencoder.resize19 | 1.425 ms | 1.425 ms | 1.000x |
| autoencoder.conv20 | 1.108 ms | 0.815 ms | 1.360x |
| autoencoder.resize23 | 6.450 ms | 6.452 ms | 1.000x |
| autoencoder.conv24 | 4.140 ms | 2.851 ms | 1.452x |
| autoencoder.resize27 | 25.000 ms | 24.997 ms | 1.000x |
| autoencoder.conv28 | 14.998 ms | 10.069 ms | 1.490x |
| autoencoder.resize31 | 101.791 ms | 101.791 ms | 1.000x |
| autoencoder.conv32 | 59.167 ms | 39.282 ms | 1.506x |
| autoencoder.resize35 | 19.793 ms | 19.791 ms | 1.000x |
| autoencoder.conv36 | 8.668 ms | 5.124 ms | 1.692x |
| autoencoder.conv38 | 46.108 ms | 26.599 ms | 1.733x |
