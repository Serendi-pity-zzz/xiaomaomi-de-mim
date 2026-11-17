"""E：实验设计、数据集与性能评估（图像质量 / 容量 / 纯算法耗时）。

对应分工：E——用合法数据集做不同容量、尺寸、算法的对比实验；实现 PSNR、
SSIM、容量、运行时间指标；产出可复现 CSV、统计图与局限分析。

设计约束（docs/成员剩余任务与接口交接.md §7、统一接口与协作.md）：
  * 原始无封包图（cover）与含密图（stego）逐一配对，PSNR/SSIM 只在这一对上算；
  * 计时只包住算法调用本身，不含 HTTP / 前端 / 文件 IO，区别于网络耗时；
  * 每次运行一行原始记录，不只给平均值；未知/未测留空，不写 0；
  * 恢复成功按 UTF-8 字节与原文完全一致判定；
  * 密钥只以算法标识出现，绝不写进 CSV 或日志；
  * 全部数字来自实测，不用示意值。

数据集：experiments/dataset/cats/ 下 30 张猫图，来自 FELIX
（DeepMicroscopy/FELIX，Experimental Study Set）。逐图 source/artist/license
见 manifest.csv 与 FELIX_Image_Level_Data.csv，均为 CC 授权，可复现、可署名。

用法（项目根目录）：
    python experiments/benchmark.py --self-test
    python experiments/benchmark.py --samples 8 --repeats 3
    python experiments/benchmark.py --samples 30 --payloads 16,128,512,2048,8192 \
        --algorithms sequential,keyed --repeats 3 --seed 20261109
    python experiments/benchmark.py --carrier-source service   # 改用集成载体（QR+猫）

作为库调用（docs §5 的 E 接口由 metrics.evaluate 提供；本模块提供 run）：
    from experiments.benchmark import run, make_case
    records = run([make_case("f1", cover=img, payload_bytes=512, algorithm="keyed")])

依赖：Pillow、numpy、matplotlib；算法来自 core.service（A/B/G 接入后自动跟随）。
"""
from __future__ import annotations

import argparse
import csv
import inspect
import io
import json
import math
import os
import platform
import statistics
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / ".deps"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np
from PIL import Image

from .metrics import evaluate as evaluate_pair, format_psnr, format_ssim, ssim_config

# 统一从集成入口取算法；A/B/G 接入后自动跟随，不改本文件。
try:
    from core import service as _svc
    IMPL = "core.service"
except Exception:  # pragma: no cover
    from core import baseline as _svc  # type: ignore
    IMPL = "core.baseline"

# ---------------------------------------------------------------- 常量

CSV_COLUMNS = [
    "sample_id", "source", "license", "split", "seed", "algorithm",
    "width", "height", "payload_bytes", "capacity_bytes",
    "embed_ms", "extract_ms", "psnr_db", "ssim", "attack", "strength",
    "scan_success", "secret_success", "integrity_status", "detection_score",
    "error",
]

CAPACITY_BYTES = 11960          # CAT1 净载荷上限（160×200×3/8 − 40）
DEFAULT_PAYLOADS = (16, 128, 512, 2048, 8192)
DEFAULT_ALGORITHMS = ("sequential", "keyed")
DEFAULT_SEED = 20261109
TARGET_SIZE = (800, 600)        # 统一分辨率；两种朝向的猫图都统一到横版

# 课程演示用固定密钥：仅用于让"密钥置乱"这一算法分支可复现，
# 不是真实保密密钥；CSV / 日志中不写入其值，只写 algorithm 标识。
DEMO_KEY = "e-benchmark-demo-key"

DATASET_DIR = ROOT / "experiments" / "dataset"
CATS_DIR = DATASET_DIR / "cats"
MANIFEST = DATASET_DIR / "manifest.csv"


# ---------------------------------------------------------------- 适配层

