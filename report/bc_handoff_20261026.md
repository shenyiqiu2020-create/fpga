# B/C 数值接口交接（2026-10-26）

## 新实验版完整 EfficientAD：模型包与数值样本

用户授权后，A 将两份新 ZIP 上传到[私有实验版 Release](https://github.com/shenyiqiu2020-create/fpga/releases/tag/tie-mount-batch-20261026-3000step)，标签指向提交 `062792d`。**Release 标签只固定资产来源；本轮推理入口及交接文档在 `codex/new-batch-efficientad` 分支，尚未合入 `main`。** B/C 先切到该分支，再登录有权访问私有仓库的 GitHub 账号下载。`tie_mount_20261026_3000step_model.zip` 含教师、学生、自动编码器权重、`normalization.npz`、`summary.json` 和 `bundle_manifest.json`，为 30,107,886 字节，SHA-256 `c43674f11a81d1bb3c06994b18847e8647360ea632e42414cb08d0e67c956245`；`tie_mount_20261026_3000step_golden.zip` 含同版 `D19_01` 缺损件、`N17_03` 正常件的输入、特征和异常图数组，为 36,505,069 字节，SHA-256 `f33321cc38ce1ec65bf82f7683b4dfa7b80a7d01eedd9177108abc4b446d3eb6`。GitHub 资产回报两份大小和 SHA-256 均与本机一致；B/C 下载及板端结果回执尚未取得。

下载 [模型 ZIP](https://github.com/shenyiqiu2020-create/fpga/releases/download/tie-mount-batch-20261026-3000step/tie_mount_20261026_3000step_model.zip)与[数值黄金 ZIP](https://github.com/shenyiqiu2020-create/fpga/releases/download/tie-mount-batch-20261026-3000step/tie_mount_20261026_3000step_golden.zip)到仓库的 Git 忽略目录 `build/work/handoff/`，核对上述 SHA-256，再执行：

```powershell
Get-FileHash build/work/handoff/tie_mount_20261026_3000step_model.zip -Algorithm SHA256
Get-FileHash build/work/handoff/tie_mount_20261026_3000step_golden.zip -Algorithm SHA256
Expand-Archive build/work/handoff/tie_mount_20261026_3000step_model.zip -DestinationPath build/work/handoff/received_20261026
Expand-Archive build/work/handoff/tie_mount_20261026_3000step_golden.zip -DestinationPath build/work/handoff/received_20261026/golden
python -B -m sim.verify_tie_mount_golden build/work/handoff/received_20261026/golden/D19_01
python -B -m sim.verify_tie_mount_golden build/work/handoff/received_20261026/golden/N17_03
```

两份新样本的模型包 ID 均为 `tie_mount_20261026_3000step_dedupval`，阈值 `0.11209306865930557`；`D19_01` 分数 `0.3200802505016327` 判缺损，`N17_03` 分数 `0.06585786491632462` 判正常。完整单张照片推理需固定提交 `fcab5146f84ae17597044ad5ddf1656ccf805401` 的 EfficientAD 候选源码，显式指定新模型五文件与清单，命令见[仿真说明](../sim/README.md)。B/C 应回报两个 ZIP 的下载 SHA-256、两条复核输出、模型包 ID、Git 提交号和板端差异。新模型只在 9 件新留出实物上做了电脑端评估，仍有正常误报、开发集漏报和裁剪拒绝；红点仅为未验证的位置候选。旧版样本与新版权重、校准及阈值不可混用。

## 已退役的旧数值包

`golden_v3` 对应 300 步旧模型，曾用于 A 的历史回归。应用户要求，其 GitHub Release 与标签已删除；旧权重原本未上传 GitHub。A 本机仍在 Git 忽略目录保留旧 ZIP 以核对历史实验，B/C **不再接收或使用旧数值包**，当前交接只认上方新版模型与 `D19_01/N17_03` 两份同版样本。

## 固定的计算边界

`input_rgb_hwc.npy` 为 `uint8 [256,256,3]`；`input_normalized_chw.npy` 为 ImageNet 均值/标准差归一化后的 `float32 [3,256,256]`。归一化教师、学生教师半支、自动编码器、学生自动编码器半支均为 `float32 [384,56,56]`。两分支分别按 384 通道计算差值平方的均值，得到原始 `float32 [56,56]` 图；按 `metadata.json` 的各自分位数做 `0.1*(raw-start)/(end-start)` 校准后，以 `0.5+0.5` 融合。融合图四周补 4 像素零，再双线性缩放到 `256×256`，取最大值并以严格 `score > threshold` 判缺损。具体数组名、量化前公式及容差以 `metadata.json` 和 `sim/verify_tie_mount_golden.py` 为准。

第一轮建议 C 选择教师–学生特征差分与 384 通道平方均值作为独立 PL 算子，使用两份特征输入和 `student_teacher_raw_hw.npy` 输出做逐元素比对；自动编码器分支可复用同一算子，再与完整软件链路的校准及融合结果逐级核对。若改用 INT8，先固定尺度、零点、累加位宽、舍入、饱和与误差容限，并另存量化参考；这些 float32 文件不能直接充当 INT8 真值。只完成此算子不代表完整 EfficientAD 已迁入 PL。

## B/C 返回的证据

- **B：板卡与系统。** 确认整板型号、硬件版本和器件完整料号，记录依据；记录 Vivado/Vitis、系统、启动串口日志、SD 卡或其它存储的文件读写、PS 可用内存与约定路径。与 C 约定输入/输出传输方式，先让板上读取固定张量并保存实际输出及耗时。板型确认前不套用相近型号约束或刷写镜像。
- **C：PL 加速。** 提交所选算子的接口表（布局、位宽、步长、数据顺序、控制信号）、可复现的 RTL/HLS 仿真与黄金输出差异、综合/实现资源和时序、与 B 联调后的板上逐样本误差及延迟。竞赛版由 Zynq ARM PS 驱动 PL；课程版须另有实际运行的 RISC-V 核、存储、互连、扩展 IP、嵌入式程序及其调用日志，分别构建和验收。
- **A：接口支持。** 保持新模型包及两份黄金样本身份稳定，核对 B/C 回传的 ZIP 哈希和两条数值复核输出；若 B/C 需要从原始图片在板端复跑完整推理，A 再按数据权限提供同版原图和固定提交的候选实现。新模型 ZIP 已含三个权重、归一化和阈值文件，黄金 ZIP 单独保存数值张量，两包须配套使用并依 `sim.model_bundle` 校验。

两份新样本用于接口对齐，不是新盲测或可靠性证明。新候选在 5 件缺损、4 件正常的留出实物中仍有一张正常照误报，两张正常照被裁剪拒绝；开发集中有四张缺损照漏报。报告须分开列正常、缺损和输入失败，不得宣称模型已可靠。后续泛化结论仍需未参与开发的正常件与缺损件盲测。
