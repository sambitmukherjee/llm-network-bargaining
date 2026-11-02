"""Version compatibility, concurrent fake calls, resumption and label comparison."""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random

import pandas as pd
import pytest

from llm_network_bargaining.fake_client import FakeChatClient
from llm_network_bargaining.model_client import FatalAPIError, Usage
from llm_network_bargaining.notes import LABELS, cli
from llm_network_bargaining.notes.compare import compare_labels
from llm_network_bargaining.notes.judge import (JUDGE_TEMPLATES, KeywordResponder, code_notes,
    estimate_notes, judge_prompt, load_judge_config, note_id)
from phase7_helpers import note_dataset, read_markdown_table


def test_both_exact_templates_and_five_changed_lines():
    notes = [dict(id='example', note='Secure 16 points.', network='hidden')]
    for version in ('judge-v1', 'judge-v2'):
        fixture = (Path('tests/golden') / f"JUDGE_{version[-2:].upper()}.txt").read_text().rstrip('\n')
        assert JUDGE_TEMPLATES[version] == fixture
        assert judge_prompt(notes, version) == fixture.replace('{NOTES_JSON}', json.dumps([dict(id='example', note='Secure 16 points.')]))
    assert judge_prompt(notes) == judge_prompt(notes, 'judge-v2')
    a, b = (JUDGE_TEMPLATES[version].splitlines() for version in ('judge-v1', 'judge-v2'))
    assert len(a) == len(b)
    assert [i for i, (old, new) in enumerate(zip(a, b)) if old != new] == [2, 5, 6, 8, 10]
    assert load_judge_config().judge_version == 'judge-v2'


@pytest.mark.parametrize('text,v1,v2', [
    ('Secure 16 points.', 'nd1f0245a57', 'n1372fe459f'),
    ('Offer 21 immediately to compete with Rulo and secure a deal.', 'nfac1c912af', 'nb191e32c11'),
])
def test_live_reference_note_ids(text, v1, v2):
    assert note_id(text, 'judge-v1') == v1
    assert note_id(text, 'judge-v2') == note_id(text) == v2


def test_versions_do_not_share_judgments(tmp_path):
    ds = note_dataset(['A fair split.', 'Secure 16 points.'])
    config = load_judge_config().model_copy(update={'consistency_share': 0})
    v1 = config.model_copy(update={'judge_version': 'judge-v1'})
    asyncio.run(code_notes(ds, v1, out=tmp_path, client=FakeChatClient(KeywordResponder()), dry_run=True))
    before = (tmp_path / 'judge_cache.jsonl').read_bytes()
    assert estimate_notes(ds, config, tmp_path)['already_cached'] == 0
    client = FakeChatClient(KeywordResponder())
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True))
    assert result.labels.status.eq('coded').all() and len(client.requests) == 1
    after = (tmp_path / 'judge_cache.jsonl').read_bytes()
    assert after.startswith(before) and len(after.splitlines()) == 4
    assert estimate_notes(ds, v1, tmp_path)['already_cached'] == 2


class DelayedFake(FakeChatClient):
    """Reply by note content after seeded delays, measuring active requests."""

    def __init__(self, *, fatal_at: int | None = None):
        super().__init__(KeywordResponder())
        self.active = self.peak = 0
        self.started = []
        self.finished = []
        self.fatal_at = fatal_at
        self.started_when_fatal = None
        self.active_at_start = []

    async def complete(self, request):
        """Allow out-of-order completion without making an SDK call."""
        index = len(self.started)
        ids = tuple(note['id'] for note in request.context['notes'])
        self.started.append(ids)
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.active_at_start.append(self.active)
        try:
            if index == self.fatal_at:
                await asyncio.sleep(.002)
                self.started_when_fatal = len(self.started)
                raise FatalAPIError('offline fatal test')
            rng = random.Random(int(hashlib.sha256('/'.join(ids).encode()).hexdigest()[:8], 16))
            await asyncio.sleep(.01 + rng.random() * .01)
            response = await super().complete(request)
            # Varied costs make an accidental completion-order sum detectable.
            usage = Usage(prompt_tokens=1 + rng.randrange(10000), completion_tokens=1 + rng.randrange(1000))
            self.finished.append(ids)
            return replace(response, usage=usage)
        finally:
            self.active -= 1


