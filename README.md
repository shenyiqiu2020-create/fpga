# 基于 Zynq7020 的工件外观异常检测系统

AMDYES 团队的 AMD 自主选题赛道工程整理稿，依据提供的 2026 选题指南第 3.3 节及第六节。当前适用组别按团队此前登记为初级组；年级、学历、报名信息与板卡修订须在最终提交前由团队确认。

## 可以直接运行什么

1. 双击 `start_demo.cmd`，打开 `http://127.0.0.1:8765`。默认使用本机已验证的 `efficientad` Python 环境；换电脑时先设置 `EA_PYTHON`。
2. 板卡接原配圆口电源与 JTAG USB。点击“初始化 FPGA”，临时加载已验证的 bitstream 和演示 ELF，不写 Flash。
3. 选择样例或上传工件图片，保持“FPGA 板端推理”，点击“开始检测”。界面显示异常响应、分数、固定阈值、真实 PL 核调用耗时、板端总耗时和本次处理耗时。
4. 需要摄像头时手动开启并授权，拍摄后再检测。拍摄模式隐藏侧栏与历史；录制画面由浏览器要求选择窗口，停止后保存本地 WebM，不上传外部服务。
5. 可切换为电脑 FP32 或 INT8 参考，界面和 CSV 会明确标出计算后端。电脑模式不伪装为 FPGA 结果。

## 已有实测

完整模型包含 Teacher、Student、Autoencoder；22 个卷积阶段及 ReLU/平均池化、7 个 Resize 在 PL 中运行，ARM 负责调度与最终评分。计算核为一个可复用 HLS IP，逐层配置，不是三个同时铺开的网络。

| 指标 | 结果 | 证据 |
|---|---:|---|
| PL 时钟 | 125 MHz | 布线后时序与 SLCR 读回 |
| PL 核调用合计 | 约 1.484 s/图 | 同两张固定输入实测 |
| 含逐层 CRC 自检总耗时 | 约 2.028 s/图 | 优化版完整模型程序 |
| 新演示服务板端总耗时 | 约 1.713 s/图 | 省略逐层 CRC，保留真实网络与评分 |
| 资源 | 25,750 LUT / 33,207 FF / 203 DSP / 57 BRAM36 | Vivado 实现报告 |
| 时序 | WNS +0.175 ns / WHS +0.038 ns | 125 MHz 布线后报告 |
| 正确性 | 31 组 C/RTL；两图 58 阶段 CRC；上传链路异常图逐像素一致 | `sim/results/`、`board/evidence/` |

JTAG 下载、图片传输、图像预处理不计入上述核耗时；前端显示的“本次处理”另外包含上位机与 JTAG 等开销。单核 ARM NEON 基线算子约 32.157 s，当前核调用约 1.484 s，约 21.68 倍；这是本工程特定实现与输入的比较，不代表所有 CPU 库的上限。

## 本次准确率评估

已收到四组共 284 张裁剪图（224 种图片哈希），使用同一冻结模型与阈值重新推理；这些图片曾参与方法排查，属于回顾性评估，不是新盲测。不同组含重复图片和不同裁剪版本，分别统计，不合并报一个准确率。

| 数据组 | 数量 | FP32 准确率 | 部署 INT8 准确率 | INT8 AUROC |
|---|---:|---:|---:|---:|
| 早期开发 | 48 | 89.58% | 93.75% | 96.88% |
| 早期留出裁剪 | 33 | 96.97% | 96.97% | 100.00% |
| 扩批开发 | 155 | 79.35% | 81.94% | 60.35% |
| 扩批留出 | 48 | 68.75% | 66.67% | 74.02% |

扩批留出 INT8 判对 32/48，32 张缺陷均检出，16 张正常全部误报；FP32 也有 15 张正常误报。当前模型对扩批样本的误报问题尚未解决，不能只引用早期较好的 96.97%。测试没有调整模型、量化或阈值。

