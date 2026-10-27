#!/usr/bin/env python3
"""Find unused consecutive-in-order host ports, skipping ports already in use."""

import argparse
import errno
import json
import re
import socket
import subprocess


def docker_published_ports() -> set[int]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Ports}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_docker_published_ports(result.stdout)


def parse_docker_published_ports(output: str) -> set[int]:
    used: set[int] = set()
    for mapping in output.splitlines():
        for binding in mapping.split(","):
            host, separator, _ = binding.strip().partition("->")
            if not separator or ":" not in host:
                continue
            port_text = host.rsplit(":", 1)[-1]
            match = re.fullmatch(r"(\d+)(?:-(\d+))?", port_text)
            if match:
                first = int(match.group(1))
                last = int(match.group(2) or first)
                used.update(range(first, last + 1))
    return used


def socket_port_is_available(port: int) -> bool:
    for family, address in (
        (socket.AF_INET, ("0.0.0.0", port)),
        (socket.AF_INET6, ("::", port)),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as listener:
                if family == socket.AF_INET6:
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind(address)
        except OSError as exc:
            if exc.errno in {errno.EADDRINUSE, errno.EACCES}:
                return False
            if family == socket.AF_INET6 and exc.errno in {
                errno.EAFNOSUPPORT,
                errno.EPROTONOSUPPORT,
            }:
                continue
            raise
    return True


def find_free_ports(start: int, count: int, excluded: set[int], docker_ports: set[int]) -> dict:
    ports: list[int] = []
    skipped: list[int] = []
    port = start
    while len(ports) < count and port <= 65535:
        if port in excluded or port in docker_ports or not socket_port_is_available(port):
            skipped.append(port)
        else:
            ports.append(port)
        port += 1
    if len(ports) != count:
        raise ValueError(f"Tidak cukup port kosong mulai dari {start} untuk {count} service.")
    return {"ports": ports, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--exclude", default="", help="Daftar port dipisahkan koma")
    args = parser.parse_args()
    if not 1024 <= args.start <= 65535:
        parser.error("Port awal harus berada di rentang 1024-65535.")
    if not 1 <= args.count <= 256:
        parser.error("Jumlah port harus berada di rentang 1-256.")
    try:
        excluded = {int(port) for port in args.exclude.split(",") if port}
        result = find_free_ports(args.start, args.count, excluded, docker_published_ports())
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
