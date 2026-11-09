"""Verify freshly calculated results against compact, reviewed targets offline.

References are comparison evidence. Empirical estimates always originate in
the saved episode records; teaching inputs are explicitly hypothetical.
"""
from pathlib import Path
from itertools import combinations, permutations
from datetime import datetime, timezone
from io import StringIO
import csv
import hashlib
import json
import math

import numpy as np
import pandas as pd
import networkx as nx

from context import ROOT, PROJECT, OUT, DATA, CONFIGS, NETWORKS, study_roots
from llm_network_bargaining.analysis.predictions import class_predictions
from llm_network_bargaining.config import load_config, expand_conditions
from llm_network_bargaining.runlog import find_logs, read_log
from llm_network_bargaining.structure import max_deals
from llm_network_bargaining.theory import in_core, characteristic_function, balanced_outcome, core_bounds

REFERENCE_PATHS = {
    'section_6/class_earnings.csv': ('class_earnings', ['network_id', 'knowledge', 'node_class']),
    'section_6/hypothesis_summary.csv': ('hypotheses', ['window', 'test']),
    'section_6/h1_networks.csv': ('h1_constituents', ['window', 'network_id']),
    'section_6/effect_intervals.csv': ('effect_intervals', ['window', 'measure']),
    'section_6/h2_overall_both_windows.csv': ('overall_rmse', ['window', 'knowledge', 'predictor']),
    'section_6/rmse.csv': ('network_rmse', ['window', 'knowledge', 'scope', 'predictor']),
    'appendices/knowledge/power_use_summary.csv': ('power_use', ['window', 'network_id', 'knowledge']),
    'appendices/knowledge/power_use_differences.csv': ('power_use_differences', ['window', 'network_id']),
    'section_6/efficiency_counts.csv': ('efficiency', ['window']),
    'section_6/pair_splits.csv': ('pair_splits', ['window', 'knowledge']),
    'appendices/health/inefficient_rounds.csv': ('inefficient_rounds', ['episode_uid', 'round']),
    'appendices/statistics/null_audit.csv': ('null_audit', ['window', 'test']),
    'appendices/statistics/holm_steps.csv': ('holm_steps', ['window', 'family', 'test']),
    'appendices/theoretical_allocations.csv': ('theory', ['Network', 'Node class']),
    'appendices/individual/triangle_worked_example.csv': ('triangle_example', ['node']),
}
CHECKS = []


def read_json(path):
    return json.loads(path.read_text())


def claims():
    return read_json(ROOT / 'reference/claims.json')


def reference_frame(path, unused_keys=None):
    """Recover the original CSV scalar types without a frozen CSV dependency."""
    name, keys = REFERENCE_PATHS[path]  # Fail on an undeclared comparison.
    records = claims()['expected'][name]
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    stream.seek(0)
    result = pd.read_csv(stream)
    assert not result.duplicated(keys).any(), path
    return result, keys


def write_json(path, value):
    from llm_network_bargaining.analysis.stats import json_ready
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, allow_nan=False) + '\n')


def evidence(paths):
    """Bind a stage receipt to its current producers, references and outputs."""
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths))}


def check(name, passed, detail=None):
    CHECKS.append(dict(name=name, passed=bool(passed), detail=detail))
    if not passed:
        raise AssertionError((name, detail))


