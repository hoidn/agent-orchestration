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


def captured_run(tmp_path, arm='terra_high', outcome='failed', patch=b''):
    """Synthetic terminal attempt and native usage; no CLI or provider executes."""
    import hashlib
    run = tmp_path / arm / 'run-1'
    call = run / 'calls/1'; call.mkdir(parents=True)
    (call / 'prompt.txt').write_text('task')
    (call / 'patch-cand-1.diff').write_bytes(patch)
    tree = tmp_path / f'tree-{arm}'
    state = tree / 'cand-1/.orchestrate/runs'
    failure = {'code': 'provider_result_missing', 'message': 'no result.json'} if outcome == 'failed' else None
    record = {'arm': arm, 'outcome': outcome, 'failure': failure, 'selected': None, 'variant': None,
              'calls': 1, 'wall_clock_sec': 1, 'patches': {}, 'tree': str(tree), 'state_root': str(state),
              'candidates': [str(tree / 'cand-1')], 'scan': {'calls': 1, 'hits': [], 'verdict': None}}
    (run / 'record.json').write_text(json.dumps(record))
    terminal = {'record': 'terminal', 'outcome': outcome, **(failure or {'value': True})}
    memo = state / 'original/memo.jsonl'; memo.parent.mkdir(parents=True)
    memo.write_text(json.dumps({'record': 'started', 'identity': 'direct', 'attempt': 1,
                               'input_parts': {'prompt': 'sha256:' + hashlib.sha256(b'task').hexdigest()}}) + '\n' +
                    json.dumps(terminal) + '\n')
    model = LUNA if arm == 'direct_task' else TERRA
    native = tmp_path / f'native-{arm}.jsonl'
    native.write_text(json.dumps({'type': 'session_meta', 'payload': {'cwd': str(tree / 'cand-1')}}) + '\n' +
                      json.dumps({'type': 'turn_context', 'payload': {'model': model, 'effort': 'high'}}) + '\n')
    receipt = tmp_path / f'receipt-{arm}.json'
    receipt.write_text(json.dumps({'provider_calls': 1, 'native_session_paths': [str(native)], 'receipt_usage': [
        {'provider': 'codex', 'call_id': '1', 'status': 'complete', 'usage': [
            {'model': model, 'charge_tokens': {'input': 1}, 'provenance': {
                'model_source': 'turn_context.model', 'complete_native_transcript': True,
                'session_sha256': 'sha256:' + hashlib.sha256(native.read_bytes()).hexdigest()}}]}]}))
    return run, receipt, model


@pytest.mark.parametrize('outcome', ['completed', 'failed'])
def test_natural_intake_uses_original_raw_snapshot_and_keeps_delivery(tmp_path, outcome):
    run, receipt, model = captured_run(tmp_path, outcome=outcome)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    row, view = pool.natural_attempt(run, receipt, model)
    assert row['outcome'] == outcome
    assert row['failure'] == json.loads((run / 'record.json').read_text())['failure']
    assert view['patches'] == {'final': str(run / 'calls/1/patch-cand-1.diff')}
    assert pool.patch_bytes(run, view, 'final') == b''  # An actually captured empty patch is natural.
    assert all(p.read_bytes() == data for p, data in before.items())
    assert not list(tmp_path.rglob('result.json'))


@pytest.mark.parametrize('damage', ['no_patch', 'nonterminal', 'record_status', 'extra_call', 'no_receipt',
                                  'wrong_model', 'foreign_native', 'changed_native', 'zero_usage', 'excluded'])
def test_natural_intake_rejects_unproved_attempts(tmp_path, damage):
    run, receipt, model = captured_run(tmp_path)
    record = json.loads((run / 'record.json').read_text())
    if damage == 'no_patch':
        (run / 'calls/1/patch-cand-1.diff').unlink()
    elif damage == 'nonterminal':
        memo = next(tmp_path.rglob('memo.jsonl')); memo.write_text(memo.read_text().splitlines()[0] + '\n')
    elif damage == 'record_status':
        record['outcome'] = 'completed'
    elif damage == 'extra_call':
        (run / 'calls/2').mkdir()
    elif damage == 'no_receipt':
        receipt.unlink()
    elif damage == 'wrong_model':
        model = LUNA
    elif damage == 'foreign_native':
        record['tree'] = str(tmp_path / 'foreign')
    elif damage == 'changed_native':
        native = next(tmp_path.glob('native-*'))
        native.write_text(native.read_text() + json.dumps({'type': 'event_msg', 'payload': {}}) + '\n')
    elif damage == 'zero_usage':
        data = json.loads(receipt.read_text()); data['receipt_usage'][0]['usage'][0]['charge_tokens'] = {'input': 0}
        receipt.write_text(json.dumps(data))
    elif damage == 'excluded':
        record['scan']['verdict'] = {'verdict': 'contaminated', 'reason': 'another attempt'}
    (run / 'record.json').write_text(json.dumps(record))
    with pytest.raises((SystemExit, FileNotFoundError)):
        pool.natural_attempt(run, receipt, model)


def test_amended_task_difficulty_rechecks_capture_and_scores_failed_delivery(tmp_path):
    rule, mapping, ratings = observations()
    rule['natural_attempt_intake'] = 'terminal-single-call-patch-v1'
    changed = {}
    for index, (old, row) in enumerate(mapping['runs'].items()):
        run, receipt, model = captured_run(tmp_path / str(index), row['arm'],
                                           'failed' if index == 3 else 'completed')
        captured, _ = pool.natural_attempt(run, receipt, model)
        changed[old] = str(run)
        row.update(captured)
    mapping['runs'] = {changed[old]: row for old, row in mapping['runs'].items()}
    for clone in mapping['clones'].values():
        clone['run'] = changed[clone['run']]
    summarize.validate_task_difficulty(rule, mapping, {}, ratings)
    _, values = summarize.score_values(mapping, ratings)
    rows = summarize.run_rows(mapping, values, {})
    assert [r['outcome'] for r in rows].count('failed') == 1
    assert next(r for r in rows if r['outcome'] == 'failed')['failure']['code'] == 'provider_result_missing'
    assert summarize.measures(rows)['terra_high.runs'] == 2
    assert summarize.measures(rows)['terra_high.minus_control'] == 4
    next(iter(mapping['runs'].values()))['capture']['patch']['sha256'] = 'forged'
    with pytest.raises(SystemExit, match='task.difficulty'):
        summarize.validate_task_difficulty(rule, mapping, {}, ratings)


def test_natural_intake_opt_in_is_not_a_generic_failed_row_override():
    rule, mapping, ratings = observations()
    rule['natural_attempt_intake'] = 'terminal-single-call-patch-v1'
    mapping['runs']['terra_high/run-2']['outcome'] = 'failed'
    with pytest.raises(SystemExit, match='task.difficulty'):
        summarize.validate_task_difficulty(rule, mapping, {}, ratings)
