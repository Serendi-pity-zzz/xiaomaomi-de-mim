"""Official B/C/F snapshots + explicit private A adapter; all output is local."""
import csv
import hashlib
import io
import json
import platform
import time
from pathlib import Path
import numpy as np
from PIL import Image
from experiments import g_team_adapter as team
from core import adaptive_steganography as g
from experiments.g_metrics import evaluate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'experiments' / 'data' / 'g_cats'
OUT = ROOT / 'outputs' / 'g_compare'
PUBLIC = 'https://example.com'
RATIOS = (0.1, 0.5, 0.8)
SEED = 20261116

def write_csv(name, rows):
    if not rows:
        return
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def confusion(rows, threshold):
    counts = dict(tp=0, tn=0, fp=0, fn=0, inconclusive_clean=0, inconclusive_stego=0)
    for row in rows:
        if row['score'] is None:
            counts['inconclusive_stego' if row['label'] else 'inconclusive_clean'] += 1
        else:
            predicted = row['score'] >= threshold
            counts[('tp' if predicted else 'fn') if row['label'] else ('fp' if predicted else 'tn')] += 1
    pos,neg = counts['tp']+counts['fn'], counts['tn']+counts['fp']
    return {**counts, 'total':len(rows), 'decidable':pos+neg,
            'tpr': counts['tp']/pos if pos else None, 'fpr': counts['fp']/neg if neg else None,
            'balanced_accuracy':(counts['tp']/pos+counts['tn']/neg)/2 if pos and neg else None}

