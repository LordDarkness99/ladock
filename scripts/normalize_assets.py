#!/usr/bin/env python3
"""
Normalisasi aset dan path URL statis pada project web/Laravel.
Mendeteksi domain eksternal atau hardcoded domain produksi (mis. https://domain-lama.com/images/...)
yang file fisiknya sebenarnya ada di folder public/ lokal, lalu mengubahnya menjadi path lokal
sehingga tidak gagal dimuat saat dijalankan di lingkungan lokal/container.
"""

import os
import sys
import re

def log(msg):
    print(f"[ASSET-NORMALIZER] {msg}", flush=True)

def find_public_files(public_dir):
    """Mendaftar semua file relatif yang ada di dalam folder public."""
    public_files = set()
    if not os.path.isdir(public_dir):
        return public_files
    for root, dirs, files in os.walk(public_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), public_dir)
            public_files.add(rel.replace("\\", "/"))
    return public_files

def normalize_blade_file(file_path, public_files):
    """Normalisasi URL hardcoded di dalam file blade/template."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return 0

    original = content
    changes = 0

    # Pola 1: {{ asset('https?://.../path/to/file') }} atau {{ asset("https?://.../path/to/file") }}
    def replace_asset_func(match):
        nonlocal changes
        quote = match.group(1)
        rel_path = match.group(2)
        # Hilangkan query string jika ada untuk pengecekan file
        clean_rel = rel_path.split("?")[0].split("#")[0]
        if clean_rel in public_files:
            changes += 1
            return f"asset({quote}{rel_path}{quote})"
        return match.group(0)

    content = re.sub(r"asset\(\s*(['\"])https?://[^/'\"]+/([^'\"]+)\1\s*\)", replace_asset_func, content)

    # Pola 2: url("https?://.../path/to/file") di dalam <style> atau style="..."
    def replace_url_css(match):
        nonlocal changes
        quote = match.group(1)
        rel_path = match.group(2)
        clean_rel = rel_path.split("?")[0].split("#")[0]
        if clean_rel in public_files:
            changes += 1
            if "{{" in match.string:
                return f"url({quote}{{{{ asset('{rel_path}') }}}}{quote})"
            return f"url({quote}/{rel_path}{quote})"
        return match.group(0)

    content = re.sub(r"url\(\s*(['\"])https?://[^/'\"]+/([^'\"]+)\1\s*\)", replace_url_css, content)

    # Pola 3: src="https?://.../images/..." atau href="https?://.../css/..."
    def replace_src_href(match):
        nonlocal changes
        attr = match.group(1) # src / href
        quote = match.group(2)
        rel_path = match.group(3)
        clean_rel = rel_path.split("?")[0].split("#")[0]
        if clean_rel in public_files:
            changes += 1
            return f'{attr}={quote}{{{{ asset("{rel_path}") }}}}{quote}'
        return match.group(0)

    content = re.sub(r"\b(src|href)=\s*(['\"])https?://[^/'\"]+/((?:images|img|css|js|assets|vendor|fonts|uploads)/[^'\"]+)\2", replace_src_href, content)

    if content != original:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return changes
        except OSError:
            return 0
    return 0

def main():
    if len(sys.argv) < 2:
        print("Usage: normalize_assets.py <src_directory>")
        sys.exit(1)

    src_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(src_dir):
        log(f"Direktori tidak ditemukan: {src_dir}")
        sys.exit(1)

    public_dir = os.path.join(src_dir, "public")
    if not os.path.isdir(public_dir):
        # Fallback jika monolith native PHP meletakkan aset di root
        public_dir = src_dir

    public_files = find_public_files(public_dir)
    log(f"Ditemukan {len(public_files)} file aset di folder public ({public_dir}).")

    views_dirs = [
        os.path.join(src_dir, "resources", "views"),
        os.path.join(src_dir, "views"),
        os.path.join(src_dir, "templates"),
    ]

    total_normalized_files = 0
    total_changes = 0

    for vd in views_dirs:
        if not os.path.isdir(vd):
            continue
        for root, _, files in os.walk(vd):
            for fn in files:
                if fn.endswith((".php", ".blade.php", ".html", ".htm", ".vue", ".twig")):
                    fp = os.path.join(root, fn)
                    c = normalize_blade_file(fp, public_files)
                    if c > 0:
                        rel = os.path.relpath(fp, src_dir)
                        log(f"✓ Normalisasi {c} path aset di: {rel}")
                        total_normalized_files += 1
                        total_changes += c

    if total_changes > 0:
        log(f"Selesai! Total {total_changes} URL aset dinormalisasi di {total_normalized_files} file.")
    else:
        log("Semua path aset template sudah menggunakan referensi lokal / tidak ditemukan URL eksternal yang salah.")

if __name__ == "__main__":
    main()
