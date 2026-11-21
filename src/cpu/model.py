"""Functional CPU baseline and deterministic serial cost model."""

from .d_compat import Config, ExecutionResult, Memory, Workload, read_vector

MODEL_VERSION = "cpu-serial-word-v1"


def _compute(op, a, b, word_bits):
    modulus = 1 << word_bits
    sign = modulus // 2

    def wrap(value):
        return (value + sign) % modulus - sign

    if op == "VADD":
        return [wrap(x + y) for x, y in zip(a, b)]
    if op == "VMUL":
        return [wrap(x * y) for x, y in zip(a, b)]
    # Wrapping the final sum gives the same fixed-width value as wrapping
    # every product and addition. Python's accumulator can be wider.
    return wrap(sum(x * y for x, y in zip(a, b)))


def cpu_cost_parts(workload: Workload, config: Config) -> dict[str, int]:
    """Serial model, all five components measured in reference cycles."""
    n, op = workload.n, workload.op
    adds = n if op == "VADD" else 0
    if op == "DOT":
        adds = max(n - 1, 0)
    writes = 1 if op == "DOT" else n
    return {
        "startup": config.cpu_startup_cycles,
        "input_read": 2 * n * config.cpu_read_cycles_per_word,
        "output_write": writes * config.cpu_write_cycles_per_word,
        "addition": adds * config.cpu_add_cycles,
        "multiplication": (0 if op == "VADD" else n) * config.cpu_mul_cycles,
    }


def estimate_cpu_cycles(workload: Workload, config: Config) -> int:
    return sum(cpu_cost_parts(workload, config).values())


def execute_cpu(workload: Workload, memory: Memory, config: Config) -> ExecutionResult:
    """Read both vectors, compute the result and replace the destination."""
    a = read_vector(memory, workload.src_a, workload.n, config.word_bits)
    b = read_vector(memory, workload.src_b, workload.n, config.word_bits)
    output = _compute(workload.op, a, b, config.word_bits)
    writes = 1 if workload.op == "DOT" else workload.n
    result = ExecutionResult(
        output=output,
        path="cpu",
        cycles=estimate_cpu_cycles(workload, config),
        host_memory_bytes=(2 * workload.n + writes) * (config.word_bits // 8),
        pim_internal_bytes=0,
    )
    memory[workload.dst] = output.copy() if isinstance(output, list) else output
    return result
