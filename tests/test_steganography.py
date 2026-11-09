"""B's CAT1 LSB protocol and PNG recovery tests."""

import hashlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PIL import Image

from core.steganography import CAPACITY_BYTES, capacity_bytes, embed, extract, positions


class SteganographyTests(unittest.TestCase):
    def setUp(self):
        self.carrier = Image.new("RGB", (240, 240), (128, 133, 199))
        self.region = (60, 32, 160, 200)

    def test_png_roundtrip_for_empty_chinese_emoji_and_boundary(self):
        for key in ("", "demo-key"):
            for secret in ("", "你好🐱", "a" * CAPACITY_BYTES):
                with self.subTest(keyed=bool(key), bytes=len(secret.encode("utf-8"))):
                    original = self.carrier.tobytes()
                    result = embed(self.carrier, secret, key, self.region)
                    self.assertEqual(self.carrier.tobytes(), original)
                    self.assertEqual(result["capacity_bytes"], 11960)
                    self.assertEqual(result["metadata"]["format"], "CAT1")
                    self.assertEqual(result["metadata"]["region"], self.region)
                    self.assertEqual(
                        result["metadata"]["algorithm"],
                        "lsb-keyed" if key else "lsb-sequential",
                    )
                    self.assertEqual(result["metadata"]["payload_bytes"], len(secret.encode("utf-8")))
                    buffer = io.BytesIO()
                    result["image"].save(buffer, format="PNG")
                    buffer.seek(0)
                    with Image.open(buffer) as reopened:
                        self.assertEqual(reopened.tobytes(), result["image"].tobytes())
                        recovered = extract(reopened, key, self.region)
                    self.assertEqual(recovered["status"], "passed")
                    self.assertEqual(recovered["secret"].encode("utf-8"), secret.encode("utf-8"))

    def test_byte_capacity_and_fixed_region(self):
        self.assertEqual(capacity_bytes(self.carrier, self.region), 11960)
        self.assertEqual(len(positions(self.carrier)), 96000)
        self.assertEqual(positions(self.carrier)[0], (60, 32, 0))
        self.assertEqual(positions(self.carrier)[-1], (219, 231, 2))
        embed(self.carrier, "猫" * 3986)
        with self.assertRaisesRegex(ValueError, "11960"):
            embed(self.carrier, "猫" * 3987)
        with self.assertRaisesRegex(ValueError, "新版协议"):
            embed(self.carrier, "x", region=(0, 0, 160, 200))
        with self.assertRaisesRegex(ValueError, "新版协议"):
            extract(self.carrier, region=(0, 0, 160, 200))

    def test_pixels_outside_cat1_region_are_unchanged(self):
        image = embed(self.carrier, "你好🐱")["image"]
        for point in ((0, 0), (59, 32), (220, 32), (60, 31), (60, 232)):
            with self.subTest(point=point):
                self.assertEqual(image.getpixel(point), self.carrier.getpixel(point))

    def test_wrong_key_and_unmarked_carrier_are_unknown(self):
        self.assertEqual(extract(self.carrier)["status"], "unknown")
        image = embed(self.carrier, "secret", "right-key")["image"]
        result = extract(image, "wrong-key")
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["secret"])

    def test_message_tamper_is_failed(self):
        image = embed(self.carrier, "secret", "demo-key")["image"]
        x, y, channel = positions(image, "demo-key")[40 * 8]
        color = list(image.getpixel((x, y)))
        color[channel] ^= 1
        image.putpixel((x, y), tuple(color))
        result = extract(image, "demo-key")
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["secret"])

    def test_header_damage_is_not_mistaken_for_success(self):
        image = embed(self.carrier, "secret")["image"]
        x, y, channel = positions(image)[4 * 8]
        color = list(image.getpixel((x, y)))
        color[channel] ^= 1
        image.putpixel((x, y), tuple(color))
        self.assertEqual(extract(image)["status"], "failed")
        image = embed(self.carrier, "secret")["image"]
        x, y, channel = positions(image)[0]
        color = list(image.getpixel((x, y)))
        color[channel] ^= 1
        image.putpixel((x, y), tuple(color))
        self.assertEqual(extract(image)["status"], "unknown")

    def test_truncated_png_is_unknown(self):
        image = embed(self.carrier, "secret")["image"]
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        truncated = buffer.getvalue()[:60]
        # 不同 Pillow 版本判定截断 PNG 的时机不同：有的在 Image.open 就抛
        # OSError，有的到像素加载时才抛。两者都不能被当成"提取成功"。
        try:
            with Image.open(io.BytesIO(truncated)) as damaged:
                result = extract(damaged)
        except OSError:
            return
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["secret"])

    def test_unreadable_pixels_are_unknown(self):
        """确定性覆盖 extract 的 OSError 分支，不依赖 Pillow 的惰性加载细节。"""
        from unittest import mock

        with mock.patch.object(
            Image.Image, "convert", side_effect=OSError("像素数据截断")
        ):
            result = extract(self.carrier)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["secret"])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            capacity_bytes(Image.new("RGB", (199, 240)))
        with self.assertRaises(TypeError):
            embed(None, "x")
        with self.assertRaises(TypeError):
            embed(self.carrier, 123)
        with self.assertRaises(TypeError):
            extract(self.carrier, None)
        with self.assertRaises(ValueError):
            embed(self.carrier, "\ud800")

    def test_legacy_pixel_vectors(self):
        vectors = {
            "": "f2ed297306c6fe7ec9a8104605c160148c44ffce0566ec58b91482b8fa14d782",
            "demo-key": "5a7aaaea0e5b5f7900229ed20e28ece5ba63d0cff1f14a278393b72d4d1f910e",
        }
        for key, expected in vectors.items():
            with self.subTest(keyed=bool(key)):
                image = embed(self.carrier, "你好🐱", key)["image"]
                self.assertEqual(hashlib.sha256(image.tobytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
