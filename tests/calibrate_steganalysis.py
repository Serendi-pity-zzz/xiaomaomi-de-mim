"""生成 C 模块的卡方检测校准文件 core/steganalysis_calibration.json。

用法（项目根目录）：

    python tests/calibrate_steganalysis.py

校准集与评估集分离：本脚本只用 CALIBRATION_PUBLICS 与 seed=100/101 的合成载体，
评估脚本 tests/eval_steganalysis.py 使用另一组公开文本与 seed=300/301。

优先在有裕量的间隔内取 0.5，否则取有效分离区间的中点。
分数重叠时停止校准，不覆盖旧文件。已知漏报（顺序嵌入的中文文本全容量）不参与阈值计算，
但会记录在文件中，报告里如实列出。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
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


def select_threshold(max_cover: float, min_detectable: float) -> tuple[float, str, float, float]:
    if not (math.isfinite(max_cover) and math.isfinite(min_detectable)
            and 0 <= max_cover < min_detectable <= 1):
        raise ValueError('校准失败：覆盖与含密分数没有有效分离区间，保留原校准文件')
    lower, upper = max_cover + 0.05, min_detectable
    if lower <= DEFAULT_THRESHOLD <= upper:
        return DEFAULT_THRESHOLD, '覆盖最大分数加 0.05 裕量后，区间内取 0.5。', lower, upper
    # 不按 0.05 网格舍入，避免窄区间舍入后落到区间外。
    threshold = (max_cover + min_detectable) / 2
    return threshold, '0.5 不在有裕量的区间内，取覆盖上界（开区间）与含密下界的中点。', max_cover, upper


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=CALIBRATION_PATH,
                        help='校准文件输出路径，默认替换正式校准文件')
    args = parser.parse_args()
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

    threshold, threshold_rule, lower, upper = select_threshold(max_cover, min_detectable)

    calibration = {
        'schema': _CALIBRATION_SCHEMA,
        'method': 'chi_square_bias_adjusted',
        'created': datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    print(f'写入 {args.output}')
    print(f'结构化覆盖样本 {len(cover_scores)} 个，最大分数 {max_cover:.4f}')
    print(f'可检测含密样本 {len(detectable)} 个，最小分数 {min_detectable:.4f}')
    print(f'已知漏报 {len(known_misses)} 个，分数 {[item["score"] for item in known_misses]}')
    print(f'阈值 {threshold:.2f}（可用区间 [{lower:.2f}, {upper:.2f}]）')
    print(f'calibration_id {calibration["calibration_id"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
