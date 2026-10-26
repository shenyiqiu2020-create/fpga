# 2026-10-27 原图重定位与双路外缘分类候选

## 任务和上一版记录

本页记录 [327 张严格可测照片候选](shape_assisted_candidate_20261027.md)之后的电脑端改进，旧报告保留当时的训练、拒绝与分组交叉验证数字，不应与本轮混算。完整 EfficientAD 的教师–学生、自动编码器、异常图融合仍是作品主线；B/C 已收到的 3000 步权重和黄金张量、默认单张推理入口均未由本候选替换。`do3/D03` 两张是内部肋条断损，依首版“可见外缘缺块/缺角/边中部缺口”的既定范围排除，留档而不改标正常。

用户希望旧版 17 张 `unavailable` 也得到正常或缺损标签。复查发现 **17/17 原始 JPEG 中工件完整**；问题在定位和分割。有些旧裁剪器虽然成功返回 `256×256` 图，却把工件静默截掉一部分，例如 `N49_0295` 的原图完整而旧裁剪图缺半。因此“裁剪成功”和“工件完整可测”必须分开检查。也不能把旧报告的 327 张可测直接解释成原裁剪框对所有照片都正确。

## 方法与质量标记

主路继续使用照片边缘背景与中心工件种子构造的 Lab 相对色差 GrabCut、严格轮廓质量门、19 项形状特征和随机森林。已有裁剪图通过严格质量门时沿用原图像素；失败时先用旧框的 1.30 倍原 JPEG 重裁。两次都失败后，才用 `src/tie_mount_relocate.py` 从经 EXIF 转正、哈希核对的**完整原 JPEG**重新定位：按照片边缘色中值在四周各补相当于原图宽度 5% 的背景画布，使用偏色光下的白色工件掩膜定位并生成新裁剪图，仍须通过同一严格轮廓质量门。来源坐标和所用裁剪图可审计；虚拟画布和重定位本身不保证新照片正确。

若严格路径仍失败，第二条路径允许轮廓接触裁剪边界，并由**单独训练的宽松边界随机森林**给二元标签。它使用同样的 19 项特征，但分割约束较弱，输出 `route=relaxed_border_contact`、`low_quality=true`、`review_recommended=true`；不能与通过严格门的结果视为同等可信。重定位成功也标记需复核。概率处于 `[0.4,0.6]` 同样提示复核；当前级联入口仍按固定阈值 `0.5` 输出 `good/defect`，记录未校准的分数。对将来真正无法裁剪或分割的照片，接口仍可能返回 `unavailable`，不能承诺任意输入必得可靠二元标签。

## 当前照片、分组验证和历史诊断

现存 347 张照片中一张 `正常14` 组内字节重复照在数据准备时跳过，得 346 张唯一照；排除 `D03` 两张后 **344 张属首版外缘任务**。其中开发侧 296 张，旧 48 张曾被查看并影响本次方法设计。各折按 `leakage_cluster` 分组：同一件实物的不同灯光照及曾有误复制关系的目录保持在同侧；训练确实使用了当前不同灯光下的正常件和缺损件照片。

开发侧 296 张（正常 169、缺损 127）现在全部得到二元标签：严格路径 295 张，其中 13 张经原图重定位；余下 `D32_0108` 一张走宽松边界模型，标为低质量。按组五折交叉验证所得逐图结果如下，全部是**开发阶段已见条件**的估计：

| 划分种子 | TN | FP | FN | TP | 判对/全部 | 平衡准确率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 | 167 | 2 | 1 | 126 | 293/296 | 99.01% |
| 42 | 167 | 2 | 2 | 125 | 292/296 | 98.62% |
| 2026 | 167 | 2 | 2 | 125 | 292/296 | 98.62% |

三个种子按件概率均值分别为正常 46/46、缺损 33/33；79 件并不等于 296 件独立实物。原先不可测的 17 张中，**16 张经完整原图重定位后通过严格门，三次分组划分逐张均判对**；`D32_0108` 由宽松边界模型判缺损，三次也判对，但须保留质量风险标记。它的单图分数和“一张判对”不是部署准确率证明。开发模型文件在 Git 忽略的 `build/work/results/tie_mount_shape_cascade_dev_v2/`。

旧 48 张的冻结开发模型事后诊断为正常 `TN=16/16`、缺损 `TP=32/32`，48/48 得到二元标签，其中 3 张经原图重定位；4 张触发人工复核建议，包括一张落在谨慎分数区间的照片。**旧 48 张已参与排错与方法选择，这个 48/48 绝非独立测试或“100%识别率”。** 诊断记录为 `build/work/results/tie_mount_shape_cascade_old48_diagnostic_v2/`。

随后把旧 48 张并入最终实验候选。当前 344 张中，原有 327 张严格可测、又有 16 张经完整原图重定位通过严格门，合计**严格路径 343 张**；最后的 `D32_0108` 走低质量二级路径。因而 344/344 都有二元输出、0 张 `unavailable`，但 **344/344 可输出不等于 344/344 判对或未来可靠**。完整模型用当前全部 344 张任务内照片训练；已无独立旧照片测试集。模型和回顾性逐图记录在 Git 忽略的 `build/work/results/tie_mount_shape_cascade_full_current_v2/`。

