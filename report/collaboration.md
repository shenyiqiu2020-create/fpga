# GitHub 协作步骤（第一次使用版）

仓库地址：<https://github.com/shenyiqiu2020-create/fpga>。这是队长创建的私人仓库；如果打不开，请先登录自己的 GitHub 账号，接受队长发出的邀请，或请队长确认账号权限。不要在群聊发送密码、访问令牌和私钥。

## 第一次取得仓库

1. 安装 GitHub Desktop，使用获得邀请的 GitHub 账号登录。
2. 在浏览器打开仓库主页，点击 **Code → Open with GitHub Desktop**，或在 Desktop 用 **File → Clone repository** 选择该仓库。
3. 选定电脑上的本地目录并 Clone。此后在 GitHub Desktop 选择仓库，点 **Fetch origin / Pull origin** 获取队友更新。
4. 用编辑器打开本地 `fpga` 文件夹。先看根目录 `README.md` 和 [工作记录](progress.md)，再开始自己的任务。

## 如何使用这次交付的更新包

此次文件来自仓库下载快照，不是在线同步的提交。队员在 GitHub Desktop **先 Pull**，再在自己的工作分支解压更新包。压缩包内顶层直接是 `README.md`、`src/`、`sim/`、`report/` 等，复制这些文件到本地克隆的 `fpga/` 根目录，保持相对路径，不要放到 `fpga/fpga-main/` 子目录。

若 GitHub Desktop 的 Changes 显示队友在同一文件已有更新，先打开差异，逐段合并；不要直接覆盖队友内容。建议由一位队员导入一次，其余队员通过 Pull 获取该提交，避免重复复制。

## 平时如何提交和同步

1. 工作前点击 **Fetch origin / Pull origin**，确认自己从最新状态开始。
2. 在 GitHub Desktop 创建一个有意义的分支，例如 `feat/score-map`；每个功能尽量单独分支。
3. 修改文件，并在 `report/progress.md` 补记改动、原因、实际验证和下一步。代码测试在仓库根目录执行：`python -m unittest discover -s sim -v`。
4. 在 GitHub Desktop 的 **Changes** 查看逐文件差异，确保没有误加入缓存、数据集、权重或本地生成的大文件；填写可读的提交说明，点 **Commit to ...**。
5. 点击 **Publish branch / Push origin** 上传分支，然后选择 **Create Pull Request**，让另一位队员看改动和运行记录。合并后其他队员 Pull。

提交只保存到本机；Push 后才会上传到 GitHub。Pull Request 是合并到主分支前供队友查看的变更页。遇到冲突时，先保留双方内容，核对后再提交；不要用强制推送覆盖主分支。

## 本项目的约定

- `src/` 放可复用源码，`sim/` 放验证，`data/` 放数据来源与清单，`board/` 放板级配置和实测，`build/` 放可复现构建和工具报告，`report/` 放设计与进度。
- 不把“计划加速”“待测指标”写成已经跑通。实验结果要记录板卡、工具版本、输入、运行命令和输出。
- 竞赛版 ARM PS + PL 与课程版 RISC-V SoC 分别记录，避免误以为目前已经有 RISC-V 或可运行的检测系统。
