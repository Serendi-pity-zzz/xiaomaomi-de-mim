"""CAT1-compatible RGB LSB embedding and extraction.

The carrier region and packet layout are deliberately fixed. Changing either
requires a new format version. An explicit region confirms A's carrier uses
this CAT1 region; it cannot redefine the format.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import struct

from PIL import Image


MAGIC = b"CAT1"
HEADER_BYTES = 40
REGION_WIDTH = 160
REGION_HEIGHT = 200
CAPACITY_BYTES = REGION_WIDTH * REGION_HEIGHT * 3 // 8 - HEADER_BYTES


def _utf8(value: str, name: str) -> bytes:
    if not isinstance(value, str):
        raise TypeError(f"{name} 必须是字符串")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} 不是有效的 UTF-8 文本") from exc


def _region(
    image: Image.Image, region: tuple[int, int, int, int] | None
) -> tuple[int, int, int, int]:
    if not isinstance(image, Image.Image):
        raise TypeError("image 必须是 Pillow Image")
    if image.width < 200 or image.height < 240:
        raise ValueError("图像尺寸不符合 CAT1 载体协议")
    expected = (image.width - 180, 32, REGION_WIDTH, REGION_HEIGHT)
    if region is not None and region != expected:
        raise ValueError(f"CAT1 区域必须是 {expected}；其他区域需使用新版协议")
    return expected


def capacity_bytes(
    image: Image.Image, region: tuple[int, int, int, int] | None = None
) -> int:
    """Return the maximum UTF-8 payload length after the CAT1 header."""
    _region(image, region)
    return CAPACITY_BYTES


def positions(
    image: Image.Image,
    key: str = "",
    region: tuple[int, int, int, int] | None = None,
) -> list[tuple[int, int, int]]:
    """Return CAT1 bit positions in the exact legacy order."""
    x0, y0, width, height = _region(image, region)
    key_bytes = _utf8(key, "key")
    result = [
        (x, y, channel)
        for y in range(y0, y0 + height)
        for x in range(x0, x0 + width)
        for channel in range(3)
    ]
    if key_bytes:
        seed = int.from_bytes(hashlib.sha256(key_bytes).digest(), "big")
        random.Random(seed).shuffle(result)
    return result


def _read_bytes(pixels, bit_positions: list[tuple[int, int, int]], start: int, count: int) -> bytes:
    data = bytearray(count)
    for byte_index in range(count):
        value = 0
        first_bit = (start + byte_index) * 8
        for bit_index in range(8):
            x, y, channel = bit_positions[first_bit + bit_index]
            value = (value << 1) | (pixels[x, y][channel] & 1)
        data[byte_index] = value
    return bytes(data)


def embed(
    image: Image.Image,
    secret: str,
    key: str = "",
    region: tuple[int, int, int, int] | None = None,
) -> dict:
    """Embed UTF-8 text into a copy of image and return integration data."""
    fixed_region = _region(image, region)
    data = _utf8(secret, "secret")
    key_bytes = _utf8(key, "key")
    if len(data) > CAPACITY_BYTES:
        raise ValueError(f"秘密信息超过 CAT1 容量（最多 {CAPACITY_BYTES} UTF-8 字节）")

    packet = (
        MAGIC
        + struct.pack(">I", len(data))
        + hmac.new(key_bytes, data, "sha256").digest()
        + data
    )
    result = image.convert("RGB").copy()
    pixels = result.load()
    bit_positions = positions(result, key, fixed_region)
    for bit_index in range(len(packet) * 8):
        x, y, channel = bit_positions[bit_index]
        color = list(pixels[x, y])
        color[channel] = (color[channel] & 0xFE) | (
            (packet[bit_index // 8] >> (7 - bit_index % 8)) & 1
        )
        pixels[x, y] = tuple(color)

    return {
        "image": result,
        "capacity_bytes": CAPACITY_BYTES,
        "metadata": {
            "format": "CAT1",
            "algorithm": "lsb-keyed" if key_bytes else "lsb-sequential",
            "region": fixed_region,
            "payload_bytes": len(data),
        },
    }


def extract(
    image: Image.Image,
    key: str = "",
    region: tuple[int, int, int, int] | None = None,
) -> dict:
    """Return passed, failed, or unknown without relying on saved metadata."""
    fixed_region = _region(image, region)
    key_bytes = _utf8(key, "key")
    try:
        rgb = image.convert("RGB")
        pixels = rgb.load()
        bit_positions = positions(rgb, key, fixed_region)
        header = _read_bytes(pixels, bit_positions, 0, HEADER_BYTES)
        if header[:4] != MAGIC:
            return {
                "status": "unknown",
                "secret": None,
                "detail": "无有效标记：密钥错误、载体损坏或未嵌入",
            }
        payload_length = struct.unpack(">I", header[4:8])[0]
        if payload_length > CAPACITY_BYTES:
            return {"status": "failed", "secret": None, "detail": "长度字段损坏"}
        data = _read_bytes(pixels, bit_positions, HEADER_BYTES, payload_length)
    except OSError:
        return {"status": "unknown", "secret": None, "detail": "图像数据无法读取"}

    digest = hmac.new(key_bytes, data, "sha256").digest()
    if not hmac.compare_digest(header[8:40], digest):
        return {"status": "failed", "secret": None, "detail": "消息校验失败"}
    try:
        secret = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"status": "failed", "secret": None, "detail": "文本编码无效"}
    return {"status": "passed", "secret": secret, "detail": "消息完整；不代表整幅图像完整"}
