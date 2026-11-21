# D 临时接口契约（待 C 确认）

仓库起点 `0931bed` 只有 README，当前以 `src/cpu/d_compat.py` 隔离 D 独立开发所需的数据结构。C 提交正式类型和接口后，在这里核对字段和语义。

## CPU 调用

`from src.cpu.model import execute_cpu`

`execute_cpu(workload, memory, config) -> ExecutionResult`

| 类型 | 最小字段或行为 |
| --- | --- |
| `Workload` | `op` 为大写 VADD、VMUL、DOT，`src_a`、`src_b`、`dst` 为区分大小写的非空字符串地址，`n` 为非负整数 |
| `Memory` | 可读写的映射，例如 `{"A": [1, 2], "B": [3, 4]}`。输入地址对应长度恰好为 `n` 的 list 或 tuple。输入预先位于内存，完成后替换 `memory[dst]` |
| `Config` | `word_bits` 和 CPU 启动、读、写、加、乘的模拟周期参数。默认值见报告 |
| `ExecutionResult` | `output` 为新列表或 DOT 标量，`path="cpu"`，`cycles` 是模拟周期，`host_memory_bytes` 是 CPU 与内存之间的有效载荷字节数，`pim_internal_bytes` 对 CPU 为 0 |

输入和输出都采用有符号二补码整数。支持 8、16、32、64 位，默认 32 位。输入越界报错，运算溢出按该位宽回绕，例如 8 位的 `127 + 1 → -128`。DOT 的乘积与求和都遵循同一模数，最终输出一个同位宽标量。对每一步回绕与最后统一回绕在数学上等价，分 bank 后可合并部分和。空输入仍要求两个源地址已存在，VADD/VMUL 写空列表，DOT 写整数 0。

地址缺失抛出 `KeyError`。输入形态或元素类型错误（含布尔值和浮点数）抛出 `TypeError`。未知操作、空地址、长度不符、越界整数和非法配置抛出 `ValueError`。验证在写入前完成，目的地址可与源地址相同。CPU 两次逻辑读取都计费，即使两个输入引用同一地址。

## B/C 集成前确认

- **统计窗口**从输入已驻留内存开始，到输出写回目的地址为止。初始化和事后读回检验发生在窗口外。host-memory 指跨主机与内存的有效载荷，包括经过主机的 DOT 部分和或结果。命令、同步耗时纳入周期，控制消息字节暂不纳入有效载荷。PIM 内部有效载荷单独统计，未知值填空。
- **时基与成本责任**待确认。CPU 与 PIM 应统一到同一种模拟周期。如果 B 采用不同周期长度，C 需在接口层记录换算规则并提供公共时基的结果。D 计 CPU 启动、读写、算术。建议 B 计每 bank 的本地访存和算术，C 计卸载、调度、同步、跨边界传输与 DOT 部分和的最终归约及最终写回。每段成本只记一次。bank 全部同时启动且无共享瓶颈时，以最慢 bank 完成时间为准。有串行调度、总线争用或分批时，按实际关键路径计算。
- **接入统一入口**先核对 `src/common.py`、`docs/interfaces.md` 与 `run(workload, memory, mode, config)`。正式字段落地后优先迁移 D 的适配代码。若共享整数或输出规则有变化，修改对应核心和 oracle，并重新生成数据。
- **Benchmark 适配器**提供一个可导入的 `benchmarks.backend.Backend` 对象。其 `execute(workload, memory, mode, case)` 将 D 案例转为正式参数，再调用 C。 `case.banks`、`case.offload_cycles`、`case.cpu` 是该实验点的配置。适配器将正式输出和实际路径规范化为 D 的 `ExecutionResult`，并同步正式执行后的目的地址值以供验证。无法等价转换时显式报错。后端记录版本和 `settings`（可序列化 JSON，含 PIM、时基与策略配置），Mock 用 `is_mock=True` 标记。命令加 `--controller-adapter module:attribute`，先跑 smoke，再重跑两个固定实验集。
- **Adaptive 决策**由 C 在执行前依据 `op`、`n`、bank 划分和成本参数作出。D 的 `estimate_cpu_cycles(workload, config)` 只读取操作和长度，可用作 CPU 估算。benchmark 对三种模式分别调用，只传该次输入和配置。接入时由 C 的诊断或控制流测试验证决策顺序与单路径执行，CSV 的实际路径一列无法单独证明决策时机。

## 第二轮配对字段（待 C 确认）

- 统一入口的 `Backend` 显式声明 `cycle_unit`、`semantics`、`window`。D 使用的常量在 `benchmarks/backend.py`。C 需要核实或换算后再声明；缺失字段使相应样本不可比。三条路径使用同一套 adapter 名称、模型版本和完整的 `settings` 字典，含 B 的成本和 C 的策略版本。
- Runner 对实际初始 A/B 的规范 JSON 算 SHA-256，并将种子和摘要写入 CSV。分析程序从实验设计重建输入核验摘要。位宽及 CPU 参数取自 `config_json`。旧格式缺少这些证据，需要重新跑 benchmark 才能纳入配对。
- 可选诊断为 `predicted_cpu_cycles`、`predicted_pim_cycles`、`choice_reason`、`decision_cycles` 和长度等于 bank 数的 `bank_busy_cycles`。未提供时 CSV 留空。所有时间均已换算为公共参考周期。Adaptive 的 `cycles` 必须含决策开销；`decision_cycles` 仅作分项诊断。
- 评价工具依赖后端如实填报身份、单位和统计窗口。决策先后顺序仍要由 C 的实现或执行轨迹证明。
