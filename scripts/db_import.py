#!/usr/bin/env python3
"""
Cari file dump .sql di dalam project Laravel dan import ke database MySQL
yang jalan di container Docker milik project itu. Ini melengkapi
`php artisan migrate` (yang hanya membuat struktur tabel) dengan data
lengkap dari dump, misal "campus_complaint_system_clean_import.sql".

Kalau --dump tidak diberikan, script akan cari sendiri file .sql di dalam
folder project (skip vendor/node_modules/.git/dll), dan pakai yang paling
besar ukurannya kalau ketemu lebih dari satu (asumsi paling lengkap datanya).

Usage:
    python3 db_import.py --project-path /path/project --project-name myapp \
        --compose-file /path/project/.docker-compose.yml \
        --db-name myapp_db --db-root-pass xxxx --dc "docker compose"

    # atau tunjuk file dump-nya langsung:
    python3 db_import.py ... --dump /path/project/database/backup.sql
"""
import argparse
import os
import subprocess
import sys

SKIP_DIRS = {"vendor", "node_modules", ".git", ".docker", "storage", "bootstrap"}


def find_dump_files(project_path: str):
    candidates = []
    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith(".sql"):
                candidates.append(os.path.join(dirpath, fn))
    
    # Priority sorting: files with 'structure', 'schema', 'create', 'init' come first, then others sorted by size
    def sort_key(p):
        fn = os.path.basename(p).lower()
        if any(kw in fn for kw in ["structure", "schema", "init", "create"]):
            return (0, fn)
        return (1, -os.path.getsize(p))

    candidates.sort(key=sort_key)
    return candidates


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-path", required=True)
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--compose-file", default="")
    ap.add_argument("--compose-project-name", default=None)
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--db-root-pass", required=True)
    ap.add_argument("--db-container", default=None, help="Nama container DB")
    ap.add_argument("--central-db", action="store_true", help="Gunakan docker exec langsung ke DB central")
    ap.add_argument("--dump", default=None, help="Path eksplisit ke file .sql (opsional, kalau tidak diisi akan dicari otomatis)")
    ap.add_argument("--dc", default="docker compose", help="Perintah compose yang dipakai, mis. 'docker compose' atau 'docker-compose'")
    args = ap.parse_args()

    dump_files = []
    if args.dump:
        dump_path = os.path.abspath(args.dump)
        if not os.path.isfile(dump_path):
            print(f"File dump tidak ditemukan: {dump_path}", file=sys.stderr)
            sys.exit(1)
        dump_files.append(dump_path)
    else:
        found = find_dump_files(args.project_path)
        if not found:
            print("Tidak ada file .sql ditemukan di dalam project, lewati import data.")
            sys.exit(0)
        dump_files = found
        if len(found) > 1:
            print("Ditemukan beberapa file .sql di dalam project, mengimpor secara berurutan:")
            for f in found:
                size_mb = os.path.getsize(f) / (1024 * 1024)
                print(f"  - {f} ({size_mb:.1f} MB)")

    db_container = args.db_container if getattr(args, 'db_container', None) else f"db_{args.project_name}"
    
    if getattr(args, 'central_db', False):
        dc_cmd = ["docker", "exec", "-i", db_container, "mysql", "-uroot", f"-p{args.db_root_pass}", args.db_name]
    else:
        project_name_flag = args.compose_project_name if args.compose_project_name else args.project_name
        dc_cmd = args.dc.split() + [
            "-f", args.compose_file,
            "-p", project_name_flag,
            "exec", "-T", db_container,
            "mysql", "-uroot", f"-p{args.db_root_pass}", args.db_name,
        ]

    import re
    for dump_path in dump_files:
        print(f"-> Mengimpor '{os.path.basename(dump_path)}' ke database '{args.db_name}' ...")
        try:
            with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            content = re.sub(r'(?i)CREATE\s+DATABASE\s+[^;]+;', '', content)
            content = re.sub(r'(?i)DROP\s+DATABASE\s+[^;]+;', '', content)
            content = re.sub(r'(?i)USE\s+[^;]+;', '', content)

            sql_input = f"USE `{args.db_name}`;\nSET FOREIGN_KEY_CHECKS=0;\n{content}\nSET FOREIGN_KEY_CHECKS=1;\n".encode("utf-8")
            result = subprocess.run(dc_cmd, input=sql_input)
        except FileNotFoundError:
            print(f"Perintah '{args.dc}' tidak ditemukan.", file=sys.stderr)
            sys.exit(1)

        if result.returncode != 0:
            print(f"Import database '{os.path.basename(dump_path)}' gagal.", file=sys.stderr)

    print("Import database selesai.")


if __name__ == "__main__":
    main()