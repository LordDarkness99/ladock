#!/usr/bin/env python3
"""Add an optional Apache gateway service to a single-app Compose file."""

import argparse
import re
from pathlib import Path


MEMORY_LIMIT_PATTERN = re.compile(r"[1-9][0-9]*(?:\.[0-9]+)?(?:[bBkKmMgG]|[kKmMgG][bB])?")
PROJECT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
NETWORK_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def add_gateway_service(
    compose: str,
    project: str,
    gateway_port: int,
    memory_limit: str,
    network: str = "ladock_net",
) -> str:
    if not PROJECT_PATTERN.fullmatch(project):
        raise ValueError(f"Nama project tidak valid: {project!r}")
    if not 1024 <= gateway_port <= 65535:
        raise ValueError("Port gateway harus berada di rentang 1024-65535.")
    if not MEMORY_LIMIT_PATTERN.fullmatch(memory_limit):
        raise ValueError(f"Batas memori tidak valid: {memory_limit!r}")
    if not NETWORK_PATTERN.fullmatch(network):
        raise ValueError(f"Nama network tidak valid: {network!r}")

    networks_marker = "\nnetworks:\n"
    if compose.count(networks_marker) != 1:
        raise ValueError("Compose harus memiliki tepat satu bagian top-level networks.")
    if f"  gateway_{project}:\n" in compose:
        raise ValueError(f"Service gateway_{project} sudah ada di Compose.")

    gateway_service = f"""
  gateway_{project}:
    build:
      context: .docker/gateway
      dockerfile: Dockerfile
    container_name: {project}_gateway
    restart: unless-stopped
    mem_limit: {memory_limit}
    ports:
      - "{gateway_port}:80"
    volumes:
      - ./.docker/apache-gateway.conf:/usr/local/apache2/conf/extra/vhost.conf:ro
    depends_on:
      - app_{project}
    networks:
      - {network}
"""
    return compose.replace(networks_marker, f"\n{gateway_service}{networks_marker}", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--gateway-port", required=True, type=int)
    parser.add_argument("--memory-limit", required=True)
    parser.add_argument("--network", default="ladock_net")
    args = parser.parse_args()

    try:
        compose = args.compose.read_text(encoding="utf-8")
        updated = add_gateway_service(
            compose,
            args.project,
            args.gateway_port,
            args.memory_limit,
            args.network,
        )
        args.compose.write_text(updated, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Gateway ditambahkan ke {args.compose}")


if __name__ == "__main__":
    main()
