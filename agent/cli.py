"""Command-line interface for deterministic research-synthesis workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from academic_suggestions import AcademicSuggestionEngine
from advanced_humanize import AdvancedHumanizer
from argument_diagnostics import ArgumentDiagnostics

from .config import load_config
from .extractor import extract_source
from .io import write_csv, write_json, write_markdown_matrix, write_sqlite
from .parsing import read_source
from .pipeline import ResearchSynthesist
from .synthesis import Synthesizer
from .validation import Validator

SOURCE_COMMANDS = {
    "matrix",
    "debate-map",
    "gap-analysis",
    "concept-map",
    "historical-synthesis",
    "research-questions",
    "audit",
    "citation-audit",
    "synthesize",
}


def _sources(files: list[str]):
    return [
        extract_source(read_source(file), str(file), path=file)
        for file in files
    ]


def _default_output(command: str, matrix_format: str | None = None) -> str:
    if command == "human-edit":
        return "outputs/human_edit.txt"
    if command == "matrix":
        extension = {"json": "json", "csv": "csv", "md": "md", "sqlite": "sqlite"}
        return f"outputs/matrix.{extension[matrix_format or 'json']}"
    return f"outputs/{command.replace('-', '_')}.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-synthesist")
    subparsers = parser.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source", help="Extract one source record")
    source.add_argument("file")
    source.add_argument("--id", required=True)
    source.add_argument("--title", default="")
    source.add_argument("-o", "--output")

    for name in sorted(SOURCE_COMMANDS - {"synthesize"}):
        command = subparsers.add_parser(name)
        command.add_argument("files", nargs="+")
        command.add_argument("-o", "--output")
        if name == "matrix":
            command.add_argument(
                "--format",
                choices=("json", "csv", "md", "sqlite"),
                default="json",
            )
        if name in {"audit", "citation-audit"}:
            command.add_argument("--text", required=True)

    synthesize = subparsers.add_parser("synthesize")
    synthesize.add_argument("files", nargs="+")
    synthesize.add_argument("-o", "--output")

    paragraph_audit = subparsers.add_parser("paragraph-audit")
    paragraph_audit.add_argument("--paragraph", required=True)
    paragraph_audit.add_argument("-o", "--output")

    human_edit = subparsers.add_parser("human-edit")
    human_edit.add_argument("file")
    human_edit.add_argument(
        "--profile",
        choices=("conservative", "standard", "polish"),
        default="standard",
    )
    human_edit.add_argument("-o", "--output")

    suggestions = subparsers.add_parser("suggest")
    suggestions.add_argument("file")
    suggestions.add_argument(
        "--profile",
        choices=("conservative", "standard", "polish"),
        default="standard",
    )
    suggestions.add_argument("-o", "--output")

    return parser


def _write_matrix(rows: list[dict], output: str, output_format: str) -> None:
    writers = {
        "json": write_json,
        "csv": write_csv,
        "md": write_markdown_matrix,
        "sqlite": write_sqlite,
    }
    writers[output_format](rows, output)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command

    if command == "source":
        data = extract_source(
            read_source(args.file),
            args.id,
            args.title,
            path=args.file,
        ).to_dict()
        if args.output:
            write_json(data, args.output)
            print(args.output)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if command == "human-edit":
        output = args.output or _default_output(command)
        text = Path(args.file).read_text(encoding="utf-8")
        revised = AdvancedHumanizer().humanize_literature_review(text, args.profile)
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(revised, encoding="utf-8")
        print(output)
        return 0

    if command == "suggest":
        output = args.output or _default_output(command)
        text = Path(args.file).read_text(encoding="utf-8")
        write_json(AcademicSuggestionEngine().suggest(text, args.profile), output)
        print(output)
        return 0

    if command == "paragraph-audit":
        output = args.output or _default_output(command)
        write_json(ArgumentDiagnostics().analyse(args.paragraph), output)
        print(output)
        return 0

    output = args.output or _default_output(
        command,
        getattr(args, "format", None),
    )

    if command == "synthesize":
        write_json(ResearchSynthesist().model_synthesis(args.files), output)
        print(output)
        return 0

    sources = _sources(args.files)
    synthesizer = Synthesizer(load_config())

    if command == "matrix":
        _write_matrix(synthesizer.matrix(sources), output, args.format)
    elif command == "debate-map":
        write_json(synthesizer.debates(sources), output)
    elif command == "concept-map":
        write_json(synthesizer.concepts(sources), output)
    elif command == "historical-synthesis":
        write_json(synthesizer.historical(sources), output)
    elif command == "gap-analysis":
        write_json([gap.__dict__ for gap in synthesizer.gaps(sources)], output)
    elif command == "research-questions":
        write_json(
            synthesizer.research_questions(synthesizer.gaps(sources)),
            output,
        )
    elif command in {"audit", "citation-audit"}:
        gaps = synthesizer.gaps(sources) if command == "audit" else []
        prose = Path(args.text).read_text(encoding="utf-8")
        write_json(Validator().quality_report(sources, [], gaps, prose), output)
    else:  # Defensive guard if a parser command is added without a handler.
        raise ValueError(f"Unsupported command: {command}")

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
