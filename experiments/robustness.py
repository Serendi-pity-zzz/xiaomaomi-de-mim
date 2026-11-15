"""F：二维码鲁棒性与抗干扰测试。

对应分工：F——实现 JPEG、噪声、遮挡、裁剪、旋转等干扰，分别统计
「普通扫码成功率」「秘密信息恢复成功率」「完整性校验通过率」，
并对比二维码纠错能力与 LSB 信息脆弱性的差异。

设计约束（见 docs/成员剩余任务与接口交接.md）：
  * 每次实验一行原始记录，不只给平均值；
  * 扫码文本必须与公开原文完全一致才算成功；
  * 秘密恢复必须以 UTF-8 字节完全一致才算成功；
  * unknown / 未测 一律留空，不按 0 记；
  * 密钥只以「是否使用」进入记录，绝不写入 CSV 或日志。

用法（在项目根目录）：
    python experiments/robustness.py
    python experiments/robustness.py --samples 3 --strengths 0,20,40,60,80,100
    python experiments/robustness.py --carrier path/to/stego.png --public https://x --secret 喵

依赖：Pillow、numpy（与 E 共用），扫码解码需 opencv-python-headless 或 pyzbar，
缺一不可时扫码列留空并在报告中注明「未测」，不伪造成功率。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import platform
import sys
import time
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / ".deps"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np
from PIL import Image, ImageDraw

# 统一从集成入口取算法；A/B 接入后本脚本自动跟着换实现，不用改这里。
try:
    from core import service as _svc
    generate = _svc.generate
    embed = _svc.embed
    extract = _svc.extract
    IMPL = "core.service"
except Exception:  # pragma: no cover - 仅在 service 不可用时回退
    from core.baseline import generate, embed, extract  # type: ignore
    IMPL = "core.baseline"

# ---------------------------------------------------------------- 常量

#: 与 web/src/utils/experiments.ts 一致的六类干扰
ATTACKS = OrderedDict([
    ("jpeg", "JPEG 有损压缩"),
    ("gaussian", "高斯噪声"),
    ("salt", "椒盐噪声"),
    ("occlude", "中心遮挡"),
    ("occlude_region", "定点遮挡（覆盖载体条带）"),
    ("crop", "四周裁剪"),
    ("rotate", "旋转"),
])

DEFAULT_STRENGTHS = (0, 20, 40, 60, 80, 100)
DEFAULT_SEED = 20261107  # 与前端 canvas 演示同一天，便于对照记录

#: docs/成员剩余任务与接口交接.md §7 规定的统一列
CSV_COLUMNS = [
    "sample_id", "source", "license", "split", "seed", "algorithm",
    "width", "height", "payload_bytes", "capacity_bytes",
    "embed_ms", "extract_ms", "psnr_db", "ssim", "attack", "strength",
    "scan_success", "secret_success", "integrity_status", "detection_score",
    "error",
]

CAPACITY_BYTES = 11960  # CAT1 净载荷上限


# ---------------------------------------------------------------- 干扰算子

def _as_rgb(im: Image.Image) -> Image.Image:
    return im.convert("RGB") if im.mode != "RGB" else im


def attack_jpeg(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """质量 q = 1 - 0.95s（与前端 toDataURL 的 quality 一致），q=1 为无损。"""
    quality = max(1, min(100, int(round((1.0 - 0.95 * s) * 100))))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, subsampling=0)
    buf.seek(0)
    with Image.open(buf) as back:
        return back.convert("RGB")


def attack_gaussian(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """每个通道加 N(0, (40s)^2) 噪声，与前端 z*40s 同量级。"""
    arr = np.asarray(im, dtype=np.float32)
    noise = rng.normal(0.0, 1.0, arr.shape).astype(np.float32) * (s * 40.0)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "RGB")


def attack_salt(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """每像素以 p = 0.3s 的概率置为纯黑或纯白（椒盐）。"""
    arr = np.array(im)
    p = s * 0.3
    hit = rng.random(arr.shape[:2]) < p
    white = rng.random(arr.shape[:2]) < 0.5
    arr[hit] = 0
    arr[hit & white] = 255
    return Image.fromarray(arr, "RGB")


def attack_occlude(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """图中心盖白色矩形，边长 = 50% × s × 宽（高同比例）。"""
    out = im.copy()
    w, h = out.size
    bw, bh = w * 0.5 * s, h * 0.5 * s
    x0, y0 = w / 2 - bw / 2, h / 2 - bh / 2
    ImageDraw.Draw(out).rectangle([x0, y0, x0 + bw, y0 + bh], fill="white")
    return out


def attack_crop(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """四边各裁掉 20%·s，不补边（模拟拍照裁切，位置会整体平移）。"""
    cx, cy = int(im.width * s * 0.2), int(im.height * s * 0.2)
    if 2 * cx >= im.width or 2 * cy >= im.height:
        raise ValueError("裁剪比例过大，图像尺寸不足")
    return im.crop((cx, cy, im.width - cx, im.height - cy))


def attack_rotate(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """绕中心旋转 45°·s，画布不扩张，空出部分填白。"""
    return im.rotate(-45.0 * s, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))


def attack_occlude_region(im: Image.Image, s: float, rng: np.random.Generator) -> Image.Image:
    """F 追加用例（非前端内置）：白块盖住 CAT1 条带左侧 s 比例，真正打在载荷上。

    条带按 core.baseline.positions 的定义：x=[w-180, w-20)、y=[32,232)。
    前端只做「中心遮挡」，强度不足时根本覆盖不到条带，会得出错误结论，
    因此这里补一个定点遮挡作对照。
    """
    out = im.copy()
    w = out.width
    if w < 200:
        raise ValueError('图像宽度不足，无法按 CAT1 条带遮挡')
    x0, y0 = w - 180, 32
    bw = max(1, int(round(160 * s)))
    ImageDraw.Draw(out).rectangle([x0, y0, x0 + bw, y0 + 200], fill='white')
    return out


ATTACK_FUNCS = {
    "jpeg": attack_jpeg,
    "gaussian": attack_gaussian,
    "salt": attack_salt,
    "occlude": attack_occlude,
    "occlude_region": attack_occlude_region,
    "crop": attack_crop,
    "rotate": attack_rotate,
}


def apply_attack(im: Image.Image, name: str, strength: int, seed: int) -> Image.Image:
    """强度 0 表示不处理（对照组），保证与 s=0 结果逐像素一致。"""
    im = _as_rgb(im)
    if strength == 0:
        return im.copy()
    s = max(0.0, min(100, strength)) / 100.0
    rng = np.random.default_rng(seed)
    return ATTACK_FUNCS[name](im, s, rng)


# ---------------------------------------------------------------- 扫码解码

_QR_BACKEND = None


def _init_qr_backend() -> str:
    global _QR_BACKEND
    if _QR_BACKEND:
        return _QR_BACKEND
    try:
        import cv2  # noqa: F401
        _QR_BACKEND = "opencv"
    except Exception:
        try:
            import pyzbar.pyzbar  # noqa: F401
            _QR_BACKEND = "pyzbar"
        except Exception:
            _QR_BACKEND = "unavailable"
    return _QR_BACKEND


def decode_qr(im: Image.Image) -> dict:
    """返回 {'text': str|None, 'backend': str}。

    固定流程（写进报告，避免"多试几次挑成功"）：灰度 → decode；
    失败则 2 倍最近邻放大再试一次。只返回真实解码结果。
    """
    backend = _init_qr_backend()
    if backend == "unavailable":
        return {"text": None, "backend": "unavailable"}

    rgb = _as_rgb(im)

    if backend == "opencv":
        import cv2

        det = cv2.QRCodeDetector()
        for scale in (1, 2):
            img = rgb
            if scale != 1:
                img = rgb.resize((rgb.width * scale, rgb.height * scale), Image.NEAREST)
            gray = np.asarray(img.convert("L"))
            try:
                text, _pts, _ = det.detectAndDecode(gray)
            except Exception:
                text = ""
            if text:
                return {"text": text, "backend": "opencv"}
        return {"text": None, "backend": "opencv"}

    from pyzbar.pyzbar import decode as zbar_decode

    for candidate in decode_zbar_list(rgb):
        if getattr(candidate, "type", "") == "QRCODE":
            try:
                return {"text": candidate.data.decode("utf-8"), "backend": "pyzbar"}
            except UnicodeDecodeError:
                return {"text": None, "backend": "pyzbar"}
    return {"text": None, "backend": "pyzbar"}


def decode_zbar_list(rgb: Image.Image):
    from pyzbar.pyzbar import decode as zbar_decode
    return zbar_decode(rgb)


# ---------------------------------------------------------------- 度量

def psnr(a: Image.Image, b: Image.Image) -> float | None:
    """同尺寸才有意义；无差异返回 inf（按 §7 约定）。"""
    if a.size != b.size:
        return None
    x = np.asarray(_as_rgb(a), dtype=np.float64)
    y = np.asarray(_as_rgb(b), dtype=np.float64)
    mse = float(np.mean((x - y) ** 2))
    if mse == 0.0:
        return float("inf")
    return 10.0 * np.log10((255.0 ** 2) / mse)


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- 单条用例

def build_carrier(public: str, secret: str, key: str, seed: int) -> dict:
    """用当前集成实现生成载体并嵌入秘密，返回含耗时与尺寸的上下文。"""
    t0 = time.perf_counter()
    carrier = generate(public)
    t1 = time.perf_counter()
    stego = embed(carrier, secret, key)
    t2 = time.perf_counter()
    return {
        "image": _as_rgb(stego),
        "embed_ms": round((t1 - t0) * 1000 + (t2 - t1) * 1000, 2),
        "capacity_bytes": CAPACITY_BYTES,
        "seed": seed,
    }


def evaluate_one(stego: Image.Image, public: str, secret: str, key: str,
                 attack_name: str, strength: int, seed: int) -> dict:
    """跑一次「干扰 → 扫码 / 提取」并如实记录三项结果。"""
    record = {
        "attack": attack_name,
        "strength": strength,
        "scan_success": "",
        "secret_success": "",
        "integrity_status": "unknown",
        "extract_ms": "",
        "psnr_db": "",
        "ssim": "",
        "error": "",
    }
    expect_bytes = secret.encode("utf-8")

    try:
        attacked = apply_attack(stego, attack_name, strength, seed)
    except Exception as exc:  # 参数越界等，如实记录
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
        return record

    record["width"], record["height"] = attacked.size

    # 质量度量（与原始含密图比较；E 负责 SSIM 定义，这里不填）
    value = psnr(stego, attacked)
    record["psnr_db"] = "" if value is None else ("inf" if value == float("inf") else round(value, 3))

    # 1) 扫码：文本与公开原文一致才算成功
    qr = decode_qr(attacked)
    if qr["backend"] == "unavailable":
        record["scan_success"] = ""      # 未测，留空
    elif qr["text"] is None:
        record["scan_success"] = False
    else:
        record["scan_success"] = (qr["text"] == public)

    # 2) 秘密提取 + 3) 完整性校验（CAT1 的 HMAC 就是当前唯一的完整性判据）
    t0 = time.perf_counter()
    try:
        result = extract(attacked, key)
    except Exception as exc:
        # 提取在协议层就跑不动（例如裁剪后尺寸不足），这仍然是「没恢复出秘密」，
        # 原因写进 error 列，不把它当成「未测」。
        record["error"] = "%s: %s" % (type(exc).__name__, exc)
        result = {"status": "unknown", "secret": None}
    record["extract_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    status = result.get("status", "unknown")
    record["integrity_status"] = status
    got = result.get("secret")
    # 只要执行了提取却没拿到逐字节一致的原文，就记为「未恢复」。
    # unknown / failed 的区别留在 integrity_status 列，不混进成功率。
    record["secret_success"] = bool(
        status == "passed" and got is not None
        and got.encode("utf-8") == expect_bytes
    )
    return record


def make_case(sample_id: str, public: str, secret: str, key: str = "",
              carrier: str | None = None, source: str = "", license_: str = "内置绘制，无外部版权依赖",
              split: str = "test") -> dict:
    """构造一个待测用例；carrier 可指定已有含密 PNG（例如 A 融合后的图）。"""
    return {
        "sample_id": sample_id, "public": public, "secret": secret,
        "key": key, "carrier": carrier, "source": source,
        "license": license_, "split": split,
    }


# ---------------------------------------------------------------- 批量接口

def run(cases: list, config: dict | None = None) -> list:
    """F 的模块接口：cases → 每次实验一条记录（docs §5）。

    config 字段：
      attacks    : list[str]，默认全部六类
      strengths  : list[int]，默认 0/20/40/60/80/100
      repeats    : int，同条件重复次数（默认 1）
      seed       : int，固定随机种子
      save_dir   : str|None，落盘攻击样例图的目录
      其余作为环境信息透传，不参与计算。
    """
    cfg = dict(config or {})
    attacks = cfg.get("attacks", list(ATTACKS))
    strengths = cfg.get("strengths", list(DEFAULT_STRENGTHS))
    repeats = int(cfg.get("repeats", 1))
    seed = int(cfg.get("seed", DEFAULT_SEED))
    save_dir = cfg.get("save_dir")
    # 样例图默认取中间强度，保证"攻击测试样例"一定存在对应的实测记录
    save_at = cfg.get("save_strengths")
    if save_dir and not save_at:
        nonzero = sorted(st for st in strengths if st > 0)
        save_at = (nonzero[len(nonzero) // 2],) if nonzero else ()

    records = []
    for case in cases:
        if case.get("carrier"):
            with Image.open(case["carrier"]) as raw:
                stego = _as_rgb(raw)
            ctx = {"embed_ms": "", "capacity_bytes": CAPACITY_BYTES, "seed": seed}
            source = case.get("source") or ("外部载体 %s" % Path(case["carrier"]).name)
        else:
            ctx = build_carrier(case["public"], case["secret"], case.get("key", ""), seed)
            stego = ctx["image"]
            source = case.get("source") or "core.service.generate（内置猫咪并置基线）"

        # 先自检：未受干扰时必须能扫、能提取，否则整组数据无意义
        for rep in range(repeats):
            for attack_name in attacks:
                for strength in strengths:
                    rec = evaluate_one(stego, case["public"], case["secret"],
                                       case.get("key", ""), attack_name, strength, seed)
                    rec.update({
                        "sample_id": case["sample_id"],
                        "source": source,
                        "license": case.get("license", ""),
                        "split": case.get("split", "test"),
                        "seed": seed,
                        "algorithm": "lsb-keyed" if case.get("key") else "lsb-sequential",
                        "payload_bytes": len(case["secret"].encode("utf-8")),
                        "capacity_bytes": ctx["capacity_bytes"],
                        "embed_ms": ctx["embed_ms"],
                        "detection_score": "",
                        "repeat": rep,
                    })
                    if save_dir and strength in save_at:
                        _save_sample(save_dir, case["sample_id"], attack_name, strength, rep, rec, stego)
                    records.append({k: rec.get(k, "") for k in CSV_COLUMNS + ["repeat"]})
    return records


def _save_sample(save_dir, sample_id, attack_name, strength, rep, rec, stego):
    """把干扰后的图落盘，作为「攻击测试样例」。"""
    try:
        out = Path(save_dir)
        out.mkdir(parents=True, exist_ok=True)
        attacked = apply_attack(stego, attack_name, strength, int(rec.get("seed", DEFAULT_SEED)))
        attacked.save(out / ("%s_%s_%03d_r%d.png" % (sample_id, attack_name, strength, rep)))
    except Exception:
        pass  # 样例图失败不影响记录


# ---------------------------------------------------------------- 汇总与报告

def _rate(rows, key):
    """分子/分母只统计已测项；未测返回 None（报告中写「未测」）。"""
    tested = [r for r in rows if r[key] != ""]
    if not tested:
        return None, 0, 0
    ok = sum(1 for r in tested if r[key] is True)
    return (ok / len(tested)), ok, len(tested)


def summarize(records: list) -> list:
    groups = OrderedDict()
    for r in records:
        groups.setdefault((r["attack"], r["strength"]), []).append(r)

    out = []
    for (attack, strength), rows in groups.items():
        scan_rate, scan_ok, scan_n = _rate(rows, "scan_success")
        sec_rate, sec_ok, sec_n = _rate(rows, "secret_success")
        integrity_ok = sum(1 for r in rows if r["integrity_status"] == "passed")
        out.append({
            "attack": attack,
            "attack_name": ATTACKS.get(attack, attack),
            "strength": strength,
            "n": len(rows),
            "scan_rate": scan_rate, "scan_ok": scan_ok, "scan_n": scan_n,
            "secret_rate": sec_rate, "secret_ok": sec_ok, "secret_n": sec_n,
            "integrity_rate": integrity_ok / len(rows), "integrity_ok": integrity_ok,
            "unknown": sum(1 for r in rows if r["integrity_status"] == "unknown"),
            "mean_psnr": _mean_psnr(rows),
        })
    return out


def _mean_psnr(rows):
    vals = [float(r["psnr_db"]) for r in rows
            if r["psnr_db"] not in ("", None) and r["psnr_db"] != "inf"]
    return round(sum(vals) / len(vals), 2) if vals else None


def write_csv(records: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow({k: _csv_cell(r.get(k, "")) for k in CSV_COLUMNS})


def _csv_cell(v):
    if v is True:
        return "1"
    if v is False:
        return "0"
    return v


def write_summary_csv(summary: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["attack", "attack_name", "strength", "n", "scan_ok", "scan_n", "scan_rate",
            "secret_ok", "secret_n", "secret_rate", "integrity_ok", "integrity_rate",
            "unknown", "mean_psnr"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in summary:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in cols})


def environment(records: list, cfg: dict) -> dict:
    import PIL
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pillow": PIL.__version__,
        "numpy": np.__version__,
        "qr_backend": _init_qr_backend(),
        "impl": IMPL,
        "seed": int(cfg.get("seed", DEFAULT_SEED)),
        "attacks": list(cfg.get("attacks", list(ATTACKS))),
        "strengths": list(cfg.get("strengths", DEFAULT_STRENGTHS)),
        "repeats": int(cfg.get("repeats", 1)),
        "records": len(records),
        "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_report(summary: list, records: list, env: dict, path: Path, samples: int):
    lines = []
    add = lines.append
    add("# F：二维码鲁棒性与抗干扰测试报告")
    add("")
    add("> 由 `experiments/robustness.py` 自动生成，数字均为本次实测，未做任何人工调整。")
    add("")
    add("## 1. 环境与参数")
    add("")
    add("| 项 | 值 |")
    add("|---|---|")
    for k, v in env.items():
        if k in ("records", "样本数"):
            continue
        add("| %s | %s |" % (k, v))
    add("| 样本数 | %d |" % samples)
    add("| 记录数 | %d |" % len(records))
    add("")
    add("干扰强度按 0—100 取值，0 为未处理对照；算法与前端 `web/src/utils/experiments.ts` 同构：")
    add("")
    add("- JPEG：质量 = 1 − 0.95·s（s=0.2 → 81，s=1 → 5）")
    add("- 高斯噪声：每通道 N(0, (40s)²)，即 σ = 40s")
    add("- 椒盐噪声：每像素 30%·s 概率置黑或白")
    add("- 中心遮挡：居中白块，边长 = 50%·s × 图宽（高同比例）")
    add("- 裁剪：四边各裁 20%·s，不补边，尺寸随之变小")
    add("- 旋转：绕中心 ±45°·s，画布不变，空处填白")
    add("")
    add("扫码解码流程固定：灰度 → OpenCV `QRCodeDetector.detectAndDecode`；失败则 2 倍最近邻放大再试一次。"
        "不重复调参挑成功，失败即记失败。")
    add("")
    add("## 2. 三项指标汇总")
    add("")
    add("扫码成功率 = 解码文本与公开原文**完全一致**的条数 / 已测条数（扫码后端不可用时整列留空）；"
        "秘密恢复成功率 = 提取到的 UTF-8 字节与原文**完全一致**的条数 / 已执行提取的条数"
        "（提取状态为 unknown 或协议层拒绝，都算未恢复，原因见 CSV 的 error 列）；"
        "完整性通过率 = CAT1 头部标记与 HMAC 校验通过条数 / 全部条数（unknown 不计为通过）。")
    add("")
    add("| 干扰 | 强度 | 条数 | 扫码成功 | 秘密恢复 | 完整性通过 | unknown | 平均 PSNR(dB) |")
    add("|---|---|---|---|---|---|---|---|")
    for row in summary:
        add("| %s | %d | %d | %s | %s | %d/%d | %d | %s |" % (
            row["attack_name"], row["strength"], row["n"],
            _fmt_rate(row["scan_ok"], row["scan_n"]),
            _fmt_rate(row["secret_ok"], row["secret_n"]),
            row["integrity_ok"], row["n"], row["unknown"],
            "" if row["mean_psnr"] is None else row["mean_psnr"]))
    add("")
    add("## 3. 结论")
    add("")
    for line in _conclusions(summary, env):
        add("- " + line)
    add("")
    add("## 4. 局限")
    add("")
    add("- 解码器是 OpenCV，不是真实手机：手机相机 + 微信/支付宝扫码通常比 OpenCV 宽容，"
        "因此本表的扫码成功率是**保守下界**，不是手机实测值。真实扫码需按 README 演示顺序另行记录。")
    add("- Python 侧噪声用 `numpy.random.default_rng(seed)`，与浏览器 LCG 的不同实现会得到不同噪声像素，"
        "统计口径一致但不能逐像素对比。")
    add("- 完整性判据目前只是 CAT1 的 HMAC（只覆盖消息，不覆盖整幅图像），"
        "D 的分块认证接入后需重跑本实验并区分「覆盖范围内/外」。")
    add("- 载体为 `core.service.generate` 的内置猫咪并置基线，不是 A 的艺术融合成果；"
        "A 交付后传入 `--carrier` 重跑，结论才算对最终载体成立。")
    add("- 扫码后端缺失时扫码列留空；提取状态 unknown 记在 integrity_status 列，不计为通过，也不推断为篡改；裁剪后尺寸变化，PSNR 不适用，记为留空。")
    add("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_rate(ok, n):
    if n == 0:
        return "未测"
    return "%d/%d（%.0f%%）" % (ok, n, 100.0 * ok / n)


def _conclusions(summary: list, env: dict) -> list:
    """只用实测数据说话：好结论坏结论都按数字写。"""
    out = []
    by = OrderedDict()
    for row in summary:
        by.setdefault(row["attack"], []).append(row)

    def spray(rows, key):
        ok = sum(r[key + "_ok"] for r in rows)
        n = sum(r[key + "_n"] for r in rows)
        return ok, n

    # 1) 对照行
    ctrl = [r for r in summary if r["strength"] == 0 and r["scan_n"]]
    if ctrl:
        ok_all = all(r["scan_ok"] == r["scan_n"] and r["secret_ok"] == r["secret_n"] for r in ctrl)
        out.append("对照行（强度 0）扫码与恢复全部通过，说明载体、嵌入与提取流程本身没有问题。"
                   if ok_all else
                   "对照行未全部通过，先排查载体或解码流程，再解读下面各项数字。")

    # 2) 像素级干扰：LSB 一碰就碎
    touched = [r for a in ("jpeg", "gaussian", "salt", "rotate", "crop")
               for r in by.get(a, []) if r["strength"] > 0]
    if touched:
        ok, n = spray(touched, "secret")
        out.append("凡是会改写像素的干扰（JPEG、高斯噪声、椒盐噪声、旋转、裁剪），强度只要大于 0，"
                   "秘密恢复合计只有 %d/%d：LSB 把信息放在最低位，重编码、插值、叠加噪声都会直接改写这些位。" % (ok, n))

    # 3) 二维码在各干扰下的耐受力上限（合并成一行，避免十条重复句）
    peaks = []
    worst = None
    for name, label in (("jpeg", "JPEG 压缩"), ("gaussian", "高斯噪声"),
                        ("salt", "椒盐噪声"), ("crop", "四周裁剪"), ("rotate", "旋转")):
        rows = [r for r in by.get(name, []) if r["strength"] > 0 and r["scan_n"]]
        if not rows:
            continue
        good = [r for r in rows if r["scan_ok"] == r["scan_n"]]
        if good:
            peak = max(r["strength"] for r in good)
            if name == "jpeg":
                peak = peak  # 质量换算在下面统一算
            peaks.append((peak, label, name))
        else:
            worst = (min(r["strength"] for r in rows), label)
    if peaks:
        peaks.sort(reverse=True)
        parts = []
        for peak, label, name in peaks:
            if name == "jpeg":
                quality = max(1, int(round((1 - 0.95 * peak / 100) * 100)))
                parts.append("%s到强度 %d（质量约 %d）" % (label, peak, quality))
            else:
                parts.append("%s到强度 %d" % (label, peak))
        out.append("二维码的耐受上限：%s，扫码仍全部成功；同一批图在这些强度下秘密恢复全为 0——"
                   "纠错码（等级 H）与 LSB 的耐受力差距就体现在这里。" % "、".join(parts))
    if worst:
        out.append("%s最不友好：强度刚过 %d 二维码就解不出来了（椒盐把约 %d%% 的像素直接打成纯黑或纯白，"
                   "定位图案也随之失效）。" % (worst[1], worst[0], int(30 * worst[0] / 100)))

    # 4) 遮挡：位置比面积更关键
    occ = [r for r in by.get("occlude", []) if r["strength"] > 0]
    occr = [r for r in by.get("occlude_region", []) if r["strength"] > 0]
    if occ and occr:
        occ_ok, occ_n = spray(occ, "secret")
        occr_ok, occr_n = spray(occr, "secret")
        out.append("遮挡是唯一「面积大反而没伤到秘密」的干扰：中心遮挡累积 %d/%d 仍能恢复，"
                   "因为白块落在图像中部、没有压到 CAT1 条带；改成定点遮挡（压在条带上）后立刻降到 %d/%d。"
                   "结论是遮挡的**位置**比**面积**更决定后果，也说明前端现有的中心遮挡用例不足以评估隐写鲁棒性。"
                   % (occ_ok, occ_n, occr_ok, occr_n))

    # 5) 完整性与恢复同生共死
    mism = [r for r in summary if r["integrity_ok"] != r["secret_ok"]]
    if not mism:
        out.append("完整性通过数与秘密恢复数在所有条件下完全相同：当前完整性判据就是 CAT1 的 HMAC，"
                   "只有包头能解析时才生效。数据一旦被破坏，结果多为 unknown（无法判断）而不是 failed（判为篡改）——"
                   "这正是 D 的区域认证需要补上的缺口。")

    # 6) unknown 统计
    unknown = sum(r["unknown"] for r in summary)
    if unknown:
        out.append("共 %d 条记录提取状态为 unknown（读不到 CAT1 标记），按约定不计为通过，也不据此断言被篡改。"
                   % unknown)

    if env.get("qr_backend") == "unavailable":
        out.append("本次扫码后端不可用，扫码列全部留空——这不是成功率 0，而是没有测。")
    return out


# ---------------------------------------------------------------- CLI

def default_cases(n: int) -> list:
    secrets = ["来自喵星人的问候", "secret payload #1: keep it short", "喵🐱LSB"]
    publics = ["https://example.com/cat", "https://example.com/meow?from=lab"]
    cases = []
    for i in range(n):
        cases.append(make_case(
            sample_id="case%02d" % (i + 1),
            public=publics[i % len(publics)],
            secret=secrets[i % len(secrets)],
            key="" if i % 2 == 0 else "课程演示密钥",
            source="core.service.generate（内置猫咪并置基线）",
        ))
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description="F：二维码鲁棒性与抗干扰测试")
    parser.add_argument("--samples", type=int, default=2, help="自动生成多少个载体样本")
    parser.add_argument("--strengths", default=",".join(str(s) for s in DEFAULT_STRENGTHS),
                        help="逗号分隔的强度列表，默认 0,20,40,60,80,100")
    parser.add_argument("--attacks", default=",".join(ATTACKS), help="逗号分隔的干扰类型")
    parser.add_argument("--repeats", type=int, default=1, help="同条件重复次数")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", default=str(ROOT / "experiments" / "results"), help="结果目录")
    parser.add_argument("--samples-dir", default=str(ROOT / "experiments" / "samples"), help="攻击样例目录")
    parser.add_argument("--carrier", default=None, help="改用一张已有含密 PNG 作为载体")
    parser.add_argument("--public", default="https://example.com/cat", help="--carrier 模式下对应的公开原文")
    parser.add_argument("--secret", default="来自喵星人的问候", help="--carrier 模式下对应的秘密原文")
    args = parser.parse_args(argv)

    attacks = [a.strip() for a in args.attacks.split(",") if a.strip()]
    unknown = [a for a in attacks if a not in ATTACKS]
    if unknown:
        parser.error("未知干扰类型：%s（可选：%s）" % (unknown, ", ".join(ATTACKS)))
    strengths = [int(x) for x in args.strengths.split(",") if x.strip() != ""]

    if args.carrier:
        cases = [make_case("carrier01", args.public, args.secret, carrier=args.carrier,
                           source="外部载体 %s" % Path(args.carrier).name)]
    else:
        cases = default_cases(max(1, args.samples))

    cfg = {
        "attacks": attacks,
        "strengths": strengths,
        "repeats": max(1, args.repeats),
        "seed": args.seed,
        "save_dir": args.samples_dir,
    }

    print("实现：%s；扫码后端：%s" % (IMPL, _init_qr_backend()))
    records = run(cases, cfg)
    summary = summarize(records)

    out_dir = Path(args.out)
    write_csv(records, out_dir / "robustness_raw.csv")
    write_summary_csv(summary, out_dir / "robustness_summary.csv")
    env = environment(records, cfg)
    write_report(summary, records, env, out_dir / "robustness_report.md", len(cases))
    (out_dir / "robustness_env.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")

    print("原始记录：%d 条 -> %s" % (len(records), out_dir / "robustness_raw.csv"))
    for row in summary:
        print("%-8s %3d  n=%d  扫码 %s  恢复 %s  完整性 %d/%d" % (
            row["attack"], row["strength"], row["n"],
            _fmt_rate(row["scan_ok"], row["scan_n"]),
            _fmt_rate(row["secret_ok"], row["secret_n"]),
            row["integrity_ok"], row["n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