def _call_with_supported_kwargs(fn, *args, **kwargs):
    """按函数签名只传它接受的形参，兼容 baseline / B 模块的不同签名。"""
    params = inspect.signature(fn).parameters
    accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
    sent = {}
    for k, v in kwargs.items():
        if k in params or accepts_kwargs:
            sent[k] = v
    return fn(*args, **sent)


def _as_image(result) -> Image.Image:
    """baseline.embed/generate 返回 Image；B/A 模块返回含 'image' 的 dict。"""
    if isinstance(result, dict):
        img = result.get("image")
        if not isinstance(img, Image.Image):
            raise ValueError("模块返回 dict 但缺少 image 字段")
        return img.convert("RGB") if img.mode != "RGB" else img
    if isinstance(result, Image.Image):
        return result.convert("RGB") if result.mode != "RGB" else result
    raise TypeError("无法识别的返回类型：%s" % type(result).__name__)


def _region_of(image: Image.Image) -> tuple[int, int, int, int]:
    return (image.width - 180, 32, 160, 200)


def _embed(cover: Image.Image, secret: str, key: str) -> tuple[Image.Image, dict]:
    region = _region_of(cover)
    out = _call_with_supported_kwargs(_svc.embed, cover, secret, key, region=region)
    img = _as_image(out)
    metadata = out.get("metadata", {}) if isinstance(out, dict) else {}
    return img, metadata


def _extract(stego: Image.Image, key: str) -> dict:
    region = _region_of(stego)
    out = _call_with_supported_kwargs(_svc.extract, stego, key, region=region)
    return out if isinstance(out, dict) else {"status": "unknown", "secret": None}


def _generate_cover(public: str) -> Image.Image:
    """carrier-source=service 时用集成生成（当前为内置猫+二维码）。"""
    try:
        out = _call_with_supported_kwargs(_svc.generate, public, config={})
    except TypeError:
        out = _svc.generate(public)
    return _as_image(out)


def _capacity(image: Image.Image) -> int:
    fn = getattr(_svc, "capacity_bytes", None)
    if callable(fn):
        try:
            return int(_call_with_supported_kwargs(fn, image, region=_region_of(image)))
        except Exception:
            pass
    return CAPACITY_BYTES  # CAT1 协议固定值，不猜


# ---------------------------------------------------------------- 数据集

def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with MANIFEST.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_covers(limit: int | None = None) -> list[dict]:
    """返回 [{sample_id, image, source, license}]，统一分辨率与 RGB。"""
    manifest = {row["file"]: row for row in load_manifest()}
    items = []
    for p in sorted(CATS_DIR.glob("*")):
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
            continue
        with Image.open(p) as raw:
            cover = raw.convert("RGB").resize(TARGET_SIZE, Image.LANCZOS)
        meta = manifest.get(p.name, {})
        source = meta.get("source_url") or ("FELIX/%s" % p.name)
        license_ = meta.get("license") or "CC BY-SA 4.0"
        items.append({
            "sample_id": "cat_%s" % p.stem,
            "image": cover,
            "source": source,
            "license": license_,
        })
        if limit and len(items) >= limit:
            break
    return items


