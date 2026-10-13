"""Independent memo prefixes obey their structured program order."""

from pathlib import Path
import json

import pytest

from orchestrator.workflow.evaluated import runtime, views, effect_inputs
from orchestrator.workflow.evaluated.memo import MemoError
from orchestrator.workflow.evaluated.machine import site_classes, evaluate_closed_program
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.workflow_evaluated_parallel_helpers import (
    COMMAND, RUN_REF, replay_case, mapped, worker, command_rows, completed_rows, write_rows, effect,
    coordinator_rows, site_index,
)


def preflight(authority):
    return runtime._replay_resume_prefix(authority, {}, run_id='run-1',
        workspace=authority.run_root.parents[2], provider_io=None,
        site_classes=site_classes(authority.program))


def test_completed_interleaved_items_replay_in_input_order_without_dispatch(tmp_path, monkeypatch):
    with replay_case(tmp_path) as authority:
        snapshot = write_rows(authority, completed_rows(authority))
        before = authority.memo_path.read_bytes()
        monkeypatch.setattr(runtime, 'execute_pure_run', lambda *a, **k: pytest.fail('redispatch'))
        for _ in range(2):
            assert runtime.execute_pure_resume(authority, {}, run_id='run-1', workspace=tmp_path) == (0, [0, 1, 2, 3])
        assert views._replay(authority, snapshot) == ([0, 1, 2, 3], None, True)
        assert authority.memo_path.read_bytes() == before


def test_discovery_visits_both_partial_item_prefixes(tmp_path, monkeypatch):
    body = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    with replay_case(tmp_path, mapped('(call worker :repo repo)'), declarations=worker(body)) as authority:
        rows = [*command_rows(authority, 1), *command_rows(authority, 0)]
        rows += [command_rows(authority, 1, site=1)[0], command_rows(authority, 0, site=1)[0]]
        snapshot = write_rows(authority, rows)
        assert preflight(authority)[2] == 2
        checked = []
        monkeypatch.setattr(effect_inputs, '_check_resume_boundary', lambda *args, **kwargs: checked.append(args[4]))
        result = preflight(authority)
        assert result[2] == 2 and result[-1] is True
        assert {effect(authority, i, site=1)[0] for i in range(2)} <= set(checked)
        assert views._replay(authority, snapshot)[2] is False


@pytest.mark.parametrize('corruption', ['gap', 'reverse', 'overlap', 'unknown', 'duplicate', 'unreachable', 'postmap'])
def test_structurally_impossible_parallel_evidence_is_rejected(tmp_path, corruption):
    body = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    outer = mapped('(call worker :repo repo)')
    if corruption == 'unreachable':
        body = f'(if true {COMMAND} {COMMAND.replace("fetch", "inc")})'
    if corruption == 'postmap':
        outer = f'(let* ((batch {outer})) (command-result check :argv ("python" "probe.py") :returns Int))'
    with replay_case(tmp_path, outer, declarations=worker(body), result='Int' if corruption == 'postmap' else 'List[Int]') as authority:
        first = command_rows(authority, 0, site=site_index(authority, boundary='fetch'))
        second = command_rows(authority, 0, site=site_index(authority, boundary='inc'))
        choices = {
            'gap': [*second], 'reverse': [*second, *first],
            'overlap': [first[0], second[0], first[1], second[1]],
            'unknown': [*command_rows(authority, 9, operand='x')],
            'duplicate': [*first, *first], 'unreachable': [*second],
        }
        rows = choices.get(corruption)
        if corruption == 'postmap':
            rows = [*command_rows(authority, 0, site=site_index(authority, boundary='check')), *first, *second]
        with pytest.raises(MemoError, match='memo_inconsistent'):
            snapshot = write_rows(authority, rows)
            views._replay(authority, snapshot)


def test_input_divergence_uses_journal_order_after_all_sibling_discovery(tmp_path, monkeypatch):
    with replay_case(tmp_path) as authority:
        write_rows(authority, completed_rows(authority))
        checked = []

        def diverge(*args, **kwargs):
            checked.append(args[3])
            raise effect_inputs._EffectInputDiverged(args[3], 'changed')

        monkeypatch.setattr(effect_inputs, '_replay_committed_effect', diverge)
        with pytest.raises(effect_inputs._EffectInputDiverged, match=r'\[2\]'):
            preflight(authority)
        assert checked == [effect(authority, 2)[0]]


