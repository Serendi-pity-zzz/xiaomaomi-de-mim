"""Web adapters for the fixed CAT1 carrier and team algorithms."""
from .baseline import generate
from .steganography import embed as embed_cat1, extract
from .steganalysis import analyze


def embed(image, secret, key=''):
    return embed_cat1(image, secret, key)['image']


def detect(image, method='chi_square'):
    region = (image.width - 180, 32, 160, 200) if image.width >= 200 and image.height >= 240 else None
    return {'status': 'available', **analyze(image, region, method=method)}

from .tamper_detector import create_metadata, verify as verify_integrity

def authenticate_image(image, key, region=None, block_size=32, *, image_id=None):
    """Create a trusted integrity sidecar after all image edits are complete."""
    return create_metadata(
        image, key, region=region, block_size=block_size, image_id=image_id
    )


def check_image_integrity(image, metadata, key):
    """Verify pixels against the expected sidecar selected by the caller."""
    return verify_integrity(image, metadata, key)
