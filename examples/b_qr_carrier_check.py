"""用现有 MVP 二维码载体对 B 做双链路实测（不是 A 的艺术融合载体）。

两条链路分别记录，不互相代替：
1. 公开链路：pyzbar 真实解码二维码，比对公开原文；
2. 秘密链路：PNG 写盘重开后，用 B 模块恢复 UTF-8 原文。
另外逐字节确认 B 没有改动二维码区域与猫咪条带两侧保留区。

pyzbar 是可选依赖（pip install --target .deps pyzbar）。未安装时
扫码状态写 unverified，绝不记为通过。密钥值不写入结果文件。
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT))

from PIL import Image

from core.baseline import generate
from core.steganography import CAPACITY_BYTES, embed, extract


PUBLIC = "https://example.com/cat1"
SECRET = "来自喵星人的问候🐱"
KEY_MODES = (("empty", ""), ("keyed", "B-演示密钥"))
STRIPE_WIDTH = 200
CAT1_LEFT_INSET = 180
CAT1_RIGHT_INSET = 20
CAT1_Y = (32, 232)


def _scan(image: Image.Image) -> dict:
    """返回真实解码状态；缺少解码库时明确标 unverified。"""
    try:
        from pyzbar.pyzbar import decode
    except (ImportError, OSError) as exc:
        return {
            "status": "unverified",
            "decoded_texts": [],
            "detail": f"扫码解码库不可用（{type(exc).__name__}），未做扫码验证",
        }
    try:
        codes = [
            item.data.decode("utf-8")
            for item in decode(image.convert("RGB"))
            if item.type == "QRCODE"
        ]
    except Exception as exc:  # 解码器自身异常不能被当成"通过"
        return {"status": "failed", "decoded_texts": [], "detail": f"解码异常：{type(exc).__name__}"}
    return {
        "status": "passed" if PUBLIC in codes else "failed",
        "decoded_texts": codes,
        "detail": "解码文本与公开原文一致" if PUBLIC in codes else "未读到与公开原文一致的二维码",
    }


def _unchanged(before: Image.Image, after: Image.Image, box: tuple[int, int, int, int]) -> bool:
    return before.crop(box).tobytes() == after.crop(box).tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "b_qr_carrier_results.json",
        help="JSON 结果路径，默认写入 outputs/（被 Git 忽略）",
    )
    args = parser.parse_args()

    carrier = generate(PUBLIC).convert("RGB")
    qr_width = carrier.width - STRIPE_WIDTH
    region = (carrier.width - CAT1_LEFT_INSET, CAT1_Y[0], 160, CAT1_Y[1] - CAT1_Y[0])
    boxes = {
        "qr_region": (0, 0, qr_width, carrier.height),
        "stripe_left_margin": (qr_width, 0, region[0], carrier.height),
        "stripe_right_margin": (carrier.width - CAT1_RIGHT_INSET, 0, carrier.width, carrier.height),
    }

    from importlib.metadata import PackageNotFoundError, version

    import PIL

    def _package_version(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "missing"

    qrcode_version = _package_version("qrcode")
    pyzbar_version = _package_version("pyzbar")

    record = {
        "carrier": "core.baseline.generate（MVP 二维码 + 猫咪条带并置，非 A 的艺术融合图）",
        "public": PUBLIC,
        "secret_bytes": len(SECRET.encode("utf-8")),
        "region": list(region),
        "capacity_bytes": CAPACITY_BYTES,
        "image_size": list(carrier.size),
        "environment": {
            "python": platform.python_version(),
            "Pillow": PIL.__version__,
            "qrcode": qrcode_version,
            "pyzbar": pyzbar_version,
        },
        "scan_before_embed": _scan(carrier),
        "cases": [],
    }

    all_ok = record["scan_before_embed"]["status"] == "passed"
    for mode, key in KEY_MODES:
        result = embed(carrier, SECRET, key, region)
        stego = result["image"]
        protected = {name: _unchanged(carrier, stego, box) for name, box in boxes.items()}

        buffer = io.BytesIO()
        stego.save(buffer, format="PNG")
        buffer.seek(0)
        with Image.open(buffer) as reopened:
            recovered = extract(reopened, key, region)
            scan_after = _scan(reopened)

        case = {
            "key_mode": mode,
            "protected_regions_unchanged": protected,
            "png_roundtrip": True,
            "secret_status": recovered["status"],
            "secret_recovered": recovered["secret"] == SECRET if recovered["secret"] is not None else False,
            "scan_after_embed": scan_after,
        }
        record["cases"].append(case)
        case_ok = (
            all(protected.values())
            and case["secret_status"] == "passed"
            and case["secret_recovered"]
            and scan_after["status"] == "passed"
        )
        all_ok = all_ok and case_ok
        print(
            f"[{mode:5}] 二维码区域不变={protected['qr_region']} "
            f"条带边缘不变={protected['stripe_left_margin'] and protected['stripe_right_margin']} "
            f"秘密恢复={case['secret_status']}/{case['secret_recovered']} "
            f"扫码={scan_after['status']}"
        )

    record["overall"] = "passed" if all_ok else "failed_or_unverified"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果文件：{args.output}")
    print(f"总体结论：{record['overall']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