def test_pending_must_not_repeat_frontier_cannot_hide_committed_sibling(tmp_path, monkeypatch):
    binding = ExternalToolBinding(name='fetch', stable_command=('python', 'probe.py'),
        closure=('probe.py',), must_not_repeat=True)
    with replay_case(tmp_path, boundaries={'fetch': binding}) as authority:
        write_rows(authority, [command_rows(authority, 0)[0], *command_rows(authority, 1)])
        checked = []
        original = effect_inputs._replay_committed_effect

        def validate(*args, **kwargs):
            checked.append(args[3])
            return original(*args, **kwargs)

        monkeypatch.setattr(effect_inputs, '_replay_committed_effect', validate)
        with pytest.raises(effect_inputs._PreflightRefusal, match='must not be repeated'):
            preflight(authority)
        assert checked == [effect(authority, 1)[0]]


def test_views_evaluate_workspace_data_without_cwd_or_closure_resolution(tmp_path, monkeypatch):
    with replay_case(tmp_path) as authority:
        write_rows(authority, completed_rows(authority))
        for path in tmp_path.glob('*.orc'):
            path.unlink()
        (tmp_path / 'probe.py').unlink()

        def forbidden(*args, **kwargs):
            pytest.fail('source-free view resolved filesystem input or cwd')

        monkeypatch.setattr(Path, 'resolve', forbidden)
        monkeypatch.setattr(Path, 'is_dir', forbidden)
        monkeypatch.setattr(effect_inputs, '_resolve_effect_input', forbidden)
        view = views.load_evaluated_view(authority.run_root)
        assert view['workflow_outputs'] == [0, 1, 2, 3]


def test_live_parallel_execution_is_still_refused(tmp_path):
    with replay_case(tmp_path) as authority:
        with pytest.raises(ValueError, match='unsupported body kind'):
            evaluate_closed_program(authority.program, {})


@pytest.mark.parametrize('orphan', [False, True])
def test_pure_fault_in_one_item_does_not_hide_sibling_or_orphan_evidence(tmp_path, monkeypatch, orphan):
    body = f'''(let* ((divisor (if (= repo "a") 0.0 1.0)))
        (if (= repo "a") (/ 1.0 divisor) {COMMAND.replace('Int', 'Float')}))'''
    with replay_case(tmp_path, mapped('(call worker :repo repo)'),
            declarations=worker(body, result='Float'), result='List[Float]') as authority:
        rows = [*command_rows(authority, 1, value=1.0)]
        if orphan:
            rows.append(command_rows(authority, 0)[0])
        snapshot = write_rows(authority, rows)
        if orphan:
            with pytest.raises(MemoError, match='pending start is unreachable'):
                views._replay(authority, snapshot)
            return
        checked = []
        original = effect_inputs._replay_committed_effect

        def validate(*args, **kwargs):
            checked.append(args[3])
            return original(*args, **kwargs)

        monkeypatch.setattr(effect_inputs, '_replay_committed_effect', validate)
        with pytest.raises(ValueError, match='divisor is zero'):
            preflight(authority)
        assert checked == [effect(authority, 1)[0]]
        assert views._replay(authority, snapshot)[2] is False


def test_failed_terminal_reaches_all_retry_frontiers(tmp_path):
    with replay_case(tmp_path) as authority:
        start = command_rows(authority, 0)[0]
        rows = [start, dict(record='failed', identity=start['identity'], attempt=1,
            code='command_failed', exit_info={}), *command_rows(authority, 1),
            dict(record='terminal', outcome='failed', code='command_failed', message='failed item')]
        snapshot = write_rows(authority, rows)
        assert preflight(authority)[2] == 1
        assert views._replay(authority, snapshot)[2] is False
        assert views.load_evaluated_view(authority.run_root)['status'] == 'failed'


