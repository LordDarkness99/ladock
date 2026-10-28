#!/usr/bin/env python3
"""Patch legacy ADOdb and PHP 8-incompatible string offsets in deployed apps."""

import argparse
import re
from pathlib import Path

if __package__:
    from .env_config import read_env_file
else:
    from env_config import read_env_file


SETTING_PATTERN = re.compile(
    r"^(?P<prefix>\s*\$database\s*\[\s*['\"]default['\"]\s*\]"
    r"\s*\[\s*['\"](?P<key>host|user|pass|name|driver)['\"]\s*\]\s*=\s*)"
    r"(?P<quote>['\"])(?P<value>(?:\\.|.)*?)(?P=quote)(?P<suffix>\s*;.*)$"
)
PHP_CURLY_OFFSET_PATTERN = re.compile(
    r"(?P<value>\$[A-Za-z_][A-Za-z0-9_]*(?:(?:->)[A-Za-z_][A-Za-z0-9_]*|\[[^\]\r\n]+\])*)"
    r"\{(?P<offset>[^{}\r\n]+)\}"
)


def php_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def update_adodb_config(config_path: Path, env_path: Path) -> bool:
    env_values = read_env_file(env_path)
    db_values = {
        "host": env_values.get("DB_HOST", ""),
        "user": env_values.get("DB_USERNAME") or env_values.get("DB_USER", ""),
        "pass": env_values.get("DB_PASSWORD", ""),
        "name": env_values.get("DB_DATABASE", ""),
        "driver": "mysqli",
    }
    missing = [key for key, value in db_values.items() if key != "pass" and not value]
    if missing:
        raise ValueError(f"Variabel koneksi DB tidak lengkap di {env_path}: {', '.join(missing)}")

    original_lines = config_path.read_text(encoding="utf-8").splitlines()
    updated_lines = []
    found: set[str] = set()
    for line in original_lines:
        match = SETTING_PATTERN.match(line)
        if not match:
            updated_lines.append(line)
            continue
        key = match.group("key")
        found.add(key)
        updated_lines.append(
            f"{match.group('prefix')}{php_string(db_values[key])}{match.group('suffix')}"
        )

    required = {"host", "user", "pass", "name", "driver"}
    if not required.issubset(found):
        absent = ", ".join(sorted(required - found))
        raise ValueError(f"Konfigurasi ADOdb tidak lengkap di {config_path}; tidak ditemukan: {absent}")

    changed = updated_lines != original_lines
    if changed:
        config_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return changed


def update_adodb_mysqli_driver(driver_path: Path) -> bool:
    source = driver_path.read_text(encoding="utf-8")
    signature = re.compile(
        r"(?P<prefix>\bfunction\s+MetaIndexes\s*\(\s*\$table\s*,\s*\$primary\s*=\s*FALSE)\s*\)",
        re.IGNORECASE,
    )
    updated, count = signature.subn(r"\g<prefix>, $owner = false)", source, count=1)
    if count == 0:
        if re.search(
            r"\bfunction\s+MetaIndexes\s*\(\s*\$table\s*,\s*\$primary\s*=\s*FALSE\s*,\s*\$owner\s*=",
            source,
            re.IGNORECASE,
        ):
            updated = source
        else:
            raise ValueError(f"Tanda tangan MetaIndexes tidak dikenali di {driver_path}")

    result_count_lines = (
        "\t\t$this->_numOfRows = $ADODB_COUNTRECS ? @mysqli_num_rows($this->_queryID) : -1;\n"
        "\t\t$this->_numOfFields = @mysqli_num_fields($this->_queryID);"
    )
    guarded_result_count_lines = (
        "\t\tif (!($this->_queryID instanceof mysqli_result)) {\n"
        "\t\t\t$this->_numOfRows = 0;\n"
        "\t\t\t$this->_numOfFields = 0;\n"
        "\t\t\treturn;\n"
        "\t\t}\n"
        + result_count_lines
    )
    if guarded_result_count_lines in updated:
        pass
    elif result_count_lines in updated:
        updated = updated.replace(result_count_lines, guarded_result_count_lines, 1)
    else:
        raise ValueError(f"Inisialisasi hasil query tidak dikenali di {driver_path}")

    lines = updated.splitlines(keepends=True)
    guarded_lines = []
    found_free_result = False
    for line in lines:
        if line.strip() != "mysqli_free_result($this->_queryID);":
            guarded_lines.append(line)
            continue
        found_free_result = True
        if guarded_lines and guarded_lines[-1].strip() == "if ($this->_queryID instanceof mysqli_result) {":
            guarded_lines.append(line)
            continue
        indentation = line[: len(line) - len(line.lstrip())]
        guarded_lines.extend(
            [
                f"{indentation}if ($this->_queryID instanceof mysqli_result) {{\n",
                f"{indentation}\t{line.lstrip()}",
                f"{indentation}}}\n",
            ]
        )
    if not found_free_result:
        raise ValueError(f"Penutupan hasil query tidak dikenali di {driver_path}")
    updated = "".join(guarded_lines)

    changed = updated != source
    if changed:
        driver_path.write_text(updated, encoding="utf-8")
    return changed


