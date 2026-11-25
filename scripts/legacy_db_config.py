#!/usr/bin/env python3
"""Adapt legacy PHP database settings to LaDock service environments."""

import argparse
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .env_config import read_env_file
except ImportError:
    from env_config import read_env_file


def _literal_php_setting(path: Path, array_name: str, key: str) -> str:
    content = path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        rf"^\s*\${array_name}\s*\[\s*['\"]default['\"]\s*\]\s*"
        rf"\[\s*['\"]{re.escape(key)}['\"]\s*\]\s*=\s*(['\"])(.*?)\1\s*;",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if match:
        return match.group(2).strip()

    pattern_arr = re.compile(
        rf"^\s*['\"]{re.escape(key)}['\"]\s*=>\s*(['\"])(.*?)\1\s*,?",
        re.MULTILINE,
    )
    match_arr = pattern_arr.search(content)
    return match_arr.group(2).strip() if match_arr else ""


def _symfony_dsn(config_path: Path) -> str:
    content = config_path.read_text(encoding="utf-8", errors="ignore")
    environment = ""
    fallback_dsn = ""
    in_environment = False
    in_propel = False
    in_param = False
    for line in content.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if not stripped or stripped.startswith("#"):
            continue
        if indent == 0:
            in_environment = stripped.endswith(":")
            environment = stripped[:-1] if in_environment else ""
            in_propel = False
            in_param = False
        elif in_environment and indent == 2:
            in_propel = stripped == "propel:"
            in_param = False
        elif in_environment and in_propel and indent == 4:
            in_param = stripped == "param:"
        elif in_environment and in_propel and in_param and indent >= 6:
            match = re.match(r"dsn\s*:\s*(.*?)\s*(?:#.*)?$", stripped)
            if match:
                dsn = match.group(1).strip("\"'")
                if environment == "all":
                    return dsn
                if not fallback_dsn:
                    fallback_dsn = dsn
    return fallback_dsn


def get_legacy_database_name(service_dir: Path) -> str:
    wordpress_config = service_dir / "wp-config.php"
    if wordpress_config.is_file():
        content = wordpress_config.read_text(encoding="utf-8", errors="ignore")
        match = re.search(
            r"define\s*\(\s*(['\"])DB_NAME\1\s*,\s*(['\"])(.*?)\2\s*\)",
            content,
            re.DOTALL,
        )
        if match:
            return match.group(3).strip()

    adodb_configs = (
        service_dir / "lib/includes/database.php",
        service_dir / "public/lib/includes/database.php",
    )
    for config_path in adodb_configs:
        if config_path.is_file():
            name = _literal_php_setting(config_path, "database", "name")
            if name:
                return name

    codeigniter_config = service_dir / "application/config/database.php"
    if codeigniter_config.is_file():
        name = _literal_php_setting(codeigniter_config, "db", "database")
        if name:
            return name

    laravel4_config = service_dir / "app/config/database.php"
    if laravel4_config.is_file():
        content = laravel4_config.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"['\"]database['\"]\s*=>\s*['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1).strip()

    laravel5_config = service_dir / "config/database.php"
    if laravel5_config.is_file():
        content = laravel5_config.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"['\"]database['\"]\s*=>\s*(?:env\([^,]+,\s*)?['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1).strip()

    symfony_config = service_dir / "config/databases.yml"
    if symfony_config.is_file():
        dsn = _symfony_dsn(symfony_config)
        if dsn.startswith("mysql://"):
            return urlsplit(dsn).path.lstrip("/").split("?", 1)[0]
        match = re.search(r"(?:dbname|database)=([^;]+)", dsn, re.IGNORECASE)
        if match:
            return match.group(1).strip("\"'")
    return ""


