"""Local command line interface. Keys are read at runtime and never serialized."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import warnings
from pathlib import Path

from PIL import Image

from core.tamper_detector import MAX_METADATA_BYTES, MAX_PIXELS, create_metadata, verify


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 含重复字段。")
        result[key] = value
    return result


def load_metadata(path: Path) -> dict:
    with path.open("rb") as handle:
        data = handle.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError("元数据文件过大。")
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    if type(value) is not dict:
        raise ValueError("元数据必须是 JSON 对象。")
    return value


def load_png(path: Path) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.format != "PNG" or image.mode != "RGB":
                raise ValueError("仅接受 RGB PNG 原图，不自动转格式或颜色模式。")
            if image.width * image.height > MAX_PIXELS or image.n_frames != 1:
                raise ValueError("图像超过 400 万像素或为多帧 PNG。")
            image.load()
            return image.copy()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="D 模块：PNG 区域完整性认证与分块定位")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify"):
        p = sub.add_parser(command)
        p.add_argument("image", type=Path, help="最终含密 RGB PNG")
        p.add_argument("metadata", type=Path, help="独立 JSON 认证记录")
        p.add_argument("--key-env", help="读取密钥的环境变量名；省略则隐藏输入")
        if command == "create":
            p.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
            p.add_argument("--block-size", type=int, default=32)
            p.add_argument("--image-id", help="组长在可信存储中使用的图像标识")
    args = parser.parse_args(argv)
    if args.command == "create" and args.metadata.exists():
        print("认证记录已存在；为避免覆盖基准，请使用新的输出路径。", file=sys.stderr)
        return 2
    try:
        if args.key_env:
            key = os.environ.get(args.key_env, "")
            if not key:
                raise ValueError("指定环境变量未提供非空密钥。")
        else:
            key = getpass.getpass("完整性认证密钥（不会保存）：")
        image = load_png(args.image)
        if args.command == "create":
            metadata = create_metadata(image, key, args.region, args.block_size, image_id=args.image_id)
            # Exclusive creation prevents accidentally overwriting a trusted reference.
            with args.metadata.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(json.dumps({"status": "created", "image_id": metadata["image_id"],
                              "region": metadata["region"], "total_blocks": len(metadata["blocks"])},
                             ensure_ascii=False))
            return 0
        result = verify(image, load_metadata(args.metadata), key)
    except (ValueError, OSError, SyntaxError, EOFError, RecursionError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        if args.command == "create":
            print("生成失败：请检查 RGB PNG、非空密钥、区域、分块参数与输出路径。", file=sys.stderr)
            return 2
        result = {"status": "unknown", "coverage": None,
                  "detail": "输入不可读、元数据无效或密钥不可用，无法完成校验。",
                  "metadata_authenticated": False, "localization_available": False, "blocks": []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"passed": 0, "failed": 1, "unknown": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