def update_php_curly_offsets(root: Path) -> list[Path]:
    changed_paths = []
    if not root.is_dir():
        return changed_paths
    for php_path in root.rglob("*.php"):
        source = php_path.read_text(encoding="utf-8", errors="replace")
        updated, count = PHP_CURLY_OFFSET_PATTERN.subn(
            r"\g<value>[\g<offset>]",
            source,
        )
        if count:
            php_path.write_text(updated, encoding="utf-8")
            changed_paths.append(php_path)
    return changed_paths


def update_pattemplate_constructor(root: Path) -> list[Path]:
    changed_paths = []
    if not root.is_dir():
        return changed_paths
    legacy_constructor = re.compile(
        r"(?P<indent>^[ \t]*)function\s+patTemplate\s*\(\s*\$type\s*=\s*['\"]html['\"]\s*\)\s*\{",
        re.MULTILINE,
    )
    for php_path in root.rglob("patTemplate.php"):
        source = php_path.read_text(encoding="utf-8", errors="replace")
        match = legacy_constructor.search(source)
        if not match or re.search(r"\bfunction\s+__construct\s*\(", source[:match.start()]):
            continue
        indent = match.group("indent")
        updated = (
            source[:match.start()]
            + f"{indent}function __construct( $type = 'html' ) {{\n"
            + f"{indent}    $this->patTemplate( $type );\n"
            + f"{indent}}}\n\n"
            + source[match.start():]
        )
        php_path.write_text(updated, encoding="utf-8")
        changed_paths.append(php_path)
    return changed_paths


def update_legacy_app_registry(registry_path: Path) -> bool:
    source = registry_path.read_text(encoding="utf-8")
    signature = re.compile(r"\bfunction\s+allClass\s*\(\s*\$classes\s*\)\s*\{")
    match = signature.search(source)
    if not match:
        raise ValueError(f"Method allClass tidak ditemukan di {registry_path}")
    if re.match(r"\s*global\s+\$app\s*;", source[match.end():]):
        return False

    initialization = (
        "\n\t\tglobal $app;\n"
        "\t\tif (!isset($app) || !is_object($app)) {\n"
        "\t\t\t$app = new stdClass();\n"
        "\t\t}\n"
    )
    updated = source[:match.end()] + initialization + source[match.end():]
    registry_path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env", type=Path)
    parser.add_argument("--driver", action="append", default=[], type=Path)
    parser.add_argument("--php-root", action="append", default=[], type=Path)
    parser.add_argument("--registry", action="append", default=[], type=Path)
    args = parser.parse_args()
    if bool(args.config) != bool(args.env):
        parser.error("--config dan --env harus diberikan bersamaan.")
    if not args.config and not args.driver and not args.php_root and not args.registry:
        parser.error("Berikan konfigurasi, driver, atau direktori PHP yang akan diperbarui.")
    if args.config and not args.config.is_file():
        parser.error(f"File konfigurasi tidak ditemukan: {args.config}")

    try:
        changed = update_adodb_config(args.config, args.env) if args.config else False
        for driver_path in args.driver:
            if not driver_path.is_file():
                raise ValueError(f"Driver ADOdb tidak ditemukan: {driver_path}")
            changed = update_adodb_mysqli_driver(driver_path) or changed
        for registry_path in args.registry:
            if not registry_path.is_file():
                raise ValueError(f"Registry class tidak ditemukan: {registry_path}")
            changed = update_legacy_app_registry(registry_path) or changed
        changed_php_paths = []
        for php_root in args.php_root:
            changed_php_paths.extend(update_php_curly_offsets(php_root))
            changed_php_paths.extend(update_pattemplate_constructor(php_root))
        changed = bool(changed_php_paths) or changed
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if changed_php_paths:
        for php_path in changed_php_paths:
            print(f"Sintaks offset PHP 8 diperbarui: {php_path}")
    if changed:
        print("Kompatibilitas ADOdb/PHP diperbarui.")
    else:
        print("Konfigurasi dan sintaks sudah sesuai.")


if __name__ == "__main__":
    main()
