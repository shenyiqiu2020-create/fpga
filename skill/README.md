# 可复用技能包

本目录提交的是从本工程中提炼并实际验证的工程方法，不是仅含标题的占位文件。当前不声明 PYNQ Skill 加分，板端采用 standalone ARM 程序。

## 黄金参考与工件身份校验

适用场景：任何需要固定输入、权重、固件、参考输出的 FPGA 或软件工程。

用法：执行 `python skill/golden_checks/check_manifest.py data/submission_manifest.json --root .`。清单中的每项仅含相对路径和 SHA256，可换成另一工程的文件清单。退出码 0 表示身份一致，退出码 1 表示文件缺失或内容变化。

来源：IP 修改后 Vivado 可能继续使用旧导出或旧综合缓存；只看版本号和“Build succeeded”不足以确认使用了新 RTL。本队对综合、打包、通过仿真的 RTL 与 Vivado 实际导入文件逐项比对。

验证：`python sim/test_delivery_tools.py` 覆盖正确哈希、故意修改文件、越界路径、有效时序及负 slack 五种情况；原始结果在 `sim/results/delivery_tools_validation.json`。完整项目的模型和固件还由 `build/verify_delivery.py` 复核。

失效条件：哈希只能证明字节身份，不能证明模型有效或参考答案正确；清单本身不可信时也不能作为信任根。模型、接口、工具版本或量化规则改变后必须重新建立独立参考。

## 资源和时序核验

适用场景：使用 Vivado 标准 timing summary 格式的单时钟或多时钟 FPGA 工程。

用法：`python skill/golden_checks/read_timing.py build/reports/vivado_timing.rpt`。解析 setup/hold slack 和时钟列表，任一负 slack 返回失败；报告格式不匹配时直接报错，不猜测数值。

来源：HLS 时钟估计与实际布线时序不同；提高配置频率也不能证明板上按该频率工作。本队将 HLS 调度、布线后时序、SLCR 时钟寄存器和板上计时分开核验。

失效条件：该脚本不核验约束是否完整，不检查跨时钟协议，也不能替代硬件时钟读回或板测。新报告格式须重新验证解析器。

## 基于证据的优化工作流

提示词模板与适用范围见 `optimization_workflow.md`；失败案例及边界见 `failure_cases.md`。它们适合其他 HLS 运算核，但不保证换模型或换板后仍获得同样收益。
