扎带固定座已裁剪模型输入（256×256 PNG）

historical_development_48/ 是早期开发对照 48 张（do6–do15、正常5/16）；
  与历史评分表逐图 SHA-256 匹配，不能改用之后 v2 的同名裁剪目录。
historical_holdout_33_accepted/ 是早期 35 张留出原图中的 33 张成功裁剪输入；
  其中 D19_01–04 对应 raw/do16，N17_03 对应 raw/正常17；另两张裁剪拒绝照
  N17_02、N19_01 的原图此前已删除，历史拒绝记录仍在 source_map.csv。
expanded_development_155/ 是扩批后已见开发对照 155 张。
expanded_holdout_48/ 是扩批后的 48 张历史留出输入（do35–do42、正常42/45/46/47）。

同名的两组 48 张是不同历史数据，不能混作一组；这些照片现已参与方法排查，
不代表新的独立盲测。每组随附映射或评分表，input_manifest.csv 给出所有 PNG 的 SHA-256。
raw 原图另在 tie_mount_all_raw_photos_20261102.zip，模型权重及两例黄金张量另在旧模型 Release。
