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


RUNTIME_DEFAULTS = {
    "PHP": "8.2",
    "Node.js": "20",
    "Python": "3.11",
    "Go": "1.22",
    "Ruby": "3.3",
    "Java": "21",
}


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


def _version_from_constraint(value, java=False):
    if java:
        value = re.sub(r"(?<=\d)_(?=\d)", ".", value)
    match = re.search(r"(?<![A-Za-z0-9])v?(\d+(?:\.\d+){0,2})", value)
    if not match:
        return ""
    version = match.group(1).rstrip(".")
    if java:
        if version.startswith("1."):
            return version.split(".", 1)[1]
        return version.split(".", 1)[0]
    return version


def _tool_version(app_path, tool_names):
    content = read_text_file(app_path / ".tool-versions")
    for line in content.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in tool_names:
            return parts[1], ".tool-versions"
    return "", ""


def detect_dockerfile_runtime(app_path):
    """Infer the deployed runtime from the last recognized base image."""
    content = read_text_file(Path(app_path) / "Dockerfile")
    if not content:
        return "", "", "", ""

    arg_defaults = {
        name: value.strip("\"'")
        for name, value in re.findall(
            r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\s#]+)",
            content,
            re.MULTILINE,
        )
    }

    def expand_arg(match):
        name = match.group(1) or match.group(2)
        return arg_defaults.get(name, match.group(0))

    content = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-[^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)", expand_arg, content)
    detected_runtime = ("", "", "", "")
    for line in content.splitlines():
        match = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", line, re.IGNORECASE)
        if not match:
            continue
        image_ref = match.group(1).split("@", 1)[0]
        image_name, separator, tag = image_ref.rpartition(":")
        if not separator:
            image_name, tag = image_ref, ""
        image_name = image_name.rsplit("/", 1)[-1].lower()

        language = ""
        version = ""
        if image_name in {"php", "node", "python", "ruby", "golang", "go"}:
            language = {
                "php": "PHP",
                "node": "Node.js",
                "python": "Python",
                "ruby": "Ruby",
                "golang": "Go",
                "go": "Go",
            }[image_name]
            version = _version_from_constraint(tag)
        elif image_name in {"eclipse-temurin", "openjdk"}:
            language = "Java"
            version = _version_from_constraint(tag, java=True)
        elif image_name == "maven":
            java_version = re.search(r"(?:temurin|jdk|openjdk)-(\d+)", tag, re.IGNORECASE)
            if java_version:
                language = "Java"
                version = java_version.group(1)
        elif image_name == "gradle":
            java_version = re.search(r"jdk(\d+)", tag, re.IGNORECASE)
            if java_version:
                language = "Java"
                version = java_version.group(1)

        if language:
            detected_runtime = (language, version or "Unknown", "Dockerfile", tag)
    return detected_runtime


def _first_version(app_path, candidates, java=False):
    for filename, pattern in candidates:
        content = read_text_file(app_path / filename)
        if not content:
            continue
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        constraint = match.group(1).strip().strip("\"'")
        version = _version_from_constraint(constraint, java=java)
        if version:
            return version, filename, constraint
    return "", "", ""


