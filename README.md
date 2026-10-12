# 基于 FPGA 的工件外观检测系统

2026 年全国大学生嵌入式芯片与系统设计竞赛 FPGA 创新设计赛道作品。

| 项目 | 内容 |
| --- | --- |
| 团队 | AMDYES |
| 组队 | 1 名队长、2 名队员，均为大三；在读本科资格以报名审核为准 |
| 参赛厂商 | AMD |
| 选定赛道 | AMD 自主选题（初级），对应选题指南第 3.3 节 |
| 目标器件 | ALINX 板卡，实物照片可见 XC7Z020；布局疑似 AX7021 系列，版本待核对 |
| 算法方向 | 先复现 EfficientAD 完整推理，再研究 Zynq PS/PL 迁移；几何约束为可能的后续扩展 |
| 开源协议 | [MIT](LICENSE) |

## 项目简介

本作品面向小批量规则工件的外观质量检测需求，拟基于 Zynq-7020 构建桌面式视觉检测系统。在固定照明与定位条件下，检测局部破损、缺角、缺孔等缺陷，输出异常区域、合格判定和检测统计，并支持结果显示与记录保存。

团队当前目标是先在公开数据集上复现并评估 EfficientAD 推理，再将推理链路迁移到 ALINX Zynq-7020 板上，最后考虑实物。原论文包含局部教师–学生异常图及自动编码器相关的异常图；当前仓库尚无这些网络、权重、融合或板端实现。原先提出的几何约束是可能的后续扩展，不能替代论文完整推理或声称已经实现。

硬件侧计划围绕卷积、特征差分与通道累加设计可复用加速单元，研究 INT8 权重与激活量化、分块缓存及数据流优化。竞赛版拟由 Zynq 的 ARM（PS）负责图像输入、参数配置与结果显示，FPGA（PL）负责计算加速。课程版可在 PL 中加入 RISC-V SoC 并复用加速器；两版分别构建和验证。网络规模、接口和阈值由后续基线测试与资源评估确定。

当前仓库已有异常评分图的软件参考计算，以及一个固定机位的**灰度像素模板演示**：输入正常参考图和待测图，保存差异图、缺陷掩码、红色叠加图和 JSON 判定。演示只在人工生成的规则工件图片上验证，使用像素差异而非教师/学生网络；阈值未用真实样本标定。尚无模型权重、真实数据评估、硬件加速器、构建脚本或板级实测数据。

## 当前开发入口

- [项目工作交接报告](report/team_outline.md)：先读状态快照、三条工作线、交付接口和验收节点；新结果以进度记录为准。
- [工作记录与下一步](report/progress.md)：记录每次改动、原因、验证和待办，供队员同步进度。
- [AMD 自主选题赛道规则核对表](report/contest_rules.md)：初级组资格、器件、交付物、AI 协作记录与待核验事项；开始新任务前先核对。
- [EfficientAD 数据集与板端迁移计划](report/efficientad_plan.md)：来源核对、阶段完成判据和 ALINX 板卡待确认信息。
- [GitHub 协作步骤](report/collaboration.md)：通过 GitHub Desktop 获取项目、提交分支和同步。
- [异常评分图参考实现](src/score_map.py)：消费已对齐的教师/学生特征，不含网络训练或权重。
- [图片模板基线](src/image_baseline.py)：固定机位、同尺寸图片的像素差异判定；与 EfficientAD 模型分开记录。
- [模拟图片生成器](sim/make_demo_images.py)：生成正常、缺角、缺孔三张人工图片，仅用于流程检查。

在仓库根目录安装软件参考模块依赖并运行数值检查：

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s sim -v
```

在仓库根目录运行电脑端图片演示（PowerShell、终端均可；生成文件放在被 Git 忽略的 `build/work/`）：

```sh
python -m sim.make_demo_images --output-dir build/work/demo_inputs
python -m src.image_baseline build/work/demo_inputs/normal.png build/work/demo_inputs/missing_corner.png --output-dir build/work/demo_corner
python -m src.image_baseline build/work/demo_inputs/normal.png build/work/demo_inputs/missing_hole.png --output-dir build/work/demo_hole
```

在 `build/work/demo_corner/` 和 `build/work/demo_hole/` 查看 `result.json`（判定、区域数、像素数、区域坐标）、`score.npy`（浮点平方差）、`score.png`（差异可视化）、`mask.png`（保留的异常区域）和 `overlay.png`（待测图上红色标记）。上述模拟图应分别判为 `defect`，缺角面积 256 像素、缺孔面积 144 像素；正常图与自身比较应判为 `normal`。这只是软件流程的预期值，不是检测准确率或板上结果。

换成自采图片时，用一张正常图片作为 `reference`，把待测图片作为 `target`。两张图必须同尺寸、相机与工件位置对齐、照明尽量固定，否则移动或光照变化也会产生红色区域。`--threshold` 是归一化灰度差的平方阈值，默认 `0.25`；`--min-area` 是保留区域的最小像素数，默认 `9`。这些默认值只为模拟图片设置，需要从独立的真实验证集重新确定。输出框坐标的 `right`、`bottom` 为不包含边界。

加入模型之后，保存教师和学生的 `[C,H,W]` 特征为 `.npy`，再执行：

```sh
python src/score_map.py teacher.npy student.npy --output score.npy
```

只有在两组 INT8 特征的量化尺度与零点已经对齐后才可追加 `--int8`。输出是 `[H,W]` 的局部异常分数图；阈值、几何约束和最终判定尚未实现。

## 目录结构

仓库根目录 `fpga/` 即规则中的 `<project_name>/`。以下七个目录与选题指南第 3.3.5.4 节逐项对应；各目录中的 `README.md` 说明后续文件的归属，并使目录可被 Git 保存。

```text
fpga/
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
├── src/
│   ├── README.md
│   ├── image_baseline.py
│   └── score_map.py
├── sim/
│   ├── README.md
│   ├── make_demo_images.py
│   ├── test_image_baseline.py
│   └── test_score_map.py
├── build/
│   └── README.md
├── board/
│   └── README.md
├── data/
│   └── README.md
├── skill/
│   └── README.md
└── report/
    ├── README.md
    ├── progress.md
    ├── collaboration.md
    ├── contest_rules.md
    ├── efficientad_plan.md
    └── team_outline.md
