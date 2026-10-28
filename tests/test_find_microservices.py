import json

from scripts.find_microservices import scan


def test_scans_services_with_different_runtime_manifests(tmp_path):
    php = tmp_path / "api"
    php.mkdir()
    (php / "artisan").write_text("", encoding="utf-8")
    (php / "composer.json").write_text(
        json.dumps({"name": "team/api"}), encoding="utf-8"
    )
    node = tmp_path / "frontend"
    node.mkdir()
    (node / "package.json").write_text('{"name":"frontend"}', encoding="utf-8")
    go = tmp_path / "worker"
    go.mkdir()
    (go / "go.mod").write_text("module example.com/worker\n", encoding="utf-8")

    services = scan(str(tmp_path))

    assert [(service["name"], service["path"]) for service in services] == [
        ("api", str(php)),
        ("frontend", str(node)),
        ("worker", str(go)),
    ]


def test_root_application_is_not_split_into_nested_dependencies(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"app"}', encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "go.mod").write_text("module example.com/nested\n", encoding="utf-8")

    services = scan(str(tmp_path))

    assert len(services) == 1
    assert services[0]["path"] == str(tmp_path)


def test_wordpress_site_is_one_app_and_plugin_manifests_are_not_services(tmp_path):
    wordpress = tmp_path / "homedir" / "public_html"
    (wordpress / "wp-admin").mkdir(parents=True)
    (wordpress / "wp-includes" / "sodium_compat").mkdir(parents=True)
    (wordpress / "wp-content" / "plugins" / "buddypress").mkdir(parents=True)
    (wordpress / "wp-config.php").write_text("<?php", encoding="utf-8")
    (wordpress / "wp-includes" / "sodium_compat" / "composer.json").write_text(
        json.dumps({"name": "paragonie/sodium_compat", "require": {"php": "^5.6"}}),
        encoding="utf-8",
    )
    (
        wordpress / "wp-content" / "plugins" / "buddypress" / "composer.json"
    ).write_text(json.dumps({"name": "buddypress/buddypress"}), encoding="utf-8")

    services = scan(str(tmp_path))

    assert len(services) == 1
    assert services[0]["path"] == str(wordpress)
    assert services[0]["name"] == "public_html"


def test_wordpress_site_inside_public_is_not_skipped_or_split(tmp_path):
    wordpress = tmp_path / "public"
    (wordpress / "wp-admin").mkdir(parents=True)
    (wordpress / "wp-includes").mkdir()
    plugin = wordpress / "wp-content" / "plugins" / "example-plugin"
    plugin.mkdir(parents=True)
    (plugin / "composer.json").write_text("{}", encoding="utf-8")

    services = scan(str(tmp_path))

    assert len(services) == 1
    assert services[0]["path"] == str(wordpress)


def test_composer_packages_without_application_entrypoint_are_not_services(tmp_path):
    project = tmp_path / "legacy_app"
    package = project / "plugins" / "select2"
    package.mkdir(parents=True)
    (package / "composer.json").write_text(
        json.dumps({"name": "vendor/select2"}),
        encoding="utf-8",
    )
    (project / "composer.json").write_text(
        json.dumps({"name": "vendor/legacy-app"}),
        encoding="utf-8",
    )
    (project / "web").mkdir()
    (project / "web" / "index.php").write_text("<?php", encoding="utf-8")

    services = scan(str(tmp_path))

    assert services == [{"name": "legacy_app", "path": str(project)}]


def test_composer_application_with_symfony_entrypoint_is_a_service(tmp_path):
    app = tmp_path / "symfony"
    (app / "public").mkdir(parents=True)
    (app / "public" / "index.php").write_text("<?php", encoding="utf-8")
    (app / "composer.json").write_text("{}", encoding="utf-8")
    plugin = app / "plugins" / "select2"
    plugin.mkdir(parents=True)
    (plugin / "composer.json").write_text(
        json.dumps({"name": "vendor/select2"}),
        encoding="utf-8",
    )

    services = scan(str(tmp_path))

    assert services == [{"name": "symfony", "path": str(app)}]
