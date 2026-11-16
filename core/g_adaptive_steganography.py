# === 文件说明 ===
# 用途：实现任务 G 的密钥位置排序、Sobel/局部方差自适应 LSB，以及容量检查、嵌入和提取。
# 关联文件：core/g_png.py 负责 PNG 参数保存；experiments/g_team_adapter.py 调用本模块参加对比实验。
# 相关测试：tests/g_test_core.py、tests/g_test_alignment.py；位置规则和 GEX1 协议说明见 docs/g_交接说明.md。
# === 原代码 ===
"""Private GEX1: RGB, protected masks, sequential/keyed/adaptive single-bit LSB.

No CAT1 compatibility or automatic format dispatch is claimed.
All bytes use big endian; each byte is embedded most-significant bit first.
"""
import hashlib
import hmac
import struct
import numpy as np

MAGIC = b'GEX1'
METHOD = 1
VERSION = 1
HEADER_BYTES = 44
PREFIX = struct.Struct('>4sBBHI')
METHODS = {'sequential': 0, 'keyed': 1, 'sobel': 2, 'variance': 3}


def mask_array(image, protected_mask=None):
    if image.width * image.height > 4_000_000:
        raise ValueError('Image exceeds 4 million pixels')
    if protected_mask is None:
        return np.zeros((image.height, image.width), dtype=bool)
    mask = np.asarray(protected_mask)
    if mask.shape != (image.height, image.width) or mask.dtype != np.bool_:
        raise ValueError('protected_mask must be a boolean array matching the image')
    return mask


def _validate(image, key, region):
    if image.mode != 'RGB':
        raise ValueError('Expected an RGB image')
    if not isinstance(key, str) or not key:
        raise ValueError('A nonempty string key is required')
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ValueError('region must be (x, y, width, height)')
    if any(type(v) is not int or not 0 <= v < 2**32 for v in region):
        raise ValueError('region requires unsigned 32-bit integers')
    x, y, w, h = region
    if not w or not h or x + w > image.width or y + h > image.height:
        raise ValueError('region is empty or outside the image')
    if w * h * 3 < HEADER_BYTES * 8:
        raise ValueError('region cannot hold the header')


def _context(image, region, protected_mask=None):
    # Row-major, one 0/1 byte per pixel. Preserves the original no-mask GEX1.
    mask_digest = hashlib.sha256(mask_array(image, protected_mask).astype('uint8').tobytes()).digest()
    return struct.pack('>6I', image.width, image.height, *region) + mask_digest


def capacity_bytes(image, key, region, *, protected_mask=None):
    _validate(image, key, region)
    mask = mask_array(image, protected_mask)
    x, y, w, h = region
    count = int(np.count_nonzero(~mask[y:y+h, x:x+w])) * 3
    if count < HEADER_BYTES * 8:
        raise ValueError('Unprotected region cannot hold the header')
    return count // 8 - HEADER_BYTES


def texture_scores(image, method='sobel'):
    """Integer high-seven-bit features, with replicate image-edge padding."""
    rgb = np.asarray(image).astype(np.int64) & 254
    gray = (77 * rgb[:, :, 0] + 150 * rgb[:, :, 1] + 29 * rgb[:, :, 2]) >> 8
    pad = np.pad(gray, 1, mode='edge')
    h, w = gray.shape
    cells = [pad[j:j+h, i:i+w] for j in range(3) for i in range(3)]
    if method == 'variance':
        return 9 * sum(c * c for c in cells) - sum(cells)**2
    if method != 'sobel':
        raise ValueError('Unknown texture method')
    gx = -cells[0] + cells[2] - 2*cells[3] + 2*cells[5] - cells[6] + cells[8]
    gy = -cells[0] - 2*cells[1] - cells[2] + cells[6] + 2*cells[7] + cells[8]
    return abs(gx) + abs(gy)