def main():
    import argparse
    global OUT
    parser = argparse.ArgumentParser(description='G: pinned A/B/C/F comparison')
    parser.add_argument('--smoke', action='store_true', help='Only first two sources; writes outputs/g_smoke')
    args = parser.parse_args()
    if args.smoke:
        OUT = ROOT / 'outputs' / 'g_smoke'
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'samples').mkdir(exist_ok=True)
    manifest = json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    if args.smoke:
        manifest = manifest[:2]
    assert len({r['source_group'] for r in manifest}) == len(manifest)
    rows, detections, attacks, timings = [], [], [], []
    attack_ids = [r['sample_id'] for r in manifest if r['split']=='evaluation'][:3]
    for i,item in enumerate(manifest):
        sample = item['sample_id']
        key = hashlib.sha256(('public-research-fixture/'+sample).encode()).hexdigest()
        photo = DATA/item['image']
        with Image.open(photo) as im:
            assert hashlib.sha256(im.convert('RGB').tobytes()).hexdigest() == item['rgb_sha256'], sample
            carrier = team.generate(PUBLIC, im)
        original,region,mask = (carrier[k] for k in ('image','region','protected_mask'))
        x,y,w,h = region
        base = {k:item[k] for k in ('sample_id','split','source_group')}
        clean = team.detect(original, region)
        detections.append({**base,'algorithm':'clean','ratio':0,'label':0,'score':clean['score'],'decision':clean['decision']})
        common_capacity = min(11960, g.capacity_bytes(original,key,region,protected_mask=mask))
        for ratio in RATIOS:
            payload_bytes = int(common_capacity*ratio)
            seed = SEED+i*100+int(ratio*100)
            rng = np.random.default_rng(seed)
            secret = ''.join(chr(int(v)) for v in rng.integers(32,127,payload_bytes))
            algorithms = list(team.ALGORITHMS)
            algorithms = algorithms[i%5:]+algorithms[:i%5]
            for algorithm in algorithms:
                # Warm up each algorithm once; rotated order reduces fixed ordering bias.
                if i==0 and ratio==0.1:
                    warm = team.embed(carrier,secret,key,algorithm)
                    team.extract(warm['image'],key,region,mask,algorithm)
                repeats = 3 if i<6 and ratio==0.5 else 1
                for repeat in range(repeats):
                    start = time.perf_counter()
                    output = team.embed(carrier,secret,key,algorithm)
                    embed_ms = (time.perf_counter()-start)*1000
                    start = time.perf_counter()
                    decoded = team.extract(output['image'],key,region,mask,algorithm)
                    extract_ms = (time.perf_counter()-start)*1000
                    assert decoded['secret'] == secret
                    timings.append({**base,'algorithm':algorithm,'ratio':ratio,'repeat':repeat,
                                    'embed_ms':embed_ms,'extract_ms':extract_ms})
                stream = io.BytesIO()
                team.save(stream,output,mask,algorithm)
                stream.seek(0)
                restored = team.restore(stream,key,algorithm)
                stream.seek(0)
                with Image.open(stream) as im:
                    stego = im.copy()
                success = restored['status']=='passed' and restored['secret'].encode()==secret.encode()
                protected = bool(np.array_equal(np.asarray(original)[mask],np.asarray(stego)[mask]))
                assert success and protected
                synchronized = ''
                if algorithm.startswith('G-') and ratio==0.5:
                    opts = {'protected_mask':mask,'method':algorithm[2:]}
                    synchronized = g.positions(original,key,region,**opts)==g.positions(stego,key,region,**opts)
                    assert synchronized
                quality = evaluate(original,stego)
                local = evaluate(original.crop((x,y,x+w,y+h)),stego.crop((x,y,x+w,y+h)))
                analysis = team.detect(stego,region)
                qr = team.scan(stego,PUBLIC)
                row = {**base,'source':item['source_url'],'license':item['license'],'seed':seed,
                       'algorithm':algorithm,'carrier_version':carrier['carrier_version'],
                       'width':original.width,'height':original.height,'payload_bytes':payload_bytes,
                       'capacity_bytes':output['capacity_bytes'],'ratio':ratio,
                       'embed_ms':embed_ms,'extract_ms':extract_ms,
                       'psnr_db':quality['psnr_db'],'ssim':quality['ssim'],
                       'region_psnr_db':local['psnr_db'],'region_ssim':local['ssim'],
                       'attack':'none','strength':0,'scan_success':qr,'secret_success':success,
                       'integrity_status':restored['status'],'detection_score':analysis['score'],
                       'detection_decision':analysis['decision'],'calibration_id':analysis['calibration_id'],
                       'positions_equal':synchronized,'protected_unchanged':protected,'error':''}
                rows.append(row)
                detections.append({**base,'algorithm':algorithm,'ratio':ratio,'label':1,
                                   'score':analysis['score'],'decision':analysis['decision']})
                if sample==attack_ids[0] and ratio==0.5:
                    (OUT/'samples'/f'{sample}_{algorithm}.png').write_bytes(stream.getvalue())
                    original.save(OUT/'samples'/f'{sample}_cover.png')
                if sample in attack_ids and ratio==0.5:
                    for name in team.F.ATTACKS:
                        for strength in (0,20,60):
                            attacked = team.F.apply_attack(stego,name,strength,seed)
                            decoded = team.extract(attacked,key,region,mask,algorithm)
                            aq = evaluate(stego,attacked) if attacked.size==stego.size else {}
                            attacks.append({**base,'source':item['source_url'],'license':item['license'],
                                            'seed':seed,'algorithm':algorithm,'width':attacked.width,
                                            'height':attacked.height,'payload_bytes':payload_bytes,
                                            'capacity_bytes':output['capacity_bytes'],'embed_ms':'','extract_ms':'',
                                            'psnr_db':aq.get('psnr_db'),'ssim':aq.get('ssim'),
                                            'attack':name,'strength':strength,
                                            'scan_success':team.scan(attacked,PUBLIC),
                                            'secret_success':decoded['status']=='passed' and decoded['secret']==secret,
                                            'integrity_status':decoded['status'],'detection_score':'',
                                            'error':decoded['detail'] if decoded['status']!='passed' else ''})
            print(f'{sample} {ratio:.0%}: B/C/F + G verified',flush=True)
        for name,data in [('comparison.csv',rows),('detection_samples.csv',detections),('robustness.csv',attacks),('timings.csv',timings)]:
            write_csv(name,data)

    train = [r for r in detections if r['split']=='calibration']
    test = [r for r in detections if r['split']=='evaluation']
    assert not {r['source_group'] for r in train} & {r['source_group'] for r in test}
    candidates = sorted({0.5,1.0,*[r['score'] for r in train if r['score'] is not None and r['score']>0]})
    threshold = max(candidates,key=lambda t:(confusion(train,t)['balanced_accuracy'],-confusion(train,t)['fpr'],t))
    detection = {'official_threshold':0.5,'local_shared_threshold':threshold,
                 'fit_policy':'One shared threshold, maximize calibration balanced accuracy; ties favor low FPR then higher threshold. Never fit evaluation labels.',
                 'training':confusion(train,threshold),'evaluation':{}}
    for algorithm in team.ALGORITHMS:
        detection['evaluation'][algorithm] = {}
        for ratio in RATIOS:
            selected = [r for r in test if r['label']==0 or (r['algorithm']==algorithm and r['ratio']==ratio)]
            detection['evaluation'][algorithm][str(ratio)] = {
                'official':confusion(selected,0.5),'local_shared':confusion(selected,threshold)}
    summary = {'date':'2026-11-16','sources':len(manifest),'calibration_sources':len(manifest)-len({r['source_group'] for r in test}),
               'evaluation_sources':len({r['source_group'] for r in test}),'conditions':len(rows),
               'secret_passed':sum(r['secret_success'] for r in rows),'qr_passed':sum(r['scan_success'] is True for r in rows),
               'qr_unavailable':sum(r['scan_success'] is None for r in rows),
               'protected_checks':sum(r['protected_unchanged'] for r in rows),
               'position_checks':sum(r['positions_equal'] is True for r in rows),
               'timing_rows':len(timings),'attack_rows':len(attacks),'attack_sources':attack_ids,
               'python':platform.python_version(),'numpy':np.__version__,'pillow':Image.__version__,
               'dataset_sha256':hashlib.sha256((DATA/'manifest.json').read_bytes()).hexdigest(),
               'team_manifest_sha256':hashlib.sha256((team.VENDOR/'manifest.json').read_bytes()).hexdigest(),
               'common_capacity':common_capacity,'payload_policy':'same seeded ASCII bytes per source/ratio for all methods',
               'carrier':'A-G-private-1; explicit local integration proposal, not unmodified A',
               'detection':'Official C bias-adjusted chi-square; entire 160x200 region; score is not a probability',
               'integrity':'Message authentication only; B-sequential empty key has no secret-key authenticity',
               'timing_policy':'one warmup per method; 3 repeats first six sources at 50%, one otherwise; excludes PNG/QR/C/metrics'}
    for name,data in [('summary.json',summary),('detection_results.json',detection)]:
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