def test_historical_failed_successor_start_does_not_constrain_active_retry(tmp_path):
    body = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    with replay_case(tmp_path, mapped('(call worker :repo repo)'), declarations=worker(body)) as authority:
        old = command_rows(authority, 0, site=1)[0]
        rows = [old, dict(record='failed', identity=old['identity'], attempt=1, code='failed', exit_info={}),
            *command_rows(authority, 0), *command_rows(authority, 0, site=1, attempt=2)]
        snapshot = write_rows(authority, rows)
        assert views._replay(authority, snapshot)[2] is False
        assert preflight(authority)[2] == 2


def test_c8_invalidated_starts_do_not_constrain_retried_parallel_item(tmp_path):
    body = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    with replay_case(tmp_path, mapped('(call worker :repo repo)'), declarations=worker(body)) as authority:
        rows = [*command_rows(authority, 1), *command_rows(authority, 1, site=1),
                *command_rows(authority, 0), *command_rows(authority, 0, site=1)]
        before = write_rows(authority, rows)
        anchor = before.active_commits[effect(authority, 0)[0]].offset
        rows.append(dict(record='invalidated', from_commit=anchor, time=2.0))
        rows.extend(command_rows(authority, 0, attempt=2))
        rows.extend(command_rows(authority, 0, site=1, attempt=2))
        after = write_rows(authority, rows)
        assert len(after.active_commits) == 4
        assert after.active_commits[effect(authority, 1)[0]] == before.active_commits[effect(authority, 1)[0]]
        assert views._replay(authority, after)[2] is False
        assert preflight(authority)[2] == 4


def test_postmap_start_waits_for_every_item_even_when_all_later_commit(tmp_path):
    body = f'(let* ((batch {mapped()})) (command-result check :argv ("python" "probe.py") :returns Int))'
    with replay_case(tmp_path, body, result='Int') as authority:
        post = command_rows(authority, 0, site=site_index(authority, boundary='check'))
        rows = [post[0]]
        for index in range(4):
            rows.extend(command_rows(authority, index, site=site_index(authority, boundary='fetch')))
        rows.append(post[1])
        snapshot = write_rows(authority, rows)
        with pytest.raises(MemoError, match='structured predecessor'):
            views._replay(authority, snapshot)


def test_serial_pending_start_keeps_existing_order_policy(tmp_path):
    body = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    with replay_case(tmp_path, '(call worker :repo "a")', declarations=worker(body), result='Int') as authority:
        first = command_rows(authority, 0)
        second = command_rows(authority, 0, site=1)
        snapshot = write_rows(authority, [first[0], second[0], first[1]])
        assert preflight(authority)[2] == 1
        assert views._replay(authority, snapshot) == (None, second[0]['identity'], False)


def test_nested_maps_and_calls_preserve_independent_inner_prefix_order(tmp_path):
    inner = mapped('(call leaf :repo child)', source='(list "a" "b")', label='child')
    declarations = worker(inner, result='List[Int]') + f'(defworkflow leaf ((repo String)) -> Int {COMMAND})'
    with replay_case(tmp_path, mapped('(call worker :repo repo)', source='(list "a" "b")'),
            declarations=declarations, result='List[List[Int]]') as authority:
        rows = []
        for outer, inner_index in [(1, 1), (0, 1), (1, 0), (0, 0)]:
            rows.extend(command_rows(authority, inner_index, indices=[outer, inner_index]))
        rows.append(dict(record='terminal', outcome='completed', value=[[0, 1], [0, 1]]))
        snapshot = write_rows(authority, rows)
        assert views._replay(authority, snapshot) == ([[0, 1], [0, 1]], None, True)
        assert preflight(authority)[2] == 4


@pytest.mark.parametrize('continuation', ['item', 'postmap'])
@pytest.mark.parametrize('evidence', ['start', 'commit'])
def test_late_coordinator_settlement_cannot_authorize_earlier_continuation(tmp_path, continuation, evidence):
    body = f'(let* ((r {RUN_REF}) (n {COMMAND})) n)' if continuation == 'item' else f'(let* ((r {RUN_REF})) r.value)'
    outer = mapped('(call worker :repo repo)', source='(list "a")')
    if continuation == 'postmap':
        outer = f'(let* ((batch {outer})) (command-result check :argv ("python" "probe.py") :returns Int))'
    with replay_case(tmp_path, outer, declarations=worker(body),
            result='Int' if continuation == 'postmap' else 'List[Int]') as authority:
        rows = coordinator_rows(authority, site=site_index(authority, kind='run_ref'))
        successor = command_rows(authority, 0, site=site_index(authority, kind='command'))
        rows.extend(successor if evidence == 'commit' else [successor[0]])
        rows.append(dict(record='settled', identity=rows[0]['identity'], attempt=1, by='settle'))
        snapshot = write_rows(authority, rows)
        with pytest.raises(MemoError, match='structured predecessor'):
            views._replay(authority, snapshot)


