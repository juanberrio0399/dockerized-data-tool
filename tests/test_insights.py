"""Tests for --insights. The HTTP call is always mocked: no test ever reaches the real Gemini API."""

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

KEY = "test-key-not-a-real-one"
ANSWER = "Revenue is right-skewed and one column has empty values."

# A CSV whose every text cell is a token that must never show up in the request body.
ROWS_CSV = (
    "customer,city,units,revenue\n"
    "ZZTOPSECRETNAME,ZZHIDDENCITY,10,100.0\n"
    "ZZANOTHERNAME,ZZOTHERCITY,20,250.0\n"
    "ZZTHIRDNAME,ZZTHIRDCITY,30,400.0\n"
)
SECRETS = ["ZZTOPSECRETNAME", "ZZHIDDENCITY", "ZZANOTHERNAME", "ZZOTHERCITY", "ZZTHIRDNAME", "ZZTHIRDCITY"]


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else ok_payload(ANSWER)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def ok_payload(text):
    """Shape documented for the Interactions API: steps -> model_output -> content -> text."""
    return {
        "object": "interaction",
        "status": "completed",
        "steps": [
            {"type": "thought", "content": [{"type": "text", "text": "internal reasoning"}]},
            {"type": "model_output", "content": [{"type": "text", "text": text}]},
        ],
    }


class Calls(list):
    """The recorded POSTs, with the queue of answers attached so a test can replace it."""

    queue: list


