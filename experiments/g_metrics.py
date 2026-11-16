"""Local RGB image quality metrics used until the formal E module arrives."""
import numpy as np
from skimage.metrics import structural_similarity


def evaluate(original, stego):
    if original.mode != 'RGB' or stego.mode != 'RGB' or original.size != stego.size:
        raise ValueError('Metrics require matching RGB images')
    a, b = np.asarray(original), np.asarray(stego)
    mse = float(np.mean((a.astype(float) - b.astype(float))**2))
    if min(a.shape[:2]) < 7:
        raise ValueError('SSIM requires at least 7 pixels on both axes')
    return {'psnr_db': float('inf') if mse == 0 else float(10*np.log10(255**2/mse)),
            'ssim': float(structural_similarity(a, b, channel_axis=2, data_range=255, win_size=7)),
            'mse': mse, 'changed_channels': int(np.count_nonzero(a != b))}

