# B/C 数值接口交接（2026-10-26）

## 接收物与核对

A 本机交接包：`build/work/handoff/tie_mount_golden_v3.zip`（54,423,455 字节）。SHA-256：`ea67815d874c1145ea34a46ca8bb1b3702c5642791ae33a4558934ce9af51c88`。同一 ZIP 已上传到[私有 GitHub Release](https://github.com/shenyiqiu2020-create/fpga/releases/tag/tie-mount-golden-v3)，[直接下载资产](https://github.com/shenyiqiu2020-create/fpga/releases/download/tie-mount-golden-v3/tie_mount_golden_v3.zip)。该 Release 的标签指向 `0cfcfff`；接收者仍应拉取最新 `main` 获取本交接说明。压缩包不在 Git 提交中，B/C 的下载与复核回执尚未收到。

包内为 `tie_mount_golden_v3/{N02_01,N05_01,D07_01}/`，每例各有 `metadata.json` 和 12 个 `.npy` 数组，共 39 个文件。A 于 2026-10-26 检查了 ZIP CRC、与本机原始黄金目录逐文件 SHA-256 一致，并用 `sim.verify_tie_mount_golden` 复核三例公式和判定。三例均绑定 `sim/model_bundles/tie_mount_grouped_v1_300step.json` 的冻结 300 步完整 EfficientAD 模型包。`metadata.json` 逐数组给出名称、形状、dtype 和 SHA-256，并给出模型包、校准文件和源裁剪图身份。

接收者登录有权访问该私有仓库的 GitHub 账号，把下载的 ZIP 放在仓库根目录的 `build/work/handoff/`。然后在 PowerShell 执行（`python` 需安装 NumPy）：

```powershell
Get-FileHash build/work/handoff/tie_mount_golden_v3.zip -Algorithm SHA256
Expand-Archive build/work/handoff/tie_mount_golden_v3.zip -DestinationPath build/work/handoff/received_v3
python -B -m sim.verify_tie_mount_golden build/work/handoff/received_v3/tie_mount_golden_v3/N02_01
python -B -m sim.verify_tie_mount_golden build/work/handoff/received_v3/tie_mount_golden_v3/N05_01
python -B -m sim.verify_tie_mount_golden build/work/handoff/received_v3/tie_mount_golden_v3/D07_01
```

接收者记录自己的 ZIP 哈希、三条校验输出、Git 提交号和环境版本。解压目录建议保持在 Git 忽略的 `build/work/`。如果任一哈希、模型包 ID、形状或数值复核不符，先停止硬件对比并向 A 核对包版本。

| 样本 | 人工标签与用途 | 冻结模型分数 | 阈值 | 模型判定 |
| --- | --- | ---: | ---: | --- |
| `N02_01` | 正常，参与校准 | 0.0697559341788292 | 0.0697559341788292 | 正常 |
| `N05_01` | 正常，独立测试样本 | 0.12137062847614288 | 0.0697559341788292 | 误报缺损 |
| `D07_01` | 外缘缺损，独立测试样本 | 0.4988238215446472 | 0.0697559341788292 | 缺损 |

## 固定的计算边界

`input_rgb_hwc.npy` 为 `uint8 [256,256,3]`；`input_normalized_chw.npy` 为 ImageNet 均值/标准差归一化后的 `float32 [3,256,256]`。归一化教师、学生教师半支、自动编码器、学生自动编码器半支均为 `float32 [384,56,56]`。两分支分别按 384 通道计算差值平方的均值，得到原始 `float32 [56,56]` 图；按 `metadata.json` 的各自分位数做 `0.1*(raw-start)/(end-start)` 校准后，以 `0.5+0.5` 融合。融合图四周补 4 像素零，再双线性缩放到 `256×256`，取最大值并以严格 `score > threshold` 判缺损。具体数组名、量化前公式及容差以 `metadata.json` 和 `sim/verify_tie_mount_golden.py` 为准。

第一轮建议 C 选择教师–学生特征差分与 384 通道平方均值作为独立 PL 算子，使用两份特征输入和 `student_teacher_raw_hw.npy` 输出做逐元素比对；自动编码器分支可复用同一算子，再与完整软件链路的校准及融合结果逐级核对。若改用 INT8，先固定尺度、零点、累加位宽、舍入、饱和与误差容限，并另存量化参考；这些 float32 文件不能直接充当 INT8 真值。只完成此算子不代表完整 EfficientAD 已迁入 PL。

## B/C 返回的证据

- **B：板卡与系统。** 确认整板型号、硬件版本和器件完整料号，记录依据；记录 Vivado/Vitis、系统、启动串口日志、SD 卡或其它存储的文件读写、PS 可用内存与约定路径。与 C 约定输入/输出传输方式，先让板上读取固定张量并保存实际输出及耗时。板型确认前不套用相近型号约束或刷写镜像。
- **C：PL 加速。** 提交所选算子的接口表（布局、位宽、步长、数据顺序、控制信号）、可复现的 RTL/HLS 仿真与黄金输出差异、综合/实现资源和时序、与 B 联调后的板上逐样本误差及延迟。竞赛版由 Zynq ARM PS 驱动 PL；课程版须另有实际运行的 RISC-V 核、存储、互连、扩展 IP、嵌入式程序及其调用日志，分别构建和验收。
- **A：接口支持。** 保持冻结模型包及三份样本身份稳定；若 B/C 需要从原始图片在板端复跑完整推理，另行提供同版原图、三个权重、`normalization.npz`、`summary.json` 和候选实现固定提交，并依 `sim.model_bundle` 逐文件校验。当前 ZIP 仅含固定数值张量，不能单独恢复完整模型推理。

三份样本用于接口对齐，不是新盲测或可靠性证明。`N05` 误报在演示阶段可接受，但独立正常测试件目前只有这一件且两张照片都误报；报告须分开列正常和缺损结果，不得宣称模型已可靠。后续泛化结论仍需未参与开发的正常件与缺损件盲测。
