from pathlib import Path

import pytest

from scripts.update_adodb_config import (
    update_adodb_config,
    update_adodb_mysqli_driver,
    update_legacy_app_registry,
    update_php_curly_offsets,
    update_pattemplate_constructor,
)


def test_updates_legacy_adodb_connection_from_env_and_preserves_other_settings(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DB_HOST="ladock_mysql"\n'
        'DB_DATABASE="clinic_db"\n'
        'DB_USERNAME="clinic_user"\n'
        'DB_PASSWORD="pass$with\\\\slash\'quote"\n',
        encoding="utf-8",
    )
    config_file = tmp_path / "database.php"
    config_file.write_text(
        "<?php\n"
        "$database['default']['host'] = 'old-host';\n"
        "$database['default']['user'] = 'old-user';\n"
        "$database['default']['pass'] = 'old-pass';\n"
        "$database['default']['name'] = 'old-db';\n"
        "$database['default']['driver'] = 'mysql';\n"
        "$database['default']['debug'] = TRUE;\n",
        encoding="utf-8",
    )

    assert update_adodb_config(config_file, env_file)
    updated = config_file.read_text(encoding="utf-8")
    assert "$database['default']['host'] = 'ladock_mysql';" in updated
    assert "$database['default']['driver'] = 'mysqli';" in updated
    assert "$database['default']['debug'] = TRUE;" in updated
    assert "old-host" not in updated


def test_rejects_missing_db_settings_in_env(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_HOST=ladock_mysql\n", encoding="utf-8")
    config_file = tmp_path / "database.php"
    config_file.write_text("<?php\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Variabel koneksi DB tidak lengkap"):
        update_adodb_config(config_file, env_file)


def test_fixes_legacy_mysqli_driver_signature_and_is_idempotent(tmp_path: Path):
    driver_file = tmp_path / "adodb-mysqli.inc.php"
    driver_file.write_text(
        "function MetaIndexes ($table, $primary = FALSE)\n"
        "{\n"
        "    return false;\n"
        "}\n"
        "function _initrs()\n"
        "{\n"
        "\t\t$this->_numOfRows = $ADODB_COUNTRECS ? @mysqli_num_rows($this->_queryID) : -1;\n"
        "\t\t$this->_numOfFields = @mysqli_num_fields($this->_queryID);\n"
        "}\n"
        "function _close()\n"
        "{\n"
        "\t\tmysqli_free_result($this->_queryID);\n"
        "}\n"
        "function _next()\n"
        "{\n"
        "\t\tmysqli_free_result($this->_queryID);\n"
        "}\n",
        encoding="utf-8",
    )

    assert update_adodb_mysqli_driver(driver_file)
    updated = driver_file.read_text(encoding="utf-8")
    assert "function MetaIndexes ($table, $primary = FALSE, $owner = false)" in updated
    assert "if (!($this->_queryID instanceof mysqli_result))" in updated
    assert updated.count("if ($this->_queryID instanceof mysqli_result)") == 2
    assert not update_adodb_mysqli_driver(driver_file)


def test_rejects_unknown_mysqli_driver_signature(tmp_path: Path):
    driver_file = tmp_path / "adodb-mysqli.inc.php"
    driver_file.write_text("function MetaIndexes($table)\n{\n}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Tanda tangan MetaIndexes tidak dikenali"):
        update_adodb_mysqli_driver(driver_file)


def test_updates_legacy_php_curly_offsets_only_in_given_tree(tmp_path: Path):
    template_dir = tmp_path / "patTemplates"
    template_dir.mkdir()
    php_file = template_dir / "patTemplate.php"
    php_file.write_text(
        "<?php\nif ($var{0} == '_') {\n    echo $record['name']{1};\n}\n",
        encoding="utf-8",
    )
    unrelated_dir = tmp_path / "other"
    unrelated_dir.mkdir()
    unrelated_file = unrelated_dir / "legacy.php"
    unrelated_file.write_text("<?php echo $field{0};\n", encoding="utf-8")

    changed = update_php_curly_offsets(template_dir)

    assert changed == [php_file]
    assert "$var[0]" in php_file.read_text(encoding="utf-8")
    assert "$record['name'][1]" in php_file.read_text(encoding="utf-8")
    assert "$field{0}" in unrelated_file.read_text(encoding="utf-8")
    assert update_php_curly_offsets(template_dir) == []


def test_adds_php8_constructor_for_legacy_pattemplate(tmp_path: Path):
    template_dir = tmp_path / "patTemplates"
    template_dir.mkdir()
    template_file = template_dir / "patTemplate.php"
    template_file.write_text(
        "<?php\n"
        "class patTemplate {\n"
        "    function patTemplate( $type = 'html' ) {\n"
        "        $this->setType( $type );\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    assert update_pattemplate_constructor(template_dir) == [template_file]
    updated = template_file.read_text(encoding="utf-8")
    assert "function __construct( $type = 'html' ) {" in updated
    assert "$this->patTemplate( $type );" in updated
    assert update_pattemplate_constructor(template_dir) == []


def test_initializes_legacy_global_app_registry_for_php8(tmp_path: Path):
    registry_file = tmp_path / "load.class.php"
    registry_file.write_text(
        "<?php\n"
        "class Load {\n"
        "\tfunction allClass($classes){\n"
        "\t\tforeach ($classes as $class => $object) {\n"
        "\t\t\t$app->$class = $object;\n"
        "\t\t}\n"
        "\t}\n"
        "}\n",
        encoding="utf-8",
    )

    assert update_legacy_app_registry(registry_file)
    patched = registry_file.read_text(encoding="utf-8")
    assert "global $app;" in patched
    assert "$app = new stdClass();" in patched
    assert not update_legacy_app_registry(registry_file)
