# 从零复现与运行说明

## 一 环境和身份

目标为 Windows、Vivado/Vitis 2025.2 与 Zynq7020 工程目标 xc7z020clg484-2。原开发机 AMD 工具位于 `D:/amd/2025.2`。完整硬件模型已冻结，不需要先重新训练。

电脑参考与网页环境已验证 Python 3.11.17、NumPy 1.26.4、Pillow 10.4.0、PyTorch 2.7.1+cu128、torchvision 0.22.1+cu128、scikit-learn 1.5.2。无 NVIDIA GPU 时可使用 PyTorch CPU 版本，电脑整数参考会明显变慢；FPGA 推理本身不使用 PC GPU。

```powershell
conda create -n efficientad_demo python=3.11
conda activate efficientad_demo
python -m pip install numpy==1.26.4 pillow==10.4.0 scikit-learn==1.5.2
python -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
```

上面的 CUDA 索引适用于相应 NVIDIA 环境；CPU 环境按 PyTorch 官方安装入口选择 CPU wheel。请先核对现有环境，不必重复安装到已有 `efficientad` 环境。报告中的 PC GPU 速度不是 FPGA 的推理速度。

## 二 文件与数值自检

在本目录根运行：

```powershell
python build/verify_delivery.py
python sim/test_delivery_tools.py
python build/restore_prebuilt.py
python sim/evaluate_accuracy.py
```

最后一条只运行包内两张标定样例，预期 INT8 分数为 0.345157206 与 0.073264331，逐阶段 CRC 匹配；输出明确标为一致性检查。不要将两张图片 2/2 判对写成独立准确率。

`restore_prebuilt.py` 从交付 IP 归档还原原生工具文件，核对与原通过 C/RTL 的文件身份；它不是重新综合。已实现设计可用 `board/view_implemented.cmd` 查看 checkpoint。

## 三 从源码重新构建硬件

1. 安装并配置 Vivado/Vitis 2025.2，确认支持 Zynq7000 的目标器件。
2. 修改命令入口中的 AMD 工具目录，或保持已验证的 `D:/amd/2025.2`。
3. 如果不复用已有 PS BSP，在 Vitis 以 `board/ax7021_efficientad_full.xsa` 创建平台，选择 `ps7_cortexa9_0` 与 standalone，Build 平台后找到包含 `Xilinx.spec`、`include/`、`lib/` 的域目录。
4. 设置 `EA_BSP` 为该域路径，`EA_PYTHON` 为构建脚本使用的 Python，必要时设置 `EA_GCC` 为相应 ARM 编译器完整路径。
5. 执行 `build/rebuild.cmd`。HLS 使用 8 ns 目标，先做 C、综合、IP 导出，再做 31 组 C/RTL；Vivado 在独立目录创建工程、布线并验证 setup/hold；最后编译 PS 自检程序。
6. 检查 `src/accelerator/logs/`，新 XPR 在 `src/accelerator/_build/vivado/ea_full.xpr`。不允许只刷新版本号就沿用旧 RTL。
7. 新生成的文件在 `src/accelerator/generated/`；核对报告后才能更新 `board/` 对应文件与身份清单，不能混用不同构建的 bit、XSA、PS 初始化和 ELF。

首次完整构建预计需要数十分钟，取决于 CPU、内存及工具缓存。新版本必须重新建立 C/RTL 和板测证据，旧截图不能替代新构建结果。

## 四 运行现有板端自检

板卡接原配电源和 JTAG USB，确认 Digilent 线缆序列号配置与实际一致。本机已验证序列号写在 JTAG 脚本中；换板时必须修改并人工确认，不能自动挑选另一块板。

执行 `src/accelerator/run_overlap.cmd`，串口为 COM11、115200、8N1。两个完整模型结果应分别为 DEFECT 与 NORMAL，58 个阶段 CRC 通过。该程序含逐层 CRC，自检总耗时约 2.028 s/图，核调用约 1.484 s。

## 五 演示前端与新图片输入

设置 `EA_PYTHON` 为电脑参考环境，双击 `start_demo.cmd`。网页仅监听 `127.0.0.1:8765`，不向公网发送图片。

“初始化 FPGA”通过 JTAG 临时配置 bit 和 `efficientad_demo.elf`；不写 Flash。演示 ELF 是持久服务，收到请求后执行完整三网络，ARM 评分并返回 56x56 融合图及 29 阶段计时；上位机按同一规则恢复到 256x256。

前端可以上传已裁剪图，或对原始照片启用自动定位。定位器针对本批白色固定座、俯拍和有对比度背景验证，遇到模糊、遮挡、出框或多目标应拒绝，不能保证任意现场泛化。摄像头取景与录屏必须由用户点击授权。

`build/build_demo.py` 可重编译演示 ELF。它复用同一冻结权重和评分代码，只改 PS 输入输出协议；本次已对两张上传样例的完整异常图逐像素比对，最大绝对误差为 0。

## 六 本次回顾评估与后续盲测

本次收到的四组数据已存入 `data/test_inputs/`。执行 `python sim/evaluate_received_inputs.py --board-heldout` 可复现284张FP32/INT8回顾评估与75张板测，预计数分钟。原模型和阈值不变。

对后续未参与训练和方法排查的新实物，提供 256x256 RGB 裁剪图目录和 CSV，字段为 `image,label,object_group,role`；标签为 `good` 或 `defect`，role 为 `test` 或 `holdout`。使用已冻结的正常化统计、原阈值和同一份 INT8 权重，不依据测试结果调参。

```powershell
python sim/evaluate_accuracy.py --images data/independent_test/images --labels data/independent_test/labels.csv --output sim/results/independent_accuracy
```

脚本按实物组排除 D19、N17，保存逐图 FP32/INT8 分数、文件哈希、混淆矩阵、准确率、AUROC、精确率、召回率和 F1。现场原图应先按同一裁剪规范生成输入，并单独统计定位失败和自动处理覆盖率，不能悄悄删掉失败图片。

## 七 浏览器回归与交付打包

网页测试入口为 `sim/test_frontend.cjs`，需要 Node.js、Playwright 和本机 Edge；可用环境变量 `EA_PLAYWRIGHT` 指定已有 Playwright 模块路径。先启动本地演示服务，再运行 `node sim/test_frontend.cjs`；测试会临时初始化指定 FPGA，验证两张样例、上传、导出、最新精度卡片和窄屏，并保存截图与 JSON。摄像头和屏幕选择仍需本人授权。

执行 `python build/package_submission.py` 生成清洁压缩包、SHA256 与逐文件清单，排除本机缓存、旧资料、报名隐私截图；压缩完成后逐项核对 ZIP 中的实际字节哈希。
