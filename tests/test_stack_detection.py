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
        self.assertEqual(res["runtime_version_source"], "composer.json")
        self.assertEqual(res["runtime_version_constraint"], "^8.2")
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
        self.assertEqual(res["runtime_version"], "20")
        self.assertEqual(res["runtime_version_source"], "package.json")
        self.assertEqual(res["runtime_version_constraint"], "20.x")

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
        self.assertEqual(res["runtime_version_source"], "go.mod")

    def test_runtime_version_files_override_manifest_defaults(self):
        cases = [
            ("php_app", ".php-version", "8.1.27", "PHP", "8.1.27"),
            ("node_app", ".nvmrc", "v22.4.1", "Node.js", "22.4.1"),
            ("python_app", ".python-version", "3.12.3", "Python", "3.12.3"),
            ("go_app", ".go-version", "1.23.1", "Go", "1.23.1"),
            ("ruby_app", ".ruby-version", "3.2.4", "Ruby", "3.2.4"),
            ("java_app", ".java-version", "21.0.2", "Java", "21"),
        ]
        markers = {
            "PHP": "index.php",
            "Node.js": "package.json",
            "Python": "requirements.txt",
            "Go": "go.mod",
            "Ruby": "Gemfile",
            "Java": "pom.xml",
        }

        for dirname, version_file, version, language, expected_version in cases:
            with self.subTest(language=language):
                app_path = Path(self.test_dir) / dirname
                app_path.mkdir()
                (app_path / version_file).write_text(version + "\n", encoding="utf-8")
                marker = app_path / markers[language]
                if language == "Node.js":
                    marker.write_text('{"name":"test"}\n', encoding="utf-8")
                else:
                    marker.write_text("", encoding="utf-8")

                result = detect_stack(str(app_path))

                self.assertEqual(result["primary_language"], language)
                self.assertEqual(result["runtime_version"], expected_version)
                self.assertEqual(result["runtime_version_source"], version_file)

    def test_python_and_java_versions_can_be_read_from_manifests(self):
        python_app = Path(self.test_dir) / "python_manifest"
        python_app.mkdir()
        (python_app / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.10,<3.13"\n', encoding="utf-8"
        )
        result = detect_stack(str(python_app))
        self.assertEqual(result["runtime_version"], "3.10")
        self.assertEqual(result["runtime_version_source"], "pyproject.toml")
        self.assertEqual(result["runtime_version_constraint"], ">=3.10,<3.13")

        java_app = Path(self.test_dir) / "java_manifest"
        java_app.mkdir()
        (java_app / "pom.xml").write_text(
            "<project><properties><maven.compiler.release>17</maven.compiler.release>"
            "</properties></project>",
            encoding="utf-8",
        )
        result = detect_stack(str(java_app))
        self.assertEqual(result["primary_language"], "Java")
        self.assertEqual(result["runtime_version"], "17")
        self.assertEqual(result["runtime_version_source"], "pom.xml")

    def test_java_legacy_version_and_env_example_are_handled_safely(self):
        java_app = Path(self.test_dir) / "java8_app"
        java_app.mkdir()
        (java_app / "build.gradle").write_text(
            "sourceCompatibility = JavaVersion.VERSION_1_8\n", encoding="utf-8"
        )
        result = detect_stack(str(java_app))
        self.assertEqual(result["runtime_version"], "8")

        php_app = Path(self.test_dir) / "php_env_app"
        php_app.mkdir()
        (php_app / "index.php").write_text("<?php", encoding="utf-8")
        (php_app / ".env.example").write_text("DB_CONNECTION=pgsql\n", encoding="utf-8")
        result = detect_stack(str(php_app))
        self.assertEqual(result["database"], "MySQL")

    def test_project_dockerfile_runtime_overrides_other_runtime_hints(self):
        app_path = Path(self.test_dir) / "dockerfile_node_app"
        app_path.mkdir()
        (app_path / "Dockerfile").write_text(
            "ARG NODE_VERSION=20.12.2\nFROM node:${NODE_VERSION}-alpine\n",
            encoding="utf-8",
        )
        (app_path / ".nvmrc").write_text("v18.19.0\n", encoding="utf-8")
        (app_path / "package.json").write_text(
            '{"engines":{"node":"18.x"}}', encoding="utf-8"
        )
        (app_path / "composer.json").write_text(
            '{"require":{"php":"^8.1"}}', encoding="utf-8"
        )

        result = detect_stack(str(app_path))

        self.assertEqual(result["primary_language"], "Node.js")
        self.assertEqual(result["runtime_version"], "20.12.2")
        self.assertEqual(result["runtime_version_source"], "Dockerfile")
        self.assertIn("JavaScript/TypeScript (Node.js)", result["all_languages"])
        self.assertNotIn("Node.js", result["all_languages"])

    def test_dockerfile_runtime_is_detected_without_a_language_manifest(self):
        app_path = Path(self.test_dir) / "dockerfile_go_app"
        app_path.mkdir()
        (app_path / "Dockerfile").write_text(
            "FROM golang:1.23.1-alpine AS build\n"
            "FROM alpine:3.20\n",
            encoding="utf-8",
        )

        result = detect_stack(str(app_path))

        self.assertEqual(result["primary_language"], "Go")
        self.assertEqual(result["runtime_version"], "1.23.1")
        self.assertEqual(result["runtime_version_source"], "Dockerfile")

    def test_dockerfile_uses_the_last_recognized_runtime_stage(self):
        app_path = Path(self.test_dir) / "dockerfile_multi_runtime_app"
        app_path.mkdir()
        (app_path / "Dockerfile").write_text(
            "FROM node:22 AS assets\nFROM php:8.2-apache\n",
            encoding="utf-8",
        )
        (app_path / "package.json").write_text('{"name":"assets"}', encoding="utf-8")
        (app_path / "composer.json").write_text(
            '{"require":{"php":"^8.1"}}', encoding="utf-8"
        )

        result = detect_stack(str(app_path))

        self.assertEqual(result["primary_language"], "PHP")
        self.assertEqual(result["runtime_version"], "8.2")
        self.assertEqual(result["runtime_version_source"], "Dockerfile")


if __name__ == "__main__":
    unittest.main()
