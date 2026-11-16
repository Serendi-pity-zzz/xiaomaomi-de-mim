# === 文件说明 ===
# 用途：统一发现并执行 g_test_*.py 中的 G 测试，以及原项目 test*.py 回归测试。
# 关联文件：本目录的 g_test_core.py、g_test_alignment.py、g_test_research.py、g_test_transport.py。
# 运行方式：在项目根目录执行 python -B tests/g_run_tests.py；保留原有 tests/test_roundtrip.py。
# === 原代码 ===
"""Run renamed G tests and the existing project regressions from the repo root."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
if (ROOT / '.deps').is_dir():
    sys.path.insert(0, str(ROOT / '.deps'))

def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.discover(str(ROOT / 'tests'), pattern='g_test_*.py'),
        loader.discover(str(ROOT / 'tests'), pattern='test*.py'),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
