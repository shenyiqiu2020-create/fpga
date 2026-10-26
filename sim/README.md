# 仿真与验证

**当前首版：** 对单张正面工件照片判断“正常 / 有可见外缘缺损”；定位另作候选。旧 300 步冻结模型的[逐图分数表](../data/tie_mount_binary_baseline_20261025.csv)可用 `python -B -m sim.evaluate_tie_mount_binary data/tie_mount_binary_baseline_20261025.csv` 复核。2026-10-26 另有按实物分组的[开发分数](../data/tie_mount_20261026_development_scores.csv)和[新留出分数](../data/tie_mount_20261026_holdout_scores.csv)，必须分别列正常误报、缺损漏报及裁剪拒绝，不能在测试图上重新选择阈值。详情见[组员交接](../report/team_outline.md)。

**扩批实验结果：** 用户新增照片并删除五张跨目录误复制照后，[扩批冻结脚本](freeze_tie_mount_expanded.py)登记 347 张原图，组内重复只取一张。`freeze` 只哈希与解码，`prepare` 才分别生成开发集和独立留出集及 `source_map.csv`。完整 EfficientAD 9000 步实验包 [tie_mount_expanded_20261026_9000step.json](model_bundles/tie_mount_expanded_20261026_9000step.json)仅供 A 复盘；[扩批留出分数](../data/tie_mount_expanded_20261026_holdout_scores.csv)显示损坏 32/32 报出但正常 0/16 判对，准确率 66.7%，因此**单张默认入口和 B/C 已发模型仍使用下述 3000 步包**。`summarize_tie_mount_round.py` 以源图与裁剪图哈希核对冻结预测，分别输出逐图与逐件混淆矩阵；留出结果不能用来追调阈值后再称独立准确率。复现步骤和限制见[扩批协议](../report/expanded_batch_protocol_20261026.md)、[进度记录](../report/progress.md)。

**2026-10-27 外缘辅助候选：** 针对上述正常误报，A 在保留完整 EfficientAD 的同时增加了背景相对 GrabCut 工件分割、19 项轮廓特征和随机森林分类，另有独立的外缘凹陷位置候选模块。现有多灯光照片按实物分组进入训练；`do3/D03` 内部肋条断损不属于首版外缘类别，排除训练和指标。开发侧 296 张目标图中，282 张可判、14 张分割 `unavailable`；三次分组交叉验证在可判图上均正常 158/160、外缘缺损 120/122 判对。旧 48 张照片已参与方法排查；一次事后诊断中 45/48 张可判、3 张不可判，不能称独立测试或“100%识别率”。最终实验候选在所有 346 张唯一照中排除 `D03` 两张后，用 327 张可靠分割照完成重训，17 张留档 `unavailable`，**没有剩余独立测试集**。候选模型尚未替换本页默认 EfficientAD，更未更新 B/C Release。参数、分母、三种回顾性分组划分的波动和新实物验收条件见[辅助候选记录](../report/shape_assisted_candidate_20261027.md)。

只想在本机试运行新原图的辅助候选时，先安装 `requirements-shape.txt`，然后显式指定**实验模型**；输出 `good/defect/uncertain/unavailable`，与下方 EfficientAD 的默认 `result.json` 不是同一接口：

```powershell
python -m pip install -r requirements-shape.txt
python -B -m sim.train_tie_mount_shape_rf infer-photo --photo "D:\工件照片\待测.jpg" --used-crop-output build/work/results/shape_one_used_crop.png --model-json build/work/results/tie_mount_shape_rf_full_current_v1/shape_rf_model.json --manifest build/work/results/tie_mount_shape_rf_full_current_v1/manifest.json
```

模型 JSON、原图和所有训练资料在 Git 忽略的 `build/work/` 或 `D:\工件照片`，不随仓库交付；其他电脑需按[完整复现命令](../report/shape_assisted_candidate_20261027.md)自行重训。不能把实验候选概率视为已校准的真实破损概率，也不能把辅助分类结果冒充完整 EfficientAD 或板端识别成绩。

