import contextlib
import io
import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from d_integrity_cli import load_metadata, main
from core.tamper_detector import create_metadata


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.png = self.root / "image.png"
        self.record = self.root / "record.json"
        self.image = Image.new("RGB", (12, 10), (1, 2, 3))
        self.image.save(self.png)
        self.key = secrets.token_hex(32)
        self.env = patch.dict(os.environ, {"D_TEST_KEY": self.key})
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, *args):
        output = io.StringIO()
        error = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main([*map(str, args), "--key-env", "D_TEST_KEY"])
        self.assertNotIn(self.key, output.getvalue() + error.getvalue())
        return code, output.getvalue(), error.getvalue()

    def write_record(self):
        self.record.write_text(json.dumps(create_metadata(self.image, self.key)), encoding="utf-8")

    def test_create_and_verify(self):
        code, _, _ = self.invoke("create", self.png, self.record)
        self.assertEqual(code, 0)
        code, output, _ = self.invoke("verify", self.png, self.record)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["status"], "passed")

    def test_create_preserves_existing_record(self):
        self.record.write_text("do not replace", encoding="utf-8")
        self.assertEqual(self.invoke("create", self.png, self.record)[0], 2)
        self.assertEqual(self.record.read_text(), "do not replace")

    def test_modified_pixels_exit_one(self):
        self.write_record()
        self.image.putpixel((0, 0), (4, 5, 6))
        self.image.save(self.png)
        code, output, _ = self.invoke("verify", self.png, self.record)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["status"], "failed")

    def test_missing_record_unknown(self):
        code, output, _ = self.invoke("verify", self.png, self.record)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["status"], "unknown")

    def test_wrong_key_unknown(self):
        self.write_record()
        with patch.dict(os.environ, {"D_TEST_KEY": secrets.token_hex(32)}):
            code, output, _ = self.invoke("verify", self.png, self.record)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["status"], "unknown")

    def test_broken_png_unknown(self):
        self.write_record()
        self.png.write_bytes(b"not a PNG")
        self.assertEqual(self.invoke("verify", self.png, self.record)[0], 2)

    def test_wrong_image_modes_unknown(self):
        self.write_record()
        for mode in ["RGBA", "L", "P"]:
            self.image.convert(mode).save(self.png)
            self.assertEqual(self.invoke("verify", self.png, self.record)[0], 2)

    def test_jpeg_not_silently_converted(self):
        self.write_record()
        jpeg = self.root / "image.jpg"
        self.image.save(jpeg)
        self.assertEqual(self.invoke("verify", jpeg, self.record)[0], 2)

    def test_bad_metadata_unknown(self):
        for value in ["{", "[]", "null", '{"tag":1,"tag":2}']:
            self.record.write_text(value, encoding="utf-8")
            self.assertEqual(self.invoke("verify", self.png, self.record)[0], 2)

    def test_duplicate_json_keys_rejected(self):
        self.record.write_text('{"x":1,"x":2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_metadata(self.record)

    def test_invalid_create_region(self):
        self.assertEqual(self.invoke("create", self.png, self.record, "--region", "0", "0", "13", "1")[0], 2)
        self.assertFalse(self.record.exists())

    def test_empty_env_key_unknown(self):
        with patch.dict(os.environ, {"D_TEST_KEY": ""}):
            code, output, _ = self.invoke("verify", self.png, self.record)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
