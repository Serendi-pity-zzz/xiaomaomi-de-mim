"""C 模块实测评估：卡方检测的混淆矩阵、误报/漏报与区域范围对比。

用法（项目根目录）：

    python tests/eval_steganalysis.py

评估集与校准集分离（不同公开文本、不同随机种子、不同载荷种子）。原始逐条结果
写入 outputs/steganalysis/eval_results.csv、rs_results.csv 和 summary.json，
汇总表写入 summary.md；outputs 被 Git 忽略，正式交付时按需保留。

本脚本只做实测，不修改其他成员模块；密钥值不写入任何输出文件。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / '.deps', ROOT, ROOT / 'tests'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from PIL import Image  # noqa: E402

from core.steganalysis import (  # noqa: E402
    DEFAULT_CALIBRATION_FILENAME,
    LIMITATIONS,
    analyze,
    environment_summary,
    load_calibration,
    rs_features,
)
from steganalysis_data import (  # noqa: E402
    CAT_CAPACITY_BYTES,
    EVALUATION_PUBLICS,
    EVALUATION_SYNTHETIC,
    builtin_cover,
    cat_region,
    embed_cat1,
    payload,
    randomize_lsb,
    synthetic_cover,
)

OUTPUT_DIR = ROOT / 'outputs' / 'steganalysis'
CALIBRATION_PATH = ROOT / 'core' / DEFAULT_CALIBRATION_FILENAME
KEYED_TEST_KEY = 'evaluation-key-not-logged'

CSV_FIELDS = [
    'sample_id', 'source', 'carrier', 'license', 'split', 'seed', 'algorithm',
    'width', 'height', 'payload_bytes', 'capacity_bytes', 'message_kind',
    'condition', 'method', 'analysis_scope', 'detection_statistic',
    'detection_score', 'detection_threshold', 'detection_decision',
    'pair_count', 'error',
]


def wilson_interval(success: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% 置信区间；分母为 0 时返回 (0, 1)。"""
    if total <= 0:
        return 0.0, 1.0
    p = success / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def percentage(success: int, total: int) -> str:
    if total <= 0:
        return 'n/a'
    low, high = wilson_interval(success, total)
    return f'{success / total:.1%} (95% CI {low:.1%}–{high:.1%})'


def _analyze_row(image, region) -> dict:
    """调用检测并把结果摊平为 CSV 字段。"""
    result = analyze(image, region, calibration_path=CALIBRATION_PATH)
    return {
        'method': result['method'],
        'analysis_scope': result['analysis_scope'],
        'detection_statistic': result['statistic'],
        'detection_score': result['score'],
        'detection_threshold': result['threshold'],
        'detection_decision': result['decision'],
        'pair_count': result.get('details', {}).get('pair_count'),
        'error': '',
    }


def build_cover_rows() -> tuple[list[dict], list[tuple[str, Image.Image, str]]]:
    rows = []
    images = []
    for index, public in enumerate(EVALUATION_PUBLICS):
        image = builtin_cover(public)
        sample_id = f'eval-cover-cat-{index:02d}'
        rows.append({
            'sample_id': sample_id,
            'source': f'builtin_cat_qr:{index}',
            'carrier': 'builtin_cat_qr',
            'license': 'generated',
            'split': 'evaluation',
            'seed': '',
            'algorithm': 'cover',
            'width': image.width,
            'height': image.height,
            'payload_bytes': '',
            'capacity_bytes': CAT_CAPACITY_BYTES,
            'message_kind': '',
            'condition': 'cover',
            **_analyze_row(image, cat_region(image)),
        })
        images.append((sample_id, image, 'builtin_cat_qr'))
    for kind, seed in EVALUATION_SYNTHETIC:
        image = synthetic_cover(kind, seed)
        sample_id = f'eval-cover-{kind}-{seed}'
        carrier = f'synthetic_{kind}'
        rows.append({
            'sample_id': sample_id,
            'source': f'synthetic:{kind}',
            'carrier': carrier,
            'license': 'generated',
            'split': 'evaluation',
            'seed': seed,
            'algorithm': 'cover',
            'width': image.width,
            'height': image.height,
            'payload_bytes': '',
            'capacity_bytes': CAT_CAPACITY_BYTES,
            'message_kind': '',
            'condition': 'cover',
            **_analyze_row(image, cat_region(image)),
        })
        images.append((sample_id, image, carrier))
    return rows, images


