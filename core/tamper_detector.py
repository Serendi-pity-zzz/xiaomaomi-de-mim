"""Authenticated RGB-region integrity with authenticated block localization.

The JSON sidecar is generated AFTER steganographic embedding. It never changes
the image or the CAT1 carrier. A valid sidecar authenticates the block digests;
an invalid sidecar or an incorrect key cannot establish image tampering.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import struct
import uuid
from typing import Any

from PIL import Image

VERSION = "CAT-INTEGRITY-1"
ALGORITHM = "HMAC-SHA256+SHA256-BLOCKS"
MAX_PIXELS = 4_000_000
MAX_BLOCKS = 16_384
MAX_METADATA_BYTES = 4_000_000
_MANIFEST_DOMAIN = b"cat-integrity/manifest/v1\x00"
_BLOCK_DOMAIN = b"cat-integrity/rgb-block/v1\x00"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {
    "version", "algorithm", "image_id", "image", "region", "block_size", "blocks", "tag"
}


def _integer(value: Any) -> bool:
    return type(value) is int


def _key_bytes(key: str) -> bytes:
    if not isinstance(key, str) or not key:
        raise ValueError("完整性认证需要非空密钥；请使用独立的高熵密钥。")
    if len(key) > 4096:
        raise ValueError("密钥过长。")
    return key.encode("utf-8")


def _check_image(image: Image.Image) -> None:
    if not isinstance(image, Image.Image):
        raise ValueError("image 必须是 Pillow Image 对象。")
    if image.mode != "RGB":
        raise ValueError("仅接受 RGB 图像；请在生成载体时统一模式，验证时不要自动转换。")
    if image.width < 1 or image.height < 1 or image.width * image.height > MAX_PIXELS:
        raise ValueError(f"图像应为正尺寸，且不超过 {MAX_PIXELS} 像素。")
    image.load()


def _region(value: Any, size: tuple[int, int]) -> list[int]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("region 应为 (x, y, width, height)。")
    if not all(_integer(v) for v in value):
        raise ValueError("region 的四个值必须是整数，不能是布尔值。")
    x, y, width, height = value
    if min(x, y) < 0 or min(width, height) <= 0:
        raise ValueError("region 的原点非负，宽高必须大于零。")
    if x + width > size[0] or y + height > size[1]:
        raise ValueError("region 超出图像边界。")
    return list(value)


def _rectangles(region: list[int], block_size: int):
    x0, y0, width, height = region
    for y in range(y0, y0 + height, block_size):
        for x in range(x0, x0 + width, block_size):
            yield [x, y, min(block_size, x0 + width - x), min(block_size, y0 + height - y)]


def _check_grid(region: list[int], block_size: int) -> int:
    if not _integer(block_size) or not 1 <= block_size <= 4096:
        raise ValueError("block_size 必须是 1–4096 的整数。")
    count = ((region[2] + block_size - 1) // block_size) * (
        (region[3] + block_size - 1) // block_size
    )
    if count > MAX_BLOCKS:
        raise ValueError(f"分块超过 {MAX_BLOCKS} 个；请增大 block_size。")
    return count


def _canonical(manifest: dict) -> bytes:
    # Fixed UTF-8 JSON representation; there are no floating-point fields.
    return json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _block_digest(image: Image.Image, rect: list[int]) -> str:
    x, y, width, height = rect
    pixels = image.crop((x, y, x + width, y + height)).tobytes()
    return hashlib.sha256(_BLOCK_DOMAIN + struct.pack(">4I", *rect) + pixels).hexdigest()


def _unsigned(metadata: dict) -> dict:
    """Validate bounded, exact schema before trusting any coverage information."""
    if type(metadata) is not dict or set(metadata) != _FIELDS:
        raise ValueError("元数据缺失或字段不符合版本约定。")
    if metadata["version"] != VERSION or metadata["algorithm"] != ALGORITHM:
        raise ValueError("不支持的完整性元数据版本或算法。")
    image_id = metadata["image_id"]
    if not isinstance(image_id, str) or not 1 <= len(image_id) <= 128:
        raise ValueError("image_id 必须是 1–128 字符的标识。")
    image = metadata["image"]
    if type(image) is not dict or set(image) != {"width", "height", "mode"}:
        raise ValueError("图像描述无效。")
    width, height = image["width"], image["height"]
    if not _integer(width) or not _integer(height) or min(width, height) <= 0:
        raise ValueError("图像尺寸无效。")
    if width * height > MAX_PIXELS or image["mode"] != "RGB":
        raise ValueError("图像描述超出限制或不是 RGB。")
    region = _region(metadata["region"], (width, height))
    count = _check_grid(region, metadata["block_size"])
    blocks = metadata["blocks"]
    if type(blocks) is not list or len(blocks) != count:
        raise ValueError("分块列表缺失或数量不符。")
    for rect, block in zip(_rectangles(region, metadata["block_size"]), blocks):
        if type(block) is not dict or set(block) != {"region", "sha256"}:
            raise ValueError("分块字段无效。")
        if type(block["region"]) is not list or len(block["region"]) != 4:
            raise ValueError("分块坐标无效。")
        if not all(_integer(v) for v in block["region"]) or block["region"] != rect:
            raise ValueError("分块必须按行覆盖整个声明区域，不能重排、重叠或遗漏。")
        if not isinstance(block["sha256"], str) or not _HEX.fullmatch(block["sha256"]):
            raise ValueError("分块摘要无效。")
    if not isinstance(metadata["tag"], str) or not _HEX.fullmatch(metadata["tag"]):
        raise ValueError("认证标签无效。")
    unsigned = {name: metadata[name] for name in _FIELDS if name != "tag"}
    if len(_canonical(unsigned)) > MAX_METADATA_BYTES:
        raise ValueError("元数据过大。")
    return unsigned


def create_metadata(
    image: Image.Image,
    key: str,
    region: tuple[int, int, int, int] | None = None,
    block_size: int = 32,
    *,
    image_id: str | None = None,
) -> dict:
    """Create a JSON-serializable, authenticated sidecar for the FINAL RGB image.

    This does not store the key, alter the image, or embed anything into CAT1.
    A None region covers the full image. Coordinates are absolute, half-open.
    Store the sidecar associated with the expected image_id in a trusted place.
    """
    key_bytes = _key_bytes(key)
    _check_image(image)
    rect = _region(region if region is not None else (0, 0, *image.size), image.size)
    _check_grid(rect, block_size)
    if image_id is None:
        image_id = uuid.uuid4().hex
    if not isinstance(image_id, str) or not 1 <= len(image_id) <= 128:
        raise ValueError("image_id 必须是 1–128 字符的标识。")
    manifest = {
        "version": VERSION,
        "algorithm": ALGORITHM,
        "image_id": image_id,
        "image": {"width": image.width, "height": image.height, "mode": "RGB"},
        "region": rect,
        "block_size": block_size,
        "blocks": [
            {"region": block, "sha256": _block_digest(image, block)}
            for block in _rectangles(rect, block_size)
        ],
    }
    encoded = _canonical(manifest)
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("元数据过大。")
    manifest["tag"] = hmac.new(key_bytes, _MANIFEST_DOMAIN + encoded, hashlib.sha256).hexdigest()
    return manifest


def _unknown(reason: str, detail: str) -> dict:
    return {
        "status": "unknown", "coverage": None, "detail": detail,
        "reason": reason, "metadata_authenticated": False,
        "localization_available": False, "blocks": [],
    }


def verify(image: Image.Image, metadata: dict, key: str) -> dict:
    """Return passed/failed/unknown, authenticated coverage, and block results.

    The caller must select the expected image's sidecar from trusted storage.
    A MAC mismatch is UNKNOWN: wrong key and modified metadata are ambiguous.
    FAILED means authenticated expectations disagree with supplied RGB pixels
    or dimensions. It does not establish malicious intent or actor identity.
    """
    try:
        key_bytes = _key_bytes(key)
    except (ValueError, UnicodeError):
        return _unknown("key_unavailable", "缺少可用的非空密钥，无法建立认证结论。")
    try:
        unsigned = _unsigned(metadata)
        expected = hmac.new(
            key_bytes, _MANIFEST_DOMAIN + _canonical(unsigned), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, metadata["tag"]):
            return _unknown(
                "metadata_unverified", "元数据认证未通过：可能为密钥不符或元数据被修改；不能据此认定图像被篡改。"
            )
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        return _unknown("metadata_invalid", "缺少或无法解析有效的受认证元数据。")

    coverage = {
        "image_id": unsigned["image_id"],
        "region": list(unsigned["region"]),
        "image_size": [unsigned["image"]["width"], unsigned["image"]["height"]],
        "channels": "RGB", "bits_per_channel": 8,
        "pixel_bits": "all", "block_size": unsigned["block_size"],
        "full_image": unsigned["region"] == [0, 0, unsigned["image"]["width"], unsigned["image"]["height"]],
        "file_bytes_authenticated": False,
    }
    try:
        _check_image(image)
    except (ValueError, OSError, SyntaxError):
        result = _unknown("image_unreadable", "图像不可读、不是 RGB 或超出限制，未完成像素校验。")
        result.update(metadata_authenticated=True, coverage=coverage)
        return result
    result = {
        "coverage": coverage, "metadata_authenticated": True,
        "localization_available": False, "blocks": [],
    }
    if list(image.size) != coverage["image_size"]:
        return dict(result, status="failed", reason="dimensions_mismatch",
                    detail="图像尺寸与受认证记录不同；坐标系已变化，不输出分块定位。")
    try:
        blocks = [
            {"index": index, "region": list(block["region"]),
             "status": "passed" if hmac.compare_digest(
                 _block_digest(image, block["region"]), block["sha256"]
             ) else "failed"}
            for index, block in enumerate(unsigned["blocks"])
        ]
    except (ValueError, OSError, SyntaxError):
        return dict(result, status="unknown", reason="image_unreadable",
                    detail="读取像素失败，未完成校验。")
    failed_count = sum(block["status"] == "failed" for block in blocks)
    result.update(blocks=blocks, localization_available=True, failed_blocks=failed_count,
                  total_blocks=len(blocks))
    if failed_count:
        return dict(result, status="failed", reason="pixels_mismatch",
                    detail=f"认证区域内 {failed_count}/{len(blocks)} 个块与记录不符；定位精度为块，不表示块内每个像素都被修改。")
    return dict(result, status="passed", reason="covered_pixels_match",
                detail="声明覆盖区域的全部 RGB 像素与认证记录一致；不证明覆盖外区域、PNG 文件字节或消息可恢复。")
