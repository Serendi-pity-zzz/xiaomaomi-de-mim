"""生成 C 模块的卡方检测校准文件 core/steganalysis_calibration.json。

用法（项目根目录）：

    python tests/calibrate_steganalysis.py

校准集与评估集分离：本脚本只用 CALIBRATION_PUBLICS 与 seed=100/101 的合成载体，
评估脚本 tests/eval_steganalysis.py 使用另一组公开文本与 seed=300/301。

阈值取“覆盖样本最大分数”与“可检测含密样本最小分数”的中点（最大间隔），
并四舍五入到 0.05。已知漏报（顺序嵌入的中文文本全容量）不参与阈值计算，
但会记录在文件中，报告里如实列出。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / '.deps', ROOT, ROOT / 'tests'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from core.steganalysis import (  # noqa: E402
    DEFAULT_CALIBRATION_FILENAME,
    DEFAULT_THRESHOLD,
    LIMITATIONS,
    _CALIBRATION_SCHEMA,
    analyze,
    calibration_id,
    environment_summary,
)
from steganalysis_data import (  # noqa: E402
    CAT_CAPACITY_BYTES,
    CALIBRATION_PUBLICS,
    cat_region,
    builtin_cover,
    embed_cat1,
    payload,
    synthetic_cover,
)

CALIBRATION_PATH = Path(__file__).resolve().parents[1] / 'core' / DEFAULT_CALIBRATION_FILENAME


def _round(value):
    return None if value is None else round(float(value), 6)


def _analyze(image, region):
    result = analyze(image, region, threshold=0.5)
    return {
        'score': _round(result.get('score')),
        'statistic': _round(result.get('statistic')),
        'pair_count': result.get('details', {}).get('pair_count'),
    }


def collect_covers() -> list[dict]:
    covers = []
    for index, public in enumerate(CALIBRATION_PUBLICS):
        image = builtin_cover(public)
        covers.append({
            'sample_id': f'cal-cover-cat-{index:02d}',
            'source': f'builtin_cat_qr:{index}',
            'kind': 'builtin_cat_qr',
            'width': image.width,
            'height': image.height,
            **_analyze(image, cat_region(image)),
        })
    for kind, seed in (('gradient', 100), ('plasma', 100), ('noise', 100), ('flat', 100),
                       ('checker', 101), ('radial', 101), ('stripes', 101), ('gradient', 101)):
        image = synthetic_cover(kind, seed)
        covers.append({
            'sample_id': f'cal-cover-{kind}-{seed}',
            'source': f'synthetic:{kind}',
            'kind': kind,
            'width': image.width,
            'height': image.height,
            **_analyze(image, cat_region(image)),
        })
    return covers


def collect_stegos(covers: list[dict]) -> list[dict]:
    stegos = []
    for index, public in enumerate(CALIBRATION_PUBLICS):
        image = builtin_cover(public)
        for condition, text, key, message_kind, known_miss in (
            ('sequential_ascii_full', payload('ascii', CAT_CAPACITY_BYTES, 1), '', 'ascii', False),
            ('keyed_chinese_full', payload('zh', CAT_CAPACITY_BYTES, 2), 'calibration-key', 'zh', False),
            ('sequential_chinese_full', payload('zh', CAT_CAPACITY_BYTES, 4), '', 'zh', True),
        ):
            stego = embed_cat1(image, text, key)
            stegos.append({
                'sample_id': f'cal-stego-cat-{index:02d}-{condition}',
                'source': f'builtin_cat_qr:{index}',
                'kind': 'builtin_cat_qr',
                'condition': condition,
                'algorithm': 'lsb-keyed' if key else 'lsb-sequential',
                'payload_bytes': len(text.encode('utf-8')),
                'capacity_bytes': CAT_CAPACITY_BYTES,
                'message_kind': message_kind,
                'position_independent': bool(key) or message_kind == 'ascii',
                'known_miss': known_miss,
                **_analyze(stego, cat_region(stego)),
            })
    for kind, seed in (('gradient', 100), ('plasma', 100), ('checker', 101), ('radial', 101)):
        image = synthetic_cover(kind, seed)
        text = payload('ascii', CAT_CAPACITY_BYTES, 3)
        stego = embed_cat1(image, text, 'calibration-key')
        stegos.append({
            'sample_id': f'cal-stego-{kind}-{seed}',
            'source': f'synthetic:{kind}',
            'kind': kind,
            'condition': 'keyed_ascii_full',
            'algorithm': 'lsb-keyed',
            'payload_bytes': len(text.encode('utf-8')),
            'capacity_bytes': CAT_CAPACITY_BYTES,
            'message_kind': 'ascii',
            'position_independent': True,
            **_analyze(stego, cat_region(stego)),
        })
    return stegos


def main() -> int:
    covers = collect_covers()
    stegos = collect_stegos(covers)
    structured_covers = [item for item in covers if not item.get('boundary_control')]
    cover_scores = [item['score'] for item in structured_covers if item['score'] is not None]
    if not cover_scores:
        raise SystemExit('校准失败：没有可用的覆盖样本分数')
    max_cover = max(cover_scores)
    detectable = [item['score'] for item in stegos
                  if item['position_independent'] and not item.get('known_miss')
                  and item['score'] is not None]
    if not detectable:
        raise SystemExit('校准失败：没有可检测的含密样本分数')
    min_detectable = min(detectable)
    known_misses = [item for item in stegos if item.get('known_miss')]

    lower = max_cover + 0.05
    upper = min_detectable
    if lower <= DEFAULT_THRESHOLD <= upper:
        threshold = DEFAULT_THRESHOLD
        threshold_rule = (
            '结构化覆盖样本最大分数加 0.05 裕量为下界，可检测含密样本最小分数为上界；'
            f'区间 [{lower:.2f}, {upper:.2f}] 内取可解释的 0.5，兼顾裕量与检出率。'
        )
    else:
        threshold = max(0.05, round(((max_cover + min_detectable) / 2.0) * 20) / 20.0)
        threshold_rule = (
            '0.5 不在校准间隔内，退化为覆盖上界与可检测下界的中点（0.05 网格）。'
        )

    calibration = {
        'schema': _CALIBRATION_SCHEMA,
        'method': 'chi_square_bias_adjusted',
        'created': date(2026, 11, 15).isoformat(),
        'threshold': threshold,
        'threshold_rule': threshold_rule,
        'threshold_interval': {'lower': _round(lower), 'upper': _round(upper)},
        'score_definition': (
            'score = P(χ²_k-1 >= r_adj)，其中 r 为经典值对卡方统计量，'
            'r_adj = max(0, r - 2N(b-0.5)^2)，b 为区域内 LSB 为 1 的比例。'
            'score 是检测分数，不是含密概率或严格 p 值。'
        ),
        'calibration_set': {
            'cover_samples': len(cover_scores),
            'stego_samples': len(stegos),
            'detectable_stego_samples': len(detectable),
            'known_miss_samples': len(known_misses),
            'max_cover_score': _round(max_cover),
            'min_detectable_stego_score': _round(min_detectable),
            'covers': covers,
            'stegos': stegos,
        },
        'environment': environment_summary(),
        'limitations': list(LIMITATIONS),
    }
    calibration['calibration_id'] = calibration_id(calibration)
    CALIBRATION_PATH.write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    print(f'写入 {CALIBRATION_PATH}')
    print(f'结构化覆盖样本 {len(cover_scores)} 个，最大分数 {max_cover:.4f}')
    print(f'可检测含密样本 {len(detectable)} 个，最小分数 {min_detectable:.4f}')
    print(f'已知漏报 {len(known_misses)} 个，分数 {[item["score"] for item in known_misses]}')
    print(f'阈值 {threshold:.2f}（可用区间 [{lower:.2f}, {upper:.2f}]）')
    print(f'calibration_id {calibration["calibration_id"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
