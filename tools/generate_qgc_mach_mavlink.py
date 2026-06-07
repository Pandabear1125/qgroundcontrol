#!/usr/bin/env python3
"""Generate local QGC + Mach MAVLink C headers from PX4 XML."""

from __future__ import annotations

import argparse
import copy
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path


DEFAULT_DIALECT = "qgc_mach"
DEFAULT_INCLUDE_XML = "all.xml"
DEFAULT_XML_DIR = "src/modules/mavlink/mavlink/message_definitions/v1.0"
DEFAULT_PYMAVLINK_DIR = "src/modules/mavlink/mavlink/pymavlink"
WIRE_PROTOCOL = "2.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_output_root() -> Path:
    return _repo_root() / "libs/mavlink/include/mavlink/v2.0"


def _run(command: list[str], *, cwd: Path | None = None, stdout: int | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, cwd=cwd, check=True, stdout=stdout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing command {command[0]!r}") from exc
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(shlex.quote(part) for part in command)
        raise RuntimeError(f"command failed with exit code {exc.returncode}: {rendered}") from exc


def _check_output(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(command, cwd=cwd, text=True).strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing command {command[0]!r}") from exc
    except subprocess.CalledProcessError as exc:
        rendered = " ".join(shlex.quote(part) for part in command)
        raise RuntimeError(f"command failed with exit code {exc.returncode}: {rendered}") from exc


def _resolve_commit(px4_repo: Path, px4_ref: str) -> str:
    return _check_output(["git", "-C", str(px4_repo), "rev-parse", "--verify", f"{px4_ref}^{{commit}}"])


def _archive_tree(px4_repo: Path, commit: str, repo_path: str, destination: Path) -> Path:
    result = _run(["git", "-C", str(px4_repo), "archive", commit, repo_path], stdout=subprocess.PIPE)
    archive = result.stdout

    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(destination)

    output_path = destination / repo_path
    if not output_path.exists():
        raise RuntimeError(f"git archive did not produce expected path: {output_path}")

    return output_path


def _resolve_source_xml(xml_dir: Path, source_xml: str) -> Path:
    source_path = Path(source_xml)
    if source_path.is_absolute():
        return source_path
    return xml_dir / source_path


def _source_message_metadata(source_xml: Path, message_elements: list[ET.Element]) -> list[dict[str, int | str]]:
    messages: list[dict[str, int | str]] = []
    seen_ids: set[int] = set()
    seen_names: set[str] = set()

    for message in message_elements:
        name = message.attrib.get("name")
        message_id_text = message.attrib.get("id")
        if not name or not message_id_text:
            raise RuntimeError(f"{source_xml} contains a message without both name and id")

        try:
            message_id = int(message_id_text)
        except ValueError as exc:
            raise RuntimeError(f"{source_xml} contains non-numeric message id {message_id_text!r}") from exc

        if name in seen_names:
            raise RuntimeError(f"{source_xml} contains duplicate message name {name}")
        if message_id in seen_ids:
            raise RuntimeError(f"{source_xml} contains duplicate message id {message_id}")

        seen_names.add(name)
        seen_ids.add(message_id)
        messages.append({"name": name, "id": message_id})

    return messages


def _build_hybrid_xml(
    xml_dir: Path,
    source_xml: str,
    include_xml: str,
    dialect: str,
) -> tuple[Path, list[dict[str, int | str]], Path]:
    source_path = _resolve_source_xml(xml_dir, source_xml)
    if not source_path.is_file():
        raise RuntimeError(f"missing source MAVLink XML at {source_path}")

    source_root = ET.parse(source_path).getroot()
    source_enums = source_root.find("enums")
    source_messages = source_root.find("messages")

    if source_messages is None:
        raise RuntimeError(f"{source_path} must contain <messages>")

    message_elements = source_messages.findall("message")
    if not message_elements:
        raise RuntimeError(f"{source_path} does not define any messages")

    messages = _source_message_metadata(source_path, message_elements)

    wrapper = ET.Element("mavlink")
    ET.SubElement(wrapper, "include").text = include_xml
    ET.SubElement(wrapper, "version").text = "3"
    ET.SubElement(wrapper, "dialect").text = "0"

    enums = ET.SubElement(wrapper, "enums")
    if source_enums is not None:
        for enum in source_enums.findall("enum"):
            enums.append(copy.deepcopy(enum))

    output_messages = ET.SubElement(wrapper, "messages")
    for message in message_elements:
        output_messages.append(copy.deepcopy(message))

    ET.indent(wrapper, space="  ")
    output = xml_dir / f"{dialect}.xml"
    ET.ElementTree(wrapper).write(output, encoding="utf-8", xml_declaration=True)
    return output, messages, source_path


def _mavgen_command(args: argparse.Namespace, px4_pymavlink_dir: Path | None) -> tuple[list[str], str]:
    command = args.mavgen_cmd or os.environ.get("MAVGEN_CMD")
    if command:
        return shlex.split(command), "custom"

    if px4_pymavlink_dir is not None:
        px4_mavgen = px4_pymavlink_dir / "tools/mavgen.py"
        if not px4_mavgen.is_file():
            raise RuntimeError(f"PX4 pymavlink archive did not contain {px4_mavgen}")
        uv = shutil.which("uv")
        if uv:
            return [
                uv,
                "run",
                "--with",
                "future",
                "--with",
                "lxml",
                "--with",
                "fastcrc",
                "python",
                str(px4_mavgen),
            ], "px4_archive"
        return [sys.executable, str(px4_mavgen)], "px4_archive"

    mavgen_on_path = shutil.which("mavgen.py")
    if mavgen_on_path:
        return [mavgen_on_path], "path"

    raise RuntimeError("could not find mavgen.py; install pymavlink or pass --mavgen-cmd")


def _generate_headers(mavgen: list[str], dialect_xml: Path, output_dir: Path) -> None:
    command = [
        *mavgen,
        "--lang=C",
        f"--wire-protocol={WIRE_PROTOCOL}",
        f"--output={output_dir}",
        str(dialect_xml),
    ]
    _run(command)


def _replace_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    for child in destination.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _validate_output_root(output_root: Path, force_output_root: bool) -> None:
    default_output_root = _default_output_root().resolve()
    if output_root == default_output_root or force_output_root:
        return

    raise RuntimeError(
        f"refusing to replace non-default MAVLink output root {output_root}; "
        f"expected {default_output_root}. Pass --force-output-root to generate elsewhere."
    )


def _message_header_name(message_name: str) -> str:
    return f"mavlink_msg_{message_name.lower()}.h"


def _read_macro(text: str, macro: str, header_path: Path) -> int:
    match = re.search(rf"^#define\s+{re.escape(macro)}\s+(\d+)\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{header_path} is missing macro {macro}")
    return int(match.group(1))


def _generated_message_metadata(
    output_root: Path,
    dialect: str,
    source_messages: list[dict[str, int | str]],
) -> list[dict[str, int | str]]:
    dialect_dir = output_root / dialect
    generated: list[dict[str, int | str]] = []

    for source_message in source_messages:
        name = str(source_message["name"])
        source_id = int(source_message["id"])
        header_path = dialect_dir / _message_header_name(name)

        if not header_path.is_file():
            raise RuntimeError(f"missing generated message header {header_path}")

        text = header_path.read_text(encoding="utf-8")
        macro_base = f"MAVLINK_MSG_ID_{name}"
        generated_id = _read_macro(text, macro_base, header_path)
        if generated_id != source_id:
            raise RuntimeError(f"{header_path} has id {generated_id}, expected {source_id} from source XML")

        generated.append(
            {
                "id": generated_id,
                "name": name,
                "min_len": _read_macro(text, f"{macro_base}_MIN_LEN", header_path),
                "len": _read_macro(text, f"{macro_base}_LEN", header_path),
                "crc": _read_macro(text, f"{macro_base}_CRC", header_path),
            }
        )

    return generated


def _write_manifest(
    output_root: Path,
    args: argparse.Namespace,
    commit: str,
    mavgen_source: str,
    source_path: Path,
    messages: list[dict[str, int | str]],
) -> None:
    manifest = output_root / f"{args.dialect}_manifest.txt"
    lines = [
        "# QGC MAVLink generated headers",
        f"dialect={args.dialect}",
        f"wire_protocol={WIRE_PROTOCOL}",
        f"source_ref={args.px4_ref}",
        f"source_commit={commit}",
        f"xml_dir={args.xml_dir}",
        f"source_xml={source_path.name}",
        f"include_xml={args.include_xml}",
        f"mavgen_source={mavgen_source}",
    ]

    for message in messages:
        lines.append(
            f"message={message['id']},{message['name']},"
            f"min_len={message['min_len']},len={message['len']},crc={message['crc']}"
        )

    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--px4-repo", type=Path, required=True, help="PX4 repository containing MAVLink XML.")
    parser.add_argument("--px4-ref", required=True, help="PX4 ref/commit to generate from.")
    parser.add_argument("--xml-dir", default=DEFAULT_XML_DIR, help="MAVLink XML directory inside PX4.")
    parser.add_argument(
        "--source-xml",
        required=True,
        help="Mach MAVLink XML to merge. Relative paths are resolved inside --xml-dir.",
    )
    parser.add_argument(
        "--include-xml",
        default=DEFAULT_INCLUDE_XML,
        help="Base MAVLink XML included by the generated wrapper dialect.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_default_output_root(),
        help="Destination MAVLink C header root.",
    )
    parser.add_argument(
        "--force-output-root",
        action="store_true",
        help="Allow replacing a non-default --output-root. Intended for tests or one-off inspection.",
    )
    parser.add_argument("--dialect", default=DEFAULT_DIALECT, help="Generated QGC hybrid dialect name.")
    parser.add_argument(
        "--mavgen-cmd",
        help="Command used to invoke mavgen.py. Defaults to MAVGEN_CMD, then PX4's bundled mavgen.py from --px4-ref.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    px4_repo = args.px4_repo.resolve()
    output_root = args.output_root.resolve()

    try:
        commit = _resolve_commit(px4_repo, args.px4_ref)
        _validate_output_root(output_root, args.force_output_root)

        with tempfile.TemporaryDirectory(prefix="qgc_mavlink_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            xml_dir = _archive_tree(px4_repo, commit, args.xml_dir, temp_dir / "xml")
            px4_pymavlink_dir = None
            if not (args.mavgen_cmd or os.environ.get("MAVGEN_CMD")):
                px4_pymavlink_dir = _archive_tree(px4_repo, commit, DEFAULT_PYMAVLINK_DIR, temp_dir / "pymavlink")
            mavgen, mavgen_source = _mavgen_command(args, px4_pymavlink_dir)
            dialect_xml, source_messages, source_path = _build_hybrid_xml(
                xml_dir,
                args.source_xml,
                args.include_xml,
                args.dialect,
            )
            generated_root = temp_dir / "generated"
            _generate_headers(mavgen, dialect_xml, generated_root)
            _replace_tree(generated_root, output_root)
            generated_messages = _generated_message_metadata(output_root, args.dialect, source_messages)
            _write_manifest(output_root, args, commit, mavgen_source, source_path, generated_messages)

        print(f"Generated {args.dialect} MAVLink headers at {output_root}")
        print(f"PX4 source commit: {commit}")
        print(f"MAVLink generator source: {mavgen_source}")
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
