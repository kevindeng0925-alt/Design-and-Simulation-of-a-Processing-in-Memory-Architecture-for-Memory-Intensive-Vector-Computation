"""Synthetic observations live only in temporary test directories.

The success-path fixtures exercise the CSV contract of a non-mock model.
Their invented timings must never appear in results/.
"""

import contextlib
import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.backend import Backend
from benchmarks.comparison import analyze
from benchmarks.cpu_study import write_study, plot_study
from benchmarks.plot_results import main as plot
from benchmarks.provenance import save_json
from benchmarks.review_run import assess, review
from benchmarks.run_benchmarks import CPU_BACKEND, FIELDS, MODES, cases_for, run_case
from src.cpu.model import execute_cpu


def design_for(lengths):
    d = json.loads(Path("benchmarks/design.json").read_text(encoding="utf-8"))
    d["validation"] = dict(lengths=lengths, banks=[1], offload_cycles=[0], seed=2)
    d["calibration"] = dict(lengths=[17], banks=[1], offload_cycles=[0], seed=1)
    d["plots"] = dict(length=lengths[0], banks=1, offload_cycles=0)
    d["cpu_study"]["lengths"] = [1, 4]
    return d


def synthetic_rows(design, split, pim_costs=None):
    rows = []
    for case in cases_for(design, split):
        cpu, *_ = run_case(case, {"cpu": CPU_BACKEND})
        config = json.loads(cpu["config_json"])
        config["backend_settings"] = {"fixture": "synthetic-suite"}
        pim = (pim_costs or {}).get(case.n, 80)
        for mode in MODES:
            choice = "cpu" if mode == "cpu" else "pim"
            cost = {"cpu": 100, "pim": pim, "adaptive": pim + 3}[mode]
            row = dict(cpu, config_json=json.dumps(config), backend="synthetic-fixture",
                       model_version="test-v1", requested_mode=mode, actual_path=choice,
                       cycles=str(cost), decision_cycles="3" if mode == "adaptive" else "")
            rows.append(row)
    return rows


def save_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class ComparisonTests(unittest.TestCase):
    def test_multiple_reversals_observed_tie_and_missing_grid_point(self):
        design = design_for(list(range(1, 9)))
        rows = synthetic_rows(design, "validation", {1: 100, 2: 110, 3: 90, 4: 120})
        rows = [r for r in rows if r["n"] != 5]
        summary, points = analyze(rows, design, "validation")
        self.assertEqual(summary["pairs"], dict(valid=21, missing=3, invalid=0, incomparable=0))
        self.assertEqual(summary["winners"], dict(tie=3, cpu=6, pim=12))
        self.assertEqual([(r["lower_n"], r["upper_n"]) for r in summary["crossing_intervals"]
                          if r["op"] == "VADD"], [(2, 3), (3, 4)])
        self.assertEqual(len(points), 24)

    def test_no_crossover_for_uniform_advantage_or_all_ties(self):
        d = design_for([1, 2, 4])
        for price, winner in [(80, "pim"), (100, "tie"), (120, "cpu")]:
            with self.subTest(price=price):
                rows = synthetic_rows(d, "validation", dict.fromkeys([1, 2, 4], price))
                summary, _ = analyze(rows, d, "validation")
                self.assertEqual(summary["crossing_intervals"], [])
                self.assertEqual(summary["winners"], {winner: 9})

    def test_comparability_and_duplicate_controls(self):
        d = design_for([1])
        for field, value in [("input_sha256", "other"), ("input_seed", "3"),
                             ("cycle_unit", "ns"), ("window", "kernel-only"),
                             ("semantics", "unbounded"), ("config_json", "{}"),
                             ("model_version", "test-v2"), ("backend", "other-suite")]:
            with self.subTest(field=field):
                rows = synthetic_rows(d, "validation")
                rows[1][field] = value
                s, _ = analyze(rows, d, "validation")
                self.assertEqual((s["pairs"]["incomparable"], s["adaptive"]["incomparable"]), (1, 1))
                self.assertFalse(s["complete"])
        rows = synthetic_rows(d, "validation")
        s, _ = analyze(rows + [rows[0]], d, "validation")
        self.assertEqual(s["pairs"]["invalid"], 1)
        self.assertFalse(s["complete"])

    def test_changed_suites_do_not_bridge_lengths(self):
        d = design_for([2, 3])
        rows = synthetic_rows(d, "validation", {2: 140, 3: 80})
        for row in rows:
            if row["n"] == 3:
                row["model_version"] = "changed"
        s, _ = analyze(rows, d, "validation")
        self.assertEqual(s["pairs"]["valid"], 6)
        self.assertEqual(s["crossing_intervals"], [])
        self.assertFalse(s["complete"])

    def test_adaptive_ties_misses_and_signed_excess(self):
        d = design_for([1, 2])
        rows = synthetic_rows(d, "validation", {1: 100, 2: 120})
        for row in rows:
            if row["requested_mode"] == "adaptive" and row["n"] == 1 and row["op"] == "DOT":
                row["actual_path"] = "cpu"
                row["cycles"] = "95"
        s, points = analyze(rows, d, "validation")
        self.assertEqual(s["adaptive"]["valid"], 6)
        self.assertEqual(s["fastest_fraction"], .5)
        self.assertEqual(s["total_extra_cycles"], 70)  # -5 + 3 + 3 + 3 * 23
        self.assertEqual(s["negative_extra"], 1)
        self.assertEqual(s["decision_conflicts"], 1)
        self.assertIn(-5, [p["extra_cycles"] for p in points])
        self.assertFalse(s["complete"])

    def test_missing_mock_and_incorrect_adaptive(self):
        d = design_for([1])
        rows = synthetic_rows(d, "validation")
        rows[2]["is_mock"] = "true"
        rows[5]["correct"] = "false"
        rows.pop()
        s, _ = analyze(rows, d, "validation")
        self.assertEqual(s["adaptive"], dict(valid=0, invalid=2, missing=1, incomparable=0))
        self.assertEqual(s["pairs"]["valid"], 3)
        self.assertIsNone(s["fastest_fraction"])
        self.assertIsNone(s["total_extra_cycles"])

    def test_optional_diagnostics_pass_through(self):
        case = next(cases_for(design_for([1]), "validation"))

        def fixture(job, mem, mode, case):
            result = execute_cpu(job, mem, case.cpu)
            return replace(result, choice_reason="test", predicted_cpu_cycles=10,
                           predicted_pim_cycles=15, decision_cycles=2, bank_busy_cycles=[0])

        backend = Backend("mock", "test", fixture, is_mock=True)
        cpu, _, adaptive = run_case(case, {"cpu": CPU_BACKEND, "adaptive": backend})
        self.assertNotIn("decision_cycles", cpu)
        self.assertEqual((adaptive["choice_reason"], adaptive["predicted_cpu_cycles"],
                          adaptive["predicted_pim_cycles"], adaptive["decision_cycles"],
                          adaptive["bank_busy_cycles"]), ("test", 10, 15, 2, "[0]"))