截至 2026-10-26，本轮新模型入口和交接说明在 `codex/new-batch-efficientad` 分支；`main` 尚未合入。B/C 应先切到该分支，再按本页运行。

## 单张原始照片推理

在仓库根目录用隔离的 EfficientAD 环境运行：

```powershell
build/work/efficientad-env/Scripts/python.exe -B -m sim.infer_tie_mount_photo "D:\工件照片\待测.jpg" --output-dir build/work/results/tie_mount_one_photo
```

此命令默认使用 `batch_20261026` 冻结模型。需要在模型报缺损时给出可视化候选位置，可显式写出模型配置并加 `--mark-edge-candidate`：

```powershell
build/work/efficientad-env/Scripts/python.exe -B -m sim.infer_tie_mount_photo "D:\工件照片\待测.jpg" --output-dir build/work/results/tie_mount_one_photo_batch_20261026 --model-profile batch_20261026 --mark-edge-candidate
```

输出目录必须尚不存在。脚本先核对所选模型包，再用 `src/tie_mount_crop.py` 从原始 JPEG/PNG 定位白色方形工件并生成 `256×256` 裁剪图，加载冻结的教师、学生、自动编码器权重及**同版**正常验证件确定的归一化与阈值。`result.json` 中的 `predicted_defect`/`verdict` 是整件二分类结论，`score` 与 `threshold` 可供软件接口读取；`inference/maps/` 保存三类异常图。`--mark-edge-candidate` 只在报缺损时尝试输出 `edge_location/preview.png`、原图 `source_preview.jpg` 和 `defect_location_candidate` 坐标；失败会写 `status=unavailable`，不会改变模型判定。这个点是融合图的固定几何后处理建议，并非已验证的缺口位置。原图和输出不会自动提交 Git。

默认模型包清单是 `sim/model_bundles/tie_mount_20261026_3000step_dedupval.json`（ID `tie_mount_20261026_3000step_dedupval`，阈值 `0.11209306865930557`）。推理前逐文件校验三个权重、`normalization.npz` 和 `summary.json` 的 SHA-256，避免不同轮次的权重、归一化或阈值混用；`result.json` 记录模型包 ID 和清单哈希。手工更换任一文件时，必须同时用 `--bundle-manifest` 指向匹配清单，校验失败会拒绝推理。旧 `golden_v3` 配置仅供 A 本机回顾性对照，其 GitHub Release 与标签已删除；旧数值张量不能用来验证新模型。由同轮文件生成新清单可用 `python -B -m sim.model_bundle --bundle-id <id> --trainings-dir <dir> --normalization <file> --summary <file> --output <new.json>`。

