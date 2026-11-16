import io
import unittest
from PIL import Image
from core import baseline
from core import adaptive_steganography as g

KEY = 'public-test-key'


class KeyedLSBTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (24, 24), (127, 128, 129))
        self.region = (2, 2, 20, 20)

    def reload(self, image):
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        stream.seek(0)
        with Image.open(stream) as loaded:
            return loaded.copy()

    def test_messages_and_exact_capacity_after_png(self):
        capacity = g.capacity_bytes(self.image, KEY, self.region)
        for secret in ('', 'hello', '你好🐱', 'a' * capacity):
            with self.subTest(secret_bytes=len(secret.encode('utf-8'))):
                saved = self.reload(g.embed(self.image, secret, KEY, self.region)['image'])
                result = g.extract(saved, KEY, self.region)
                self.assertEqual(result['status'], 'passed')
                self.assertEqual(result['secret'].encode('utf-8'), secret.encode('utf-8'))

    def test_capacity_rejection_does_not_modify_input(self):
        before = self.image.tobytes()
        with self.assertRaises(ValueError):
            g.embed(self.image, 'a' * (g.capacity_bytes(self.image, KEY, self.region) + 1), KEY, self.region)
        self.assertEqual(before, self.image.tobytes())

    def test_position_sync_uniqueness_and_key_difference(self):
        before = g.positions(self.image, KEY, self.region)
        output = self.reload(g.embed(self.image, '你好', KEY, self.region)['image'])
        self.assertEqual(before, g.positions(output, KEY, self.region))
        self.assertNotEqual(before, g.positions(self.image, 'other-public-key', self.region))
        header, payload = before
        self.assertEqual(len(header), 352)
        self.assertEqual(len(set(header + payload)), 20 * 20 * 3)

    def test_source_and_outside_region_unchanged(self):
        before = self.image.tobytes()
        output = g.embed(self.image, 'abc', KEY, self.region)['image']
        self.assertEqual(before, self.image.tobytes())
        for y in range(24):
            for x in range(24):
                a, b = self.image.getpixel((x, y)), output.getpixel((x, y))
                if not (2 <= x < 22 and 2 <= y < 22):
                    self.assertEqual(a, b)
                self.assertEqual(tuple(v & 254 for v in a), tuple(v & 254 for v in b))

    def test_wrong_key_and_unmarked_image(self):
        output = g.embed(self.image, 'abc', KEY, self.region)['image']
        for image, key in ((output, 'wrong'), (self.image, KEY)):
            result = g.extract(image, key, self.region)
            self.assertEqual(result['status'], 'unknown')
            self.assertIsNone(result['secret'])

    def test_payload_tampering(self):
        output = g.embed(self.image, 'abc', KEY, self.region)['image']
        _, payload = g.positions(output, KEY, self.region)
        x, y, c = payload[0]
        rgb = list(output.getpixel((x, y)))
        rgb[c] ^= 1
        output.putpixel((x, y), tuple(rgb))
        result = g.extract(output, KEY, self.region)
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['secret'])

    def test_corrupted_length_is_bounded(self):
        output = g.embed(self.image, 'abc', KEY, self.region)['image']
        header, _ = g.positions(output, KEY, self.region)
        for x, y, c in header[8 * 8:12 * 8]:
            rgb = list(output.getpixel((x, y)))
            rgb[c] |= 1
            output.putpixel((x, y), tuple(rgb))
        self.assertEqual(g.extract(output, KEY, self.region)['status'], 'failed')

    def test_invalid_inputs(self):
        cases = [(self.image, '', self.region), (self.image.convert('L'), KEY, self.region),
                 (self.image, KEY, (-1, 0, 20, 20)), (self.image, KEY, (0, 0, 25, 24)),
                 (self.image, KEY, (0, 0, 1, 1)), (self.image, KEY, (0, 0, 0, 20))]
        for image, key, region in cases:
            with self.subTest(region=region, mode=image.mode):
                with self.assertRaises(ValueError):
                    g.embed(image, 'abc', key, region)

    def test_existing_cat_carrier_and_cat1_unchanged(self):
        image = baseline.generate('https://example.com')
        region = (image.width - 180, 32, 160, 200)
        self.assertEqual(g.capacity_bytes(image, KEY, region), 11956)
        output = self.reload(g.embed(image, '任务G 🐱', KEY, region)['image'])
        self.assertEqual(g.extract(output, KEY, region)['secret'], '任务G 🐱')
        legacy = self.reload(baseline.embed(image, 'CAT1 回归', KEY))
        self.assertEqual(baseline.extract(legacy, KEY)['secret'], 'CAT1 回归')
        self.assertEqual(g.extract(legacy, KEY, region)['status'], 'unknown')
