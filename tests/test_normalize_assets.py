#!/usr/bin/env python3
"""
Test Suite: Normalisasi Asset dan Path Statis
Menguji:
1. Normalisasi {{ asset('https://domain.com/path') }} ke {{ asset('path') }} saat file lokal ada
2. Normalisasi url("https://domain.com/path") di dalam CSS/style
3. Menjaga URL eksternal jika file lokal memang tidak ada (contoh Google Fonts atau CDN)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.normalize_assets import find_public_files, normalize_blade_file


class TestNormalizeAssets(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_assets_")
        self.public_dir = os.path.join(self.test_dir, "public")
        os.makedirs(os.path.join(self.public_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(self.public_dir, "css"), exist_ok=True)

        # Buat dummy asset lokal
        with open(os.path.join(self.public_dir, "images", "logo.png"), "w") as f:
            f.write("logo")
        with open(os.path.join(self.public_dir, "images", "bg.jpg"), "w") as f:
            f.write("bg")
        with open(os.path.join(self.public_dir, "css", "app.css"), "w") as f:
            f.write("body {}")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_public_files(self):
        files = find_public_files(self.public_dir)
        self.assertIn("images/logo.png", files)
        self.assertIn("images/bg.jpg", files)
        self.assertIn("css/app.css", files)

    def test_normalize_asset_function(self):
        public_files = find_public_files(self.public_dir)
        blade_path = os.path.join(self.test_dir, "welcome.blade.php")
        with open(blade_path, "w") as f:
            f.write("""
            <img src="{{ asset('https://legacy-domain.jatimprov.go.id/images/logo.png') }}">
            <link rel="stylesheet" href="{{ asset('https://fonts.googleapis.com/css?family=Nunito') }}">
            """)

        changes = normalize_blade_file(blade_path, public_files)
        self.assertEqual(changes, 1)

        with open(blade_path, "r") as f:
            content = f.read()

        # Logo harus dinormalisasi karena file lokal ada
        self.assertIn("asset('images/logo.png')", content)
        # Google fonts harus dibiarkan karena CDN eksternal
        self.assertIn("fonts.googleapis.com", content)

    def test_normalize_css_url(self):
        public_files = find_public_files(self.public_dir)
        blade_path = os.path.join(self.test_dir, "style.blade.php")
        with open(blade_path, "w") as f:
            f.write("""
            <style>
                body { background-image: url("https://old-domain.com/images/bg.jpg"); }
            </style>
            """)

        changes = normalize_blade_file(blade_path, public_files)
        self.assertEqual(changes, 1)

        with open(blade_path, "r") as f:
            content = f.read()

        self.assertIn("images/bg.jpg", content)
        self.assertNotIn("old-domain.com", content)


if __name__ == "__main__":
    unittest.main()
