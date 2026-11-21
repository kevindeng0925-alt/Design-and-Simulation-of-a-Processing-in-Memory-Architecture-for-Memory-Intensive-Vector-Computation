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
```

示例的 VADD、VMUL、DOT 输出分别为 `[6, 2, -2]`、`[8, -15, 0]`、`-7`。每套正式实验应输出 `189 ok`、`0 failed` 和 `378 unavailable`。图表脚本会从验证集 CSV 生成周期图与 host-memory 流量图，并报告缺少可用数据的加速比图。生成到一个新目录可避免和之前的图混在一起。

- [CPU 临时接口与集成约定](docs/d/INTERFACE_DRAFT.md)
- [Baseline、Benchmark 和 Results 报告草稿](docs/d/REPORT.md)
- [展示提纲与演示步骤](docs/d/DEMO.md)
- [进度与验证记录](docs/d/PROGRESS.md)
- [实验配置](benchmarks/design.json) · [校准 CSV](results/data/calibration.csv) · [保留验证 CSV](results/data/validation.csv)
- [CPU 模拟周期图](results/figures/latency_vs_length.png) · [CPU 主机内存流量图](results/figures/host_traffic_vs_length.png)
