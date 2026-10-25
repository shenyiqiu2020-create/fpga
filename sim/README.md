# 仿真与验证

**当前首版：** 对单张正面工件照片只验收“正常 / 有可见外缘缺损”。`evaluate_tie_mount_binary.py` 读取冻结阈值的[逐图分数表](../data/tie_mount_binary_baseline_20261025.csv)，分别输出照片级 TP/FN/TN/FP 和“同件任一视角报缺损”的实物级结果。运行 `python -B -m sim.evaluate_tie_mount_binary data/tie_mount_binary_baseline_20261025.csv`。不在测试数据上找新阈值；结果详见[进度记录](../report/progress.md)。下方区域/位置脚本仍可用于 EfficientAD 排错与以后功能扩展，不决定这版二分类验收。

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

`infer_tie_mount_holdout.py` 用已有教师、学生、自动编码器权重及已保存的归一化和正常验证阈值，对新的 `256×256` 裁剪图做**冻结推理**；不从新图重算阈值。输出逐图判定 CSV、三类 TIFF 异常图和模型/校准哈希清单。`--external-repo` 指向 Git 忽略的候选 EfficientAD 源码，`--images-dir` 指向平铺 PNG 目录，`--trainings-dir` 指向含三个 `*_final.pth` 的目录，`--normalization`、`--summary` 指向已有校准文件，`--output-dir` 必须是新目录。留出批次的完整命令和结果见[进度记录](../report/progress.md)。在旧 9 张测试图上回放的 27 张分图与原导出图最大绝对差为 0.0。对新批次进行区域排错时，`evaluate_tie_mount_defect_rois.py` 加 `--flat`，并令 `--class-root build/work/data/tie_mount_holdout_20261025/crops --maps-root build/work/results/tie_mount_holdout_20261025_baseline/maps --annotations data/tie_mount_holdout_20261025_rois.csv --output build/work/results/tie_mount_holdout_20261025_baseline/roi_audit.csv --overlay-dir build/work/results/tie_mount_holdout_20261025_baseline/roi_overlays`。区域框为事后人工复核，不作为模型输入或部署阈值。

`neutralize_tie_mount_background.py` 为灰底受控对照脚本：`--class-root` 指向已裁剪的 `tie_mount`，`--output-root` 指向新的空目录，`--background` 默认 128；全部训练、验证、测试照片均应用同一候选白色掩膜与置灰规则，保留原尺寸和分组。脚本记录源图 SHA-256 与掩膜占比，但不保证任意背景都能分割准确。实际 300 步完整 EfficientAD 对照的正常误报未改善，缺口定位更差，**不可将此选项直接接入默认推理**；见[进度记录](../report/progress.md)。

首版实物范围已改为外缘缺角/缺口。`sim/test_tie_mount_outline.py` 用合成方形检查几种非训练平面角度下的新几何基线，不代表真实工件识别准确率。`D03` 断肋照片退出首版数据清单，也不能改标为 `good`；现有 10 张本机照片的五件实物归属见 Git 忽略的 `build/work/data/tie_mount_20261025/inventory.csv`。

`evaluate_efficientad_localization.py` 将每张异常测试图与 MVTec AD 的 `ground_truth/*/*_mask.png` 对齐，分别计算融合图、教师–学生图、自动编码器图的像素 ROC AUC，并对 63 张异常图取逐图平均。它保存逐图 CSV、按类别汇总 JSON，以及 8 张图像级误判的输入/标注/融合热图对照 PNG；热图按每张图单独拉伸，仅供肉眼复核。AUC 的并列分数处理和坏掩码拒绝由 `test_evaluate_efficientad_maps.py` 检查。运行结果和指标边界见 [迁移计划](../report/efficientad_plan.md)。
