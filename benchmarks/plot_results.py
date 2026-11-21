"""Plot directly from a benchmark CSV using a fixed slice of the design."""

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from benchmarks.run_benchmarks import MODES, OPS

LABELS = {"cpu": "CPU-only", "pim": "Always-PIM", "adaptive": "Adaptive CPU/PIM"}
COLORS = {"cpu": "#24619c", "pim": "#ad542d", "adaptive": "#287859"}


def eligible(row):
    return row["status"] == "ok" and row["correct"] == "true" and row["is_mock"] == "false"


def series(rows, op, mode, x_field, y_field):
    """Keep gaps for failed/unavailable cases so no line crosses a missing point."""
    points = {}
    for row in rows:
        if row["op"] != op or row["requested_mode"] != mode:
            continue
        x = int(row[x_field])
        if x in points:
            raise ValueError(f"duplicate case at {op}/{mode}/{x_field}={x}")
        points[x] = float(row[y_field]) if eligible(row) else math.nan
    return dict(sorted(points.items()))


def speedup_series(rows, op, mode):
    cpu = series(rows, op, "cpu", "banks", "cycles")
    compare = series(rows, op, mode, "banks", "cycles")
    return {
        x: cpu[x] / cycles if x in cpu and cycles > 0 else math.nan
        for x, cycles in compare.items()
    }


def plot_panels(path, rows, title, xlabel, ylabel, note, modes, get_points, log_x=False):
    fig, axes = plt.subplots(1, len(OPS), figsize=(10.4, 4.0), sharey=True)
    handles = {}
    try:
        for ax, op in zip(axes, OPS):
            for mode in modes:
                points = get_points(rows, op, mode)
                if any(math.isfinite(y) for y in points.values()):
                    line, = ax.plot(list(points), list(points.values()), "o-", markersize=4,
                                    linewidth=1.6, color=COLORS[mode], label=LABELS[mode])
                    handles[mode] = line
            if not ax.lines:
                ax.text(0.5, 0.5, "No eligible data", ha="center", transform=ax.transAxes)
            if ylabel == "Speedup (CPU cycles / mode cycles)":
                ax.axhline(1, color="#626d75", linewidth=1, linestyle="--")
                ax.set_xticks(sorted({int(row["banks"]) for row in rows}))
            if log_x:
                ax.set_xscale("log", base=2)
            ax.set_title(op, loc="left", fontsize=11, weight="bold")
            ax.set_xlabel(xlabel)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", color="#d8dfe6", linewidth=0.7)
            ax.set_axisbelow(True)
        axes[0].set_ylabel(ylabel)
        fig.suptitle(title, x=0.10, ha="left", fontsize=15, weight="bold")
        fig.legend(handles.values(), [LABELS[mode] for mode in handles],
                   loc="upper right", bbox_to_anchor=(0.98, 0.916), frameon=False, ncol=3)
        fig.text(0.10, 0.035, note, fontsize=8, color="#374451")
        fig.subplots_adjust(left=0.10, right=0.97, bottom=0.22, top=0.74, wspace=0.18)
        fig.savefig(path, dpi=160, facecolor="white")
    finally:
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--design", type=Path, default=Path("benchmarks/design.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    with args.input.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    splits = {row["split"] for row in rows}
    if len(splits) != 1:
        parser.error("provide a nonempty CSV containing one split")
    split, = splits
    design = json.loads(args.design.read_text(encoding="utf-8"))
    fixed = design["plots"]
    banks, overhead, length = fixed["banks"], fixed["offload_cycles"], fixed["length"]
    with_overhead = [row for row in rows if int(row["offload_cycles"]) == overhead]
    length_rows = [row for row in with_overhead if int(row["banks"]) == banks]
    bank_rows = [row for row in with_overhead if int(row["n"]) == length]
    if not any(map(eligible, length_rows)):
        parser.error("the bank/overhead slice has no correct non-mock rows")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    shown_rows = [row for row in length_rows + bank_rows if eligible(row)]
    cpu_configs = {json.dumps(json.loads(row["config_json"])["cpu"], sort_keys=True)
                   for row in shown_rows}
    if len(cpu_configs) != 1:
        parser.error("selected rows must share one CPU configuration")
    cpu = json.loads(cpu_configs.pop())
    versions = sorted({row["model_version"] for row in shown_rows})
    model_note = (
        f"Signed i{cpu['word_bits']}, serial CPU with no cache or overlap. Input: {args.input.name}"
        f" ({split}).\nCPU cycles: start={cpu['cpu_startup_cycles']}, read/write per word="
        f"{cpu['cpu_read_cycles_per_word']}/{cpu['cpu_write_cycles_per_word']}, "
        f"add/mul={cpu['cpu_add_cycles']}/{cpu['cpu_mul_cycles']}. Model: {', '.join(versions)}."
    )
    eligible_modes = {row["requested_mode"] for row in length_rows if eligible(row)}
    missing = [LABELS[mode] for mode in MODES if mode not in eligible_modes]
    scope = f"Banks={banks}, offload={overhead} cycles."
    if missing:
        scope += " No eligible data: " + ", ".join(missing) + "."
    length_note = scope + " " + model_note
    for file, title, y_label, field in (
        ("latency_vs_length.png", "Simulated latency by vector length", "Simulated cycles", "cycles"),
        ("host_traffic_vs_length.png", "Host-memory traffic by vector length",
         "Host-memory traffic (bytes)", "host_memory_bytes"),
    ):
        plot_panels(args.output_dir / file, length_rows, title, "Vector length (elements)",
                    y_label, length_note, MODES,
                    lambda data, op, mode: series(data, op, mode, "n", field),
                    log_x=all(int(row["n"]) > 0 for row in length_rows))
        print(args.output_dir / file)

    compared = MODES[1:]
    speedup_path = args.output_dir / "speedup_vs_banks.png"
    has_speedup = any(
        math.isfinite(y)
        for op in OPS
        for mode in compared
        for y in speedup_series(bank_rows, op, mode).values()
    )
    if has_speedup:
        plot_panels(speedup_path, bank_rows, "Simulated speedup by bank count",
                    "Memory banks", "Speedup (CPU cycles / mode cycles)",
                    f"Length={length} elements, offload={overhead} cycles. " + model_note,
                    compared, speedup_series)
        print(speedup_path)
    else:
        print(f"Skipped {speedup_path}: no eligible PIM/Adaptive rows paired with CPU.")


if __name__ == "__main__":
    main()
