import unittest

from src.cpu.d_compat import Config, Workload
from src.cpu.model import estimate_cpu_cycles, execute_cpu


class CpuTests(unittest.TestCase):
    def test_hand_calculated_results_and_costs(self):
        samples = [
            ("VADD", [6, 2, -2], 47, 36),
            ("VMUL", [8, -15, 0], 53, 36),
            ("DOT", -7, 47, 28),
        ]
        for op, output, cycles, byte_count in samples:
            with self.subTest(op=op):
                memory = {"A": [2, -3, 0], "B": (4, 5, -2)}
                workload = Workload(op, "A", "B", "C", 3)
                result = execute_cpu(workload, memory, Config())
                self.assertEqual((result.output, memory["C"]), (output, output))
                self.assertEqual((result.cycles, estimate_cpu_cycles(workload, Config())),
                                 (cycles, cycles))
                self.assertEqual((result.host_memory_bytes, result.pim_internal_bytes),
                                 (byte_count, 0))
                self.assertEqual(result.path, "cpu")

    def test_empty_inputs_still_require_both_addresses(self):
        memory = {"A": [], "B": []}
        for op, expected in [("VADD", ([], 8, 0)), ("VMUL", ([], 8, 0)), ("DOT", (0, 12, 4))]:
            with self.subTest(op=op):
                result = execute_cpu(Workload(op, "A", "B", "C", 0), memory, Config())
                self.assertEqual((result.output, result.cycles, result.host_memory_bytes),
                                 expected)
        del memory["B"]
        with self.assertRaises(KeyError):
            execute_cpu(Workload("DOT", "A", "B", "C", 0), memory, Config())

    def test_fixed_width_overflow_and_aliasing(self):
        for op, expected in [("VADD", [-128, 101]), ("VMUL", [127, 124]), ("DOT", -5)]:
            with self.subTest(op=op):
                memory = {"A": [127, -100], "B": [1, -55]}
                result = execute_cpu(Workload(op, "A", "B", "A", 2), memory,
                                     Config(word_bits=8))
                self.assertEqual(result.output, expected)
                self.assertEqual(memory["A"], expected)
                self.assertEqual(result.host_memory_bytes, 5 if op == "DOT" else 6)
                if op != "DOT":
                    self.assertIsNot(result.output, memory["A"])

    def test_invalid_inputs_do_not_replace_destination(self):
        for b, expected_error in [(None, TypeError), ([], ValueError),
                                  ([True], TypeError), ([1.0], TypeError),
                                  ([128], ValueError)]:
            with self.subTest(b=b):
                memory = {"A": [0], "B": b, "C": 99}
                with self.assertRaises(expected_error):
                    execute_cpu(Workload("VADD", "A", "B", "C", 1), memory,
                                Config(word_bits=8))
                self.assertEqual(memory["C"], 99)

    def test_invalid_workload_and_config(self):
        for args in [("DIV", "A", "B", "C", 1), ("DOT", "A", "B", "", 1),
                     ("DOT", "A", "B", "C", -1), ("DOT", "A", "B", "C", True)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                Workload(*args)
        for kwargs in [{"word_bits": 7}, {"cpu_mul_cycles": 0},
                       {"cpu_startup_cycles": -1}, {"cpu_write_cycles_per_word": 1.5}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Config(**kwargs)

    def test_config_changes_cost_single_dot_has_no_addition(self):
        config = Config(word_bits=16, cpu_startup_cycles=0, cpu_read_cycles_per_word=5,
                        cpu_write_cycles_per_word=6, cpu_add_cycles=100, cpu_mul_cycles=7)
        memory = {"A": [3], "B": [-2]}
        result = execute_cpu(Workload("DOT", "A", "B", "C", 1), memory, config)
        self.assertEqual((result.output, result.cycles, result.host_memory_bytes), (-6, 23, 6))


if __name__ == "__main__":
    unittest.main()
