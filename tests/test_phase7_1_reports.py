"""Phase 7.1 report layouts and regressions against the original bot outcomes."""

import json
from pathlib import Path
import re
import asyncio

import numpy as np
import pandas as pd
import pytest

from llm_network_bargaining.analysis import report
from llm_network_bargaining.analysis.benchmarks import benchmark_errors, ordering_accuracy
from llm_network_bargaining.analysis.data import load_dataset
from llm_network_bargaining.analysis.gate import STUDY_CONFIGS, pilot_gate
from llm_network_bargaining.analysis.metrics import condition_class_summary
from llm_network_bargaining.analysis.predictions import advantaged_class
from llm_network_bargaining.config import load_configs
from llm_network_bargaining.runner import plan_jobs, run_jobs
from phase7_helpers import read_markdown_table


MAIN_ROWS = '''| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.10 | 0.25 | 0.4335 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.02222 | 0.08889 | not supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.88 | 0.1667 | 0.4335 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.03 | 0.1445 | 0.4335 | not supported |
| H6 | not run | — | — | — | not run |'''
ROBUST_ROWS = '''| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.09 | 0.25 | 0.3333 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.01111 | 0.04444 | supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.95 | 0.1667 | 0.3333 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.05 | 0.02426 | 0.07279 | not supported |
| H6 | not run | — | — | — | not run |'''
PIVOT = '''| network_id | n_pairs | equal_split | myerson | position_value | balanced | degree | betweenness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| line3 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| line4 | 1 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| line5 | 3 | 0.83 | 0.67 | 0.67 | 0.83 | 0.50 | 0.33 |
| star3 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| star4 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| stem | 3 | 0.50 | 0.67 | 0.67 | 0.67 | 0.67 | 0.83 |'''
CLASS_HEADER = 'condition_key node_class n_episodes points_mean points_mean_ci_low points_mean_ci_high share_mean share_mean_ci_low share_mean_ci_high equal_split myerson position_value balanced'


def section(text: str, heading: str) -> str:
    """Read a section up to the next heading of the same or higher level."""
    content = text.split(heading + '\n', 1)[1]
    level = len(heading.split(' ', 1)[0])
    return re.split(rf'^#{{1,{level}}} ', content, maxsplit=1, flags=re.M)[0]


def tables(text: str) -> list[list[dict[str, str]]]:
    """Read every generated Markdown table without confusing escaped pipes."""
    chunks = re.findall(r'^\|[^\n]+\n\| ---[^\n]+\n(?:\|[^\n]+\n)*', text, re.M)
    return [read_markdown_table(chunk, re.split(r'(?<!\\)\|', chunk.splitlines()[0])[1].strip()) for chunk in chunks]


@pytest.fixture(scope='module')
def reports71(report_logs, tmp_path_factory):
    """Reuse the established 52-episode fixture; isolate 18 new stretch episodes."""
    root = tmp_path_factory.mktemp('reports71')
    stretch = root / 'stretch'
    configs = load_configs([Path('configs') / f'{name}.yaml' for name in STUDY_CONFIGS[2:]])
    # The saved reference outcomes and costs use 12-round stretch episodes.
    for index, config in enumerate(configs):
        settings = config.settings.model_copy(update={'rounds': 12})
        configs[index] = config.model_copy(update={'settings': settings})
    # Session fixture execution precedes function-scoped guards, so guard explicitly.
    import openai
    import socket
    def refuse(*args, **kwargs):
        raise AssertionError('Report fixtures must stay offline.')
    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(socket.socket, 'connect', refuse)
        guard.setattr(openai, 'AsyncOpenAI', refuse)
        guard.setattr(openai, 'OpenAI', refuse)
        summary = asyncio.run(run_jobs(plan_jobs(configs, max_episodes=2), out_root=stretch, dry_run_bot='aspiration'))
    assert summary.done == 18
    pilot = report.write_pilot_report([report_logs], root / 'pilot', include_dry=True)
    study = report.write_study_report([report_logs], root / 'study', include_dry=True)
    both = report.write_study_report([report_logs, stretch], root / 'both', include_dry=True)
    return dict(root=root, roots=[report_logs], stretch=stretch, pilot=pilot, study=study, both=both)


