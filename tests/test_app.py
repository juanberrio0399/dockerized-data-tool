"""Tests for the CLI: clear errors and exit codes instead of tracebacks."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def run(tmp_path, content=None, name="data.csv", binary=False):
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content) if binary else path.write_text(content, encoding="utf-8")
    return path


def test_sample_summary_is_unchanged(capsys):
    assert app.main(str(ROOT / "sample.csv")) == app.EXIT_OK
    out = capsys.readouterr().out
    assert "Rows: 5  |  Columns: 3" in out
    assert "Columns: product, units, revenue" in out
    assert "Numeric summary:" in out
    assert "revenue" in out.split("Numeric summary:")[1]


def test_missing_file_exits_2_with_message(tmp_path, capsys):
    code = app.main(str(tmp_path / "nope.csv"))
    captured = capsys.readouterr()
    assert code == app.EXIT_BAD_PATH
    assert "file not found" in captured.err
    assert captured.out == ""


def test_directory_is_rejected(tmp_path, capsys):
    assert app.main(str(tmp_path)) == app.EXIT_BAD_PATH
    assert "not a file" in capsys.readouterr().err


def test_empty_file_exits_1(tmp_path, capsys):
    path = run(tmp_path, "")
    assert app.main(str(path)) == app.EXIT_BAD_DATA
    assert "empty" in capsys.readouterr().err


def test_malformed_csv_exits_1(tmp_path, capsys):
    path = run(tmp_path, 'a,b\n1,2\n3,"unclosed\n')
    assert app.main(str(path)) == app.EXIT_BAD_DATA
    assert "could not parse" in capsys.readouterr().err


def test_binary_file_exits_1(tmp_path, capsys):
    path = run(tmp_path, bytes([0xFF, 0xFE, 0x00, 0x81, 0x9F]) * 50, name="image.csv", binary=True)
    assert app.main(str(path)) == app.EXIT_BAD_DATA
    assert "could not parse" in capsys.readouterr().err


def test_header_only_file_reports_no_rows(tmp_path, capsys):
    path = run(tmp_path, "product,units,revenue\n")
    assert app.main(str(path)) == app.EXIT_OK
    out = capsys.readouterr().out
    assert "Rows: 0" in out
    assert "No data rows to summarize." in out


def test_text_only_columns_report_no_numeric_summary(tmp_path, capsys):
    path = run(tmp_path, "name,city\nAna,Bogota\nLuis,Cali\n")
    assert app.main(str(path)) == app.EXIT_OK
    assert "No numeric columns to summarize." in capsys.readouterr().out


def test_cli_process_has_no_traceback(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "app.py"), str(tmp_path / "missing.csv")], capture_output=True, text=True)
    assert result.returncode == app.EXIT_BAD_PATH
    assert "Traceback" not in result.stderr
    assert result.stderr.strip().startswith("Error:")
