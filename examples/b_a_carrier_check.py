#!/usr/bin/env python3
"""B × A 联调：在 A 的艺术融合载体上验证「公开扫码 + 秘密恢复」双链路。

输入是 A 的成员产出图（PR #1 的 outputs/qr_test/case_1_H_level_with_cat.png），
默认放在被 Git 忽略的 outputs/a_assets/ 下；也可用 --image 指定任意 A 生成的 PNG。
本脚本只读 A 的素材，不修改 A 的模块，也不依赖 numpy。

结果写入 examples/b_a_carrier_results.json（进仓库）：只记录 key_mode，
不写密钥值、不写秘密原文之外的内容。缺少 pyzbar 时扫码标为 unverified，
脚本返回非零，绝不把未验证项记成通过。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from core.steganography import CAPACITY_BYTES, capacity_bytes, embed, extract  # noqa: E402

SECRET = "来自喵星人的问候🐱"
KEY_MODES = (("empty", ""), ("keyed", "B-联调密钥"))
DEFAULT_IMAGE = ROOT / "outputs" / "a_assets" / "outputs__qr_test__case_1_H_level_with_cat.png"
DEFAULT_OUTPUT = ROOT / "examples" / "b_a_carrier_results.json"


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def _scan(image: Image.Image) -> dict:
    """pyzbar 程序解码；这是程序扫码，不是手机扫码，也不是 A 的正式验收。"""
    try:
        from pyzbar.pyzbar import decode
    except (ImportError, OSError) as exc:
        return {
            "status": "unverified",
            "texts": [],
            "detail": f"扫码解码库不可用（{type(exc).__name__}），未做扫码验证",
        }
    try:
        texts = [item.data.decode("utf-8", "replace") for item in decode(image)]
        return {
            "status": "passed" if texts else "failed",
            "texts": texts,
            "detail": "pyzbar 程序解码；不是手机扫码",
        }
    except Exception as exc:  # 解码库在损坏图上可能抛多种异常
        return {"status": "failed", "texts": [], "detail": f"解码异常：{type(exc).__name__}: {exc}"}


def _region_color_count(image: Image.Image, region: tuple[int, int, int, int]) -> int | None:
    x0, y0, w, h = region
    colors = image.crop((x0, y0, x0 + w, y0 + h)).getcolors(maxcolors=w * h + 1)
    return len(colors) if colors else None


def _changed_pixels_outside_region(
    before: Image.Image, after: Image.Image, region: tuple[int, int, int, int]
) -> int:
    """统计 CAT1 区域之外被改动的像素数；B 的实现应当让这个数恒为 0。"""
    if before.size != after.size:
        return -1
    raw_before, raw_after = before.tobytes(), after.tobytes()
    x0, y0, w, h = region
    width = before.width
    count = 0
    for offset in range(0, len(raw_before), 3):
        if raw_before[offset : offset + 3] == raw_after[offset : offset + 3]:
            continue
        pixel = offset // 3
        x, y = pixel % width, pixel // width
        if not (x0 <= x < x0 + w and y0 <= y < y0 + h):
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="在 A 的艺术融合载体上跑 B 的双链路联调")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="A 生成的 PNG 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="结果 JSON 路径")
    args = parser.parse_args()

    if not args.image.is_file():
        print(f"输入图不存在：{args.image}")
        print("请用 --image 指定 A 生成的 PNG；该素材来自 A 的 PR，未被本仓库收录。")
        return 2

    with Image.open(args.image) as opened:
        source = opened.convert("RGB")
    region = (source.width - 180, 32, 160, 200)
    raw = args.image.read_bytes()

    scan_before = _scan(source)
    color_count = _region_color_count(source, region)
    record = {
        "purpose": "B × A 联调：A 的艺术融合载体上，公开扫码与秘密恢复是否互相不破坏",
        "input": {
            "path": args.image.relative_to(ROOT).as_posix()
            if args.image.is_relative_to(ROOT)
            else args.image.as_posix(),
            "source": "A 的 PR #1 outputs/qr_test/case_1_H_level_with_cat.png（只读快照，不进仓库）",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": list(source.size),
            "mode": source.mode,
        },
        "cat1_region": list(region),
        "capacity_bytes": capacity_bytes(source, region),
        "cat1_region_distinct_colors": color_count,
        "cat1_region_note": (
            "该区域是纯白底（A 的 protected_mask 保护导致猫图不覆盖）。"
            "在此写 LSB 会留下明显统计特征，C 的检测模块容易命中；这是 CAT1 固定区域的固有代价，不是嵌入错误。"
            if color_count == 1
            else "该区域含多种颜色，统计特征需由 C 的检测模块另行评估。"
        ),
        "environment": {
            "python": platform.python_version(),
            "Pillow": _version("Pillow"),
            "qrcode": _version("qrcode"),
            "pyzbar": _version("pyzbar"),
        },
        "scan_before_embed": scan_before,
        "secret_bytes": len(SECRET.encode("utf-8")),
        "cases": [],
    }

    all_ok = scan_before["status"] == "passed" and record["capacity_bytes"] == CAPACITY_BYTES
    before_texts = scan_before["texts"]

    for key_mode, key in KEY_MODES:
        result = embed(source, SECRET, key, region)
        buffer = io.BytesIO()
        result["image"].save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        # 必须走真实的 PNG 写盘/重开路径，才能证明无损恢复
        with Image.open(io.BytesIO(png_bytes)) as saved:
            stego = saved.convert("RGB")
            scan_after = _scan(stego)
            recovered = extract(stego, key, region)

        outside = _changed_pixels_outside_region(source, result["image"], region)
        case_ok = (
            scan_after["status"] == "passed"
            and scan_after["texts"] == before_texts
            and recovered["status"] == "passed"
            and recovered["secret"] == SECRET
            and outside == 0
        )
        record["cases"].append(
            {
                "key_mode": key_mode,
                "png_bytes": len(png_bytes),
                "metadata": result["metadata"],
                "scan_after_embed": scan_after,
                "public_text_unchanged": scan_after["texts"] == before_texts,
                "secret_status": recovered["status"],
                "detail": recovered["detail"],
                "secret_recovered": recovered["secret"] == SECRET,
                "pixels_changed_outside_cat1_region": outside,
                "passed": case_ok,
            }
        )
        all_ok = all_ok and case_ok
        print(
            f"[{key_mode}] 扫码 {scan_after['status']} / 秘密 {recovered['status']} / "
            f"区域外改动 {outside} 像素 -> {'通过' if case_ok else '未通过'}"
        )

    record["overall"] = "passed" if all_ok else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"总体结论：{record['overall']}；结果写入 {args.output}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
