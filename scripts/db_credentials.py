#!/usr/bin/env python3
"""Generate collision-resistant MySQL usernames for deployed services."""

import argparse
import hashlib
import re
from collections.abc import Iterable


def service_db_username(
    project_name: str,
    service_name: str,
    preferred: str = "",
    used: Iterable[str] = (),
) -> str:
    used_usernames = set(used)
    if preferred and preferred not in used_usernames:
        if len(preferred) > 32:
            raise ValueError("Username MySQL tidak boleh lebih dari 32 karakter.")
        return preferred

    identity = f"{project_name}_{service_name}".encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:16]
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", project_name).strip("_")[:10] or "ladock"
    username = f"{prefix}_{suffix}_u"
    if username in used_usernames:
        raise ValueError(f"Tidak dapat membuat username MySQL unik untuk service '{service_name}'.")
    return username


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--preferred", default="")
    parser.add_argument("--used", action="append", default=[])
    args = parser.parse_args()

    try:
        print(
            service_db_username(
                args.project,
                args.service,
                preferred=args.preferred,
                used=args.used,
            ),
            end="",
        )
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