def positions(image, key, region, *, protected_mask=None, method='keyed', header_only=False):
    """Header is method-independent; adaptive payload depends only on high bits."""
    capacity_bytes(image, key, region, protected_mask=protected_mask)
    if method not in METHODS:
        raise ValueError('Unsupported method')
    mask = mask_array(image, protected_mask)
    context = _context(image, region, protected_mask)
    key_bytes = key.encode('utf-8')
    x0, y0, width, height = region
    candidates = [(x, y, c) for y in range(y0, y0 + height)
                  for x in range(x0, x0 + width) if not mask[y, x] for c in range(3)]

    def rank(position, domain):
        x, y, c = position
        digest = hmac.digest(key_bytes, domain + context + struct.pack('>IIB', x, y, c), 'sha256')
        return digest, y, x, c

    header = sorted(candidates, key=lambda p: rank(p, b'ruoai-g-v1/header'))[:HEADER_BYTES * 8]
    if header_only:
        return header, []
    reserved = set(header)
    payload = [p for p in candidates if p not in reserved]
    if method == 'keyed':
        payload.sort(key=lambda p: rank(p, b'ruoai-g-v1/payload'))
    elif method in ('sobel', 'variance'):
        scores = texture_scores(image, method)
        pixels = [(x, y) for x, y, c in candidates if c == 0]
        pixels.sort(key=lambda p: (-int(scores[p[1], p[0]]), p[1], p[0]))
        buckets = {p: min(3, i * 4 // len(pixels)) for i, p in enumerate(pixels)}
        payload.sort(key=lambda p: (buckets[p[:2]], rank(p, b'ruoai-g-v1/payload')))
    return header, payload


def _write(image, order, data):
    pixels = image.load()
    for i in range(len(data) * 8):
        x, y, channel = order[i]
        rgb = list(pixels[x, y])
        rgb[channel] = (rgb[channel] & 254) | ((data[i // 8] >> (7 - i % 8)) & 1)
        pixels[x, y] = tuple(rgb)


def _read(image, order, count):
    if count < 0 or count * 8 > len(order):
        raise ValueError('Read exceeds available positions')
    pixels = image.load()
    result = bytearray(count)
    for i in range(count * 8):
        x, y, channel = order[i]
        result[i // 8] |= (pixels[x, y][channel] & 1) << (7 - i % 8)
    return bytes(result)


def embed(image, secret, key, region, *, protected_mask=None, method='keyed'):
    capacity = capacity_bytes(image, key, region, protected_mask=protected_mask)
    if method not in METHODS:
        raise ValueError('Unsupported method')
    if not isinstance(secret, str):
        raise ValueError('secret must be a string')
    data = secret.encode('utf-8')
    if len(data) > capacity:
        raise ValueError(f'Payload exceeds capacity ({capacity} bytes)')
    prefix = PREFIX.pack(MAGIC, METHODS[method], VERSION, 0, len(data))
    tag = hmac.digest(key.encode('utf-8'), prefix + _context(image, region, protected_mask) + data, 'sha256')
    header, payload = positions(image, key, region, protected_mask=protected_mask, method=method)
    output = image.copy()
    _write(output, header, prefix + tag)
    _write(output, payload, data)
    return {'image': output, 'capacity_bytes': capacity,
            'metadata': {'protocol': 'GEX1', 'method': METHODS[method], 'position_version': VERSION,
                         'region': list(region), 'width': image.width, 'height': image.height,
                         'mask_sha256': hashlib.sha256(mask_array(image, protected_mask).astype('uint8').tobytes()).hexdigest(),
                         'header_bytes': HEADER_BYTES}}


def extract(image, key, region, *, protected_mask=None):
    capacity = capacity_bytes(image, key, region, protected_mask=protected_mask)
    header, _ = positions(image, key, region, protected_mask=protected_mask, header_only=True)
    raw = _read(image, header, HEADER_BYTES)
    magic, method, version, reserved, length = PREFIX.unpack(raw[:12])

    def result(status, detail, secret=None):
        return {'status': status, 'secret': secret, 'detail': detail}

    if magic != MAGIC:
        return result('unknown', 'No GEX1 marker: wrong key, damaged or unmarked image')
    if method not in METHODS.values() or (version, reserved) != (VERSION, 0):
        return result('unknown', 'Unsupported GEX1 configuration')
    if length > capacity:
        return result('failed', 'Invalid payload length')
    method_name = next(name for name, value in METHODS.items() if value == method)
    _, payload = positions(image, key, region, protected_mask=protected_mask, method=method_name)
    data = _read(image, payload, length)
    expected = hmac.digest(key.encode('utf-8'), raw[:12] + _context(image, region, protected_mask) + data, 'sha256')
    if not hmac.compare_digest(raw[12:], expected):
        return result('failed', 'Message authentication failed')
    try:
        secret = data.decode('utf-8')
    except UnicodeDecodeError:
        return result('failed', 'Invalid UTF-8 message')
    return result('passed', 'Message verified; whole-image integrity is not verified', secret)
