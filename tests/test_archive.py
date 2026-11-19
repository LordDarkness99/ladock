#!/usr/bin/env python3
"""
Test Suite: Deteksi dan Ekstraksi Arsip (.zip, .tar.gz)
Menguji:
1. Validasi file ZIP normal
2. Deteksi file ZIP korup
3. Pencegahan Path Traversal (Zip Slip)
"""

import os
import sys
import tempfile
import zipfile
import unittest
from pathlib import Path

# Tambahkan direktori root proyek ke sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.extract_archive import validate_and_extract_zip, is_safe_path, fix_split_laravel_paths


class TestArchiveExtraction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_ladock_archive_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_safe_path_checker(self):
        base = "/tmp/app"
        self.assertTrue(is_safe_path(base, "/tmp/app/index.php"))
        self.assertTrue(is_safe_path(base, "/tmp/app/src/app.js"))
        self.assertFalse(is_safe_path(base, "/tmp/evil.php"))
        self.assertFalse(is_safe_path(base, "/etc/passwd"))
        self.assertFalse(is_safe_path(base, "/tmp/app/../../etc/passwd"))

    def test_valid_zip_extraction(self):
        zip_path = os.path.join(self.test_dir, "valid.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("app/index.php", "<?php echo 'ok'; ?>")
            zf.writestr("app/artisan", "#!/usr/bin/env php")

        dest = os.path.join(self.test_dir, "dest_valid")
        os.makedirs(dest, exist_ok=True)
        validate_and_extract_zip(zip_path, dest)

        self.assertTrue(os.path.isfile(os.path.join(dest, "app", "index.php")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "app", "artisan")))

    def test_corrupt_zip_detection(self):
        corrupt_path = os.path.join(self.test_dir, "corrupt.zip")
        with open(corrupt_path, "wb") as f:
            f.write(b"PK\x03\x04This is not a real zip file body...")

        dest = os.path.join(self.test_dir, "dest_corrupt")
        with self.assertRaises(Exception):
            validate_and_extract_zip(corrupt_path, dest)

    def test_zip_slip_prevention(self):
        slip_zip = os.path.join(self.test_dir, "slip.zip")
        with zipfile.ZipFile(slip_zip, "w") as zf:
            # Entry with path traversal
            zf.writestr("../evil_file.txt", "MALICIOUS CONTENT")
            zf.writestr("safe_file.txt", "SAFE CONTENT")

        dest = os.path.join(self.test_dir, "dest_slip")
        os.makedirs(dest, exist_ok=True)
        validate_and_extract_zip(slip_zip, dest)

        # safe_file should be extracted, evil_file must NOT be extracted outside dest
        self.assertTrue(os.path.isfile(os.path.join(dest, "safe_file.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.test_dir, "evil_file.txt")))

    def test_fix_split_laravel_paths(self):
        proj_dir = os.path.join(self.test_dir, "split_proj")
        pub_dir = os.path.join(proj_dir, "public")
        boot_dir = os.path.join(proj_dir, "bootstrap")
        os.makedirs(pub_dir, exist_ok=True)
        os.makedirs(boot_dir, exist_ok=True)

        index_php = os.path.join(pub_dir, "index.php")
        with open(index_php, "w") as f:
            f.write(
                "<?php\n"
                "require __DIR__.'/../web_app/bootstrap/autoload.php';\n"
                "$app = require_once __DIR__.'/../web_app/bootstrap/start.php';\n"
                "$app->run();\n"
            )

        paths_php = os.path.join(boot_dir, "paths.php")
        with open(paths_php, "w") as f:
            f.write(
                "<?php\n"
                "return array(\n"
                "    'app' => __DIR__.'/../app',\n"
                "    'public' => __DIR__.'/../../public_html',\n"
                ");\n"
            )

        fix_split_laravel_paths(proj_dir, "web_app")

        with open(index_php, "r") as f:
            new_index = f.read()
        self.assertIn("require __DIR__.'/../bootstrap/autoload.php';", new_index)
        self.assertIn("require_once __DIR__.'/../bootstrap/start.php';", new_index)
        self.assertNotIn("web_app", new_index)

        with open(paths_php, "r") as f:
            new_paths = f.read()
        self.assertIn("'public' => __DIR__.'/../public'", new_paths)
        self.assertNotIn("public_html", new_paths)


if __name__ == "__main__":
    unittest.main()
