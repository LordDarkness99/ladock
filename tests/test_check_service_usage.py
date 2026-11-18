import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.check_service_usage import (
    evaluate_service_usage,
    inspect_all_services,
    parse_cpanel_userdata,
    parse_cpanel_bandwidth,
    detect_configured_database,
    find_internal_archives,
    format_cli_report,
)


def test_detect_internal_archives(tmp_path: Path):
    svc = tmp_path / "my_service"
    svc.mkdir()
    (svc / "index.php").write_text("<?php", encoding="utf-8")
    (svc / "backup_archive.zip").write_text("fake zip", encoding="utf-8")
    (svc / "public.tar.gz").write_text("fake tar", encoding="utf-8")

    archives = find_internal_archives(str(svc))
    assert set(archives) == {"backup_archive.zip", "public.tar.gz"}


def test_detect_configured_database_codeigniter(tmp_path: Path):
    svc = tmp_path / "ci_app"
    cfg = svc / "application/config"
    cfg.mkdir(parents=True)
    (cfg / "database.php").write_text(
        """<?php
        $db['default']['database'] = 'my_real_db';
        """,
        encoding="utf-8",
    )
    assert detect_configured_database(str(svc)) == "my_real_db"


def test_detect_configured_database_wordpress(tmp_path: Path):
    svc = tmp_path / "wp_app"
    svc.mkdir()
    (svc / "wp-config.php").write_text(
        """<?php
        define('DB_NAME', 'wordpress_live');
        """,
        encoding="utf-8",
    )
    assert detect_configured_database(str(svc)) == "wordpress_live"


def test_detect_configured_database_symfony(tmp_path: Path):
    svc = tmp_path / "sym_app"
    cfg = svc / "config"
    cfg.mkdir(parents=True)
    (cfg / "databases.yml").write_text(
        """all:
  propel:
    param:
      dsn: mysql:dbname=symfony_db;host=127.0.0.1
        """,
        encoding="utf-8",
    )
    assert detect_configured_database(str(svc)) == "symfony_db"


def test_parse_cpanel_userdata(tmp_path: Path):
    meta_dir = tmp_path / "userdata"
    meta_dir.mkdir()
    (meta_dir / "cache.json").write_text(
        json.dumps({
            "sub.domain.com": ["user", "root", "sub", "domain.com", "/home/user/public_html/sub"],
            "domain.com": ["user", "root", "main", "domain.com", "/home/user/public_html"],
        }),
        encoding="utf-8",
    )
    (meta_dir / "main").write_text(
        """---
main_domain: domain.com
sub_domains:
  - sub.domain.com
        """,
        encoding="utf-8",
    )

    data = parse_cpanel_userdata(str(tmp_path))
    assert data["has_cpanel_meta"] is True
    assert data["main_domain"] == "domain.com"
    assert "sub.domain.com" in data["sub_domains"]
    assert data["docroots"]["sub.domain.com"] == "/home/user/public_html/sub"


def test_parse_cpanel_bandwidth(tmp_path: Path):
    meta_dir = tmp_path / "bandwidth"
    meta_dir.mkdir()
    (meta_dir / "bandwidth_db.json").write_text(
        json.dumps({
            "domains": {
                "active.domain.com": 4200,
                "domain.com": 15000,
                "UNKNOWN": 1,
            }
        }),
        encoding="utf-8",
    )

    bw = parse_cpanel_bandwidth(str(tmp_path))
    assert bw["active.domain.com"] == 4200
    assert bw["domain.com"] == 15000


def test_evaluate_service_usage_active_vs_unused_cpanel(tmp_path: Path):
    # Setup cPanel metadata
    meta_dir = tmp_path / ".cpanel_metadata"
    meta_dir.mkdir()
    userdata = meta_dir / "userdata"
    userdata.mkdir()
    (userdata / "main").write_text(
        """---
main_domain: example.gov.id
sub_domains:
  - portal.example.gov.id
        """,
        encoding="utf-8",
    )
    (userdata / "cache.json").write_text(
        json.dumps({
            "example.gov.id": ["usr", "root", "main", "example.gov.id", "/home/usr/public_html"],
            "portal.example.gov.id": ["usr", "root", "sub", "example.gov.id", "/home/usr/public_html/portal"],
        }),
        encoding="utf-8",
    )
    (meta_dir / "bandwidth_db.json").write_text(
        json.dumps({"domains": {"example.gov.id": 100, "portal.example.gov.id": 50}}),
        encoding="utf-8",
    )

    # Setup database dumps directory
    db_dir = tmp_path / "db_dumps"
    db_dir.mkdir()
    (db_dir / "example_main.sql").write_text("CREATE TABLE t (id INT);", encoding="utf-8")
    (db_dir / "portal_db.sql").write_text("CREATE TABLE t (id INT);", encoding="utf-8")

    # Service 1: root_web (Main site)
    root_web = tmp_path / "apps/root_web"
    root_web.mkdir(parents=True)
    (root_web / "index.php").write_text("<?php", encoding="utf-8")

    # Service 2: portal (Subdomain)
    portal = tmp_path / "apps/portal"
    portal.mkdir(parents=True)
    (portal / "index.php").write_text("<?php", encoding="utf-8")

    # Service 3: tesis (Thesis / junk)
    tesis = tmp_path / "apps/tesis"
    tesis.mkdir(parents=True)
    (tesis / "index.php").write_text("<?php", encoding="utf-8")
    (tesis / "tesis.zip").write_text("dummy", encoding="utf-8")

    # Service 4: unused_backup (contains archive, missing DB)
    backup_app = tmp_path / "apps/old_app"
    backup_app.mkdir(parents=True)
    (backup_app / "index.php").write_text("<?php", encoding="utf-8")
    (backup_app / "app.tar.gz").write_text("dummy", encoding="utf-8")

    services = [
        {"name": "root_web", "path": str(root_web)},
        {"name": "portal", "path": str(portal)},
        {"name": "tesis", "path": str(tesis)},
        {"name": "old_app", "path": str(backup_app)},
    ]

    results = inspect_all_services(
        services=services,
        project_dir=str(tmp_path),
        cpanel_meta_dir=str(meta_dir),
        db_dumps_dir=str(db_dir),
    )

    status_by_name = {r["name"]: r["is_used"] for r in results}
    assert status_by_name["root_web"] is True
    assert status_by_name["portal"] is True
    assert status_by_name["tesis"] is False
    assert status_by_name["old_app"] is False

    report = format_cli_report(results)
    assert "root_web" in report
    assert "portal" in report
    assert "SERVICE MASIH DIGUNAKAN (2 service" in report
    assert "SERVICE TIDAK DIGUNAKAN (2 service" in report


def test_cli_override_include_and_exclude(tmp_path: Path):
    s1 = tmp_path / "app1"
    s1.mkdir()
    (s1 / "index.php").write_text("<?php", encoding="utf-8")

    s2 = tmp_path / "tesis"
    s2.mkdir()
    (s2 / "index.php").write_text("<?php", encoding="utf-8")

    services = [
        {"name": "app1", "path": str(s1)},
        {"name": "tesis", "path": str(s2)},
    ]

    # Include tesis specifically
    results = inspect_all_services(
        services=services,
        force_include=["tesis"],
        force_exclude=["app1"],
    )
    status_by_name = {r["name"]: r["is_used"] for r in results}
    assert status_by_name["tesis"] is True
    assert status_by_name["app1"] is False
