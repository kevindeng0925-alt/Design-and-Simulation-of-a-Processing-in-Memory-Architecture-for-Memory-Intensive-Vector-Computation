"""Temporary D-only types. See docs/d/INTERFACE_DRAFT.md."""

from collections.abc import MutableMapping
from dataclasses import dataclass

Vector = list[int] | tuple[int, ...]
Value = Vector | int
Memory = MutableMapping[str, Value]


@dataclass(frozen=True)
class Workload:
    op: str
    src_a: str
    src_b: str
    dst: str
    n: int

    def __post_init__(self):
        if self.op not in ("VADD", "VMUL", "DOT"):
            raise ValueError(f"unsupported operation: {self.op!r}")
        if type(self.n) is not int or self.n < 0:
            raise ValueError("n must be a nonnegative integer")
        for address in (self.src_a, self.src_b, self.dst):
            if not isinstance(address, str) or not address.strip():
                raise ValueError("addresses must be nonempty strings")


@dataclass(frozen=True)
class Config:
    word_bits: int = 32
    cpu_startup_cycles: int = 8
    cpu_read_cycles_per_word: int = 4
    cpu_write_cycles_per_word: int = 4
    cpu_add_cycles: int = 1
    cpu_mul_cycles: int = 3

    def __post_init__(self):
        if type(self.word_bits) is not int or self.word_bits not in (8, 16, 32, 64):
            raise ValueError("word_bits must be 8, 16, 32, or 64")
        if type(self.cpu_startup_cycles) is not int or self.cpu_startup_cycles < 0:
            raise ValueError("cpu_startup_cycles must be a nonnegative integer")
        for name, value in vars(self).items():
            if name not in ("word_bits", "cpu_startup_cycles"):
                if type(value) is not int or value <= 0:
                    raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ExecutionResult:
    output: list[int] | int
    path: str
    cycles: int
    host_memory_bytes: int
    pim_internal_bytes: int | None = None
    predicted_cpu_cycles: int | None = None
    predicted_pim_cycles: int | None = None
    choice_reason: str | None = None
    decision_cycles: int | None = None
    bank_busy_cycles: list[int] | None = None


def read_vector(memory: Memory, address: str, n: int, word_bits: int) -> Vector:
    values = memory[address]
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{address!r} must contain a vector")
    if len(values) != n:
        raise ValueError(f"{address!r} has length {len(values)}, expected {n}")
    limit = 1 << (word_bits - 1)
    for value in values:
        if type(value) is not int:
            raise TypeError(f"{address!r} must contain integers")
        if not -limit <= value < limit:
            raise ValueError(f"{address!r} contains a value outside signed i{word_bits}")
    return values
