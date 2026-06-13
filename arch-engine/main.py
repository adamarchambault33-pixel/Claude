"""Arch Statement-to-Proposal Engine — CLI entry point.

Milestone 1: Extract + Structure.

Run a merchant processing statement PDF through stages 1 and 2 and print clean,
structured JSON to the terminal.

Usage:
    python main.py path/to/statement.pdf
    python main.py path/to/statement.pdf --raw          # also dump raw extract
    python main.py path/to/statement.pdf -o output/x.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from extract import extract_raw
from structure import DEFAULT_MODEL, structure_statement


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Extract + structure a merchant processing statement into clean JSON."
    )
    parser.add_argument("pdf", help="Path to the statement PDF")
    parser.add_argument(
        "-o", "--output", help="Write the JSON to this file as well as printing it"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw extracted text/tables before the JSON (for debugging)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model to use (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args(argv)

    # Stage 1: Extract
    try:
        print(f"[1/2] Extracting text + tables from {args.pdf} ...", file=sys.stderr)
        raw_text = extract_raw(args.pdf)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Extract failed: {exc}", file=sys.stderr)
        return 1

    if args.raw:
        print("\n========== RAW EXTRACT ==========", file=sys.stderr)
        print(raw_text, file=sys.stderr)
        print("========== END RAW EXTRACT ==========\n", file=sys.stderr)

    # Stage 2: Structure
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Structure failed: ANTHROPIC_API_KEY is not set.\n"
            "Copy .env.example to .env and add your key (or export ANTHROPIC_API_KEY).",
            file=sys.stderr,
        )
        return 1

    try:
        print(f"[2/2] Structuring with {args.model} ...", file=sys.stderr)
        statement = structure_statement(raw_text, model=args.model)
    except RuntimeError as exc:
        print(f"Structure failed: {exc}", file=sys.stderr)
        return 1

    json_out = statement.model_dump_json(indent=2)
    print(json_out)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_out)
        print(f"\nWrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
