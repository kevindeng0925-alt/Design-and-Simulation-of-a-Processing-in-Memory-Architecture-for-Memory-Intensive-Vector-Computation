import unittest
from dataclasses import replace

from src.cpu.d_compat import Config, Workload
from src.cpu.model import cpu_cost_parts, estimate_cpu_cycles, execute_cpu


class CpuResearchTests(unittest.TestCase):
    def test_signed_i32_limits_and_dot_accumulation(self):
        hi, lo = 2147483647, -2147483648
        for op, a, b, answer in [
            ("VADD", [hi, lo], [1, -1], [lo, hi]),
            ("VMUL", [lo, hi], [-1, 2], [lo, -2]),
            ("DOT", [hi, 1], [1, 1], lo),
            ("DOT", [lo, lo], [-1, -1], 0),
            ("DOT", [hi, hi, hi], [1, 1, -1], hi),
        ]:
            with self.subTest(op=op, a=a):
                mem = {"A": a, "B": b}
                result = execute_cpu(Workload(op, "A", "B", "C", len(a)), mem, Config())
                self.assertEqual((result.output, mem["C"]), (answer, answer))

    def test_hand_calculated_cost_parts(self):
        config = Config(cpu_startup_cycles=2, cpu_read_cycles_per_word=3,
                        cpu_write_cycles_per_word=5, cpu_add_cycles=7, cpu_mul_cycles=11)
        for op, n, parts in [
            ("VADD", 0, (2, 0, 0, 0, 0)), ("VMUL", 0, (2, 0, 0, 0, 0)),
            ("DOT", 0, (2, 0, 5, 0, 0)), ("DOT", 1, (2, 6, 5, 0, 11)),
            ("DOT", 3, (2, 18, 5, 14, 33)), ("VMUL", 3, (2, 18, 15, 0, 33)),
            ("VADD", 3, (2, 18, 15, 21, 0)),
        ]:
            with self.subTest(op=op, n=n):
                job = Workload(op, "A", "B", "C", n)
                expected = dict(zip(("startup", "input_read", "output_write",
                                     "addition", "multiplication"), parts))
                self.assertEqual(cpu_cost_parts(job, config), expected)
                actual = execute_cpu(job, {"A": [0]*n, "B": [0]*n}, config)
                self.assertEqual(actual.cycles, sum(parts))

    def test_isolated_parameter_changes(self):
        base = Config()
        for op, multiply, write in [("VADD", 0, 4), ("VMUL", 4, 4), ("DOT", 4, 1)]:
            with self.subTest(op=op):
                job = Workload(op, "A", "B", "C", 4)
                before = estimate_cpu_cycles(job, base)
                for cfg, delta in [(replace(base, cpu_mul_cycles=4), multiply),
                                   (replace(base, cpu_write_cycles_per_word=5), write),
                                   (replace(base, cpu_startup_cycles=0), -8)]:
                    self.assertEqual(estimate_cpu_cycles(job, cfg) - before, delta)
