# EfficientAD 数据集验证与 Zynq 推理迁移计划

本页记录**团队目标与执行顺序**，不是已完成结果，也不是 AMD 指南的附加硬性条款。2026-10-11 团队确认：1 名队长和 2 名队员均为大三；板卡品牌为 ALINX，实物照片可见 XC7Z020、布局疑似 AX7021 系列（版本待核对，见 [board/README.md](../board/README.md)）；先在公开数据集上验证 EfficientAD，再将推理链路迁移到板端，最后考虑自采实物。2026-10-15 组员报告工件已到货 100 件，尚未试拍；采集与按工件编号划分见 [data/capture_plan.md](../data/capture_plan.md)。课程 RISC-V SoC 路线仍单独验收，新课程页面要求见 [course_requirements.md](course_requirements.md)。赛道规定见 [contest_rules.md](contest_rules.md)。

## 论文、代码和数据分别核对

| 项目 | 已核实 | 尚需确认 |
| --- | --- | --- |
| 论文 | [EfficientAD 原论文（WACV 2024）](https://openaccess.thecvf.com/content/WACV2024/papers/Batzner_EfficientAD_Accurate_Visual_Anomaly_Detection_at_Millisecond-Level_Latencies_WACV_2024_paper.pdf) 可公开阅读，报告了 MVTec AD、VisA、MVTec LOCO AD 上的实验 | 可读论文不等于作者公开了训练代码、权重或允许任意再分发 |
| 代码 | [nelson1425/EfficientAD](https://github.com/nelson1425/EfficientAD) 是**第一候选**公开仓库，自称非官方实现并标示 Apache-2.0 许可；已固定提交、教师权重哈希；[Anomalib EfficientAd](https://github.com/open-edge-platform/anomalib/blob/main/src/anomalib/models/image/efficient_ad/README.md) 是备选 | 已在真实 `bottle` 类跑完 1,000 步、分图导出、验证集定阈值和逐图平均像素 AUC；训练少于默认步数，尚无缺陷框/IoU，仍属初步基线 |
| 数据 | [MVTec AD 官方数据页](https://www.mvtec.com/research-teaching/datasets/mvtec-ad) 提供正常训练图、正常/异常测试图及像素标注，许可为 CC BY-NC-SA 4.0；本机已提取 `bottle` 类，数量与压缩包校验值见 [data/README.md](../data/README.md) | 复核队员下载的官方入口和获取日期；原始数据不直接并入本项目 MIT 仓库；实物扎带座需另采数据 |

现有 `src/score_map.py` 只计算**已对齐特征**的局部教师–学生平方差；`src/image_baseline.py` 是固定位置像素模板，用于文件与结果保存流程检查。两者都不是完整 EfficientAD 推理，也没有论文实验成绩。原论文还使用自动编码器分支处理更广域的逻辑异常，并结合两类异常图；因此不能只跑现有 `score_map.py` 就称为完成论文迁移。

## 阶段与通过条件

| 阶段 | 工作 | 完成证据 |
| --- | --- | --- |
| 0. 锁定基线 | 确定一个代码实现、模型规模（先评估较小版本）、一个 MVTec AD 类别和训练/推理依赖；记录许可、下载来源、提交哈希；使用独立环境，不改坏当前 NumPy/Pillow 演示 | `report/` 记录来源、版本、命令、权重与数据校验值；队友可重建环境 |
| 1. 电脑端数据集验证 | 按选定实现运行教师、学生和自动编码器的完整推理；保存输入、两类异常图、融合图、图像判定和官方格式结果；训练和阈值确定只用规定的数据划分 | 同一批测试图片两次运行结果一致；用官方评估脚本取得实际指标；保留失败样本，不复制论文成绩 |
| 2. 定义迁移边界 | 固定预处理、输入分辨率、权重、归一化、特征形状、异常图融合与阈值；逐层测算参数量、激活内存、算量和软件耗时 | 一份 PS/PL 功能及数据传输接口表，板上内存与资源预算，软件黄金参考及容差 |
| 3. 板上数据集推理 | 先把数据集图片放在 ALINX Zynq 板上，从文件读入；选择经资源预算验证的算子/网络部分在 PL 实现，其余由 ARM PS 执行，完成端到端推理与结果保存 | 板上输入、输出异常图和判定与电脑参考逐样本比对；保留综合/实现报告、时序、资源、实际延迟与功耗条件（若测得） |
| 4. 实物与展示 | 在数据集链路稳定后确定一种实物和固定采集条件，重新收集正常/缺陷样本、校准阈值，再接相机/照明/显示 | 实物照片、标注、误检漏检记录和完整现场演示；与数据集结果分开报告 |

“迁移到 FPGA”在本项目中应写清楚是**整条推理链在 Zynq 板上运行**，以及哪些运算确实由 PL 承担；ARM PS 运行的部分也要如实列出。是否能让教师、学生、自动编码器三个网络全部在 PL 中运行，必须由资源、存储带宽和时序实测决定，当前不能承诺。若完整模型不适合器件，先比较较小模型、分层 PS/PL、定点量化等方案；任何删去自动编码器或改用别的算法的版本要另命名、重新评估，不能冒充论文完整模型。

## 当前输入与待确认事项

1. ALINX 板卡的型号**版本**、FPGA 完整订货料号、DDR 容量、板上系统与可用接口；照片使 AX7021 成为候选，但还不足以选择板级工程、约束和镜像。
2. `nelson1425/EfficientAD` 已下载到 Git 忽略的 `build/work/external/efficientad/`，提交固定为 `fcab5146f84ae17597044ad5ddf1656ccf805401`；随仓库附带教师小模型权重，SHA-256 见[工作交接报告](team_outline.md)。人工图两步检查与真实 `bottle` 数据的 100/1,000 步运行均已完成。外部仓库自报结果不能当成本队实测，1,000 步的本机指标也不能当作论文完整复现。
3. A 工作线电脑已核对：RTX 4060 Laptop GPU（8188 MiB 显存）、驱动 566.24；系统 Python 3.13.0、16 GB RAM。已使用 `uv 0.13.0` 在 Git 忽略的 `build/work/` 中安装 Python 3.10.22 并建立 `efficientad-env`，不改动系统 Python 3.13。torch 1.13.0+cu117、torchvision 0.14.0+cu117、NumPy 1.24.4、Pillow 9.5.0、scikit-learn 1.2.2 已可导入并使用 GPU。队员提供的 `mvtec_anomaly_detection.tar.xz` 已通过完整目录与文件类型检查，提取 `bottle` 类。压缩包内许可及本机哈希见 [data/README.md](../data/README.md)；候选仓库 README 中的旧 MyDrive 直链于 2026-10-12 返回 HTTP 404。

## 真实 `bottle` 类初步运行（电脑端）

本机先运行 100 步检查耗时，再从同一教师初始权重**重新训练** 1,000 步；两次是独立运行，不是续训。候选脚本固定随机种子 42，从 209 张正常训练图划出 188 张训练、21 张正常验证；测试集为 20 张正常和 63 张异常。小模型输入缩放为 `256×256`，脚本将融合异常图插值回原图 `900×900` 保存。`--imagenet_train_path` 保持默认 `none`，即未使用 ImageNet 辅助惩罚项；默认训练步数原为 70,000，本机明确改成 100/1,000。

在仓库根目录用 PowerShell 执行。请确认数据、隔离环境与外部代码位于前述 Git 忽略路径；每次运行使用**新的**输出目录，候选脚本不会覆盖已有目录。

```powershell
$projectRoot = (Get-Location).Path
$env:TEMP = Join-Path $projectRoot 'build/work/tmp'
$env:TMP = $env:TEMP
$runRoot = Join-Path $projectRoot 'build/work/efficientad-real/bottle-repro'
New-Item -ItemType Directory -Force -Path $env:TEMP, $runRoot | Out-Null
Push-Location (Join-Path $projectRoot 'build/work/external/efficientad')
& (Join-Path $projectRoot 'build/work/efficientad-env/Scripts/python.exe') efficientad.py --dataset mvtec_ad --subdataset bottle --model_size small --weights (Join-Path $projectRoot 'build/work/external/efficientad/models/teacher_small.pth') --mvtec_ad_path (Join-Path $projectRoot 'build/work/data/mvtec_ad') --output_dir $runRoot --train_steps 1000 *> (Join-Path $runRoot 'run.log')
Pop-Location
python -B -m sim.evaluate_efficientad_maps --class-root build/work/data/mvtec_ad/bottle --maps-root build/work/efficientad-real/bottle-repro/anomaly_maps/mvtec_ad/bottle/test --output-dir build/work/efficientad-real/bottle-repro/evaluation
```

2026-10-12 本机 100 步运行用时约 93 秒，候选程序与独立脚本均得图像级 AUC `75.9524%`；1,000 步用时约 284 秒，两者均得 `95.7143%`。两次均保存 83 张融合异常图 TIFF（每张 `900×900`、float32、值有限），以及三网络最终文件；输出位于 `build/work/efficientad-real/bottle-100step/` 与 `bottle-1000step/`。独立脚本在各运行目录的 `evaluation/` 保存 `per_image.csv` 和 `summary.json`，逐图读取后核对数量、尺寸与有限数值。AUC 衡量测试图排序，**不是**以某个阈值做出的判定正确率。阈值和分图导出见下节；仍无像素定位指标或板上运行结果。`bottle` 瓶身异常不能代表拟采购尼龙扎带座的缺角或堵孔效果。

1,000 步最终模型文件的本机 SHA-256：`teacher_final.pth` 为 `976FDA79AEF1DB98A108B4922DFA6FB904CAE86F9E81700ED75C470D2A72FDAB`；`student_final.pth` 为 `412DF3C0E32D0247D884647EBBBBB46AF42C05D39A99CB49A91761E79460B1C2`；`autoencoder_final.pth` 为 `5DEB5DB376B9DE6F84F895C0D6E8CAC873C4DD4A2162AB742EC9C6F415A486F8`。这是本机训练产物的身份记录，文件仍在 Git 忽略目录，不随仓库上传。

## 分图导出与验证集阈值（电脑端）

`sim.export_efficientad_components` 只读取上述 1,000 步模型、`bottle` 数据和候选脚本保存的融合图。它按种子 42 重建 188/21 的正常训练/验证划分，重算教师特征均值、标准差及两类异常图在验证集上的分位数；分别保存局部教师–学生图、自动编码器相关图和融合图。重算后的 83 张测试融合图与候选脚本上一轮 TIFF **逐像素完全相同**（最大绝对差 `0.0`）；脚本以后若差异超过 `1e-4` 会报错，不输出判定汇总。教师与自动编码器原始特征均为 `[1,384,56,56]`，学生为 `[1,768,56,56]`；输入为 `[1,3,256,256]`。`normalization.npz` 保存教师均值/标准差和四个分位数；三类异常图插值回每张原图的 `900×900` 尺寸。

在仓库根目录用 PowerShell 执行；输出目录请换成一个尚不存在的名称：

```powershell
$env:TEMP = Join-Path (Get-Location).Path 'build/work/tmp'
$env:TMP = $env:TEMP
& build/work/efficientad-env/Scripts/python.exe -B -m sim.export_efficientad_components --external-repo build/work/external/efficientad --class-root build/work/data/mvtec_ad/bottle --trainings-dir build/work/efficientad-real/bottle-1000step/trainings/mvtec_ad/bottle --reference-maps-root build/work/efficientad-real/bottle-1000step/anomaly_maps/mvtec_ad/bottle/test --output-dir build/work/efficientad-real/bottle-1000step/components-repro
```

本机实际结果在 `build/work/efficientad-real/bottle-1000step/components/`。`maps/validation/` 有 21 张正常验证图的三类异常图，`maps/test/` 有 83 张测试图的三类异常图；`validation_scores.csv`、`test_predictions.csv` 和 `summary.json` 给出逐图分数及判定。判定规则只取 **21 张正常验证图的图像最大分数中的最高值** `0.19837449491024017`，测试图分数严格大于它才判异常；测试图片未参与阈值选择。测试集结果：异常检出 59/63、漏检 4/63；正常判对 16/20、误报 4/20，图像级 AUC 仍为 `95.7143%`。漏检均属 `contamination`，文件为 `002.png`、`003.png`、`004.png`、`019.png`；误报的正常图为 `005.png`、`006.png`、`013.png`、`014.png`。该阈值在 21 张验证图上保证零误报，但样本少，**不能保证**新拍图片或实物的误报率。已对同一权重与测试图片再做一次推理并逐像素对照；像素排序评估见下节。尚未从空环境重新训练或做板上实测，异常图本身也不等于已给出可靠的缺陷框。

## 像素位置排序与误判复核（电脑端）

读取 `bottle/ground_truth/` 中 63 张异常图的像素标注。每张图先按标注把像素分成“缺陷/背景”，再计算三类异常图各自的像素 ROC AUC，最后**对 63 张异常图等权平均**。这与把所有像素混在一起算 AUC、阈值二值分割的 IoU 或论文完整基准都不同；正常测试图没有缺陷掩码，不纳入此平均。评估脚本逐一核对图像、掩码和三类 TIFF 的数量、尺寸及有限数值；对 `contamination/002.png` 的融合图额外与 scikit-learn `roc_auc_score` 核对，数值完全相同。

| 异常图 | 63 图平均像素 AUC | `broken_large` 20 图 | `broken_small` 22 图 | `contamination` 21 图 |
| --- | ---: | ---: | ---: | ---: |
| 融合图 | 91.82% | 92.53% | 96.34% | 86.40% |
| 教师–学生图 | 80.59% | 73.88% | 91.57% | 75.48% |
| 自动编码器相关图 | 93.91% | 95.06% | 97.08% | 89.50% |

运行命令（仓库根目录，输出目录必须换成不存在的名称）：

```powershell
python -B -m sim.evaluate_efficientad_localization --class-root build/work/data/mvtec_ad/bottle --maps-root build/work/efficientad-real/bottle-1000step/components/maps/test --predictions-csv build/work/efficientad-real/bottle-1000step/components/test_predictions.csv --output-dir build/work/efficientad-real/bottle-1000step/localization-repro
```

本机实际输出在 Git 忽略的 `build/work/efficientad-real/bottle-1000step/localization/`：`per_defect_image.csv` 为逐图数据，`summary.json` 为上述统计，`failure_previews/` 有 8 张输入/标注/融合热图的对照 PNG。热图为**每张单独拉伸**，只能看位置，颜色亮度不能跨图片比较。人工查看这 8 张预览后，4 张漏检均为 `contamination`：`002.png` 的缺陷区域在融合图中排序较高（该图像素 AUC 97.58%），但整图最高分 `0.1958` 低于图像阈值 `0.1984`；另外三张的融合图像素 AUC 约 66.7%–69.8%。4 张误报正常图的最高分只略高于阈值；预览在瓶口纹理、反光或中心附近可见较亮区域，但仅凭预览不能断定误报的具体成因。当前测试集已经用于评估，不能再依据这些误判调阈值后把同一测试集成绩当作独立结果。

这些数值只能支持“在公开瓶类异常图上有一定位置排序能力”的结论；尚未设定像素二值阈值、计算 IoU/缺陷框，也未做扎带座或 Zynq 板上验证。后续若需要输出缺陷框，应先用正常验证图或另设验证样本确定像素阈值，再在保留的独立测试集上评估。

## 人工图流程检查的复现方法

下列步骤仅检查外部脚本的三网络代码路径与输出文件。`sim.make_efficientad_smoke_data` 把本仓库生成人工图排成 MVTec 风格目录，使用 `bottle` 作为脚本类别名；图片**不是** MVTec AD bottle 数据。10 张正常训练图是同一图片的重复副本，训练仅 2 步，不能用于准确率、泛化能力或论文性能结论。

在仓库根目录用 PowerShell 执行，`--output-dir` 每次换成一个新的空目录；外部仓库须位于上述提交，隔离环境须安装上述依赖：

```powershell
$projectRoot = (Get-Location).Path
python -B -m sim.make_efficientad_smoke_data --output-dir build/work/efficientad-smoke/check
$env:TEMP = Join-Path $projectRoot 'build/work/tmp'
$env:TMP = $env:TEMP
Push-Location (Join-Path $projectRoot 'build/work/external/efficientad')
& (Join-Path $projectRoot 'build/work/efficientad-env/Scripts/python.exe') efficientad.py --dataset mvtec_ad --subdataset bottle --model_size small --weights (Join-Path $projectRoot 'build/work/external/efficientad/models/teacher_small.pth') --mvtec_ad_path (Join-Path $projectRoot 'build/work/efficientad-smoke/check/dataset') --output_dir (Join-Path $projectRoot 'build/work/efficientad-smoke/check/output') --train_steps 2
Pop-Location
```

2026-10-12 本机流程检查完成：生成 3 张 `128×128`、float32 且数值有限的融合异常图 TIFF，以及教师、学生、自动编码器各一份最终检查点。候选脚本打印的人工图 AUC 为 50.0000；这个数值没有检测性能意义。脚本目前只把融合图保存为 TIFF，局部图、自动编码器相关图和逐图判定仍须在真实数据基线阶段单独导出。正式训练默认 70,000 步；未指定 ImageNet 路径时关闭辅助惩罚项，须在报告中说明配置差异。
