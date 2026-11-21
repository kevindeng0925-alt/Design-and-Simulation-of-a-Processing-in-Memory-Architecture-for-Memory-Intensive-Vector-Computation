"""Run a deterministic D benchmark and keep failed/unavailable rows."""

import argparse
import csv
import hashlib
import itertools
import json
import operator
import random
from dataclasses import asdict
from importlib import import_module
from pathlib import Path

from benchmarks.backend import Backend, Case, CYCLE_UNIT, SEMANTICS, WINDOW
from src.cpu.d_compat import Config, Workload
from src.cpu.model import MODEL_VERSION, execute_cpu

OPS = ("VADD", "VMUL", "DOT")
MODES = ("cpu", "pim", "adaptive")
FIELDS = (
    "split", "op", "n", "banks", "offload_cycles", "requested_mode", "actual_path",
    "cycles", "host_memory_bytes", "pim_internal_bytes", "correct", "status", "error",
    "input_seed", "config_json", "model_version", "backend", "is_mock",
    "input_sha256", "cycle_unit", "semantics", "window", "predicted_cpu_cycles",
    "predicted_pim_cycles", "choice_reason", "decision_cycles", "bank_busy_cycles",
)


def _cpu(workload, memory, mode, case):
    return execute_cpu(workload, memory, case.cpu)


CPU_BACKEND = Backend("src.cpu.model.execute_cpu", MODEL_VERSION, _cpu,
                      cycle_unit=CYCLE_UNIT, semantics=SEMANTICS, window=WINDOW)


def cases_for(design, split):
    config = Config(**design["cpu"])
    axes = design[split]
    for name, minimum in (("lengths", 0), ("banks", 1), ("offload_cycles", 0)):
        axis = axes[name]
        if (not axis or any(type(x) is not int or x < minimum for x in axis)
                or len(set(axis)) != len(axis)):
            raise ValueError(f"{split}.{name} requires distinct integers >= {minimum}")
    seed = axes["seed"]
    if type(seed) is not int:
        raise ValueError(f"{split}.seed must be an integer")
    for op, n, banks, overhead in itertools.product(
        OPS, axes["lengths"], axes["banks"], axes["offload_cycles"]
    ):
        yield Case(split, op, n, banks, overhead, seed, config)


def generate_inputs(n, word_bits, seed):
    randomizer = random.Random(seed)
    bound = min(128, 1 << (word_bits - 1))
    return tuple([randomizer.randrange(-bound, bound) for _ in range(n)] for _ in range(2))


def input_digest(a, b):
    payload = json.dumps([a, b], separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def reference_answer(op, a, b, bits):
    """Independent oracle using indexed arithmetic and bit masks."""
    mask = (1 << bits) - 1
    sign = 1 << (bits - 1)

    def signed(value):
        low = value & mask
        return low - (1 << bits) if low & sign else low

    if op == "DOT":
        return signed(sum(a[i] * b[i] for i in range(len(a))))
    action = operator.add if op == "VADD" else operator.mul
    return [signed(action(a[i], b[i])) for i in range(len(a))]


def output_matches(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return all(type(item) is int for item in actual) and actual == expected
    return actual == expected


def run_case(case, backends):
    workload = Workload(case.op, "A", "B", "C", case.n)
    a, b = generate_inputs(case.n, case.cpu.word_bits, case.input_seed)
    digest = input_digest(a, b)
    expected = reference_answer(case.op, a, b, case.cpu.word_bits)
    for mode in MODES:
        backend = backends.get(mode)
        row = dict(split=case.split, op=case.op, n=case.n, banks=case.banks,
                   offload_cycles=case.offload_cycles, input_seed=case.input_seed,
                   requested_mode=mode, input_sha256=digest)
        row["config_json"] = json.dumps(
            {"cpu": asdict(case.cpu), "backend_settings": backend.settings if backend else None},
            sort_keys=True,
        )
        if backend is None:
            yield {**row, "status": "unavailable", "error": "No C controller adapter configured"}
            continue

        row.update(model_version=backend.model_version, backend=backend.name,
                   is_mock=str(backend.is_mock).lower(), cycle_unit=backend.cycle_unit,
                   semantics=backend.semantics, window=backend.window)
        memory = {"A": a.copy(), "B": b.copy()}
        try:
            result = backend.execute(workload, memory, mode, case)
            row["actual_path"] = result.path
            row["correct"] = str(output_matches(result.output, expected)
                                 and output_matches(memory.get(workload.dst), expected)).lower()
            if row["correct"] != "true":
                raise ValueError(f"wrong result or missing write to {workload.dst!r}")
            if result.path not in ("cpu", "pim") or (mode != "adaptive" and result.path != mode):
                raise ValueError(f"unexpected actual path {result.path!r} for {mode}")
            for field in ("cycles", "host_memory_bytes", "pim_internal_bytes"):
                value = getattr(result, field)
                if field == "pim_internal_bytes" and value is None:
                    continue
                if type(value) is not int or value < 0:
                    raise ValueError(f"{field} must be a nonnegative integer")
            for field in ("predicted_cpu_cycles", "predicted_pim_cycles", "decision_cycles"):
                value = getattr(result, field, None)
                if value is not None:
                    if type(value) is not int or value < 0:
                        raise ValueError(f"invalid {field}")
                    row[field] = value
            busy = getattr(result, "bank_busy_cycles", None)
            if busy is not None:
                if len(busy) != case.banks or any(type(v) is not int or v < 0 for v in busy):
                    raise ValueError("invalid bank_busy_cycles")
                row["bank_busy_cycles"] = json.dumps(busy)
            row["choice_reason"] = getattr(result, "choice_reason", None)
            row.update(status="ok", cycles=result.cycles, host_memory_bytes=result.host_memory_bytes,
                       pim_internal_bytes=result.pim_internal_bytes)
        except Exception as exc:
            row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        yield row


def write_csv(path, cases, backends):
    counts = dict(ok=0, failed=0, unavailable=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for case in cases:
            for row in run_case(case, backends):
                writer.writerow(row)
                counts[row["status"]] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=Path("benchmarks/design.json"))
    parser.add_argument("--split", choices=("smoke", "calibration", "validation"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller-adapter", help="Import path of a Backend as module:attribute")
    args = parser.parse_args()
    backends = {"cpu": CPU_BACKEND}
    if args.controller_adapter:
        module_name, separator, attribute = args.controller_adapter.partition(":")
        if not separator or not module_name or not attribute:
            parser.error("--controller-adapter must be module:attribute")
        adapter = getattr(import_module(module_name), attribute)
        if not isinstance(adapter, Backend):
            parser.error("--controller-adapter must point to a Backend instance")
        backends = dict.fromkeys(MODES, adapter)
    design = json.loads(args.design.read_text(encoding="utf-8"))
    cases = list(cases_for(design, args.split))
    counts = write_csv(args.output, cases, backends)
    print(f"{args.output}: {counts}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
