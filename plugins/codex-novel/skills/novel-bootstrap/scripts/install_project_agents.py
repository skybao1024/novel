from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "project-AGENTS.md"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install project-scoped Codex guidance into a Novel project."
    )
    parser.add_argument("--project", type=Path, required=True)
    return parser


def _existing_result(destination: Path, template: bytes) -> int:
    if destination.is_symlink():
        print(f"refusing to replace symlink: {destination}", file=sys.stderr)
        return 3
    if not destination.is_file():
        print(f"refusing to replace non-file path: {destination}", file=sys.stderr)
        return 3
    if destination.read_bytes() == template:
        print(f"unchanged: {destination}")
        return 0
    print(f"refusing to overwrite existing guidance: {destination}", file=sys.stderr)
    return 3


def main() -> int:
    args = _parser().parse_args()
    project_root = args.project.expanduser().resolve()
    manifest = project_root / "novel.yaml"
    destination = project_root / "AGENTS.md"

    if not project_root.is_dir():
        print(f"project directory does not exist: {project_root}", file=sys.stderr)
        return 2
    if not manifest.is_file():
        print(f"cannot find Novel manifest: {manifest}", file=sys.stderr)
        return 2

    template = TEMPLATE_PATH.read_bytes()
    if os.path.lexists(destination):
        return _existing_result(destination, template)

    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )
    except FileExistsError:
        return _existing_result(destination, template)

    with os.fdopen(descriptor, "wb") as guidance:
        guidance.write(template)
        guidance.flush()
        os.fsync(guidance.fileno())
    print(f"created: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