```

| 目录 | 比赛要求 | 本项目内容 |
| --- | --- | --- |
| [src/](src/README.md) | 设计源码 | 教师/学生网络训练与参考实现、RTL/HLS 加速单元、PS 侧调用与检测流程 |
| [sim/](sim/README.md) | 仿真或验证脚本与结果 | 算子和系统验证、量化误差分析、异常图与几何判定的参考比对 |
| [build/](build/README.md) | 可复现构建脚本、综合与实现报告 | Vivado/Vitis 构建入口、资源报告、时序报告和优化前后对比 |
| [board/](board/README.md) | 上板工程、运行脚本与实测输出 | 板卡配置、约束与部署文件、运行入口、实测输出与参考比对 |
| [data/](data/README.md) | 测试数据与参考结果 | 工件样本、划分清单、缺陷标注、黄金参考和量化校准数据 |
| [skill/](skill/README.md) | 可复用技能包 | 提示词工作流、工程模板、校验方法和经验证的排错经验 |
| [report/](report/README.md) | 设计报告与大模型协作记录 | 设计依据、软硬件划分、优化结果、复现说明和协作纠错过程 |

新增目录及普通文件使用英文小写字母、数字、下划线或连字符命名，不使用中文、空格或特殊字符。`README.md` 按规则目录示例保留标准名称，`LICENSE` 沿用仓库现有许可证，`.gitignore` 用于排除工具缓存；中文说明写在正文中。

## 环境与复现步骤

选题指南第 3.3.3.1 节推荐 Vivado / Vitis 2026.1 或 2025.2。若采用其他版本，应在设计报告中解释原因并验证构建脚本可复现。实际使用的工具版本、板卡型号、操作系统及软件依赖将在实现阶段记录。

目前可复现的是仓库结构、评分图参考计算和人工图片上的电脑端模板演示：

```sh
git clone https://github.com/shenyiqiu2020-create/fpga.git
cd fpga
```

系统实现完成后，按以下顺序补齐可执行命令、输入文件、预期输出和验证结果：

1. 在 `board/` 声明板卡、器件完整型号、相机接口、照明和工件定位方式；在 `report/` 记录工具和依赖版本。
2. 在 `data/` 登记数据来源、授权、训练/验证/测试划分以及获取方法。
3. 在 `src/` 提供离线训练、软件基线、量化和硬件实现；记录权重来源与校验值。
4. 在 `sim/` 执行仿真和黄金参考比对，记录误差容限、判定阈值及结果。
5. 在 `build/` 执行构建，保存综合、实现、资源和时序报告。
6. 在 `board/` 部署运行，保存实测输出、参考比对及性能统计。
7. 在 `skill/` 和 `report/` 整理已验证经验、优化对比、协作记录和完整复现说明。

上述系统步骤尚未实现，当前不能用于训练、生成 bitstream 或运行板端检测。规则要求作品最终在板上跑通并提供实测输出，离线数值检查与板级实测结果分别记录。

## 两条实施路线与最小演示

两版可复用同一套图片采集规范、软件参考算法、阈值评估、测试图片和结果格式，但必须分别构建与验收。

| 路线 | 必须补齐的部分 | 当前状态 |
| --- | --- | --- |
| 竞赛版 | Zynq ARM PS 读图、显示和保存；选定并验证一项 PL 计算模块，和软件黄金参考比对；整机上板记录输入、输出、耗时与资源 | 尚未开始板端工作 |
| 课程版 | 在 PL 构建真正运行程序的 RISC-V 内核及存储、总线、外设组成的 SoC，接入可复用检测模块；单独保存程序运行与接口验证证据 | 尚未开始；仅有 Zynq ARM 不满足此要求 |

面向团队提供的 11 月 4 日期限，按“数据集上的 EfficientAD 完整推理基线 → 固定数值与资源预算 → Zynq 板上数据集图片的推理和 PS/PL 比对 → 实物”的顺序推进。板端至少验证一个 PL 算子是本团队的工程目标，**不是指南规定的最低数量**。若器件资源不足，先比较较小模型、PS/PL 分层和量化；任何省略自动编码器或换算法的方案须单独命名、重新评估，不应称为论文完整模型。11 月 4 日须以正式通知核对；阶段判据见 [迁移计划](report/efficientad_plan.md) 和 [工作记录](report/progress.md)。

## 提交依据

本次初始化依据提供的 AMD 2026 选题指南第 3.3 节，重点为第 3.3.5.1 至 3.3.5.4 节（文档页码 21-22），以及报名页面中可见的选定赛道、作品名称和简介。报名页面的简介末尾受滚动区域遮挡，本文概述仅使用可核实内容。

后续提交应包含完整源码、仿真或验证结果、可复现构建脚本、综合与实现报告、上板工程和实测输出、技能包、设计报告及大模型协作记录。仓库中的性能、准确率、资源占用和时钟频率均应来自实际测试，并注明测试条件。
