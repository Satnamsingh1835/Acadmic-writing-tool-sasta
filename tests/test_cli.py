import json
from pathlib import Path

from agent.cli import main
from agent.io import write_csv, write_json, write_markdown_matrix, write_sqlite


def test_source_command_does_not_require_generic_files_attribute(tmp_path, capsys):
    source = tmp_path / "source.txt"
    source.write_text("Gupta (2000) examines caste and land relations.", encoding="utf-8")

    exit_code = main(["source", str(source), "--id", "S1"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == "S1"


def test_source_command_creates_nested_output_directory(tmp_path):
    source = tmp_path / "source.txt"
    output = tmp_path / "nested" / "records" / "S1.json"
    source.write_text("Gupta (2000) examines caste and land relations.", encoding="utf-8")

    main(["source", str(source), "--id", "S1", "--output", str(output)])

    assert json.loads(output.read_text(encoding="utf-8"))["source_id"] == "S1"


def test_human_edit_uses_text_output_and_skips_source_extraction(tmp_path):
    draft = tmp_path / "draft.txt"
    output = tmp_path / "edited" / "draft.txt"
    draft.write_text(
        "It is important to note that caste shapes access to land.",
        encoding="utf-8",
    )

    main(["human-edit", str(draft), "--output", str(output)])

    assert "important to note" not in output.read_text(encoding="utf-8").lower()


def test_paragraph_audit_does_not_require_source_files(tmp_path):
    output = tmp_path / "audit.json"

    main(
        [
            "paragraph-audit",
            "--paragraph",
            "Caste shapes access to land.",
            "--output",
            str(output),
        ]
    )

    assert "researcher_questions" in json.loads(output.read_text(encoding="utf-8"))


def test_matrix_default_extension_matches_selected_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("Gupta (2000) examines caste and land relations.", encoding="utf-8")

    main(["matrix", str(source), "--format", "csv"])

    assert (tmp_path / "outputs" / "matrix.csv").exists()
    assert not (tmp_path / "outputs" / "matrix.json").exists()


def test_output_writers_create_files_for_empty_results(tmp_path):
    json_path = tmp_path / "nested" / "result.json"
    csv_path = tmp_path / "nested" / "result.csv"
    markdown_path = tmp_path / "nested" / "result.md"
    sqlite_path = tmp_path / "nested" / "result.sqlite"

    write_json([], json_path)
    write_csv([], csv_path)
    write_markdown_matrix([], markdown_path)
    write_sqlite([], sqlite_path)

    for path in (json_path, csv_path, markdown_path, sqlite_path):
        assert path.exists(), Path(path)