# Each parameter is a separate test of one binding table header.
HEADERS = [
    ('study', '## Provenance', 'condition_key episodes'),
    ('pilot', '## Outcomes', CLASS_HEADER),
    ('study', '## Class outcomes (second half)', CLASS_HEADER),
    ('study', '### Class outcomes without the last round', CLASS_HEADER),
    ('study', '### Invalid moves and reasons', 'condition_key model_alias n_asked n_invalid invalid_rate by_reason'),
    ('study', '### Rules quiz', 'condition_key model_alias n mean_score perfect_share q1_accuracy q2_accuracy q3_accuracy'),
    ('study', '### Attempts and failure categories', 'condition_key abandoned_episodes failed_attempts interrupted_attempts failed_by_category non_completed_cost_usd'),
    ('study', '### Costs and usage', 'config_name model_alias status dry_run calls prompt_tokens cached_tokens cache_write_tokens completion_tokens reasoning_tokens cost_usd'),
    ('study', '### Pair proposer share', 'condition_key n_episodes n_test proposer_share proposer_share_ci_low proposer_share_ci_high method p_value'),
    ('study', '### Triangle lock-in', 'condition_key n_episodes lock_in lock_in_ci_low lock_in_ci_high'),
    ('study', '### Efficiency', 'condition_key n_episodes efficiency efficiency_ci_low efficiency_ci_high'),
    ('pilot', '## Learning curves', 'network n_episodes w_early w_late gap within_0.1'),
    ('pilot', '### Power-use index', 'condition_key n_episodes pui pui_ci_low pui_ci_high'),
    ('study', '## Hypotheses', 'Hypothesis Data Statistic p Holm-adjusted_p Decision'),
    ('study', '### H1 secondary per-network analysis', 'network n mean ci_low ci_high p_value p_adjusted decision'),
    ('study', '### H1 per-network inputs', 'network n mean ci_low ci_high method alternative n_resamples statistic p_value'),
    ('study', '### H3 per-network inputs', 'network k n mean ci_low ci_high'),
    ('study', '### H4 per-network inputs', 'network n mean ci_low ci_high'),
    ('study', '### H5 per-network inputs', 'network full_map.n full_map.mean full_map.ci_low full_map.ci_high own_links.n own_links.mean own_links.ci_low own_links.ci_high difference difference_ci_low difference_ci_high'),
    ('both', '### H6 per-network inputs', 'network terra_hub.n terra_hub.mean terra_hub.ci_low terra_hub.ci_high luna_hub.n luna_hub.mean luna_hub.ci_low luna_hub.ci_high difference difference_ci_low difference_ci_high terra_hub.method terra_hub.alternative terra_hub.n_resamples terra_hub.statistic terra_hub.p_value luna_hub.method luna_hub.alternative luna_hub.n_resamples luna_hub.statistic luna_hub.p_value'),
    ('study', '### Overall RMSE and P(best)', 'predictor n_classes rmse ci_low ci_high p_best'),
    ('study', '### Per-network RMSE', 'condition_key predictor n_episodes n_classes rmse ci_low ci_high'),
    ('study', '### Distance to the core', 'network_id node_class observed core_min core_max distance'),
    ('study', '### Ordering accuracy (four benchmarks, degree and betweenness)', 'predictor n_pairs n_tied_observed correct accuracy ci_low ci_high'),
    ('study', '### Ordering accuracy (four benchmarks, degree and betweenness)', 'network_id n_pairs equal_split myerson position_value balanced degree betweenness'),
    ('study', '## Mixed models', 'predictor n_obs n_groups intercept intercept_se pred pred_se slot1_norm slot1_norm_se log_likelihood aic converged warnings error'),
]
HEADERS += [('pilot', heading, columns) for name, heading, columns in HEADERS
            if name == 'study' and heading in {
                '### Invalid moves and reasons', '### Rules quiz', '### Attempts and failure categories',
                '### Costs and usage', '### Pair proposer share', '### Triangle lock-in', '### Efficiency'}]


