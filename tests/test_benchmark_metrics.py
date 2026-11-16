"""E：metrics.py 与 benchmark.py 的单元测试（正常 / 边界 / 异常）。

运行：python -m pytest tests/test_benchmark_metrics.py -q
若不装 pytest，也可直接 `python tests/test_benchmark_metrics.py` 走内置 runner。
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / ".deps"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from PIL import Image

from experiments import metrics
from experiments import benchmark


def _img(w=64, h=48, color=(100, 120, 140)):
    return Image.new("RGB", (w, h), color)


# ---------------------------------------------------------------- metrics

def test_metrics_identical_returns_inf_and_ssim_one():
    a = _img()
    m = metrics.evaluate(a, a.copy())
    assert math.isinf(m["psnr_db"])
    assert abs(m["ssim"] - 1.0) < 1e-6
    assert m["size_mismatch"] is False


def test_metrics_lsb_change_is_small_but_measurable():
    a = _img()
    b = a.copy()
    b.putpixel((3, 3), (101, 120, 140))
    m = metrics.evaluate(a, b)
    assert math.isfinite(m["psnr_db"]) and m["psnr_db"] > 0
    assert 0.0 < m["ssim"] <= 1.0


def test_metrics_size_mismatch_returns_none():
    m = metrics.evaluate(_img(64, 48), _img(32, 48))
    assert m["psnr_db"] is None and m["ssim"] is None
    assert m["size_mismatch"] is True
    assert metrics.format_psnr(None) == "" and metrics.format_ssim(None) == ""


def test_metrics_known_psnr_extremes():
    # 全黑 vs 全白：MSE=255^2 -> PSNR=0 dB
    m = metrics.evaluate(_img(color=(0, 0, 0)), _img(color=(255, 255, 255)))
    assert abs(m["psnr_db"] - 0.0) < 1e-9


def test_metrics_ssim_config_declares_window_channel_range():
    cfg = metrics.ssim_config()
    assert "gray" in cfg["channel"] and "11x11" in cfg["window"]
    assert cfg["data_range"] == 255.0


def test_metrics_bad_input_raises():
    try:
        metrics.evaluate("x", _img())  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("非 Image 输入应抛 TypeError")


# ---------------------------------------------------------------- benchmark

def test_embed_extract_roundtrip_both_algorithms():
    cover = _img(320, 240)
    for algo, key in (("sequential", ""), ("keyed", benchmark.DEMO_KEY)):
        stego, meta = benchmark._embed(cover, "喵星人🐱", key)
        assert stego.size == cover.size
        m = metrics.evaluate(cover, stego)
        assert math.isfinite(m["psnr_db"])
        r = benchmark._extract(stego, key)
        assert r.get("status") == "passed" and r.get("secret") == "喵星人🐱"


def test_wrong_key_does_not_recover():
    cover = _img(320, 240)
    stego, _ = benchmark._embed(cover, "secret", benchmark.DEMO_KEY)
    r = benchmark._extract(stego, "wrong-key")
    assert r.get("status") != "passed" or r.get("secret") != "secret"


def test_capacity_overflow_is_valueerror():
    cover = _img(320, 240)
    try:
        benchmark._embed(cover, "A" * (benchmark.CAPACITY_BYTES + 1), "")
    except ValueError:
        return
    raise AssertionError("容量超限应抛 ValueError")


def test_run_one_records_real_metrics_not_placeholder():
    cover = _img(320, 240)
    case = benchmark.make_case("unit", cover, 128, "sequential")
    rec = benchmark.run_one(case, {"seed": 123})
    assert rec["psnr_db"] not in ("", None)
    assert rec["ssim"] not in ("", None)
    assert float(rec["embed_ms"]) >= 0
    assert rec["secret_success"] is True
    assert rec["integrity_status"] == "passed"
    # 密钥值不得出现
    assert benchmark.DEMO_KEY not in str(rec)


def test_csv_columns_follow_protocol():
    required = ["sample_id", "source", "license", "split", "seed", "algorithm",
                "width", "height", "payload_bytes", "capacity_bytes",
                "embed_ms", "extract_ms", "psnr_db", "ssim", "attack", "strength",
                "scan_success", "secret_success", "integrity_status",
                "detection_score", "error"]
    assert benchmark.CSV_COLUMNS == required


# ---------------------------------------------------------------- runner
def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", t.__name__, repr(e))
    print("total=%d failed=%d" % (len(tests), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
