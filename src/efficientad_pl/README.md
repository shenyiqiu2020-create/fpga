# 完整 EfficientAD 板端实现

冻结模型：`tie_mount_20261026_3000step_dedupval`，Zynq-7020，Vivado/Vitis 2025.2。

| 版本 | 计算核 | 已记录板测，含自检 |
|---|---|---:|
| `efficientad_full_pl` | DDR窗口读取，PE16×SIMD8 | 约23.6秒/图 |
| `efficientad_full_pl_opt` | 64 KiB行缓存，PE16×SIMD8 | 约9.44秒/图 |
| `efficientad_full_pl_packed` | DSP双INT8乘法打包，PE32×SIMD8，4路重定标 | **约5.04秒/图** |

三个目录保存各阶段HLS、ARM程序、构建/验证脚本及小型证据文件，彼此保持原有相对目录关系。
`generated` 中跟踪的是JSON/Tcl/报告/记录，不重复跟踪固件包里的参数头文件、二进制或工具数据库。
FINN的`mac.hpp`、`utils.hpp`与BSD-3-Clause许可原样保留在各版本`hls/vendor/finn-hlslib`。

最新两张图的58个阶段CRC和最终分数均通过实际板测。计算核约4.507秒，含自检总耗时约5.041秒；
50 MHz，208 DSP、22429 LUT、49 BRAM36，WNS=+1.862ns，WHS=+0.039ns。
原先的两个版本保留用于理解改动、对照历史证据和重建基线。

## 使用和重建

先看[板端交付说明](../../board/README.md)及[最新板测报告](../../report/efficientad_pl_kernel_20261101.md)。
在仓库根目录执行：

```powershell
python build/prepare_efficientad_pl.py
```

它校验[部署包](../../board/efficientad_pl/efficientad_full_pl_packed.zip)后解压到被Git忽略的
`build/work/efficientad_pl/`，再覆盖本目录的可编辑源码，并为基线准备相同的模型参数与测试输入。
所有权重/测试输入均来自同一份冻结包。原始`.pth`和训练照片仍使用原私有Release，不新增到Git。

工作目录中的`efficientad_full_pl_packed`包含完整的`app_sources`、预编译bit/ELF/XSA、测试向量、IP及加载脚本。
可直接运行该目录的`RUN_PACKED.cmd`，再用`READ_PROFILE.cmd`读取计时。
原包脚本采用本机AMD安装路径和已验证的JTAG序列号；换电脑或电缆时须按板端说明调整。

要从源码重建，使用工作目录内`scripts/build_hls.tcl`与`scripts/build_vivado.tcl`。
HLS的`prepare`阶段使用全新solution以避开旧RTL导出缓存；`check_rtl.py --vivado`核对导入RTL。
`scripts/build_app.py`可使用`EA_BSP`指定含`include/`和`lib/`的standalone BSP，`EA_ARM_GCC`指定交叉编译器。
默认值仍是本机已验证的2025.2环境。Vitis GUI也可从新XSA创建平台后编译`app_sources`。

完整模型的卷积、ReLU、平均池化和网络内部Resize在PL；调度、归一化、异常图融合及分数判定在ARM。
预存图片链路已验证；实时摄像头、持久启动和独立INT8精度评估尚未完成，详见报告边界。
