#!/usr/bin/env python3
"""
Scanner rekursif untuk menemukan sub-project aplikasi yang didukung LaDock.

Fitur:
  - Scan rekursif hingga kedalaman MAX_DEPTH (default 5)
  - Skip folder blacklist (vendor, node_modules, .git, storage, dll.)
  - Nama service diambil dari composer.json "name", fallback ke nama folder
  - Deduplikasi nama: jika ada clash, tambahkan prefix nama folder induk
  - Output per baris: <service_name>\t<absolute_path>

Usage:
    python3 find_microservices.py /path/ke/root-project [max_depth]

Exit code:
    0  = ditemukan >= 1 service (output ke stdout)
    1  = tidak ada service ditemukan
"""

import json
import os
import re
import sys

# Folder yang SELALU dilewati saat scan
SKIP_DIRS = {
    "vendor", "node_modules", ".git", ".hg", ".svn",
    "storage", "bootstrap", "cache", "public",
    ".docker", "docker", ".idea", ".vscode", "__pycache__",
}

MAX_DEPTH_DEFAULT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_name(raw: str) -> str:
    """Ubah string sembarangan jadi nama service yang aman untuk Docker."""
    # Ambil bagian terakhir kalau ada slash (mis. "vendor/package-name" → "package-name")
    if "/" in raw:
        raw = raw.split("/")[-1]
    name = raw.lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return name or "service"


def _service_name_from_composer(composer_path: str) -> str | None:
    """Baca 'name' dari composer.json, sanitasi dan return. None kalau tidak ada."""
    try:
        with open(composer_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = (data.get("name") or "").strip()
        if raw:
            return _sanitize_name(raw)
    except Exception:
        pass
    return None


def _is_wordpress_app(path: str) -> bool:
    return (
        os.path.isfile(os.path.join(path, "wp-config.php"))
        or os.path.isfile(os.path.join(path, "wp-load.php"))
        or os.path.isfile(os.path.join(path, "wp-settings.php"))
        or (
            os.path.isdir(os.path.join(path, "wp-admin"))
            and os.path.isdir(os.path.join(path, "wp-includes"))
        )
    )


def _is_supported_app(path: str) -> bool:
    """Return whether a directory is an application rather than a dependency."""
    if _is_wordpress_app(path):
        return True

    php_entrypoints = (
        "artisan",
        "spark",
        "index.php",
        "public/index.php",
        "web/index.php",
        "bin/console",
    )
    if os.path.isfile(os.path.join(path, "composer.json")):
        return (
            os.path.isfile(os.path.join(path, "Dockerfile"))
            or any(
                os.path.isfile(os.path.join(path, item))
                for item in php_entrypoints
            )
        )

    manifests = {
        "composer.json",
        "package.json",
        "requirements.txt",
        "Pipfile",
        "pyproject.toml",
        "go.mod",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Dockerfile",
    }
    return any(os.path.isfile(os.path.join(path, manifest)) for manifest in manifests)


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def scan(root: str, max_depth: int = MAX_DEPTH_DEFAULT) -> list[dict]:
    """
    Scan rekursif folder `root` dan kembalikan list dict:
      [{"name": str, "path": str}, ...]

    Aturan:
      1. Folder yang mengandung manifest runtime yang dikenal = satu service.
         Tidak lagi di-scan ke dalam (service tidak boleh bersarang).
      2. Folder di SKIP_DIRS atau diawali titik diabaikan.
      3. Scan sampai max_depth level ke bawah.
    """
    found: list[dict] = []
    root = os.path.abspath(root)

    def _walk(current_path: str, depth: int):
        if depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError:
            return

        for entry in entries:
            full = os.path.join(current_path, entry)
            if not os.path.isdir(full):
                continue
            if _is_wordpress_app(full):
                found.append({"name": _sanitize_name(entry), "path": full})
                continue
            if entry in SKIP_DIRS or entry.startswith("."):
                continue

            if _is_supported_app(full):
                # Prefer package name from composer.json; otherwise use the directory.
                name = _service_name_from_composer(
                    os.path.join(full, "composer.json")
                ) or _sanitize_name(entry)
                found.append({"name": name, "path": full})
                # Tidak scan ke dalam folder service ini lagi
            else:
                _walk(full, depth + 1)

    # Treat a root-level app as one service rather than splitting nested dependencies.
    if _is_supported_app(root):
        name = _service_name_from_composer(
            os.path.join(root, "composer.json")
        ) or _sanitize_name(os.path.basename(root))
        found.append({"name": name, "path": root})
    else:
        _walk(root, 1)

    return found


def _deduplicate_names(services: list[dict]) -> list[dict]:
    """
    Jika ada dua service dengan nama sama, tambahkan prefix nama folder induk
    supaya nama container Docker tetap unik.
    """
    # Hitung frekuensi nama
    name_count: dict[str, int] = {}
    for svc in services:
        name_count[svc["name"]] = name_count.get(svc["name"], 0) + 1

    result = []
    for svc in services:
        name = svc["name"]
        if name_count[name] > 1:
            # Ambil nama folder induk sebagai disambiguator
            parent = _sanitize_name(os.path.basename(os.path.dirname(svc["path"])))
            new_name = f"{parent}_{name}" if parent else name
            result.append({"name": new_name, "path": svc["path"]})
        else:
            result.append(svc)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: find_microservices.py /path/ke/root [max_depth]", file=sys.stderr)
        sys.exit(1)

    root = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) >= 3 else MAX_DEPTH_DEFAULT

    if not os.path.isdir(root):
        print(f"Folder tidak ditemukan: {root}", file=sys.stderr)
        sys.exit(1)

    services = scan(root, max_depth)
    services = _deduplicate_names(services)

    if not services:
        print(f"Tidak ditemukan project Laravel di bawah: {root}", file=sys.stderr)
        sys.exit(1)

    # Output: satu baris per service, tab-separated: name<TAB>path
    for svc in services:
        print(f"{svc['name']}\t{svc['path']}")


if __name__ == "__main__":
    main()
