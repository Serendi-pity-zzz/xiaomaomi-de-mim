"""PNG carries region and full mask; extraction never needs the original image."""
import base64
import hashlib
import json
import zlib
import numpy as np
from PIL import Image, PngImagePlugin
from .adaptive_steganography import mask_array, extract

FIELD = 'ruoai_gex1'


def save_png(path, embedded, protected_mask=None):
    image = embedded['image']
    mask = mask_array(image, protected_mask).astype('uint8').tobytes()
    metadata = dict(embedded['metadata'])
    if metadata['mask_sha256'] != hashlib.sha256(mask).hexdigest():
        raise ValueError('Saved mask differs from embedding mask')
    metadata['mask_encoding'] = 'zlib-base64-u8-row-major'
    metadata['mask'] = base64.b64encode(zlib.compress(mask)).decode('ascii')
    info = PngImagePlugin.PngInfo()
    info.add_text(FIELD, json.dumps(metadata, separators=(',', ':')))
    image.save(path, format='PNG', pnginfo=info)


def load_png(path):
    with Image.open(path) as source:
        if source.format != 'PNG' or source.mode != 'RGB':
            raise ValueError('Expected an RGB PNG')
        count = source.width * source.height
        if count > 4_000_000:
            raise ValueError('Image exceeds 4 million pixels')
        try:
            metadata = json.loads(source.info[FIELD])
            if (metadata['protocol'], metadata['position_version']) != ('GEX1', 1):
                raise ValueError('Unsupported bundle')
            if (metadata['width'], metadata['height']) != source.size:
                raise ValueError('Metadata dimensions do not match image')
            if metadata['mask_encoding'] != 'zlib-base64-u8-row-major':
                raise ValueError('Unsupported mask encoding')
            packed = base64.b64decode(metadata['mask'], validate=True)
            decoder = zlib.decompressobj()
            raw = decoder.decompress(packed, count + 1)
            if len(raw) != count or not decoder.eof or decoder.unused_data:
                raise ValueError('Invalid or oversized mask')
            if any(v not in (0, 1) for v in raw):
                raise ValueError('Invalid mask values')
            if hashlib.sha256(raw).hexdigest() != metadata['mask_sha256']:
                raise ValueError('Mask digest mismatch')
            region = tuple(metadata['region'])
        except (KeyError, TypeError, json.JSONDecodeError, zlib.error) as exc:
            raise ValueError('Missing or invalid GEX1 PNG metadata') from exc
        image = source.copy()
    mask = np.frombuffer(raw, dtype='uint8').reshape(image.height, image.width).astype(bool)
    return image, region, mask, metadata


def extract_png(path, key):
    image, region, mask, _ = load_png(path)
    return extract(image, key, region, protected_mask=mask)