def test_concurrency_outputs_and_peak_in_flight(tmp_path):
    ds = note_dataset([f'A fair split number {i}.' for i in range(100)])
    config = load_judge_config().model_copy(update={'batch_size': 2})
    clients = []
    for concurrency in (1, 8):
        client = DelayedFake()
        clients.append(client)
        asyncio.run(code_notes(ds, config, out=tmp_path / str(concurrency), client=client, dry_run=True, concurrency=concurrency))
    assert clients[0].peak == 1
    assert 1 < clients[1].peak <= 8
    assert clients[1].started[:50] != clients[1].finished[:50]
    assert len(clients[1].started) == 60  # 50 primary batches, ten independent repeats
    assert 1 < max(clients[1].active_at_start[50:]) <= 8
    for name in ('note_labels.csv', 'consistency.json', 'judge_costs.json'):
        assert (tmp_path / '1' / name).read_bytes() == (tmp_path / '8' / name).read_bytes(), name


def test_fatal_error_finishes_in_flight_and_resumes_only_uncached(tmp_path):
    ds = note_dataset([f'Note {i}.' for i in range(100)])
    config = load_judge_config().model_copy(update={'batch_size': 2, 'consistency_share': 0})
    client = DelayedFake(fatal_at=1)
    out = tmp_path / 'resumed'
    with pytest.raises(FatalAPIError):
        asyncio.run(code_notes(ds, config, out=out, client=client, dry_run=True, concurrency=8))
    assert client.active == 0
    assert len(client.started) == client.started_when_fatal == 8
    cache = [json.loads(line) for line in (out / 'judge_cache.jsonl').read_text().splitlines()]
    cached = {row['note_id'] for row in cache}
    assert len(cached) == 14
    rerun = DelayedFake()
    asyncio.run(code_notes(ds, config, out=out, client=rerun, dry_run=True, concurrency=8))
    sent = {key for ids in rerun.started for key in ids}
    assert not sent & cached
    assert sent | cached == {note_id(text) for text in ds.turns.note}
    asyncio.run(code_notes(ds, config, out=tmp_path / 'whole', client=DelayedFake(), dry_run=True, concurrency=8))
    assert (out / 'note_labels.csv').read_bytes() == (tmp_path / 'whole/note_labels.csv').read_bytes()


def test_split_batches_obey_semaphore(tmp_path):
    ds = note_dataset([f'Fair {i}.' for i in range(12)])
    config = load_judge_config().model_copy(update={'batch_size': 4, 'consistency_share': 0})
    client = DelayedFake()
    base = client.responder
    def respond(request):
        response = base(request)
        if len(request.context['notes']) > 2:
            return replace(response, content='{}')
        return response
    client.responder = respond
    result = asyncio.run(code_notes(ds, config, out=tmp_path, client=client, dry_run=True, concurrency=2))
    assert result.labels.status.eq('coded').all() and client.peak == 2
    assert len(client.requests) == 15  # three parents retried thrice, six child halves


@pytest.mark.parametrize('calls,concurrency,minutes', [(425, 8, 18), (425, 1, 142), (0, 8, 0), (5, 8, 1)])
def test_estimated_time(calls, concurrency, minutes, tmp_path):
    config = load_judge_config().model_copy(update={'batch_size': 1})
    result = estimate_notes(note_dataset([f'Note {i}' for i in range(calls)]), config, tmp_path, concurrency=concurrency)
    assert result['estimated_calls'] == calls
    assert result['estimated_minutes'] == minutes


