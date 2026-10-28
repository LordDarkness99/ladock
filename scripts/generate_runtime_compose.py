#!/usr/bin/env python3
"""Generate a Compose service for a non-default/custom project runtime."""

import argparse
import json
import re
from pathlib import Path


MEMORY_LIMIT_PATTERN = re.compile(r"[1-9][0-9]*(?:\.[0-9]+)?(?:[bBkKmMgG]|[kKmMgG][bB])?")


def build_runtime_compose(
    project: str,
    http_port: int,
    memory_limit: str,
    runtime: dict,
    central_db_network: str = "ladock_net",
) -> str:
    if not MEMORY_LIMIT_PATTERN.fullmatch(memory_limit):
        raise ValueError(f"Batas memori tidak valid: {memory_limit!r}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise ValueError(f"Nama project tidak valid: {project!r}")

    container_port = int(runtime["container_port"])
    dockerfile = runtime["dockerfile"]
    return "\n".join(
        [
            "services:",
            f"  app_{project}:",
            "    build:",
            "      context: ./src",
            f"      dockerfile: {dockerfile}",
            f"    container_name: {project}_app",
            "    restart: unless-stopped",
            f"    mem_limit: {memory_limit}",
            f"    working_dir: {runtime['working_dir']}",
            "    env_file:",
            '      - "./src/.env"',
            "    environment:",
            '      APP_ENV: "local"',
            f'      PORT: "{container_port}"',
            f'      SERVER_PORT: "{container_port}"',
            "    ports:",
            f'      - "{http_port}:{container_port}"',
            "    networks:",
            f"      - {central_db_network}",
            "",
            "networks:",
            f"  {central_db_network}:",
            f"    name: {central_db_network}",
            "    external: true",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--http-port", required=True, type=int)
    parser.add_argument("--memory-limit", required=True)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--central-db-network", default="ladock_net")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        runtime = json.loads(args.runtime.read_text(encoding="utf-8"))
        compose = build_runtime_compose(
            args.project,
            args.http_port,
            args.memory_limit,
            runtime,
            args.central_db_network,
        )
        args.output.write_text(compose, encoding="utf-8")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Generated {args.output}")


if __name__ == "__main__":
    main()
