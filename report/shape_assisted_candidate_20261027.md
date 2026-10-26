# 2026-10-27 外缘形状辅助分类候选

## 问题与任务边界

扩批后完整 EfficientAD 9000 步候选在先前冻结的 48 张照片上把 16 张正常照全部报成缺损。融合异常图的最高响应会落在正常工件的高光和结构边缘，因此仅增加 EfficientAD 训练步数或移动整图阈值，没有解决本轮正常误报。教师–学生、自动编码器及融合异常图仍完整保留；下述方法是 A 在电脑端新增的**外缘缺料辅助候选**，不替换已交 B/C 的 3000 步模型或黄金样本。

用户重申 `do3`（内部组号 `D03`）是**内部肋条断损**，早已退出首版“可见外缘缺块、缺角、边中部缺口”任务。其 2 张照片单独留档，不用于本轮形状分类训练或二分类成绩，也不改标正常。细长削角、外缘断条和翘片仍属首版难例；只看外轮廓无法判断内部肋条。

## 数据、光照与方法

原图当前有 92 个编号目录、347 张照片，`正常14` 一张组内完全重复照在数据准备时跳过。原先为完整 EfficientAD 冻结的开发侧有 298 张可用裁剪图；去掉 `D03` 两张后，形状候选的开发侧为 **296 张**（正常 169、外缘缺损 127）。每个目录是一件实物，同件不同灯光照片放在同一组；曾跨目录误复制照片的相关实物还用 `leakage_cluster` 合并约束。按该簇做五折交叉验证时，一件实物的照片只会在该折的训练侧或验证侧，不会同时出现。训练折包含现有正常件和损坏件在不同灯光下拍摄的照片。

分割首先读取已有的 `256×256` 工件裁剪图，以四边 9 像素估计背景色、中央 `36×36` 区域作为工件种子，用相对于背景的 Lab 亮度和色差初始化 GrabCut，而非固定要求工件 RGB 为纯白。三次迭代后，取最大外轮廓并计算 19 项几何特征，包括外接旋转矩形填充率、凸包凹陷、周长和多边形顶点。分类器是带类权重的随机森林（400 棵树、最大深度 5、叶节点至少 3 张）。这条分支使用**带标签缺损照**训练，与只用正常照训练的 EfficientAD 不是同一种训练方式。随机森林输出的“缺损概率”未经概率校准，不能解释为真实破损概率。模型以 JSON 保存，推理时核对 SHA-256；不加载不可信的 pickle。

分割时检查工件是否居中、是否与背景有反差、轮廓是否逼近裁剪边界。边界检查失败时，先从同一张原始 JPEG 按已记录的裁剪框至多扩大到 1.30 倍重新裁剪（受原图尺寸限制）；仍不可靠则返回 `unavailable`，不硬判正常或缺损。返回概率处于 `[0.4,0.6]` 的照片可单列 `uncertain`；所有覆盖率须同时报告，不能把拒绝照片从原始分母中隐去。中央种子、背景边带和扩大裁剪都要求工件完整入镜、背景与白色工件有可分辨反差；它们尚未在用户计划的新纯色背景和新灯光下验证。

## 开发侧探索性结果

使用随机划分种子 11、42、2026，各做一次按 `leakage_cluster` 的五折交叉验证。296 张目标照片中，原裁剪图有 23 张触发严格分割门；从原 JPEG 扩大重裁后救回 9 张，剩余 **14 张 `unavailable`**（正常 9、缺损 5）。因此可判定分母是 **282 张**（正常 160、缺损 122），覆盖率 **282/296 = 95.27%**。三次划分在可判定照片上均为 `TN=158、FP=2、TP=120、FN=2`，逐图平衡准确率 **98.56%**、普通准确率 **278/282 = 98.58%**。14 张未判定不能算进 278 张判对，也不能把 282 张当成 282 件独立实物。同一开发数据上比较、选择了分割和分类方案，这些数字是探索性估计，不是未来现场识别率。

没有严格轮廓门的早期版本虽覆盖 296/296，但只做开发侧诊断：三种分组划分的正常判对约 161–162/169、缺损判对约 124–125/127。它不能与严格门的可判定子集准确率直接相比。另试过在现有裁剪图四周填充虚拟背景来消除拒绝，分组验证反而明显下降，故没有采用。将 EfficientAD 与形状分类器简单地要求两者都报坏，也会增加缺损漏判；没有把该规则设为默认。

## 旧照片诊断与后续独立验收

原先的 48 张留出照片已在前一轮失败排查中被多次查看，并影响这次方法选择。用冻结开发模型和同样的扩大裁剪规则做一次**事后诊断**：45/48 张可判定，其中正常 `TN=14/14`、外缘缺损 `TP=31/31`；另有正常 2 张、缺损 1 张 `unavailable`。可判定照片中另有 1 张概率落入 `[0.4,0.6]`，按谨慎输出应记为 `uncertain`。四件正常与八件缺损均至少有可判视角，其多视角均值在这次诊断中分类正确。由于这些照片已参与方法选择，**45/45 不是独立测试准确率**，也不能声称“识别率 100%”或部署可靠。逐图记录和模型哈希位于 Git 忽略的 `build/work/results/tie_mount_shape_rf_seen_holdout_rebox_v1/`。

