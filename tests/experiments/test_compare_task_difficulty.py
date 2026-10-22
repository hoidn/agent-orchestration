"""Natural task-difficulty calibration contracts; scripted/offline only."""
import copy
import json

import pytest

from experiments.compare import pool, prepare, scan, summarize
from tests.experiments.test_compare_model_cap import guarded  # noqa: F401
from tests.experiments.compare_harness_support import world  # noqa: F401

LUNA = 'gpt-5.6-luna'
TERRA = 'gpt-5.6-terra'


def criterion():
    return {'purpose': 'calibration', 'calibration_kind': 'task_difficulty', 'anchors': [],
            'rubric': {**pool.DEFAULT_RUBRIC, 'reference': None},
            'arms': ['direct_task', 'terra_high'], 'runs_per_arm': {'direct_task': 2, 'terra_high': 2},
            'arm_models': {'direct_task': LUNA, 'terra_high': TERRA}, 'judges': [TERRA],
            'primary': [{'measure': 'terra_high.minus_control', 'op': '>=', 'value': 2}]}


def observations():
    rule = criterion()
    rows = {}; clones = {}; batch = []; ratings = {TERRA: {}}
    for arm in rule['arms']:
        for number in (1, 2):
            run = f'{arm}/run-{number}'
            cid = f'{arm}-{number}'
            rows[run] = {'arm': arm, 'outcome': 'completed', 'excluded': None, 'selected': None,
                         'calls': 1, 'wall_clock_sec': 1}
            clones[cid] = {'run': run, 'arm': arm, 'labels': ['final']}
            batch.append(cid)
            ratings[TERRA][cid] = {key: 1 if arm == 'direct_task' else 2 for key in summarize.CRITERIA}
    mapping = {'task': '/tasks/task', 'runs': rows, 'clones': clones, 'batches': [batch],
               'judges': {TERRA: {}}, 'rubric': rule['rubric']}
    return rule, mapping, ratings


def test_task_difficulty_explicitly_suppresses_all_projected_controls(tmp_path):
    (tmp_path / 'anchors').mkdir()
    (tmp_path / 'anchors/upstream.diff').write_text('retained artificial control')
    assert pool.anchor_paths(tmp_path, criterion()) == []
    assert pool.anchor_paths(tmp_path) == [tmp_path / 'anchors/upstream.diff']


@pytest.mark.parametrize('change', [
    {'purpose': 'comparison'}, {'anchors': ['upstream']}, {'calibration': {}},
    {'rubric': {**pool.DEFAULT_RUBRIC, 'reference': 'upstream'}},
])
def test_task_difficulty_rejects_contradictory_control_contract(tmp_path, change):
    with pytest.raises(SystemExit, match='task.difficulty'):
        pool.anchor_paths(tmp_path, {**criterion(), **change})


def test_compose_keeps_all_custom_final_patch_arms_in_one_blind_batch():
    usable = {arm: [(f'{arm}/{i}', {'arm': arm, 'patches': {'final': 'f.diff'}}) for i in (1, 2)]
              for arm in ('direct_task', 'terra_high')}
    batches = pool.compose(usable)
    assert len(batches) == 1
    assert sorted((rec['arm'], path, labels) for path, rec, labels in batches[0]) == sorted(
        (arm, f'{arm}/{i}', ['final']) for arm in usable for i in (1, 2))


def test_task_difficulty_preserves_four_scores_and_reuses_canonical_gap():
    rule, mapping, ratings = observations()
    summarize.validate_task_difficulty(rule, mapping, {}, ratings)
    _, values = summarize.score_values(mapping, ratings)
    rows = summarize.run_rows(mapping, values, {})
    measures = summarize.measures(rows)
    assert len(rows) == 4
    assert measures['terra_high.minus_control'] == 4
    assert summarize.verdict(rule, measures)['primary'][0]['met'] is True
    assert summarize.calibration({}, mapping, rule) is None


@pytest.mark.parametrize('damage', ['missing_run', 'extra_run', 'failed', 'excluded_run', 'missing_clone',
                                  'duplicate_clone', 'duplicate_run', 'missing_judge', 'excluded_judge',
                                  'missing_rating', 'invalid_rating', 'wrong_arm', 'wrong_counts'])
def test_task_difficulty_never_shrinks_its_declared_denominator(damage):
    rule, mapping, ratings = observations()
    excluded = {}
    if damage == 'missing_run':
        mapping['runs'].pop('direct_task/run-2')
    elif damage == 'extra_run':
        mapping['runs']['extra'] = copy.deepcopy(mapping['runs']['direct_task/run-1'])
    elif damage == 'failed':
        mapping['runs']['direct_task/run-2']['outcome'] = 'failed'
    elif damage == 'excluded_run':
        mapping['runs']['direct_task/run-2']['excluded'] = 'contaminated'
    elif damage == 'missing_clone':
        mapping['clones'].pop('direct_task-2')
    elif damage == 'duplicate_clone':
        mapping['batches'][0][-1] = mapping['batches'][0][0]
    elif damage == 'duplicate_run':
        mapping['clones']['direct_task-2']['run'] = 'direct_task/run-1'
    elif damage == 'missing_judge':
        ratings.clear()
    elif damage == 'excluded_judge':
        excluded[TERRA] = 'contaminated'
    elif damage == 'missing_rating':
        ratings[TERRA].pop('direct_task-2')
    elif damage == 'invalid_rating':
        ratings[TERRA]['direct_task-2']['root_cause'] = float('nan')
    elif damage == 'wrong_arm':
        mapping['clones']['direct_task-2']['arm'] = 'terra_high'
    elif damage == 'wrong_counts':
        rule['runs_per_arm']['direct_task'] = 1
    with pytest.raises(SystemExit, match='task.difficulty'):
        summarize.validate_task_difficulty(rule, mapping, excluded, ratings)