@pytest.fixture
def calls(monkeypatch):
    """Captures every POST and replies with whatever the test queued. Also kills the retry sleep."""
    recorded = Calls()
    queue = [FakeResponse()]

    def fake_post(url, json=None, headers=None, timeout=None):
        recorded.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(app.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    recorded.queue = queue  # tests replace queue[:] to control the answers
    return recorded


def csv_file(tmp_path, content=ROWS_CSV):
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---------- happy path ----------


def test_insights_prints_the_answer_after_the_summary(tmp_path, calls, capsys):
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_OK
    out = capsys.readouterr().out
    assert "Numeric summary:" in out  # the normal summary still runs first
    assert ANSWER in out
    assert app.GEMINI_MODEL in out
    assert len(calls) == 1


def test_nothing_is_sent_without_the_flag(tmp_path, calls, capsys):
    assert app.main([csv_file(tmp_path)]) == app.EXIT_OK
    assert calls == []


def test_request_targets_the_pinned_model_and_endpoint(tmp_path, calls):
    app.main([csv_file(tmp_path), "--insights"])
    call = calls[0]
    assert call["url"] == app.GEMINI_URL == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert call["json"]["model"] == app.GEMINI_MODEL
    assert app.GEMINI_MODEL != "gemini-1.5-flash"  # retired model, must never come back
    assert call["timeout"] == app.GEMINI_TIMEOUT


# ---------- privacy ----------


def test_no_raw_row_value_is_ever_sent(tmp_path, calls):
    app.main([csv_file(tmp_path), "--insights"])
    body = str(calls[0]["json"])
    for secret in SECRETS:
        assert secret not in body
    for line in ROWS_CSV.strip().splitlines()[1:]:
        assert line not in body
    # what IS sent: aggregates and the column names
    assert "Numeric summary (pandas describe)" in body
    assert "revenue" in body


def test_anonymize_also_hides_the_column_names(tmp_path, calls):
    app.main([csv_file(tmp_path), "--insights", "--insights-anonymize"])
    body = str(calls[0]["json"])
    for name in ("customer", "city", "units", "revenue"):
        assert name not in body
    assert "col_1" in body and "col_4" in body


def test_anonymize_does_not_rename_the_users_dataframe(tmp_path, calls, capsys):
    app.main([csv_file(tmp_path), "--insights", "--insights-anonymize"])
    assert "Columns: customer, city, units, revenue" in capsys.readouterr().out


def test_anonymize_alone_is_rejected(tmp_path, calls):
    with pytest.raises(SystemExit):
        app.main([csv_file(tmp_path), "--insights-anonymize"])
    assert calls == []


def test_payload_is_capped(tmp_path, calls):
    wide = ",".join(f"column_with_a_long_name_{i}" for i in range(500))
    app.main([csv_file(tmp_path, wide + "\n" + ",".join("1" for _ in range(500)) + "\n"), "--insights"])
    assert len(calls[0]["json"]["input"]) <= app.GEMINI_MAX_CHARS + 200  # cap + the short framing sentence


def test_the_key_travels_in_the_header_only(tmp_path, calls, capsys):
    app.main([csv_file(tmp_path), "--insights"])
    call = calls[0]
    assert call["headers"]["x-goog-api-key"] == KEY
    assert KEY not in call["url"]
    assert KEY not in str(call["json"])
    captured = capsys.readouterr()
    assert KEY not in captured.out and KEY not in captured.err


# ---------- failures: never a traceback, never a lost summary ----------


def test_missing_key_exits_4_and_keeps_the_summary(tmp_path, calls, monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    captured = capsys.readouterr()
    assert "Numeric summary:" in captured.out
    assert "GEMINI_API_KEY" in captured.err
    assert calls == []


def test_blank_key_is_treated_as_missing(tmp_path, calls, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert "GEMINI_API_KEY" in capsys.readouterr().err
    assert calls == []


def test_api_error_exits_4_with_the_status_and_message(tmp_path, calls, capsys):
    calls.queue[:] = [FakeResponse(400, {"error": {"message": "API key not valid"}})]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    captured = capsys.readouterr()
    assert "Numeric summary:" in captured.out
    assert "HTTP 400" in captured.err and "API key not valid" in captured.err


def test_timeout_exits_4(tmp_path, calls, capsys):
    calls.queue[:] = [requests.Timeout("too slow")]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert "did not answer within" in capsys.readouterr().err


def test_connection_error_exits_4(tmp_path, calls, capsys):
    calls.queue[:] = [requests.ConnectionError("offline")]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert "could not reach the Gemini API" in capsys.readouterr().err


def test_empty_answer_exits_4(tmp_path, calls, capsys):
    calls.queue[:] = [FakeResponse(200, {"steps": []})]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert "empty answer" in capsys.readouterr().err


def test_non_json_error_body_does_not_crash(tmp_path, calls, capsys):
    calls.queue[:] = [FakeResponse(503, None), FakeResponse(503, None)]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert "no details" in capsys.readouterr().err


# ---------- one retry on 429 / 5xx ----------


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_once_and_succeeds(tmp_path, calls, capsys, status):
    calls.queue[:] = [FakeResponse(status, {}), FakeResponse()]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_OK
    assert len(calls) == 2
    assert ANSWER in capsys.readouterr().out


def test_retries_only_once(tmp_path, calls, capsys):
    calls.queue[:] = [FakeResponse(429, {}), FakeResponse(429, {"error": {"message": "quota"}})]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert len(calls) == 2
    assert "HTTP 429" in capsys.readouterr().err


def test_client_errors_are_not_retried(tmp_path, calls):
    calls.queue[:] = [FakeResponse(403, {"error": {"message": "forbidden"}}), FakeResponse()]
    assert app.main([csv_file(tmp_path), "--insights"]) == app.EXIT_INSIGHTS
    assert len(calls) == 1


# ---------- payload building ----------


def test_stats_payload_reports_nulls_and_skips_text_describe():
    import pandas as pd

    df = pd.DataFrame({"name": ["ZZSECRET", "ZZSECRET", None], "units": [1, 2, None]})
    payload = app.stats_payload(df)
    assert "ZZSECRET" not in payload  # describe()'s `top` row would have leaked it
    lines = payload.splitlines()
    # the dtype spelling changed in pandas 3 (object -> str), so only the shape of the line is asserted
    assert any(line.startswith("- name: ") and line.endswith(", 1 empty") for line in lines)
    assert any(line.startswith("- units: ") and line.endswith(", 1 empty") for line in lines)
    assert "Rows: 3" in payload


def test_stats_payload_handles_a_file_without_numeric_columns():
    import pandas as pd

    payload = app.stats_payload(pd.DataFrame({"city": ["ZZHIDDENCITY"]}))
    assert "No numeric columns." in payload
    assert "ZZHIDDENCITY" not in payload