def test_unsettled_last_coordinator_retains_settling_view(tmp_path):
    with replay_case(tmp_path, mapped('(call worker :repo repo)', source='(list "a")'),
            declarations=worker(f'(let* ((r {RUN_REF})) r.value)')) as authority:
        snapshot = write_rows(authority, coordinator_rows(authority))
        value, next_effect, halted = views._replay(authority, snapshot)
        view = views._view(authority, snapshot, None, next_effect, halted, True)
        assert value == [0] and halted is True
        assert view['status'] == 'settling'
        assert next(iter(view['steps'].values()))['status'] == 'settling'
        assert view['workflow_outputs'] is None


def test_unsettled_coordinator_does_not_hide_later_sibling_divergence(tmp_path, monkeypatch):
    body = f'(if (= repo "a") (let* ((r {RUN_REF})) r.value) {COMMAND})'
    with replay_case(tmp_path, mapped('(call worker :repo repo)'), declarations=worker(body)) as authority:
        write_rows(authority, [*coordinator_rows(authority), *command_rows(authority, 1, site=1)])
        checked = []

        def validate(*args, **kwargs):
            checked.append(args[3])
            if args[1]['class'] == 'command':
                raise effect_inputs._EffectInputDiverged(args[3], 'later sibling changed')
            from orchestrator.workflow.evaluated.replay import committed_value
            return committed_value(args[0], args[1], args[5], args[3])

        monkeypatch.setattr(effect_inputs, '_replay_committed_effect', validate)
        monkeypatch.setattr(runtime, 'reconcile_evaluated_run_ref', lambda *a, **k: pytest.fail('reconcile before C7'))
        assert runtime.execute_pure_resume(authority, {}, run_id='run-1', workspace=tmp_path) == (2, None)
        assert checked == [effect(authority, 0)[0], effect(authority, 1, site=1)[0]]


def test_public_report_reads_parallel_authority_after_source_disappears(tmp_path):
    from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
    with replay_case(tmp_path) as authority:
        write_rows(authority, completed_rows(authority))
        for path in tmp_path.glob('*.orc'):
            path.unlink()
        (tmp_path / 'probe.py').unlink()
        before = _tree_bytes(tmp_path)
        report = _cli(tmp_path, 'report', '--run-id', 'run-1', '--runs-root',
            str(authority.run_root.parent), '--format', 'json')
        assert report.returncode == 0, report.stderr
        payload = json.loads(report.stdout)
        assert payload['run']['workflow_outputs'] == [0, 1, 2, 3]
        assert payload['progress']['completed'] == 4
        assert _tree_bytes(tmp_path) == before


def test_map_result_retains_pure_workspace_dependencies(tmp_path):
    first = '(command-result fetch :argv ("python" "probe.py" "seed") :returns String)'
    batch = mapped('(call worker :repo repo)').replace('(string/concat repo "/work")', 'root')
    body = f'(let* ((root {first}) (batch {batch})) batch)'
    with replay_case(tmp_path, body, declarations=worker('7')) as authority:
        snapshot = write_rows(authority, command_rows(authority, 0, value='seed', operand='seed'))
        results = []

        def evaluate(program, inputs, **kwargs):
            result = evaluate_closed_program(program, inputs, **kwargs)
            results.append(result)
            return result

        assert views._replay(authority, snapshot, evaluate=evaluate) == ([7, 7, 7, 7], None, True)
        assert results[0].dependencies == {effect(authority, 0)[0]}


