"""Resume planning charges only unreserved pending judge batches, never settled work twice."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.orc_structural_search import judging, ledger
from experiments.orc_structural_search.records import append_record


@pytest.fixture
def resume(tmp_path):
    evidence, pools = tmp_path / 'E', tmp_path / 'P'
    evidence.mkdir()
    (evidence / 'log.jsonl').touch()
    pool = pools / 'gen-1/task'
    (pool / 'records').mkdir(parents=True)
    mapping = {'batches': [['clone']] * 3, 'criterion_sha256': 'frozen',
               'judges': {'judge-a': {'dir': 'a'}, 'judge-b': {'dir': 'b'}}}
    (pool / 'records/mapping.json').write_text(json.dumps(mapping))
    for name, info in mapping['judges'].items():
        inputs = {'batches': [{'clones': ['clone']}] * 3, 'criterion_sha256': 'frozen', 'judge_model': name}
        (pool / 'records' / f'score-inputs-{name}.json').write_text(json.dumps(inputs))
        state = pool / 'judges' / info['dir'] / 'state/r1'
        state.mkdir(parents=True)
        (state / 'run.json').write_text(json.dumps({'bound_inputs': inputs}))
        (pool / 'records/judges' / name / 'calls').mkdir(parents=True)
    launch = {'resume': True, 'evidence_root': evidence, 'pools_root': pools}
    return SimpleNamespace(evidence=evidence, pool=pool, mapping=mapping, launch=launch,
                           judge={'judges': list(mapping['judges'])}, tasks=[Path('task')])


def memo(s, name, *, completed=False, partial=False):
    state = s.pool / 'judges' / s.mapping['judges'][name]['dir'] / 'state/r1'
    rows = []
    if partial:
        call = s.pool / 'records/judges' / name / 'calls/1'
        call.mkdir()
        (call / 'prompt.txt').write_text('one')
        rows = [{'record': 'started', 'identity': 'batch-0', 'attempt': 1,
                 'input_parts': {'prompt': 'sha256:' + hashlib.sha256(b'one').hexdigest()}},
                {'record': 'committed', 'identity': 'batch-0', 'attempt': 1, 'effect_class': 'provider'}]
    if completed:
        rows.append({'record': 'terminal', 'outcome': 'completed', 'value': []})
    (state / 'memo.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))


def planned(s):
    return judging.planned_judging([None], 1, s.tasks, 1, s.launch, s.judge, [6])


def test_logged_complete_judging_has_no_pending_budget_at_a_consumed_cap(resume):
    s = resume
    append_record(s.evidence / 'log.jsonl', {'kind': 'judging', 'generation': 1, 'task': 'task'})
    (s.evidence / ledger.LEDGER).write_text(json.dumps([{'kind': 'judge', 'key': 'old', 'planned': 4, 'calls': 4}]))
    assert planned(s) == 0
    ledger.check_budget(s.evidence, planned(s), 4, 'exact retry')


def test_completed_judges_and_committed_partial_batches_are_not_planned_again(resume):
    s = resume
    memo(s, 'judge-a', completed=True)
    memo(s, 'judge-b', partial=True)
    assert planned(s) == 2
    entries = [{'kind': 'judge', 'key': 'gen 1 task judge-b', 'planned': 3, 'calls': None}]
    (s.evidence / ledger.LEDGER).write_text(json.dumps(entries))
    assert planned(s) == 0
    entries[0]['calls'] = 1
    (s.evidence / ledger.LEDGER).write_text(json.dumps(entries))
    assert planned(s) == 2
    ledger.check_budget(s.evidence, planned(s), 3, 'partial retry')


def test_partial_budget_credit_requires_bound_inputs_and_physical_call_pairing(resume):
    s = resume
    memo(s, 'judge-a', completed=True)
    memo(s, 'judge-b', partial=True)
    (s.pool / 'records/judges/judge-b/calls/1/prompt.txt').write_text('tampered')
    with pytest.raises((ValueError, SystemExit), match='prompt'):
        planned(s)


def test_public_evaluate_and_judge_exact_retry_does_not_require_room_for_paid_judges(resume, monkeypatch):
    s = resume
    fields = {'candidate_id': 'candidate', 'generation': 1, 'split': 'adaptive'}
    append_record(s.evidence / 'log.jsonl', fields | {'kind': 'evaluation', 'task_id': 'task',
        'replicate': 1, 'outcome': 'completed'})
    append_record(s.evidence / 'log.jsonl', {'kind': 'judging', 'generation': 1, 'task': 'task'})
    (s.evidence / ledger.LEDGER).write_text(json.dumps([{'kind': 'judge', 'key': 'settled', 'planned': 4, 'calls': 4}]))
    criterion = s.evidence / 'criterion.json'
    criterion.write_text('{}')
    launch = s.launch | {'work_root': s.evidence / 'W', 'runtime': s.evidence / 'runtime', 'env': {},
        'timeout_sec': 1, 'solutions': {}, 'call_cap': 4, 'concurrency': 1}
    returned = []
    monkeypatch.setattr(judging, 'judge_generation', lambda *_args, **_kwargs: returned)
    assert judging.evaluate_and_judge([(s.evidence / 'candidate', None, fields)], 1, s.tasks,
        replicates=1, launch=launch, judge=s.judge | {'criterion': criterion}) is returned


def test_generation_resume_does_not_plan_an_already_started_generation_again(resume, monkeypatch):
    from experiments.orc_structural_search import adaptive
    s = resume
    for draw in range(4):
        append_record(s.evidence / 'log.jsonl', {'kind': 'parent_decision', 'generation': 1, 'draw': draw})
    entries = [{'kind': 'episode', 'key': 'paid', 'planned': 160, 'calls': 160}]
    (s.evidence / ledger.LEDGER).write_text(json.dumps(entries))
    criterion = s.evidence / 'criterion.json'
    criterion.write_text('{}')
    frozen = {'horizon': {'episodes_per_generation': 4}, 'envelope': {'child_planned_maximum': 4},
              'stop_rules': {'persistent_infrastructure': 3}, 'futility': {'consecutive': 4}}
    state = {'generation': 1, 'scheduled': [], 'resolved': [[1, i] for i in range(4)],
             'outcomes': ['revisit'] * 4, 'stopped': None}
    monkeypatch.setattr(adaptive, 'campaign_episode', lambda *_args, **_kwargs: {'kind': 'revisit'})
    monkeypatch.setattr(adaptive, 'calibrate_generation', lambda *_args: False)
    launch = s.launch | {'frozen': frozen, 'call_cap': 160, 'settled': lambda: None}
    result = adaptive.campaign_generation(1, state, None, store=None, campaign_id='campaign', criterion=criterion,
        rng=None, adaptive_tasks=s.tasks, launch=launch, judge=s.judge | {'criterion': criterion})
    assert result['stopped'] == 'futility'
    assert ledger._read(s.evidence / ledger.LEDGER) == entries
