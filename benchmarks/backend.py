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


# Adapters declare these after checking their native units and semantics.
CYCLE_UNIT = "reference-cycle-v1"
SEMANTICS = "signed-wrap/same-width-dot-v1"
WINDOW = "resident-input-to-writeback/decision-included/payload-bytes-v1"


@dataclass(frozen=True)
class Backend:
    name: str
    model_version: str
    execute: Callable[[Workload, Memory, str, Case], ExecutionResult]
    is_mock: bool = False
    settings: Mapping | None = None
    cycle_unit: str | None = None
    semantics: str | None = None
    window: str | None = None
