"""Reproduce G aggregates and chart from measured CSV files."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/g_compare'
ANALYSIS = ROOT/'outputs/g_analysis'
METHODS = ['B-sequential','B-keyed','G-keyed','G-sobel','G-variance']

def read(name):
    with (OUT/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(map(str,row))+' |' for row in rows]])

def pct(x):
    return '不可判定' if x is None else f'{x:.1%}'

def main():
    import argparse
    global OUT, ANALYSIS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=OUT)
    parser.add_argument('--out', type=Path, default=ANALYSIS)
    args = parser.parse_args()
    OUT, ANALYSIS = args.input.resolve(), args.out.resolve()
    if ANALYSIS == OUT or ANALYSIS == (ROOT/'experiments/results/g').resolve():
        raise ValueError('Choose a separate output directory to preserve raw evidence')
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    summary = json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    detection = json.loads((OUT/'detection_results.json').read_text(encoding='utf-8'))
    rows = [r for r in read('comparison.csv') if r['split']=='evaluation']
    timing = [r for r in read('timings.csv') if r['split']=='evaluation' and float(r['ratio'])==0.5]
    attacks = read('robustness.csv')
    aggregate, quality_table, time_table, detect_table, pairs = [], [], [], [], []
    for method in METHODS:
        for ratio in (0.1,0.5,0.8):
            group = [r for r in rows if r['algorithm']==method and float(r['ratio'])==ratio]
            entry = {'algorithm':method,'ratio':ratio,'sources':len(group)}
            for field in ('psnr_db','ssim','region_psnr_db','region_ssim'):
                entry[field] = float(np.mean([float(r[field]) for r in group]))
            aggregate.append(entry)
            if ratio==0.5:
                quality_table.append([method,len(group),f"{entry['psnr_db']:.3f}",f"{entry['ssim']:.6f}",f"{entry['region_psnr_db']:.3f}",f"{entry['region_ssim']:.6f}"])
        by_source = defaultdict(list)
        for row in timing:
            if row['algorithm']==method:
                by_source[row['sample_id']].append(row)
        medians = {field:float(np.median([np.median([float(r[field]) for r in group]) for group in by_source.values()])) for field in ('embed_ms','extract_ms')}
        time_table.append([method,11960 if method.startswith('B-') else 11956,f"{medians['embed_ms']:.1f}",f"{medians['extract_ms']:.1f}"])
        d = detection['evaluation'][method]['0.5']
        for threshold_type in ('official','local_shared'):
            e = d[threshold_type]
            detect_table.append([method,'C 原阈值' if threshold_type=='official' else '共同校准阈值',e['tp'],e['tn'],e['fp'],e['fn'],
                                 e['inconclusive_clean']+e['inconclusive_stego'],pct(e['balanced_accuracy']),pct(e['fpr'])])
    rng = np.random.default_rng(20261116)
    for reference in ('B-sequential','B-keyed'):
        baseline = {r['sample_id']:r for r in rows if r['algorithm']==reference and float(r['ratio'])==0.5}
        for method in ('G-keyed','G-sobel','G-variance'):
            selected = sorted([r for r in rows if r['algorithm']==method and float(r['ratio'])==0.5],key=lambda r:r['sample_id'])
            for metric in ('region_psnr_db','region_ssim'):
                delta = np.array([float(r[metric])-float(baseline[r['sample_id']][metric]) for r in selected])
                means = rng.choice(delta,(10000,len(delta)),replace=True).mean(axis=1)
                lo,hi = np.quantile(means,[0.025,0.975])
                pairs.append({'reference':reference,'algorithm':method,'metric':metric,'n':len(delta),
                              'mean_delta':float(delta.mean()),'ci_low':float(lo),'ci_high':float(hi)})
    paired_table = [[p['reference'],p['algorithm'],p['metric'],f"{p['mean_delta']:+.6f}",f"[{p['ci_low']:+.6f}, {p['ci_high']:+.6f}]"] for p in pairs]
    attack_table = []
    for attack in dict.fromkeys(r['attack'] for r in attacks):
        for strength in ('0','20','60'):
            group = [r for r in attacks if r['attack']==attack and r['strength']==strength]
            attack_table.append([attack,strength,len(group),f"{sum(r['scan_success']=='True' for r in group)}/{len(group)}",
                                 f"{sum(r['secret_success']=='True' for r in group)}/{len(group)}",
                                 sum(r['integrity_status']=='passed' for r in group),sum(r['integrity_status']=='failed' for r in group),sum(r['integrity_status']=='unknown' for r in group)])
    (ANALYSIS/'aggregates.json').write_text(json.dumps({'quality':aggregate,'paired':pairs,'timing':time_table},indent=2),encoding='utf-8')
    fig, axes = plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for method in METHODS:
        group = [r for r in aggregate if r['algorithm']==method]
        for ax,metric,label in zip(axes,('region_psnr_db','region_ssim'),('Region PSNR (dB)','Region SSIM')):
            ax.plot([100*r['ratio'] for r in group],[r[metric] for r in group],marker='o',label=method)
            ax.set_xlabel('Payload / common capacity (%)')
            ax.set_ylabel(label)
            ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.savefig(ANALYSIS/'quality_comparison.png',dpi=180)
    plt.close(fig)
    print('Reproduced aggregates and chart:', ANALYSIS)

if __name__=='__main__':
    main()