def build_stego_rows(covers: list[tuple[str, Image.Image, str]]) -> list[dict]:
    rows = []
    conditions = []
    for size in (64, 1024, 4096, 8192, 10240):
        conditions.append(('lsb-sequential', size, 'ascii', 1000 + size, '', 'seq_ascii'))
    for seed in (11, 12, 13):
        conditions.append(('lsb-sequential', CAT_CAPACITY_BYTES, 'ascii', seed, '', 'seq_ascii_full'))
        conditions.append(('lsb-keyed', CAT_CAPACITY_BYTES, 'ascii', seed, KEYED_TEST_KEY, 'keyed_ascii_full'))
        conditions.append(('lsb-sequential', CAT_CAPACITY_BYTES, 'zh', seed + 10, '', 'seq_zh_full'))
        conditions.append(('lsb-keyed', CAT_CAPACITY_BYTES, 'zh', seed + 10, KEYED_TEST_KEY, 'keyed_zh_full'))
    for sample_id, cover, carrier in covers:
        for algorithm, size, message_kind, seed, key, condition in conditions:
            text = payload(message_kind, size, seed)
            stego = embed_cat1(cover, text, key)
            rows.append({
                'sample_id': f'{sample_id}-{condition}-s{seed}-{size}',
                'source': sample_id,
                'carrier': carrier,
                'license': 'generated',
                'split': 'evaluation',
                'seed': seed,
                'algorithm': algorithm,
                'width': stego.width,
                'height': stego.height,
                'payload_bytes': len(text.encode('utf-8')),
                'capacity_bytes': CAT_CAPACITY_BYTES,
                'message_kind': message_kind,
                'condition': condition,
                **_analyze_row(stego, cat_region(stego)),
            })
    for kind, seed in EVALUATION_SYNTHETIC:
        cover = synthetic_cover(kind, seed)
        text = payload('ascii', CAT_CAPACITY_BYTES, 31)
        stego = embed_cat1(cover, text, KEYED_TEST_KEY)
        rows.append({
            'sample_id': f'eval-stego-{kind}-{seed}-keyed_ascii_full',
            'source': f'synthetic:{kind}',
            'carrier': f'synthetic_{kind}',
            'license': 'generated',
            'split': 'evaluation',
            'seed': seed,
            'algorithm': 'lsb-keyed',
            'width': stego.width,
            'height': stego.height,
            'payload_bytes': len(text.encode('utf-8')),
            'capacity_bytes': CAT_CAPACITY_BYTES,
            'message_kind': 'ascii',
            'condition': 'keyed_ascii_full',
            **_analyze_row(stego, cat_region(stego)),
        })
    return rows


def build_scope_rows(covers: list[tuple[str, Image.Image, str]]) -> list[dict]:
    """区域检测 vs 整图检测（同一全容量顺序载荷）。"""
    text = payload('ascii', CAT_CAPACITY_BYTES, 11)
    rows = []
    for sample_id, cover, carrier in covers:
        stego = embed_cat1(cover, text, '')
        for scope, region in (('region', cat_region(stego)), ('whole_image', None)):
            result = analyze(stego, region, calibration_path=CALIBRATION_PATH)
            rows.append({
                'sample_id': f'{sample_id}-seq_ascii_full-s11-{scope}',
                'source': sample_id,
                'carrier': carrier,
                'license': 'generated',
                'split': 'scope_comparison',
                'seed': 11,
                'algorithm': 'lsb-sequential',
                'width': stego.width,
                'height': stego.height,
                'payload_bytes': len(text.encode('utf-8')),
                'capacity_bytes': CAT_CAPACITY_BYTES,
                'message_kind': 'ascii',
                'condition': 'seq_ascii_full',
                'method': result['method'],
                'analysis_scope': result['analysis_scope'],
                'detection_statistic': result['statistic'],
                'detection_score': result['score'],
                'detection_threshold': result['threshold'],
                'detection_decision': result['decision'],
                'pair_count': result.get('details', {}).get('pair_count'),
                'error': '',
            })
    return rows


def build_boundary_rows() -> list[dict]:
    """LSB 已随机的对照：结构在、最低位被替换，与全量嵌入统计不可区分。"""
    rows = []
    for kind, seed in EVALUATION_SYNTHETIC[:10]:
        image = synthetic_cover(kind, seed)
        control = randomize_lsb(image, seed)
        rows.append({
            'sample_id': f'boundary-random-lsb-{kind}-{seed}',
            'source': f'synthetic:{kind}',
            'carrier': f'synthetic_{kind}',
            'license': 'generated',
            'split': 'boundary_control',
            'seed': seed,
            'algorithm': 'random-lsb-control',
            'width': control.width,
            'height': control.height,
            'payload_bytes': '',
            'capacity_bytes': CAT_CAPACITY_BYTES,
            'message_kind': '',
            'condition': 'random_lsb_control',
            **_analyze_row(control, cat_region(control)),
        })
    return rows


