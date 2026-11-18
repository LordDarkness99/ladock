import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.extract_archive import (
    extract_cpanel_multi_apps,
    find_cpanel_multi_app_plan,
    main as extract_archive_main,
)
from scripts.check_service_usage import inspect_all_services


def test_extract_archive_preserves_cpanel_metadata(tmp_path: Path, monkeypatch, capsys):
    # Buat arsip cpmove dummy dengan userdata dan public_html
    cpmove = tmp_path / "cpmove-demo"
    webroot = cpmove / "homedir/public_html"
    webroot.mkdir(parents=True)
    (webroot / "index.php").write_text("<?php echo 'main';", encoding="utf-8")

    userdata = cpmove / "userdata"
    userdata.mkdir()
    (userdata / "main").write_text("main_domain: demo.local\nsub_domains: []\n", encoding="utf-8")

    archive = tmp_path / "cpmove-demo.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(cpmove, arcname="cpmove-demo")

    output_dir = tmp_path / "extracted"
    monkeypatch.setattr(
        sys,
        "argv",
        ["extract_archive.py", str(archive), str(output_dir)],
    )
    extract_archive_main()

    assert (output_dir / ".cpanel_metadata/userdata/main").is_file()
    assert (output_dir / "index.php").is_file()


def test_cpanel_public_html_priority_over_other_homedir_dirs(tmp_path: Path, monkeypatch):
    # Struktur cPanel dengan folder acak di homedir dan public_html
    cpmove = tmp_path / "cpmove-site"
    homedir = cpmove / "homedir"
    homedir.mkdir(parents=True)

    # Folder sampah di luar public_html
    other_dir = homedir / "old_backup"
    other_dir.mkdir()
    (other_dir / "index.php").write_text("<?php echo 'junk';", encoding="utf-8")

    # Folder utama public_html
    pub = homedir / "public_html"
    pub.mkdir()
    (pub / "index.php").write_text("<?php echo 'active public_html';", encoding="utf-8")

    archive = tmp_path / "cpmove-site.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(cpmove, arcname="cpmove-site")

    output_dir = tmp_path / "extracted_site"
    monkeypatch.setattr(
        sys,
        "argv",
        ["extract_archive.py", str(archive), str(output_dir)],
    )
    extract_archive_main()

    # Pastikan yang disalin adalah public_html, bukan old_backup
    assert (output_dir / "index.php").read_text(encoding="utf-8") == "<?php echo 'active public_html';"


def test_deploy_script_check_only_flag(tmp_path: Path):
    deploy_sh = Path(__file__).parent.parent / "deploy.sh"
    # Buat dummy multi-service apps
    app_root = tmp_path / "my_cpanel_proj"
    apps_dir = app_root / "apps"
    apps_dir.mkdir(parents=True)

    root_web = apps_dir / "root_web"
    root_web.mkdir()
    (root_web / "index.php").write_text("<?php", encoding="utf-8")

    tesis = apps_dir / "tesis"
    tesis.mkdir()
    (tesis / "index.php").write_text("<?php", encoding="utf-8")
    (tesis / "tesis.zip").write_text("dummy", encoding="utf-8")

    # Jalankan ./deploy.sh --check-only
    proc = subprocess.run(
        ["bash", str(deploy_sh), str(app_root), "--check-only"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "PEMERIKSAAN STATUS PENGGUNAAN SERVICE" in proc.stdout
    assert "root_web" in proc.stdout
    assert "tesis" in proc.stdout
    assert "SERVICE TIDAK DIGUNAKAN" in proc.stdout
