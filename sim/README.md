# 仿真与验证

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

`evaluate_efficientad_localization.py` 将每张异常测试图与 MVTec AD 的 `ground_truth/*/*_mask.png` 对齐，分别计算融合图、教师–学生图、自动编码器图的像素 ROC AUC，并对 63 张异常图取逐图平均。它保存逐图 CSV、按类别汇总 JSON，以及 8 张图像级误判的输入/标注/融合热图对照 PNG；热图按每张图单独拉伸，仅供肉眼复核。AUC 的并列分数处理和坏掩码拒绝由 `test_evaluate_efficientad_maps.py` 检查。运行结果和指标边界见 [迁移计划](../report/efficientad_plan.md)。
