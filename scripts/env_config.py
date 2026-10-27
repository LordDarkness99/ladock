#!/usr/bin/env python3
"""Read and update simple dotenv files without executing their contents."""

import argparse
import re
from pathlib import Path


ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _decode_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = re.sub(r"\\([\\\"$])", r"\1", value)
            value = value.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")
        else:
            value = value.replace(r"\'", "'").replace(r"\\", "\\")
        return value

    value = re.split(r"\s+#", value, maxsplit=1)[0]
    return value.rstrip()


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ENV_ASSIGNMENT.match(line)
        if match:
            values[match.group(1)] = _decode_value(match.group(2))
    return values


def _encode_value(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", r"\$")
        .replace("\n", r"\n")
        .replace("\r", r"\r")
        .replace("\t", r"\t")
    )
    return f'"{escaped}"'


def set_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    assignment = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*)$")
    matching_lines = [
        (index, line, assignment.match(line))
        for index, line in enumerate(lines)
        if assignment.match(line)
    ]
    updated = f"{key}={_encode_value(value)}"
    if matching_lines and all(
        line.strip() == updated
        for _, line, _ in matching_lines
    ):
        return

    found = False
    for index, _, _ in matching_lines:
        lines[index] = updated
        found = True
    if not found:
        lines.append(updated)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    get_parser = commands.add_parser("get")
    get_parser.add_argument("--file", required=True, type=Path)
    get_parser.add_argument("key")

    set_parser = commands.add_parser("set")
    set_parser.add_argument("--file", required=True, type=Path)
    set_parser.add_argument("--key", required=True)
    set_parser.add_argument("--value", required=True)

    args = parser.parse_args()
    if args.command == "get":
        print(read_env_file(args.file).get(args.key, ""), end="")
        return

    set_env_value(args.file, args.key, args.value)
    if not args.file.exists():
        parser.error(f"Gagal menulis file environment: {args.file}")


if __name__ == "__main__":
    main()
