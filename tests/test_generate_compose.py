import json

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


def test_microservice_runtime_metadata_controls_image_port_and_source_mount(tmp_path):
    service_dir = tmp_path / "node_service"
    service_dir.mkdir()
    (service_dir / ".ladock-runtime.json").write_text(
        json.dumps(
            {
                "language": "Node.js",
                "container_port": 3000,
                "working_dir": "/app",
                "dockerfile": ".ladock.Dockerfile",
                "custom_dockerfile": False,
            }
        ),
        encoding="utf-8",
    )

    compose = build_app_compose(
        project="sample",
        services=[{"name": "web", "http_port": 8081}],
        gateway_port=8080,
        php_versions={},
        composer_versions={},
        service_paths={"web": str(service_dir)},
    )

    assert f"context: {service_dir}" in compose
    assert "dockerfile: .ladock.Dockerfile" in compose
    assert '"8081:3000"' in compose
    assert "working_dir: /app" in compose
    assert f"{service_dir}:/var/www" not in compose


def test_php_microservice_sets_document_root_from_runtime_metadata(tmp_path):
    service_dir = tmp_path / "wordpress"
    service_dir.mkdir()
    (service_dir / ".ladock-runtime.json").write_text(
        json.dumps(
            {
                "language": "PHP",
                "container_port": 80,
                "working_dir": "/var/www",
                "document_root": "/var/www",
                "dockerfile": "Dockerfile",
                "custom_dockerfile": False,
            }
        ),
        encoding="utf-8",
    )

    compose = build_app_compose(
        project="sample",
        services=[{"name": "wordpress", "http_port": 8081}],
        gateway_port=8080,
        php_versions={"wordpress": "8.2"},
        composer_versions={"wordpress": "2"},
        service_paths={"wordpress": str(service_dir)},
    )

    assert 'LADOCK_DOCUMENT_ROOT: "/var/www"' in compose
