# 基于 FPGA 的工件外观检测系统

2026 年全国大学生嵌入式芯片与系统设计竞赛 FPGA 赛道 AMD 自主选题初级组项目。

| 项目 | 内容 |
| --- | --- |
| 团队 | AMDYES |
| 组队 | 1 名队长、2 名队员，均为大三；在读本科资格以报名审核为准 |
| 参赛厂商 | AMD |
| 选定赛道 | AMD 自主选题（初级），对应选题指南第 3.3 节 |
| 目标器件 | ALINX 板卡，实物照片可见 XC7Z020；布局疑似 AX7021 系列，版本待核对 |
| 算法方向 | 完整 EfficientAD 是作品主线，保留教师–学生、自动编码器与异常图融合；外缘轮廓级联是尚待独立实物验收的电脑端辅助候选，按实测结果研究 Zynq PS/PL 迁移 |
| 开源协议 | [MIT](LICENSE) |

## 项目简介

**板端部署更新（2026-11-01）：** 同版3000步完整EfficientAD已在XC7Z020工程上跑通两张预存的256×256调试图片：卷积、ReLU、平均池化与网络内部Resize在PL，调度与异常分数在ARM。58个阶段CRC和两张图的最终INT8参考分数通过。最新PE32/Q4核在50 MHz下计算约4.507秒/图，含原有自检总耗时约5.04秒/图，上一版分别约8.914秒和9.44秒。[源码](src/efficientad_pl/README.md)、[部署包与加载说明](board/README.md)、[实测报告](report/efficientad_pl_kernel_20261101.md)已入库。这是完整链路的两张图自检，实时摄像头、持久启动与独立INT8精度评估仍待完成。

本作品面向小批量工件的外观质量检测，计划在 ALINX Zynq-7020 板卡上完成图像输入、缺损判定、异常位置候选、结果显示与记录。首版实物为白色方形扎带固定座，输入是完整入镜的正面照片，判断“正常 / 有可见外缘缺角或缺口”。`do3/D03` 属于内部肋条断损，按已确定的首版范围留档，不混入外缘缺损成绩；工件上的两个实心圆和两个盲凹孔是正常结构。

**算法与当前实现（2026-10-27）：** 完整 EfficientAD 是作品主线，保留教师–学生、自动编码器、两类异常图融合和位置输出。单张照片入口默认使用已发布供 B/C 下载的 3000 步完整 EfficientAD。A 另开发了电脑端外缘辅助级联：在原始照片上重新定位工件，严格轮廓可测时用形状分类器；仍未通过时由单独训练的宽松边界分类器给出带复核标记的二元判断。该级联是针对自采工件外缘缺料的辅助候选，尚未替换默认 EfficientAD，也未成为板端模型。[算法和分母](report/shape_cascade_candidate_20261027.md)及[单张运行命令](sim/README.md)分别记录两条路线。

**现有照片上的证据：** 347 张原图中一张组内重复照在数据准备时跳过，346 张唯一照再排除 `D03` 两张，首版范围为 **344 张**。新级联对 344 张均给出正常或缺损判断；按实物及误复制关系分组的回顾性五折验证，三次划分各判对 **340/344 张**，仍各错 4 张。旧 48 张照片已经参与方法排查，这不是新工件、新背景或新灯光的独立准确率。完整 EfficientAD 的 9000 步扩批实验在当时 48 张留出照片中虽然报出 32/32 张缺损，却把 16/16 张正常照误报；因此没有替换默认 3000 步版本。缺口位置输出目前也只是候选，尚无定位准确率。[逐图数据](data/tie_mount_expanded_20261026_inventory.csv)和[进度记录](report/progress.md)保留证据。

