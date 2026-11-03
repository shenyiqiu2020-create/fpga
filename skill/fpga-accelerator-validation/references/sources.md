# 结构参考与内容来源

访问日期：2026-11-03。

1. [Agent Skills Specification](https://agentskills.io/specification)：参考 YAML `name`/`description`、目录与分层加载约定。
2. [OpenAI skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md)：参考适用范围描述、按需引用、脚本封装和验证方法。
3. [Anthropic webapp-testing](https://github.com/anthropics/skills/blob/main/skills/webapp-testing/SKILL.md)：参考“按任务分支选择流程”“现成脚本先看帮助”“从可观察结果确认执行完成”的组织方式。没有复制其 Playwright 脚本或引入浏览器依赖。

本技能正文、测试覆盖选择、证据分级与辅助脚本由本项目的 FPGA 移植/验证实践提炼并重写，自有内容采用 MIT。外部仓库的代码没有复制进来；仅参考公开格式与工作流组织。FINN 和 EfficientAD 的代码许可仍按主项目 `report/sources.md` 登记，不能因技能采用 MIT 而替代第三方许可。

`SKILL.md` 是 Agent Skills 的标准入口名，因此保留大小写。其他说明与脚本采用小写文件名；不为满足小写习惯把入口改成无法发现的 `skill.md`。
