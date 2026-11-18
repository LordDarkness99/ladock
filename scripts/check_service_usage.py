#!/usr/bin/env python3
"""
Pemeriksa status penggunaan service aplikasi (terutama cPanel / Microservices).

Fungsi:
1. Mendeteksi apakah service 'MASIH DIGUNAKAN' (Active / In-use) atau 'TIDAK DIGUNAKAN' (Unused / Abandoned / Junk).
2. Mengevaluasi:
   - Konfigurasi Virtual Host cPanel (userdata: main_domain, sub_domains, addon_domains, docroot)
   - Catatan traffic dan bandwidth HTTP
   - Ketersediaan dan validitas dump database (.sql)
   - Pola nama sampah/tesis/uji coba (tesis, test, sample, backup, dll.)
   - Keberadaan file arsip backup internal (misal tesis.zip, individu.zip, *.tar.gz)
   - Entrypoint aplikasi (index.php, index.html, dsb.)
3. Menghasilkan laporan terstruktur untuk CLI dan daftar service aktif untuk deployment.

Usage:
    python3 check_service_usage.py /path/to/project [options]
    python3 check_service_usage.py --services "root_web:/path/a,surveylance:/path/b" [options]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


JUNK_NAME_REGEX = re.compile(
    r"^(tesis|thesis|skripsi|tugas_akhir|uji|ujicoba|test|tests|testing|dummy|sample|contoh|temp|tmp|old|backup|bak|copy|cadangan)(_.*)?$",
    re.IGNORECASE,
)

JUNK_SUFFIX_REGEX = re.compile(
    r".*(_old|_bak|_backup|_copy|_test|_testing|_tesis)$",
    re.IGNORECASE,
)

ARCHIVE_EXTENSIONS = (".zip", ".tar.gz", ".tgz", ".rar", ".tar.bz2", ".tar")


def parse_cpanel_userdata(cpanel_meta_dir: str | None) -> dict:
    """
    Membaca metadata cPanel dari folder userdata / .cpanel_metadata.
    Mengembalikan dict berisi:
      - main_domain: str
      - sub_domains: list[str]
      - addon_domains: dict
      - docroots: dict[domain, docroot]
      - has_cpanel_meta: bool
    """
    result = {
        "main_domain": None,
        "sub_domains": [],
        "addon_domains": {},
        "docroots": {},
        "has_cpanel_meta": False,
    }
    if not cpanel_meta_dir or not os.path.isdir(cpanel_meta_dir):
        return result

    # Cari folder userdata
    userdata_dir = cpanel_meta_dir
    if not os.path.basename(userdata_dir) == "userdata":
        candidate = os.path.join(cpanel_meta_dir, "userdata")
        if os.path.isdir(candidate):
            userdata_dir = candidate
        else:
            candidate_nested = os.path.join(cpanel_meta_dir, ".cpanel_metadata", "userdata")
            if os.path.isdir(candidate_nested):
                userdata_dir = candidate_nested

    if not os.path.isdir(userdata_dir):
        return result

    result["has_cpanel_meta"] = True

    # 1. Baca cache.json jika ada
    cache_json_file = os.path.join(userdata_dir, "cache.json")
    if os.path.isfile(cache_json_file):
        try:
            with open(cache_json_file, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            for domain, details in data.items():
                if isinstance(details, list) and len(details) >= 5:
                    dtype = details[2]  # "main" | "sub" | "addon"
                    docroot = details[4]
                    result["docroots"][domain.lower()] = docroot
                    if dtype == "main":
                        result["main_domain"] = domain.lower()
                    elif dtype == "sub":
                        if domain.lower() not in result["sub_domains"]:
                            result["sub_domains"].append(domain.lower())
                    elif dtype == "addon":
                        result["addon_domains"][domain.lower()] = docroot
        except Exception:
            pass

    # 2. Baca file main jika ada
    main_file = os.path.join(userdata_dir, "main")
    if os.path.isfile(main_file):
        try:
            with open(main_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m_main = re.search(r"main_domain:\s*([^\s]+)", content)
            if m_main and not result["main_domain"]:
                result["main_domain"] = m_main.group(1).lower().strip()

            in_subdomains = False
            for line in content.splitlines():
                if re.match(r"^sub_domains:", line):
                    in_subdomains = True
                    continue
                if in_subdomains:
                    if line.startswith("  - ") or line.startswith("    - "):
                        sub = line.strip("- \t").lower()
                        if sub and sub not in result["sub_domains"]:
                            result["sub_domains"].append(sub)
                    elif line and not line.startswith(" ") and not line.startswith("\t"):
                        in_subdomains = False
        except Exception:
            pass

    # 3. Baca file domain individual
    for fn in os.listdir(userdata_dir):
        if fn in ("main", "cache.json") or fn.endswith(".cache") or fn.endswith("_SSL"):
            continue
        fp = os.path.join(userdata_dir, fn)
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    c = f.read()
                m_doc = re.search(r"documentroot:\s*([^\s]+)", c)
                if m_doc:
                    result["docroots"][fn.lower()] = m_doc.group(1)
            except Exception:
                pass

    return result


def parse_cpanel_bandwidth(cpanel_meta_dir: str | None) -> dict[str, int]:
    """
    Membaca catatan bandwidth / traffic domain dari bandwidth_db.json atau folder bandwidth.
    Mengembalikan dict[domain, traffic_score_or_bytes].
    """
    traffic = {}
    if not cpanel_meta_dir or not os.path.isdir(cpanel_meta_dir):
        return traffic

    search_dirs = [
        cpanel_meta_dir,
        os.path.join(cpanel_meta_dir, ".cpanel_metadata"),
        os.path.join(cpanel_meta_dir, "bandwidth"),
        os.path.join(cpanel_meta_dir, ".cpanel_metadata", "bandwidth"),
    ]

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        bw_json = os.path.join(d, "bandwidth_db.json")
        if os.path.isfile(bw_json):
            try:
                with open(bw_json, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                domains = data.get("domains", {})
                for dom, count in domains.items():
                    if dom != "UNKNOWN":
                        traffic[dom.lower()] = traffic.get(dom.lower(), 0) + int(count)
            except Exception:
                pass

        for fn in os.listdir(d):
            if fn.endswith("-bytes_log") or fn.endswith("-access_log"):
                dom = fn.split("-bytes_log")[0].split("-access_log")[0].lower()
                fp = os.path.join(d, fn)
                try:
                    size = os.path.getsize(fp)
                    if size > 0:
                        traffic[dom] = traffic.get(dom, 0) + size
                except OSError:
                    pass

    return traffic


def find_db_dumps_in_dirs(search_dirs: list[str]) -> dict[str, dict]:
    """
    Mencari file dump .sql pada folder-folder yang diberikan.
    Mengembalikan dict[db_or_file_name_lowercase, {"path": str, "size": int}].
    """
    dumps = {}
    for d in search_dirs:
        if not d or not os.path.isdir(d):
            continue
        for root_dir, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(".sql"):
                    fp = os.path.join(root_dir, fn)
                    try:
                        sz = os.path.getsize(fp)
                    except OSError:
                        sz = 0
                    base = fn[:-4].lower()
                    dumps[base] = {"path": fp, "size": sz}
    return dumps


def detect_configured_database(service_path: str) -> str | None:
    """
    Mendeteksi nama database yang dikonfigurasi di dalam source code service.
    """
    # 1. CodeIgniter
    ci_db = os.path.join(service_path, "application", "config", "database.php")
    if os.path.isfile(ci_db):
        try:
            with open(ci_db, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r"['\"]database['\"]\s*=>\s*['\"]([^'\"]+)['\"]", content)
            if m and m.group(1) and not m.group(1).startswith("DB_"):
                return m.group(1)
            m = re.search(r"\$db\[[^\]]+\]\['database'\]\s*=\s*['\"]([^'\"]+)['\"]", content)
            if m and m.group(1):
                return m.group(1)
        except Exception:
            pass

    # 2. WordPress
    for wp_fn in ("wp-config.php", "wp-config.php.old", "wp-config.php.save"):
        wp_cfg = os.path.join(service_path, wp_fn)
        if os.path.isfile(wp_cfg):
            try:
                with open(wp_cfg, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r"define\s*\(\s*['\"]DB_NAME['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", content)
                if m and m.group(1) and not m.group(1).startswith("DB_"):
                    return m.group(1)
            except Exception:
                pass

    # 3. Symfony 1
    sym_db = os.path.join(service_path, "config", "databases.yml")
    if os.path.isfile(sym_db):
        try:
            with open(sym_db, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r"dbname=([a-zA-Z0-9_]+)", content)
            if m:
                return m.group(1)
        except Exception:
            pass

    # 4. .env
    dotenv = os.path.join(service_path, ".env")
    if os.path.isfile(dotenv):
        try:
            with open(dotenv, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("DB_DATABASE="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
        except Exception:
            pass

    # 5. Legacy PHP config files
    for root_dir, _, files in os.walk(service_path):
        # Maksimal kedalaman 2
        rel = os.path.relpath(root_dir, service_path)
        if rel.count(os.sep) > 2:
            continue
        for fn in files:
            if fn.endswith((".php", ".inc")) and any(k in fn.lower() for k in ("database", "config", "db", "koneksi", "conn")):
                fp = os.path.join(root_dir, fn)
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        c = f.read(5000)
                    m = re.search(r"\$(db_name|database|dbname|db)\s*=\s*['\"]([^'\"]+)['\"]", c)
                    if m and m.group(2):
                        return m.group(2)
                except Exception:
                    pass
    return None


def find_internal_archives(service_path: str) -> list[str]:
    """Cari file zip/tar/rar di root atau level 1 folder service."""
    archives = []
    try:
        entries = os.listdir(service_path)
    except OSError:
        return archives

    for e in entries:
        low = e.lower()
        if any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS):
            archives.append(e)
    return archives


def evaluate_service_usage(
    service_name: str,
    service_path: str,
    cpanel_meta: dict,
    bandwidth_data: dict[str, int],
    available_dumps: dict[str, dict],
    all_service_names: list[str],
) -> dict:
    """
    Evaluasi apakah sebuah service masih digunakan atau tidak.
    """
    reasons: list[str] = []
    is_used = False
    details = {
        "domain": None,
        "is_cpanel_domain": False,
        "has_traffic": False,
        "traffic_score": 0,
        "configured_db": None,
        "db_dump_exists": False,
        "is_junk_thesis": False,
        "has_archive_artifact": False,
        "internal_archives": [],
    }

    # 1. Cek entrypoint
    has_entrypoint = (
        os.path.isfile(os.path.join(service_path, "index.php"))
        or os.path.isfile(os.path.join(service_path, "index.html"))
        or os.path.isfile(os.path.join(service_path, "public", "index.php"))
        or os.path.isfile(os.path.join(service_path, "artisan"))
        or os.path.isfile(os.path.join(service_path, "package.json"))
        or os.path.isfile(os.path.join(service_path, "Dockerfile"))
    )

    # 2. Cek database yang dikonfigurasi
    cfg_db = detect_configured_database(service_path)
    details["configured_db"] = cfg_db
    if cfg_db:
        # Cek apakah dump SQL tersedia
        db_low = cfg_db.lower()
        if db_low in available_dumps or any(db_low in k for k in available_dumps):
            details["db_dump_exists"] = True
        else:
            details["db_dump_exists"] = False

    # 3. Cek pola junk / tesis / test
    name_low = service_name.lower()
    if JUNK_NAME_REGEX.match(name_low) or JUNK_SUFFIX_REGEX.match(name_low):
        details["is_junk_thesis"] = True

    # 4. Cek file arsip internal (tesis.zip, individu.zip, dll)
    archives = find_internal_archives(service_path)
    details["internal_archives"] = archives
    if archives:
        details["has_archive_artifact"] = True

    # 5. Cek cPanel metadata (domain / subdomain)
    has_meta = cpanel_meta.get("has_cpanel_meta", False)
    main_domain = cpanel_meta.get("main_domain")
    sub_domains = cpanel_meta.get("sub_domains", [])
    addon_domains = cpanel_meta.get("addon_domains", {})

    matched_domain = None
    is_main_domain = False
    is_subdomain = False

    if name_low in ("root_web", "main", "webroot") or os.path.basename(service_path) in ("public_html", "www"):
        is_main_domain = True
        matched_domain = main_domain
    else:
        # Cek kecocokan dengan sub_domains / addon_domains
        for sub in sub_domains:
            # Misal: sub = "surveylance.imunisasi.dinkes.jatimprov.go.id"
            sub_prefix = sub.split(".")[0]
            if name_low == sub_prefix or sub_prefix in name_low or name_low in sub:
                is_subdomain = True
                matched_domain = sub
                break

        if not matched_domain:
            for addon, docroot in addon_domains.items():
                addon_prefix = addon.split(".")[0]
                if name_low == addon_prefix or name_low in addon:
                    is_subdomain = True
                    matched_domain = addon
                    break

        if not matched_domain and has_meta:
            # Cek kecocokan docroot
            for dom, docroot in cpanel_meta.get("docroots", {}).items():
                if docroot and os.path.basename(docroot).lower() == name_low:
                    matched_domain = dom
                    if dom == main_domain:
                        is_main_domain = True
                    else:
                        is_subdomain = True
                    break

    details["domain"] = matched_domain
    details["is_cpanel_domain"] = bool(matched_domain)

    # 6. Cek bandwidth / traffic
    if matched_domain:
        traffic_val = bandwidth_data.get(matched_domain.lower(), 0)
        details["traffic_score"] = traffic_val
        details["has_traffic"] = traffic_val > 0
    else:
        # Cek apakah ada domain traffic yang mengandung service_name
        for dom, traffic_val in bandwidth_data.items():
            if name_low in dom.lower():
                details["traffic_score"] = traffic_val
                details["has_traffic"] = traffic_val > 0
                matched_domain = dom
                details["domain"] = dom
                break

    # =========================================================================
    # LOGIKA PENGAMBILAN KEPUTUSAN (USED vs UNUSED)
    # =========================================================================

    # Kasus A: Service adalah root_web / Main Domain cPanel
    if is_main_domain:
        is_used = True
        reasons.append(f"Web root utama cPanel (Domain: {matched_domain or 'default'})")
        if details["has_traffic"]:
            reasons.append("Tercatat traffic HTTP aktif pada log bandwidth")
        if details["db_dump_exists"]:
            reasons.append(f"Database aktif terdeteksi ({cfg_db})")

    # Kasus B: Service adalah Subdomain / Addon Domain aktif yang terdaftar di cPanel
    elif is_subdomain:
        is_used = True
        reasons.append(f"Subdomain aktif di cPanel VirtualHost ({matched_domain})")
        if details["has_traffic"]:
            reasons.append("Tercatat traffic HTTP aktif pada log bandwidth")
        if details["db_dump_exists"]:
            reasons.append(f"Database terhubung dan dump tersedia ({cfg_db})")

    # Kasus C: Service BUKAN domain utama dan BUKAN subdomain cPanel terdaftar (pada struktur cPanel)
    elif has_meta:
        has_negative_signals = (
            details["is_junk_thesis"]
            or details["has_archive_artifact"]
            or (cfg_db and not details["db_dump_exists"])
            or (not details["has_traffic"] and not details["db_dump_exists"])
        )
        if has_negative_signals:
            is_used = False
            reasons.append("Tidak terdaftar sebagai domain/subdomain pada konfigurasi cPanel")

            if details["is_junk_thesis"]:
                reasons.append(f"Nama '{service_name}' teridentifikasi sebagai modul tesis akademik / uji coba")

            if details["has_archive_artifact"]:
                arch_str = ", ".join(details["internal_archives"])
                reasons.append(f"Berisi berkas arsip backup kadaluarsa di dalam foldernya ({arch_str})")

            if cfg_db and not details["db_dump_exists"]:
                reasons.append(f"Database '{cfg_db}' tidak ditemukan di berkas dump MySQL cPanel")

            if not details["has_traffic"]:
                reasons.append("Tidak memiliki aktivitas traffic HTTP (0 byte)")
        else:
            is_used = True
            reasons.append("Sub-aplikasi web aktif (memiliki entrypoint dan database valid)")

    # Kasus D: Bukan cPanel (proyek microservices reguler)
    else:
        if details["is_junk_thesis"]:
            is_used = False
            reasons.append(f"Nama '{service_name}' terindikasi sebagai folder uji coba / tesis / cadangan")
        elif details["has_archive_artifact"] and len(details["internal_archives"]) > 0:
            is_used = False
            reasons.append(f"Berisi artefak arsip ({', '.join(details['internal_archives'])})")
        elif not has_entrypoint:
            is_used = False
            reasons.append("Tidak ditemukan entrypoint aplikasi yang valid (index.php/package.json/Dockerfile)")
        else:
            is_used = True
            reasons.append("Service aplikasi valid dengan manifest runtime dan entrypoint aktif")

    status_str = "MASIH DIGUNAKAN" if is_used else "TIDAK DIGUNAKAN"

    return {
        "name": service_name,
        "path": service_path,
        "is_used": is_used,
        "status": status_str,
        "reasons": reasons,
        "details": details,
    }


def inspect_all_services(
    services: list[dict],
    project_dir: str | None = None,
    cpanel_meta_dir: str | None = None,
    db_dumps_dir: str | None = None,
    force_include: list[str] | None = None,
    force_exclude: list[str] | None = None,
    all_as_used: bool = False,
) -> list[dict]:
    """
    Memeriksa seluruh daftar service yang diberikan.
    """
    force_include = [s.strip().lower() for s in (force_include or []) if s.strip()]
    force_exclude = [s.strip().lower() for s in (force_exclude or []) if s.strip()]

    # Cari cPanel metadata jika belum ditentukan
    meta_dir_to_use = cpanel_meta_dir
    if not meta_dir_to_use and project_dir:
        for candidate in (
            os.path.join(project_dir, ".cpanel_metadata"),
            os.path.join(project_dir, "userdata"),
            os.path.join(project_dir, "..", ".cpanel_metadata"),
            os.path.join(project_dir, "..", "userdata"),
        ):
            if os.path.isdir(candidate):
                meta_dir_to_use = candidate
                break

    cpanel_meta = parse_cpanel_userdata(meta_dir_to_use)
    bandwidth_data = parse_cpanel_bandwidth(meta_dir_to_use)

    # Cari dump database
    db_dirs = []
    if db_dumps_dir:
        db_dirs.append(db_dumps_dir)
    if project_dir:
        db_dirs.extend([
            os.path.join(project_dir, "mysql"),
            os.path.join(project_dir, "..", "mysql", "db"),
            os.path.join(project_dir, "db"),
        ])
    dumps = find_db_dumps_in_dirs(db_dirs)

    all_names = [s["name"] for s in services]
    results = []

    for svc in services:
        name = svc["name"]
        path = svc["path"]
        name_low = name.lower()

        eval_result = evaluate_service_usage(
            service_name=name,
            service_path=path,
            cpanel_meta=cpanel_meta,
            bandwidth_data=bandwidth_data,
            available_dumps=dumps,
            all_service_names=all_names,
        )

        # Overrides
        if all_as_used:
            eval_result["is_used"] = True
            eval_result["status"] = "MASIH DIGUNAKAN"
            eval_result["reasons"].append("Dipaksa aktif oleh opsi --all-services")
        elif name_low in force_include:
            eval_result["is_used"] = True
            eval_result["status"] = "MASIH DIGUNAKAN"
            eval_result["reasons"].append("Dipaksa aktif oleh opsi --include-service")
        elif name_low in force_exclude:
            eval_result["is_used"] = False
            eval_result["status"] = "TIDAK DIGUNAKAN"
            eval_result["reasons"].append("Dinonaktifkan oleh opsi --exclude-service")

        results.append(eval_result)

    return results


def format_cli_report(results: list[dict]) -> str:
    """Format laporan dalam bentuk teks CLI yang rapi dan mudah dibaca."""
    lines = []
    lines.append("=" * 64)
    lines.append("  PEMERIKSAAN STATUS PENGGUNAAN SERVICE (cPanel / Microservice)")
    lines.append("=" * 64)

    used = [r for r in results if r["is_used"]]
    unused = [r for r in results if not r["is_used"]]

    lines.append("")
    lines.append(f" [✓] SERVICE MASIH DIGUNAKAN ({len(used)} service - AKAN DIDEPLOY):")
    if used:
        for r in used:
            reason_str = "; ".join(r["reasons"])
            lines.append(f"     • {r['name']:<14} : {reason_str}")
    else:
        lines.append("     (Tidak ada service yang terdeteksi aktif)")

    lines.append("")
    lines.append(f" [✗] SERVICE TIDAK DIGUNAKAN ({len(unused)} service - DILEWATI):")
    if unused:
        for r in unused:
            reason_str = "; ".join(r["reasons"])
            lines.append(f"     • {r['name']:<14} : {reason_str}")
    else:
        lines.append("     (Semua service digunakan)")

    lines.append("=" * 64)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Periksa service yang digunakan vs tidak digunakan.")
    parser.add_argument("project_path", nargs="?", default="", help="Path direktori project atau apps/")
    parser.add_argument("--project-path", dest="project_path_opt", help="Alias untuk path direktori project atau apps/")
    parser.add_argument("--services", help="Daftar service eksplisit: name1:path1,name2:path2")
    parser.add_argument("--cpanel-meta", help="Path direktori metadata cPanel (userdata / bandwidth)")
    parser.add_argument("--db-dumps-dir", help="Path direktori file dump database .sql")
    parser.add_argument("--project-name", help="Nama project untuk pencarian dump DB")
    parser.add_argument("--all", action="store_true", help="Tandai semua service sebagai digunakan")
    parser.add_argument("--include", help="Nama service yang dipaksa aktif (koma terpisah)")
    parser.add_argument("--exclude", help="Nama service yang dipaksa nonaktif (koma terpisah)")
    parser.add_argument("--json", action="store_true", help="Output format JSON")
    parser.add_argument("--used-only", action="store_true", help="Output hanya nama service aktif (dipisah spasi)")
    parser.add_argument("--report", action="store_true", help="Tampilkan laporan format tabel CLI")

    args = parser.parse_args()

    services = []
    effective_project_path = args.project_path_opt or args.project_path
    if args.services:
        for item in args.services.split(","):
            item = item.strip()
            if ":" in item:
                k, v = item.split(":", 1)
                services.append({"name": k.strip(), "path": os.path.abspath(v.strip())})
    elif effective_project_path:
        proj_path = os.path.abspath(effective_project_path)
        apps_dir = os.path.join(proj_path, "apps")
        if os.path.isdir(apps_dir):
            for d in sorted(os.listdir(apps_dir)):
                fp = os.path.join(apps_dir, d)
                if os.path.isdir(fp) and not d.startswith("."):
                    services.append({"name": d, "path": fp})
        elif os.path.isdir(proj_path):
            # Coba scan via find_microservices jika ada
            try:
                from scripts.find_microservices import scan
                services = scan(proj_path)
            except Exception:
                for d in sorted(os.listdir(proj_path)):
                    fp = os.path.join(proj_path, d)
                    if os.path.isdir(fp) and not d.startswith("."):
                        services.append({"name": d, "path": fp})

    if not services:
        if args.json:
            print("[]")
        sys.exit(0)

    force_inc = args.include.split(",") if args.include else []
    force_exc = args.exclude.split(",") if args.exclude else []

    results = inspect_all_services(
        services=services,
        project_dir=effective_project_path,
        cpanel_meta_dir=args.cpanel_meta,
        db_dumps_dir=args.db_dumps_dir,
        force_include=force_inc,
        force_exclude=force_exc,
        all_as_used=args.all,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.used_only:
        used_names = [r["name"] for r in results if r["is_used"]]
        print(" ".join(used_names))
    else:
        print(format_cli_report(results))


if __name__ == "__main__":
    main()
