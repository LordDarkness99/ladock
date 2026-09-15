#!/usr/bin/env python3
"""
Scan sebuah direktori (rekursif) untuk mencari project Laravel, ditandai
dengan adanya file 'artisan' di root folder project.

Usage:
    python3 find_laravel_projects.py /path/yang/mau/discan
    python3 find_laravel_projects.py            # default: folder saat ini

Print satu path project per baris ke stdout. Dipakai deploy.sh saat
project path tidak diisi, supaya user bisa pilih dari daftar interaktif.
"""
import os
import sys

# Folder yang dilewati saat scan (biar cepat & tidak salah nemu artisan
# palsu di dalam vendor/ punya project lain)
SKIP_DIRS = {"vendor", "node_modules", ".git", "storage", ".docker", "bootstrap", "public"}
MAX_DEPTH = 6


def find_laravel_projects(root: str, max_depth: int = MAX_DEPTH):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []

    found = []
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
            continue

        # jangan turun ke folder yang jelas bukan tempat project Laravel lain
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        if "artisan" in filenames:
            found.append(dirpath)
            dirnames[:] = []  # sudah ketemu project di sini, tidak perlu masuk lebih dalam

    return found


if __name__ == "__main__":
    scan_root = sys.argv[1] if len(sys.argv) > 1 else "."
    for path in find_laravel_projects(scan_root):
        print(path)