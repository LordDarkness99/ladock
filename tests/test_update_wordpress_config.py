from pathlib import Path

from scripts.update_wordpress_config import get_database_name, update_wordpress_config


def test_wordpress_database_defines_are_replaced_with_env_lookups(tmp_path):
    config = tmp_path / "wp-config.php"
    config.write_text(
        "<?php\n"
        "define( 'DB_NAME', 'old_database' );\n"
        'define("DB_USER", "old_user");\n'
        "define('DB_PASSWORD', 'old_password');\n"
        "define('DB_HOST', '192.0.2.10');\n"
        "define('WP_HOME', 'https://old.example/path');\n"
        "define('WP_SITEURL', 'https://old.example/path');\n"
        "$table_prefix = 'wp_';\n"
        "require_once(ABSPATH . 'wp-settings.php');\n",
        encoding="utf-8",
    )

    assert get_database_name(config) == "old_database"
    changed = update_wordpress_config(config)
    updated = config.read_text(encoding="utf-8")

    assert changed == 7
    assert "define('DB_NAME', getenv('DB_DATABASE'))" in updated
    assert "define('DB_USER', getenv('DB_USERNAME'))" in updated
    assert "define('DB_PASSWORD', getenv('DB_PASSWORD'))" in updated
    assert "define('DB_HOST', getenv('DB_HOST'))" in updated
    assert "define('WP_HOME', getenv('APP_URL'))" in updated
    assert "define('WP_SITEURL', getenv('APP_URL'))" in updated
    assert "$_SERVER['REQUEST_URI'] = rtrim($ladock_path_prefix" in updated
    assert "old_password" not in updated
    assert get_database_name(config) == ""


def test_wordpress_config_without_literal_db_defines_still_gets_site_url_env(tmp_path):
    config = tmp_path / "wp-config.php"
    original = (
        "<?php\n$table_prefix = 'wp_';\n"
        "require_once(ABSPATH . 'wp-settings.php');\n"
    )
    config.write_text(original, encoding="utf-8")

    assert update_wordpress_config(config) == 3
    updated = config.read_text(encoding="utf-8")
    assert "define('WP_HOME', getenv('APP_URL'));" in updated
    assert "define('WP_SITEURL', getenv('APP_URL'));" in updated
    assert "// LaDock path-prefix support for reverse-proxy deployments." in updated
    assert update_wordpress_config(config) == 0


def test_wordpress_rewrite_rules_use_service_root_behind_gateway(tmp_path):
    config = tmp_path / "wp-config.php"
    config.write_text(
        "<?php\n$table_prefix = 'wp_';\nrequire_once(ABSPATH . 'wp-settings.php');\n",
        encoding="utf-8",
    )
    htaccess = tmp_path / ".htaccess"
    htaccess.write_text(
        "RewriteBase /index2/\n"
        "RewriteRule . /index2/index.php [L]\n",
        encoding="utf-8",
    )

    assert update_wordpress_config(config) == 4
    assert htaccess.read_text(encoding="utf-8") == (
        "RewriteBase /\n"
        "RewriteRule . /index.php [L]\n"
    )
    assert update_wordpress_config(config) == 0


def test_legacy_wordpress_query_comparison_is_safe_on_php8(tmp_path):
    config = tmp_path / "wp-config.php"
    config.write_text(
        "<?php\n$table_prefix = 'wp_';\nrequire_once(ABSPATH . 'wp-settings.php');\n",
        encoding="utf-8",
    )
    query_file = tmp_path / "wp-includes" / "class-wp-query.php"
    query_file.parent.mkdir()
    query_file.write_text(
        "if ( ! is_scalar( $qv['p'] ) || $qv['p'] < 0 ) {\n",
        encoding="utf-8",
    )

    assert update_wordpress_config(config) == 4
    assert query_file.read_text(encoding="utf-8") == (
        "if ( ! is_scalar( $qv['p'] ) || ( '' !== $qv['p'] && $qv['p'] < 0 ) ) {\n"
    )
    assert update_wordpress_config(config) == 0
