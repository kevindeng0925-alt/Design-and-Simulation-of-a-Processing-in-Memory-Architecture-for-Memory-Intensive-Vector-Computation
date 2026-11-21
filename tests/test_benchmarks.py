import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.backend import Backend
from benchmarks.run_benchmarks import CPU_BACKEND, cases_for, run_case, write_csv
from src.cpu.d_compat import ExecutionResult


DESIGN = json.loads(Path("benchmarks/design.json").read_text(encoding="utf-8"))


class BenchmarkTests(unittest.TestCase):
    def test_fixed_design_has_bank_edges_and_disjoint_validation(self):
        cases = list(cases_for(DESIGN, "calibration"))
        validation = list(cases_for(DESIGN, "validation"))
        keys = lambda rows: {(c.op, c.n, c.banks, c.offload_cycles) for c in rows}
        self.assertTrue(any(0 < c.n < c.banks for c in cases))
        self.assertTrue(any(c.n > c.banks and c.n % c.banks for c in cases))
        self.assertTrue(keys(cases).isdisjoint(keys(validation)))
        self.assertNotEqual(cases[0].input_seed, validation[0].input_seed)

    def test_unavailable_rows_are_blank_and_csv_is_reproducible(self):
        cases = list(cases_for(DESIGN, "smoke"))
        with tempfile.TemporaryDirectory() as temp:
            first, second = (Path(temp) / name for name in ("a.csv", "b.csv"))
            counts = write_csv(first, cases, {"cpu": CPU_BACKEND})
            write_csv(second, cases, {"cpu": CPU_BACKEND})
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(counts, {"ok": 36, "failed": 0, "unavailable": 72})
            with first.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
        cpu, pim, adaptive = rows[:3]
        self.assertEqual((cpu["correct"], cpu["is_mock"], cpu["actual_path"]),
                         ("true", "false", "cpu"))
        for row in (pim, adaptive):
            self.assertEqual(row["status"], "unavailable")
            self.assertEqual((row["cycles"], row["host_memory_bytes"], row["correct"]),
                             ("", "", ""))

    def test_backend_receives_independent_memory_and_failure_is_kept(self):
        case = next(c for c in cases_for(DESIGN, "smoke") if c.n == 2)
        memories = []

        def test_only(workload, memory, mode, config):
            self.assertEqual((workload.n, config.banks, config.offload_cycles),
                             (case.n, case.banks, case.offload_cycles))
            self.assertNotIn("C", memory)
            memories.append((memory, memory["A"].copy(), memory["B"].copy()))
            left, right = memory["A"], memory["B"]
            output = [left[0] + right[0], left[1] + right[1]]
            if mode == "pim":
                output[1] += 1
            memory["C"] = output
            memory["A"][0] = 99999
            return ExecutionResult(output, "pim", 10, 0)

        mock = Backend("test-only", "mock", test_only, is_mock=True)
        rows = list(run_case(case, {"cpu": CPU_BACKEND, "pim": mock, "adaptive": mock}))
        self.assertIsNot(memories[0][0], memories[1][0])
        self.assertEqual(memories[0][1:], memories[1][1:])
        self.assertEqual((rows[1]["status"], rows[1]["correct"]), ("failed", "false"))
        self.assertNotIn("cycles", rows[1])
        self.assertEqual((rows[2]["status"], rows[2]["actual_path"], rows[2]["is_mock"]),
                         ("ok", "pim", "true"))

    def test_backend_requires_destination_and_integer_metrics(self):
        case = next(c for c in cases_for(DESIGN, "smoke") if c.n == 0)
        for store_output in (False, True):
            def test_only(workload, memory, mode, config):
                if store_output:
                    memory["C"] = []
                return ExecutionResult([], "pim", 1.5, 0)

            mock = Backend("test-only", "mock", test_only, is_mock=True)
            _, row, _ = run_case(case, {"pim": mock})
            self.assertEqual(row["status"], "failed")
            self.assertIn("cycles" if store_output else "missing write", row["error"])
            self.assertNotIn("host_memory_bytes", row)


if __name__ == "__main__":
    unittest.main()
