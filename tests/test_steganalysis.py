"""C 模块单元测试：正常、边界与异常案例。

运行（项目根目录）：

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / '.deps', ROOT, ROOT / 'tests'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from PIL import Image  # noqa: E402

from core.steganalysis import (  # noqa: E402
    DEFAULT_CALIBRATION_FILENAME,
    LIMITATIONS,
    METHOD_CHI_SQUARE,
    METHOD_RS,
    analyze,
    calibration_id,
    chi_square_sf,
    load_calibration,
    rs_features,
)
from steganalysis_data import (  # noqa: E402
    CAT_CAPACITY_BYTES,
    builtin_cover,
    cat_region,
    embed_cat1,
    payload,
)

try:
    from scipy.stats import chi2 as scipy_chi2
except ImportError:  # SciPy 不是本模块依赖，仅用于交叉验证
    scipy_chi2 = None


class ChiSquareDistributionTests(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(chi_square_sf(3.841458820694124, 1), 0.05, places=6)
        self.assertAlmostEqual(chi_square_sf(18.307038053275146, 10), 0.05, places=6)
        self.assertAlmostEqual(chi_square_sf(0.0, 5), 1.0)
        self.assertAlmostEqual(chi_square_sf(5.991464547107979, 2), 0.05, places=6)

    def test_bounds_and_monotonicity(self):
        previous = 1.0
        for statistic in (0, 1, 5, 20, 100, 1000):
            value = chi_square_sf(statistic, 12)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
            self.assertLessEqual(value, previous)
            previous = value

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            chi_square_sf(1.0, 0)
        with self.assertRaises(ValueError):
            chi_square_sf(float('nan'), 3)
        with self.assertRaises(ValueError):
            chi_square_sf(float('inf'), 3)
        for df in (True, 1.5, float('nan'), float('inf'), '3', None):
            with self.subTest(df=df), self.assertRaises(ValueError):
                chi_square_sf(1, df)
        for statistic in (True, '1', None):
            with self.subTest(statistic=statistic), self.assertRaises(ValueError):
                chi_square_sf(statistic, 3)

    @unittest.skipUnless(scipy_chi2 is not None, '未安装 SciPy，跳过交叉验证')
    def test_matches_scipy(self):
        for df in (1, 2, 5, 10, 127, 255):
            for statistic in (0.1, 0.5, 1.0, float(df), 2.0 * df + 5.0, 4.0 * df):
                self.assertAlmostEqual(
                    chi_square_sf(statistic, df),
                    float(scipy_chi2.sf(statistic, df)),
                    places=10,
                )


class AnalyzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cover = builtin_cover('https://example.com/steganalysis-test')
        cls.region = cat_region(cls.cover)
        cls.full_text = payload('ascii', CAT_CAPACITY_BYTES, 11)
        cls.full_stego = embed_cat1(cls.cover, cls.full_text, '')
        cls.keyed_stego = embed_cat1(cls.cover, payload('zh', CAT_CAPACITY_BYTES, 12), 'unit-test-key')

    def test_cover_is_not_flagged(self):
        result = analyze(self.cover, self.region)
        self.assertEqual(result['method'], METHOD_CHI_SQUARE)
        self.assertEqual(result['analysis_scope'], 'region')
        self.assertEqual(result['decision'], 'clean')
        self.assertLess(result['score'], result['threshold'])
        self.assertEqual(result['samples'], 160 * 200 * 3)
        for key in ('method', 'statistic', 'score', 'threshold', 'decision',
                    'calibration_id', 'limitations', 'details'):
            self.assertIn(key, result)
        self.assertIn('不能据此证明', result['detail'])

    def test_full_capacity_is_flagged(self):
        result = analyze(self.full_stego, self.region)
        self.assertEqual(result['decision'], 'suspicious')
        self.assertGreaterEqual(result['score'], result['threshold'])
        self.assertGreater(result['details']['pair_count'], 1)
        self.assertGreater(result['details']['classic_statistic'], result['statistic'])
        self.assertIn('不能据此断言存在秘密', result['detail'])

    def test_keyed_full_capacity_is_flagged(self):
        result = analyze(self.keyed_stego, self.region)
        self.assertEqual(result['decision'], 'suspicious')

    def test_small_payload_is_not_detected(self):
        stego = embed_cat1(self.cover, payload('ascii', 1024, 5), '')
        result = analyze(stego, self.region)
        self.assertEqual(result['decision'], 'clean')
        self.assertLess(result['score'], result['threshold'])

    def test_whole_image_scope(self):
        result = analyze(self.cover)
        self.assertEqual(result['analysis_scope'], 'whole_image')
        self.assertEqual(result['region'], {'x': 0, 'y': 0,
                                            'width': self.cover.width,
                                            'height': self.cover.height})
        self.assertEqual(result['decision'], 'clean')

    def test_full_image_region_matches_whole_image(self):
        region_result = analyze(self.cover, (0, 0, self.cover.width, self.cover.height))
        whole_result = analyze(self.cover)
        self.assertEqual(region_result['statistic'], whole_result['statistic'])
        self.assertEqual(region_result['score'], whole_result['score'])

    def test_deterministic_and_json_serializable(self):
        first = analyze(self.full_stego, self.region)
        second = analyze(self.full_stego, self.region)
        self.assertEqual(first, second)
        json.dumps(first, ensure_ascii=False)

    def test_manual_threshold_and_source(self):
        result = analyze(self.full_stego, self.region, threshold=0.999)
        self.assertEqual(result['threshold'], 0.999)
        self.assertEqual(result['threshold_source'], 'manual')
        self.assertEqual(result['decision'], 'clean')
        json.dumps(result, ensure_ascii=False)

    def test_manual_threshold_does_not_need_calibration(self):
        missing = ROOT / 'outputs' / 'missing-calibration-for-test.json'
        result = analyze(self.cover, self.region, threshold=0.5, calibration_path=missing)
        self.assertEqual(result['calibration_id'], 'manual')
        self.assertIn('calibration_note', result)
        self.assertEqual(result['decision'], 'clean')

    def test_invalid_thresholds(self):
        for value in (0.0, -0.1, 1.1, True, '0.5', None):
            if value is None:
                continue
            with self.assertRaises(ValueError):
                analyze(self.cover, self.region, threshold=value)

    def test_small_region_is_inconclusive(self):
        result = analyze(self.cover, (0, 0, 2, 2))
        self.assertEqual(result['decision'], 'inconclusive')
        self.assertIsNone(result['score'])
        self.assertIsNone(result['statistic'])
        self.assertIn('无法判定', result['detail'])

    def test_single_value_pair_is_inconclusive(self):
        flat = Image.new('RGB', (40, 40), (100, 100, 100))
        result = analyze(flat, (0, 0, 40, 40))
        self.assertEqual(result['decision'], 'inconclusive')
        self.assertIn('值对', result['detail'])

    def test_degenerate_lsb_ratio_is_inconclusive(self):
        image = Image.new('RGB', (260, 256), (100, 100, 100))
        for y in range(image.height):
            for x in range(130, image.width):
                image.putpixel((x, y), (150, 150, 150))
        result = analyze(image, (80, 32, 160, 200))
        self.assertEqual(result['decision'], 'inconclusive')
        self.assertIn('偏置修正退化', result['detail'])

    def test_grayscale_input_is_converted(self):
        gray = self.cover.convert('L')
        result = analyze(gray, self.region)
        self.assertEqual(result['method'], METHOD_CHI_SQUARE)
        self.assertIn(result['decision'], ('clean', 'suspicious', 'inconclusive'))

    def test_rs_method_returns_auxiliary_result(self):
        result = analyze(self.cover, self.region, method='rs')
        self.assertEqual(result['method'], METHOD_RS)
        self.assertEqual(result['decision'], 'inconclusive')
        self.assertIsNone(result['score'])
        self.assertIn('rs', result['details'])
        self.assertEqual(result['details']['rs']['pooled']['groups'], 24000)

    def test_include_rs_in_details(self):
        result = analyze(self.cover, self.region, include_rs=True)
        self.assertIn('rs', result['details'])
        self.assertEqual(result['details']['rs']['usage'], 'auxiliary_only')

    def test_unknown_method(self):
        with self.assertRaises(ValueError):
            analyze(self.cover, self.region, method='spa')

    def test_invalid_region_arguments(self):
        for region in ((0, 0, 10), (0, 0, 10, 10, 10), (0, 0, 0, 10),
                       (0, 0, -5, 10), (-1, 0, 10, 10), (0, 0, 10.5, 10),
                       (0, 0, True, 10), (0, 0, 10, 10.0)):
            with self.assertRaises(ValueError):
                analyze(self.cover, region)

    def test_region_out_of_bounds(self):
        for region in ((self.cover.width - 5, 0, 10, 10),
                       (0, self.cover.height - 5, 10, 10)):
            with self.assertRaises(ValueError):
                analyze(self.cover, region)

    def test_non_image_input(self):
        for value in ('not-an-image', None, b'PNG'):
            with self.assertRaises(ValueError):
                analyze(value, (0, 0, 10, 10))

    def test_limitations_are_exposed(self):
        result = analyze(self.cover, self.region)
        self.assertEqual(result['limitations'], LIMITATIONS)
        self.assertTrue(any('概率' in item for item in result['limitations']))


class RsFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cover = builtin_cover('https://example.com/rs-test')
        cls.region = cat_region(cls.cover)

    def test_counts_and_ranges(self):
        features = rs_features(self.cover, self.region)
        self.assertEqual(features['group_size'], 4)
        self.assertEqual(features['mask'], [0, 1, 1, 0])
        pooled = features['pooled']
        self.assertEqual(pooled['groups'], 24000)
        for channel in features['channels'].values():
            for key in ('r_m', 's_m', 'r_neg', 's_neg'):
                self.assertGreaterEqual(channel[key], 0.0)
                self.assertLessEqual(channel[key], 1.0)
            for key in ('d_m', 'd_neg'):
                self.assertGreaterEqual(channel[key], -1.0)
                self.assertLessEqual(channel[key], 1.0)

    def test_cover_d_m_drops_after_full_embedding(self):
        stego = embed_cat1(self.cover, payload('ascii', CAT_CAPACITY_BYTES, 11), '')
        cover_m = rs_features(self.cover, self.region)['pooled']['d_m']
        stego_m = rs_features(stego, self.region)['pooled']['d_m']
        self.assertGreater(cover_m, 0.9)
        self.assertLess(stego_m, 0.1)

    def test_region_without_complete_group_is_inconclusive(self):
        for region in ((0, 0, 1, 1), (0, 0, 3, 1)):
            with self.subTest(region=region):
                result = analyze(self.cover, region, method='rs')
                self.assertEqual(result['decision'], 'inconclusive')
                features = result['details']['rs']
                self.assertEqual(features['pooled']['groups'], 0)
                self.assertIsNone(features['pooled']['d_m'])
                for channel in features['channels'].values():
                    self.assertEqual(channel['groups'], 0)
                    self.assertIsNone(channel['r_m'])
                json.dumps(result, allow_nan=False)
                combined = analyze(self.cover, region, include_rs=True)
                self.assertEqual(combined['decision'], 'inconclusive')

    def test_one_complete_group_per_channel(self):
        result = rs_features(self.cover, (0, 0, 4, 1))
        self.assertEqual(result['pooled']['groups'], 3)
        self.assertIsNotNone(result['pooled']['d_m'])


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / 'core' / DEFAULT_CALIBRATION_FILENAME
        cls.calibration = load_calibration(cls.path)

    def test_calibration_metadata(self):
        self.assertEqual(self.calibration['schema'], 'steganalysis-calibration/1')
        self.assertGreater(self.calibration['threshold'], 0.0)
        self.assertLessEqual(self.calibration['threshold'], 1.0)
        self.assertEqual(self.calibration['calibration_id'], calibration_id(self.calibration))
        self.assertEqual(self.calibration['calibration_id'],
                         load_calibration()['calibration_id'])

    def test_threshold_interval_is_consistent(self):
        interval = self.calibration['threshold_interval']
        self.assertLessEqual(interval['lower'], self.calibration['threshold'])
        self.assertLessEqual(self.calibration['threshold'], interval['upper'])

    def test_tampered_calibration_is_rejected(self):
        tampered = dict(self.calibration)
        tampered['threshold'] = 0.9
        target = ROOT / 'outputs' / 'tampered_calibration.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(json.dumps(tampered, ensure_ascii=False), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_calibration(target)
        finally:
            target.unlink(missing_ok=True)

    def test_missing_calibration(self):
        with self.assertRaises(ValueError):
            load_calibration(ROOT / 'outputs' / 'does-not-exist.json')

    def test_malformed_calibration_is_rejected(self):
        invalid = [[], None, 'not-an-object', 42]
        for field, values in (('method', ('rs', None)),
                              ('threshold', (None, True, 0, 1.1, float('nan')))):
            for value in values:
                item = dict(self.calibration)
                item[field] = value
                item['calibration_id'] = calibration_id(item)
                invalid.append(item)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'calibration.json'
            for value in invalid:
                with self.subTest(value=value):
                    target.write_text(json.dumps(value), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_calibration(target)


class EvaluationMetricsTests(unittest.TestCase):
    def test_threshold_calibration_handles_narrow_and_overlapping_scores(self):
        from calibrate_steganalysis import select_threshold
        self.assertEqual(select_threshold(0.000046, 0.593774)[0], 0.5)
        threshold = select_threshold(0.511, 0.512)[0]
        self.assertGreater(threshold, 0.511)
        self.assertLessEqual(threshold, 0.512)
        for lower, upper in ((0.6, 0.4), (0.4, 0.4), (0, float('nan'))):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                select_threshold(lower, upper)

    def test_unknowns_are_not_counted_as_correct_or_negative(self):
        from eval_steganalysis import confusion_metrics
        result = confusion_metrics(
            {'n': 5, 'flagged': 1, 'inconclusive': 2},
            {'n': 5, 'detected': 2, 'inconclusive': 1})
        self.assertEqual([result[k] for k in ('tp', 'fn', 'fp', 'tn')], [2, 2, 1, 2])
        self.assertAlmostEqual(result['accuracy_decided'], 4 / 7)
        self.assertAlmostEqual(result['fpr_decided'], 1 / 3)
        self.assertAlmostEqual(result['fnr_decided'], 1 / 2)
        self.assertAlmostEqual(result['decision_coverage'], 7 / 10)

    def test_all_unknown_metrics_are_unavailable(self):
        from eval_steganalysis import confusion_metrics
        result = confusion_metrics(
            {'n': 2, 'flagged': 0, 'inconclusive': 2},
            {'n': 3, 'detected': 0, 'inconclusive': 3})
        for key in ('accuracy_decided', 'fpr_decided', 'fnr_decided'):
            self.assertIsNone(result[key])
        self.assertEqual(result['decision_coverage'], 0)


if __name__ == '__main__':
    unittest.main()
