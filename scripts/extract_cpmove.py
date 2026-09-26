#!/usr/bin/env python3
"""
Extract arsip backup cPanel (cpmove-*.tar.gz / backup-*.tar.gz) dan susun ulang
jadi struktur project Laravel yang normal (artisan + public/ jadi satu folder),
supaya bisa langsung dipakai oleh deploy.sh.

Beberapa hosting cPanel menaruh folder 'public' Laravel terpisah dari kode
aplikasinya sendiri (mis. app Laravel di homedir/repositories/, sedangkan
webroot yang sebenarnya ada di homedir/public_html/, dengan public_html/index.php
me-require '../repositories/...'). Script ini mendeteksi pola itu dan
menggabungkannya jadi satu folder project yang siap dipakai deploy.sh.

Setelah public digabung, index.php ditulis ulang total dengan template standar
Laravel (fix_public_index_php) — bukan regex replace, karena regex rapuh
terhadap variasi penulisan + komentar blok yang bisa "memakan" baris require.

Usage:
    python3 extract_cpmove.py /path/ke/cpmove-xxx.tar.gz /path/output/project

Print HANYA path project hasil akhir ke stdout (baris terakhir), sisanya ke
stderr, supaya gampang ditangkap lewat $(...) di bash.
"""
import os
import re
import shutil
import sys
import tarfile
import tempfile


def log(msg):
    print(msg, file=sys.stderr)


# Template index.php standar Laravel 5.6+ — kompatibel sampai Laravel 10.
# Sengaja TIDAK menyertakan baris backdoor yang kadang ditempel di arsip cPanel
# (mis. "@include base64_decode('...')" yang menyamar jadi gambar).
STANDARD_INDEX_PHP = """<?php

use Illuminate\\Contracts\\Http\\Kernel;
use Illuminate\\Http\\Request;

define('LARAVEL_START', microtime(true));

/*
|--------------------------------------------------------------------------
| Check If The Application Is Under Maintenance
|--------------------------------------------------------------------------
|
| If the application is in maintenance / demo mode via the "down" command
| we will load this file so that any pre-rendered content can be shown
| instead of starting the framework, which could cause an exception.
|
*/

if (file_exists($maintenance = __DIR__.'/../storage/framework/maintenance.php')) {
    require $maintenance;
}

/*
|--------------------------------------------------------------------------
| Register The Auto Loader
|--------------------------------------------------------------------------
*/

require __DIR__.'/../vendor/autoload.php';

/*
|--------------------------------------------------------------------------
| Turn On The Lights
|--------------------------------------------------------------------------
*/

$app = require_once __DIR__.'/../bootstrap/app.php';

/*
|--------------------------------------------------------------------------
| Run The Application
|--------------------------------------------------------------------------
*/

$kernel = $app->make(Kernel::class);

$response = $kernel->handle(
    $request = Request::capture()
)->send();

$kernel->terminate($request, $response);
"""


def find_dir_named(root, name):
    """Cari folder bernama persis `name` di bawah root."""
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) == name:
            return dirpath
    return None


def find_laravel_root(homedir):
    """Cari folder yang benar-benar root Laravel: punya artisan + composer.json +
    bootstrap/, dan BUKAN di dalam vendor/ (banyak paket vendor ikut nyimpan file
    'artisan' stub palsu untuk testing)."""
    candidates = []
    for dirpath, dirnames, filenames in os.walk(homedir):
        if "vendor" in dirpath.split(os.sep):
            dirnames[:] = []
            continue
        if "artisan" in filenames and "composer.json" in filenames and "bootstrap" in dirnames:
            candidates.append(dirpath)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.count(os.sep))
    return candidates[0]


def find_db_dumps(extracted_account_root):
    """Cari dump .sql per-database di folder mysql/."""
    mysql_dir = os.path.join(extracted_account_root, "mysql")
    dumps = []
    if os.path.isdir(mysql_dir):
        for fn in os.listdir(mysql_dir):
            if fn.lower().endswith(".sql"):
                dumps.append(os.path.join(mysql_dir, fn))
    if not dumps:
        combined = os.path.join(extracted_account_root, "mysql.sql")
        if os.path.isfile(combined):
            log("PERINGATAN: hanya ditemukan mysql.sql (dump GABUNGAN semua database di akun ini).")
            log("            Import ini bisa memasukkan database lain juga, bukan cuma punya project ini.")
            dumps.append(combined)
    dumps.sort(key=os.path.getsize, reverse=True)
    return dumps


def detect_split_public(laravel_root, homedir):
    """Deteksi pola cPanel: public_html terpisah, index.php-nya me-require
    '../<nama_folder_laravel_root>/...'."""
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
    """Kalau index.php masih merujuk ke path cPanel ('../repositories/...' atau
    'dirname(__FILE__)/../foo/...'), timpa seluruhnya dengan template standar
    Laravel. Backup ke index.php.orig dulu.

    Kenapa timpa total, bukan regex-replace? Karena regex sebelumnya '[^;]*?'
    bisa melintasi komentar blok '/* ... */' yang tidak punya ';' di dalamnya,
    sehingga baris 'require __DIR__.'/../vendor/autoload.php';' ikut terhapus
    (tertelan oleh match). Menimpa total = hasil deterministik, tidak bergantung
    pada bentuk asli file.
    """
    index_php = os.path.join(public_dir, "index.php")
    if not os.path.isfile(index_php):
        return
    try:
        with open(index_php, "r", encoding="utf-8", errors="ignore") as f:
            original = f.read()
    except OSError:
        return

    # Deteksi apakah index.php masih menunjuk ke luar folder project
    # (path cPanel) — pakai pola yang cukup lebar untuk menangkap variasi.
    needs_fix = bool(re.search(
        r"repositories/|\.\./\.\./[^'\"]*?/vendor/autoload\.php|base64_decode\s*\(",
        original,
    ))

    if not needs_fix:
        log("-> public/index.php tidak butuh perbaikan path (sudah standar).")
        return

    try:
        shutil.copy2(index_php, index_php + ".orig")
    except OSError:
        pass

    with open(index_php, "w", encoding="utf-8") as f:
        f.write(STANDARD_INDEX_PHP)

    log("-> public/index.php ditulis ulang ke template standar Laravel (tanpa backdoor/path cPanel).")
    log(f"   (file asli disimpan sebagai {os.path.basename(index_php)}.orig untuk audit)")


