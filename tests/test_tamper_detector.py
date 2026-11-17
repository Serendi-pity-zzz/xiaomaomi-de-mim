import copy
import io
import json
import secrets
import unittest

from PIL import Image

from core.tamper_detector import create_metadata, verify


class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = secrets.token_hex(32)
        cls.other_key = secrets.token_hex(32)

    def setUp(self):
        self.image = Image.new("RGB", (65, 49), (121, 132, 143))
        self.region = (5, 7, 53, 39)
        self.metadata = create_metadata(self.image, self.key, self.region, 16, image_id="测试图-D")

    def test_unchanged_passes(self):
        result = verify(self.image, self.metadata, self.key)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["metadata_authenticated"])
        self.assertEqual(result["failed_blocks"], 0)
        self.assertEqual(result["coverage"]["region"], list(self.region))

    def test_default_covers_full_image(self):
        result = verify(self.image, create_metadata(self.image, self.key), self.key)
        self.assertTrue(result["coverage"]["full_image"])

    def test_json_utf8_roundtrip(self):
        metadata = json.loads(json.dumps(self.metadata, ensure_ascii=False))
        self.assertEqual(verify(self.image, metadata, self.key)["status"], "passed")

    def test_png_lossless_resave(self):
        stream = io.BytesIO()
        self.image.save(stream, format="PNG", compress_level=9)
        stream.seek(0)
        with Image.open(stream) as image:
            self.assertEqual(verify(image, self.metadata, self.key)["status"], "passed")

    def test_every_rgb_bit_is_covered(self):
        for channel in range(3):
            for bit in range(8):
                with self.subTest(channel=channel, bit=bit):
                    image = self.image.copy()
                    pixel = list(image.getpixel((13, 19)))
                    pixel[channel] ^= 1 << bit
                    image.putpixel((13, 19), tuple(pixel))
                    result = verify(image, self.metadata, self.key)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual([b["region"] for b in result["blocks"] if b["status"] == "failed"],
                                     [[5, 7, 16, 16]])

    def test_two_distant_blocks_localized(self):
        image = self.image.copy()
        image.putpixel((5, 7), (0, 0, 0))
        image.putpixel((57, 45), (0, 0, 0))
        result = verify(image, self.metadata, self.key)
        failed = [b["region"] for b in result["blocks"] if b["status"] == "failed"]
        self.assertEqual(failed, [[5, 7, 16, 16], [53, 39, 5, 7]])

    def test_edge_blocks_cover_exact_region(self):
        blocks = self.metadata["blocks"]
        self.assertEqual(len(blocks), 12)
        self.assertEqual(sum(b["region"][2] * b["region"][3] for b in blocks), 53 * 39)
        self.assertEqual(blocks[-1]["region"], [53, 39, 5, 7])

    def test_region_inside_boundaries_fail(self):
        for point in [(5, 7), (57, 7), (5, 45), (57, 45)]:
            with self.subTest(point=point):
                image = self.image.copy()
                image.putpixel(point, (0, 0, 0))
                self.assertEqual(verify(image, self.metadata, self.key)["status"], "failed")

    def test_outside_half_open_region_passes(self):
        for point in [(4, 7), (58, 7), (5, 6), (5, 46), (0, 0)]:
            with self.subTest(point=point):
                image = self.image.copy()
                image.putpixel(point, (0, 0, 0))
                self.assertEqual(verify(image, self.metadata, self.key)["status"], "passed")

    def test_full_image_detects_previously_uncovered_pixel(self):
        metadata = create_metadata(self.image, self.key)
        image = self.image.copy()
        image.putpixel((0, 0), (0, 0, 0))
        self.assertEqual(verify(image, metadata, self.key)["status"], "failed")

    def test_dimensions_mismatch_has_no_localization(self):
        result = verify(self.image.crop((0, 0, 64, 49)), self.metadata, self.key)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "dimensions_mismatch")
        self.assertFalse(result["localization_available"])
        self.assertEqual(result["blocks"], [])

    def test_wrong_key_unknown_and_no_coverage(self):
        result = verify(self.image, self.metadata, self.other_key)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["coverage"])
        self.assertEqual(result["blocks"], [])

    def test_empty_or_wrong_type_key_unknown(self):
        for key in ["", None, 5, "x" * 4097]:
            with self.subTest(kind=type(key).__name__):
                self.assertEqual(verify(self.image, self.metadata, key)["status"], "unknown")

    def test_creator_rejects_empty_key(self):
        with self.assertRaises(ValueError):
            create_metadata(self.image, "")

    def test_unknown_metadata_shapes(self):
        for metadata in [None, {}, [], "invalid", {"version": "CAT1"}]:
            self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")

    def test_modified_metadata_cannot_establish_tampering(self):
        for field, value in [("image_id", "other"), ("tag", "0" * 64),
                             ("region", [6, 7, 53, 39]), ("block_size", 32)]:
            with self.subTest(field=field):
                metadata = copy.deepcopy(self.metadata)
                metadata[field] = value
                result = verify(self.image, metadata, self.key)
                self.assertEqual(result["status"], "unknown")
                self.assertFalse(result["metadata_authenticated"])
                self.assertIsNone(result["coverage"])

    def test_replacing_digest_without_mac_fails_authentication(self):
        modified = self.image.copy()
        modified.putpixel((6, 8), (0, 0, 0))
        fresh = create_metadata(modified, self.key, self.region, 16, image_id="测试图-D")
        forged = copy.deepcopy(self.metadata)
        forged["blocks"] = fresh["blocks"]
        self.assertEqual(verify(modified, forged, self.key)["status"], "unknown")

    def test_deleted_reordered_duplicate_and_extra_blocks_unknown(self):
        variants = []
        for mode in ["delete", "reverse", "duplicate", "extra"]:
            metadata = copy.deepcopy(self.metadata)
            if mode == "delete":
                metadata["blocks"].pop()
            elif mode == "reverse":
                metadata["blocks"].reverse()
            elif mode == "duplicate":
                metadata["blocks"][1] = metadata["blocks"][0]
            else:
                metadata["blocks"].append(metadata["blocks"][0])
            variants.append(metadata)
        for metadata in variants:
            self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")

    def test_extra_fields_and_versions_rejected(self):
        for name, value in [("extra", 1), ("version", "CAT-INTEGRITY-99"), ("algorithm", "md5")]:
            metadata = copy.deepcopy(self.metadata)
            metadata[name] = value
            self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")

    def test_malformed_digest_and_tag_rejected(self):
        for value in [None, "g" * 64, "f" * 63, "f" * 65, 12, "é" * 64]:
            metadata = copy.deepcopy(self.metadata)
            metadata["tag"] = value
            self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")
            metadata = copy.deepcopy(self.metadata)
            metadata["blocks"][0]["sha256"] = value
            self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")

    def test_untrusted_huge_dimensions_rejected(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["image"]["width"] = 10 ** 50
        self.assertEqual(verify(self.image, metadata, self.key)["status"], "unknown")

    def test_non_rgb_is_unknown_with_authenticated_metadata(self):
        for mode in ["RGBA", "L", "P"]:
            result = verify(self.image.convert(mode), self.metadata, self.key)
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["metadata_authenticated"])
            self.assertFalse(result["localization_available"])

    def test_non_image_is_unknown(self):
        self.assertEqual(verify(None, self.metadata, self.key)["status"], "unknown")

    def test_invalid_regions_rejected(self):
        regions = [(-1, 0, 1, 1), (0, 0, 0, 1), (0, 0, 1, -1), (64, 0, 2, 1),
                   (0, 48, 1, 2), (True, 0, 1, 1), (0, 0, 1.0, 1), (0, 0, 1), "bad"]
        for region in regions:
            with self.subTest(region=region), self.assertRaises(ValueError):
                create_metadata(self.image, self.key, region)

    def test_invalid_block_sizes_rejected(self):
        for size in [0, -1, 4097, True, 1.0, None]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                create_metadata(self.image, self.key, block_size=size)

    def test_too_many_blocks_rejected(self):
        with self.assertRaises(ValueError):
            create_metadata(Image.new("RGB", (129, 129)), self.key, block_size=1)

    def test_large_image_rejected(self):
        with self.assertRaises(ValueError):
            create_metadata(Image.new("RGB", (2001, 2000)), self.key)

    def test_one_pixel_region_and_large_block(self):
        metadata = create_metadata(self.image, self.key, (64, 48, 1, 1), 4096)
        self.assertEqual(metadata["blocks"][0]["region"], [64, 48, 1, 1])
        self.assertEqual(verify(self.image, metadata, self.key)["status"], "passed")

    def test_creator_rejects_non_rgb(self):
        with self.assertRaises(ValueError):
            create_metadata(self.image.convert("RGBA"), self.key)

    def test_invalid_image_id_rejected(self):
        for value in ["", "x" * 129, 10]:
            with self.assertRaises(ValueError):
                create_metadata(self.image, self.key, image_id=value)

    def test_inputs_are_not_mutated(self):
        pixels = self.image.tobytes()
        before = copy.deepcopy(self.metadata)
        verify(self.image, self.metadata, self.key)
        create_metadata(self.image, self.key)
        self.assertEqual(self.image.tobytes(), pixels)
        self.assertEqual(self.metadata, before)

    def test_returned_region_does_not_alias_metadata(self):
        result = verify(self.image, self.metadata, self.key)
        result["coverage"]["region"][0] = 99
        result["blocks"][0]["region"][0] = 99
        self.assertEqual(self.metadata["region"][0], 5)
        self.assertEqual(self.metadata["blocks"][0]["region"][0], 5)

    def test_no_key_or_pixel_bytes_in_metadata(self):
        serialized = json.dumps(self.metadata)
        self.assertNotIn(self.key, serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("pixels", serialized)

    def test_json_key_order_does_not_change_authentication(self):
        metadata = dict(reversed(list(self.metadata.items())))
        self.assertEqual(verify(self.image, metadata, self.key)["status"], "passed")

    def test_replay_requires_external_expected_record_selection(self):
        # Explicit boundary: verify does not maintain a trusted image_id registry.
        another = Image.new("RGB", self.image.size, (1, 2, 3))
        record = create_metadata(another, self.key, image_id="different-image")
        self.assertEqual(verify(another, record, self.key)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