记录该诊断后，把旧 48 张中能可靠分割的照片并入最终候选训练。现有 **346 张唯一照片**中排除 `D03` 2 张，任务内为 **344 张**；其中原裁剪 317 张可测、更宽原图回退 10 张，共 **327 张进入最终训练**，另有 **17 张 `unavailable`**（正常 11、缺损 6）留档而未冒充可训练输入。全部当前照片，包括原先的 48 张，现都属于已见数据；完整模型工件与记录在 Git 忽略的 `build/work/results/tie_mount_shape_rf_full_current_v1/`，其中模型 JSON 的 SHA-256 为 `230486c1f78985d03dd74678c5e0a6f2e38aac76ad2b441a8be5c6ad63f49482`。它只是待线下验收的软件候选，未设为默认推理，也未上传 B/C 私有 Release。

为审计全部已有照片，最终重训前还在 327 张可测图上做了按 `leakage_cluster` 的**回顾性**五折交叉验证。种子 11 和 2026 为 `TN=172、FP=2、TP=152、FN=1`，平衡准确率 99.10%；种子 42 为 `TN=171、FP=3、TP=142、FN=11`，平衡准确率 95.54%。按件概率均值，前两次为正常 50/50、缺损 41/41，种子 42 为正常 50/50、缺损 38/41。不同划分下的缺损漏检差异说明不能只引用最好的一折或一个种子。这是**已看照片的回顾性估计**；最终模型已用全部 327 张可测图训练，不存在对该模型仍独立的旧照片测试集。

## 本机复现与单张试用

在仓库根目录用系统 Python 安装额外电脑端依赖；完整 EfficientAD 原隔离环境及 B/C 权重不因此改动：

```powershell
python -m pip install -r requirements-shape.txt
python -B -m sim.train_tie_mount_shape_rf train --source-map build/work/data/tie_mount_expanded_20261026_prepared_v1/source_map.csv --prepared-root build/work/data/tie_mount_expanded_20261026_prepared_v1 --output-dir build/work/results/tie_mount_shape_rf_dev_replay
python -B -m sim.train_tie_mount_shape_rf diagnostic --source-map build/work/data/tie_mount_expanded_20261026_holdout_v1/source_map.csv --prepared-root build/work/data/tie_mount_expanded_20261026_holdout_v1 --model-json build/work/results/tie_mount_shape_rf_dev_replay/shape_rf_model.json --manifest build/work/results/tie_mount_shape_rf_dev_replay/manifest.json --output-dir build/work/results/tie_mount_shape_rf_seen_replay
python -B -m sim.train_tie_mount_shape_rf refit-current --development-map build/work/data/tie_mount_expanded_20261026_prepared_v1/source_map.csv --development-root build/work/data/tie_mount_expanded_20261026_prepared_v1 --seen-holdout-map build/work/data/tie_mount_expanded_20261026_holdout_v1/source_map.csv --seen-holdout-root build/work/data/tie_mount_expanded_20261026_holdout_v1 --exploratory-report build/work/results/tie_mount_shape_rf_seen_replay/report.json --output-dir build/work/results/tie_mount_shape_rf_full_replay
```

输出目录须事先不存在；训练脚本记录源清单及采用裁剪图的 SHA-256、模型 JSON 哈希、分组和逐图预测。最终候选对新原图的电脑端试用：

```powershell
python -B -m sim.train_tie_mount_shape_rf infer-photo --photo "D:\工件照片\待测.jpg" --used-crop-output build/work/results/shape_one_used_crop.png --model-json build/work/results/tie_mount_shape_rf_full_current_v1/shape_rf_model.json --manifest build/work/results/tie_mount_shape_rf_full_current_v1/manifest.json
```

`infer-photo` 返回 `good/defect/uncertain/unavailable` 和实际使用裁剪图的哈希；概率是未校准模型分数。文件未随 Git 提交，B/C 不应把这个实验候选当作已验收的板端权重。离开本机时须重新获得原始照片、冻结清单并按上述步骤重训，不能仅凭文档中的百分比复现。

线下验收应在训练和判定规则冻结后，用从未参与本轮训练的新正常件拍摄，再在同件上造成新的外缘破损形态；同件破坏前后照片都只放在测试侧。新纯色背景和新灯光颜色分别记录。逐照片和逐实物同时报告正常误报、缺损漏报、`unavailable/uncertain` 和总覆盖率。多视角实物判定优先使用预先固定的概率均值，不因某一张照片偶然报坏就自动判整件坏；这仍须新实物实测。

缺口位置另由 [`src/tie_mount_shape.py`](../src/tie_mount_shape.py)给出外缘凹陷**候选点**。它在分割或几何不可靠时返回 `unavailable`，没有逐图精确缺口真值，不能声称位置准确率。B 的板卡与系统、C 的 PL 加速及课程 RISC-V 工作线不因本实验改变；辅助分类器尚未获线下验证，也未更新私有 Release 中的 B/C 模型。
