"""Regenerate a CAT1 PNG carrier and verify its UTF-8 payload."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(ROOT))

from PIL import Image

from core.steganography import embed, extract


SECRET = "你好🐱"


def make_carrier() -> Image.Image:
    """Create a synthetic RGB carrier of the minimum CAT1 dimensions."""
    carrier = Image.new("RGB", (240, 240))
    pixels = carrier.load()
    for y in range(carrier.height):
        for x in range(carrier.width):
            pixels[x, y] = (220 - x // 5, 226 - y // 6, 240 - (x + y) // 12)
    return carrier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("b_lsb_cat1.png"),
        help="PNG path; defaults to the example directory",
    )
    args = parser.parse_args()
    result = embed(make_carrier(), SECRET, key="", region=(60, 32, 160, 200))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result["image"].save(args.output, format="PNG")
    with Image.open(args.output) as saved:
        recovered = extract(saved, key="")
    if recovered["status"] != "passed" or recovered["secret"] != SECRET:
        raise RuntimeError("PNG roundtrip failed")
    print(f"PNG: {args.output}")
    print(f"status: {recovered['status']}")
    print(f"payload_bytes: {len(SECRET.encode('utf-8'))}")
    print(f"capacity_bytes: {result['capacity_bytes']}")


if __name__ == "__main__":
    main()