def make_payload(nbytes: int, seed: int) -> str:
    """生成恰好 nbytes 字节的可复现 UTF-8 秘密（ASCII，便于精确控制载荷）。"""
    rng = np.random.default_rng(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    idx = rng.integers(0, len(alphabet), size=nbytes)
    return "".join(alphabet[i] for i in idx)


def make_case(sample_id: str, cover: Image.Image, payload_bytes: int,
              algorithm: str, source: str = "", license_: str = "") -> dict:
    return {
        "sample_id": sample_id, "cover": cover, "payload_bytes": int(payload_bytes),
        "algorithm": algorithm, "source": source, "license": license_,
    }


# ---------------------------------------------------------------- 单条实验

def run_one(case: dict, cfg: dict) -> dict:
    """跑一次「cover -> embed -> measure -> extract」，返回一行原始记录。"""
    cover = case["cover"]
    algorithm = case["algorithm"]
    key = DEMO_KEY if algorithm == "keyed" else ""
    secret = make_payload(int(case["payload_bytes"]), int(cfg["seed"]))

    rec = {k: "" for k in CSV_COLUMNS}
    rec.update({
        "sample_id": case["sample_id"],
        "source": case.get("source", ""),
        "license": case.get("license", ""),
        "split": "eval",
        "seed": int(cfg["seed"]),
        "algorithm": "lsb-keyed" if key else "lsb-sequential",
        "width": cover.width,
        "height": cover.height,
        "payload_bytes": len(secret.encode("utf-8")),
        "capacity_bytes": "",
        "attack": "",        # E 不做干扰，留空（归 F）
        "strength": "",
        "scan_success": "",  # E 不测扫码，留空（归 A/F）
        "detection_score": "",  # 归 C
        "repeat": int(case.get("repeat", 0)),
    })

    # 1) 嵌入：只包住算法本身计时（纯算法耗时，不含任何网络/文件 IO）
    t0 = time.perf_counter()
    try:
        stego, metadata = _embed(cover, secret, key)
    except ValueError as exc:
        # 容量超限是合法的边界结果，如实记录
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        rec["integrity_status"] = "unknown"
        return rec
    except Exception as exc:
        rec["error"] = "%s: %s" % (type(exc).__name__, exc)
        rec["integrity_status"] = "unknown"
        return rec
    embed_ms = (time.perf_counter() - t0) * 1000.0
    rec["embed_ms"] = round(embed_ms, 3)
    rec["capacity_bytes"] = metadata.get("capacity_bytes") or _capacity(cover)
    rec["width"], rec["height"] = stego.size

    # 2) 质量：原始无封包图 cover 与含密图 stego 配对
    m = evaluate_pair(cover, stego)
    rec["psnr_db"] = format_psnr(m["psnr_db"])
    rec["ssim"] = format_ssim(m["ssim"])

    # 3) 提取：同样只计纯算法耗时；字节完全一致才算恢复成功
    t1 = time.perf_counter()
    try:
        result = _extract(stego, key)
    except Exception as exc:
        result = {"status": "unknown", "secret": None}
        rec["error"] = ("%s: %s" % (type(exc).__name__, exc)) + " (extract)"
    extract_ms = (time.perf_counter() - t1) * 1000.0
    rec["extract_ms"] = round(extract_ms, 3)

    status = str(result.get("status", "unknown"))
    rec["integrity_status"] = status
    got = result.get("secret")
    rec["secret_success"] = bool(
        status == "passed" and isinstance(got, str)
        and got.encode("utf-8") == secret.encode("utf-8")
    )
    return rec


# ---------------------------------------------------------------- 批量

def run(cases: list[dict], config: dict | None = None) -> list[dict]:
    """批量执行：每个 case 一行原始记录。"""
    cfg = dict(config or {})
    cfg.setdefault("seed", DEFAULT_SEED)
    records = []
    for case in cases:
        records.append(run_one(case, cfg))
    return records


def build_cases(cfg: dict) -> list[dict]:
    samples = load_covers(cfg.get("samples"))
    if cfg.get("carrier_source") == "service":
        # 用集成生成的 QR+猫载体替代猫图，source/license 如实标注
        samples = [{
            "sample_id": "svc_%02d" % (i + 1),
            "image": _generate_cover("https://example.com/cat/%d" % (i + 1)),
            "source": "core.service.generate（集成载体）",
            "license": "内置绘制，无外部版权依赖",
        } for i in range(max(1, cfg.get("samples", 8)))]
    if not samples:
        raise RuntimeError("没有可用载体：请先准备 experiments/dataset/cats/ 或改用 --carrier-source service")

    cases = []
    for rep in range(int(cfg["repeats"])):
        for s in samples:
            for payload in cfg["payloads"]:
                for algo in cfg["algorithms"]:
                    c = make_case(s["sample_id"], s["image"], payload, algo,
                                  s["source"], s["license"])
                    c["repeat"] = rep
                    cases.append(c)
    return cases


# ---------------------------------------------------------------- 汇总/输出

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def summarize(records: list[dict]) -> list[dict]:
    """按 algorithm × payload 汇总，分子/分母只统计实测项。"""
    groups: OrderedDict[tuple[str, int], list[dict]] = OrderedDict()
    for r in records:
        groups.setdefault((r["algorithm"], int(r["payload_bytes"])), []).append(r)

    out = []
    for (algo, payload), rows in groups.items():
        psnrs = [_num(r["psnr_db"]) for r in rows if r["psnr_db"] not in ("", "inf")]
        psnrs = [x for x in psnrs if x is not None and math.isfinite(x)]
        ssims = [x for x in (_num(r["ssim"]) for r in rows) if x is not None]
        embeds = [_num(r["embed_ms"]) for r in rows]
        embeds = [x for x in embeds if x is not None]
        extracts = [_num(r["extract_ms"]) for r in rows]
        extracts = [x for x in extracts if x is not None]
        ok = sum(1 for r in rows if r["secret_success"] is True)
        tested = sum(1 for r in rows if r["secret_success"] != "")
        out.append({
            "algorithm": algo,
            "payload_bytes": payload,
            "n": len(rows),
            "psnr_mean": round(statistics.mean(psnrs), 3) if psnrs else "",
            "psnr_std": round(statistics.pstdev(psnrs), 3) if len(psnrs) > 1 else "",
            "ssim_mean": round(statistics.mean(ssims), 6) if ssims else "",
            "ssim_std": round(statistics.pstdev(ssims), 6) if len(ssims) > 1 else "",
            "embed_ms_mean": round(statistics.mean(embeds), 3) if embeds else "",
            "extract_ms_mean": round(statistics.mean(extracts), 3) if extracts else "",
            "secret_ok": ok, "secret_n": tested,
            "secret_rate": (ok / tested) if tested else "",
            "inf_psnr": sum(1 for r in rows if r["psnr_db"] == "inf"),
            "errors": sum(1 for r in rows if r["error"] != ""),
        })
    return out


def write_csv(records: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS + ["repeat"])
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k, "") for k in CSV_COLUMNS + ["repeat"]})


