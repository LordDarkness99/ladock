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

from scripts.extract_archive import validate_and_extract_zip, is_safe_path


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


if __name__ == "__main__":
    unittest.main()
