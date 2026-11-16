import hashlib
import io
import json
import unittest
import numpy as np
from PIL import Image
from core import adaptive_steganography as g
from experiments import g_team_adapter as team
from core.g_png import save_png, load_png, extract_png

KEY = 'public-integration-test-key'

class TeamAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = Image.fromarray(np.random.default_rng(42).integers(0, 256, (200, 160, 3), dtype='uint8'))
        cls.carrier = team.generate('https://example.com', cls.cat)

    def test_snapshots_exact(self):
        for item in json.loads((team.VENDOR / 'manifest.json').read_text()):
            self.assertEqual(hashlib.sha256((team.VENDOR / item['path']).read_bytes()).hexdigest(), item['sha256'])

    def test_original_a_conflict_and_private_adapter(self):
        original = team.generate('https://example.com', self.cat, mode='a-original')
        x,y,w,h = original['region']
        self.assertTrue(original['protected_mask'][y:y+h,x:x+w].all())
        with self.assertRaises(ValueError):
            team.embed(original, 'message', KEY)
        mask = self.carrier['protected_mask']
        self.assertTrue(np.array_equal(np.asarray(original['image'])[mask], np.asarray(self.carrier['image'])[mask]))
        self.assertTrue(team.scan(self.carrier['image'], 'https://example.com'))

    def test_all_five_algorithms_png_recovery_and_protection(self):
        c = self.carrier
        before = c['image'].tobytes()
        for algorithm in team.ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                result = team.embed(c, '中文、emoji 🐱、PNG roundtrip', KEY, algorithm)
                stream = io.BytesIO()
                team.save(stream, result, c['protected_mask'], algorithm)
                stream.seek(0)
                decoded = team.restore(stream, KEY, algorithm)
                self.assertEqual(decoded['status'], 'passed')
                self.assertEqual(decoded['secret'], '中文、emoji 🐱、PNG roundtrip')
                self.assertTrue(np.array_equal(np.asarray(c['image'])[c['protected_mask']],
                                              np.asarray(result['image'])[c['protected_mask']]))
        self.assertEqual(before, c['image'].tobytes())

    def test_formal_b_matches_cat1_baseline(self):
        legacy = team.load('team_legacy_test', 'core/baseline.py')
        im = self.carrier['image']
        for key in ('', KEY):
            out = team.B.embed(im, '兼容性🐱', key)
            self.assertEqual(out['image'].tobytes(), legacy.embed(im, '兼容性🐱', key).tobytes())
            self.assertEqual(legacy.extract(out['image'], key)['secret'], '兼容性🐱')

    def test_protocols_are_not_silently_mixed(self):
        c = self.carrier
        b = team.embed(c, 'B', KEY, 'B-keyed')['image']
        improved = team.embed(c, 'G', KEY, 'G-sobel')['image']
        self.assertNotEqual(team.extract(b, KEY, c['region'], c['protected_mask'], 'G-sobel')['status'], 'passed')
        self.assertNotEqual(team.B.extract(improved, KEY)['status'], 'passed')

    def test_c_uses_released_calibration(self):
        c = self.carrier
        result = team.detect(c['image'], c['region'])
        self.assertEqual(result['method_detail'], 'chi_square_bias_adjusted')
        self.assertEqual(result['threshold_source'], 'calibration')
        self.assertEqual(result['threshold'], 0.5)

    def test_f_zero_strength_is_identity_and_crop_is_failure(self):
        c = self.carrier
        out = team.embed(c, 'crop boundary', KEY)['image']
        for name in team.F.ATTACKS:
            self.assertEqual(team.F.apply_attack(out, name, 0, 42).tobytes(), out.tobytes())
        cropped = team.F.apply_attack(out, 'crop', 60, 42)
        self.assertNotEqual(cropped.size, out.size)
        self.assertEqual(team.extract(cropped, KEY, c['region'], c['protected_mask'], 'G-sobel')['status'], 'unknown')

    def test_all_g_methods_sync_capacity_and_tampering(self):
        # Tiny fixture keeps full-capacity and edge/corner checks inexpensive.
        im = Image.fromarray(np.random.default_rng(9).integers(0,256,(24,24,3),dtype='uint8'))
        region = (0,0,24,24)
        mask = np.zeros((24,24), dtype=bool)
        mask[4:7, 4:7] = True
        cap = g.capacity_bytes(im, KEY, region, protected_mask=mask)
        for method in g.METHODS:
            for message in ('', '你好🐱', 'x'*cap):
                with self.subTest(method=method, size=len(message)):
                    out = g.embed(im, message, KEY, region, protected_mask=mask, method=method)
                    order = g.positions(im, KEY, region, protected_mask=mask, method=method)
                    self.assertEqual(order, g.positions(out['image'], KEY, region, protected_mask=mask, method=method))
                    self.assertEqual(g.extract(out['image'], KEY, region, protected_mask=mask)['secret'], message)
                    self.assertTrue(np.array_equal(np.asarray(im) & 254, np.asarray(out['image']) & 254))
                    if message:
                        x,y,ch = order[1][0]
                        pixel = list(out['image'].getpixel((x,y)))
                        pixel[ch] ^= 1
                        out['image'].putpixel((x,y), tuple(pixel))
                        self.assertEqual(g.extract(out['image'], KEY, region, protected_mask=mask)['status'], 'failed')
            with self.assertRaises(ValueError):
                g.embed(im, 'x'*(cap+1), KEY, region, protected_mask=mask, method=method)

    def test_bundle_missing_metadata_is_not_passed(self):
        stream = io.BytesIO()
        self.carrier['image'].save(stream, format='PNG')
        stream.seek(0)
        with self.assertRaises(ValueError):
            extract_png(stream, KEY)

    def test_wrong_key_and_mask(self):
        c = self.carrier
        out = team.embed(c, 'authenticated', KEY)['image']
        self.assertEqual(team.extract(out, 'wrong', c['region'], c['protected_mask'], 'G-sobel')['status'], 'unknown')
        mask = c['protected_mask'].copy()
        x,y,_,_ = c['region']
        mask[y,x] = True
        self.assertNotEqual(team.extract(out, KEY, c['region'], mask, 'G-sobel')['status'], 'passed')

if __name__ == '__main__':
    unittest.main()
