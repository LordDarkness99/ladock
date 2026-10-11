#!/usr/bin/env python3
"""
Comprehensive Stack & Dependency Detector for LaDock
Mendeteksi bahasa, framework, package manager, versi runtime,
ekstensi PHP, web server, dan jenis database.
Menyimpan hasil ke stack.json.

Usage:
    python3 detect_stack.py <app_directory> [--output /path/to/stack.json]
"""

import os
import sys
import json
import re
import datetime
from pathlib import Path


def read_json_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return {}


def read_text_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def detect_php_version_from_composer(composer_data):
    require = composer_data.get("require", {})
    php_constraint = require.get("php", "")
    if not php_constraint:
        return "8.4"

    # Match common constraints
    if re.search(r"8\.[4-9]", php_constraint):
        return "8.4"
    if re.search(r"8\.3", php_constraint):
        return "8.3"
    if re.search(r"8\.2", php_constraint):
        return "8.2"
    if re.search(r"8\.1", php_constraint):
        return "8.1"
    if re.search(r"8\.0", php_constraint):
        return "8.0"
    if re.search(r"7\.4", php_constraint):
        return "7.4"
    if re.search(r"7\.3", php_constraint):
        return "7.3"
    if re.search(r"7\.2", php_constraint):
        return "7.2"
    if re.search(r"7\.[0-1]", php_constraint):
        return "7.1"
    if re.search(r"5\.[4-6]", php_constraint):
        return "5.6"

    return "8.2"


