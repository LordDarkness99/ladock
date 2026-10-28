#!/usr/bin/env python3
"""Adapt WordPress database, URL, and rewrite settings to LaDock deployments."""

import argparse
import re
from pathlib import Path


DATABASE_SETTINGS = {
    "DB_NAME": "DB_DATABASE",
    "DB_USER": "DB_USERNAME",
    "DB_PASSWORD": "DB_PASSWORD",
    "DB_HOST": "DB_HOST",
}
SITE_SETTINGS = {
    "WP_HOME": "APP_URL",
    "WP_SITEURL": "APP_URL",
}
PATH_PREFIX_BOOTSTRAP = """// LaDock path-prefix support for reverse-proxy deployments.
$ladock_path_prefix = parse_url((string) getenv('APP_URL'), PHP_URL_PATH);
if ($ladock_path_prefix && $ladock_path_prefix !== '/') {
\t$ladock_request_uri = isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '/';
\tif (strpos($ladock_request_uri, $ladock_path_prefix) !== 0) {
\t\t$_SERVER['REQUEST_URI'] = rtrim($ladock_path_prefix, '/') . '/' . ltrim($ladock_request_uri, '/');
\t}
}
"""


def _literal_setting_pattern(constant: str) -> re.Pattern:
    return re.compile(
        rf"define\s*\(\s*(['\"]){constant}\1\s*,\s*(['\"])(?:\\.|(?!\2).)*\2\s*\)",
        re.DOTALL,
    )


def get_database_name(config_path: Path) -> str:
    content = config_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(
        r"define\s*\(\s*(['\"])DB_NAME\1\s*,\s*(['\"])(.*?)\2\s*\)",
        re.DOTALL,
    )
    match = pattern.search(content)
    return match.group(3).strip() if match else ""


def _normalize_wordpress_rewrite_paths(config_path: Path) -> int:
    htaccess_path = config_path.with_name(".htaccess")
    if not htaccess_path.is_file():
        return 0

    content = htaccess_path.read_text(encoding="utf-8", errors="ignore")
    updated = content
    rewrite_base = re.compile(r"^(\s*RewriteBase\s+)(\S+)", re.MULTILINE)
    updated = rewrite_base.sub(
        lambda match: match.group(0) if match.group(2) == "/" else f"{match.group(1)}/",
        updated,
        count=1,
    )
    rewrite_rule = re.compile(
        r"^(\s*RewriteRule\s+\.\s+)(/\S*/)?index\.php(\s+\[L\])[ \t]*(\r?\n?)$",
        re.MULTILINE,
    )
    updated = rewrite_rule.sub(
        lambda match: (
            match.group(0)
            if match.group(2) in (None, "/")
            else f"{match.group(1)}/index.php{match.group(3)}{match.group(4)}"
        ),
        updated,
        count=1,
    )
    if updated != content:
        htaccess_path.write_text(updated, encoding="utf-8")
        return 1
    return 0


def _normalize_php8_query_comparison(config_path: Path) -> int:
    query_file = config_path.parent / "wp-includes" / "class-wp-query.php"
    if not query_file.is_file():
        return 0

    content = query_file.read_text(encoding="utf-8", errors="ignore")
    legacy_check = "! is_scalar( $qv['p'] ) || $qv['p'] < 0"
    php8_compatible_check = (
        "! is_scalar( $qv['p'] ) || ( '' !== $qv['p'] && $qv['p'] < 0 )"
    )
    if legacy_check not in content:
        return 0

    query_file.write_text(content.replace(legacy_check, php8_compatible_check, 1), encoding="utf-8")
    return 1


def update_wordpress_config(config_path: Path) -> int:
    content = config_path.read_text(encoding="utf-8", errors="ignore")
    updated = content
    changed = 0

    for constant, environment_key in DATABASE_SETTINGS.items():
        pattern = _literal_setting_pattern(constant)
        updated, replacements = pattern.subn(
            f"define('{constant}', getenv('{environment_key}'))",
            updated,
            count=1,
        )
        changed += replacements

    for constant, environment_key in SITE_SETTINGS.items():
        pattern = _literal_setting_pattern(constant)
        updated, replacements = pattern.subn(
            f"define('{constant}', getenv('{environment_key}'))",
            updated,
            count=1,
        )
        changed += replacements
        if not replacements and not re.search(
            rf"define\s*\(\s*(['\"]){constant}\1\s*,",
            updated,
        ):
            updated = updated.replace(
                "$table_prefix",
                f"define('{constant}', getenv('{environment_key}'));\n\n$table_prefix",
                1,
            )
            changed += 1

    if "// LaDock path-prefix support for reverse-proxy deployments." not in updated:
        settings_require = re.search(
            r"^\s*require_once\s*\(\s*ABSPATH\s*\.\s*['\"]wp-settings\.php['\"]\s*\)\s*;",
            updated,
            re.MULTILINE,
        )
        if not settings_require:
            raise ValueError("Titik bootstrap wp-settings.php tidak ditemukan.")
        updated = (
            updated[: settings_require.start()]
            + PATH_PREFIX_BOOTSTRAP
            + "\n"
            + updated[settings_require.start() :]
        )
        changed += 1

    changed += _normalize_wordpress_rewrite_paths(config_path)
    changed += _normalize_php8_query_comparison(config_path)

    if changed:
        config_path.write_text(updated, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--database-name", action="store_true")
    args = parser.parse_args()
    try:
        if args.database_name:
            print(get_database_name(args.config), end="")
            return
        changed = update_wordpress_config(args.config)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if changed:
        print("Konfigurasi WordPress disesuaikan untuk environment LaDock.")
    else:
        print("Konfigurasi WordPress sudah sesuai untuk environment LaDock.")


if __name__ == "__main__":
    main()
