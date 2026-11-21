"""One-factor CPU sensitivity experiment and plots from its saved observations."""

import argparse
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

from benchmarks.provenance import digest, save_json
from benchmarks.run_benchmarks import OPS, generate_inputs, input_digest, reference_answer
from src.cpu.d_compat import Config, Workload
from src.cpu.model import MODEL_VERSION, cpu_cost_parts, execute_cpu

PARTS = ("startup", "input_read", "output_write", "addition", "multiplication")
FIGURES = ("cpu_cost_parts.png", "cpu_sensitivity.png")


def observations(design):
    study = design["cpu_study"]
    base = Config(**design["cpu"])
    for n in study["lengths"]:
        a, b = generate_inputs(n, base.word_bits, study["seed"])
        for op in OPS:
            job = Workload(op, "A", "B", "C", n)
            expected = reference_answer(op, a, b, base.word_bits)
            for scenario, changes in study["scenarios"].items():
                cfg = replace(base, **changes)
                mem = {"A": a.copy(), "B": b.copy()}
                result = execute_cpu(job, mem, cfg)
                parts = cpu_cost_parts(job, cfg)
                if result.output != expected or mem["C"] != expected or sum(parts.values()) != result.cycles:
                    raise ValueError(f"CPU study verification failed: {op}/{n}/{scenario}")
                yield dict(scenario=scenario, op=op, n=n, input_seed=study["seed"],
                           model_version=MODEL_VERSION, input_sha256=input_digest(a, b),
                           **asdict(cfg), **parts, cycles=result.cycles,
                           host_memory_bytes=result.host_memory_bytes, correct="true")


def write_study(path, design):
    rows = list(observations(design))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{path}: {len(rows)} verified CPU observations")


def plot_study(path, figure_dir, design_path):
    design = json.loads(design_path.read_text(encoding="utf-8"))
    study = design["cpu_study"]
    figure_dir.mkdir(parents=True, exist_ok=True)
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    data = {(r["scenario"], r["op"], int(r["n"])): r for r in rows}
    expected = {(s, op, n) for s in study["scenarios"] for op in OPS for n in study["lengths"]}
    if set(data) != expected or len(data) != len(rows) or any(r["correct"] != "true" for r in rows):
        raise ValueError("incomplete or duplicated CPU sensitivity grid")
    for (scenario, op, n), row in data.items():
        cfg = {**design["cpu"], **study["scenarios"][scenario]}
        if (row["model_version"] != MODEL_VERSION or int(row["input_seed"]) != study["seed"]
                or any(int(row[name]) != value for name, value in cfg.items())
                or sum(int(row[name]) for name in PARTS) != int(row["cycles"])):
            raise ValueError(f"study row disagrees with design or cost total: {scenario}/{op}/{n}")
    small, large = min(study["lengths"]), max(study["lengths"])
    fig, ax = plt.subplots(figsize=(8, 3.8))
    left = [0] * len(OPS)
    colors = ("#714b79", "#287086", "#67acac", "#c68836", "#794a2d")
    for field, color in zip(PARTS, colors):
        values = [int(data["base", op, large][field]) for op in OPS]
        ax.barh(OPS, values, left=left, label=field.replace("_", " "), color=color)
        left = [x + y for x, y in zip(left, values)]
    ax.set_xlabel("Simulated cycles")
    ax.set_title(f"Where CPU cycles go at N = {large:,}", loc="left")
    ax.legend(ncol=5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.24))
    fig.subplots_adjust(left=.13, bottom=.32, top=.87, right=.97)
    note = f"Source: {path.name} | {MODEL_VERSION} | fixed signed i{design['cpu']['word_bits']}, serial CPU"
    fig.text(.04, .025, note, fontsize=8)
    fig.savefig(figure_dir / FIGURES[0], dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4), sharey=True, sharex=True)
    scenarios = [s for s in study["scenarios"] if s != "base"]
    for ax, n in zip(axes, (small, large)):
        for offset, op, color in zip((-.23, 0, .23), OPS, colors[1:4]):
            changes = [100 * (int(data[s, op, n]["cycles"]) / int(data["base", op, n]["cycles"]) - 1)
                       for s in scenarios]
            ax.barh([i + offset for i in range(len(scenarios))], changes,
                    height=.21, color=color, label=op)
        ax.set_yticks(range(len(scenarios)), scenarios)
        ax.axvline(0, color="#333333", lw=.7)
        ax.set_title(f"N = {n:,}")
        ax.set_xlabel("Cycle change from base (%)")
    axes[0].invert_yaxis()
    axes[1].legend(frameon=False)
    fig.suptitle("Sensitivity to one cost change at a time", x=.17, ha="left")
    fig.subplots_adjust(left=.17, right=.97, bottom=.18, top=.81)
    fig.text(.04, .025, note, fontsize=8)
    fig.savefig(figure_dir / FIGURES[1], dpi=150)
    plt.close(fig)
    save_json(figure_dir / "cpu_study_figures.json", {
        "source_csv": digest(path), "design": digest(design_path),
        "files": {name: digest(figure_dir / name) for name in FIGURES},
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "plot"))
    parser.add_argument("--design", type=Path, default=Path("benchmarks/design.json"))
    parser.add_argument("--csv", type=Path, default=Path("results/data/cpu_study.csv"))
    parser.add_argument("--figures", type=Path, default=Path("results/figures"))
    args = parser.parse_args()
    if args.action == "run":
        write_study(args.csv, json.loads(args.design.read_text(encoding="utf-8")))
    else:
        plot_study(args.csv, args.figures, args.design)


if __name__ == "__main__":
    main()
