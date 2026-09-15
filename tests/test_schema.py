"""Tests for schema contracts: --infer-schema writes a structural contract, --schema enforces it."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def infer(tmp_path, csv=None):
    schema = tmp_path / "schema.yaml"
    assert app.main([str(csv or ROOT / "sample.csv"), "--infer-schema", str(schema)]) == app.EXIT_OK
    return schema


def test_infer_writes_columns_and_types_without_sample_ranges(tmp_path, capsys):
    schema = infer(tmp_path)
    doc = yaml.safe_load(schema.read_text(encoding="utf-8"))
    assert list(doc["columns"]) == ["product", "units", "revenue"]
    for column in doc["columns"].values():
        assert "checks" not in column or not column["checks"]
        assert not any(key.startswith(("greater_than", "less_than", "in_range")) for key in column)
    assert "Schema written" in capsys.readouterr().out


def test_a_different_valid_file_passes_the_inferred_contract(tmp_path, capsys):
    schema = infer(tmp_path)
    other = write(tmp_path, "other.csv", "product,units,revenue\nZ,1,5\nY,99999,123456\n")
    assert app.main([str(other), "--schema", str(schema)]) == app.EXIT_OK
    out = capsys.readouterr().out
    assert "Schema: OK" in out
    assert "Rows: 2" in out


def test_missing_column_fails_with_exit_3(tmp_path, capsys):
    schema = infer(tmp_path)
    capsys.readouterr()
    bad = write(tmp_path, "bad.csv", "product,units\nA,1\n")
    assert app.main([str(bad), "--schema", str(schema)]) == app.EXIT_SCHEMA
    captured = capsys.readouterr()
    assert "missing column 'revenue'" in captured.err
    assert "Rows:" not in captured.out


def test_wrong_type_reports_column_value_and_csv_line(tmp_path, capsys):
    schema = infer(tmp_path)
    capsys.readouterr()
    bad = write(tmp_path, "bad.csv", "product,units,revenue\nA,10,100\nB,twelve,200\n")
    assert app.main([str(bad), "--schema", str(schema)]) == app.EXIT_SCHEMA
    err = capsys.readouterr().err
    assert "column 'units'" in err
    assert "'twelve'" in err
    assert "line 3" in err
    assert "TypeError" not in err


def test_empty_values_in_a_required_column(tmp_path, capsys):
    schema = infer(tmp_path)
    capsys.readouterr()
    bad = write(tmp_path, "bad.csv", "product,units,revenue\nA,,100\n")
    assert app.main([str(bad), "--schema", str(schema)]) == app.EXIT_SCHEMA
    err = capsys.readouterr().err
    assert "column 'units'" in err
    assert "empty values" in err


def test_columns_with_empty_values_in_the_reference_stay_optional(tmp_path):
    ref = write(tmp_path, "ref.csv", "product,units,note\nA,1,\nB,2,urgent\n")
    schema = infer(tmp_path, ref)
    ok = write(tmp_path, "ok.csv", "product,units,note\nC,3,\n")
    assert app.main([str(ok), "--schema", str(schema)]) == app.EXIT_OK


def test_missing_schema_file_exits_2(tmp_path, capsys):
    assert app.main([str(ROOT / "sample.csv"), "--schema", str(tmp_path / "nope.yaml")]) == app.EXIT_BAD_PATH
    assert "schema file not found" in capsys.readouterr().err


def test_invalid_schema_file_exits_1(tmp_path, capsys):
    broken = write(tmp_path, "broken.yaml", "columns: [this is: not valid")
    assert app.main([str(ROOT / "sample.csv"), "--schema", str(broken)]) == app.EXIT_BAD_DATA
    assert "invalid schema" in capsys.readouterr().err


def test_summary_without_options_does_not_import_pandera(tmp_path):
    sys.modules.pop("pandera", None)
    assert app.main([str(ROOT / "sample.csv")]) == app.EXIT_OK
    assert "pandera" not in sys.modules
