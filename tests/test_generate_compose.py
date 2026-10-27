import pytest

from scripts.generate_compose import build_app_compose


def test_memory_limit_is_applied_to_every_microservice_container():
    services = [
        {"name": "web", "http_port": 8081},
        {"name": "api", "http_port": 8082},
    ]
    app_compose = build_app_compose(
        project="sample",
        services=services,
        gateway_port=8080,
        php_versions={},
        composer_versions={},
        memory_limit="1G",
    )

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
        php_versions={},
        composer_versions={},
    )

    assert app_compose.count("mem_limit: 512M") == len(services) + 1


def test_microservices_load_environment_from_each_service_and_use_shared_network():
    app_compose = build_app_compose(
        project="sample",
        services=[{"name": "web", "http_port": 8081}],
        gateway_port=8080,
        php_versions={},
        composer_versions={},
        central_db_network="shared_net",
    )

    assert '      - "./.env"' in app_compose
    assert "DB_PASSWORD:" not in app_compose
    assert app_compose.count("      - shared_net") == 2
    assert "db_web:" not in app_compose
    assert 'name: shared_net' in app_compose
    assert "3308:3306" not in app_compose


def test_invalid_memory_limit_is_rejected():
    with pytest.raises(ValueError, match="Batas memori tidak valid"):
        build_app_compose(
            project="sample",
            services=[{"name": "web", "http_port": 8081}],
            gateway_port=8080,
            php_versions={},
            composer_versions={},
            memory_limit="512M; other: value",
        )
