"""Generate or verify the repository's checked-in Narrative Core JSON Schemas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "backend" / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from novel_core.schemas import schema_documents, schema_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in schemas differ from generated output",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "schemas",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mismatches: list[Path] = []

    if not args.check:
        args.output.mkdir(parents=True, exist_ok=True)

    for filename, schema in schema_documents():
        destination = args.output / filename
        expected = schema_json(schema)
        if args.check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != expected:
                mismatches.append(destination)
        else:
            destination.write_text(expected, encoding="utf-8")

    if mismatches:
        for path in mismatches:
            print(f"schema out of date: {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