def detect_runtime_version(language, app_path, composer_data=None, package_data=None):
    """Return a deployable version, its source file, and the original constraint."""
    app_path = Path(app_path)
    composer_data = composer_data or {}
    package_data = package_data or {}

    docker_language, docker_version, docker_source, docker_constraint = detect_dockerfile_runtime(app_path)
    if docker_language == language:
        return docker_version, docker_source, docker_constraint

    version_files = {
        "PHP": [(".php-version", r"^\s*([^\s#]+)")],
        "Node.js": [
            (".nvmrc", r"^\s*([^\s#]+)"),
            (".node-version", r"^\s*([^\s#]+)"),
        ],
        "Python": [
            (".python-version", r"^\s*([^\s#]+)"),
            ("runtime.txt", r"^\s*python[-= ]?([^\s#]+)"),
        ],
        "Go": [(".go-version", r"^\s*([^\s#]+)")],
        "Ruby": [(".ruby-version", r"^\s*([^\s#]+)")],
        "Java": [
            (".java-version", r"^\s*([^\s#]+)"),
            (".sdkmanrc", r"^\s*java\s*=\s*([^\s#]+)"),
        ],
    }

    if language in version_files:
        version, source, constraint = _first_version(
            app_path, version_files[language], java=language == "Java"
        )
        if version:
            return version, source, constraint

    tool_names = {
        "PHP": {"php"},
        "Node.js": {"node", "nodejs"},
        "Python": {"python", "python3"},
        "Go": {"golang", "go"},
        "Ruby": {"ruby"},
        "Java": {"java"},
    }
    if language in tool_names:
        constraint, source = _tool_version(app_path, tool_names[language])
        version = _version_from_constraint(constraint, java=language == "Java")
        if version:
            return version, source, constraint

    if language == "PHP":
        constraint = composer_data.get("require", {}).get("php", "")
        if constraint:
            return detect_php_version_from_composer(composer_data), "composer.json", constraint
        platform_version = composer_data.get("config", {}).get("platform", {}).get("php", "")
        if platform_version:
            version = _version_from_constraint(platform_version)
            if version:
                return version, "composer.json", platform_version
    elif language == "Node.js":
        constraint = package_data.get("engines", {}).get("node", "")
        if constraint:
            version = _version_from_constraint(constraint)
            if version:
                return version, "package.json", constraint
    elif language == "Python":
        candidates = [
            ("pyproject.toml", r"(?:requires-python|python)\s*=\s*[\"']([^\"']+)"),
            ("Pipfile", r"python(?:_full)?_version\s*=\s*[\"']([^\"']+)"),
        ]
        version, source, constraint = _first_version(app_path, candidates)
        if version:
            return version, source, constraint
    elif language == "Go":
        content = read_text_file(app_path / "go.mod")
        match = re.search(r"^\s*go\s+([0-9.]+)", content, re.MULTILINE)
        if match:
            return match.group(1), "go.mod", match.group(1)
    elif language == "Ruby":
        version, source, constraint = _first_version(
            app_path, [("Gemfile", r"^\s*ruby\s+[\"']([^\"']+)")]
        )
        if version:
            return version, source, constraint
    elif language == "Java":
        candidates = [
            ("pom.xml", r"<(?:java\.version|maven\.compiler\.(?:release|source))>\s*([^<]+)"),
            (
                "build.gradle",
                r"(?:JavaVersion\.VERSION_|JavaLanguageVersion\.of\s*\(|sourceCompatibility\s*=\s*)[\"']?(\d+(?:[._]\d+)?)",
            ),
            (
                "build.gradle.kts",
                r"(?:JavaVersion\.VERSION_|JavaLanguageVersion\.of\s*\(|sourceCompatibility\s*=\s*)[\"']?(\d+(?:[._]\d+)?)",
            ),
        ]
        version, source, constraint = _first_version(app_path, candidates, java=True)
        if version:
            return version, source, constraint

    return RUNTIME_DEFAULTS.get(language, "Unknown"), "detector_default", ""


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
        return RUNTIME_DEFAULTS["PHP"]
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
        "runtime_version_source": "unknown",
        "runtime_version_constraint": "",
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
    docker_language, _, _, _ = detect_dockerfile_runtime(app_path)
    docker_language_entry = {
        "Node.js": "JavaScript/TypeScript (Node.js)"
    }.get(docker_language, docker_language)

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
    if docker_language_entry and docker_language_entry not in languages:
        languages.insert(0, docker_language_entry)
    elif docker_language_entry in languages:
        languages.remove(docker_language_entry)
        languages.insert(0, docker_language_entry)

    stack["all_languages"] = languages

    # 2. Detail Spesifik per Bahasa Utama
    composer_data = {}
    if has_composer:
        composer_data = read_json_file(app_path / "composer.json")

    package_data = {}
    if has_package_json:
        package_data = read_json_file(app_path / "package.json")

    # A. PHP STACK
    if docker_language == "PHP" or (not docker_language and "PHP" in languages):
        stack["primary_language"] = "PHP"
        stack["web_server"] = "Apache"

        version, source, constraint = detect_runtime_version(
            "PHP", app_path, composer_data=composer_data
        )
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint

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
    elif docker_language == "Node.js" or (
        not docker_language and "JavaScript/TypeScript (Node.js)" in languages
    ):
        stack["primary_language"] = "Node.js"
        stack["web_server"] = "Node.js Built-in"
        version, source, constraint = detect_runtime_version(
            "Node.js", app_path, package_data=package_data
        )
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint

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
    elif docker_language == "Python" or (not docker_language and "Python" in languages):
        stack["primary_language"] = "Python"
        stack["web_server"] = "Gunicorn/Uvicorn"
        version, source, constraint = detect_runtime_version("Python", app_path)
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint

        if (app_path / "poetry.lock").is_file():
            stack["package_manager"] = "poetry"
            stack["lock_file"] = "poetry.lock"
        elif (app_path / "Pipfile.lock").is_file() or (app_path / "Pipfile").is_file():
            stack["package_manager"] = "pipenv"
            stack["lock_file"] = "Pipfile.lock"
        else:
            stack["package_manager"] = "pip"
            stack["lock_file"] = "requirements.txt" if (app_path / "requirements.txt").is_file() else "None"

        req_content = "\n".join(
            read_text_file(app_path / filename)
            for filename in ("requirements.txt", "pyproject.toml", "Pipfile")
        )
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
    elif docker_language == "Go" or (not docker_language and "Go" in languages):
        stack["primary_language"] = "Go"
        stack["package_manager"] = "go modules"
        stack["lock_file"] = "go.sum" if (app_path / "go.sum").is_file() else "go.mod"
        version, source, constraint = detect_runtime_version("Go", app_path)
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint
        stack["web_server"] = "Go HTTP"

    # E. RUBY STACK
    elif docker_language == "Ruby" or (not docker_language and "Ruby" in languages):
        stack["primary_language"] = "Ruby"
        stack["package_manager"] = "bundler"
        stack["lock_file"] = "Gemfile.lock" if (app_path / "Gemfile.lock").is_file() else "Gemfile"
        version, source, constraint = detect_runtime_version("Ruby", app_path)
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint
        stack["web_server"] = "Rack"
        gemfile = read_text_file(app_path / "Gemfile").lower()
        if "rails" in gemfile:
            stack["framework"] = "Ruby on Rails"
            stack["entrypoint"] = "bin/rails"
        elif "sinatra" in gemfile:
            stack["framework"] = "Sinatra"
        else:
            stack["framework"] = "Ruby App"

    # F. JAVA STACK
    elif docker_language == "Java" or (not docker_language and "Java" in languages):
        stack["primary_language"] = "Java"
        stack["package_manager"] = "maven" if (app_path / "pom.xml").is_file() else "gradle"
        if (app_path / "pom.xml").is_file():
            stack["lock_file"] = "pom.xml"
        elif (app_path / "gradle.lockfile").is_file():
            stack["lock_file"] = "gradle.lockfile"
        elif (app_path / "build.gradle.kts").is_file():
            stack["lock_file"] = "build.gradle.kts"
        else:
            stack["lock_file"] = "build.gradle"
        version, source, constraint = detect_runtime_version("Java", app_path)
        stack["runtime_version"] = version
        stack["runtime_version_source"] = source
        stack["runtime_version_constraint"] = constraint
        stack["web_server"] = "Java"
        java_manifests = "\n".join(
            read_text_file(app_path / name)
            for name in ("pom.xml", "build.gradle", "build.gradle.kts")
        ).lower()
        stack["framework"] = "Spring Boot" if "spring-boot" in java_manifests else "Java App"

    # 3. Deteksi Database
    env_content = read_text_file(app_path / ".env")
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