新模型的五文件 ZIP 可从[私有实验版 Release](https://github.com/shenyiqiu2020-create/fpga/releases/tag/tie-mount-batch-20261026-3000step)取得；A 本机副本为 `build/work/handoff/tie_mount_20261026_3000step_model.zip`，SHA-256 为 `c43674f11a81d1bb3c06994b18847e8647360ea632e42414cb08d0e67c956245`。GitHub 回报 30,107,886 字节及相同 SHA-256；包内 `bundle_manifest.json` 与仓库独立清单一致，五文件哈希逐项通过。B/C 收到后应放在自己的 Git 忽略目录并核对 ZIP 与五文件哈希。若从 ZIP 解压为 `build/work/handoff/received_20261026/tie_mount_20261026_model/`，应显式传 `--model-profile batch_20261026 --trainings-dir build/work/handoff/received_20261026/tie_mount_20261026_model --normalization build/work/handoff/received_20261026/tie_mount_20261026_model/normalization.npz --summary build/work/handoff/received_20261026/tie_mount_20261026_model/summary.json --bundle-manifest build/work/handoff/received_20261026/tie_mount_20261026_model/bundle_manifest.json`。仍须另有固定提交 `fcab5146f84ae17597044ad5ddf1656ccf805401` 的候选 EfficientAD 源码；ZIP 不含原始照片或新版黄金张量。

新模型对应的两份 float32 黄金张量也在[同一私有实验版 Release](https://github.com/shenyiqiu2020-create/fpga/releases/tag/tie-mount-batch-20261026-3000step)；A 本机副本为 `build/work/handoff/tie_mount_20261026_3000step_golden.zip`，SHA-256 为 `f33321cc38ce1ec65bf82f7683b4dfa7b80a7d01eedd9177108abc4b446d3eb6`。GitHub 回报 36,505,069 字节及相同 SHA-256。包内 `D19_01` 是缺损件，冻结分数 `0.3200802505016327`、判缺损；`N17_03` 是正常件，分数 `0.06585786491632462`、判正常。两者阈值均为 `0.11209306865930557`，模型包 ID 均为 `tie_mount_20261026_3000step_dedupval`；本机 ZIP CRC 与两次 `sim.verify_tie_mount_golden` 复核通过。接收后分别对解压的 `D19_01/`、`N17_03/` 运行 `python -B -m sim.verify_tie_mount_golden <目录>`，再与板上输出对比。这是新模型的数值参考，不是新盲测或定位正确率证明；旧 `golden_v3` 三份样本只适用于旧模型。

自动裁剪当前在已收集的棕、绿背景及偏色光照下对 346 张有效照片全部成功；偏光回退只在原规则拒绝后尝试，并保留真实截边拒绝。先前两张拍摄截边照已由用户删除，下述 3000 步模型的旧留出分数仍保留当时 2 张拒绝的历史记录。拍摄方向无需预先转正，但不能据此宣称任意视角、光照和背景均可靠。3000 步模型在此前成功裁剪的留出正常照中仍误报 1/13；扩批实验模型又在新留出正常照中误报 16/16，单张输出不能作为可靠的工业判废依据。

单独复核已有 `256×256` 裁剪图与对应融合 TIFF 的位置候选可运行 `python -B -m sim.localize_tie_mount_edge <crop.png> <combined.tiff> --output-dir <新目录>`。输出 `result.json`、`preview.png` 和 `expected_edge_band.png`，记录原始整图峰值、预期外轮廓带内候选峰值及输入哈希。固定外轮廓带可覆盖缺失角和边中部凹口的预期区域，但不等于缺口真值；新批次尚无人工缺口框定位评估。

## 历史 EfficientAD 黄金样本（已停止交接）

`export_tie_mount_golden.py` 使用同一个冻结的 300 步模型包，把已有 `256×256` 裁剪图导出为输入张量、归一化教师特征、学生两半特征、自动编码器特征、教师–学生与自动编码器异常图、融合图、最高分及二分类结论。每份 `metadata.json` 记录模型包、源图及数组 SHA-256、实物组号和人工标签。导出时会与原推理函数逐项比对。可在仓库根目录复现一份：

```powershell
build/work/efficientad-env/Scripts/python.exe -B -m sim.export_tie_mount_golden build/work/data/tie_mount_grouped_v1/prepared/tie_mount/validation/good/0007_N02.png --object-group N02 --reference-label normal --output-dir build/work/results/tie_mount_golden_v3/N02_01
build/work/efficientad-env/Scripts/python.exe -B -m sim.verify_tie_mount_golden build/work/results/tie_mount_golden_v3/N02_01
```

本机还导出了 `N05_01`（正常件，旧模型误报缺陷）和 `D07_01`（缺损件，旧模型报缺陷），分别来自 `build/work/data/tie_mount_grouped_v1/prepared/tie_mount/test/good/0013_N05.png` 与 `build/work/data/tie_mount_holdout_20261025/crops/D07_01.png`；它们只用于 A 的历史回归。`verify_tie_mount_golden.py` 只依赖 NumPy，会核验数组身份并从特征重算两分支异常图、融合图、分数与判定。旧三份数组 ZIP 的 GitHub Release 与标签已按用户要求删除；B/C 当前只接收本页上方新模型的两份同版黄金样本。硬件方可先选定某个算子和张量边界，再用新样本比较其输出；课程版实际 RISC-V 内核和竞赛版 PS/PL 仍需分别实现与验证。

对应比赛规则第 3.3.5.1 和 3.3.5.4 节，保存仿真或验证脚本、测试配置及结果。

## 计划验证内容

- 卷积、特征差分、通道累加的算子级输入输出比对。
- 浮点参考、量化软件实现与硬件实现的误差比较。
- 教师与学生特征尺度对齐、异常评分图和判定阈值验证。
- 缺角、缺孔、局部破损及正常工件的系统验证。
- 几何约束与区域统计的正确性验证。

每项结果应注明命令、工具版本、输入数据与权重版本、黄金参考、误差容限和通过条件。测试输入与参考结果归入 `data/`，板级实测归入 `board/`。

当前新增 `test_score_map.py`，检查异常位置与通道均值、INT8 极值相减后的平方不溢出，以及错误形状的输入被拒绝。运行 `python -m unittest discover -s sim -v`。这属于软件数值检查，尚无 RTL/HLS 仿真、模型准确率或板级检测结果。

`make_demo_images.py` 用 NumPy/Pillow 生成人工的正常、缺角、缺孔图片。`test_image_baseline.py` 检查端到端判定、区域坐标、保存文件、无效输入和小面积噪点。这些图片由项目代码生成，不来自真实工件或第三方数据集。

`make_efficientad_smoke_data.py` 将上述人工图片复制成第一候选 EfficientAD 脚本可读取的 `bottle/train/good` 与 `bottle/test/{good,broken}` 目录。`bottle` 仅是脚本目录名，图片不是 MVTec AD 的 bottle 类；训练图是重复副本。它只用于检查外部脚本能否运行并保存输出，不能计算有意义的检测准确率。复现命令与环境版本见 [迁移计划](../report/efficientad_plan.md)。

`evaluate_efficientad_maps.py` 读取候选实现保存的融合异常图 TIFF，与 MVTec AD `test/` 图片逐张核对，检查尺寸及有限数值，保存逐图最大分数和图像级 AUC。它不标定判定阈值，也不计算像素级定位指标；真实 `bottle` 类的命令和结果见 [迁移计划](../report/efficientad_plan.md)。`test_evaluate_efficientad_maps.py` 检查分数并列时的 AUC 计算及缺图报错。

`export_efficientad_components.py` 在隔离 Python 3.10 环境中读取候选实现与本机训练文件，重算教师特征标准化和验证图分位数，导出正常验证图及测试图的两类分图和融合图。脚本要求重算融合图与上次保存的图逐张误差不超过 `1e-4`，再用正常验证图最高图像分数设阈值，保存逐图判定与误检漏检统计；它不计算像素定位指标。阈值的逻辑及参考图误差检查由 `test_evaluate_efficientad_maps.py` 覆盖。

`prepare_tie_mount_dataset.py` 读取 `file,object_group,split,label` 清单，禁止同一实物跨集合，调用 `src/tie_mount_crop.py` 裁剪并生成候选 EfficientAD 可读取的 `tie_mount/{train,validation,test}` 目录。`object_group` 只是拍摄记录，不要求在工件上写字。可选 `--train-quarter-turns` 仅对训练正常图增加 90°/180°/270° 图片，并在输出清单标出旋转角；不会增加独立实物数，也不会增强验证/测试图。该选项在 2026-10-25 的小样本对照中使缺损漏判增多，**不应默认作为改进方案**。输入原图和生成目录放在 Git 忽略的 `build/work/`。`export_efficientad_components.py` 的 `--validation-root` 可读取独立的 `validation/good`，避免默认逐张随机切分。完整步骤见[采集方案](../data/capture_plan.md)和[本轮记录](../report/progress.md)。

`analyze_tie_mount_map_peaks.py` 将两版 EfficientAD 的融合图最高分点与白色工件候选掩膜对照，输出最高点坐标、像素颜色、距掩膜距离及掩膜内外最大分，供调查边缘阴影和背景误报。参数是 `--class-root`、`--maps-root`、`--output`，分别指向生成数据集的 `tie_mount`、导出结果的 `components/maps` 和 Git 忽略目录内的 CSV 路径。白色掩膜不是缺陷真值；缺角本来可能在掩膜外，因此“最高点在掩膜外”不能单独认定误判。当前实物诊断见[进度记录](../report/progress.md)。

`evaluate_tie_mount_defect_rois.py` 用[可见缺口粗框](../data/tie_mount_visible_defect_rois.csv)逐图检查融合图及两类分图的整图最高点与缺口框内最大分；`--overlay-dir` 可生成黄框/红点复核图。输入分别由 `--class-root`、`--maps-root`、`--annotations` 指定，结果 CSV 由 `--output` 指定。此处框是事后排错区域，不能直接当作像素真值或正式定位准确率；本次只有 2/9 张缺损照的未增强版融合图最高点落在框内，详见[进度记录](../report/progress.md)。

`infer_tie_mount_holdout.py` 用已有教师、学生、自动编码器权重及已保存的归一化和正常验证阈值，对新的 `256×256` 裁剪图做**冻结推理**；不从新图重算阈值。输出逐图判定 CSV、三类 TIFF 异常图和模型/校准哈希清单。`--external-repo` 指向 Git 忽略的候选 EfficientAD 源码，`--images-dir` 指向平铺 PNG 目录，`--trainings-dir` 指向含三个 `*_final.pth` 的目录，`--normalization`、`--summary` 指向已有校准文件；更换模型包时也须指定匹配的 `--bundle-manifest`；`--output-dir` 必须是新目录。留出批次的完整命令和结果见[进度记录](../report/progress.md)。在旧 9 张测试图上回放的 27 张分图与原导出图最大绝对差为 0.0。对新批次进行区域排错时，`evaluate_tie_mount_defect_rois.py` 加 `--flat`，并令 `--class-root build/work/data/tie_mount_holdout_20261025/crops --maps-root build/work/results/tie_mount_holdout_20261025_baseline/maps --annotations data/tie_mount_holdout_20261025_rois.csv --output build/work/results/tie_mount_holdout_20261025_baseline/roi_audit.csv --overlay-dir build/work/results/tie_mount_holdout_20261025_baseline/roi_overlays`。区域框为事后人工复核，不作为模型输入或部署阈值。

`neutralize_tie_mount_background.py` 为灰底受控对照脚本：`--class-root` 指向已裁剪的 `tie_mount`，`--output-root` 指向新的空目录，`--background` 默认 128；全部训练、验证、测试照片均应用同一候选白色掩膜与置灰规则，保留原尺寸和分组。脚本记录源图 SHA-256 与掩膜占比，但不保证任意背景都能分割准确。实际 300 步完整 EfficientAD 对照的正常误报未改善，缺口定位更差，**不可将此选项直接接入默认推理**；见[进度记录](../report/progress.md)。

首版实物范围已改为外缘缺角/缺口。`sim/test_tie_mount_outline.py` 用合成方形检查几种非训练平面角度下的新几何基线，不代表真实工件识别准确率。`D03` 断肋照片退出首版数据清单，也不能改标为 `good`；现有 10 张本机照片的五件实物归属见 Git 忽略的 `build/work/data/tie_mount_20261025/inventory.csv`。

`evaluate_efficientad_localization.py` 将每张异常测试图与 MVTec AD 的 `ground_truth/*/*_mask.png` 对齐，分别计算融合图、教师–学生图、自动编码器图的像素 ROC AUC，并对 63 张异常图取逐图平均。它保存逐图 CSV、按类别汇总 JSON，以及 8 张图像级误判的输入/标注/融合热图对照 PNG；热图按每张图单独拉伸，仅供肉眼复核。AUC 的并列分数处理和坏掩码拒绝由 `test_evaluate_efficientad_maps.py` 检查。运行结果和指标边界见 [迁移计划](../report/efficientad_plan.md)。
