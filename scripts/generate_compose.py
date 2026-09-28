#!/usr/bin/env python3
"""
Generator dinamis untuk docker-compose.yml mode Microservices.

Membaca metadata service dari argumen dan mengeluarkan konten
docker-compose.yml yang siap dipakai ke stdout.

Setiap service mendapat:
  - Container app berbasis Apache (PHP + Laravel)
  - Database terpisah di dalam 1 container MySQL shared
  - Port host berurutan mulai dari BASE_HTTP_PORT+1

Ditambah container Gateway (Apache reverse-proxy) sebagai pintu depan
tunggal yang merutekan request berdasarkan path prefix.

Usage:
    python3 generate_compose.py \\
        --project  <project_name> \\
        --services '<name1>:<http_port1>,<name2>:<http_port2>,...' \\
        --service-paths '<name1>:/abs/path1,<name2>:/abs/path2,...' \\
        --docker-dir  /abs/path/to/.docker \\
        --gateway-port <port>  \\
        --db-port     <port>   \\
        --php-versions '<name1>:<phpver1>,<name2>:<phpver2>,...' \\
        --composer-versions '<name1>:<compver1>,...' \\
        --db-creds '<name1>:<dbname>:<dbuser>:<dbpass>|...'

Output: konten YAML ke stdout
"""

import argparse
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Compose builder
# ---------------------------------------------------------------------------

def build_compose(
    project: str,
    services: list[dict],         # [{"name": str, "http_port": int}, ...]
    gateway_port: int,
    db_port: int,
    db_creds: dict,               # {svc_name: {"db_name","db_user","db_pass"}}
    db_root_pass: str,
    php_versions: dict[str, str],
    composer_versions: dict[str, str],
    service_paths: dict[str, str] | None = None,  # {svc_name: abs_path}
    docker_dir: str = ".docker",
) -> str:
    lines: list[str] = ["services:"]

    # ── Gateway (Apache httpd reverse proxy) ──────────────────────────────
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

    # ── Service app containers ─────────────────────────────────────────────
    for svc in services:
        sname     = svc["name"]
        http_port = svc["http_port"]
        php_ver   = php_versions.get(sname, "8.4")
        comp_ver  = composer_versions.get(sname, "2")
        creds     = db_creds.get(sname, {})
        db_name   = creds.get("db_name", f"{sname}_db")
        db_user   = creds.get("db_user", f"{sname}_user")
        db_pass   = creds.get("db_pass", "secret")

        # Build context: path absolut folder service (jika tersedia)
        svc_context  = (service_paths or {}).get(sname, ".")
        dockerfile   = f"{docker_dir}/Dockerfile"
        vhost_mount  = f"{docker_dir}/apache-vhost.conf"

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
            f'      DB_HOST: "db_{project}"',
            f'      DB_PORT: "3306"',
            f'      DB_DATABASE: "{db_name}"',
            f'      DB_USERNAME: "{db_user}"',
            f'      DB_PASSWORD: "{db_pass}"',
            f"    depends_on:",
            f"      db_{project}:",
            f"        condition: service_healthy",
            f"    networks:",
            f"      - {project}_net",
        ]

    # ── MySQL shared (1 instance, multi-database) ──────────────────────────
    lines += [
        "",
        f"  db_{project}:",
        f"    image: mysql:8.0",
        f"    container_name: {project}_db",
        f"    restart: unless-stopped",
        f"    command: --default-authentication-plugin=mysql_native_password",
        f"    environment:",
        f'      MYSQL_ROOT_PASSWORD: "{db_root_pass}"',
        f'      MYSQL_DATABASE: "_placeholder"',
        f"    ports:",
        f'      - "{db_port}:3306"',
        f"    volumes:",
        f"      - {project}_dbdata:/var/lib/mysql",
        f"    networks:",
        f"      - {project}_net",
        f"    healthcheck:",
        f'      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-p{db_root_pass}"]',
        f"      interval: 5s",
        f"      timeout: 5s",
        f"      retries: 15",
    ]

    # ── Networks & Volumes ─────────────────────────────────────────────────
    lines += [
        "",
        "networks:",
        f"  {project}_net:",
        "",
        "volumes:",
        f"  {project}_dbdata:",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    args = ap.parse_args()

    # Parse services list
    svc_ports = _pairs(args.services)
    services = [{"name": n, "http_port": int(p)} for n, p in svc_ports.items()]
    if not services:
        print("Tidak ada service yang diberikan.", file=sys.stderr)
        sys.exit(1)

    php_versions      = _pairs(args.php_versions)
    composer_versions = _pairs(args.composer_versions)

    # Parse db creds: name:dbname:dbuser:dbpass
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

    yaml_content = build_compose(
        project=args.project,
        services=services,
        gateway_port=args.gateway_port,
        db_port=args.db_port,
        db_creds=db_creds,
        db_root_pass=args.db_root_pass,
        php_versions=php_versions,
        composer_versions=composer_versions,
        service_paths=service_paths,
        docker_dir=args.docker_dir,
    )

    sys.stdout.write(yaml_content)


if __name__ == "__main__":
    main()