def _replace_php_assignment(content: str, array_name: str, key: str, value: str):
    pattern = re.compile(
        rf"^(?P<prefix>[ \t]*\${array_name}\s*\[\s*['\"]default['\"]\s*\]\s*"
        rf"\[\s*['\"]{re.escape(key)}['\"]\s*\]\s*=\s*)"
        r"(?P<value>[^;\r\n]*)(?P<suffix>;[^\r\n]*)$",
        re.MULTILINE,
    )
    updated, count = pattern.subn(lambda match: f"{match.group('prefix')}{value}{match.group('suffix')}", content)
    if count:
        return updated, count

    pattern_arr = re.compile(
        rf"^(?P<prefix>[ \t]*['\"]{re.escape(key)}['\"]\s*=>\s*)"
        r"(?P<value>[^,\r\n]*)(?P<suffix>,?[^\r\n]*)$",
        re.MULTILINE,
    )
    return pattern_arr.subn(lambda match: f"{match.group('prefix')}{value}{match.group('suffix')}", content)


def update_codeigniter_config(service_dir: Path) -> bool:
    config_path = service_dir / "application/config/database.php"
    if not config_path.is_file():
        return False

    content = config_path.read_text(encoding="utf-8", errors="ignore")
    updated = content
    changed = False
    db_values = {
        "hostname": "getenv('DB_HOST') ?: 'localhost'",
        "username": "getenv('DB_USERNAME') ?: (getenv('DB_USER') ?: '')",
        "password": "getenv('DB_PASSWORD') ?: ''",
        "database": "getenv('DB_DATABASE') ?: ''",
    }
    found = set()
    for key, value in db_values.items():
        updated, count = _replace_php_assignment(updated, "db", key, value)
        if count:
            found.add(key)
    if found != set(db_values):
        missing = ", ".join(sorted(set(db_values) - found))
        raise ValueError(f"Konfigurasi CodeIgniter tidak lengkap di {config_path}; tidak ditemukan: {missing}")

    config_config = service_dir / "application/config/config.php"
    if config_config.is_file():
        config_content = config_config.read_text(encoding="utf-8", errors="ignore")
        base_url_pattern = re.compile(
            r"^(?P<prefix>[ \t]*\$config\s*\[\s*['\"]base_url['\"]\s*\]\s*=\s*)"
            r"(?P<value>[^;\r\n]*)(?P<suffix>;[^\r\n]*)$",
            re.MULTILINE,
        )
        config_updated, base_url_count = base_url_pattern.subn(
            lambda match: (
                f"{match.group('prefix')}rtrim(getenv('APP_URL') ?: 'http://localhost', '/') . '/'"
                f"{match.group('suffix')}"
            ),
            config_content,
            count=1,
        )
        if not base_url_count:
            raise ValueError(f"Konfigurasi base_url CodeIgniter tidak ditemukan di {config_config}")
        if config_updated != config_content:
            config_config.write_text(config_updated, encoding="utf-8")
            changed = True

    if updated != content:
        config_path.write_text(updated, encoding="utf-8")
        changed = True
    return changed


