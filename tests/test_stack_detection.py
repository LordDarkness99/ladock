#!/usr/bin/env python3
"""
Test Suite: Deteksi Stack dan Dependensi (detect_stack.py)
Menguji deteksi:
1. PHP Laravel
2. Node.js Express / Next.js
3. Python Django / Flask
4. Go
"""

import os
import sys
import tempfile
import json
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.detect_stack import detect_stack


class TestStackDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_ladock_stack_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_laravel_detection(self):
        app_path = os.path.join(self.test_dir, "laravel_app")
        os.makedirs(app_path)
        with open(os.path.join(app_path, "artisan"), "w") as f:
            f.write("#!/usr/bin/env php")
        with open(os.path.join(app_path, "composer.json"), "w") as f:
            json.dump({
                "require": {
                    "php": "^8.2",
                    "laravel/framework": "^10.0",
                    "ext-pdo": "*",
                    "ext-curl": "*"
                }
            }, f)

        res = detect_stack(app_path)
        self.assertEqual(res["primary_language"], "PHP")
        self.assertEqual(res["framework"], "Laravel")
        self.assertEqual(res["runtime_version"], "8.2")
        self.assertIn("curl", res["php_extensions"])
        self.assertIn("pdo", res["php_extensions"])

    def test_nodejs_express_detection(self):
        app_path = os.path.join(self.test_dir, "express_app")
        os.makedirs(app_path)
        with open(os.path.join(app_path, "package.json"), "w") as f:
            json.dump({
                "name": "my-express-api",
                "dependencies": { "express": "^4.18.2" },
                "engines": { "node": "20.x" }
            }, f)
        with open(os.path.join(app_path, "package-lock.json"), "w") as f:
            f.write("{}")

        res = detect_stack(app_path)
        self.assertEqual(res["primary_language"], "Node.js")
        self.assertEqual(res["framework"], "Express")
        self.assertEqual(res["package_manager"], "npm")
        self.assertEqual(res["lock_file"], "package-lock.json")

    def test_python_django_detection(self):
        app_path = os.path.join(self.test_dir, "django_app")
        os.makedirs(app_path)
        with open(os.path.join(app_path, "manage.py"), "w") as f:
            f.write("#!/usr/bin/env python")
        with open(os.path.join(app_path, "requirements.txt"), "w") as f:
            f.write("django>=4.2\npsycopg2-binary>=2.9\n")

        res = detect_stack(app_path)
        self.assertEqual(res["primary_language"], "Python")
        self.assertEqual(res["framework"], "Django")
        self.assertEqual(res["package_manager"], "pip")

    def test_go_detection(self):
        app_path = os.path.join(self.test_dir, "go_app")
        os.makedirs(app_path)
        with open(os.path.join(app_path, "go.mod"), "w") as f:
            f.write("module example.com/my-app\n\ngo 1.22\n")
        with open(os.path.join(app_path, "main.go"), "w") as f:
            f.write("package main\nfunc main() {}\n")

        res = detect_stack(app_path)
        self.assertEqual(res["primary_language"], "Go")
        self.assertEqual(res["runtime_version"], "1.22")


if __name__ == "__main__":
    unittest.main()
