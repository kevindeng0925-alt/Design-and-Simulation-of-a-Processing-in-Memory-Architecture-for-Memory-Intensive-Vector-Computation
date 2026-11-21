from dataclasses import asdict
import json

from .d_compat import Config, Workload
from .model import execute_cpu


def main():
    for op in ("VADD", "VMUL", "DOT"):
        memory = {"A": [2, -3, 0], "B": [4, 5, -2]}
        result = execute_cpu(Workload(op, "A", "B", "C", 3), memory, Config())
        print(json.dumps({"op": op, **asdict(result)}))


if __name__ == "__main__":
    main()
