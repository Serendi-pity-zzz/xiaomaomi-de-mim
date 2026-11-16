# === 文件说明 ===
# 用途：验证 PNG 参数校验、独立进程提取、一键演示、稳定高位特征、损坏输入及指标边界。
# 关联文件：core/g_png.py、core/g_adaptive_steganography.py、examples/g_demo.py、experiments/g_metrics.py。
# 运行入口：tests/g_run_tests.py；临时文件用于隔离每次测试的输入输出。
# === 原代码 ===
"""Independent-process transport and CLI checks for the current G delivery."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from core import g_adaptive_steganography as g
from core.g_png import save_png, load_png
from experiments.g_metrics import evaluate

ROOT = Path(__file__).resolve().parents[1]
KEY = 'public-test-key'

class TransportTests(unittest.TestCase):
    def fixture(self):
        return Image.fromarray(np.random.default_rng(7).integers(0,256,(24,24,3),dtype='uint8'))

    def test_demo_roundtrip(self):
        from examples.g_demo import run
        with tempfile.TemporaryDirectory() as folder:
            result = run(Path(folder))
            self.assertTrue(result['secret_success'])
            self.assertTrue(result['scan_success'])

    def test_fresh_process_extracts_only_png_and_key(self):
        im = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'g_bundle.png'
            save_png(path,g.embed(im,'新进程🐱',KEY,(0,0,24,24),method='sobel'))
            script = 'from core.g_png import extract_png; import sys; r=extract_png(sys.argv[1],sys.argv[2]); assert r["status"]=="passed"; assert r["secret"]=="新进程🐱"'
            run = subprocess.run([sys.executable,'-B','-c',script,str(path),KEY],cwd=ROOT,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_high_bit_features_and_flat_edges(self):
        im = self.fixture()
        flipped = Image.fromarray(np.asarray(im)^1)
        for method in ('sobel','variance'):
            self.assertTrue(np.array_equal(g.texture_scores(im,method),g.texture_scores(flipped,method)))
            self.assertTrue(np.all(g.texture_scores(Image.new('RGB',(10,10)),method)==0))

    def test_bundle_rejects_changed_mask_and_metadata_dimensions(self):
        import json
        from PIL.PngImagePlugin import PngInfo
        im = self.fixture()
        output = g.embed(im,'message',KEY,(0,0,24,24))
        mask = np.zeros((24,24),dtype=bool)
        mask[0,0] = True
        with self.assertRaises(ValueError):
            save_png(io.BytesIO(),output,mask)
        stream = io.BytesIO()
        save_png(stream,output)
        stream.seek(0)
        with Image.open(stream) as loaded:
            metadata = json.loads(loaded.info['ruoai_gex1'])
            metadata['width'] += 1
            info = PngInfo()
            info.add_text('ruoai_gex1',json.dumps(metadata))
            damaged = io.BytesIO()
            loaded.save(damaged,format='PNG',pnginfo=info)
        damaged.seek(0)
        with self.assertRaises(ValueError):
            load_png(damaged)

    def test_metric_identity(self):
        im = self.fixture()
        result = evaluate(im,im)
        self.assertEqual(result['ssim'],1)
        self.assertEqual(result['psnr_db'],float('inf'))

    def test_bad_masks_and_corrupted_png(self):
        im = self.fixture()
        for mask in (np.zeros((1,1),dtype=bool),np.zeros((24,24),dtype='uint8'),np.ones((24,24),dtype=bool)):
            with self.assertRaises(ValueError):
                g.embed(im,'message',KEY,(0,0,24,24),protected_mask=mask)
        with self.assertRaises((ValueError,OSError)):
            load_png(io.BytesIO(b'not-a-png'))
