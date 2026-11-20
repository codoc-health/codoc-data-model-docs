#!/usr/bin/env python3
"""Check the data dictionary CSVs in docs/csv for consistency.

Table pages (docs/**/*.md) render their columns with {{ read_csv('...') }}.
On each page, the CSV named after the page describes the table itself; any
other CSV on that page lists extension fields of the same table.

Run from anywhere:  python scripts/check_data_model.py
Exits with status 1 when a problem is found. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from pathlib import Path

HEADER = ["Field", "User Guide", "ETL Conventions", "Datatype",
          "Required", "Primary Key", "Foreign Key", "FK Table"]
FLAGS = ("Required", "Primary Key", "Foreign Key")
# Column types used in the model. Add to this list when a new type is introduced.
DATATYPE = re.compile(r"bigint\(64\)|integer\(32\)|double\(53\)|varchar\(\d+\)"
                      r"|text|boolean|date|timestamptz")
FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")
READ_CSV = re.compile(r"""read_csv\(\s*['"]([^'"]+)['"]""")
# Backticks are reserved for column and table names; values are written in *italics*.
BACKTICKED_NAME = re.compile(r"`([a-z][a-z0-9_]*)`")

problems: dict[tuple[str, int | None, str], None] = {}  # insertion-ordered set


def report(path: Path, line: int | None, message: str) -> None:
    problems[(os.path.relpath(path), line, message)] = None


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse(text: str, strict: bool):
    reader = csv.reader(io.StringIO(text), strict=strict)
    rows = []
    try:
        for row in reader:
            if row:  # blank lines group related fields visually; the site skips them
                rows.append((reader.line_num, row))
    except csv.Error as exc:
        return rows, (reader.line_num, exc)
    return rows, None


def read_table(path: Path) -> list[tuple[int, dict[str, str]]]:
    """Return (line number, column) pairs for one dictionary CSV."""
    text = path.read_text(encoding="utf-8-sig")
    rows, failure = parse(text, strict=True)
    if failure:
        report(path, failure[0], f"invalid CSV: {failure[1]}")
        rows, _ = parse(text, strict=False)  # keep checking what the lenient site build renders
    if not rows or rows[0][1] != HEADER:
        report(path, 1, f"header must be exactly: {','.join(HEADER)}")
        return []
    table = []
    for line, row in rows[1:]:
        if len(row) != len(HEADER):
            report(path, line, f"expected {len(HEADER)} cells, found {len(row)}")
        else:
            table.append((line, dict(zip(HEADER, (cell.strip() for cell in row)))))
    return table


def check_columns(path: Path, table) -> None:
    for line, col in table:
        name = col["Field"]
        if not FIELD_NAME.fullmatch(name):
            report(path, line, f"invalid field name {name!r}")
        for flag in FLAGS:
            if col[flag] not in ("Yes", "No"):
                report(path, line, f"{name}: {flag} must be Yes or No, found {col[flag]!r}")
        if not DATATYPE.fullmatch(col["Datatype"]):
            report(path, line, f"{name}: unknown datatype {col['Datatype']!r}")
        if (col["Foreign Key"] == "Yes") != bool(col["FK Table"]):
            report(path, line, f"{name}: Foreign Key is {col['Foreign Key']!r} "
                               f"but FK Table is {col['FK Table'] or 'empty'!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the data dictionary CSVs for consistency.")
    parser.add_argument("--docs-dir", type=Path, default=Path(__file__).resolve().parent.parent / "docs")
    docs = parser.parse_args().docs_dir.resolve()

    # Which CSVs each page renders. Every reference must exist and every CSV must be used.
    pages: dict[Path, list[Path]] = {}
    for page in sorted(docs.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for match in READ_CSV.finditer(text):
            path = (docs / match.group(1)).resolve()
            if path.is_file():
                pages.setdefault(page, []).append(path)
            else:
                report(page, line_of(text, match.start()), f"read_csv points to a missing file: {match.group(1)}")
    used = {path for paths in pages.values() for path in paths}
    for path in sorted(docs.rglob("*.csv")):
        if path.resolve() not in used:
            report(path, None, "CSV is not rendered by any page")

    tables = {path: read_table(path) for path in sorted(used)}
    for path, table in tables.items():
        check_columns(path, table)

    # Each page documents one table (the CSV named after the page) plus optional extensions.
    main_tables: dict[str, list] = {}
    for page, paths in pages.items():
        own = next((path for path in paths if path.stem == page.stem), None)
        if own is None:
            report(page, None, f"page must render {page.stem}.csv, the table it documents")
            continue
        main_tables[page.stem] = tables[own]
        for path in paths:
            keys = [col["Field"] for _, col in tables[path] if col["Primary Key"] == "Yes"]
            if path == own and len(keys) != 1:
                report(path, None, f"table must have exactly one primary key, found: {', '.join(keys) or 'none'}")
            elif path != own and keys:
                report(path, None, f"extension fields cannot be a primary key: {', '.join(keys)}")

    # Names in backticks must be a column shown on the same page, or a documented table.
    for page, paths in pages.items():
        fields: set[str] = set()
        for path in paths:
            for line, col in tables[path]:
                if col["Field"] in fields:
                    report(path, line, f"duplicate field {col['Field']} on {os.path.relpath(page)}")
                fields.add(col["Field"])
        known = fields | set(main_tables)
        text = page.read_text(encoding="utf-8")
        for match in BACKTICKED_NAME.finditer(text):
            if match.group(1) not in known:
                report(page, line_of(text, match.start()),
                       f"`{match.group(1)}` is not a column of this table (write values in *italics*)")
        for path in paths:
            for line, col in tables[path]:
                for name in BACKTICKED_NAME.findall(col["User Guide"] + " " + col["ETL Conventions"]):
                    if name not in known:
                        report(path, line, f"{col['Field']}: `{name}` is not a column of this table "
                                           "(write values in *italics*)")

    # Foreign keys must point to a documented table, with the same type as its primary key.
    for path, table in tables.items():
        for line, col in table:
            target = col["FK Table"]
            if not target:
                continue
            if target not in main_tables:
                report(path, line, f"{col['Field']}: FK Table {target!r} is not a documented table")
                continue
            keys = [key for _, key in main_tables[target] if key["Primary Key"] == "Yes"]
            if len(keys) == 1 and keys[0]["Datatype"] != col["Datatype"]:
                report(path, line, f"{col['Field']} is {col['Datatype']} but its target "
                                   f"{target}.{keys[0]['Field']} is {keys[0]['Datatype']}")

    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for file, line, message in problems:
        if in_actions:  # shown inline on the pull request diff
            text = message.replace("%", "%25").replace("\n", "%0A")
            print(f"::error file={file}{f',line={line}' if line else ''}::{text}")
        else:
            print(f"{file}:{line}: {message}" if line else f"{file}: {message}")
    if problems:
        print(f"\n{len(problems)} problem(s) found.", file=sys.stderr)
        return 1
    print(f"Data model OK: {len(main_tables)} tables, {len(tables)} CSV files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
