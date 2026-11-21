# D 报告草稿

## Baseline

CPU 路径先从两个内存地址各读一个向量，然后计算，最后把结果写回目标地址。VADD 和 VMUL 写回一个长度为 N 的向量。DOT 将 N 个乘积加起来，只写回一个整数。

模型版本 `cpu-serial-word-v1`。令 W 为每个整数的字节数，R 为写回的字数（VADD/VMUL 为 N，DOT 为 1）。

```text
host-memory bytes = (2N + R) × W
cycles = startup + 2N × read + R × write + arithmetic
VADD arithmetic = N × add
VMUL arithmetic = N × mul
DOT  arithmetic = N × mul + max(N - 1, 0) × add
```

| 参数 | 默认值 | 单位 |
| --- | ---: | --- |
| 整数位宽 | 32 | bit |
| 启动 | 8 | 模拟周期 / 任务 |
| 读、写 | 4、4 | 模拟周期 / 字 |
| 加、乘 | 1、3 | 模拟周期 / 次 |

参数为课程实验的自设值。访存与计算串行相加，CPU 模型不包含缓存、SIMD、预取、流水线、访存重叠或 DRAM 通道争用。主机流量按逻辑读取和写回的有效载荷计数，排除 Python 对象占用和结果核验访问。仿真以同一个抽象周期为比较单位。Python 运行耗时属于实验工具开销，本实验未采集。

## Benchmark

每个配置由操作、长度、bank 数、卸载开销以及种子确定。三条模式各拿一个独立内存副本。核验通过后才写性能值，核验同时检查返回值和目的地址。参考答案由独立整数逻辑生成，手算单元测试另外覆盖溢出、空向量、缺失地址、错误长度、结果形态和成本。失败行保留错误信息，模式不可用则保留空指标和 `unavailable`。

| 数据集 | 长度 N | Bank 数 | 卸载开销（周期） | 种子 |
| --- | --- | --- | --- | ---: |
| Smoke | 0、2、10 | 1、4 | 0、32 | 1600 |
| 校准 | 2、10、32、128、512、2048、8192 | 1、4、8 | 0、32、128 | 1610 |
| 保留验证 | 3、11、64、256、1024、4096、16384 | 2、4、16 | 16、32、96 | 1620 |

两套正式数据集长度互斥，输入种子也不同。固定 N、改变 bank 数时可以比较并行扩展性，固定 bank 数和卸载开销时可以比较长度增长的影响。接入 Adaptive 后，只允许用校准集定模型或阈值，冻结策略后再评价保留集。首轮测试同时包含 `N < banks` 和 `N % banks != 0`。

## Results

校准集和保留验证集各含 189 个 CPU 案例，全部核验通过。每个数据集还各含 378 个 PIM/Adaptive 的 `unavailable` 行。下表取自保留验证集的 N=1024、4 banks、卸载开销 32 周期。bank 数和卸载参数用于后续对照，CPU 公式中没有这两项。

| 操作 | CPU 模拟周期 | Host-memory（bytes） |
| --- | ---: | ---: |
| VADD | 13,320 | 12,288 |
| VMUL | 15,368 | 12,288 |
| DOT | 12,299 | 8,196 |

VADD 与 VMUL 搬运的数据量相同。VMUL 每个元素额外花 2 个计算周期，所以此处多 2,048 周期。DOT 只写回一个整数，因此这里比 VADD 少写 4,092 bytes。两个已生成的图固定 4 banks 和 32 个卸载周期，横轴用对数刻度展示长度范围。曲线外观受刻度影响，原始 CPU 模型周期与流量随 N 线性增长（DOT 的空输入单独处理）。

[模拟周期图](../../results/figures/latency_vs_length.png) · [主机内存流量图](../../results/figures/host_traffic_vs_length.png) · [保留验证 CSV](../../results/data/validation.csv)

三模式比较待 B/C 接入。接入后固定 N=1024、卸载开销 32 周期，绘制 `speedup = CPU cycles / 比较模式 cycles`。对每个操作、bank 数和卸载开销组合，按 N 检查 `PIM cycles - CPU cycles` 的正负和零值。若相邻样点异号，报告交叉区间。若测试范围无交叉，说明是全段哪条路径更快，或哪些点缺少可用观测。当前缺少 PIM 周期，交叉点及加速比均无法计算。Adaptive 的决策质量可用验证集上与最快路径一致的比例及额外周期 `adaptive cycles - min(cpu cycles, pim cycles)` 表示，并记录有效样本数。

## 方法依据

- Group 16 Proposal §3–4 及 Fig. 1 提供 CPU 与 bank 本地计算路径、相同任务语义和三项性能指标。课程分工细则给出 D 的代码位置和校准与验证流程。
- Wulf 与 McKee（1995）提出 memory wall 问题。Mutlu 等（2019、2025）说明为什么要关注数据搬运成本。 [Mutlu 等 2019](https://doi.org/10.1016/j.micpro.2019.01.009) · [Mutlu 等 2025](https://arxiv.org/abs/2012.03112)
- Gómez-Luna 等（2022）分别测量 UPMEM 的传输和计算，并在固定问题大小下改变 DPU 数量。这里采用类似的变量控制和统计范围区分。Lee 等（2021）说明 bank 级本地执行的现实背景。Seshadri 等（2017）的 Ambit 使用 DRAM 内的位运算机制，适合作为架构背景。本文周期参数均为课程模型设定。 [Gómez-Luna 等 2022](https://arxiv.org/abs/2105.03814) · [Lee 等 2021](https://doi.org/10.1109/ISCA52012.2021.00013) · [Seshadri 等 2017](https://doi.org/10.1145/3123939.3124544)
