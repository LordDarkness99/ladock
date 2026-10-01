#!/usr/bin/env python3
"""
Generator dinamis untuk docker-compose-db.yml dan docker-compose-app.yml mode Microservices.

Usage:
    python3 generate_compose.py \
        --project  <project_name> \
        --services '<name1>:<http_port1>,<name2>:<http_port2>,...' \
        --service-paths '<name1>:/abs/path1,<name2>:/abs/path2,...' \
        --docker-dir  /abs/path/to/.docker \
        --gateway-port <port>  \
        --db-port     <port>   \
        --php-versions '<name1>:<phpver1>,<name2>:<phpver2>,...' \
        --composer-versions '<name1>:<compver1>,...' \
        --db-creds '<name1>:<dbname>:<dbuser>:<dbpass>|...' \
        --output-dir /abs/path/to/project
"""

import argparse
import sys
import os


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


def build_db_compose(
    project: str,
    services: list[dict],
    base_db_port: int,
    db_creds: dict,
    db_root_pass: str,
) -> str:
    lines: list[str] = ["services:"]

    for idx, svc in enumerate(services):
        sname = svc["name"]
        svc_db_port = base_db_port + idx
        creds = db_creds.get(sname, {})
        db_name = creds.get("db_name", f"{sname}_db")
        db_user = creds.get("db_user", f"{sname}_user")
        db_pass = creds.get("db_pass", "secret")

        lines += [
            "",
            f"  db_{sname}:",
            f"    image: mysql:8.0",
            f"    container_name: {project}_{sname}_db",
            f"    restart: unless-stopped",
            f"    command: --default-authentication-plugin=mysql_native_password",
            f"    environment:",
            f'      MYSQL_ROOT_PASSWORD: "{db_root_pass}"',
            f'      MYSQL_DATABASE: "{db_name}"',
            f'      MYSQL_USER: "{db_user}"',
            f'      MYSQL_PASSWORD: "{db_pass}"',
            f"    ports:",
            f'      - "{svc_db_port}:3306"',
            f"    volumes:",
            f"      - {project}_{sname}_dbdata:/var/lib/mysql",
            f"    networks:",
            f"      - {project}_net",
            f"    healthcheck:",
            f'      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-p{db_root_pass}"]',
            f"      interval: 5s",
            f"      timeout: 5s",
            f"      retries: 15",
        ]

    lines += [
        "",
        "networks:",
        f"  {project}_net:",
        f"    name: {project}_net",
        "",
        "volumes:",
    ]
    for svc in services:
        sname = svc["name"]
        lines.append(f"  {project}_{sname}_dbdata:")

    return "\n".join(lines) + "\n"


def build_app_compose(
    project: str,
    services: list[dict],
    gateway_port: int,
    db_creds: dict,
    php_versions: dict[str, str],
    composer_versions: dict[str, str],
    service_paths: dict[str, str] | None = None,
    docker_dir: str = ".docker",
) -> str:
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
        f"      - {project}_net",
    ]

    # Service app containers
    for svc in services:
        sname = svc["name"]
        http_port = svc["http_port"]
        php_ver = php_versions.get(sname, "8.4")
        comp_ver = composer_versions.get(sname, "2")
        creds = db_creds.get(sname, {})
        db_name = creds.get("db_name", f"{sname}_db")
        db_user = creds.get("db_user", f"{sname}_user")
        db_pass = creds.get("db_pass", "secret")

        svc_context = (service_paths or {}).get(sname, ".")
        dockerfile = f"{docker_dir}/Dockerfile"
        vhost_mount = f"{docker_dir}/apache-vhost.conf"

        lines += [
            "",
            f"  app_{sname}:",
            f"    build:",
            f"      context: {svc_context}",
            f"      dockerfile: {dockerfile}",
            f"      args:",
            f'        PHP_VERSION: "{php_ver}"',
            f'        COMPOSER_VERSION: "{comp_ver}"',
            f"    container_name: {project}_{sname}_app",
            f"    restart: unless-stopped",
            f"    working_dir: /var/www",
            f"    ports:",
            f'      - "{http_port}:80"',
            f"    volumes:",
            f"      - {svc_context}:/var/www",
            f"      - {vhost_mount}:/etc/apache2/sites-available/000-default.conf:ro",
            f"    environment:",
            f'      APP_ENV: "local"',
            f'      DB_CONNECTION: "mysql"',
            f'      DB_HOST: "db_{sname}"',
            f'      DB_PORT: "3306"',
            f'      DB_DATABASE: "{db_name}"',
            f'      DB_USERNAME: "{db_user}"',
            f'      DB_PASSWORD: "{db_pass}"',
            f"    networks:",
            f"      - {project}_net",
        ]

    lines += [
        "",
        "networks:",
        f"  {project}_net:",
        f"    name: {project}_net",
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
    ap.add_argument("--db-port",           required=True, type=int)
    ap.add_argument("--db-root-pass",      required=True)
    ap.add_argument("--php-versions",      default="",   help="'name1:phpver,name2:phpver,...'")
    ap.add_argument("--composer-versions", default="",   help="'name1:compver,...'")
    ap.add_argument("--db-creds",          default="",
                    help="'svcname:dbname:dbuser:dbpass|...' (pipe-separated per service)")
    ap.add_argument("--output-dir",        required=True, help="Folder tempat menulis docker-compose-db.yml dan docker-compose-app.yml")
    args = ap.parse_args()

    svc_ports = _pairs(args.services)
    services = [{"name": n, "http_port": int(p)} for n, p in svc_ports.items()]
    if not services:
        print("Tidak ada service yang diberikan.", file=sys.stderr)
        sys.exit(1)

    php_versions      = _pairs(args.php_versions)
    composer_versions = _pairs(args.composer_versions)

    db_creds: dict[str, dict] = {}
    if args.db_creds.strip():
        for entry in args.db_creds.split("|"):
            parts = entry.strip().split(":")
            if len(parts) >= 4:
                svc_name = parts[0]
                db_creds[svc_name] = {
                    "db_name": parts[1],
                    "db_user": parts[2],
                    "db_pass": parts[3],
                }

    service_paths = _pairs(args.service_paths)

    db_yaml = build_db_compose(
        project=args.project,
        services=services,
        base_db_port=args.db_port,
        db_creds=db_creds,
        db_root_pass=args.db_root_pass,
    )

    app_yaml = build_app_compose(
        project=args.project,
        services=services,
        gateway_port=args.gateway_port,
        db_creds=db_creds,
        php_versions=php_versions,
        composer_versions=composer_versions,
        service_paths=service_paths,
        docker_dir=args.docker_dir,
    )

    db_file_path = os.path.join(args.output_dir, ".docker-compose-db.yml")
    app_file_path = os.path.join(args.output_dir, ".docker-compose-app.yml")

    with open(db_file_path, "w") as f:
        f.write(db_yaml)

    with open(app_file_path, "w") as f:
        f.write(app_yaml)

    print(f"Generated {db_file_path} and {app_file_path}")


if __name__ == "__main__":
    main()