def test_invalid_concurrency_and_fatal_cli(report_logs, tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        cli.main(['estimate', str(report_logs), '--include-dry', '--concurrency', '0'])
    assert exc.value.code == 2
    monkeypatch.setattr(cli, 'load_dataset', lambda *args, **kwargs: note_dataset(['A fair split.']))
    monkeypatch.setattr(cli, 'FakeChatClient', lambda responder: DelayedFake(fatal_at=0))
    assert cli.main(['code', str(report_logs), '--out', str(tmp_path), '--dry-run']) == 1


def comparison_files(folder: Path) -> tuple[Path, Path]:
    """Four shared coded rows, one changed exclusion label, and excluded extras."""
    folder.mkdir(parents=True, exist_ok=True)
    base = [dict(episode_uid='episode', turn_index=i, round=1, phase=1, node='B', note=f'Note {i}', status='coded',
                 **{label: False for label in LABELS}) for i in range(4)]
    a, b = [dict(row) for row in base], [dict(row) for row in base]
    a[0]['exclusion'] = a[1]['exclusion'] = b[0]['exclusion'] = True
    paths = folder / 'labels_a.csv', folder / 'labels_b.csv'
    # A-only row and a shared row uncoded in B must not affect agreement.
    a += [dict(base[0], turn_index=4), dict(base[0], turn_index=5)]
    b += [dict(base[0], turn_index=5, status='uncoded')]
    pd.DataFrame(a).to_csv(paths[0], index=False)
    pd.DataFrame(b).to_csv(paths[1], index=False)
    return paths


def test_compare_expected_values_and_read_only(tmp_path, monkeypatch, capsys):
    paths = comparison_files(tmp_path)
    before = [path.read_bytes() for path in paths]
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert cli.main(['compare', *map(str, paths)]) == 0
    text = capsys.readouterr().out
    assert 'Matched rows: 4' in text
    rows = read_markdown_table(text, 'label')
    assert rows[0] == dict(label='exclusion', n='4', agreement='0.75', yes_rate_a='0.50', yes_rate_b='0.25', kappa='0.50')
    assert [row['kappa'] for row in rows[1:]] == ['—'] * 3
    changes = read_markdown_table(text, 'round')
    assert len(changes) == 1 and changes[0]['changes'] == 'exclusion: yes → no'
    assert [path.read_bytes() for path in paths] == before
    b = pd.read_csv(paths[1])
    b['episode_uid'] = 'different'
    b.to_csv(paths[1], index=False)
    assert cli.main(['compare', *map(str, paths)]) == 2


def test_compare_formats_round_and_phase_as_integers(tmp_path):
    paths = comparison_files(tmp_path)
    table = pd.read_csv(paths[0]).assign(round=12.0, phase=3.0)
    table.to_csv(paths[0], index=False)
    text = compare_labels(*paths)
    assert read_markdown_table(text, 'round') == [dict(
        round='12', phase='3', node='B', note='Note 1', changes='exclusion: yes → no')]


def test_report_note_tables_follow_config_selection(tmp_path):
    from llm_network_bargaining.analysis.report import _notes_section

    ds = note_dataset(['A fair split.', 'Secure 16 points.'])
    ds.dry_run = True
    config = load_judge_config().model_copy(update={'consistency_share': 1})
    asyncio.run(code_notes(ds, config, out=tmp_path, client=FakeChatClient(KeywordResponder()), dry_run=True))
    path = tmp_path / 'note_labels.csv'
    labels = pd.read_csv(path)
    labels.loc[0, ['episode_uid', 'config_name']] = ['pilot_full_map/line3/full_map/terra/000', 'pilot_full_map']
    labels.to_csv(path, index=False)
    text = _notes_section(path, ds)
    assert 'pilot_full_map' not in text
    prevalence = read_markdown_table(text, 'condition_key')
    assert len(prevalence) == 1 and prevalence[0]['n_notes'] == '1'
    repeats = read_markdown_table(text, 'label')
    assert all(row['n'] == '1' for row in repeats)
