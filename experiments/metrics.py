"""E：图像质量评估指标——PSNR 与 SSIM 的统一定义。

对应分工：E——实现 PSNR、SSIM、容量、运行时间等指标计算。
对应接口（docs/成员剩余任务与接口交接.md §5）::

    evaluate(original, stego) -> dict   # psnr_db, ssim, width, height

本模块是 SSIM 定义的唯一来源（F 的 robustness.py 明确把 SSIM 留给 E）。
不依赖 scikit-image，只用 Pillow + numpy，便于在 .deps 中复现。

SSIM 约定（写进每条结果，避免"只报一个数不报口径"）：
  * 结构：Wang et al. 2004 的全局 SSIM；
  * 通道：RGB 先按 ITU-R 601-2 亮度公式转单通道灰度
          Y = 0.299 R + 0.587 G + 0.114 B（取值范围 0–255）；
  * 窗口：11×11 各向同性高斯窗，sigma = 1.5，归一化到和为 1；
  * 边界：reflect 填充，避免边缘因补零被低估；
  * 常数：C1 = (0.01×255)^2，C2 = (0.03×255)^2，data_range = 255；
  * 聚合：对整幅图的 SSIM 图取算术平均（global SSIM）。

PSNR 约定：
  * 在 RGB 三通道上按 8bit（MAX=255）计算；
  * MSE = mean((original - stego)^2)，PSNR = 10·log10(255^2 / MSE)；
  * 两图完全相同时 MSE=0，PSNR = inf（按 §7 约定，不写成 0）；
  * 尺寸不一致返回 None（PSNR 无意义），不猜测、不缩放。

用法：
    from experiments.metrics import evaluate
    m = evaluate(original_img, stego_img)
    # {'psnr_db': ..., 'ssim': ..., 'width': ..., 'height': ...,
    #  'mse': ..., 'ssim_config': {...}}

    PYTHONPATH=.deps python -m experiments.metrics --self-test
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image

# SSIM 固定口径——所有实验结果都用这一组参数，改任一值需升版本号并在报告说明。
SSIM_VERSION = "wang2004-global-v1"
SSIM_WINDOW = 11
SSIM_SIGMA = 1.5
SSIM_DATA_RANGE = 255.0
SSIM_C1 = (0.01 * SSIM_DATA_RANGE) ** 2
SSIM_C2 = (0.03 * SSIM_DATA_RANGE) ** 2

PSNR_MAX = 255.0


def ssim_config() -> dict:
    """返回本模块 SSIM 的完整口径，供 CSV 元数据与报告引用。"""
    return {
        "version": SSIM_VERSION,
        "structure": "Wang et al. 2004 global SSIM",
        "channel": "RGB -> gray (ITU-R 601-2: 0.299R+0.587G+0.114B)",
        "window": "%dx%d gaussian" % (SSIM_WINDOW, SSIM_WINDOW),
        "sigma": SSIM_SIGMA,
        "border": "reflect",
        "data_range": SSIM_DATA_RANGE,
        "C1": SSIM_C1,
        "C2": SSIM_C2,
        "aggregate": "arithmetic mean of SSIM map",
        "implementation": "numpy (no scikit-image)",
    }


def _as_rgb(im: Image.Image) -> Image.Image:
    return im.convert("RGB") if im.mode != "RGB" else im


def _gaussian_kernel1d(size: int, sigma: float) -> np.ndarray:
    """一维高斯核，归一化到和为 1。"""
    ax = np.arange(size, dtype=np.float64) - (size - 1) / 2.0
    kernel = np.exp(-(ax ** 2) / (2.0 * sigma ** 2))
    return kernel / kernel.sum()


def _gaussian_filter2d(arr: np.ndarray, size: int, sigma: float) -> np.ndarray:
    """可分离高斯滤波，边界 reflect；等价于 scipy.ndimage.gaussian_filter(mode='reflect')。"""
    pad = size // 2
    h, w = arr.shape
    k = _gaussian_kernel1d(size, sigma)

    # 横向：在左右 reflect 填充上取窗口，输出保持 (h, w)
    padded_x = np.pad(arr, ((0, 0), (pad, pad)), mode="reflect")
    tmp = np.zeros((h, w), dtype=np.float64)
    for i in range(size):
        tmp += k[i] * padded_x[:, i:i + w]

    # 纵向：在上下 reflect 填充上取窗口，输出保持 (h, w)
    padded_y = np.pad(tmp, ((pad, pad), (0, 0)), mode="reflect")
    out = np.zeros((h, w), dtype=np.float64)
    for i in range(size):
        out += k[i] * padded_y[i:i + h, :]
    return out


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    """RGB(uint8/float) -> 灰度 float64，ITU-R 601-2 亮度，范围 0–255。"""
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.float64)


def psnr_db(original: Image.Image, stego: Image.Image) -> float | None:
    """RGB 上的 PSNR(dB)。尺寸不一致返回 None；完全一致返回 inf。"""
    if original.size != stego.size:
        return None
    x = np.asarray(_as_rgb(original), dtype=np.float64)
    y = np.asarray(_as_rgb(stego), dtype=np.float64)
    mse = float(np.mean((x - y) ** 2))
    if mse == 0.0:
        return float("inf")
    return 10.0 * math.log10((PSNR_MAX ** 2) / mse)


def ssim(original: Image.Image, stego: Image.Image) -> float | None:
    """全局 SSIM，口径见模块 docstring / ssim_config()。尺寸不一致返回 None。"""
    if original.size != stego.size:
        return None
    x = _to_gray(np.asarray(_as_rgb(original), dtype=np.float64))
    y = _to_gray(np.asarray(_as_rgb(stego), dtype=np.float64))

    win, sig, L = SSIM_WINDOW, SSIM_SIGMA, SSIM_DATA_RANGE
    C1, C2 = SSIM_C1, SSIM_C2

    mu_x = _gaussian_filter2d(x, win, sig)
    mu_y = _gaussian_filter2d(y, win, sig)
    mu_x_sq = mu_x * mu_x
    mu_y_sq = mu_y * mu_y
    mu_xy = mu_x * mu_y

    sigma_x_sq = _gaussian_filter2d(x * x, win, sig) - mu_x_sq
    sigma_y_sq = _gaussian_filter2d(y * y, win, sig) - mu_y_sq
    sigma_xy = _gaussian_filter2d(x * y, win, sig) - mu_xy

    numerator = (2.0 * mu_xy + C1) * (2.0 * sigma_xy + C2)
    denominator = (mu_x_sq + mu_y_sq + C1) * (sigma_x_sq + sigma_y_sq + C2)
    ssim_map = numerator / denominator
    return float(np.mean(ssim_map))


def evaluate(original: Image.Image, stego: Image.Image) -> dict[str, Any]:
    """统一评测入口（§5 的 E 接口）。

    返回 psnr_db / ssim / width / height，并附 mse 与 ssim_config 便于复核口径。
    尺寸不一致时 psnr_db / ssim 为 None（调用方应写成空值或 unknown，不能写 0）。
    """
    if not isinstance(original, Image.Image) or not isinstance(stego, Image.Image):
        raise TypeError("original 与 stego 必须是 Pillow Image")

    if original.size != stego.size:
        return {
            "psnr_db": None,
            "ssim": None,
            "width": original.width,
            "height": original.height,
            "stego_width": stego.width,
            "stego_height": stego.height,
            "mse": None,
            "size_mismatch": True,
            "ssim_config": ssim_config(),
        }

    x = np.asarray(_as_rgb(original), dtype=np.float64)
    y = np.asarray(_as_rgb(stego), dtype=np.float64)
    mse = float(np.mean((x - y) ** 2))
    p = psnr_db(original, stego)
    s = ssim(original, stego)

    return {
        "psnr_db": p,
        "ssim": s,
        "width": original.width,
        "height": original.height,
        "stego_width": stego.width,
        "stego_height": stego.height,
        "mse": mse,
        "size_mismatch": False,
        "ssim_config": ssim_config(),
    }


def format_psnr(value: float | None) -> str:
    """写 CSV 用：inf -> 'inf'，None -> ''（未测），其余保留 3 位。"""
    if value is None:
        return ""
    if math.isinf(value):
        return "inf"
    return "%.3f" % value


def format_ssim(value: float | None) -> str:
    """写 CSV 用：None -> ''（未测），其余保留 6 位。"""
    return "" if value is None else "%.6f" % value


# ---------------------------------------------------------------- 自检

def _self_test() -> None:
    """无需 pytest 的基本自检：正常 / 边界 / 异常三类。"""
    a = Image.new("RGB", (64, 48), (120, 130, 140))

    # 正常：完全相同 -> PSNR inf、SSIM ~1
    m = evaluate(a, a.copy())
    assert math.isinf(m["psnr_db"]), m
    assert abs(m["ssim"] - 1.0) < 1e-6, m
    assert m["mse"] == 0.0 and not m["size_mismatch"]

    # 正常：轻微改动（LSB 翻转一个像素）-> 有限值且 SSIM 接近 1
    b = a.copy()
    b.putpixel((10, 10), (121, 130, 140))
    m2 = evaluate(a, b)
    assert m2["psnr_db"] is not None and math.isfinite(m2["psnr_db"]), m2
    assert 0.0 < m2["ssim"] <= 1.0, m2

    # 边界：尺寸不一致 -> None，不猜测
    c = Image.new("RGB", (32, 48), (120, 130, 140))
    m3 = evaluate(a, c)
    assert m3["psnr_db"] is None and m3["ssim"] is None and m3["size_mismatch"]

    # 边界：纯黑/纯白极端图
    blk = Image.new("RGB", (32, 32), (0, 0, 0))
    wht = Image.new("RGB", (32, 32), (255, 255, 255))
    m4 = evaluate(blk, wht)
    assert math.isfinite(m4["psnr_db"]) and m4["ssim"] < 1.0, m4

    # 异常：非 Image 输入
    try:
        evaluate("not-an-image", a)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("非 Image 输入应抛 TypeError")

    # 与已知解析值对照：全 0 与全 255，MSE=65025，PSNR=0dB
    m5 = evaluate(blk, wht)
    assert abs(m5["psnr_db"] - 0.0) < 1e-9, m5
    assert m5["ssim"] < 0.0 or m5["ssim"] < 1.0  # 灰度下 SSIM 有限且远小于 1

    print("metrics self-test OK:", ssim_config())


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="E：PSNR / SSIM 指标")
    ap.add_argument("--self-test", action="store_true", help="运行正常/边界/异常自检")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        ap.print_help()