class AcceptanceTests(unittest.TestCase):
    def test_end_to_end_formal_gate_and_stale_speedup_cleanup(self):
        d = design_for([2, 4])
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            design, draft = root / "design.json", root / "REPORT.md"
            data, figures = root / "data", root / "figures"
            save_json(design, d)
            draft.write_text("Synthetic test only", encoding="utf-8")
            cal_file, val_file = data / "calibration.csv", data / "validation.csv"
            calibration = synthetic_rows(d, "calibration")
            validation = synthetic_rows(d, "validation")
            save_csv(cal_file, calibration)
            save_csv(val_file, validation)
            study = data / "cpu_study.csv"
            write_study(study, d)
            plot_study(study, figures, design)

            def make_plots():
                args = ["plot", "--input", str(val_file), "--design", str(design),
                        "--output-dir", str(figures)]
                with patch.object(sys, "argv", args):
                    plot()

            def bind_draft_and_generate_summary():
                record, _ = assess(design, root, draft)
                draft.write_text(f"<!-- experiment: {record['experiment']} -->", encoding="utf-8")
                review(design, root, draft, False)

            make_plots()
            speedup = figures / "speedup_vs_banks.png"
            self.assertTrue(speedup.is_file())
            bind_draft_and_generate_summary()
            self.assertEqual(review(design, root, draft, True), 0)
            # Even a freshly generated receipt cannot make mock data official.
            calibration[1]["is_mock"] = "true"
            save_csv(cal_file, calibration)
            bind_draft_and_generate_summary()
            self.assertEqual(review(design, root, draft, True), 2)
            calibration[1]["is_mock"] = "false"
            save_csv(cal_file, calibration)
            bind_draft_and_generate_summary()
            with (root / "review/run_report.md").open("a", encoding="utf-8") as file:
                file.write("stale")
            with self.assertRaisesRegex(ValueError, "run_report.md"):
                review(design, root, draft, True)
            original = speedup.read_bytes()
            speedup.write_bytes(b"wrong figure")
            record, _ = assess(design, root, draft)
            self.assertFalse(record["formal_complete"])
            speedup.write_bytes(original)
            keep = figures / "my-figure.png"
            keep.write_bytes(b"user file")
            for row in validation:
                if row["requested_mode"] != "cpu":
                    row.update(status="unavailable", cycles="", correct="")
            save_csv(val_file, validation)
            record, _ = assess(design, root, draft)
            self.assertTrue(any("comparison_figures.json" in issue for issue in record["issues"]))
            make_plots()
            self.assertFalse(speedup.exists())
            self.assertEqual(keep.read_bytes(), b"user file")
            bind_draft_and_generate_summary()
            self.assertEqual(review(design, root, draft, True), 2)
