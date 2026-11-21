# D 进度记录

## 2026-11-21

| 项目 | 进度与验证 |
| --- | --- |
| 仓库 | 原目录保存课程资料和已有汇报。新 checkout 在 `pim-project`。开发基于 `main` 的 `0931bed`，任务分支 `d/cpu-baseline-benchmarks`。起点只有 README，未发现 AGENTS.md |
| 环境 | 本机 Python 3.12.4、项目虚拟环境和 Matplotlib 3.9.4。依赖安装和 `pip check` 已通过 |
| CPU | VADD、VMUL、DOT，配置化模拟周期、host-memory 流量及固定宽度整数。三条演示输出已核对 |
| 测试 | `python -m unittest discover -s tests -v` 共 11 项通过。首次溢出测试的手算余数有误，按 `5500 = 21 × 256 + 124` 更正用例并重跑 |
| Smoke | `python -m benchmarks.run_benchmarks --split smoke --output .venv/smoke.csv`，36 正确、0 失败、72 不可用 |
| 校准和验证 | 各 189 正确、0 失败、378 不可用，已保存原始 CSV |
| 绘图 | 从保留验证 CSV 生成两张 CPU 图并检查版面。三模式图和 bank 加速比图待真实配对数据 |
| 文档 | 临时接口、成本模型、报告草稿、演示和复现命令已整理 |
| 干净环境复现 | 在独立 worktree 和新建虚拟环境中按 README 安装、测试、运行示例、跑三套实验和绘图。11 项测试通过，重新生成的 CSV 和图无 Git 差异 |

运行命令及输出路径集中在 [README](../../README.md)。待 C 确认的有符号整数规则、地址、输出与单位见 [临时接口约定](INTERFACE_DRAFT.md)。

## 接入条件

B 提供三运算、bank 成本和内部分项统计。C 提供共享类型、统一 `run` 入口、并行完成时间、DOT 最终归约与执行前的 Adaptive 策略。对齐统计窗口后用 smoke 跑三模式，再以校准集冻结策略、运行保留验证集、生成比较图并补写收支平衡点和决策误差。
