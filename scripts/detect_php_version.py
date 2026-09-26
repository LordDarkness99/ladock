#!/usr/bin/env python3
"""
Deteksi versi PHP yang cocok untuk sebuah project Laravel, dibaca dari
constraint "php" di composer.json (require / require-dev).

Usage:
    python3 detect_php_version.py /path/ke/composer.json

Selalu print satu baris versi PHP ke stdout (fallback "8.4" kalau tidak
bisa dideteksi), supaya gampang ditangkap dari bash: PHP_VERSION=$(python3 ...)
"""
import json
import re
import sys

SUPPORTED = ["5.6", "7.0", "7.1", "7.2", "7.3", "7.4", "8.0", "8.1", "8.2", "8.3", "8.4"]
DEFAULT = "8.4"


def _version_key(v: str):
    return [int(x) for x in v.split(".")]


def detect(composer_path: str) -> str:
    try:
        with open(composer_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return DEFAULT

    constraint = (
        (data.get("require") or {}).get("php")
        or (data.get("require-dev") or {}).get("php")
    )
    if not constraint:
        return DEFAULT

    # 1) Kalau versi persis (mis. "8.2", "7.4") langsung tersebut di constraint, pakai itu
    for version in sorted(SUPPORTED, key=_version_key, reverse=True):
        if version in constraint:
            return version

    # 2) Fallback: baca operator + angka mayor.minor, mis. ">=8.1", "^7", "~7.4.0"
    match = re.search(r'(>=|>|\^|~)\s*(\d+)(?:\.(\d+))?', constraint)
    if match:
        major = int(match.group(2))
        minor = int(match.group(3)) if match.group(3) else 0
        candidate = f"{major}.{minor}"
        if candidate in SUPPORTED:
            return candidate
        same_major = [v for v in SUPPORTED if v.startswith(f"{major}.")]
        if same_major:
            # ambil versi tertinggi yang tersedia di mayor version yang sama
            return sorted(same_major, key=_version_key)[-1]

    return DEFAULT


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(DEFAULT)
        sys.exit(0)

    composer_path = sys.argv[1]
    result = detect(composer_path).strip()

    # Jaga-jaga: kalau karena alasan apapun hasilnya bukan versi yang valid, paksa fallback.
    if result not in SUPPORTED:
        print(f"[detect_php_version] Hasil deteksi '{result}' tidak valid, fallback ke {DEFAULT}", file=sys.stderr)
        result = DEFAULT

    # Debug ke stderr (tidak ikut tertangkap oleh $(...) di bash) supaya kelihatan constraint aslinya
    try:
        with open(composer_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        constraint = (raw.get("require") or {}).get("php") or (raw.get("require-dev") or {}).get("php")
        print(f"[detect_php_version] composer.json php constraint: {constraint!r} -> dipilih PHP {result}", file=sys.stderr)
    except Exception:
        print(f"[detect_php_version] composer.json tidak terbaca / tidak ada constraint php -> fallback PHP {result}", file=sys.stderr)

    # Baris INI SAJA yang boleh ke stdout, supaya aman ditangkap $(...) di bash
    print(result)