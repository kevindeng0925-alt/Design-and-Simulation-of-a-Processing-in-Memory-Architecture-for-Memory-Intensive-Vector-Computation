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


def estimate_cpu_cycles(workload: Workload, config: Config) -> int:
    """Predict the modeled CPU cycles using only the operation and length."""
    n = workload.n
    writes = 1 if workload.op == "DOT" else n
    if workload.op == "VADD":
        arithmetic = n * config.cpu_add_cycles
    elif workload.op == "VMUL":
        arithmetic = n * config.cpu_mul_cycles
    else:
        arithmetic = n * config.cpu_mul_cycles + max(n - 1, 0) * config.cpu_add_cycles
    return (
        config.cpu_startup_cycles
        + 2 * n * config.cpu_read_cycles_per_word
        + writes * config.cpu_write_cycles_per_word
        + arithmetic
    )


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