@pytest.mark.parametrize('kind', ['none', 'pure', 'effectful', 'empty'])
@pytest.mark.parametrize('completed', [False, True])
def test_serial_tail_after_map_keeps_historical_start_policy(tmp_path, kind, completed):
    sequential = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    declarations = worker(sequential) + '(defworkflow pure-item ((repo String)) -> Int 7)'
    declarations += '(defproc empty () -> List[String] :effects () :lowering inline (list))'
    tail = '(call worker :repo "a")'
    item = COMMAND.replace('fetch', 'check') if kind == 'effectful' else '(call pure-item :repo repo)'
    source = 'repos' if kind == 'empty' else '(list "a")'
    body = tail if kind == 'none' else f'(let* ((batch {mapped(item, source=source)})) {tail})'
    if kind == 'empty':
        body = f'(let* ((repos (empty))) {body})'
    with replay_case(tmp_path, body, declarations=declarations, result='Int') as authority:
        first = command_rows(authority, 0, site=site_index(authority, boundary='fetch'))
        second = command_rows(authority, 0, site=site_index(authority, boundary='inc'))
        rows = list(command_rows(authority, 0, site=site_index(authority, boundary='check'))) if kind == 'effectful' else []
        rows.extend([first[0], second[0], first[1]])
        if completed:
            rows.append(second[1])
        snapshot = write_rows(authority, rows)
        assert preflight(authority)[2] == len(snapshot.active_commits)
        assert views._replay(authority, snapshot)[2] is completed


@pytest.mark.parametrize('completed', [False, True])
def test_nested_item_tail_retains_strict_starts_after_inner_map(tmp_path, completed):
    inner = mapped(COMMAND.replace('fetch', 'check').replace('repo', 'child'), source='(list "a")', label='child')
    sequential = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    with replay_case(tmp_path, mapped('(call worker :repo repo)'),
            declarations=worker(f'(let* ((batch {inner})) {sequential})')) as authority:
        rows = list(command_rows(authority, 0, site=site_index(authority, boundary='check'), indices=[0, 0]))
        first = command_rows(authority, 0, site=site_index(authority, boundary='fetch'))
        second = command_rows(authority, 0, site=site_index(authority, boundary='inc'))
        rows.extend([first[0], second[0], first[1]])
        if completed:
            rows.append(second[1])
        snapshot = write_rows(authority, rows)
        with pytest.raises(MemoError, match='memo_inconsistent'):
            views._replay(authority, snapshot)


def test_empty_map_keeps_an_earlier_map_barrier_pending(tmp_path):
    declarations = worker('7') + '(defproc empty () -> List[String] :effects () :lowering inline (list))'
    first_map = mapped(COMMAND.replace('fetch', 'check'), source='(list "a")')
    empty_map = mapped('(call worker :repo repo)', source='repos')
    body = f'(let* ((repos (empty)) (batch {first_map}) (empty-batch {empty_map})) (command-result fetch :argv ("python" "probe.py" "a") :returns Int))'
    with replay_case(tmp_path, body, declarations=declarations, result='Int') as authority:
        predecessor = command_rows(authority, 0, site=site_index(authority, boundary='check'))
        successor = command_rows(authority, 0, site=site_index(authority, boundary='fetch'))
        snapshot = write_rows(authority, [predecessor[0], successor[0], predecessor[1], successor[1]])
        with pytest.raises(MemoError, match='structured predecessor'):
            views._replay(authority, snapshot)


def test_later_serial_start_must_still_follow_the_completed_map(tmp_path):
    sequential = f'(let* ((first {COMMAND}) (second {COMMAND.replace("fetch", "inc")})) second)'
    batch = mapped(COMMAND.replace('fetch', 'check'), source='(list "a")')
    body = f'(let* ((batch {batch})) (call worker :repo "a"))'
    with replay_case(tmp_path, body, declarations=worker(sequential), result='Int') as authority:
        batch_rows = command_rows(authority, 0, site=site_index(authority, boundary='check'))
        first = command_rows(authority, 0, site=site_index(authority, boundary='fetch'))
        second = command_rows(authority, 0, site=site_index(authority, boundary='inc'))
        snapshot = write_rows(authority, [batch_rows[0], second[0], batch_rows[1], *first, second[1]])
        with pytest.raises(MemoError, match='memo_inconsistent'):
            views._replay(authority, snapshot)