为显示划分敏感性，以下是方法选定之后，对全部当前照片做的**回顾性**按组五折交叉验证；不属于独立验收：

| 划分种子 | TN | FP | FN | TP | 判对/全部 | 平衡准确率 | 需复核提示 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 | 183 | 2 | 2 | 157 | 340/344 | 98.83% | 22 |
| 42 | 182 | 3 | 1 | 158 | 340/344 | 98.87% | 23 |
| 2026 | 183 | 2 | 2 | 157 | 340/344 | 98.83% | 21 |

三次按件概率均值均为正常 50/50、缺损 41/41，但这是同批 91 件的回顾性汇总；逐图每次仍错 4/344，且二级路径只有一张已知缺损样本可检验。不能只报按件 91/91，不能以旧照片反复调方法后宣称跨背景、跨灯光或新破损形态的识别率。缺口位置模块 `src/tie_mount_shape.py` 仍仅给候选点，没有逐图位置真值或定位准确率。

最终候选的 `manifest.json` SHA-256 为 `b9df698a4f3051abd156970aaf27df43e9a20340629547b11bb4f52ca0115614`；它记录原 JPEG 与已备裁剪 PNG 身份的聚合 `training_input_set_sha256=5644f5c7624476e1fea968fa9894dc22810bba75b5097935e443a4896d1a9ad9`、配置和两份模型校验值。`strict_model.json` SHA-256 为 `9d87cf201a87d2ff4b3e18b8f92ab95c6cf36b7d908ea90f8b68408633da693f`，`relaxed_model.json` 为 `812f728cf4a9cf3189136ab9cc86b8e7949313e39f981a5b8cc500f8544349d0`。哈希只证明同一实验工件，不证明模型可靠。

## 本机复现与单张入口

在仓库根目录运行，三个输出目录均须事先不存在；输入源清单、原 JPEG 和裁剪图留在本机，未随 Git 提交：

```powershell
python -m pip install -r requirements-shape.txt
python -B -m sim.train_tie_mount_shape_cascade train-development --source-map build/work/data/tie_mount_expanded_20261026_prepared_v1/source_map.csv --prepared-root build/work/data/tie_mount_expanded_20261026_prepared_v1 --output-dir build/work/results/tie_mount_shape_cascade_dev_replay
python -B -m sim.train_tie_mount_shape_cascade diagnostic --source-map build/work/data/tie_mount_expanded_20261026_holdout_v1/source_map.csv --prepared-root build/work/data/tie_mount_expanded_20261026_holdout_v1 --strict-model build/work/results/tie_mount_shape_cascade_dev_replay/strict_model.json --relaxed-model build/work/results/tie_mount_shape_cascade_dev_replay/relaxed_model.json --manifest build/work/results/tie_mount_shape_cascade_dev_replay/manifest.json --output-dir build/work/results/tie_mount_shape_cascade_old48_replay
python -B -m sim.train_tie_mount_shape_cascade refit-current --development-map build/work/data/tie_mount_expanded_20261026_prepared_v1/source_map.csv --development-root build/work/data/tie_mount_expanded_20261026_prepared_v1 --seen-holdout-map build/work/data/tie_mount_expanded_20261026_holdout_v1/source_map.csv --seen-holdout-root build/work/data/tie_mount_expanded_20261026_holdout_v1 --diagnostic-report build/work/results/tie_mount_shape_cascade_old48_replay/report.json --output-dir build/work/results/tie_mount_shape_cascade_full_replay
```

单张试用须显式指定这套**实验级联模型**，和现行 EfficientAD 的默认 `result.json` 不属于同一接口。`--used-crop-output` 选择尚不存在的 PNG 路径；结果包含 `verdict`、`route`、`low_quality`、`review_recommended`、质量细节和实际使用裁剪图哈希：

```powershell
python -B -m sim.train_tie_mount_shape_cascade infer-photo --photo "D:\工件照片\待测.jpg" --strict-model build/work/results/tie_mount_shape_cascade_full_current_v2/strict_model.json --relaxed-model build/work/results/tie_mount_shape_cascade_full_current_v2/relaxed_model.json --manifest build/work/results/tie_mount_shape_cascade_full_current_v2/manifest.json --used-crop-output build/work/results/shape_cascade_one_crop.png
```

## 线下验收边界

下一轮先冻结模型、阈值、低质量提示规则与数据清单，再用**新的实物**拍正常照，在同件制造此前未见的外缘破坏形态；同件破坏前后全部只放测试侧。按新纯色背景、新灯光颜色分别记录逐图、逐件混淆矩阵，另列 `unavailable`、人工复核提示数和覆盖率。若为了改善失误而把这些照片再加入训练，须另收下一批真正独立的照片评估。当前级联尚未交付 B/C；他们的板卡、PL 加速及课程 RISC-V 工作不变。
