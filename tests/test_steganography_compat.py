"""B 的 CAT1 模块与组长原 core/baseline.py 的双向兼容回归。

上一轮只在交互式会话里手工核对过 6 组输出，没有留下可重复执行的用例。
本文件把该检查固化：任何一次改动若悄悄改变封包、位序或置乱规则，
都会被这里的像素向量和交叉提取断言拦下，旧 CAT1 图不会静默失读。
"""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".deps"))

from PIL import Image

from core import baseline
from core import steganography


KEYS = ("", "演示密钥")
SECRETS = ("", "你好🐱", "a" * steganography.CAPACITY_BYTES)
CROSS_SECRETS = ("", "你好🐱", "来自喵星人的问候🐱")


class Cat1CompatibilityTests(unittest.TestCase):
    def setUp(self):
        # 240x240 是 CAT1 允许的最小尺寸；纯色载体避免引入二维码生成依赖。
        self.carrier = Image.new("RGB", (240, 240), (128, 133, 199))
        self.region = (60, 32, 160, 200)

    def test_embed_pixels_match_baseline_for_six_combinations(self):
        for key in KEYS:
            for secret in SECRETS:
                with self.subTest(keyed=bool(key), payload_bytes=len(secret.encode("utf-8"))):
                    legacy = baseline.embed(self.carrier, secret, key)
                    current = steganography.embed(
                        self.carrier, secret, key, self.region
                    )["image"]
                    self.assertEqual(current.size, legacy.size)
                    self.assertEqual(current.tobytes(), legacy.tobytes())

    def test_cross_extraction_after_png_roundtrip(self):
        """旧模块写的图新模块能读，新模块写的图旧模块也能读。"""
        for key in KEYS:
            for secret in CROSS_SECRETS:
                with self.subTest(keyed=bool(key), payload_bytes=len(secret.encode("utf-8"))):
                    legacy = baseline.embed(self.carrier, secret, key)
                    current = steganography.embed(
                        self.carrier, secret, key, self.region
                    )["image"]

                    legacy_buffer = io.BytesIO()
                    legacy.save(legacy_buffer, format="PNG")
                    legacy_buffer.seek(0)
                    current_buffer = io.BytesIO()
                    current.save(current_buffer, format="PNG")
                    current_buffer.seek(0)

                    with Image.open(legacy_buffer) as old_png, Image.open(current_buffer) as new_png:
                        by_new = steganography.extract(old_png, key, self.region)
                        by_old = baseline.extract(new_png, key)

                    self.assertEqual(by_new["status"], "passed")
                    self.assertEqual(by_new["secret"].encode("utf-8"), secret.encode("utf-8"))
                    self.assertEqual(by_old["status"], "passed")
                    self.assertEqual(by_old["secret"].encode("utf-8"), secret.encode("utf-8"))

    def test_capacity_error_matches_baseline(self):
        oversized = "a" * (steganography.CAPACITY_BYTES + 1)
        with self.assertRaises(ValueError):
            baseline.embed(self.carrier, oversized)
        with self.assertRaises(ValueError):
            steganography.embed(self.carrier, oversized, region=self.region)


if __name__ == "__main__":
    unittest.main()