@pytest.mark.parametrize('name,heading,columns', HEADERS)
def test_binding_header(reports71, name, heading, columns):
    expected = columns.split()
    expected = [{'within_0.1': 'within 0.1', 'Holm-adjusted_p': 'Holm-adjusted p'}.get(item, item) for item in expected]
    content = section(reports71[name].read_text(), heading)
    assert '| ' + ' | '.join(expected) + ' |' in content


def test_registered_rows_gate_and_pivot(reports71):
    study, pilot = (reports71[name].read_text() for name in ('study', 'pilot'))
    assert MAIN_ROWS in section(study, '## Hypotheses')
    assert ROBUST_ROWS in section(study, '## Robustness')
    assert PIVOT in study
    assert 'left out: pair, triangle.' in study
    assert '| myerson | 15 | 1.33 | 1.23 | 1.99 | 1.00 |' in study
    assert '| equal_split | 10 | 0 | 7.5 | 0.75 | 0.75 | 0.75 |' in study
    assert '| minimum_study/line3/full_map/terra | 2 |' in study
    assert 'RMSE over the 15 classes where all four benchmarks are defined; left out: triangle (no balanced outcome).' in study
    assert '| G5: Game length | Own-links pilot window comparison | gap ≤ 0.1 on line3 and star3 → 12 rounds, otherwise 24 | 24 rounds | INFO |' in pilot
    assert '0 abandoned; failed share 0.00 | PASS |' in pilot
    assert 'Overall: **PASS**. Game length: **24 rounds**.' in pilot
    assert '| line3 | 2 | 0.31 | 0.70 | 0.40 | no |' in pilot
    assert '| star3 | 2 | 0.49 | 0.83 | 0.34 | no |' in pilot
    expected_step = 'Set `settings.rounds: 24` in the five study configs (minimum_study, own_links_arm, stretch_2c_sweep, stretch_2d_control, stretch_2f_h6), keep the pilot configs at 24, then run the minimum study.'
    assert pilot_gate(load_dataset(reports71['roots'], include_dry=True), reports71['roots']).next_steps == [expected_step]


def test_all_count_cells_and_cost_totals(reports71):
    for name, expected in [('study', (1830, 1044115, 23738)), ('pilot', (2074, 1581642, 27207)), ('both', None)]:
        text = reports71[name].read_text()
        for table in tables(text):
            for row in table:
                for column, value in row.items():
                    if report._is_count(column):
                        assert re.fullmatch(r'\d+|—', value), (column, value)
        costs = read_markdown_table(section(text, '### Costs and usage'), 'config_name')
        total = costs.pop()
        assert total['config_name'] == 'total'
        source = json.loads((reports71[name].parent / 'analysis/diagnostics.json').read_text())['costs']
        for column in report.COST_COLUMNS[4:]:
            assert float(total[column]) == pytest.approx(sum(float(row[column]) for row in costs), abs=.0001)
            assert total[column] == report._format(sum(row[column] for row in source), column=column)
        if expected:
            assert tuple(int(total[column]) for column in ('calls', 'prompt_tokens', 'completion_tokens')) == expected
        assert all(total[column] == '0' for column in ('cached_tokens', 'cache_write_tokens', 'reasoning_tokens'))
    with pytest.raises(ValueError, match='Non-integral count'):
        report.markdown_table(pd.DataFrame([dict(n=2.5)]))
    assert report._format({'not_a_neighbour': 1, 'bad_points': 2}) == 'bad_points: 2; not_a_neighbour: 1'
    assert report._format({}) == report._format([]) == '—'
    assert report._format(['minimum_study', 'own_links_arm']) == 'minimum_study, own_links_arm'
    assert report._format(.0001, column='non_completed_cost_usd') == '0.0001'
    mixed = read_markdown_table(section(reports71['study'].read_text(), '## Mixed models'), 'predictor')
    assert all(row['warnings'] == '—' for row in mixed)


