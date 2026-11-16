# === 文件说明 ===
# 用途：一键演示猫图载体上的 G 隐写、PNG 保存、提取、二维码解码和统计检测。
# 关联文件：调用 experiments/g_team_adapter.py，使用 experiments/data/g_cats/g_cat02.png。
# 输出位置：outputs/g_demo/；复用 core/g_png.py 的文件格式，测试入口见 tests/g_test_transport.py。
# === 原代码 ===
"""G module demonstration, independent of the private work directory.

Run from repository root: python -m examples.g_demo
The key and message are public fixtures, not actual confidential data.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from experiments import g_team_adapter as team

ROOT = Path(__file__).resolve().parents[1]

def run(output_dir, method='sobel'):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT/'experiments/data/g_cats/g_cat02.png') as cat:
        carrier = team.generate('https://example.com', cat)
    key = hashlib.sha256(b'public-g-aligned-demo').hexdigest()
    message = '任务G：密钥置乱 + Sobel 自适应，PNG 无损恢复 🐱'
    algorithm = 'G-' + method
    output = team.embed(carrier, message, key, algorithm)
    png = output_dir/'g_stego.png'
    team.save(png, output, carrier['protected_mask'], algorithm)
    restored = team.restore(png, key, algorithm)
    success = restored['status']=='passed' and restored['secret']==message
    if not success:
        raise RuntimeError('PNG roundtrip failed')
    report = {'algorithm':algorithm, 'carrier_version':carrier['carrier_version'],
              'capacity_bytes':output['capacity_bytes'], 'secret_success':success,
              'scan_success':team.scan(output['image'], carrier['public']),
              'detection_decision':team.detect(output['image'],carrier['region'])['decision'],
              'fixture_only':True}
    (output_dir/'g_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/g_demo')
    parser.add_argument('--method',choices=('keyed','sobel','variance'),default='sobel')
    args = parser.parse_args()
    print(json.dumps(run(args.out,args.method),ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()