def build_rs_rows(covers: list[tuple[str, Image.Image, str]]) -> list[dict]:
    rows = []
    for sample_id, cover, _ in covers[:6]:
        for size in (0, 4096, 8192, 10240, CAT_CAPACITY_BYTES):
            text = payload('ascii', size, 11) if size else ''
            image = embed_cat1(cover, text, '') if size else cover
            features = rs_features(image, cat_region(image))
            suffix = 'cover' if size == 0 else f'seq_ascii_{size}'
            rows.append({
                'sample_id': f'{sample_id}-rs-{suffix}',
                'source': sample_id,
                'payload_bytes': size,
                'groups': features['pooled']['groups'],
                'd_m': features['pooled']['d_m'],
                'd_neg': features['pooled']['d_neg'],
                'r_m': features['pooled']['r_m'],
                's_m': features['pooled']['s_m'],
                'r_neg': features['pooled']['r_neg'],
                's_neg': features['pooled']['s_neg'],
            })
    return rows


def check_png_roundtrip(covers: list[tuple[str, Image.Image, str]]) -> list[dict]:
    checks = []
    text = payload('ascii', CAT_CAPACITY_BYTES, 11)
    for sample_id, cover, _ in covers[:4]:
        stego = embed_cat1(cover, text, '')
        buffer = io.BytesIO()
        stego.save(buffer, format='PNG')
        buffer.seek(0)
        with Image.open(buffer) as reopened:
            before = analyze(stego, cat_region(stego), calibration_path=CALIBRATION_PATH)
            after = analyze(reopened, cat_region(reopened), calibration_path=CALIBRATION_PATH)
        checks.append({
            'sample_id': sample_id,
            'before': before['score'],
            'after': after['score'],
            'same': before['score'] == after['score'],
        })
    return checks


def carrier_group(row: dict) -> str:
    source = row['source']
    if source.startswith('synthetic:'):
        return 'synthetic_' + source.split(':', 1)[1]
    return 'builtin_cat_qr'


def confusion_metrics(cover: dict, stego: dict) -> dict:
    """未知单独计数，二分类指标只使用已判定样本，同时披露判定覆盖率。"""
    fp, tp = cover['flagged'], stego['detected']
    unknown_cover, unknown_stego = cover['inconclusive'], stego['inconclusive']
    tn = cover['n'] - fp - unknown_cover
    fn = stego['n'] - tp - unknown_stego
    decided = tp + fn + fp + tn
    total = cover['n'] + stego['n']
    return {
        'tp': tp, 'fn': fn, 'fp': fp, 'tn': tn,
        'inconclusive_cover': unknown_cover, 'inconclusive_stego': unknown_stego,
        'accuracy_decided': (tp + tn) / decided if decided else None,
        'fpr_decided': fp / (fp + tn) if fp + tn else None,
        'fnr_decided': fn / (fn + tp) if fn + tp else None,
        'decision_coverage': decided / total if total else None,
    }