def test_class_values_and_unrounded_cross_checks(reports71):
    ds = load_dataset(reports71['roots'], include_dry=True)
    text = reports71['study'].read_text()
    saved = json.loads((reports71['study'].parent / 'analysis/hypotheses.json').read_text())
    core = benchmark_errors(ds)['core_distances']
    expected_points = {'pair': [12.00], 'line3': [4.08, 15.83], 'line4': [11.50, 12.50],
                       'line5': [6.62, 14.33, 6.08], 'star3': [17.75, 2.08], 'star4': [18.25, 1.44],
                       'stem': [8.83, 13.58, 8.79], 'triangle': [8.00]}
    for window, heading in [('second_half', '## Class outcomes (second half)'), ('second_half_no_last', '### Class outcomes without the last round')]:
        summary = condition_class_summary(ds, window=window)
        summary = summary[summary.config_name.isin(['minimum_study', 'own_links_arm'])]
        parsed = [row for table in tables(section(text, heading)) for row in table]
        assert len(parsed) == len(summary)
        for row in parsed:
            source = summary[(summary.condition_key == row['condition_key']) & (summary.node_class == row['node_class'])].iloc[0]
            assert not row['condition_key'].startswith('pilot_')
            for column in report.CLASS_COLUMNS[2:]:
                assert row[column] == report._format(source[column], column=column)
        if window == 'second_half':
            for network, values in expected_points.items():
                actual = [float(row['points_mean']) for row in parsed if row['condition_key'] == f'minimum_study/{network}/full_map/terra']
                assert actual == values
        else:
            assert [float(row['points_mean']) for row in parsed if row['condition_key'] == 'minimum_study/line3/full_map/terra'] == [4.20, 15.60]
    summary = condition_class_summary(ds)
    for row in core:
        points = summary[(summary.config_name == 'minimum_study') & (summary.network_id == row['network_id']) & (summary.node_class == row['node_class'])].points_mean.item()
        assert points == pytest.approx(row['observed'], abs=1e-9)
    for network, values in saved['results']['H5']['per_network'].items():
        for config, knowledge in [('minimum_study', 'full_map'), ('own_links_arm', 'own_links')]:
            source = summary[(summary.config_name == config) & (summary.network_id == network) & (summary.node_class == advantaged_class(network)['node_class'])].iloc[0]
            assert (source.points_mean - 12) / (source.balanced - 12) == pytest.approx(values[knowledge]['mean'], abs=1e-9)


def test_selection_and_unknown_names(reports71, capsys):
    text = reports71['study'].read_text()
    assert '| Configs excluded | pilot_full_map, pilot_own_links |' in text
    assert 'No stretch configs in these logs.' in text
    assert all(not row.get('condition_key', '').startswith('pilot_') for table in tables(text) for row in table)
    out = reports71['root'] / 'selected'
    assert report.main(['study', *map(str, reports71['roots']), '--out', str(out), '--include-dry', '--configs', 'minimum_study', '--boot', '30']) == 0
    selected = (out / 'study_report.md').read_text()
    assert '| Configs excluded | own_links_arm, pilot_full_map, pilot_own_links |' in selected
    assert next(row for row in read_markdown_table(selected, 'Hypothesis') if row['Hypothesis'] == 'H5')['Data'] == 'not run'
    episodes = pd.read_csv(out / 'analysis/episodes.csv')
    assert set(episodes.config_name) == {'minimum_study'}
    assert report.main(['study', *map(str, reports71['roots']), '--out', str(out), '--include-dry', '--configs', 'nonexistent']) == 2
    output = capsys.readouterr().out
    assert 'Configs found: minimum_study, own_links_arm, pilot_full_map, pilot_own_links' in output