def detect_stack(app_dir: str) -> dict:
    app_path = Path(app_dir).resolve()
    if not app_path.is_dir():
        return {"error": f"Directory not found: {app_dir}"}

    files_in_root = [f.name for f in app_path.iterdir() if f.is_file()]
    dirs_in_root = [d.name for d in app_path.iterdir() if d.is_dir()]

    stack = {
        "primary_language": "Unknown",
        "runtime_version": "Unknown",
        "framework": "None",
        "framework_version": "Unknown",
        "package_manager": "None",
        "lock_file": "None",
        "php_extensions": [],
        "web_server": "Apache",
        "database": "MySQL",
        "all_languages": [],
        "entrypoint": "",
        "detected_at": datetime.datetime.now().isoformat()
    }

    # 1. Deteksi Bahasa & Runtime
    languages = []
    
    # PHP detection
    has_composer = "composer.json" in files_in_root
    has_artisan = "artisan" in files_in_root
    has_php_files = any(f.endswith(".php") for f in files_in_root) or (app_path / "public" / "index.php").is_file()
    
    # Node detection
    has_package_json = "package.json" in files_in_root
    
    # Python detection
    has_py_files = "requirements.txt" in files_in_root or "Pipfile" in files_in_root or "pyproject.toml" in files_in_root or "manage.py" in files_in_root
    
    # Go detection
    has_go = "go.mod" in files_in_root or any(f.endswith(".go") for f in files_in_root)
    
    # Ruby detection
    has_ruby = "Gemfile" in files_in_root
    
    # Java detection
    has_java = "pom.xml" in files_in_root or "build.gradle" in files_in_root or "build.gradle.kts" in files_in_root

    if has_composer or has_artisan or has_php_files:
        languages.append("PHP")
    if has_package_json:
        languages.append("JavaScript/TypeScript (Node.js)")
    if has_py_files:
        languages.append("Python")
    if has_go:
        languages.append("Go")
    if has_ruby:
        languages.append("Ruby")
    if has_java:
        languages.append("Java")

    stack["all_languages"] = languages

    # 2. Detail Spesifik per Bahasa Utama
    composer_data = {}
    if has_composer:
        composer_data = read_json_file(app_path / "composer.json")

    package_data = {}
    if has_package_json:
        package_data = read_json_file(app_path / "package.json")

    # A. PHP STACK
    if "PHP" in languages:
        stack["primary_language"] = "PHP"
        stack["web_server"] = "Apache"

        # Versi PHP
        if composer_data:
            stack["runtime_version"] = detect_php_version_from_composer(composer_data)
        else:
            stack["runtime_version"] = "8.2"

        # Ekstensi PHP yang dibutuhkan
        php_exts = set(["pdo", "pdo_mysql", "mbstring", "openssl", "tokenizer", "xml", "ctype", "json", "curl", "zip"])
        if composer_data:
            for req in list(composer_data.get("require", {}).keys()) + list(composer_data.get("require-dev", {}).keys()):
                if req.startswith("ext-"):
                    php_exts.add(req[4:])
        stack["php_extensions"] = sorted(list(php_exts))

        # Package manager & lock file
        if (app_path / "composer.lock").is_file():
            stack["package_manager"] = "composer"
            stack["lock_file"] = "composer.lock"
        elif has_composer:
            stack["package_manager"] = "composer"
            stack["lock_file"] = "None (composer.json only)"

        # Framework detection
        if has_artisan or "laravel/framework" in composer_data.get("require", {}):
            stack["framework"] = "Laravel"
            stack["entrypoint"] = "public/index.php"
            # Versi Laravel
            req_ver = composer_data.get("require", {}).get("laravel/framework", "")
            if req_ver:
                stack["framework_version"] = req_ver
        elif (app_path / "wp-config.php").is_file() or (app_path / "wp-settings.php").is_file():
            stack["framework"] = "WordPress"
            stack["entrypoint"] = "index.php"
        elif (app_path / "system" / "core" / "CodeIgniter.php").is_file() or (app_path / "app" / "Config" / "App.php").is_file() or "spark" in files_in_root:
            stack["framework"] = "CodeIgniter"
            stack["entrypoint"] = "public/index.php" if (app_path / "public" / "index.php").is_file() else "index.php"
        elif (app_path / "bin" / "console").is_file() or "symfony/framework-bundle" in composer_data.get("require", {}):
            stack["framework"] = "Symfony"
            stack["entrypoint"] = "public/index.php"
        else:
            stack["framework"] = "Native PHP"
            stack["entrypoint"] = "public/index.php" if (app_path / "public" / "index.php").is_file() else "index.php"

    # B. NODE.JS STACK (jika bukan PHP atau Node merupakan primary)
    elif "JavaScript/TypeScript (Node.js)" in languages:
        stack["primary_language"] = "Node.js"
        stack["web_server"] = "Node.js Built-in"
        node_engine = package_data.get("engines", {}).get("node", "20.x")
        stack["runtime_version"] = node_engine

        # Package manager
        if (app_path / "pnpm-lock.yaml").is_file():
            stack["package_manager"] = "pnpm"
            stack["lock_file"] = "pnpm-lock.yaml"
        elif (app_path / "yarn.lock").is_file():
            stack["package_manager"] = "yarn"
            stack["lock_file"] = "yarn.lock"
        elif (app_path / "package-lock.json").is_file():
            stack["package_manager"] = "npm"
            stack["lock_file"] = "package-lock.json"
        else:
            stack["package_manager"] = "npm"

        deps = {**package_data.get("dependencies", {}), **package_data.get("devDependencies", {})}
        if "next" in deps:
            stack["framework"] = "Next.js"
            stack["framework_version"] = deps["next"]
        elif "express" in deps:
            stack["framework"] = "Express"
            stack["framework_version"] = deps["express"]
        elif "nest" in deps or "@nestjs/core" in deps:
            stack["framework"] = "NestJS"
        else:
            stack["framework"] = "Node.js Native"

    # C. PYTHON STACK
    elif "Python" in languages:
        stack["primary_language"] = "Python"
        stack["web_server"] = "Gunicorn/Uvicorn"
        stack["runtime_version"] = "3.11"

        if (app_path / "poetry.lock").is_file():
            stack["package_manager"] = "poetry"
            stack["lock_file"] = "poetry.lock"
        elif (app_path / "Pipfile.lock").is_file() or (app_path / "Pipfile").is_file():
            stack["package_manager"] = "pipenv"
            stack["lock_file"] = "Pipfile.lock"
        else:
            stack["package_manager"] = "pip"
            stack["lock_file"] = "requirements.txt" if (app_path / "requirements.txt").is_file() else "None"

        req_content = read_text_file(app_path / "requirements.txt")
        if "manage.py" in files_in_root or "django" in req_content.lower():
            stack["framework"] = "Django"
            stack["entrypoint"] = "manage.py"
        elif "flask" in req_content.lower():
            stack["framework"] = "Flask"
            stack["entrypoint"] = "app.py"
        elif "fastapi" in req_content.lower():
            stack["framework"] = "FastAPI"
            stack["entrypoint"] = "main.py"
        else:
            stack["framework"] = "Python Script/App"

    # D. GO STACK
    elif "Go" in languages:
        stack["primary_language"] = "Go"
        stack["package_manager"] = "go modules"
        stack["lock_file"] = "go.sum" if (app_path / "go.sum").is_file() else "go.mod"
        go_mod = read_text_file(app_path / "go.mod")
        m = re.search(r"go\s+([0-9\.]+)", go_mod)
        if m:
            stack["runtime_version"] = m.group(1)
        stack["web_server"] = "Go HTTP"

    # 3. Deteksi Database
    env_content = read_text_file(app_path / ".env") or read_text_file(app_path / ".env.example")
    if "pgsql" in env_content.lower() or "postgres" in env_content.lower():
        stack["database"] = "PostgreSQL"
    elif "sqlite" in env_content.lower():
        stack["database"] = "SQLite"
    elif "mongodb" in env_content.lower():
        stack["database"] = "MongoDB"
    else:
        stack["database"] = "MySQL"

    return stack


def main():
    if len(sys.argv) < 2:
        print("Usage: detect_stack.py <app_directory> [--output /path/to/stack.json]")
        sys.exit(1)

    app_dir = sys.argv[1]
    output_file = None

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    stack_info = detect_stack(app_dir)

    if output_file:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(stack_info, f, indent=2)
        print(f"Stack saved to {output_file}")

    print(json.dumps(stack_info, indent=2))


if __name__ == "__main__":
    main()
