# === 文件说明 ===
# 用途：快速核对已交付实验结果的文件哈希、样本数量、恢复结果、图像来源和成员副本。
# 关联文件：读取 results/g/g_provenance.json、各 CSV、data/g_cats/g_manifest.json 和 g_reference/g_manifest.json。
# 校验规则：成员副本分别验证中文说明后的文件哈希及原始代码正文哈希；不需要重跑完整实验。
# === 原代码 ===
"""Audit the published G evidence without rerunning the full experiment."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT/'experiments/results/g'

def rows(name):
    with (RESULTS/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def main():
    provenance = json.loads((RESULTS/'g_provenance.json').read_text(encoding='utf-8'))
    for relative,digest in provenance['sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest, relative
    summary = json.loads((RESULTS/'g_summary.json').read_text(encoding='utf-8'))
    comparison,attacks,detection,timing = (rows(n) for n in ('g_comparison.csv','g_robustness.csv','g_detection_samples.csv','g_timings.csv'))
    assert len(comparison)==summary['conditions']==450
    assert len({(r['sample_id'],r['algorithm'],r['ratio']) for r in comparison})==450
    assert len(attacks)==summary['attack_rows']==315
    assert len(timing)==summary['timing_rows']==510
    assert len(detection)==480 and sum(r['label']=='0' for r in detection)==30
    assert all(r['secret_success']=='True' and r['protected_unchanged']=='True' for r in comparison)
    assert sum(r['positions_equal']=='True' for r in comparison)==90
    assert sum(r['scan_success']=='True' for r in comparison)==450
    for row in comparison:
        assert int(row['payload_bytes'])==int(11956*float(row['ratio']))
        assert int(row['capacity_bytes'])==(11960 if row['algorithm'].startswith('B-') else 11956)
    for item in json.loads((ROOT/'experiments/g_reference/g_manifest.json').read_text()):
        raw = (ROOT/'experiments/g_reference'/item['local_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==item['annotated_sha256']
        assert hashlib.sha256(raw[item['annotation_bytes']:]).hexdigest()==item['sha256']
    from PIL import Image
    for item in json.loads((ROOT/'experiments/data/g_cats/g_manifest.json').read_text(encoding='utf-8')):
        with Image.open(ROOT/'experiments/data/g_cats'/item['image']) as im:
            assert hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()==item['rgb_sha256']
    print('Evidence verified: 450 comparisons, 315 attacks, 510 timings, 90 position checks; hashes match.')

if __name__=='__main__':
    main()
