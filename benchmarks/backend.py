"""Execution adapter for D's benchmark."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from src.cpu.d_compat import Config, ExecutionResult, Memory, Workload


@dataclass(frozen=True)
class Case:
    split: str
    op: str
    n: int
    banks: int
    offload_cycles: int
    input_seed: int
    cpu: Config


@dataclass(frozen=True)
class Backend:
    name: str
    model_version: str
    execute: Callable[[Workload, Memory, str, Case], ExecutionResult]
    is_mock: bool = False
    settings: Mapping | None = None