def summarize(cover_rows: list[dict], stego_rows: list[dict], scope_rows: list[dict],
              boundary_rows: list[dict], rs_rows: list[dict], calibration: dict) -> dict:
    def is_flagged(row):
        return row['detection_decision'] == 'suspicious'

    def is_inconclusive(row):
        return row['detection_decision'] == 'inconclusive'

    cover_groups = defaultdict(lambda: {'n': 0, 'flagged': 0, 'inconclusive': 0})
    for row in cover_rows:
        key = row.get('carrier') or carrier_group(row)
        cover_groups[key]['n'] += 1
        cover_groups[key]['flagged'] += int(is_flagged(row))
        cover_groups[key]['inconclusive'] += int(is_inconclusive(row))

    stego_groups = defaultdict(lambda: {'n': 0, 'detected': 0, 'inconclusive': 0})
    for row in stego_rows:
        if row['split'] != 'evaluation':
            continue
        key = (row['condition'], row.get('carrier') or carrier_group(row),
               row['algorithm'], row['payload_bytes'], row['message_kind'])
        stego_groups[key]['n'] += 1
        stego_groups[key]['detected'] += int(is_flagged(row))
        stego_groups[key]['inconclusive'] += int(is_inconclusive(row))

    scope_groups = defaultdict(lambda: {'n': 0, 'detected': 0, 'inconclusive': 0})
    for row in scope_rows:
        key = (row.get('carrier') or carrier_group(row), row['analysis_scope'])
        scope_groups[key]['n'] += 1
        scope_groups[key]['detected'] += int(is_flagged(row))
        scope_groups[key]['inconclusive'] += int(is_inconclusive(row))

    boundary = {'n': len(boundary_rows), 'flagged': sum(is_flagged(row) for row in boundary_rows)}

    rs_by_payload = defaultdict(list)
    for row in rs_rows:
        rs_by_payload[row['payload_bytes']].append(row['d_m'])

    cover_pair_counts = [row['pair_count'] for row in cover_rows if row.get('pair_count')]

    return {
        'calibration': {
            'path': CALIBRATION_PATH.relative_to(ROOT).as_posix(),
            'calibration_id': calibration['calibration_id'],
            'threshold': calibration['threshold'],
            'threshold_rule': calibration['threshold_rule'],
            'threshold_interval': calibration.get('threshold_interval'),
        },
        'evaluated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'environment': environment_summary(),
        'calibration_environment': calibration.get('environment'),
        'metric_notes': '混淆矩阵按载体和载荷条件分组，复用同类覆盖样本；未知单列。accuracy/fpr/fnr_decided 仅用已判定样本，结合 decision_coverage 阅读。TPR 为检出数/全部含密样本，含未知；1-TPR 是未检出率。内置猫区域重复，不能视为独立照片。',
        'covers': {
            key: {
                'n': value['n'],
                'flagged': value['flagged'],
                'inconclusive': value['inconclusive'],
                'fpr': value['flagged'] / value['n'] if value['n'] else None,
                'wilson95': wilson_interval(value['flagged'], value['n']),
            }
            for key, value in sorted(cover_groups.items())
        },
        'stego': [
            {
                'condition': key[0],
                'carrier': key[1],
                'algorithm': key[2],
                'payload_bytes': key[3],
                'message_kind': key[4],
                'n': value['n'],
                'detected': value['detected'],
                'inconclusive': value['inconclusive'],
                'tpr': value['detected'] / value['n'] if value['n'] else None,
                'wilson95': wilson_interval(value['detected'], value['n']),
                'confusion': confusion_metrics(cover_groups[key[1]], value),
            }
            for key, value in sorted(
                stego_groups.items(),
                key=lambda item: (item[0][0], item[0][1], item[0][3], item[0][2], item[0][4]),
            )
        ],
        'scope': [
            {
                'carrier': key[0],
                'analysis_scope': key[1],
                'n': value['n'],
                'detected': value['detected'],
                'inconclusive': value['inconclusive'],
                'tpr': value['detected'] / value['n'] if value['n'] else None,
            }
            for key, value in sorted(scope_groups.items())
        ],
        'boundary_control': {
            'n': boundary['n'],
            'flagged': boundary['flagged'],
            'flagged_rate': boundary['flagged'] / boundary['n'] if boundary['n'] else None,
            'note': 'LSB 已随机的对照；统计上与全量 LSB 替换不可区分，不计入覆盖样本误报率。',
        },
        'rs_d_m_by_payload': {
            str(payload_bytes): {
                'n': len(values),
                'mean': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
            }
            for payload_bytes, values in sorted(rs_by_payload.items())
        },
        'cover_pair_counts': {
            'n': len(cover_pair_counts),
            'min': min(cover_pair_counts) if cover_pair_counts else None,
            'max': max(cover_pair_counts) if cover_pair_counts else None,
        },
        'limitations': list(LIMITATIONS),
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, '') for field in fields})