def test_exploratory_saved_results_and_determinism(reports71):
    path = reports71['both']
    text = path.read_text()
    roots = [*reports71['roots'], reports71['stretch']]
    ds = load_dataset(roots, include_dry=True)
    for config in STUDY_CONFIGS[2:]:
        content = section(text, f'### {config}')
        assert 'condition_key' in content
        summary = condition_class_summary(ds)
        summary = summary[summary.config_name == config]
        class_rows = [row for table in tables(content) for row in table if 'node_class' in row]
        assert len(class_rows) == len(summary)
        for row in class_rows:
            source = summary[(summary.condition_key == row['condition_key']) & (summary.node_class == row['node_class'])].iloc[0]
            for column in report.CLASS_COLUMNS[2:]:
                assert row[column] == report._format(source[column], column=column)
        if config == 'stretch_2f_h6':
            assert 'Ranking:' not in content and '![observed' not in content
            continue
        for stem, function in [('benchmark_errors', benchmark_errors), ('ordering_accuracy', ordering_accuracy)]:
            saved = json.loads((path.parent / 'analysis' / f'{stem}_{config}.json').read_text())
            assert saved == function(ds, config=config)
            heading = '#### Benchmark errors' if stem == 'benchmark_errors' else '#### Ordering accuracy'
            columns = report.RMSE_COLUMNS if stem == 'benchmark_errors' else report.ORDER_COLUMNS
            rows = read_markdown_table(section(content, heading), 'predictor')
            for row, source in zip(rows, saved['overall']):
                assert row == {column: report._format(source[column], column=column) for column in columns}
        assert 'Ranking:' in content and f'figures/observed_vs_predicted_{config}.png' in content
    tests = json.loads((path.parent / 'analysis/hypotheses.json').read_text())
    assert tests['results']['H6']['status'] == 'run' and len(tests['family']) == 5
    second = report.write_study_report(roots, reports71['root'] / 'repeat', include_dry=True)
    assert path.read_bytes() == second.read_bytes()
    for svg in (path.parent / 'figures').glob('*.svg'):
        assert svg.read_bytes() == (second.parent / 'figures' / svg.name).read_bytes()


def test_no_shared_benchmarks_missing_gate_and_count_checks():
    assert report._rmse_section(dict(overall=[])) == ['No classes where all four benchmarks are defined.']
    from llm_network_bargaining.analysis.data import dataset_from_tables
    gate = pilot_gate(dataset_from_tables(), [])
    assert 'missing data | INFO |' in report.gate_table(gate)
    values = {'per_network': {'line3': {'full_map': {'n': 3}, 'own_links': {'n': 2}, 'n_a': 9, 'n_b': 3}}}
    with pytest.raises(AssertionError):
        report._group_inputs(values, 'H5')
    h6 = {'per_network': {'line3/terra_hub': {'n': 3}, 'line3/luna_hub': {'n': 2}},
          'assignment_differences': {'line3': {'n_a': 9, 'n_b': 3}}}
    with pytest.raises(AssertionError):
        report._group_inputs(h6, 'H6')


@pytest.mark.parametrize('balanced_rmse,ranking', [
    (2.5, 'position_value, equal_split = balanced, myerson'),
    (np.nextafter(2.5, np.inf), 'position_value, equal_split, balanced, myerson'),
])
def test_rmse_ranking_groups_only_exact_ties_in_predictor_order(balanced_rmse, ranking):
    errors = dict(
        overall=[dict(predictor=name, rmse=value, n_classes=2, ci_low=1, ci_high=4, p_best=0)
                 for name, value in [('balanced', balanced_rmse), ('myerson', 3),
                                     ('equal_split', 2.5), ('position_value', 1)]],
        core_distances=[dict(network_id='line3')], overall_networks=['line3'],
        ranking=['position_value', 'balanced', 'equal_split', 'myerson'], best='position_value')
    assert report._rmse_section(errors)[-1] == f'Ranking: {ranking}. Best benchmark: **position_value**.'


def test_no_numbered_future_protocol_references():
    phrase = 'Phase ' + '8'
    paths = [Path('README.md'), *Path('src').rglob('*.py'), *Path('configs').rglob('*.yaml'), *Path('tests').rglob('*.py')]
    assert all(phrase not in path.read_text() for path in paths)


def test_notebook_with_stretch_executes(reports71, tmp_path, monkeypatch):
    notebook = report.write_notebook(tmp_path / 'analysis.ipynb')
    original = notebook.read_bytes()
    monkeypatch.setenv('LNB_ROOTS', json.dumps([str(reports71['roots'][0]), str(reports71['stretch'])]))
    monkeypatch.setenv('LNB_INCLUDE_DRY', '1')
    monkeypatch.setenv('LNB_OUT', str(tmp_path / 'executed'))
    namespace = {'display': lambda value: None}
    for cell in json.loads(original)['cells']:
        if cell['cell_type'] == 'code':
            assert cell['outputs'] == [] and cell['execution_count'] is None
            exec(compile(''.join(cell['source']), str(notebook), 'exec'), namespace)
    assert len(list((tmp_path / 'executed/figures').glob('*.png'))) == 7
    assert notebook.read_bytes() == original