排除参与标定的 D19、N17 整个实物组后，对两组留出中的 75 张图实际执行 FPGA 推理，逐图完整异常响应与整数参考比对。详细结果见 `report/accuracy_evaluation.md` 与 `sim/results/received_accuracy/`。输入、标签与 SHA256 在 `data/test_inputs/evaluation_manifest.json`。

原早期 35 张留出照片有 2 张定位失败，只有 33 张成功裁剪图在本次交接中；定位拒绝仍保留历史记录，不声称重新验证了原图全流程。新实物盲测和像素级定位精度仍未完成。新的独立数据可用 `sim/evaluate_accuracy.py`，按实物分组并排除标定组。

## 目录对照

| 指南目录 | 本工程组织 |
|---|---|
| `src/` | `accelerator/` 冻结 HLS、PS 自检程序及其原构建入口；`model/` 固定模型参考；`ps_demo/` 图片输入服务；`demo/` 本地前后端 |
| `sim/` | 测试入口、原始 C/RTL 日志、统计结果、上传异常图对照和浏览器验证 |
| `build/` | 重建入口、工程恢复、交付检查及资源/时序/优化历史报告 |
| `board/` | bit、ELF、XSA、已布线 checkpoint、IP 归档、上板/演示服务、实测证据 |
| `data/` | 固定原模型、样例、划分与评分表、竞赛指南、文件身份清单 |
| `skill/` | 通用黄金参考校验、时序读取、提示词工作流与失败案例 |
| `report/` | 可编辑报告初稿、PDF、协作记录、复现手册和拍摄脚本 |

`src/accelerator/` 保留已验证版本的独立包布局，避免整理时改变计算源码和量化数据；重复放置的板端产物和分类证据由 SHA256 核验。工具自动生成的原生 RTL/IP 文件名保留在小写归档内或 Git 忽略的工具工作目录中；手工维护的提交文件名使用小写英文，按指南保留 `README.md` 标准例外。

桌面目录原有的手工资料保存在 `data/legacy_original/`，仅供历史追溯；原报名截图单独保存在 `data/private_archive/`。这两个目录与原有 `build/work/` 缓存均保留在本机，不放入公开交付压缩包，也不作为当前验证证据。

## 复现与检查

已验证环境为 Windows、Vivado/Vitis 2025.2、Python 3.11.17、PyTorch 2.7.1+cu128、torchvision 0.22.1+cu128、NumPy 1.26.4、Pillow 10.4.0、scikit-learn 1.5.2。GPU 仅用于电脑参考计算，板端网络不依赖 PC GPU。

```powershell
python build/verify_delivery.py
python sim/test_delivery_tools.py
python build/restore_prebuilt.py
python sim/evaluate_accuracy.py
```

从源码重建：参考 `report/reproduction.md` 设置 `EA_PYTHON`、`EA_BSP` 和 AMD 工具路径，再执行 `build/rebuild.cmd`。复现完整综合、RTL 仿真和布局布线需要相应工具与时间；`restore_prebuilt.py` 只是还原已通过验证的原生 IP 文件，不冒称重新综合。

双击 `board/view_implemented.cmd` 可在 Vivado 查看交付的已实现设计。新生成的可编辑 XPR 位于 `src/accelerator/_build/vivado/ea_full.xpr`。原 D: 工程和本工作区此前版本未被改写。

本地交付压缩包为 `build/efficientad_submission.zip`，配套 `build/submission_archive.sha256` 与 `data/submission_manifest.json`。修改文件后可执行 `python build/package_submission.py` 重新审计并打包；私人报名截图、旧资料和工具缓存被排除。

## 提交状态

报告是初稿。新实物盲测、扩批正常误报改进、官方海报模板、报名信息/板卡修订核验、现场相机与录屏实际拍摄仍待补齐；详见 `report/contest_compliance.md`。这次只整理本地工程，没有替团队向赛事或 Git 远端提交。

自有代码沿用 `license.txt` 的 MIT 协议；EfficientAD 候选代码来源与 Apache 2.0 许可、FINN 辅助库的 BSD 3 Clause 许可在 `report/sources.md` 中单独登记。没有把完整 FINN 编译器、现成 DPU 或 PYNQ Overlay 当作已实现成果。
