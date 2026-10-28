#!/usr/bin/env python3
"""
Generator dinamis untuk docker-compose-app.yml mode Microservices.

Usage:
    python3 generate_compose.py \
        --project  <project_name> \
        --services '<name1>:<http_port1>,<name2>:<http_port2>,...' \
        --service-paths '<name1>:/abs/path1,<name2>:/abs/path2,...' \
        --docker-dir  /abs/path/to/.docker \
        --gateway-port <port>  \
        --php-versions '<name1>:<phpver1>,<name2>:<phpver2>,...' \
        --composer-versions '<name1>:<compver1>,...' \
        --central-db-network <network_name> \
        --output-dir /abs/path/to/project
"""

import argparse
import json
import os
import re


MEMORY_LIMIT_PATTERN = re.compile(r"[1-9][0-9]*(?:\.[0-9]+)?(?:[bBkKmMgG]|[kKmMgG][bB])?")


def _validate_memory_limit(value: str) -> str:
    if not MEMORY_LIMIT_PATTERN.fullmatch(value):
        raise ValueError(f"Batas memori tidak valid: {value!r}. Gunakan ukuran seperti 512M atau 1G.")
    return value


def _pairs(raw: str) -> dict[str, str]:
    """Parse 'k1:v1,k2:v2,...' menjadi dict."""
    result: dict[str, str] = {}
    if not raw.strip():
        return result
    for item in raw.split(","):
        item = item.strip()
        if ":" not in item:
            continue
        k, _, v = item.partition(":")
        result[k.strip()] = v.strip()
    return result


def _runtime_for_service(service_path: str) -> dict:
    metadata_path = os.path.join(service_path, ".ladock-runtime.json")
    if not os.path.isfile(metadata_path):
        return {
            "language": "PHP",
            "container_port": 80,
            "working_dir": "/var/www",
            "dockerfile": "Dockerfile",
            "custom_dockerfile": False,
        }
    with open(metadata_path, encoding="utf-8") as file:
        return json.load(file)


def build_app_compose(
    project: str,
    services: list[dict],
    gateway_port: int,
    php_versions: dict[str, str],
    composer_versions: dict[str, str],
    service_paths: dict[str, str] | None = None,
    docker_dir: str = ".docker",
    memory_limit: str = "512M",
    central_db_network: str = "ladock_net",
) -> str:
    memory_limit = _validate_memory_limit(memory_limit)
    lines: list[str] = ["services:"]

    # Gateway
    lines += [
        "",
        f"  gateway_{project}:",
        f"    build:",
        f"      context: .docker/gateway",
        f"      dockerfile: Dockerfile",
        f"    container_name: {project}_gateway",
        f"    restart: unless-stopped",
        f"    mem_limit: {memory_limit}",
        f"    ports:",
        f'      - "{gateway_port}:80"',
        f"    volumes:",
        f"      - ./.docker/apache-gateway.conf:/usr/local/apache2/conf/extra/vhost.conf:ro",
        f"    depends_on:",
    ]
    for svc in services:
        lines.append(f"      - app_{svc['name']}")
    lines += [
        f"    networks:",
        f"      - {central_db_network}",
    ]

    # Service app containers
    for svc in services:
        sname = svc["name"]
        http_port = svc["http_port"]
        php_ver = php_versions.get(sname, "8.4")
        comp_ver = composer_versions.get(sname, "2")
        svc_context = (service_paths or {}).get(sname, ".")
        runtime = _runtime_for_service(svc_context)
        dockerfile = f"{docker_dir}/Dockerfile"
        vhost_mount = f"{docker_dir}/apache-vhost.conf"

        lines += [
            "",
            f"  app_{sname}:",
            "    build:",
            f"      context: {svc_context}",
        ]
        if runtime["language"] == "PHP" and not runtime["custom_dockerfile"]:
            lines += [
                f"      dockerfile: {dockerfile}",
                "      args:",
                f'        PHP_VERSION: "{php_ver}"',
                f'        COMPOSER_VERSION: "{comp_ver}"',
            ]
        else:
            lines.append(f"      dockerfile: {runtime['dockerfile']}")

        container_port = int(runtime["container_port"])
        lines += [
            f"    container_name: {project}_{sname}_app",
            "    restart: unless-stopped",
            f"    mem_limit: {memory_limit}",
            f"    working_dir: {runtime['working_dir']}",
            "    env_file:",
            f"      - {json.dumps(os.path.join(svc_context, '.env'))}",
            "    environment:",
            '      APP_ENV: "local"',
            f'      PORT: "{container_port}"',
            f'      SERVER_PORT: "{container_port}"',
        ]
        if runtime["language"] == "PHP" and not runtime["custom_dockerfile"]:
            lines.append(
                f'      LADOCK_DOCUMENT_ROOT: "{runtime.get("document_root", "/var/www/public")}"'
            )
        lines += [
            "    ports:",
            f'      - "{http_port}:{container_port}"',
        ]
        if runtime["language"] == "PHP" and not runtime["custom_dockerfile"]:
            lines += [
                "    volumes:",
                f"      - {svc_context}:/var/www",
                f"      - {vhost_mount}:/etc/apache2/sites-available/000-default.conf:ro",
            ]
        lines += [
            "    networks:",
            f"      - {central_db_network}",
        ]

    lines += [
        "",
        "networks:",
        f"  {central_db_network}:",
        f"    name: {central_db_network}",
        f"    external: true",
    ]

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project",           required=True, help="Nama project (slug)")
    ap.add_argument("--services",          required=True, help="'name1:port1,name2:port2,...'")
    ap.add_argument("--service-paths",     default="",   help="'name1:/path1,name2:/path2,...'")
    ap.add_argument("--docker-dir",        default=".docker", help="Path ke folder .docker/ (absolut)")
    ap.add_argument("--gateway-port",      required=True, type=int)
    ap.add_argument("--memory-limit",      type=_validate_memory_limit, default="512M",
                    help="Batas memori untuk setiap service (contoh: 512M, 1G)")
    ap.add_argument("--central-db-network", default="ladock_net")
    ap.add_argument("--php-versions",      default="",   help="'name1:phpver,name2:phpver,...'")
    ap.add_argument("--composer-versions", default="",   help="'name1:compver,...'")
    ap.add_argument("--output-dir",        required=True, help="Folder tempat menulis docker-compose-app.yml")
    args = ap.parse_args()

    svc_ports = _pairs(args.services)
    services = [{"name": n, "http_port": int(p)} for n, p in svc_ports.items()]
    if not services:
        ap.error("Tidak ada service yang diberikan.")

    php_versions      = _pairs(args.php_versions)
    composer_versions = _pairs(args.composer_versions)

    service_paths = _pairs(args.service_paths)

    app_yaml = build_app_compose(
        project=args.project,
        services=services,
        gateway_port=args.gateway_port,
        php_versions=php_versions,
        composer_versions=composer_versions,
        service_paths=service_paths,
        docker_dir=args.docker_dir,
        memory_limit=args.memory_limit,
        central_db_network=args.central_db_network,
    )

    app_file_path = os.path.join(args.output_dir, ".docker-compose-app.yml")

    with open(app_file_path, "w") as f:
        f.write(app_yaml)

    print(f"Generated {app_file_path}")


if __name__ == "__main__":
    main()