def markdown_tables(summary: dict) -> str:
    lines = ['# C 模块实测汇总（自动生成）', '']
    calibration = summary['calibration']
    lines.append(f"- 校准文件：`{calibration['path']}`")
    lines.append(f"- calibration_id：`{calibration['calibration_id']}`")
    lines.append(f"- 阈值：{calibration['threshold']}；依据：{calibration['threshold_rule']}")
    lines.append(f"- 评估环境：{summary['environment']}")
    lines.append(f"- 指标口径：{summary['metric_notes']}")
    lines.append('')
    lines.append('## 覆盖样本（误报）')
    lines.append('')
    lines.append('| 载体 | 样本数 | 判为可疑 | 无法判定 | FPR |')
    lines.append('|---|---:|---:|---:|---|')
    for key, value in summary['covers'].items():
        rate = percentage(value['flagged'], value['n'])
        lines.append(f"| {key} | {value['n']} | {value['flagged']} | "
                     f"{value['inconclusive']} | {rate} |")
    lines.append('')
    lines.append('## 含密样本（检出率）')
    lines.append('')
    lines.append('| 条件 | 载体 | 算法 | 载荷字节 | 消息 | 样本数 | 检出 | 无法判定 | TPR |')
    lines.append('|---|---|---|---:|---|---:|---:|---:|---|')
    for item in summary['stego']:
        rate = percentage(item['detected'], item['n'])
        lines.append(f"| {item['condition']} | {item['carrier']} | {item['algorithm']} | "
                     f"{item['payload_bytes']} | {item['message_kind']} | {item['n']} | "
                     f"{item['detected']} | {item['inconclusive']} | {rate} |")
    lines.append('')
    lines.append('## 分条件混淆矩阵与准确率')
    lines.append('')
    lines.append('| 条件 | 载体 | 字节 | TP | FN | FP | TN | 未知（正常/含密） | 准确率¹ | 误报率¹ | 漏报率¹ | 判定覆盖率 |')
    lines.append('|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|')
    def rate(value):
        return 'n/a' if value is None else f'{value:.1%}'
    for item in summary['stego']:
        metrics = item['confusion']
        lines.append(
            f"| {item['condition']} | {item['carrier']} | {item['payload_bytes']} | "
            f"{metrics['tp']} | {metrics['fn']} | {metrics['fp']} | {metrics['tn']} | "
            f"{metrics['inconclusive_cover']}/{metrics['inconclusive_stego']} | "
            f"{rate(metrics['accuracy_decided'])} | {rate(metrics['fpr_decided'])} | "
            f"{rate(metrics['fnr_decided'])} | {rate(metrics['decision_coverage'])} |")
    lines.append('')
    lines.append('¹ 仅在已判定样本上计算；未知不算正确或负类。各行复用同类正常样本，不可跨行相加；低判定覆盖率下的高准确率不能代表整体能力。')
    lines.append('')
    lines.append('## 区域 vs 整图（全容量顺序 ASCII）')
    lines.append('')
    lines.append('| 载体 | 分析范围 | 样本数 | 检出 | 无法判定 | TPR |')
    lines.append('|---|---|---:|---:|---:|---|')
    for item in summary['scope']:
        rate = percentage(item['detected'], item['n'])
        lines.append(f"| {item['carrier']} | {item['analysis_scope']} | {item['n']} | "
                     f"{item['detected']} | {item['inconclusive']} | {rate} |")
    lines.append('')
    lines.append('## 不可区分对照')
    lines.append('')
    boundary = summary['boundary_control']
    lines.append(f"- 样本数 {boundary['n']}，判为可疑 {boundary['flagged']}。")
    lines.append(f"- {boundary['note']}")
    lines.append('')
    lines.append('## RS 辅助特征（d_m 随载荷下降）')
    lines.append('')
    lines.append('| 载荷字节 | 样本数 | d_m 均值 | 最小 | 最大 |')
    lines.append('|---:|---:|---:|---:|---:|')
    for key, value in summary['rs_d_m_by_payload'].items():
        lines.append(f"| {key} | {value['n']} | {value['mean']:.3f} | {value['min']:.3f} | {value['max']:.3f} |")
    lines.append('')
    return '\n'.join(lines)


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT_DIR,
                        help='输出目录，默认 outputs/steganalysis')
    args = parser.parse_args()
    output_dir = args.output_dir
    calibration = load_calibration(CALIBRATION_PATH)
    cover_rows, cover_images = build_cover_rows()
    stego_rows = build_stego_rows(cover_images)
    scope_rows = build_scope_rows(cover_images)
    boundary_rows = build_boundary_rows()
    rs_rows = build_rs_rows(cover_images)
    roundtrip = check_png_roundtrip(cover_images)

    summary = summarize(cover_rows, stego_rows, scope_rows, boundary_rows, rs_rows, calibration)
    summary['png_roundtrip'] = roundtrip

    write_csv(output_dir / 'eval_results.csv', cover_rows + stego_rows + scope_rows + boundary_rows, CSV_FIELDS)
    write_csv(output_dir / 'rs_results.csv', rs_rows,
              ['sample_id', 'source', 'payload_bytes', 'groups', 'd_m', 'd_neg',
               'r_m', 's_m', 'r_neg', 's_neg'])
    (output_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output_dir / 'summary.md').write_text(markdown_tables(summary) + '\n', encoding='utf-8')

    print(markdown_tables(summary))
    print('PNG 重存后分数一致：', all(item['same'] for item in roundtrip),
          [item['sample_id'] for item in roundtrip])
    print(f'原始结果：{output_dir / "eval_results.csv"}')
    print(f'RS 结果：{output_dir / "rs_results.csv"}')
    return 0 if all(item['same'] for item in roundtrip) else 1


if __name__ == '__main__':
    raise SystemExit(main())
