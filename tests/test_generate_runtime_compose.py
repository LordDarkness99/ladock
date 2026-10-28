import pytest

from scripts.generate_runtime_compose import build_runtime_compose


def test_runtime_compose_publishes_detected_internal_port_and_loads_environment():
    compose = build_runtime_compose(
        project="orders",
        http_port=8088,
        memory_limit="1G",
        runtime={
            "dockerfile": ".ladock.Dockerfile",
            "working_dir": "/app",
            "container_port": 3000,
        },
        central_db_network="shared_net",
    )

    assert '      - "8088:3000"' in compose
    assert '      PORT: "3000"' in compose
    assert '      - "./src/.env"' in compose
    assert "mem_limit: 1G" in compose
    assert "shared_net" in compose


def test_runtime_compose_rejects_unsafe_project_and_memory_values():
    runtime = {"dockerfile": "Dockerfile", "working_dir": "/app", "container_port": 3000}
    with pytest.raises(ValueError, match="Nama project tidak valid"):
        build_runtime_compose("bad project", 8080, "512M", runtime)
    with pytest.raises(ValueError, match="Batas memori tidak valid"):
        build_runtime_compose("valid", 8080, "512M; other: true", runtime)
