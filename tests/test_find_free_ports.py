from scripts.find_free_ports import find_free_ports, parse_docker_published_ports


def test_finds_next_free_ports_and_skips_reserved_ports(monkeypatch):
    busy_ports = {8081}
    monkeypatch.setattr(
        "scripts.find_free_ports.socket_port_is_available",
        lambda port: port not in busy_ports,
    )

    result = find_free_ports(
        start=8080,
        count=4,
        excluded={8083},
        docker_ports={8082},
    )

    assert result == {
        "ports": [8080, 8084, 8085, 8086],
        "skipped": [8081, 8082, 8083],
    }


def test_rejects_when_port_range_is_exhausted(monkeypatch):
    monkeypatch.setattr("scripts.find_free_ports.socket_port_is_available", lambda _port: False)

    try:
        find_free_ports(start=65535, count=2, excluded=set(), docker_ports=set())
    except ValueError as exc:
        assert "Tidak cukup port kosong" in str(exc)
    else:
        raise AssertionError("Expected port exhaustion to fail")


def test_reads_published_docker_ports_in_ipv4_ipv6_and_ranges():
    ports = parse_docker_published_ports(
        "0.0.0.0:8080->80/tcp, :::8080->80/tcp\n"
        "127.0.0.1:9000-9002->3306-3308/tcp\n"
        "80/tcp"
    )

    assert ports == {8080, 9000, 9001, 9002}
