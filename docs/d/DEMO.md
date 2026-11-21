# D 部分展示与演示

建议 2 分钟，演示前把终端打开到仓库根目录，并按 README 安装依赖。

1. **先展示正确性（30 秒）。** 运行 `.\.venv\Scripts\python.exe -m src.cpu`。用 `[2, -3, 0]` 和 `[4, 5, -2]` 解释 DOT：对应位置相乘后再相加，得到 `8 - 15 + 0 = -7`。VADD 和 VMUL 则保留每个位置的结果。
2. **解释统计单位（30 秒）。** 示例的 VADD 读 6 个数、写 3 个数，每个数 4 bytes，所以搬运 36 bytes。47 个模拟周期来自启动 8、读写 36、计算 3。运行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 可展示对公式、错误输入和实验记录的检查。
3. **展示实验（45 秒）。** 按 README 运行 smoke，打开 `.venv/smoke.csv`。指出 `correct`、`cycles`、`host_memory_bytes` 与 `status` 四列。打开保留验证集的两张 CPU 图，说明加法和乘法搬运相同的字节数，而 DOT 只写回一个整数。
4. **交代可比较范围（15 秒）。** 这两张是 CPU 仿真图。B/C 接通后，同一个输入分别跑三种模式，再比较加速比和在哪个长度区间发生优势反转。当前 PIM 与 Adaptive 行显示 `unavailable`。

现场环境若无法重跑，打开已提交的两个 CSV 和 PNG，按同一顺序讲解。
