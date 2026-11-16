import json
import unittest
from pathlib import Path
from experiments.g_compare import confusion

class ResearchDesignTests(unittest.TestCase):
    def test_real_sources_and_authors_do_not_leak(self):
        root = Path(__file__).resolve().parents[1]/'experiments/data/g_cats'
        records = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        train = [r for r in records if r['split']=='calibration']
        test = [r for r in records if r['split']=='evaluation']
        self.assertEqual((len(train),len(test)),(10,20))
        for field in ('source_group','author_group','sha256','rgb_sha256'):
            self.assertFalse({r[field] for r in train}&{r[field] for r in test})
        for row in records:
            self.assertTrue(row['license'].startswith('CC BY') or row['license']=='CC0')
            self.assertTrue((root/row['image']).is_file())

    def test_inconclusive_is_separate_from_errors(self):
        rows = [{'label':0,'score':0.1},{'label':0,'score':None},
                {'label':1,'score':0.9},{'label':1,'score':None}]
        result = confusion(rows,0.5)
        self.assertEqual((result['tp'],result['tn'],result['fp'],result['fn']),(1,1,0,0))
        self.assertEqual((result['inconclusive_clean'],result['inconclusive_stego']),(1,1))
        self.assertEqual(result['decidable'],2)