def main():
    if len(sys.argv) < 3:
        log("Usage: extract_cpmove.py /path/ke/cpmove.tar.gz /path/output/project")
        sys.exit(1)

    archive_path = os.path.abspath(sys.argv[1])
    output_dir = os.path.abspath(sys.argv[2])

    if not os.path.isfile(archive_path):
        log(f"File arsip tidak ditemukan: {archive_path}")
        sys.exit(1)

    if os.path.exists(output_dir) and os.listdir(output_dir):
        log(f"Folder output '{output_dir}' sudah ada isinya. Hapus/kosongkan dulu atau pilih path lain.")
        sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="cpmove_extract_")
    log(f"-> Extract arsip ke folder sementara: {tmp_dir}")
    try:
        with tarfile.open(archive_path, "r:*") as tar:
            members = tar.getmembers()
            skipped = 0
            for m in members:
                try:
                    tar.extract(m, tmp_dir, filter="data")
                except TypeError:
                    try:
                        tar.extract(m, tmp_dir)
                    except Exception:
                        skipped += 1
                except Exception:
                    skipped += 1
            if skipped:
                log(f"-> Melewati {skipped} entri bermasalah (mis. symlink absolut) — aman, tidak dibutuhkan.")
    except tarfile.TarError as e:
        log(f"Gagal extract arsip: {e}")
        sys.exit(1)

    homedir = find_dir_named(tmp_dir, "homedir")
    if not homedir:
        log("Tidak ditemukan folder 'homedir' di dalam arsip. Ini yakin file cpmove/backup cPanel?")
        sys.exit(1)
    log(f"-> homedir ditemukan: {homedir}")

    laravel_root = find_laravel_root(homedir)
    if not laravel_root:
        log("Tidak ditemukan project Laravel (artisan + composer.json + bootstrap/) di dalam homedir.")
        sys.exit(1)
    log(f"-> Root project Laravel ditemukan: {laravel_root}")

    parent = os.path.dirname(output_dir)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copytree(laravel_root, output_dir)
    log(f"-> Project Laravel disalin ke: {output_dir}")

    output_public = os.path.join(output_dir, "public")
    if not os.path.isdir(output_public):
        split_public = detect_split_public(laravel_root, homedir)
        if split_public:
            log(f"-> Struktur cPanel terdeteksi: public webroot terpisah di {split_public}")
            log(f"   Menggabungkan isinya ke {output_public} ...")
            shutil.copytree(split_public, output_public)
            fix_public_index_php(output_public)
        else:
            log("PERINGATAN: folder project tidak punya 'public/' dan pola cPanel split tidak terdeteksi.")
            log("             Cek manual di mana folder public webroot project ini berada.")
    else:
        log("-> Project sudah punya folder public/ sendiri, tidak perlu digabung.")
        fix_public_index_php(output_public)

    # Bersihkan bootstrap/cache bawaan arsip cPanel: file *.php di situ berisi
    # config & route cache yang ditandatangani dengan APP_KEY lama. Kalau
    # dibiarkan, Laravel akan baca cache itu dan closure yang di-serialize
    # gagal di-unserialize (Opis\Closure\SecurityException) setelah kita
    # generate APP_KEY baru.
    bootstrap_cache = os.path.join(output_dir, "bootstrap", "cache")
    if os.path.isdir(bootstrap_cache):
        removed = 0
        for fn in os.listdir(bootstrap_cache):
            if fn.endswith(".php"):
                try:
                    os.remove(os.path.join(bootstrap_cache, fn))
                    removed += 1
                except OSError:
                    pass
        if removed:
            log(f"-> bootstrap/cache dibersihkan: {removed} file cache lama dihapus (menghindari Opis\\Closure error).")

    # Bersihkan session lama (kalau ikut ter-copy dari storage/framework/sessions).
    # Session lama mungkin menyimpan serialized closure dengan APP_KEY lama.
    sessions_dir = os.path.join(output_dir, "storage", "framework", "sessions")
    if os.path.isdir(sessions_dir):
        removed = 0
        for fn in os.listdir(sessions_dir):
            try:
                os.remove(os.path.join(sessions_dir, fn))
                removed += 1
            except OSError:
                pass
        if removed:
            log(f"-> Sesi lama dibersihkan: {removed} file dihapus.")

    # Cari & salin dump database
    extracted_account_root = os.path.dirname(homedir)
    dumps = find_db_dumps(extracted_account_root)
    if dumps:
        chosen = dumps[0]
        dest = os.path.join(output_dir, os.path.basename(chosen))
        shutil.copy2(chosen, dest)
        log(f"-> Dump database disalin: {chosen} -> {dest}")
        if len(dumps) > 1:
            log(f"   (ada {len(dumps)} file dump di folder mysql/, dipakai yang paling besar, sisanya diabaikan)")
    else:
        log("Tidak ditemukan dump database (.sql) di dalam arsip.")

    log("-> Selesai menyusun ulang project dari cpmove.")
    log(f"-> Folder sementara hasil extract mentah masih ada di {tmp_dir} (boleh dihapus manual).")
    print(output_dir)


if __name__ == "__main__":
    main()