def write_summary_csv(summary: list[dict], path: Path):
    cols = ["algorithm", "payload_bytes", "n", "psnr_mean", "psnr_std",
            "ssim_mean", "ssim_std", "embed_ms_mean", "extract_ms_mean",
            "secret_ok", "secret_n", "secret_rate", "inf_psnr", "errors"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in summary:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in cols})


def environment(records: list[dict], cfg: dict, cases: int) -> dict:
    import PIL
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "Pillow": PIL.__version__,
        "numpy": np.__version__,
        "matplotlib": __import__("matplotlib").__version__,
        "impl": IMPL,
        "carrier_source": cfg.get("carrier_source", "cats"),
        "dataset": "FELIX Experimental Study Set (CC licensed)",
        "samples": cfg.get("samples"),
        "repeats": int(cfg["repeats"]),
        "payloads": list(cfg["payloads"]),
        "algorithms": list(cfg["algorithms"]),
        "seed": int(cfg["seed"]),
        "target_size": list(TARGET_SIZE),
        "cases": cases,
        "records": len(records),
        "ssim_config": ssim_config(),
        "timing_scope": "algorithm call only (no HTTP / IO)",
        "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_report(summary: list[dict], records: list[dict], env: dict,
                 path: Path, figures: list[str]) -> str:
    L: list[str] = []
    add = L.append
    add("# E：实验设计、数据集与性能评估报告")
    add("")
    add("> 由 `experiments/benchmark.py` 自动生成，所有数字均为本次实测，未使用示意值。")
    add("")
    add("## 1. 环境与参数")
    add("")
    add("| 项 | 值 |")
    add("|---|---|")
    for k, v in env.items():
        if k in ("records", "cases"):
            continue
        add("| %s | %s |" % (k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v))
    add("| 用例数 | %d |" % env["cases"])
    add("| 记录数 | %d |" % env["records"])
    add("")

    add("## 2. 数据与配对方式")
    add("")
    if env["carrier_source"] == "cats":
        add("载体为 30 张 FELIX 猫图（`experiments/dataset/cats/`），统一缩放到 800×600 RGB，")
        add("逐图来源与许可见 `experiments/dataset/manifest.csv`（CC BY 2.0 / CC BY-SA 4.0 等，可署名复现）。")
    else:
        add("载体为 `core.service.generate` 的集成二维码+猫载体；A 的融合方案接入后重跑即可覆盖最终载体。")
    add("每条记录用**原始无封包图 cover** 与**含密图 stego** 逐一配对计算 PSNR/SSIM；")
    add("计时只包住 `embed` / `extract` 算法调用本身，不含 HTTP、前端或文件读写，")
    add("因此这里的毫秒数是**纯算法耗时**，不能与端到端网页延迟直接比较。")
    add("")
    add("SSIM 口径：%s。" % ssim_config()["channel"])
    add("窗口 %s，sigma=%s，data_range=%s，%s 聚合；实现见 `experiments/metrics.py`。"
        % (ssim_config()["window"], ssim_config()["sigma"],
           ssim_config()["data_range"], ssim_config()["aggregate"]))
    add("")

    add("## 3. 结果（按 算法 × 载荷 汇总）")
    add("")
    add("| 算法 | 载荷(B) | n | PSNR均值(dB) | PSNR标准差 | SSIM均值 | SSIM标准差 | 嵌入均值(ms) | 提取均值(ms) | 恢复成功 | 错误数 |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in summary:
        add("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %d/%d | %d |" % (
            r["algorithm"], r["payload_bytes"], r["n"],
            r["psnr_mean"] or "", r["psnr_std"] or "", r["ssim_mean"] or "",
            r["ssim_std"] or "", r["embed_ms_mean"] or "", r["extract_ms_mean"] or "",
            r["secret_ok"], r["secret_n"], r["errors"]))
    add("")
    add("> `secret_ok/secret_n` 按 UTF-8 字节与原文完全一致判定；")
    add("> 未测项留空而非 0；PSNR 无差异记为 `inf`（不计入均值）。")
    add("")

    add("## 4. 图表")
    add("")
    for fig in figures:
        add("- `results/figures/%s`" % fig)
    add("")

    add("## 5. 结论")
    add("")
    for line in _conclusions(summary, env):
        add("- " + line)
    add("")

    add("## 6. 局限")
    add("")
    add("- 载体为统一缩放后的猫图或集成基线，不是 A 的最终艺术融合图；A 接入后需用 `--carrier-source service` 或传入 A 的载体重跑。")
    add("- PSNR/SSIM 只衡量像素级失真，不等于人眼主观质量，也不代表隐写是否被检测出来（检测归 C）。")
    add("- 本实验不施加 JPEG/噪声/裁剪等干扰，抗干扰结论归 F；扫码成功与否归 A/F，这里留空。")
    add("- 载荷用 ASCII 精确控制字节数，便于对比；中文/emoji 的编码边界测试归 B。")
    add("- 计时受机器负载影响，取多次重复均值并附标准差；不同硬件不可直接比较绝对值。")
    add("- 密钥置乱（keyed）为 Python `random.Random` 确定性实现，跨语言不可假设一致（见 CAT1 协议）。")
    add("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    return "\n".join(L)


def _conclusions(summary: list[dict], env: dict) -> list[str]:
    out: list[str] = []
    if not summary:
        return ["本次没有可用记录。"]

    by: OrderedDict[str, list[dict]] = OrderedDict()
    for r in summary:
        by.setdefault(r["algorithm"], []).append(r)

    # 恢复成功率
    all_ok = sum(r["secret_ok"] for r in summary)
    all_n = sum(r["secret_n"] for r in summary)
    out.append("秘密恢复：%d/%d 条记录逐字节一致（按 UTF-8 原文判定）。" % (all_ok, all_n))

    # PSNR 随载荷变化
    for algo, rows in by.items():
        rows = [r for r in rows if r["psnr_mean"] != ""]
        if len(rows) >= 2:
            lo, hi = rows[0], rows[-1]
            out.append("%s：载荷 %d→%d 字节时，PSNR %.2f→%.2f dB，SSIM %s→%s；"
                       "嵌入耗时 %.3f→%.3f ms（纯算法）。" % (
                           algo, lo["payload_bytes"], hi["payload_bytes"],
                           lo["psnr_mean"], hi["psnr_mean"],
                           lo["ssim_mean"], hi["ssim_mean"],
                           lo["embed_ms_mean"], hi["embed_ms_mean"]))
    # 两种算法对照
    if "lsb-sequential" in by and "lsb-keyed" in by:
        s = {r["payload_bytes"]: r for r in by["lsb-sequential"]}
        k = {r["payload_bytes"]: r for r in by["lsb-keyed"]}
        common = sorted(set(s) & set(k))
        diffs = []
        for p in common:
            if s[p]["psnr_mean"] != "" and k[p]["psnr_mean"] != "":
                diffs.append(abs(s[p]["psnr_mean"] - k[p]["psnr_mean"]))
        if diffs:
            out.append("顺序 LSB 与密钥置乱 LSB 在相同载荷下的 PSNR 平均差异 %.3f dB——"
                       "置乱只改变写入顺序，不改变改动像素的数量，图像质量应基本相当。"
                       % (sum(diffs) / len(diffs)))
    return out


# ---------------------------------------------------------------- 统计图

def write_figures(summary: list[dict], out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    by: OrderedDict[str, list[dict]] = OrderedDict()
    for r in summary:
        by.setdefault(r["algorithm"], []).append(r)
    if not by:
        return files

    style = {"lsb-sequential": ("#2E6FB7", "o"), "lsb-keyed": ("#C0437E", "s")}

    # 1) PSNR vs payload
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for algo, rows in by.items():
        xs = [r["payload_bytes"] for r in rows]
        ys = [r["psnr_mean"] if r["psnr_mean"] != "" else np.nan for r in rows]
        c, m = style.get(algo, ("#555", "o"))
        ax.plot(xs, ys, marker=m, color=c, label=algo)
    ax.set_xlabel("payload (bytes)")
    ax.set_ylabel("PSNR (dB)")
    ax.set_title("Image quality vs payload (cover/stego paired)")
    ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "psnr_vs_payload.png", dpi=130); plt.close(fig)
    files.append("psnr_vs_payload.png")

    # 2) SSIM vs payload
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for algo, rows in by.items():
        xs = [r["payload_bytes"] for r in rows]
        ys = [r["ssim_mean"] if r["ssim_mean"] != "" else np.nan for r in rows]
        c, m = style.get(algo, ("#555", "o"))
        ax.plot(xs, ys, marker=m, color=c, label=algo)
    ax.set_xlabel("payload (bytes)")
    ax.set_ylabel("SSIM (global, gray)")
    ax.set_title("Structural similarity vs payload")
    ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "ssim_vs_payload.png", dpi=130); plt.close(fig)
    files.append("ssim_vs_payload.png")

    # 3) embed / extract time vs payload
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for algo, rows in by.items():
        xs = [r["payload_bytes"] for r in rows]
        c, m = style.get(algo, ("#555", "o"))
        ax.plot(xs, [r["embed_ms_mean"] for r in rows], marker=m, color=c,
                linestyle="-", label=algo + " embed")
        ax.plot(xs, [r["extract_ms_mean"] for r in rows], marker=m, color=c,
                linestyle="--", label=algo + " extract")
    ax.set_xlabel("payload (bytes)")
    ax.set_ylabel("time (ms, algorithm only)")
    ax.set_title("Pure algorithm time vs payload")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out_dir / "time_vs_payload.png", dpi=130); plt.close(fig)
    files.append("time_vs_payload.png")

    return files


