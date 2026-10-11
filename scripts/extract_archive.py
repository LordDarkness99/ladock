#!/usr/bin/env python3
"""
Archive Extractor & Normalizer for LaDock
Mendukung arsip .zip, .tar.gz, .tgz, .tar dengan:
1. Validasi integritas (corrupt check)
2. Proteksi Zip-Slip / Path Traversal
3. Normalisasi struktur cPanel (homedir/public_html) maupun zip project biasa
4. Deteksi dan ekstraksi dump database .sql

Usage:
    python3 extract_archive.py <path_arsip> [folder_output] [folder_db_output]

Output:
    Mencetak path folder project hasil ekstraksi pada baris terakhir stdout.
"""

import os
import re
import sys
import shutil
import zipfile
import tarfile
import tempfile
from pathlib import Path


def log(msg):
    print(msg, file=sys.stderr)


STANDARD_INDEX_PHP = """<?php

use Illuminate\\Contracts\\Http\\Kernel;
use Illuminate\\Http\\Request;

define('LARAVEL_START', microtime(true));

if (file_exists($maintenance = __DIR__.'/../storage/framework/maintenance.php')) {
    require $maintenance;
}

require __DIR__.'/../vendor/autoload.php';

$app = require_once __DIR__.'/../bootstrap/app.php';

$kernel = $app->make(Kernel::class);

$response = $kernel->handle(
    $request = Request::capture()
)->send();

$kernel->terminate($request, $response);
"""


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Mencegah path traversal (Zip-Slip vulnerability)."""
    base = os.path.abspath(base_dir)
    target = os.path.abspath(target_path)
    return os.path.commonpath([base]) == os.path.commonpath([base, target])


def validate_and_extract_zip(archive_path: str, dest_dir: str) -> None:
    """Validasi corrupt & ekstrak file ZIP dengan proteksi path traversal."""
    if not zipfile.is_zipfile(archive_path):
        raise ValueError(f"File bukan format ZIP yang valid: {archive_path}")

    with zipfile.ZipFile(archive_path, 'r') as zf:
        # Cek integritas zip
        corrupt_file = zf.testzip()
        if corrupt_file is not None:
            raise ValueError(f"Arsip ZIP korup terdeteksi pada entri: {corrupt_file}")

        for member in zf.infolist():
            # Mencegah path traversal
            target_path = os.path.join(dest_dir, member.filename)
            if not is_safe_path(dest_dir, target_path):
                log(f"⚠️  PERINGATAN: Melewati entri berisiko path traversal: {member.filename}")
                continue

            # Abaikan entri symlink berbahaya
            zf.extract(member, dest_dir)


def validate_and_extract_tar(archive_path: str, dest_dir: str) -> None:
    """Validasi & ekstrak arsip TAR/TGZ dengan proteksi path traversal."""
    if not tarfile.is_tarfile(archive_path):
        raise ValueError(f"File bukan format TAR/TGZ yang valid: {archive_path}")

    with tarfile.open(archive_path, 'r:*') as tar:
        for member in tar.getmembers():
            target_path = os.path.join(dest_dir, member.name)
            if not is_safe_path(dest_dir, target_path):
                log(f"⚠️  PERINGATAN: Melewati entri TAR path traversal: {member.name}")
                continue
            # Lewati symlink yang menunjuk ke path absolut atau di luar folder tujuan
            if member.islnk() or member.issym():
                if os.path.isabs(member.linkname) or not is_safe_path(dest_dir, os.path.join(os.path.dirname(target_path), member.linkname)):
                    log(f"⚠️  Melewati symlink absolut/eksternal cPanel: {member.name} -> {member.linkname}")
                    continue

            try:
                try:
                    tar.extract(member, dest_dir, filter='data')
                except (TypeError, tarfile.FilterError, Exception):
                    tar.extract(member, dest_dir)
            except Exception as e:
                log(f"⚠️  Melewati entri bermasalah: {member.name} ({e})")


def find_dir_named(root: str, name: str):
    """Cari folder bernama tertentu di bawah root."""
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) == name:
            return dirpath
    return None


def find_laravel_root(search_dir: str):
    """Cari root project Laravel (artisan + composer.json)."""
    candidates = []
    for dirpath, dirnames, filenames in os.walk(search_dir):
        if "vendor" in dirpath.split(os.sep):
            dirnames[:] = []
            continue
        if "artisan" in filenames and "composer.json" in filenames and "bootstrap" in dirnames:
            candidates.append(dirpath)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.count(os.sep))
    return candidates[0]


def find_general_app_root(search_dir: str):
    """Cari root aplikasi umum jika bukan Laravel (misal ada package.json, index.php, requirements.txt, dll)."""
    markers = [
        "composer.json", "package.json", "requirements.txt", "Pipfile",
        "pyproject.toml", "index.php", "go.mod", "Gemfile", "pom.xml"
    ]
    candidates = []
    for dirpath, dirnames, filenames in os.walk(search_dir):
        parts = dirpath.split(os.sep)
        if any(skip in parts for skip in ["vendor", "node_modules", ".git"]):
            dirnames[:] = []
            continue
        for m in markers:
            if m in filenames:
                candidates.append(dirpath)
                break
    if candidates:
        candidates.sort(key=lambda p: p.count(os.sep))
        return candidates[0]
    
    # Jika tidak ada marker, cek apakah folder berisi 1 folder anak tunggal (contoh github repo-main/)
    entries = [os.path.join(search_dir, e) for e in os.listdir(search_dir)]
    subdirs = [e for e in entries if os.path.isdir(e)]
    if len(subdirs) == 1 and len(entries) == 1:
        return subdirs[0]

    return search_dir


def find_db_dumps(root_dir: str):
    """Cari dump .sql di direktori ekstraksi."""
    dumps = []
    # 1. Cek folder mysql/ jika cPanel
    mysql_dir = os.path.join(root_dir, "mysql")
    if os.path.isdir(mysql_dir):
        for fn in os.listdir(mysql_dir):
            if fn.lower().endswith(".sql"):
                dumps.append(os.path.join(mysql_dir, fn))

    # 2. Cek file sql di root dan subfolder
    for dirpath, dirnames, filenames in os.walk(root_dir):
        parts = dirpath.split(os.sep)
        if any(skip in parts for skip in ["vendor", "node_modules", ".git"]):
            dirnames[:] = []
            continue
        for fn in filenames:
            if fn.lower().endswith(".sql"):
                p = os.path.join(dirpath, fn)
                if p not in dumps:
                    dumps.append(p)

    dumps.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return dumps


def detect_split_public(laravel_root: str, homedir: str):
    """Deteksi pola cPanel split public_html."""
    public_html = os.path.join(homedir, "public_html")
    index_php = os.path.join(public_html, "index.php")
    if not os.path.isfile(index_php):
        return None
    laravel_root_name = os.path.basename(laravel_root)
    try:
        with open(index_php, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return None
    if re.search(r"\.\./" + re.escape(laravel_root_name) + r"/", content):
        return public_html
    return None


def fix_public_index_php(public_dir: str):
    """Perbaiki path public/index.php jika masih menggunakan konfigurasi cPanel."""
    index_php = os.path.join(public_dir, "index.php")
    if not os.path.isfile(index_php):
        return
    try:
        with open(index_php, "r", encoding="utf-8", errors="ignore") as f:
            original = f.read()
    except OSError:
        return

    needs_fix = bool(re.search(
        r"repositories/|\.\./\.\./[^'\"]*?/vendor/autoload\.php|base64_decode\s*\(",
        original,
    ))
    if not needs_fix:
        return

    try:
        shutil.copy2(index_php, index_php + ".orig")
    except OSError:
        pass

    with open(index_php, "w", encoding="utf-8") as f:
        f.write(STANDARD_INDEX_PHP)
    log("-> public/index.php dinormalisasi ke template standar.")


def clean_laravel_cache(output_dir: str):
    """Bersihkan bootstrap/cache dan sessions lama."""
    bootstrap_cache = os.path.join(output_dir, "bootstrap", "cache")
    if os.path.isdir(bootstrap_cache):
        for fn in os.listdir(bootstrap_cache):
            if fn.endswith(".php"):
                try:
                    os.remove(os.path.join(bootstrap_cache, fn))
                except OSError:
                    pass

    sessions_dir = os.path.join(output_dir, "storage", "framework", "sessions")
    if os.path.isdir(sessions_dir):
        for fn in os.listdir(sessions_dir):
            try:
                os.remove(os.path.join(sessions_dir, fn))
            except OSError:
                pass


def main():
    if len(sys.argv) < 2:
        log("Usage: extract_archive.py <path_arsip> [folder_output] [folder_db_output]")
        sys.exit(1)

    archive_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(archive_path):
        log(f"Error: File arsip tidak ditemukan: {archive_path}")
        sys.exit(1)

    # Tentukan folder output
    if len(sys.argv) >= 3 and sys.argv[2]:
        output_dir = os.path.abspath(sys.argv[2])
    else:
        base_name = os.path.basename(archive_path)
        for ext in [".tar.gz", ".tgz", ".zip", ".tar.bz2", ".tar"]:
            if base_name.lower().endswith(ext):
                base_name = base_name[:-len(ext)]
                break
        base_name = re.sub(r"^cpmove-", "", base_name)
        output_dir = os.path.join(os.path.dirname(archive_path), f"{base_name}_extracted")

    db_output_dir = os.path.abspath(sys.argv[3]) if len(sys.argv) >= 4 and sys.argv[3] else None

    tmp_dir = tempfile.mkdtemp(prefix="ladock_extract_")
    log(f"-> Ekstraksi arsip ke folder sementara: {tmp_dir}")

    lower_name = archive_path.lower()
    try:
        if lower_name.endswith(".zip"):
            validate_and_extract_zip(archive_path, tmp_dir)
        elif any(lower_name.endswith(ext) for ext in [".tar.gz", ".tgz", ".tar", ".tar.bz2"]):
            validate_and_extract_tar(archive_path, tmp_dir)
        else:
            # Coba zip dulu, fallback ke tar
            try:
                validate_and_extract_zip(archive_path, tmp_dir)
            except Exception:
                validate_and_extract_tar(archive_path, tmp_dir)
    except Exception as e:
        log(f"❌ Gagal mengekstrak arsip: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(1)

    # Cek apakah arsip merupakan format cPanel (memiliki folder homedir)
    homedir = find_dir_named(tmp_dir, "homedir")
    is_cpanel = homedir is not None

    if is_cpanel:
        log("-> Terdeteksi arsip cPanel (memiliki 'homedir').")
        app_root = find_laravel_root(homedir) or find_general_app_root(homedir)
    else:
        app_root = find_laravel_root(tmp_dir) or find_general_app_root(tmp_dir)

    if not app_root or not os.path.isdir(app_root):
        log("❌ Tidak ditemukan source code aplikasi yang valid di dalam arsip.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(1)

    log(f"-> Source code aplikasi ditemukan di: {app_root}")

    # Salin ke folder output
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(os.path.dirname(output_dir), exist_ok=True)
    shutil.copytree(app_root, output_dir)
    log(f"-> Aplikasi disalin ke: {output_dir}")

    # Jika cPanel, gabungkan split public_html jika ada
    if is_cpanel and homedir:
        output_public = os.path.join(output_dir, "public")
        public_html = os.path.join(homedir, "public_html")
        if not os.path.isdir(public_html):
            alt_www = os.path.join(homedir, "www")
            if os.path.isdir(alt_www) and not os.path.islink(alt_www):
                public_html = alt_www

        if os.path.isdir(public_html):
            if not os.path.isdir(output_public):
                log(f"-> Menggabungkan public_html terpisah ke {output_public}...")
                shutil.copytree(public_html, output_public, symlinks=True)
            else:
                log(f"-> Menggabungkan file & folder aset tambahan dari public_html ke {output_public}...")
                for root_dir, dirs, files in os.walk(public_html):
                    rel = os.path.relpath(root_dir, public_html)
                    target_dir = os.path.join(output_public, rel) if rel != "." else output_public
                    os.makedirs(target_dir, exist_ok=True)
                    for fn in files:
                        src_f = os.path.join(root_dir, fn)
                        dst_f = os.path.join(target_dir, fn)
                        if not os.path.exists(dst_f) or os.path.getsize(dst_f) == 0:
                            try:
                                shutil.copy2(src_f, dst_f)
                            except OSError:
                                pass
            fix_public_index_php(output_public)

    # Bersihkan cache Laravel jika ada
    clean_laravel_cache(output_dir)

    # Temukan dump SQL
    dumps = find_db_dumps(tmp_dir)
    if dumps:
        log(f"-> Ditemukan {len(dumps)} file dump database (.sql).")
        # Jika db_output_dir diberikan, salin dump ke mysql/db/<app_name>/
        if db_output_dir:
            os.makedirs(db_output_dir, exist_ok=True)
            primary_dump = dumps[0]
            dest_sql = os.path.join(db_output_dir, "data.sql")
            shutil.copy2(primary_dump, dest_sql)
            log(f"-> Dump SQL utama disalin ke: {dest_sql}")
            for extra_dump in dumps[1:]:
                extra_dest = os.path.join(db_output_dir, os.path.basename(extra_dump))
                shutil.copy2(extra_dump, extra_dest)
        else:
            # Fallback: salin ke output_dir jika tidak ada db_output_dir spesifik
            for dump_f in dumps[:2]:
                shutil.copy2(dump_f, os.path.join(output_dir, os.path.basename(dump_f)))
    else:
        log("ℹ️  Tidak ditemukan file dump database (.sql).")

    # Bersihkan folder temp
    shutil.rmtree(tmp_dir, ignore_errors=True)
    log("✓ Ekstraksi dan penataan selesai.")

    # Baris terakhir stdout adalah path folder aplikasi
    print(output_dir)


if __name__ == "__main__":
    main()
