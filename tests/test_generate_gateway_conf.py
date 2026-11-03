import sys

import pytest

from scripts.generate_gateway_conf import build_gateway_conf, main


def test_gateway_root_does_not_render_a_service_dashboard():
    config = build_gateway_conf("sample", [{"name": "web", "http_port": 8081}], 8080)

    assert "RedirectMatch 404 ^/$" in config
    assert "RewriteRule" not in config
    assert "<table>" not in config


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
    assert (
        "<Location /php/>\n"
        "        ProxyPreserveHost On\n"
        "        ProxyPassReverseCookiePath / /php/\n"
        "    </Location>"
    ) in config
    assert (
        "<Location /node/>\n"
        "        ProxyPreserveHost On\n"
        "        ProxyPassReverseCookiePath / /node/\n"
        "    </Location>"
    ) in config


def test_gateway_supports_route_aliases_for_services():
    config = build_gateway_conf(
        "sample",
        [{"name": "root_web", "http_port": 8085, "route": "admin"}],
        8080,
    )

    assert "ProxyPass        /admin/  http://app_root_web:80/" in config
    assert "<table>" not in config
    assert "/root_web/" not in config


def test_gateway_rejects_unsafe_route_aliases():
    with pytest.raises(ValueError, match="Route gateway tidak valid"):
        build_gateway_conf(
            "sample",
            [{"name": "root_web", "http_port": 8085, "route": "../admin"}],
            8080,
        )


def test_gateway_cli_applies_service_route_alias(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_gateway_conf.py",
            "--project",
            "sample",
            "--services",
            "root_web:8085",
            "--routes",
            "root_web:admin",
            "--gateway-port",
            "8080",
        ],
    )

    main()
    config = capsys.readouterr().out

    assert "ProxyPass        /admin/  http://app_root_web:80/" in config
    assert "<table>" not in config
