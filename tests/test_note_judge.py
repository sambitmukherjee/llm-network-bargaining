"""Blind prompts, cached coding, retries, quote flags and repeat consistency."""

import asyncio
from dataclasses import replace
import json
from math import ceil
from pathlib import Path

import pandas as pd
import pytest

from llm_network_bargaining.fake_client import FakeChatClient
from llm_network_bargaining.model_client import build_chat_kwargs
from llm_network_bargaining.notes import LABELS
from llm_network_bargaining.notes import cli
from llm_network_bargaining.notes.consistency import cohens_kappa, consistency_ids
from llm_network_bargaining.notes.judge import (JUDGE_TEMPLATES, OUTPUT_COLUMNS, KeywordResponder, code_notes,
    estimate_notes, judge_prompt, judge_response_format, load_judge_config, note_id, quote_flags, validate_labels)
from phase7_helpers import note_dataset


def test_exact_request_prompt_and_blindness(tmp_path: Path) -> None:
    config = load_judge_config().model_copy(update={"consistency_share": 0})
    ds = note_dataset(["Vash has no one else, so ask 18.", "A fair 12/12 keeps things friendly."])
    client = FakeChatClient(KeywordResponder())
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    request = client.requests[0]
    expected = (Path(__file__).parent / "golden/JUDGE_V3.txt").read_text().rstrip("\n")
    assert JUDGE_TEMPLATES[config.judge_version] == expected
    assert request.kwargs == build_chat_kwargs(config.model, request.kwargs["messages"], judge_response_format())
    assert request.purpose == "judge" and request.kwargs["reasoning_effort"] == "medium"
    assert request.kwargs["max_completion_tokens"] == 12000
    prompt = request.kwargs["messages"][0]["content"]
    notes_json = json.dumps(request.context["notes"], ensure_ascii=False)
    assert prompt.replace(notes_json, "") == expected.replace("{NOTES_JSON}", "")
    for hidden in ("line3", "full_map", "own_links", config.model.model_id):
        assert hidden not in prompt
    assert set(result.labels.columns) == set(OUTPUT_COLUMNS)
    assert result.labels.dry_run.all()
    first = result.labels.iloc[0]
    assert first.exclusion and first.exclusion_quote == "no one else"
    assert not first.fairness and not first.structure and not first.recognition
    assert result.labels.iloc[1].fairness_quote == "fair"
    assert result.costs["n_calls"] == 1 and result.costs["total_cost_usd"] > 0


def test_keyword_recognition_deduplication_empty_and_cache(tmp_path: Path) -> None:
    texts = ["Classic ultimatum logic.", "Classic ultimatum logic.", "  ", "ignored auto", None]
    ds = note_dataset(texts, automatic_at=3)
    config = load_judge_config()
    client = FakeChatClient(KeywordResponder())
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    assert result.labels.status.tolist() == ["coded", "coded", "empty", "empty"]
    assert result.labels.turn_index.tolist() == [0, 1, 2, 4]
    assert result.labels.iloc[0].recognition_quote == "ultimatum"
    assert result.labels.note_id.iloc[0] == result.labels.note_id.iloc[1]
    assert len((tmp_path / "judge_cache.jsonl").read_text().splitlines()) == 1
    assert result.consistency["n_selected"] == 1 and result.consistency["n_paired"] == 1
    assert len(client.requests) == 2  # one unique primary note, plus its repeat
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    assert len(client.requests) == 2
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    estimate = estimate_notes(ds, config, tmp_path)
    assert estimate["non_empty"] == 2 and estimate["unique"] == estimate["already_cached"] == 1
    assert estimate["estimated_calls"] == 0


def test_retry_then_single_split_and_uncoded_note(tmp_path: Path) -> None:
    ds = note_dataset(["A fair split.", "Always fail this note."])
    config = load_judge_config().model_copy(update={"consistency_share": 0})
    base = KeywordResponder()
    def responder(request):
        response = base(request)
        data = json.loads(response.content)
        bad = {note["id"] for note in request.context["notes"] if "Always fail" in note["note"]}
        data["labels"] = [row for row in data["labels"] if row["id"] not in bad]
        return replace(response, content=json.dumps(data))
    client = FakeChatClient(responder)
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    assert len(client.requests) == 5
    assert client.requests[0] is client.requests[1] is client.requests[2]
    assert [len(request.context["notes"]) for request in client.requests] == [2, 2, 2, 1, 1]
    assert result.labels.status.tolist() == ["coded", "uncoded"]
    assert "missing_or_extra_ids" in result.labels["flags"].iloc[1][0]
    assert result.costs["n_calls"] == 5


