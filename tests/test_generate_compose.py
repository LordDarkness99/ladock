import pytest

from scripts.generate_compose import build_app_compose, build_db_compose


def test_db_compose_uses_separate_database_data_directory():
    compose = build_db_compose(
        project="sample",
        services=[{"name": "web", "http_port": 8081}],
        base_db_port=3308,
        db_creds={},
        db_root_pass="root-secret",
    )

    assert "../../db/sample/web/data:/var/lib/mysql" in compose
    assert "sample_web_dbdata" not in compose
    assert "\nvolumes:\n" not in compose
    assert "mem_limit: 512M" in compose


def test_memory_limit_is_applied_to_every_microservice_container():
    services = [
        {"name": "web", "http_port": 8081},
        {"name": "api", "http_port": 8082},
    ]
    db_compose = build_db_compose(
        project="sample",
        services=services,
        base_db_port=3308,
        db_creds={},
        db_root_pass="root-secret",
        memory_limit="1G",
    )
    app_compose = build_app_compose(
        project="sample",
        services=services,
        gateway_port=8080,
        db_creds={},
        php_versions={},
        composer_versions={},
        memory_limit="1G",
    )

    assert db_compose.count("mem_limit: 1G") == len(services)
    assert app_compose.count("mem_limit: 1G") == len(services) + 1


def test_default_memory_limit_is_applied_to_gateway_and_app_services():
    services = [
        {"name": "web", "http_port": 8081},
        {"name": "api", "http_port": 8082},
    ]
    app_compose = build_app_compose(
        project="sample",
        services=services,
        gateway_port=8080,
        db_creds={},
        php_versions={},
        composer_versions={},
    )

    assert app_compose.count("mem_limit: 512M") == len(services) + 1


def test_invalid_memory_limit_is_rejected():
    with pytest.raises(ValueError, match="Batas memori tidak valid"):
        build_db_compose(
            project="sample",
            services=[{"name": "web", "http_port": 8081}],
            base_db_port=3308,
            db_creds={},
            db_root_pass="root-secret",
            memory_limit="512M; other: value",
        )
