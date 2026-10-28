from scripts.generate_gateway_conf import build_gateway_conf


def test_gateway_root_dashboard_uses_document_index_without_rewrite():
    config = build_gateway_conf("sample", [{"name": "web", "http_port": 8081}], 8080)

    assert "Root dashboard is served by DirectoryIndex" in config
    assert "RewriteRule" not in config
    assert "<title>sample &mdash; Microservice Gateway</title>" in config


def test_gateway_routes_each_service_to_its_runtime_port():
    config = build_gateway_conf(
        "sample",
        [
            {"name": "php", "http_port": 8081, "container_port": 80},
            {"name": "node", "http_port": 8082, "container_port": 3000},
            {"name": "python", "http_port": 8083, "container_port": 8000},
        ],
        8080,
    )

    assert "http://app_php:80/" in config
    assert "http://app_node:3000/" in config
    assert "http://app_python:8000/" in config