**交接与下一步：** B/C 已可从[私有 Release](https://github.com/shenyiqiu2020-create/fpga/releases/tag/tie-mount-batch-20261026-3000step)取得同版 3000 步完整 EfficientAD 权重及黄金张量；旧 `golden_v3` Release 已退役。外缘级联的[代码](sim/train_tie_mount_shape_cascade.py)和[报告](report/shape_cascade_candidate_20261027.md)已随当前版本提供；训练后的模型 JSON 留在 Git 忽略的本机目录，尚未交给 B/C。A 仍需用**未参与开发的新实物**在新纯色背景、新灯光和新破坏形态下盲测并冻结最终方案。B 负责板卡和系统，C 负责 PL 加速；两张预存图的完整PS/PL推理与实测已经完成；下一步按确认的板卡接口加入实时摄像头；模型训练仍在电脑端进行。课程版 RISC-V SoC 单独构建与验收。[交接报告](report/team_outline.md)、[采集方案](data/capture_plan.md)和[板卡现状](board/README.md)列出责任与验收条件。

## 历史实验记录

以下结果属于发生时的冻结快照，不代表当前模型性能或交付状态：

- 2026-10-25 的 300/1000 步早期工件试验仍有明显正常误报；见[旧逐图分数](data/tie_mount_binary_baseline_20261025.csv)和[阶段记录](report/progress.md)。
- 2026-10-26 的 3000 步完整 EfficientAD 已形成 B/C 数值交接，早期按实物留出照片正常 12/13、缺损 20/20 判对；更大批次暴露出正常误报，不能只引用前一分数。见[数值交接](report/bc_handoff_20261026.md)和[扩批协议](report/expanded_batch_protocol_20261026.md)。
- 2026-10-27 的首个外缘分类候选仅覆盖 327/344 张任务内照片，17 张轮廓拒判；此数字已由上方双路级联更新。旧方案与增强对照见[历史候选记录](report/shape_assisted_candidate_20261027.md)。
- MVTec AD `bottle` 类 1000 步电脑端 EfficientAD 试验与固定像素模板演示，是不同数据和算法的早期参考，不能充当自采工件或板端成绩；见[迁移计划](report/efficientad_plan.md)。

## 当前开发入口

- [项目工作交接报告](report/team_outline.md)：先读状态快照、三条工作线、交付接口和验收节点；新结果以进度记录为准。
- [B/C 数值接口交接](report/bc_handoff_20261026.md)：新模型与两份同版黄金张量的私有 Release、哈希、接收复核方法及 B/C 各自应返回的证据。
- [最新照片清单](data/tie_mount_expanded_20261026_inventory.csv)与[级联候选记录](report/shape_cascade_candidate_20261027.md)：现有实物、不同光照照片、分组验证、回退路径及不能宣称的泛化范围。
- [完整 EfficientAD 单张推理](sim/README.md)与[辅助级联训练脚本](sim/train_tie_mount_shape_cascade.py)：前者是默认电脑端入口，后者须显式指定本机实验模型，两套成绩分开报告。
- [工作记录与下一步](report/progress.md)：记录每次改动、原因、验证和待办，供队员同步进度。
- [AMD 自主选题赛道规则核对表](report/contest_rules.md)：初级组资格、器件、交付物、AI 协作记录与待核验事项；开始新任务前先核对。
- [课程大作业要求与方案交接](report/course_requirements.md)：课程平台截图的要求、团队保留的 RISC-V 必达条件、课程版缺口和打包清单；与 AMD 赛道规则分开。
- [EfficientAD 数据集与板端迁移计划](report/efficientad_plan.md)：来源核对、阶段完成判据和 ALINX 板卡待确认信息。
- [GitHub 协作步骤](report/collaboration.md)：通过 GitHub Desktop 获取项目、提交分支和同步。
- [异常评分图参考实现](src/score_map.py)：消费已对齐的教师/学生特征，不含网络训练或权重。
- [图片模板基线](src/image_baseline.py)：固定机位、同尺寸图片的像素差异判定；与 EfficientAD 模型分开记录。
- [模拟图片生成器](sim/make_demo_images.py)：生成正常、缺角、缺孔三张人工图片，仅用于流程检查。
- [EfficientAD 人工数据流程检查生成器](sim/make_efficientad_smoke_data.py)：将同一批人工图片排成候选训练脚本所需的目录结构；重复样本不用于精度结论。
- [EfficientAD 异常图评估脚本](sim/evaluate_efficientad_maps.py)：核对保存图与测试图片逐张对应，输出图像级 AUC 和逐张分数；不产生二值判定或像素定位指标。
- [EfficientAD 分图与阈值导出脚本](sim/export_efficientad_components.py)：读取本机 1,000 步模型，导出教师–学生图、自动编码器图和融合图，并用正常验证图确定图像级判定阈值；需独立 Python 3.10 环境。
- [EfficientAD 像素位置评估脚本](sim/evaluate_efficientad_localization.py)：用异常测试图的像素标注计算逐图像素 AUC、按缺陷类别汇总，并生成本地误判样本对照图；不自动给出可靠缺陷框。
- [工件采集方案](data/capture_plan.md)：新实物破坏前后配对拍摄、不同背景与灯光条件、按实物隔离的独立验收和原图记录。
- [扎带座定位裁剪](src/tie_mount_crop.py)与[按实物分组的数据准备](sim/prepare_tie_mount_dataset.py)：首版自采图片输入流程；训练结果和适用边界见采集方案。
- [外缘缺损几何基线](src/tie_mount_outline.py)：根据完整正面轮廓估计平面方向并比较四角，输出临时缺损判定与疑似位置；不检测 `D03` 断肋。

在仓库根目录安装软件参考模块依赖并运行数值检查：

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s sim -v
```

若 Windows 受限环境禁止测试写入系统临时目录，可在 PowerShell 中先执行 `New-Item -ItemType Directory -Force build/work/tmp | Out-Null; $env:TEMP = (Resolve-Path build/work/tmp).Path; $env:TMP = $env:TEMP`，再运行 `python -B -m unittest discover -s sim -v`。临时输出位于 Git 忽略的 `build/work/`。

在仓库根目录运行电脑端图片演示（PowerShell、终端均可；生成文件放在被 Git 忽略的 `build/work/`）：

```sh
python -m sim.make_demo_images --output-dir build/work/demo_inputs
python -m src.image_baseline build/work/demo_inputs/normal.png build/work/demo_inputs/missing_corner.png --output-dir build/work/demo_corner
python -m src.image_baseline build/work/demo_inputs/normal.png build/work/demo_inputs/missing_hole.png --output-dir build/work/demo_hole
```

在 `build/work/demo_corner/` 和 `build/work/demo_hole/` 查看 `result.json`（判定、区域数、像素数、区域坐标）、`score.npy`（浮点平方差）、`score.png`（差异可视化）、`mask.png`（保留的异常区域）和 `overlay.png`（待测图上红色标记）。上述模拟图应分别判为 `defect`，缺角面积 256 像素、缺孔面积 144 像素；正常图与自身比较应判为 `normal`。这只是软件流程的预期值，不是检测准确率或板上结果。

换成自采图片时，用一张正常图片作为 `reference`，把待测图片作为 `target`。**当前像素模板演示不具备方向、背景或光照适应能力**；两张图必须同尺寸、相机与工件位置对齐、照明和背景尽量相同，否则移动、旋转、背景或光照变化也会产生红色区域。实物多条件处理将另行实现并验证，不能把模板演示的结果当成该目标已完成。`--threshold` 是归一化灰度差的平方阈值，默认 `0.25`；`--min-area` 是保留区域的最小像素数，默认 `9`。这些默认值只为模拟图片设置，需要从独立的真实验证集重新确定。输出框坐标的 `right`、`bottom` 为不包含边界。

加入模型之后，保存教师和学生的 `[C,H,W]` 特征为 `.npy`，再执行：

```sh
python src/score_map.py teacher.npy student.npy --output score.npy
```

只有在两组 INT8 特征的量化尺度与零点已经对齐后才可追加 `--int8`。该单独评分脚本仅输出 `[H,W]` 的局部异常分数图；完整电脑端推理与二分类入口见[仿真说明](sim/README.md)。

## 目录结构

仓库根目录 `fpga/` 即选题指南中的项目目录。以下目录保存电脑端实现和板级交付。训练用`.pth`、原始照片与工具数据库仍使用私有Release或Git忽略的`build/work/`；本次有意跟踪一份约39 MB的已验证部署ZIP，包含固件、INT8参数和两张预处理调试输入，方便队友直接上板。

| 目录 | 当前内容与后续交付 |
| --- | --- |
| [src/](src/README.md) | 异常图数值参考、工件裁剪、原图重定位和外缘辅助分类；后续加入板端相关源码 |
| [sim/](sim/README.md) | 完整 EfficientAD 电脑端推理入口、模型清单、级联训练/推理、黄金张量验证与软件测试 |
| [build/](build/README.md) | 后续可复现构建脚本及资源、时序报告；`build/work/` 存本机实验文件且不纳入 Git |
| [board/](board/README.md) | 板卡版本、启动、PS/PL部署包和两张预存图的完整模型实测证据 |
| [data/](data/README.md) | 可共享的照片清单、分组、历史分数和采集规范；原始照片留在本机 |
| [skill/](skill/README.md) | 待验证的可复用工程技能包 |
| [report/](report/README.md) | 进度、交接、算法实验、规则核对及最终设计报告资料 |

目录和普通文件名按指南使用英文小写字母、数字、下划线或连字符；中文说明写在正文中。

## 环境与复现步骤

选题指南第 3.3.3.1 节推荐 Vivado / Vitis 2026.1 或 2025.2。若采用其他版本，应在设计报告中解释原因并验证构建脚本可复现。本次板端构建与验证使用Windows及Vivado/Vitis 2025.2，工程目标xc7z020clg484-2；整板PCB版本仍待标签核实。

仓库中已有电脑端完整 EfficientAD 单张推理入口、外缘级联实验入口及数值校验脚本；私有模型 ZIP、原始照片和级联训练产物不随 Git 克隆，须按[仿真说明](sim/README.md)与[数值交接](report/bc_handoff_20261026.md)准备。克隆代码：

```sh
git clone https://github.com/shenyiqiu2020-create/fpga.git
cd fpga
```

运行前应核对代码提交、模型包 ID 与黄金张量是否同版。训练权重与照片仍需从相应私有 Release 或本机受控目录另行取得。

板级系统后续按以下顺序补齐可执行命令、输入文件、预期输出和验证结果：

1. 在 `board/` 声明板卡、器件完整型号、相机接口、照明和工件定位方式；在 `report/` 记录工具和依赖版本。
2. 在 `data/` 登记数据来源、授权、训练/验证/测试划分以及获取方法。
3. 在 `src/` 提供离线训练、软件基线、量化和硬件实现；记录权重来源与校验值。
4. 在 `sim/` 执行仿真和黄金参考比对，记录误差容限、判定阈值及结果。
5. 在 `build/` 执行构建，保存综合、实现、资源和时序报告。
6. 在 `board/` 部署运行，保存实测输出、参考比对及性能统计。
7. 在 `skill/` 和 `report/` 整理已验证经验、优化对比、协作记录和完整复现说明。

电脑端训练、推理与数值参考已形成实验成果；两张预存图的完整模型bitstream、源码、加载脚本与板测已交付。整板版本确认、实时摄像头、持久启动和独立精度验收仍未完成。规则要求作品最终在板上跑通并提供实测输出，离线数值检查与板级实测结果分别记录。

## 两条实施路线与最小演示

两版可复用同一套图片采集规范、软件参考算法、阈值评估、测试图片和结果格式，但必须分别构建与验收。

| 路线 | 必须补齐的部分 | 当前状态 |
| --- | --- | --- |
| 竞赛版 | Zynq ARM PS 读图、显示和保存；选定并验证一项 PL 计算模块，和软件黄金参考比对；整机上板记录输入、输出、耗时与资源 | 尚未开始板端工作 |
| 课程版 | 在 PL 构建真正运行程序的 RISC-V 内核及存储、总线、外设组成的 SoC，接入扩展检测 IP；嵌入式程序实际配置并读取 IP，单独保存设计、软件、验证、实物演示和提交材料 | 尚未开始；仅有 Zynq ARM 不满足本队保留的 RISC-V 要求，详见[课程要求交接](report/course_requirements.md) |

面向团队提供的 11 月 4 日期限，按“数据集上的 EfficientAD 完整推理基线 → 固定数值与资源预算 → Zynq 板上数据集图片的推理和 PS/PL 比对 → 实物”的顺序推进。板端至少验证一个 PL 算子是本团队的工程目标，**不是指南规定的最低数量**。若器件资源不足，先比较较小模型、PS/PL 分层和量化；任何省略自动编码器或换算法的方案须单独命名、重新评估，不应称为论文完整模型。11 月 4 日须以正式通知核对；阶段判据见 [迁移计划](report/efficientad_plan.md) 和 [工作记录](report/progress.md)。

## 提交依据

最初项目目录依据团队提供的 AMD 2026 选题指南第 3.3 节及报名页面建立；本页现状已按后续实物、软件实验和交接证据更新。指南口径及页码以[规则核对表](report/contest_rules.md)为准。

后续提交应包含完整源码、仿真或验证结果、可复现构建脚本、综合与实现报告、上板工程和实测输出、技能包、设计报告及大模型协作记录。仓库中的性能、准确率、资源占用和时钟频率均应来自实际测试，并注明测试条件。

课程作业另有独立提交：课程页面截图显示上传窗口为 10 月 13 日至 12 月 31 日，页面同时写“无截止日期”，因此须向教师核对最终期限；不能用这个窗口推迟竞赛准备。课程压缩包需有 PDF 报告、整理后的代码、佐证材料、AI 使用与验收记录及不超过 10 MB 的实物演示视频，整包不超过 30 MB。具体口径和未完成项见[课程要求交接](report/course_requirements.md)。