def update_laravel_config(service_dir: Path, env_path: Path) -> bool:
    env_values = read_env_file(env_path)
    required = ("DB_HOST", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD")
    missing = [key for key in required if not env_values.get(key)]
    if missing:
        return False

    config_dirs = [d for d in [service_dir / "app/config", service_dir / "config"] if d.is_dir()]
    if not config_dirs:
        return False

    changed = False
    for c_dir in config_dirs:
        for config_path in c_dir.glob("**/database.php"):
            content = config_path.read_text(encoding="utf-8", errors="ignore")
            original = content

            def repl_mysql_block(match):
                block = match.group(0)
                is_modern = c_dir.name == "config"
                if is_modern:
                    block = re.sub(r"(['\"]host['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\)|env\([^)]+\))", rf"\1env('DB_HOST', {json.dumps(env_values['DB_HOST'])})", block)
                    block = re.sub(r"(['\"]database['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\)|env\([^)]+\))", rf"\1env('DB_DATABASE', {json.dumps(env_values['DB_DATABASE'])})", block)
                    block = re.sub(r"(['\"]username['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\)|env\([^)]+\))", rf"\1env('DB_USERNAME', {json.dumps(env_values['DB_USERNAME'])})", block)
                    block = re.sub(r"(['\"]password['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\)|env\([^)]+\))", rf"\1env('DB_PASSWORD', {json.dumps(env_values['DB_PASSWORD'])})", block)
                    if env_values.get("DB_PORT"):
                        if "'port'" in block or '"port"' in block:
                            block = re.sub(r"(['\"]port['\"]\s*=>\s*)(['\"][^'\"]*['\"]|\d+|getenv\([^)]+\)|env\([^)]+\))", rf"\1env('DB_PORT', {int(env_values['DB_PORT'])})", block)
                else:
                    block = re.sub(r"(['\"]host['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\))", rf"\1{json.dumps(env_values['DB_HOST'])}", block)
                    block = re.sub(r"(['\"]database['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\))", rf"\1{json.dumps(env_values['DB_DATABASE'])}", block)
                    block = re.sub(r"(['\"]username['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\))", rf"\1{json.dumps(env_values['DB_USERNAME'])}", block)
                    block = re.sub(r"(['\"]password['\"]\s*=>\s*)(['\"][^'\"]*['\"]|getenv\([^)]+\))", rf"\1{json.dumps(env_values['DB_PASSWORD'])}", block)
                    if env_values.get("DB_PORT"):
                        if "'port'" in block or '"port"' in block:
                            block = re.sub(r"(['\"]port['\"]\s*=>\s*)(['\"][^'\"]*['\"]|\d+|getenv\([^)]+\))", rf"\1{int(env_values['DB_PORT'])}", block)
                return block

            updated = re.sub(
                r"['\"]mysql['\"]\s*=>\s*(?:array\s*\(|\[)[\s\S]*?(?:\)|\])",
                repl_mysql_block,
                content,
            )

            if updated != original:
                config_path.write_text(updated, encoding="utf-8")
                changed = True
    return changed


update_laravel4_config = update_laravel_config


def update_symfony1_config(config_path: Path, env_path: Path) -> bool:
    env_values = read_env_file(env_path)
    required = ("DB_HOST", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD")
    missing = [key for key in required if not env_values.get(key)]
    if missing:
        raise ValueError(f"Variabel koneksi DB tidak lengkap di {env_path}: {', '.join(missing)}")

    content = config_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines(keepends=True)
    in_environment = False
    in_propel = False
    in_param = False
    found = set()
    dsn = (
        f"mysql:host={env_values['DB_HOST']}"
        + (f";port={env_values['DB_PORT']}" if env_values.get("DB_PORT") else "")
        + f";dbname={env_values['DB_DATABASE']}"
    )
    values = {
        "dsn": dsn,
        "username": env_values["DB_USERNAME"],
        "password": env_values["DB_PASSWORD"],
    }
    updated_lines = []
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped and not stripped.startswith("#"):
            if indent == 0:
                in_environment = stripped.endswith(":")
                in_propel = False
                in_param = False
            elif in_environment and indent == 2:
                in_propel = stripped == "propel:"
                in_param = False
            elif in_environment and in_propel and indent == 4:
                in_param = stripped == "param:"
            elif in_environment and in_propel and in_param and indent >= 6:
                match = re.match(r"(?P<prefix>\s*(?P<key>dsn|username|password)\s*:\s*).*$", line)
                if match:
                    key = match.group("key")
                    line_ending = "\n" if line.endswith("\n") else ""
                    line = f"{match.group('prefix')}{json.dumps(values[key])}{line_ending}"
                    found.add(key)
        updated_lines.append(line)

    if found != set(values):
        missing = ", ".join(sorted(set(values) - found))
        raise ValueError(f"Konfigurasi database Symfony 1 tidak lengkap di {config_path}; tidak ditemukan: {missing}")

    updated = "".join(updated_lines)
    if updated != content:
        config_path.write_text(updated, encoding="utf-8")
        return True
    return False


def disable_local_https_redirects(service_dir: Path) -> bool:
    """Disable hardcoded HTTPS redirects in root index.php or entrypoints for local HTTP deployment."""
    changed = False
    pattern = re.compile(
        r"if\s*\([^;{}]*\bHTTPS\b[^;{}]*\)\s*\{[^}]*?(?:Location|\$location|https).*?\}",
        re.DOTALL | re.IGNORECASE,
    )
    for candidate in [service_dir / "index.php", service_dir / "web/index.php", service_dir / "public/index.php"]:
        if not candidate.is_file():
            continue
        content = candidate.read_text(encoding="utf-8", errors="ignore")
        if "HTTPS" in content and ("Location" in content or "location" in content or "https" in content):
            updated = pattern.sub("// [LaDock] HTTPS redirect disabled for local HTTP deployment", content)
            if updated != content:
                candidate.write_text(updated, encoding="utf-8")
                changed = True
    return changed


def update_symfony1_local_security(service_dir: Path) -> bool:
    """Allow HTTP only for the app-specific Symfony 1 configs in a local deployment."""
    app_dir = service_dir / "apps"
    if not app_dir.is_dir():
        return False

    pattern = re.compile(
        r"^(?P<prefix>[ \t]*is_secure\s*:\s*)true(?P<suffix>[ \t]*(?:#.*)?)$",
        re.MULTILINE | re.IGNORECASE,
    )
    changed = False
    for config_path in sorted(app_dir.rglob("security.yml")):
        content = config_path.read_text(encoding="utf-8", errors="ignore")
        updated, count = pattern.subn(r"\g<prefix>false\g<suffix>", content)
        if count:
            config_path.write_text(updated, encoding="utf-8")
            changed = True
    return changed


def update_symfony1_user_group_compatibility(service_dir: Path) -> bool:
    """Delegate the legacy Symfony user group accessor to its stored user record."""
    user_class = service_dir / "apps/backend/lib/myUser.class.php"
    if not user_class.is_file():
        return False

    content = user_class.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"\bfunction\s+getGroupId\s*\(", content, re.IGNORECASE):
        return False

    class_pattern = re.compile(
        r"(?P<prefix>\bclass\s+myUser\b[^{]*\{)",
        re.IGNORECASE,
    )
    addition = (
        "\n        public function getGroupId()\n"
        "        {\n"
        "            $user = $this->getAttribute('user');\n"
        "            return is_object($user) && method_exists($user, 'getGroupId')\n"
        "                ? $user->getGroupId()\n"
        "                : null;\n"
        "        }\n"
    )
    updated, count = class_pattern.subn(
        lambda match: match.group("prefix") + addition,
        content,
        count=1,
    )
    if not count:
        raise ValueError(f"Kelas myUser tidak ditemukan di {user_class}")
    user_class.write_text(updated, encoding="utf-8")
    return True


def clear_symfony1_cache(service_dir: Path) -> bool:
    """Remove generated Symfony cache so updated DB/security settings take effect."""
    cache_dir = service_dir / "cache"
    if not cache_dir.is_dir() or cache_dir.is_symlink():
        return False

    entries = list(cache_dir.iterdir())
    for entry in entries:
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)
    return bool(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    name_parser = commands.add_parser("database-name")
    name_parser.add_argument("--service-dir", required=True, type=Path)

    adapt_parser = commands.add_parser("adapt")
    adapt_parser.add_argument("--service-dir", required=True, type=Path)
    adapt_parser.add_argument("--env", required=True, type=Path)
    adapt_parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Disable Symfony 1 secure-only routes in the local service copy.",
    )

    args = parser.parse_args()
    try:
        if args.command == "database-name":
            print(get_legacy_database_name(args.service_dir), end="")
            return

        service_dir = args.service_dir
        symfony_config = service_dir / "config/databases.yml"
        changed = False
        if (service_dir / "application/config/database.php").is_file():
            changed = update_codeigniter_config(service_dir) or changed
        if (service_dir / "app/config/database.php").is_file():
            changed = update_laravel4_config(service_dir, args.env) or changed
        if symfony_config.is_file():
            changed = update_symfony1_config(symfony_config, args.env) or changed
        if args.allow_http:
            changed = update_symfony1_local_security(service_dir) or changed
            changed = disable_local_https_redirects(service_dir) or changed
            changed = update_symfony1_user_group_compatibility(service_dir) or changed
            changed = clear_symfony1_cache(service_dir) or changed
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if changed:
        print("Konfigurasi database legacy disesuaikan dengan environment service.")


if __name__ == "__main__":
    main()
