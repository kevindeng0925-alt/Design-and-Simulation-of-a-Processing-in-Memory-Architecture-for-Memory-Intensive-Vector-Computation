"""Pair observations against the planned grid. No interpolation or gap filling."""

import argparse
import csv
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import asdict
import json

from benchmarks.backend import CYCLE_UNIT, SEMANTICS, WINDOW
from benchmarks.provenance import save_json
from benchmarks.run_benchmarks import MODES, cases_for, generate_inputs, input_digest


def case_key(row):
    return (row["op"], int(row["banks"]), int(row["offload_cycles"]), int(row["n"]))


def row_state(row):
    if row.get("is_mock") == "true":
        return "mock"
    if row.get("status") == "unavailable":
        return "unavailable"
    mode = row.get("requested_mode")
    path = row.get("actual_path")
    if (row.get("status") != "ok" or row.get("correct") != "true"
            or row.get("is_mock") != "false" or path not in ("cpu", "pim")
            or (mode != "adaptive" and mode != path)):
        return "failed"
    for name in ("cycles", "host_memory_bytes"):
        if not str(row.get(name, "")).isascii() or not str(row.get(name, "")).isdigit():
            return "failed"
    return "success"


def signature(row, case, expected_digest):
    """The version identifies the entire adapter/model suite, including its policy."""
    try:
        config = json.loads(row["config_json"])
        if json.dumps(config["cpu"], sort_keys=True) != json.dumps(asdict(case.cpu), sort_keys=True):
            return None
        if "backend_settings" not in config:
            return None
        if row["requested_mode"] != "cpu" and not isinstance(config["backend_settings"], dict):
            return None
        matches = (
            int(row["input_seed"]) == case.input_seed,
            row.get("input_sha256") == expected_digest,
            row.get("cycle_unit") == CYCLE_UNIT,
            row.get("window") == WINDOW,
            row.get("semantics") == SEMANTICS,
            bool(row.get("backend")), bool(row.get("model_version")),
        )
        if all(matches):
            return (row["backend"], row["model_version"], json.dumps(config, sort_keys=True))
    except (KeyError, TypeError, ValueError):
        pass
    return None


def classify(modes, buckets, case, digest):
    selected = []
    for mode in modes:
        matches = buckets.get(mode, [])
        if len(matches) > 1:
            return "invalid", None
        if not matches or row_state(matches[0]) == "unavailable":
            return "missing", None
        if row_state(matches[0]) != "success":
            return "invalid", None
        selected.append(matches[0])
    signatures = {signature(row, case, digest) for row in selected}
    if None in signatures or len(signatures) != 1:
        return "incomparable", None
    return "valid", signatures.pop()


def analyze(rows, design, split):
    planned = {(c.op, c.banks, c.offload_cycles, c.n): c for c in cases_for(design, split)}
    buckets = defaultdict(lambda: defaultdict(list))
    states = Counter(dict.fromkeys(("success", "failed", "unavailable", "mock"), 0))
    extra = 0
    for row in rows:
        states[row_state(row)] += 1
        try:
            key = case_key(row)
        except (KeyError, ValueError, TypeError):
            key = None
        if key not in planned or row.get("split") != split or row.get("requested_mode") not in MODES:
            extra += 1
            continue
        buckets[key][row["requested_mode"]].append(row)
    counts = dict.fromkeys(("valid", "missing", "invalid", "incomparable"), 0)
    pairs, adaptive = counts.copy(), counts.copy()
    expected_digests = {}
    used_cpu, suites = set(), set()
    points, intervals = [], []
    fastest = negative = overhead_conflicts = 0
    excess = []
    previous = None
    for key, case in sorted(planned.items()):
        if case.n not in expected_digests:
            arrays = generate_inputs(case.n, case.cpu.word_bits, case.input_seed)
            expected_digests[case.n] = input_digest(*arrays)
        digest = expected_digests[case.n]
        observed = buckets[key]
        cpu_state, cpu_sig = classify(("cpu",), observed, case, digest)
        if cpu_state == "valid":
            used_cpu.add((case.op, case.n, cpu_sig))
        state, sig = classify(("cpu", "pim"), observed, case, digest)
        pairs[state] += 1
        adaptive_state, _ = classify(MODES, observed, case, digest)
        adaptive[adaptive_state] += 1
        point = dict(op=case.op, banks=case.banks, offload_cycles=case.offload_cycles, n=case.n,
                     cpu=cpu_state, pair=state, adaptive=adaptive_state)
        points.append(point)
        if state != "valid":
            previous = None
            continue
        suites.add(sig)
        cpu = int(observed["cpu"][0]["cycles"])
        pim = int(observed["pim"][0]["cycles"])
        winner = "tie" if cpu == pim else ("cpu" if cpu < pim else "pim")
        point.update(winner=winner, cpu_cycles=cpu, pim_cycles=pim)
        group = (key[:-1], sig)
        if previous and previous[0] == group and {previous[2], winner} == {"cpu", "pim"}:
            intervals.append(dict(op=case.op, banks=case.banks, offload_cycles=case.offload_cycles,
                                  lower_n=previous[1], upper_n=case.n))
        previous = (group, case.n, winner)
        if adaptive_state == "valid":
            row = observed["adaptive"][0]
            chosen = row["actual_path"]
            hit = winner in ("tie", chosen)
            delta = int(row["cycles"]) - min(cpu, pim)
            decision = row.get("decision_cycles")
            if decision not in (None, ""):
                chosen_cycles = cpu if chosen == "cpu" else pim
                if not str(decision).isascii() or not str(decision).isdigit():
                    point["decision_check"] = "invalid decision_cycles"
                elif int(row["cycles"]) < chosen_cycles + int(decision):
                    point["decision_check"] = "below chosen baseline plus declared decision cycles"
                overhead_conflicts += "decision_check" in point
            fastest += hit
            negative += delta < 0
            excess.append(delta)
            point.update(path=chosen, fastest=hit, extra_cycles=delta, adaptive_cycles=int(row["cycles"]))
    summary = dict(split=split, rows=len(rows), states=dict(states), planned_cases=len(planned),
                   unexpected_rows=extra, effective_cpu=len(used_cpu), pairs=pairs, adaptive=adaptive,
                   fastest_count=fastest, fastest_fraction=fastest / len(excess) if excess else None,
                   mean_extra_cycles=sum(excess) / len(excess) if excess else None,
                   total_extra_cycles=sum(excess) if excess else None, negative_extra=negative,
                   decision_conflicts=overhead_conflicts,
                   winners=dict(Counter(p["winner"] for p in points if "winner" in p)),
                   crossing_intervals=intervals, suites=sorted(suites))
    summary["complete"] = (
        len(rows) == len(planned) * len(MODES) and extra == 0
        and adaptive["valid"] == len(planned) and len(suites) == 1 and negative == 0 and overhead_conflicts == 0
    )
    return summary, points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--design", type=Path, default=Path("benchmarks/design.json"))
    parser.add_argument("--split", required=True, choices=("smoke", "calibration", "validation"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    summary, points = analyze(rows, json.loads(args.design.read_text(encoding="utf-8")), args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, {"summary": summary, "points": points})
    print(summary["pairs"], summary["adaptive"], "complete =", summary["complete"])


if __name__ == "__main__":
    main()
