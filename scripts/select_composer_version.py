#!/usr/bin/env python3
"""Select a Composer release compatible with the project's PHP runtime."""

import argparse
import re


def select_composer_version(php_version: str) -> str:
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", php_version)
    if not match:
        raise ValueError(f"Versi PHP tidak valid: {php_version!r}")

    version = tuple(int(part or 0) for part in match.groups())
    return "2.2" if version < (7, 2, 5) else "2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("php_version")
    args = parser.parse_args()
    try:
        print(select_composer_version(args.php_version))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