def test_quotes_and_id_reordering(tmp_path: Path) -> None:
    ds = note_dataset(["Vash has no one else.", "Pell offered 12."])
    config = load_judge_config().model_copy(update={"consistency_share": 0})
    base = KeywordResponder()
    def responder(request):
        response = base(request)
        labels = json.loads(response.content)["labels"]
        for row in labels:
            row.update(exclusion=True, exclusion_quote="missing phrase", fairness=False, fairness_quote="Pell",
                       recognition=True, recognition_quote=None)
        return replace(response, content=json.dumps({"labels": list(reversed(labels))}))
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=FakeChatClient(responder), dry_run=True))
    assert result.labels.exclusion.all()
    for flags in result.labels["flags"]:
        assert "quote_not_found:exclusion" in flags
        assert "quote_mismatch:fairness" in flags
        assert "quote_mismatch:recognition" in flags
    row = {label: False for label in LABELS} | {f"{label}_quote": None for label in LABELS}
    row.update(exclusion=True, exclusion_quote="NO   ONE ELSE")
    assert quote_flags(row, "Vash has no one else.") == []


def test_strict_validation_of_schema_and_ids() -> None:
    notes = [dict(id="x", note="A fair split.")]
    row = dict(id="x", **{label: False for label in LABELS}, **{f"{label}_quote": None for label in LABELS})
    assert validate_labels(json.dumps({"labels": [row]}), notes) == [row]
    for data in [{"labels": [row, row]}, {"labels": [{**row, "id": "other"}]},
                 {"labels": [{**row, "fairness": "yes"}]}, {"labels": [row], "extra": 1}]:
        with pytest.raises(ValueError):
            validate_labels(json.dumps(data), notes)
    schema = judge_response_format()["json_schema"]
    assert schema["name"] == "note_labels" and schema["strict"]
    assert not schema["schema"]["additionalProperties"]
    assert not schema["schema"]["properties"]["labels"]["items"]["additionalProperties"]


def test_kappa_reference_and_sampling() -> None:
    a = [True] * 25 + [False] * 25
    b = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    result = cohens_kappa(a, b)
    assert result["agreement"] == .7 and result["kappa"] == pytest.approx(.4)
    assert result["expected_agreement"] == .5
    assert cohens_kappa([True] * 4, [True] * 4)["kappa"] is None
    assert cohens_kappa([False] * 4, [False] * 4)["reason"] is not None
    ids = [f"n{i:010d}" for i in range(23)]
    assert consistency_ids(ids, .1, 4) == consistency_ids(list(reversed(ids)), .1, 4)
    assert len(consistency_ids(ids, .1, 4)) == ceil(.10 * 23)


def test_empty_notes_and_mode_separation(tmp_path: Path) -> None:
    ds = note_dataset(["", None])
    config = load_judge_config()
    client = FakeChatClient(KeywordResponder())
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    assert not client.requests and (result.labels.status == "empty").all()
    with pytest.raises(ValueError, match="mix"):
        asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=False))


def test_notes_cli_and_confirmation(report_logs: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(["estimate", str(report_logs), "--include-dry"]) == 0
    assert cli.main(["code", str(report_logs), "--include-dry", "--out", str(tmp_path), "--dry-run"]) == 0
    assert {"note_labels.csv", "consistency.json", "judge_costs.json"}.issubset({p.name for p in tmp_path.iterdir()})
    assert cli.main(["code", str(report_logs), "--out", str(tmp_path / "live"), "--live"]) == 1
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    def never_construct(*args, **kwargs):
        pytest.fail("Client constructed before confirmation")
    monkeypatch.setattr(cli, "OpenAIChatClient", never_construct)
    assert cli.main(["code", str(report_logs), "--out", str(tmp_path / "live"), "--include-dry", "--live"]) == 3
    assert "Reasoning makes actual cost uncertain" in capsys.readouterr().out
