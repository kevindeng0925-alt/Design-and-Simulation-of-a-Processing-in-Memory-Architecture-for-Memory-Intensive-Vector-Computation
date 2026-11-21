"""Generate a run report, or verify the saved delivery with --formal (read-only)."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from benchmarks.comparison import analyze
from benchmarks.cpu_study import FIGURES as STUDY_FIGURES, observations
from benchmarks.plot_results import FIGURES as COMPARISON_FIGURES
from benchmarks.provenance import digest


def check_figures(directory, receipt_file, expected_names, source_hash, design_hash, split=None):
    receipt = json.loads((directory / receipt_file).read_text(encoding="utf-8"))
    names = set(expected_names)
    if (receipt.get("source_csv") != source_hash or receipt.get("design") != design_hash
            or receipt.get("split") != split or set(receipt["files"]) != names):
        raise ValueError(f"{receipt_file}: source, design, split or figure set mismatch")
    for name in names:
        if digest(directory / name) != receipt["files"][name]:
            raise ValueError(f"{name}: content differs from figure receipt")
    if "speedup_vs_banks.png" not in names and receipt_file == "comparison_figures.json":
        if (directory / "speedup_vs_banks.png").exists():
            raise ValueError("stale speedup_vs_banks.png")
    return receipt["files"]


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def assess(design_path, results, report_draft):
    design = json.loads(design_path.read_text(encoding="utf-8"))
    data, figures = results / "data", results / "figures"
    sources = {"design": digest(design_path)}
    summaries, details, issues = {}, [], []
    grids = {}
    for split in ("calibration", "validation"):
        path = data / f"{split}.csv"
        sources[split] = digest(path)
        summary, points = analyze(read_rows(path), design, split)
        grids[split] = {(p["op"], p["n"], p["banks"], p["offload_cycles"]) for p in points}
        summaries[split] = summary
        if not summary["complete"]:
            issues.append(f"{split}: incomplete or invalid three-mode matrix")
        details.extend(dict(split=split, **p) for p in points)
    if grids["calibration"] & grids["validation"]:
        issues.append("calibration and validation share experimental conditions")
    if summaries["calibration"]["suites"] != summaries["validation"]["suites"]:
        issues.append("different model suites across splits")

    study_path = data / "cpu_study.csv"
    sources["cpu_study"] = digest(study_path)
    study_rows = read_rows(study_path)
    expected = [{k: str(v) for k, v in r.items()} for r in observations(design)]
    def study_key(row):
        return row["op"], row["n"], row["scenario"]

    if sorted(study_rows, key=study_key) != sorted(expected, key=study_key):
        issues.append("CPU study differs from verified observations under this design")
    validation = [p for p in details if p["split"] == "validation"]
    fixed = design["plots"]
    need_speedup = any(
        p["pair"] == "valid" and p["n"] == fixed["length"]
        and p["offload_cycles"] == fixed["offload_cycles"]
        and (p["pim_cycles"] > 0 or (p["adaptive"] == "valid" and p["adaptive_cycles"] > 0))
        for p in validation
    )
    if not need_speedup:
        issues.append("validation: no defined speedup at the planned figure slice")
    names = COMPARISON_FIGURES if need_speedup else COMPARISON_FIGURES[:2]
    images = {}
    for receipt, required, source, split in (
        ("comparison_figures.json", names, sources["validation"], "validation"),
        ("cpu_study_figures.json", STUDY_FIGURES, sources["cpu_study"], None),
    ):
        try:
            images.update(check_figures(figures, receipt, required, source, sources["design"], split))
        except (OSError, TypeError, ValueError, KeyError) as exc:
            issues.append(str(exc))

    experiment = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    if f"<!-- experiment: {experiment} -->" not in report_draft.read_text(encoding="utf-8"):
        issues.append(f"report draft has no matching experiment marker: {experiment}")
    record = dict(experiment=experiment, sources=sources, figures=images,
                  report_draft=digest(report_draft), cpu_study_observations=len(study_rows),
                  splits=summaries, formal_complete=not issues, issues=issues)
    return record, details


def render(record, details):
    stream = io.StringIO(newline="")
    fields = ("split", "op", "banks", "offload_cycles", "n", "cpu", "pair", "adaptive", "winner",
              "cpu_cycles", "pim_cycles", "adaptive_cycles", "path", "fastest", "extra_cycles", "decision_check")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(details)
    report = ["# 实验运行摘要", "", f"数据版本 `{record['experiment']}`。"
              f" CPU 敏感性实验共 {record['cpu_study_observations']} 条。", "",
              "| 数据集 | 总行数 | 成功 / 失败 / 不可用 / Mock | 有效 CPU 配置 | CPU/PIM 配对 | Adaptive 有效样本 |",
              "| --- | ---: | --- | ---: | ---: | ---: |"]
    for split, s in record["splits"].items():
        counts = " / ".join(str(v) for v in s["states"].values())
        report.append(f"| {split} | {s['rows']} | {counts} | {s['effective_cpu']} | "
                      f"{s['pairs']['valid']} | {s['adaptive']['valid']} |")
    for split, s in record["splits"].items():
        report.extend(["", f"## {split}", "",
                       "| 评价对象 | 有效 | 缺失或不可用 | 失效（含 Mock） | 不可比 |",
                       "| --- | ---: | ---: | ---: | ---: |"])
        for label, counts in (("CPU/PIM", s["pairs"]), ("Adaptive", s["adaptive"])):
            report.append(f"| {label} | {counts['valid']} | {counts['missing']} | "
                          f"{counts['invalid']} | {counts['incomparable']} |")
        if s["pairs"]["valid"]:
            report.append(f"采样点胜负计数 {s['winners']}。相邻有效点发生优势反转的区间数为 "
                          f"{len(s['crossing_intervals'])}，具体端点见 summary.json。")
        if s["adaptive"]["valid"]:
            report.append(f"选中最快路径 {s['fastest_count']}/{s['adaptive']['valid']}。"
                          f"平均额外周期 {s['mean_extra_cycles']:.2f}，负差值 {s['negative_extra']} 个。")
    report.extend(["", "## 正式三模式验收", "", "通过。" if record["formal_complete"] else "待完成。"])
    report.extend(f"- {issue}" for issue in record["issues"])
    return {"summary.json": json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            "points.csv": stream.getvalue(), "run_report.md": "\n".join(report) + "\n"}


def review(design, results, report_draft, formal):
    record, points = assess(design, results, report_draft)
    directory = results / "review"
    artifacts = render(record, points)
    if formal:
        for name, expected in artifacts.items():
            path = directory / name
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                raise ValueError(f"{name} is missing or stale")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            (directory / name).write_text(content, encoding="utf-8")
    print(f"experiment={record['experiment']}")
    for split, summary in record["splits"].items():
        print(split, summary["states"], "pairs", summary["pairs"]["valid"],
              "adaptive", summary["adaptive"]["valid"])
    for issue in record["issues"]:
        print(issue)
    print("formal_complete =", record["formal_complete"])
    return 2 if formal and not record["formal_complete"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=Path("benchmarks/design.json"))
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--report-draft", type=Path, default=Path("docs/d/REPORT.md"))
    parser.add_argument("--formal", action="store_true")
    args = parser.parse_args()
    try:
        return review(args.design, args.results, args.report_draft, args.formal)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(2, f"Review failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
