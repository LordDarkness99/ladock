from pathlib import Path

from scripts.legacy_db_config import (
    clear_symfony1_cache,
    get_legacy_database_name,
    update_codeigniter_config,
    update_symfony1_config,
    update_symfony1_local_security,
    update_symfony1_user_group_compatibility,
)


def test_codeigniter_database_name_and_settings_are_migrated_to_environment(tmp_path: Path):
    service_dir = tmp_path / "individu"
    config_dir = service_dir / "application/config"
    config_dir.mkdir(parents=True)
    database_config = config_dir / "database.php"
    database_config.write_text(
        "<?php\n"
        "$db['default']['hostname'] = 'old-host';\n"
        "$db['default']['hostname'] = '192.168.1.25';\n"
        "$db['default']['username'] = 'old-user';\n"
        "$db['default']['password'] = 'old-password';\n"
        "$db['default']['database'] = 'imunisas_individu';\n"
        "$db['default']['dbdriver'] = 'mysqli';\n",
        encoding="utf-8",
    )
    config_config = config_dir / "config.php"
    config_config.write_text(
        "<?php\n$config['base_url'] = 'https://old.example/individu/';\n",
        encoding="utf-8",
    )

    assert get_legacy_database_name(service_dir) == "imunisas_individu"
    assert update_codeigniter_config(service_dir)
    updated = database_config.read_text(encoding="utf-8")
    assert "getenv('DB_HOST')" in updated
    assert "getenv('DB_USERNAME')" in updated
    assert "getenv('DB_PASSWORD')" in updated
    assert "getenv('DB_DATABASE')" in updated
    assert "192.168.1.25" not in updated
    assert "old-password" not in updated
    assert "getenv('APP_URL')" in config_config.read_text(encoding="utf-8")
    assert not update_codeigniter_config(service_dir)


def test_codeigniter_base_url_uses_gateway_path(tmp_path: Path):
    config_dir = tmp_path / "application/config"
    config_dir.mkdir(parents=True)
    config = config_dir / "config.php"
    config.write_text(
        "<?php\n"
        "$config['base_url'] = 'http://old.example/';\n"
        "$config['index_page'] = '';\n",
        encoding="utf-8",
    )
    database_config = config_dir / "database.php"
    database_config.write_text(
        "<?php\n"
        "$db['default']['hostname'] = 'old-host';\n"
        "$db['default']['username'] = 'old-user';\n"
        "$db['default']['password'] = 'old-password';\n"
        "$db['default']['database'] = 'old-database';\n",
        encoding="utf-8",
    )

    assert update_codeigniter_config(tmp_path)
    assert "getenv('APP_URL')" in config.read_text(encoding="utf-8")


def test_symfony1_database_name_and_credentials_are_updated(tmp_path: Path):
    service_dir = tmp_path / "surveylance"
    config_dir = service_dir / "config"
    config_dir.mkdir(parents=True)
    database_config = config_dir / "databases.yml"
    database_config.write_text(
        "dev:\n"
        "  propel:\n"
        "    param:\n"
        "      dsn: mysql:host=old-host;dbname=imunisas_survey\n"
        "      username: old-user\n"
        "      password: old-password\n"
        "all:\n"
        "  propel:\n"
        "    class: sfPropelDatabase\n"
        "    param:\n"
        "      classname: PropelPDO\n"
        "      dsn: mysql:host=old-host;dbname=imunisas_survey\n"
        "      username: old-user\n"
        "      password: old-password\n"
        "      encoding: utf8\n",
        encoding="utf-8",
    )
    env_file = service_dir / ".env"
    env_file.write_text(
        'DB_HOST="ladock_mysql"\n'
        'DB_PORT="3306"\n'
        'DB_DATABASE="surveylance_db"\n'
        'DB_USERNAME="survey user"\n'
        'DB_PASSWORD="pass:/@word"\n',
        encoding="utf-8",
    )

    assert get_legacy_database_name(service_dir) == "imunisas_survey"
    assert update_symfony1_config(database_config, env_file)
    updated = database_config.read_text(encoding="utf-8")
    assert "mysql:host=ladock_mysql;port=3306;dbname=surveylance_db" in updated
    assert "      username: \"survey user\"" in updated
    assert "      password: \"pass:/@word\"" in updated
    assert "old-password" not in updated
    assert not update_symfony1_config(database_config, env_file)


def test_symfony1_local_http_adaptation_updates_only_app_security_files(tmp_path: Path):
    service_dir = tmp_path / "surveylance"
    security_config = service_dir / "apps/backend/config/security.yml"
    security_config.parent.mkdir(parents=True)
    security_config.write_text("default:\n  is_secure: true\n", encoding="utf-8")
    module_config = service_dir / "apps/backend/modules/home/config/security.yml"
    module_config.parent.mkdir(parents=True)
    module_config.write_text("all:\n  is_secure: true\n", encoding="utf-8")
    vendor_config = service_dir / "lib/vendor/symfony/test/security.yml"
    vendor_config.parent.mkdir(parents=True)
    vendor_config.write_text("default:\n  is_secure: true\n", encoding="utf-8")

    assert update_symfony1_local_security(service_dir)
    assert "is_secure: false" in security_config.read_text(encoding="utf-8")
    assert "is_secure: false" in module_config.read_text(encoding="utf-8")
    assert "is_secure: true" in vendor_config.read_text(encoding="utf-8")
    assert not update_symfony1_local_security(service_dir)


def test_symfony1_user_group_accessor_is_added_without_bypassing_login(tmp_path: Path):
    user_class = tmp_path / "apps/backend/lib/myUser.class.php"
    user_class.parent.mkdir(parents=True)
    user_class.write_text(
        "<?php\nclass myUser extends sfBasicSecurityUser\n{\n}\n",
        encoding="utf-8",
    )

    assert update_symfony1_user_group_compatibility(tmp_path)
    updated = user_class.read_text(encoding="utf-8")
    assert "$this->getAttribute('user')" in updated
    assert "method_exists($user, 'getGroupId')" in updated
    assert not update_symfony1_user_group_compatibility(tmp_path)


def test_symfony1_generated_cache_is_cleared_after_local_config_changes(tmp_path: Path):
    cached_config = tmp_path / "cache/backend/dev/config/config_databases.yml.php"
    cached_config.parent.mkdir(parents=True)
    cached_config.write_text("<?php // stale generated config", encoding="utf-8")

    assert clear_symfony1_cache(tmp_path)
    assert not (tmp_path / "cache/backend").exists()
    assert not clear_symfony1_cache(tmp_path)
