import sys
import tarfile
from pathlib import Path

from scripts.extract_archive import (
    extract_cpanel_multi_apps,
    find_cpanel_multi_app_plan,
    main as extract_archive_main,
)
from scripts.find_microservices import scan


def _create_codeigniter_app(path: Path):
    (path / "application/config").mkdir(parents=True)
    (path / "application/config/database.php").write_text("<?php", encoding="utf-8")
    (path / "index.php").write_text("<?php", encoding="utf-8")


def test_cpanel_webroot_is_split_into_root_and_nested_services(tmp_path: Path):
    web_root = tmp_path / "homedir/public_html"
    web_root.mkdir(parents=True)
    (web_root / "index.php").write_text("<?php", encoding="utf-8")
    (web_root / "cek.php").write_text("<?php", encoding="utf-8")
    (web_root / "lib").mkdir()

    wordpress = web_root / "index2"
    (wordpress / "wp-admin").mkdir(parents=True)
    (wordpress / "wp-includes").mkdir()
    (wordpress / "wp-config.php").write_text("<?php", encoding="utf-8")

    _create_codeigniter_app(web_root / "individu")
    _create_codeigniter_app(web_root / "tesis")

    surveylance = web_root / "surveylance"
    (surveylance / "apps").mkdir(parents=True)
    (surveylance / "config").mkdir()
    (surveylance / "config/databases.yml").write_text("all:\n", encoding="utf-8")
    (surveylance / "index.php").write_text("<?php", encoding="utf-8")

    plan = find_cpanel_multi_app_plan(str(web_root.parent))
    assert plan is not None
    assert {service["name"] for service in plan["sub_services"]} == {
        "index2",
        "individu",
        "surveylance",
        "tesis",
    }

    output = tmp_path / "normalized"
    extract_cpanel_multi_apps(plan, str(output))

    services = scan(str(output))
    assert {service["name"] for service in services} == {
        "root_web",
        "index2",
        "individu",
        "surveylance",
        "tesis",
    }
    root_service = output / "apps/root_web"
    assert (root_service / "index.php").is_file()
    assert (root_service / "lib").is_dir()
    assert not (root_service / "index2").exists()
    assert not (root_service / "individu").exists()


def test_cpanel_plan_is_not_used_when_root_is_not_a_legacy_php_app(tmp_path: Path):
    web_root = tmp_path / "homedir/public_html"
    wordpress = web_root / "index2"
    (wordpress / "wp-admin").mkdir(parents=True)
    (wordpress / "wp-includes").mkdir()
    (wordpress / "wp-config.php").write_text("<?php", encoding="utf-8")

    assert find_cpanel_multi_app_plan(str(web_root.parent)) is None


def test_cpanel_archive_extracts_all_apps_and_named_database_dumps(tmp_path: Path, monkeypatch, capsys):
    account = tmp_path / "cpmove"
    web_root = account / "homedir/public_html"
    web_root.mkdir(parents=True)
    (web_root / "index.php").write_text("<?php", encoding="utf-8")
    (web_root / "cek.php").write_text("<?php", encoding="utf-8")
    (web_root / "lib").mkdir()

    wordpress = web_root / "index2"
    (wordpress / "wp-admin").mkdir(parents=True)
    (wordpress / "wp-includes").mkdir()
    (wordpress / "wp-config.php").write_text("<?php", encoding="utf-8")
    _create_codeigniter_app(web_root / "individu")
    _create_codeigniter_app(web_root / "tesis")
    surveylance = web_root / "surveylance"
    (surveylance / "apps").mkdir(parents=True)
    (surveylance / "config").mkdir()
    (surveylance / "config/databases.yml").write_text("all:\n", encoding="utf-8")
    (surveylance / "index.php").write_text("<?php", encoding="utf-8")

    mysql_dir = account / "mysql"
    mysql_dir.mkdir()
    (mysql_dir / "imunisas_individu.sql").write_text("CREATE TABLE sample (id INT);", encoding="utf-8")
    archive = tmp_path / "cpmove-sample.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(account, arcname="cpmove-sample")

    output = tmp_path / "extracted"
    db_output = tmp_path / "database"
    monkeypatch.setattr(
        sys,
        "argv",
        ["extract_archive.py", str(archive), str(output), str(db_output)],
    )
    extract_archive_main()
    captured = capsys.readouterr()

    assert str(output) in captured.out
    assert {service["name"] for service in scan(str(output))} == {
        "root_web",
        "index2",
        "individu",
        "surveylance",
        "tesis",
    }
    assert (db_output / "imunisas_individu.sql").is_file()