def test_task_difficulty_counts_and_gap_threshold_come_from_frozen_criterion():
    rule, mapping, ratings = observations()
    rule['runs_per_arm'] = {arm: 1 for arm in rule['arms']}
    rule['primary'][0]['value'] = 5
    for arm in rule['arms']:
        mapping['runs'].pop(f'{arm}/run-2')
        mapping['clones'].pop(f'{arm}-2')
        mapping['batches'][0].remove(f'{arm}-2')
        ratings[TERRA].pop(f'{arm}-2')
    summarize.validate_task_difficulty(rule, mapping, {}, ratings)
    _, values = summarize.score_values(mapping, ratings)
    measures = summarize.measures(summarize.run_rows(mapping, values, {}))
    assert summarize.verdict(rule, measures)['primary'][0]['met'] is False



def test_codex_luna_is_explicit_and_each_run_allowlist_is_exact(guarded):
    assert guarded('codex', ['--model', LUNA]).returncode == 2
    selected = guarded('codex', ['--model', LUNA], ORC_ALLOWED_CODEX_MODELS=LUNA)
    assert selected.returncode == 3, selected.stderr
    assert '--disable' in json.loads(selected.stdout)['args']
    assert guarded('codex', ['--model', TERRA], ORC_ALLOWED_CODEX_MODELS=LUNA).returncode == 2
    assert guarded('codex', ['--model', LUNA], ORC_ALLOWED_CODEX_MODELS=TERRA).returncode == 2
    assert guarded('codex', ['--model', 'gpt-6.1-sol'], ORC_ALLOWED_CODEX_MODELS='gpt-6.1-sol').returncode == 2
    assert guarded('codex', ['--model', LUNA, '--enable', 'multi_agent'],
                   ORC_ALLOWED_CODEX_MODELS=LUNA).returncode == 2


@pytest.mark.parametrize('expected,actual,forbidden', [(LUNA, LUNA, False), (LUNA, TERRA, True),
                                                     (TERRA, LUNA, True), (TERRA, TERRA, False)])
def test_scan_audits_the_exact_frozen_codex_model(tmp_path, expected, actual, forbidden):
    tree = tmp_path / 'tree'; tree.mkdir()
    home = tmp_path / 'home'
    path = home / '.codex/sessions/2026/10/22/rollout-x.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'type': 'session_meta', 'payload': {'cwd': str(tree)}}) + '\n' +
                    json.dumps({'type': 'turn_context', 'payload': {'model': actual}}) + '\n')
    hits = scan.find_hits(tmp_path / 'calls', tree, 0, home, {}, expected_codex_model=expected)
    assert bool(scan.model_policy(hits)) is forbidden


def test_generation_commands_and_scans_bind_the_input_codex_model(world, monkeypatch):
    weak = prepare.run_arm(world.task, 'direct_task', world.root, world.runtime,
                           sets=(f'model={LUNA}', 'effort=high'))
    strong = prepare.run_arm(world.task, 'terra_high', world.root, world.runtime,
                             sets=(f'model={TERRA}', 'effort=high'), spec=prepare.arm_spec('direct_task', world.runtime))
    observed = []
    monkeypatch.setattr(scan, 'find_hits', lambda *args, **kwargs: observed.append(kwargs) or [])
    for records, model in ((weak, LUNA), (strong, TERRA)):
        assert f'COMPARE_CODEX_MODELS={model}' in (records / 'command.sh').read_text()
        assert f'COMPARE_CODEX_MODELS={model}' in (records / 'resume.sh').read_text()
        prepare.scan(records, 'f' * 40, home=world.tmp / 'home')
    assert observed == [{'expected_codex_model': LUNA}, {'expected_codex_model': TERRA}]


def test_judge_command_and_scan_bind_the_exact_judge_model(tmp_path, monkeypatch):
    out = tmp_path / 'pool'; (out / 'records').mkdir(parents=True)
    mapping = {'judges': {TERRA: {'dir': 'judge', 'providers': 'codex.json'}}, 'batches': [['a', 'b']],
               'criterion_sha256': 'frozen', 'compare_base': 'base', 'runs': {}, 'main': '/main',
               'runtime': '/runtime', 'created_at': 0, 'rubric': criterion()['rubric']}
    (out / 'records/mapping.json').write_text(json.dumps(mapping))
    pool.write_score_inputs(out, mapping, 'intent', tmp_path / 'runtime')
    assert f'COMPARE_CODEX_MODELS={TERRA}' in (out / 'records' / f'score-{TERRA}.sh').read_text()
    observed = []
    monkeypatch.setattr(scan, 'find_hits', lambda *args, **kwargs: observed.append(kwargs) or [])
    pool.scan_judge(out, TERRA, 'f' * 40, home=tmp_path / 'home')
    assert observed == [{'expected_codex_model': TERRA}]


def test_shim_hands_off_codex_opt_in_and_nested_calls_keep_exact_policy(world, monkeypatch):
    from tests.experiments.compare_harness_support import call, skip_without_sandbox, start
    skip_without_sandbox()
    monkeypatch.setenv('COMPARE_CODEX_MODELS', LUNA)
    _, record = start(world, 'direct_task')
    done = call(world, record,
                'echo allowed=$ORC_ALLOWED_CODEX_MODELS; echo outer=${COMPARE_CODEX_MODELS-unset}; '
                f'codex --model {TERRA} </dev/null; echo nested-exit=$?',
                binary='codex', args=('--model', LUNA, 'exec'))
    assert done.returncode == 0, done.stderr
    assert f'allowed={LUNA}' in done.stdout
    assert 'outer=unset' in done.stdout
    assert 'nested-exit=2' in done.stdout
