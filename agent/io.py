"""Output writers used by research-synthesis workflows."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any


def _output_path(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_json(data: Any, path: str | Path) -> None:
    _output_path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_markdown_matrix(rows: list[dict], path: str | Path) -> None:
    output = _output_path(path)
    if not rows:
        output.write_text("# Literature Matrix\n\n_No sources._\n", encoding="utf-8")
        return

    keys = list(rows[0])
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for row in rows:
        cells = [
            str(row.get(key, ""))
            .replace("\n", " ")
            .replace("|", "\\|")[:500]
            for key in keys
        ]
        lines.append("| " + " | ".join(cells) + " |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(rows: list[dict], path: str | Path) -> None:
    output = _output_path(path)
    if not rows:
        output.write_text("", encoding="utf-8")
        return

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(rows: list[dict], path: str | Path) -> None:
    output = _output_path(path)
    with sqlite3.connect(output) as connection:
        connection.execute("DROP TABLE IF EXISTS literature_matrix")
        if not rows:
            connection.execute(
                "CREATE TABLE literature_matrix (_empty TEXT)"
            )
            return

        keys = list(rows[0])
        quoted_keys = [key.replace('"', '""') for key in keys]
        columns = ",".join(f'"{key}" TEXT' for key in quoted_keys)
        placeholders = ",".join("?" for _ in keys)
        connection.execute(f"CREATE TABLE literature_matrix ({columns})")
        connection.executemany(
            f"INSERT INTO literature_matrix VALUES ({placeholders})",
            [
                [
                    json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, (list, dict))
                    else str(value)
                    for value in (row.get(key, "") for key in keys)
                ]
                for row in rows
            ],
        )