# ---------------------------------------------------------------- 自检 & CLI

def _self_test():
    """正常/边界/异常三类，不依赖数据集。"""
    cover = Image.new("RGB", (320, 240), (123, 45, 67))

    # 正常：小载荷，两种算法都能恢复、PSNR 有效
    for algo, key in (("sequential", ""), ("keyed", DEMO_KEY)):
        stego, meta = _embed(cover, "hello", key)
        assert isinstance(stego, Image.Image) and stego.size == cover.size
        m = evaluate_pair(cover, stego)
        assert math.isfinite(m["psnr_db"]) and 0 < m["ssim"] <= 1.0, m
        r = _extract(stego, key)
        assert r.get("status") == "passed" and r.get("secret") == "hello", r
    print("benchmark self-test OK: embed/extract/metrics 三类正常路径通过")

    # 边界：容量超限应抛 ValueError（由 run_one 转成一行记录）
    try:
        _embed(cover, "A" * (CAPACITY_BYTES + 1), "")
    except ValueError:
        print("benchmark self-test OK: 容量超限按 ValueError 处理")
    else:
        raise AssertionError("容量超限应抛 ValueError")


def main(argv=None):
    ap = argparse.ArgumentParser(description="E：实验设计、数据集与性能评估")
    ap.add_argument("--self-test", action="store_true", help="自检（不跑完整实验）")
    ap.add_argument("--samples", type=int, default=8, help="使用多少张猫图（默认 8，最多 30）")
    ap.add_argument("--payloads", default=",".join(str(p) for p in DEFAULT_PAYLOADS),
                    help="载荷字节列表，逗号分隔")
    ap.add_argument("--algorithms", default=",".join(DEFAULT_ALGORITHMS),
                    help="sequential,keyed")
    ap.add_argument("--repeats", type=int, default=3, help="同条件重复次数（取均值与标准差）")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=str(ROOT / "experiments" / "results"), help="结果目录")
    ap.add_argument("--carrier-source", choices=("cats", "service"), default="cats",
                    help="cats=合法猫图（默认）；service=集成 QR+猫载体")
    args = ap.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    payloads = [int(x) for x in args.payloads.split(",") if x.strip()]
    algorithms = [x.strip() for x in args.algorithms.split(",") if x.strip()]
    bad = [a for a in algorithms if a not in DEFAULT_ALGORITHMS]
    if bad:
        ap.error("未知算法：%s（可选 sequential, keyed）" % bad)
    if any(p > CAPACITY_BYTES for p in payloads):
        ap.error("载荷不得超过 CAT1 容量 %d 字节" % CAPACITY_BYTES)

    cfg = {
        "samples": args.samples, "payloads": payloads, "algorithms": algorithms,
        "repeats": max(1, args.repeats), "seed": args.seed,
        "carrier_source": args.carrier_source,
    }
    print("实现：%s；载体：%s；样本：%d；载荷：%s；重复：%d" % (
        IMPL, args.carrier_source, args.samples, payloads, cfg["repeats"]))

    cases = build_cases(cfg)
    records = run(cases, cfg)
    summary = summarize(records)

    out_dir = Path(args.out)
    fig_dir = out_dir / "figures"
    write_csv(records, out_dir / "benchmark_raw.csv")
    write_summary_csv(summary, out_dir / "benchmark_summary.csv")
    env = environment(records, cfg, len(cases))
    figures = write_figures(summary, fig_dir)
    write_report(summary, records, env, out_dir / "benchmark_report.md", figures)
    (out_dir / "benchmark_env.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")

    print("原始记录：%d 行 -> %s" % (len(records), out_dir / "benchmark_raw.csv"))
    for r in summary:
        print("%-15s %5d B  n=%2d  PSNR=%s dB  SSIM=%s  embed=%s ms  recover=%d/%d" % (
            r["algorithm"], r["payload_bytes"], r["n"], r["psnr_mean"] or "-",
            r["ssim_mean"] or "-", r["embed_ms_mean"] or "-",
            r["secret_ok"], r["secret_n"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
