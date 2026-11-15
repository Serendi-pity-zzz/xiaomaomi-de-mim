"""C 模块实验用的确定性样本构造。

不提交外部图片，也不依赖网络：载体全部由程序绘制或由项目内置生成器产生，
因此任何人都能在相同 Pillow/qrcode 版本下复现。真实猫图/自然照片数据集由 E
统一提供，本文件不代表正式数据集，详见 docs/C_隐写统计检测说明.md。
"""
from __future__ import annotations

import base64
import math
import random
import string
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / '.deps', ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

CAT_CAPACITY_BYTES = 11960
CAT_REGION_WIDTH = 160
CAT_REGION_HEIGHT = 200

CALIBRATION_PUBLICS = [
    'https://example.com/cal/0',
    'https://example.com/cal/1?from=calibration&note=short',
    'https://example.com/cal/2/' + 'a' * 20,
    'https://example.com/cal/3/' + 'b' * 60,
    'https://example.com/cal/4/' + 'c' * 120,
    'https://example.com/cal/5/' + 'd' * 220,
    'https://example.com/cal/6/' + 'e' * 360,
    'https://example.com/cal/7/' + 'f' * 520,
    'https://example.com/cal/8/' + 'g' * 700,
    'https://example.com/cal/9/' + 'h' * 880,
    'https://example.com/cal/10/' + 'i' * 1040,
    'https://example.com/cal/11/' + 'j' * 1140,
]

EVALUATION_PUBLICS = [
    'https://example.org/eval/0',
    'https://example.org/eval/1?split=evaluation&note=held-out',
    'https://example.org/eval/2/' + 'k' * 30,
    'https://example.org/eval/3/' + 'l' * 90,
    'https://example.org/eval/4/' + 'm' * 150,
    'https://example.org/eval/5/' + 'n' * 260,
    'https://example.org/eval/6/' + 'o' * 400,
    'https://example.org/eval/7/' + 'p' * 560,
    'https://example.org/eval/8/' + 'q' * 740,
    'https://example.org/eval/9/' + 'r' * 920,
    'https://example.org/eval/10/' + 's' * 1080,
    'https://example.org/eval/11/' + 't' * 1150,
]

SYNTHETIC_KINDS = ('gradient', 'plasma', 'noise', 'flat', 'checker', 'radial', 'stripes')
EVALUATION_SYNTHETIC = tuple(
    (kind, seed)
    for seed in (300, 301)
    for kind in SYNTHETIC_KINDS
)


def cat_region(image: Image.Image) -> tuple[int, int, int, int]:
    """与 CAT1 载体一致的秘密区域（右侧 200px 猫咪条带内）。"""
    return image.width - 180, 32, CAT_REGION_WIDTH, CAT_REGION_HEIGHT


def builtin_cover(public: str) -> Image.Image:
    from core.baseline import generate

    return generate(public)


def synthetic_cover(kind: str, seed: int, size: tuple[int, int] = (260, 256)) -> Image.Image:
    """绘制结构化的确定性载体，不用外部图片。

    这些图只用于检验统计量的可控实验，不能代表自然照片分布。
    """
    width, height = size
    image = Image.new('RGB', size)
    pixels = image.load()
    rng = random.Random(seed)
    for y in range(height):
        for x in range(width):
            if kind == 'gradient':
                pixels[x, y] = ((x * 255) // width, (y * 255) // height, ((x + y) * 255) // (width + height))
            elif kind == 'plasma':
                pixels[x, y] = (
                    int(127 + 110 * math.sin((x + seed) / 17.0)),
                    int(127 + 110 * math.cos((y - seed) / 13.0)),
                    int(127 + 110 * math.sin((x + y) / 23.0)),
                )
            elif kind == 'noise':
                v = rng.randint(0, 255)
                pixels[x, y] = (v, v, v)
            elif kind == 'flat':
                pixels[x, y] = (177, 184, 215)
            elif kind == 'checker':
                dark = (30 + seed % 40, 40, 60)
                pixels[x, y] = dark if ((x // 16) + (y // 16)) % 2 else (250, 250, 250)
            elif kind == 'radial':
                dx, dy = x - width / 2, y - height / 2
                radius = math.hypot(dx, dy)
                pixels[x, y] = (
                    int(127 + 100 * math.sin(radius / 9.0 + seed)),
                    int(127 + 100 * math.cos(radius / 7.0)),
                    int(127 + 100 * math.sin((dx + dy) / 19.0)),
                )
            elif kind == 'stripes':
                pixels[x, y] = (
                    (x * 7 + seed) % 256,
                    (y * 5) % 256,
                    ((x ^ y) + seed) % 256,
                )
            else:
                raise ValueError(f'未知载体类型：{kind}')
    return image


_ASCII_ALPHABET = string.ascii_letters + string.digits + ' .,!?;:-_'
_CHINESE = '喵星人秘密实验室信息隐藏检测鲁棒性统计卡方'


def payload(kind: str, nbytes: int, seed: int = 2026) -> str:
    """返回 UTF-8 字节数恰为 nbytes 的文本载荷。"""
    if nbytes < 0:
        raise ValueError('载荷长度不能为负')
    rng = random.Random(seed)
    if kind == 'ascii':
        return ''.join(rng.choice(_ASCII_ALPHABET) for _ in range(nbytes))
    if kind == 'zh':
        text = ''
        while len((text + rng.choice(_CHINESE)).encode('utf-8')) <= nbytes:
            text += rng.choice(_CHINESE)
        padding = nbytes - len(text.encode('utf-8'))
        return text + ('a' * padding)
    if kind == 'base64':
        raw = bytes(rng.getrandbits(8) for _ in range(nbytes // 4 * 3))
        return base64.b64encode(raw).decode('ascii')[:nbytes]
    raise ValueError(f'未知载荷类型：{kind}')


def embed_cat1(image: Image.Image, text: str, key: str = '') -> Image.Image:
    from core.baseline import embed

    return embed(image, text, key)


def randomize_lsb(image: Image.Image, seed: int) -> Image.Image:
    """把全部 LSB 替换为随机比特；用于“LSB 已随机”的不可区分对照。"""
    rng = random.Random(seed)
    data = bytearray(image.convert('RGB').tobytes())
    for index in range(len(data)):
        data[index] = (data[index] & 0xFE) | rng.getrandbits(1)
    return Image.frombytes('RGB', image.size, bytes(data))


def is_valid_png_roundtrip(image: Image.Image) -> bool:
    """辅助自检：PNG 保存再打开后像素一致。"""
    import io

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    with Image.open(buffer) as reopened:
        return reopened.convert('RGB').tobytes() == image.convert('RGB').tobytes()
