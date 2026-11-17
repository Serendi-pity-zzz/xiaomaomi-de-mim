"""D integration with the actual mimi baseline, not a replacement CAT1 fixture."""
import copy
import io
import secrets
import unittest

from PIL import Image
import zxingcpp

from core import service
from core.baseline import positions


class MimiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = secrets.token_hex(32)
        cls.public = "https://example.com/mimi/D"
        cls.secret = "D成员真实联调：你好🐱"
        cls.cover = service.generate(cls.public)

    def setUp(self):
        self.stego_key = secrets.token_hex(16)
        self.image = service.embed(self.cover, self.secret, self.stego_key)
        self.region = (self.image.width - 180, 32, 160, 200)
        self.metadata = service.authenticate_image(self.image, self.key, self.region, image_id="mimi-D-test")

    def check_status(self, image, status, metadata=None, key=None):
        result = service.check_image_integrity(image, self.metadata if metadata is None else metadata,
                                               self.key if key is None else key)
        self.assertEqual(result["status"], status)
        return result

    @staticmethod
    def flip(image, position, mask):
        changed = image.copy()
        x, y, channel = position
        pixel = list(changed.getpixel((x, y)))
        pixel[channel] ^= mask
        changed.putpixel((x, y), tuple(pixel))
        return changed

    def test_real_public_scan_and_secret_bytes_and_integrity(self):
        self.assertIn(self.public, [r.text for r in zxingcpp.read_barcodes(self.image)])
        self.assertEqual(service.extract(self.image, self.stego_key)["secret"].encode(), self.secret.encode())
        self.check_status(self.image, "passed")

    def test_empty_chinese_and_capacity_both_algorithms(self):
        for key in ("", self.stego_key):
            for secret in ("", self.secret, "a" * 11960):
                with self.subTest(keyed=bool(key), payload=len(secret.encode())):
                    im = service.embed(self.cover, secret, key)
                    record = service.authenticate_image(im, self.key)
                    self.assertEqual(service.extract(im, key)["secret"].encode(), secret.encode())
                    self.assertEqual(service.check_image_integrity(im, record, self.key)["status"], "passed")

    def test_capacity_overflow_real_baseline(self):
        with self.assertRaises(ValueError):
            service.embed(self.cover, "a" * 11961, self.stego_key)

    def test_png_save_reload_preserves_all_three(self):
        data = io.BytesIO()
        self.image.save(data, format="PNG", compress_level=9)
        data.seek(0)
        with Image.open(data) as reloaded:
            self.check_status(reloaded, "passed")
            self.assertEqual(service.extract(reloaded, self.stego_key)["secret"], self.secret)
            self.assertIn(self.public, [r.text for r in zxingcpp.read_barcodes(reloaded)])

    def test_high_bit_preserves_secret_but_fails_image_authentication(self):
        image = self.flip(self.image, positions(self.image, self.stego_key)[320], 128)
        self.assertEqual(service.extract(image, self.stego_key)["secret"], self.secret)
        self.check_status(image, "failed")

    def test_message_lsb_fails_both_checks(self):
        image = self.flip(self.image, positions(self.image, self.stego_key)[320], 1)
        self.assertEqual(service.extract(image, self.stego_key)["status"], "failed")
        self.check_status(image, "failed")

    def test_unused_carrier_lsb_still_authenticated(self):
        image = self.flip(self.image, positions(self.image, self.stego_key)[-1], 1)
        self.assertEqual(service.extract(image, self.stego_key)["secret"], self.secret)
        self.check_status(image, "failed")

    def test_outside_region_passes_but_full_image_fails(self):
        image = self.flip(self.image, (self.image.width - 1, self.image.height - 1, 0), 128)
        self.check_status(image, "passed")
        full = service.authenticate_image(self.image, self.key)
        self.check_status(image, "failed", metadata=full)

    def test_two_blocks_localized_from_authenticated_digests(self):
        x, y, w, h = self.region
        image = self.flip(self.image, (x, y, 0), 128)
        image = self.flip(image, (x + w - 1, y + h - 1, 1), 128)
        result = self.check_status(image, "failed")
        self.assertEqual(result["failed_blocks"], 2)
        self.assertEqual([b["region"] for b in result["blocks"] if b["status"] == "failed"],
                         [[x, y, 32, 32], [x + 128, y + 192, 32, 8]])

    def test_wrong_integrity_key_unknown(self):
        self.check_status(self.image, "unknown", key=secrets.token_hex(32))

    def test_wrong_stego_key_does_not_invalidate_pixels(self):
        self.assertEqual(service.extract(self.image, self.stego_key + "wrong")["status"], "unknown")
        self.check_status(self.image, "passed")

    def test_metadata_modification_unknown(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["region"][0] -= 1
        self.check_status(self.image, "unknown", metadata=metadata)

    def test_missing_metadata_unknown(self):
        self.assertEqual(service.check_image_integrity(self.image, None, self.key)["status"], "unknown")

    def test_authentication_must_happen_after_embedding(self):
        before = service.authenticate_image(self.cover, self.key, self.region)
        self.check_status(self.image, "failed", metadata=before)

    def test_crop_changes_geometry_without_false_localization(self):
        result = self.check_status(self.image.crop((0, 0, self.image.width - 1, self.image.height)), "failed")
        self.assertFalse(result["localization_available"])


if __name__ == "__main__":
    unittest.main()
