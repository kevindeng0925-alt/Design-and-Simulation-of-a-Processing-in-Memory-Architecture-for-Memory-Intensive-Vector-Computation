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

## 2026-11-22 · 第二轮

在 `计组project.1/pim-project` 的原分支上继续。已复现旧 speedup 图残留，并加入“先出三张图，再只给 CPU 数据”的临时目录回归测试，校验用户其他文件仍在。CPU 周期的五项分解已接入原有估算函数。两套固定矩阵和 84 条单因素 CPU 实验均已重跑，产出成本图、敏感性图和带来源清单的比较图。

新循环案例包括 5 组 i32 边界、7 组手算成本分解和 8 种契约字段不匹配。测试方法总数为 22，以上为方法内的输入组，不能与 84 条实验记录相加。比较算法的合成测例覆盖多个反转、平局、缺点、Mock、负额外周期和版本混用。正式三模式数据仍缺 B/C，配对数为 0。复现命令以 [README](../../README.md) 为准，验收结果见 [运行摘要](../../results/review/run_report.md)。

独立 checkout `tmp/d-round2-verification` 使用新的 Python 3.12.4 虚拟环境。首次安装遇到 pip 索引 JSON 解析错误，使用 `python -m pip install --no-cache-dir -r requirements-d.txt` 后安装成功，`pip check` 通过。按 README 跑完示例、三套 benchmark、CPU 参数实验、绘图及审查，重生成的 CSV、PNG、清单和报告均无 Git 差异。共通过 22 个测试方法，其中实际执行了 48 个 unittest 子案例。正式核验按预期返回 2，等待 B/C。
