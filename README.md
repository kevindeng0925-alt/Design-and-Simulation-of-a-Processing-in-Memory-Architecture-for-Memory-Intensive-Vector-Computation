# Bank-Level PIM Simulator

课程项目比较三种模式：CPU-only、Always-PIM 和 Adaptive CPU/PIM。当前可以运行 D 的 CPU baseline、正确性测试、批量实验和绘图。Always-PIM 与 Adaptive 等待 B/C 提供模拟器和统一入口。

## 在 Windows PowerShell 复现 D

在含此 README 的仓库目录打开 PowerShell。以下命令使用 Python 3.12，已用 3.12.4 验证。每次运行 Python 都指向本项目的虚拟环境，无需激活环境。

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements-d.txt
& $python -m pip check
& $python -m unittest discover -s tests -v
& $python -m src.cpu
& $python -m benchmarks.run_benchmarks --split smoke --output .venv/smoke.csv
& $python -m benchmarks.run_benchmarks --split calibration --output results/data/calibration.csv
& $python -m benchmarks.run_benchmarks --split validation --output results/data/validation.csv
& $python -m benchmarks.plot_results --input results/data/validation.csv --output-dir results/figures
& $python -m benchmarks.cpu_study run
& $python -m benchmarks.cpu_study plot
& $python -m benchmarks.review_run
```

示例的 VADD、VMUL、DOT 输出分别为 `[6, 2, -2]`、`[8, -15, 0]`、`-7`。每套正式实验应输出 `189 ok`、`0 failed` 和 `378 unavailable`。图表脚本会从验证集 CSV 生成周期图与 host-memory 流量图，并报告缺少可用数据的加速比图。绘图会更新脚本负责的 PNG 和来源清单，缺少加速比数据时自动清除旧的同名图。CPU 敏感性 CSV 包含 84 条记录；`review_run` 生成两套矩阵的配对明细和运行摘要。

## 如何判断是否能提交三模式结论

在上面的复现命令之后运行 `& $python -m benchmarks.review_run --formal`。它只读检查校准集和验证集的完整矩阵、有效样本、模型标识、输入、时基、统计窗口，以及保存的图、数据和报告版本。当前预期输出 `formal_complete = False` 并返回退出码 2，因为两个 PIM 相关模式均未接入。独立 CPU 实验已经能运行。

接入 C 后给三次 benchmark 命令都追加 `--controller-adapter module:attribute`，替换成组内实际入口。在报告中写入新数据支持的结论并更新 `<!-- experiment: … -->`（编号由 `review_run` 打印）。重跑 `review_run` 生成摘要，再运行 `--formal` 只读核验。准入通过仍需 C 的控制流测试确认 Adaptive 的决策时机。

只分析一个 CSV 可运行 `& $python -m benchmarks.comparison --input results/data/validation.csv --split validation --output .venv/validation-analysis.json`。用自定义网格时附上相应的 `--design`。输出逐点胜者、相邻反转区间、有效数与额外周期。比较需要新版 CSV 中的契约和输入摘要；旧版 CSV 可重画 CPU 趋势图。

- [逐次运行摘要](results/review/run_report.md) · [逐点结果](results/review/points.csv) · [机器可读验收结果](results/review/summary.json)
- [CPU 分解与敏感性原始 CSV](results/data/cpu_study.csv) · [成本分解图](results/figures/cpu_cost_parts.png) · [敏感性图](results/figures/cpu_sensitivity.png)

- [CPU 临时接口与集成约定](docs/d/INTERFACE_DRAFT.md)
- [Baseline、Benchmark 和 Results 报告草稿](docs/d/REPORT.md)
- [展示提纲与演示步骤](docs/d/DEMO.md)
- [进度与验证记录](docs/d/PROGRESS.md)
- [实验配置](benchmarks/design.json) · [校准 CSV](results/data/calibration.csv) · [保留验证 CSV](results/data/validation.csv)
- [CPU 模拟周期图](results/figures/latency_vs_length.png) · [CPU 主机内存流量图](results/figures/host_traffic_vs_length.png)
