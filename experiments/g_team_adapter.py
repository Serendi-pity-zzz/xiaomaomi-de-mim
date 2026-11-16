"""G experiment adapter. Frozen teammate sources remain byte-for-byte intact."""
import importlib.util
from pathlib import Path
import numpy as np
from PIL import Image
from core import adaptive_steganography as g
from core.g_png import save_png, extract_png

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'experiments' / 'g_reference'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, VENDOR / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

A = load('team_a', 'core/qr_generator.py')
B = load('team_b', 'core/steganography.py')
C = load('team_c', 'core/steganalysis.py')
F = load('team_f', 'experiments/robustness.py')
ALGORITHMS = ('B-sequential', 'B-keyed', 'G-keyed', 'G-sobel', 'G-variance')

def generate(public, cat_image, *, mode='texture-adapted'):
    """Two explicit carriers: submitted A, or a local A/G proposal.

    A's mask is retained as fusion_protected_mask. Only the texture-adapted
    proposal receives a steganography mask that allows the declared region.
    Never silently interpret the original A mask as an embedding mask.
    """
    result = A.generate(public, {'cat_image': cat_image, 'correction': 'H'})
    image = result['image'].copy()
    x, y, w, h = result['region']
    if mode == 'a-original':
        return {**result, 'carrier_version': 'A-submitted', 'public': public}
    if mode != 'texture-adapted':
        raise ValueError('Unknown carrier mode')
    if x < image.width - 200 or x + w > image.width or y + h > image.height:
        raise ValueError('A region is outside the safe right-hand strip')
    # The QR and quiet zone are copied exactly from A. Only declared payload
    # pixels receive the photo; B and G both operate on this same new cover.
    image.paste(cat_image.convert('RGB').resize((w, h), Image.Resampling.LANCZOS), (x, y))
    mask = np.ones((image.height, image.width), dtype=bool)
    mask[y:y+h, x:x+w] = False
    return {**result, 'image': image, 'protected_mask': mask,
            'fusion_protected_mask': result['protected_mask'].copy(),
            'carrier_version': 'A-G-private-1', 'public': public}

def embed(carrier, secret, key, algorithm='G-sobel'):
    image, region, mask = (carrier[k] for k in ('image', 'region', 'protected_mask'))
    if algorithm not in ALGORITHMS:
        raise ValueError('Unsupported algorithm')
    if algorithm.startswith('B-'):
        x, y, w, h = region
        if np.any(mask[y:y+h, x:x+w]):
            raise ValueError('B CAT1 cannot honor protection inside the payload region')
        return B.embed(image, secret, '' if algorithm == 'B-sequential' else key, region)
    return g.embed(image, secret, key, region, protected_mask=mask, method=algorithm[2:])

def extract(image, key, region, mask, algorithm):
    if algorithm not in ALGORITHMS:
        raise ValueError('Unsupported algorithm')
    try:
        if algorithm.startswith('B-'):
            return B.extract(image, '' if algorithm == 'B-sequential' else key, region)
        return g.extract(image, key, region, protected_mask=mask)
    except (ValueError, TypeError, OSError) as exc:
        return {'status': 'unknown', 'secret': None, 'detail': str(exc)}

def save(path, output, mask, algorithm):
    if algorithm.startswith('B-'):
        output['image'].save(path, format='PNG')
    else:
        save_png(path, output, mask)

def restore(path, key, algorithm):
    """G reconstructs region/mask from PNG; B retains CAT1's fixed geometry."""
    if algorithm.startswith('B-'):
        with Image.open(path) as im:
            return B.extract(im.convert('RGB'), '' if algorithm == 'B-sequential' else key)
    return extract_png(path, key)

def detect(image, region):
    # Use C's unchanged released threshold and calibration, no fit on test data.
    return C.analyze(image, region)

def scan(image, public):
    result = F.decode_qr(image)
    return None if result['backend'] == 'unavailable' else result['text'] == public