def equivalent(actual, expected, atol=1e-10):
    """Same structure and values, allowing only declared numeric tolerance."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            equivalent(actual[k], v, atol) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, (list, tuple)) and len(actual) == len(expected) and all(
            equivalent(a, e, atol) for a, e in zip(actual, expected))
    if expected is None:
        return actual is None or isinstance(actual, float) and math.isnan(actual)
    if isinstance(expected, bool):
        return isinstance(actual, (bool, np.bool_)) and actual == expected
    if isinstance(expected, (int, float)):
        if not isinstance(actual, (int, float, np.number)):
            return False
        return (math.isnan(float(expected)) and math.isnan(float(actual))) or math.isclose(
            float(actual), float(expected), abs_tol=atol, rel_tol=0)
    return actual == expected


def verify_inputs():
    with (ROOT / 'provenance/input_manifest.csv').open(newline='') as stream:
        manifest = list(csv.DictReader(stream))
    assert len(manifest) == len({r['path'] for r in manifest}) == 194
    for row in manifest:
        path = PROJECT / row['path']
        assert path.is_file() and path.stat().st_size == int(row['bytes']), row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], row['path']
    logs = list(find_logs(study_roots()))
    expected = {PROJECT / r['path'] for r in manifest if r['path'].startswith('runs/')}
    assert set(logs) == expected and len(logs) == 160
    write_json(OUT / 'input_verification.json', dict(
        files=194, study_episodes=160, all_hashes_match=True,
        inputs=[dict(path=r['path'], sha256=r['sha256']) for r in manifest],
        new_model_calls=False))
    print('194 declared repository inputs verified; exactly 160 study logs', flush=True)


def outside_options(net, points, matching):
    partner = {a: b for a, b in matching} | {b: a for a, b in matching}
    return {node: max([0] + [net.pie - points[other] for edge in net.edges if node in edge
                for other in edge if other != node and other != partner.get(node)]) for node in net.nodes}


def worked_examples():
    """Calculate D.1–D.4 using declared toy inputs and the tracked theory."""
    inputs = claims()['teaching']
    sequence = inputs['four_round_sequence']
    net = get_network('line3')
    assert all((a, b) in net.edges and sum(points) == net.pie
               and all(p >= 0 for p in points) for a, b, *points in sequence)
    values = np.array([r[2:] for r in sequence], dtype=float)
    participation = np.array([[node in r[:2] for node in net.nodes] for r in sequence])
    rates = participation.mean(axis=0)
    shares = np.array([values[participation[:, i], i].mean() / net.pie for i in range(3)])
    contributions = []
    for order in permutations(net.edges):
        graph = nx.Graph()
        graph.add_nodes_from(net.nodes)
        before = 0
        credit = {}
        for edge in order:
            graph.add_edge(*edge)
            worth = net.pie * len(nx.max_weight_matching(graph, maxcardinality=True))
            credit['–'.join(edge)] = worth - before
            before = worth
        contributions.append(dict(order=['–'.join(e) for e in order], credit=credit))
    link_credit = {label: np.mean([r['credit'][label] for r in contributions]) for label in contributions[0]['credit']}
    predictions = class_predictions('line3').set_index('node_class')
    four = get_network('line4')
    matching = (('A', 'B'), ('C', 'D'))
    equal = dict(zip(four.nodes, inputs['four_line_equal_payoffs']))
    options = outside_options(four, equal, matching)
    gains = {n: equal[n] - options[n] for n in four.nodes}
    toy = np.asarray(inputs['episode_toy_rows'], dtype=float)
    indices = np.asarray(inputs['bootstrap_indices_one_based']) - 1
    bootstrap = toy[indices].mean(axis=0)
    means = toy.mean(axis=0)
    prediction = np.array([predictions.loc['A|C', 'myerson'], predictions.loc['B', 'myerson']])
    result = dict(
        four_round_sequence=sequence, participation=dict(zip(net.nodes, rates)),
        conditional_share=dict(zip(net.nodes, shares)), earnings=dict(zip(net.nodes, values.mean(axis=0))),
        end_class_participation=float(rates[[0, 2]].mean()), end_class_conditional_share=float(shares[[0, 2]].mean()),
        pooled_end_conditional_share=float(values[:, [0, 2]].sum() / participation[:, [0, 2]].sum() / 24),
        link_contributions=contributions, link_credit=link_credit,
        position_from_link_credit={n: sum(link_credit['–'.join(e)] / 2 for e in net.edges if n in e) for n in net.nodes},
        equal_four_in_core=in_core(four, equal), equal_four_outside_options=options,
        equal_four_gains=gains, equal_four_balanced=all(gains[a] == gains[b] for a, b in matching),
        four_line_counterexample_in_core=in_core(four, dict(zip(four.nodes, inputs['four_line_core_counterexample']))),
        triangle_core_empty=core_bounds(get_network('triangle')) is None,
        triangle_total_worth=get_network('triangle').pie * max_deals(get_network('triangle')),
        triangle_pair_constraints_required_total=3 * get_network('triangle').pie / 2,
        three_line_core=[balanced_outcome(net)[n] for n in net.nodes],
        continuous_example_in_core=in_core(net, dict(zip(net.nodes, [1, 23, 0]))),
        continuous_deviation=inputs['continuous_deviation'],
        continuous_deviation_strictly_improves=inputs['continuous_deviation'][0] > 23 and inputs['continuous_deviation'][1] > 0 and sum(inputs['continuous_deviation']) == 24,
        integer_strict_improvement_min_total=(23 + 1) + (0 + 1),
        integer_strict_deviation_exists=any(q > 23 and 24 - q > 0 for q in range(25)),
        episode_toy_rows=inputs['episode_toy_rows'], bootstrap_rows=inputs['bootstrap_indices_one_based'],
        bootstrap_end_mean=float(bootstrap[0]), bootstrap_centre_mean=float(bootstrap[1]),
        rmse_squared_error_mean=float(np.mean((means - prediction) ** 2)),
        rmse=float(np.sqrt(np.mean((means - prediction) ** 2))))
    # Maximum differs from maximal on the four-line's central-only matching.
    central = (('B', 'C'),)
    result['four_line_central_is_maximal'] = not any(
        not set(e).intersection({n for edge in central for n in edge}) for e in four.edges)
    result['four_line_central_is_maximum'] = len(central) == max_deals(four)
    result['four_line_two_link_deal_frequencies'] = [1., 1.]
    result['four_line_two_link_fractions_of_deals'] = [1 / len(matching)] * len(matching)
    return result


def get_network(name):
    from llm_network_bargaining.networks import get_network as lookup
    return lookup(name)


def verify_narrative():
    expected = claims()
    cs = pd.read_csv(DATA / 'section_6/class_earnings.csv')
    h = pd.read_csv(DATA / 'section_6/hypothesis_summary.csv')
    effects = pd.read_csv(DATA / 'section_6/effect_intervals.csv')
    rmse = pd.read_csv(DATA / 'section_6/rmse.csv')
    history = pd.read_csv(DATA / 'appendices/individual/episode_nodes.csv')
    deals = pd.read_csv(DATA / 'appendices/individual/deal_offers.csv')
    no_deals = history.query("window=='primary' and n_deals==0")
    keys = list(expected['histories']['no_late_deal_cases'][0])
    actual_cases = no_deals[keys].sort_values(keys).to_dict('records')
    expected_case_frame = pd.DataFrame(expected['histories']['no_late_deal_cases'])
    expected_case_frame['episode_index'] = pd.to_numeric(expected_case_frame['episode_index'])
    expected_cases = expected_case_frame.sort_values(keys).to_dict('records')
    check('Eight late exclusion cases have the reviewed episode and agent identities', equivalent(actual_cases, expected_cases))
    full = history.query("window=='all'")
    check('All 600 agents trade during their full episode', len(full) == 600 and full.n_deals.gt(0).all())
    star = deals.query("network_id=='star4' and knowledge=='full_map' and round>=13")
    hub = np.where(star.maker.eq('H'), star.maker_points, star.recipient_points)
    leaf = np.where(star.maker.eq('H'), star.recipient_points, star.maker_points)
    check('All 120 star4 late deals split 23:1; 94 accepted offers were authored by leaves',
          len(star) == 120 and (hub == 23).all() and (leaf == 1).all() and star.maker.str.startswith('L').sum() == 94)
    winners = {}
    for net in ['line3', 'line4', 'line5', 'star3', 'star4', 'stem']:
        group = rmse[rmse.knowledge.eq('full_map') & rmse.scope.eq(net)]
        best = group.rmse.min()
        winners[net] = sorted(group.loc[np.isclose(group.rmse, best, atol=1e-10, rtol=0), 'predictor'])
    check('Full-map network-specific benchmark winners match the paper', winners == {
        'line3': ['balanced'], 'line4': ['equal_split'], 'line5': ['myerson'],
        'star3': ['balanced'], 'star4': ['balanced'], 'stem': ['equal_split']}, winners)
    line = cs[cs.network_id.eq('line5') & cs.knowledge.eq('full_map')].set_index('node_class')
    check('Five-line observed centre earns less than endpoints', line.loc['C', 'points_mean'] < line.loc['A|E', 'points_mean'])
    orderings = {}
    for predictor in ['equal_split', 'myerson', 'position_value', 'balanced']:
        orderings[predictor] = float(line.loc['C', predictor] - line.loc['A|E', predictor])
    check('Myerson and position reverse that ordering; equal split and balance tie it',
          orderings['myerson'] > 0 and orderings['position_value'] > 0
          and abs(orderings['equal_split']) < 1e-10 and abs(orderings['balanced']) < 1e-10, orderings)
    check('Myerson five-line centre and endpoint values are 7.2 and 5.2',
          np.allclose([line.loc['C', 'myerson'], line.loc['A|E', 'myerson']], [7.2, 5.2], atol=1e-10, rtol=0))
    core = []
    for uid, rows in history.query("window=='primary' and knowledge=='full_map' and network_id in ['star3','star4']").groupby('episode_uid'):
        net = get_network(rows.network_id.iloc[0])
        allocation = dict(zip(rows.node, rows.points_mean))
        blockers = [dict(coalition=sorted(s), worth=w, assigned=sum(allocation[n] for n in s))
                    for s, w in characteristic_function(net).items()
                    if sum(allocation[n] for n in s) < w - 1e-9]
        core.append(dict(episode_uid=uid, allocation=allocation, in_core=in_core(net, allocation), blocking_coalitions=blockers))
    check('All 20 full-map star episode vectors lie outside the continuous core',
          len(core) == 20 and all(not row['in_core'] and row['blocking_coalitions'] for row in core))
    hubs = cs.query("knowledge=='full_map'").set_index(['network_id', 'node_class'])
    increment = 100 * (hubs.loc[('star4', 'H'), 'share_mean'] - hubs.loc[('star3', 'H'), 'share_mean'])
    check('H3 final hub-share increment rounds to 0.42 percentage points', f'{increment:.2f}' == '0.42', increment)
    check('Four main Holm decisions agree across both windows',
          h.pivot(index='test', columns='window', values='decision').nunique(axis=1).eq(1).all())
    h2 = pd.read_csv(DATA / 'section_6/h2_overall_both_windows.csv')
    check('Myerson has the lowest overall H2 RMSE in both settings and both windows', all(
        group.sort_values('rmse').predictor.iloc[0] == 'myerson' for _, group in h2.groupby(['window', 'knowledge'])))
    powers = pd.read_csv(DATA / 'appendices/knowledge/power_use_summary.csv').query("window=='primary'")
    differences = pd.read_csv(DATA / 'appendices/knowledge/power_use_differences.csv').query("window=='primary'")
    means = powers.groupby('knowledge')['mean'].mean()
    difference = float(differences.difference.mean())
    check('H5 averages exactly six per-network contrasts with equal weights',
          len(differences) == 6 and np.isclose(means['full_map'] - means['own_links'], difference, atol=1e-14, rtol=0)
          and np.isclose(difference, effects.query("window=='primary' and measure=='H5_difference'").estimate.iloc[0], atol=1e-14, rtol=0))
    check('H5 setting means display as 0.5329 and 0.4339',
          f'{means["full_map"]:.4f}' == '0.5329' and f'{means["own_links"]:.4f}' == '0.4339')
    check('Line4 and stem H5 intervals include zero', all(
        row.ci_low < 0 < row.ci_high for row in differences[differences.network_id.isin(['line4', 'stem'])].itertuples()))
    worked = read_json(OUT / 'worked_examples.json')
    check('Teaching outcome averages follow node-then-class weighting',
          equivalent(worked['participation'], dict(A=.75, B=1., C=.25))
          and equivalent(worked['conditional_share'], dict(A=.25, B=.625, C=.75))
          and equivalent(worked['earnings'], dict(A=4.5, B=15., C=4.5))
          and worked['end_class_participation'] == worked['end_class_conditional_share'] == .5
          and worked['pooled_end_conditional_share'] == .375)
    check('Teaching link-credit and core/balance calculations hold',
          equivalent(worked['link_credit'], {'A–B': 12., 'B–C': 12.})
          and equivalent(worked['position_from_link_credit'], dict(A=6., B=12., C=6.))
          and worked['equal_four_in_core'] and not worked['equal_four_balanced']
          and equivalent(worked['equal_four_outside_options'], dict(A=0, B=12, C=12, D=0))
          and not worked['four_line_counterexample_in_core'] and worked['triangle_core_empty']
          and equivalent(worked['three_line_core'], [0, 24, 0]))
    check('Teaching matching, bootstrap, RMSE and integer/continuous examples hold',
          worked['four_line_central_is_maximal'] and not worked['four_line_central_is_maximum']
          and equivalent(worked['four_line_two_link_deal_frequencies'], [1., 1.])
          and equivalent(worked['four_line_two_link_fractions_of_deals'], [.5, .5])
          and np.isclose(worked['bootstrap_end_mean'], 7 / 3, rtol=0, atol=1e-14)
          and np.isclose(worked['bootstrap_centre_mean'], 58 / 3, rtol=0, atol=1e-14)
          and worked['rmse_squared_error_mean'] == 10 and np.isclose(worked['rmse'], np.sqrt(10))
          and worked['continuous_deviation_strictly_improves'] and not worked['integer_strict_deviation_exists']
          and worked['integer_strict_improvement_min_total'] == 25
          and worked['triangle_total_worth'] == 24 and worked['triangle_pair_constraints_required_total'] == 36)
    # Every defined balanced reference is checked against the actual equal-gains
    # equations, not merely assumed balanced because the selector is named so.
    balance_checks = []
    for name in NETWORKS:
        net = get_network(name)
        points = balanced_outcome(net)
        if points is None:
            check(name + ' balanced reference undefined only for empty triangle core', name == 'triangle')
            continue
        matches = [m for m in combinations(net.edges, max_deals(net)) if len({n for e in m for n in e}) == 2 * len(m)]
        supported = []
        for matching in matches:
            active = {n for e in matching for n in e}
            feasible = all(abs(points[a] + points[b] - net.pie) < 1e-9 for a, b in matching) and all(
                abs(points[n]) < 1e-9 for n in net.nodes if n not in active)
            options = outside_options(net, points, matching)
            equal_gains = all(abs((points[a] - options[a]) - (points[b] - options[b])) < 1e-9 for a, b in matching)
            if feasible and equal_gains:
                supported.append([list(e) for e in matching])
        check(name + ' selected balanced vector is in the core and satisfies equal gains on a supporting matching', in_core(net, points) and bool(supported))
        balance_checks.append(dict(network=name, points=points, supporting_matchings=supported))
    return dict(network_winners=winners, five_line_ordering_differences=orderings,
                star_episode_core_checks=core, balanced_reference_checks=balance_checks,
                h3_final_increment_percentage_points=increment, no_late_deal_cases=actual_cases,
                h5=dict(full_map=float(means['full_map']), own_links=float(means['own_links']), difference=difference))


def verify():
    CHECKS.clear()
    records = {name: read_json(OUT / name) for name in [
        'input_verification.json', 'replay_verification.json', 'analysis_verification.json',
        'figure_verification.json', 'table_verification.json', 'protocol_summary.json', 'provenance_verification.json']}
    check('All 194 input fingerprints match', records['input_verification.json']['all_hashes_match'])
    check('160 saved episode replays match', records['replay_verification.json']['episodes'] == 160 and records['replay_verification.json']['all_matched'])
    analysis = records['analysis_verification.json']
    for name in ['analysis_verification.json', 'table_verification.json', 'figure_verification.json']:
        check(name + ' producers, references and generated artifact hashes remain current', all(
            (ROOT / path).is_file() and hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == value
            for path, value in records[name]['artifacts'].items()))
    check('Every scientific comparison and independent null audit passed',
          analysis['passed'] == analysis['total'] == len(analysis['checks'])
          and all(row['passed'] for row in analysis['checks'])
          and {row['reference'] for row in analysis['comparisons']} == set(REFERENCE_PATHS))
    check('All 15 tables match, including eight empirical and five teaching/specification tables',
          records['table_verification.json']['tables_total'] == 15 and records['table_verification.json']['all_cells_match'])
    check('All six figures pass numerical/structural checks', records['figure_verification.json']['figures'] == 6 and records['figure_verification.json']['all_numeric_checks_passed'])
    check('Six retained pre-sprint fingerprints and run chronology match', records['provenance_verification.json']['version_fingerprints_match'])
    narrative = verify_narrative()
    with (ROOT / 'provenance/output_map.csv').open(newline='') as stream:
        routes = list(csv.DictReader(stream))
    groups = OUT / 'verification'
    group_records = {
        'N01': ['protocol_summary.json', 'protocol/verified_conditions.json'],
        'N02': ['data/appendices/statistics/null_audit.csv', 'data/appendices/statistics/holm_steps.csv', 'draw_streams.json'],
        'N03': ['data/section_6/efficiency_counts.csv', 'data/appendices/health/inefficient_rounds.csv'],
        'N04': ['data/section_6/class_earnings.csv'], 'N05': ['data/section_6/hypothesis_summary.csv', 'data/section_6/h1_networks.csv', 'data/section_6/effect_intervals.csv'],
        'N06': ['data/section_6/rmse.csv', 'verification/narrative_details.json'], 'N07': ['verification/narrative_details.json'],
        'N08': ['data/section_6/h2_overall_both_windows.csv', 'data/section_6/hypothesis_summary.csv'],
        'N09': ['data/appendices/knowledge/power_use_summary.csv', 'data/appendices/knowledge/power_use_differences.csv'],
        'N10': ['protocol_summary.json', 'replay_verification.json'], 'N11': ['verification/narrative_details.json', 'data/appendices/individual/triangle_worked_example.csv'],
        'N12': ['data/appendices/individual/deal_offers.csv'], 'N13': ['protocol/late_own_links.txt', 'protocol/verified_conditions.json', 'table_verification.json'],
        'N14': ['worked_examples.json', 'figure_d1_manifest.json'], 'N15': ['worked_examples.json', 'data/appendices/theoretical_allocations.csv'],
        'N16': ['worked_examples.json', 'verification/narrative_details.json', 'figures/figure_d2_coordinates.json'],
        'N17': ['worked_examples.json', 'data/appendices/statistics/null_audit.csv', 'data/appendices/statistics/holm_steps.csv'],
        'N18': ['provenance_verification.json'],
    }
    write_json(groups / 'narrative_details.json', narrative)
    output_routes = []
    for route in routes:
        row = dict(route)
        if row['kind'] == 'narrative_group' and row['id'] != 'N19':
            dependencies = group_records[row['id']]
            check(row['id'] + ' output-map artifacts exist', all((OUT / p).is_file() for p in dependencies))
            path = groups / (row['scope_group'] + '.json')
            write_json(path, dict(id=row['id'], scope_group=row['scope_group'], checked=True, outputs=dependencies,
                qualification='Checks calculate retained values; assumptions and author recollections remain qualifications, not empirical observations.'))
            row['actual_output'] = str(path.relative_to(ROOT))
        elif row['id'] == 'N19':
            row['actual_output'] = ''
            row['qualification'] = 'Literature, motivation, limitations and author accounts are non-computational context; no machine verification claimed.'
        else:
            relative = row['future_output'].removeprefix('results/')
            if row['kind'] == 'figure':
                relative += '.png'
            check(row['id'] + ' output-map artifact exists', (OUT / relative).is_file(), relative)
            row['actual_output'] = 'results/' + relative
        output_routes.append(row)
    write_json(groups / 'output_map.json', output_routes)
    stages = [dict(file=name, sha256=hashlib.sha256((OUT / name).read_bytes()).hexdigest()) for name in records]
    result = dict(checked_utc=datetime.now(timezone.utc).isoformat(), passed=len(CHECKS), total=len(CHECKS), checks=CHECKS,
        analysis_checks=analysis['total'], tables=15, figures=6, output_routes=len(routes),
        study_episodes=160, inputs=194, new_model_calls=False, scientific_root_seed=1,
        bootstrap_repetitions=2000, stages=stages,
        qualification='Current results-only checks. This receipt does not claim a fresh dependency installation or validation of subjective author accounts.')
    write_json(groups / 'receipt.json', result)
    print(f"Results-only verification complete: {len(CHECKS)} checks, {analysis['total']} scientific checks, 15 tables, six figures", flush=True)


if __name__ == '__main__':
    verify()
