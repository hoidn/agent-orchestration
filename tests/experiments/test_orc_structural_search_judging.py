"""Waiting for a scan verdict (judging.await_verdict) on a scan file that is not JSON yet."""

import json
import threading
import pytest

from experiments.orc_structural_search import judging


def test_await_verdict_says_once_that_a_scan_is_not_json_and_keeps_polling(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(judging, "POLL_SEC", 0.01)
    scan = tmp_path / "scan.json"
    scan.write_text('{"hits": [')  # being written
    later = {"hits": [{"file": "f", "line": 1, "pattern": "p"}], "verdict": {"verdict": "cleared"}}
    timer = threading.Timer(0.3, lambda: scan.write_text(json.dumps(later)))
    timer.start()
    found = judging.await_verdict(scan, lambda value: value, "prepare.py scan --run R")
    timer.join()
    printed = capsys.readouterr().out
    assert (found, printed.count(f"{scan} is not JSON")) == (later, 1)


# The real harness builds the pool; scripted scoring writes memos without provider spend.
from tests.experiments.test_orc_structural_search_scoring import evaluations, score  # noqa: F401
from tests.experiments.compare_harness_support import world  # noqa: F401


def test_score_pool_retries_once_and_settles_judge_reservations(evaluations, world):
    import subprocess
    out, mapping, _, log, criterion = evaluations
    calls = []
    def scorer(pool, name, script):
        calls.append((name, script))
        if script == 'score':
            raise subprocess.CalledProcessError(1, 'scripted first failure')
        score(out, mapping, name, world.tmp / 'home')
    proof = judging.score_pool(log.parent, out, 'retry', names=list(mapping['judges']), solution=world.solution,
                               call_cap=10, scorer=scorer, criterion=criterion)
    assert calls == [(name, script) for name in mapping['judges'] for script in ('score', 'resume')]
    assert proof['qualification_sha256']
    entries = json.loads((log.parent / 'calls.json').read_text())
    assert len(entries) == 2 and all(entry['calls'] == 0 for entry in entries)


@pytest.mark.parametrize('tamper', ['receipt', 'pool-hash'])
def test_retry_revalidates_receipt_before_resume_dispatch(evaluations, tamper):
    import subprocess
    import pytest
    out, mapping, _, log, criterion = evaluations
    receipt = __import__('pathlib').Path(json.loads(criterion.read_text())['qualification']['file'])
    calls = []
    def scorer(pool, name, script):
        calls.append(script)
        if tamper == 'receipt':
            receipt.write_text(receipt.read_text() + ' ')
        else:
            data = json.loads((pool / 'records/mapping.json').read_text())
            data['criterion_sha256'] = '0' * 64
            (pool / 'records/mapping.json').write_text(json.dumps(data))
            for judge in data['judges']:
                path = pool / 'records' / f'score-inputs-{judge}.json'
                inputs = json.loads(path.read_text())
                inputs['criterion_sha256'] = '0' * 64
                path.write_text(json.dumps(inputs))
        raise subprocess.CalledProcessError(1, 'scripted failure')
    with pytest.raises(ValueError, match='hash mismatch|criterion changed'):
        judging.score_pool(log.parent, out, 'stale', names=list(mapping['judges']), solution='solution',
                           call_cap=10, scorer=scorer, criterion=criterion)
    assert calls == ['score']
    assert all(entry['calls'] == 0 for entry in json.loads((log.parent / 'calls.json').read_text()))


def test_duplicate_dispatch_names_refuse_before_reservation(evaluations):
    import pytest
    out, mapping, _, log, criterion = evaluations
    names = [*mapping['judges'], next(iter(mapping['judges']))]
    with pytest.raises(ValueError, match='dispatch'):
        judging.score_pool(log.parent, out, 'duplicate', names=names, solution='solution', call_cap=10,
                           scorer=lambda *_: pytest.fail('dispatched'), criterion=criterion)
    assert not (log.parent / 'calls.json').exists()


def test_two_judge_failures_are_an_incident_and_settle_every_reservation(evaluations):
    import subprocess
    import pytest
    out, mapping, _, log, criterion = evaluations
    calls = []
    def scorer(pool, name, script):
        calls.append(script)
        raise subprocess.CalledProcessError(1, 'scripted failure')
    with pytest.raises(judging.JudgeIncident):
        judging.score_pool(log.parent, out, 'failed', names=list(mapping['judges']), solution='solution', call_cap=10,
                           scorer=scorer, criterion=criterion)
    assert calls == ['score', 'resume']
    assert all(entry['calls'] == 0 for entry in json.loads((log.parent / 'calls.json').read_text()))


def test_scan_waits_until_operator_adjudicates_hits(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'scan.json'
    scan = {'hits': [{'file': 'evidence', 'line': 1, 'pattern': 'private'}], 'verdict': None}
    path.write_text(json.dumps(scan))
    def adjudicate(_seconds):
        path.write_text(json.dumps(scan | {'verdict': {'verdict': 'cleared', 'reason': 'reviewed'}}))
    monkeypatch.setattr(judging.time, 'sleep', adjudicate)
    result = judging.await_verdict(path, lambda x: x, 'prepare scan')
    assert result['verdict']['verdict'] == 'cleared'
    assert 'prepare scan' in capsys.readouterr().out
