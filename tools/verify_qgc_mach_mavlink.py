#!/usr/bin/env python3
"""Verify generated local QGC + Mach MAVLink dialect headers."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_DIALECT = "qgc_mach"
WIRE_PROTOCOL = "2.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _message_header_name(message_name: str) -> str:
    return f"mavlink_msg_{message_name.lower()}.h"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc


def _expect_macro(text: str, macro: str, expected: int) -> str | None:
    match = re.search(rf"^#define\s+{re.escape(macro)}\s+(\d+)\s*$", text, re.MULTILINE)
    if not match:
        return f"missing macro {macro}"
    actual = int(match.group(1))
    if actual != expected:
        return f"{macro} is {actual}, expected {expected}"
    return None


def _parse_manifest(mavlink_root: Path, dialect: str) -> tuple[dict[str, str], list[dict[str, int | str]], list[str]]:
    manifest_path = mavlink_root / f"{dialect}_manifest.txt"
    if not manifest_path.is_file():
        return {}, [], [f"missing manifest {manifest_path}"]

    values: dict[str, str] = {}
    messages: list[dict[str, int | str]] = []
    failures: list[str] = []
    message_pattern = re.compile(r"^message=(\d+),([^,]+),min_len=(\d+),len=(\d+),crc=(\d+)$")

    for line_number, line in enumerate(_read(manifest_path).splitlines(), start=1):
        if not line or line.startswith("#"):
            continue

        message_match = message_pattern.match(line)
        if message_match:
            message_id, name, min_len, length, crc = message_match.groups()
            messages.append(
                {
                    "id": int(message_id),
                    "name": name,
                    "min_len": int(min_len),
                    "len": int(length),
                    "crc": int(crc),
                }
            )
            continue

        if "=" not in line:
            failures.append(f"{manifest_path}:{line_number}: malformed line {line!r}")
            continue

        key, value = line.split("=", 1)
        values[key] = value

    if not messages:
        failures.append(f"{manifest_path}: no message entries found")

    return values, messages, failures


def _verify_message_header(dialect_dir: Path, name: str, expected: dict[str, int | str]) -> list[str]:
    failures: list[str] = []
    header_path = dialect_dir / _message_header_name(name)

    if not header_path.is_file():
        return [f"missing message header {header_path}"]

    text = _read(header_path)
    macro_base = f"MAVLINK_MSG_ID_{name}"
    checks = {
        macro_base: int(expected["id"]),
        f"{macro_base}_MIN_LEN": int(expected["min_len"]),
        f"{macro_base}_LEN": int(expected["len"]),
        f"{macro_base}_CRC": int(expected["crc"]),
    }

    for macro, value in checks.items():
        failure = _expect_macro(text, macro, value)
        if failure:
            failures.append(f"{header_path}: {failure}")

    return failures


def _verify_dialect_header(dialect_header: Path, messages: list[dict[str, int | str]]) -> list[str]:
    failures: list[str] = []

    if not dialect_header.is_file():
        return [f"missing dialect header {dialect_header}"]

    text = _read(dialect_header)

    for message in messages:
        name = str(message["name"])
        message_id = int(message["id"])
        crc = int(message["crc"])
        min_len = int(message["min_len"])
        length = int(message["len"])

        crc_entry = f"{{{message_id}, {crc}, {min_len}, {length},"
        if crc_entry not in text:
            failures.append(f"{dialect_header}: missing CRC entry {crc_entry}...")

        if f"MAVLINK_MESSAGE_INFO_{name}" not in text:
            failures.append(f"{dialect_header}: missing MAVLINK_MESSAGE_INFO_{name}")

        name_entry = f'{{ "{name}", {message_id} }}'
        if name_entry not in text:
            failures.append(f"{dialect_header}: missing message name entry {name_entry}")

    return failures


def _verify_manifest_values(
    mavlink_root: Path,
    dialect: str,
    source_commit: str | None,
    values: dict[str, str],
) -> list[str]:
    failures: list[str] = []
    manifest_path = mavlink_root / f"{dialect}_manifest.txt"
    required = {
        "dialect": dialect,
        "wire_protocol": WIRE_PROTOCOL,
    }

    if source_commit:
        required["source_commit"] = source_commit

    for key, expected_value in required.items():
        actual_value = values.get(key)
        if actual_value != expected_value:
            failures.append(f"{manifest_path}: {key} is {actual_value!r}, expected {expected_value!r}")

    if "mavgen_source" not in values:
        failures.append(f"{manifest_path}: missing mavgen_source")

    return failures


def verify(mavlink_root: Path, dialect: str, source_commit: str | None) -> list[str]:
    failures: list[str] = []
    dialect_dir = mavlink_root / dialect
    manifest_values, messages, manifest_failures = _parse_manifest(mavlink_root, dialect)
    failures.extend(manifest_failures)

    if not (dialect_dir / "mavlink.h").is_file():
        failures.append(f"missing dialect mavlink.h at {dialect_dir / 'mavlink.h'}")

    if messages:
        failures.extend(_verify_dialect_header(dialect_dir / f"{dialect}.h", messages))

    for message in messages:
        failures.extend(_verify_message_header(dialect_dir, str(message["name"]), message))

    failures.extend(_verify_manifest_values(mavlink_root, dialect, source_commit, manifest_values))
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mavlink-root",
        type=Path,
        default=_repo_root() / "libs/mavlink/include/mavlink/v2.0",
        help="Generated MAVLink C header root.",
    )
    parser.add_argument("--dialect", default=DEFAULT_DIALECT, help="Dialect directory/header name.")
    parser.add_argument("--source-commit", help="Expected PX4 source commit recorded in the manifest.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures = verify(args.mavlink_root.resolve(), args.dialect, args.source_commit)

    if failures:
        print("QGC MAVLink verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"QGC MAVLink verification passed for {args.mavlink_root / args.dialect}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
