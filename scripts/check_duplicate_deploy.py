#!/usr/bin/env python3
"""Identify projects that already have a LaDock deployment."""

import argparse
import json
import re
import sys
from pathlib import Path


def project_slug(name: str) -> str:
    return re.sub(r"^_+|_+$", "", re.sub(r"[^a-z0-9]+", "_", name.lower()))


def is_project_deployed(
    slug: str,
    deploy_root: Path,
    legacy_root: Path,
    container_names: list[str],
) -> bool:
    for root in (deploy_root, legacy_root):
        project_dir = root / slug
        if any(
            (project_dir / marker).is_file()
            for marker in ("docker-compose.yml", ".docker-compose-app.yml")
        ):
            return True

    for name in container_names:
        if name in {f"{slug}_app", f"app_{slug}", f"{slug}_gateway"}:
            return True
        if name.startswith(f"{slug}_") and name.endswith("_app"):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--deploy-root", required=True, type=Path)
    parser.add_argument("--legacy-root", required=True, type=Path)
    args = parser.parse_args()

    container_names = sys.stdin.read().splitlines()
    print(json.dumps({
        "deployed": is_project_deployed(
            args.slug,
            args.deploy_root,
            args.legacy_root,
            container_names,
        )
    }))


if __name__ == "__main__":
    main()
