# === 文件说明 ===
# 用途：计算同尺寸 RGB 图像的 PSNR、SSIM、均方误差和发生变化的通道数。
# 关联文件：由 experiments/g_compare.py 调用；tests/g_test_transport.py 验证相同图像的指标。
# 职责说明：这是 G 的实验辅助模块，未替代 E 的正式交付；指标定义见 docs/g_交接说明.md。
# === 原代码 ===
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

