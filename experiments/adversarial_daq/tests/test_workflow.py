import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

from test_runner import fixture

ROOT = Path(__file__).resolve().parents[1]


def frontend():
    return ['adversarial.orc', '--entry-workflow', 'adversarial::run',
            '--provider-externs-file', 'providers.json', '--prompt-externs-file', 'prompts.json',
            '--command-boundaries-file', 'commands.json']


def test_public_compiler_accepts_real_workflow():
    assert (ROOT / 'adversarial.orc').exists(), 'adversarial .orc is not implemented'
    result = subprocess.run([sys.executable, '-m', 'orchestrator', 'compile', *frontend()],
                            cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def setup(tmp_path, rounds, *, invalid_suite=False, claims=None):
    for name in ('adversarial.orc', 'providers.json', 'prompts.json', 'commands.json'):
        shutil.copy(ROOT / name, tmp_path / name)
    for name in ('scripts', 'prompts'):
        shutil.copytree(ROOT / name, tmp_path / name)
    proposal, challenge, p = fixture(tmp_path)
    if invalid_suite:
        (p / 'suite.py').write_text('raise SystemExit(2)\n')
    (p / 'dossier.md').write_text('Synthetic control-flow fixture, not DAQ evidence.\n')
    plan = []
    for number, (skeptic, builder) in enumerate(rounds, 1):
        current = tmp_path / 'artifacts' / f'round-{number}'
        if number > 1:
            shutil.copytree(p, current)
        proposal = f'artifacts/round-{number}/proposal.json'
        challenge = f'artifacts/round-{number}/challenge.json'
        manifest = json.loads((current / 'challenge.json').read_text())
        manifest['proposal'] = proposal
        (current / 'challenge.json').write_text(json.dumps(manifest))
        document = f'artifacts/round-{number}/dossier.md'
        claim = claims[number - 1] if claims else f'Synthetic criterion C{number}'
        (current / 'dossier.md').write_text(f'Synthetic control-flow criterion only: {claim}\n')
        submission = {'document': document, 'manifest': proposal}
        counter = {**submission, 'manifest': challenge}
        plan.extend([submission, counter, vote(skeptic, claim, document), vote(builder, claim, document)])
    (tmp_path / 'plan.json').write_text(json.dumps(plan))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    shim = bin_dir / 'claude'
    # A shebang containing this workspace's space would fail and PATH could fall
    # through to a real provider. env resolves the fixture's venv interpreter.
    shim.write_text('#!/usr/bin/env python3\n' + '''
import json,os,sys
from pathlib import Path
root=Path.cwd()
log=root/'requests.jsonl'
cursor=root/'cursor.txt'
n=int(cursor.read_text()) if cursor.exists() else 0
with log.open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
value=json.loads((root/'plan.json').read_text())[n]
fail_once=value.pop('_fail_once',False)
marker=root/f'failed-{n}'
if fail_once and not marker.exists():
    marker.write_text('failed before result commit')
    sys.exit(17)
tamper=value.pop('_tamper',False)
if 'evidence_digest' in value and value['evidence_digest']=='$CURRENT':
    report=max((root/'artifacts/evidence').glob('*/report.json'),key=lambda p:p.stat().st_mtime_ns)
    value['evidence_digest']=json.loads(report.read_text())['experiment_digest']
    if tamper:
        data=json.loads(report.read_text());data['totals']={}
        report.write_text(json.dumps(data))
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps(value))
cursor.write_text(str(n+1))
''')
    shim.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + str(Path(sys.executable).parent)
               + os.pathsep + os.environ.get('PATH', ''))
    return env


def vote(position, claim, document):
    result = {'position': position, 'claim': claim,
              'evidence_digest': '$CURRENT', 'fair': True, 'relevant': True,
              'reproduced': True, 'blockers': [], 'reason': 'Control-flow fixture',
              'report': document}
    if position == 'NEEDS_EXPERT':
        result.update(relevant=False, blockers=['Independent DAQ evidence unavailable'])
    return result


def cli(root, env, *args):
    return subprocess.run([sys.executable, '-m', 'orchestrator', *args], cwd=root,
                          env=env, text=True, capture_output=True, timeout=90)


def run(root, env, limit=4):
    result = cli(root, env, 'run', *frontend(), '--input', 'brief=synthetic workflow verification',
                 '--input', f'round_limit={limit}')
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = next((root / '.orchestrate/runs').iterdir()).name
    report = cli(root, env, 'report', '--run-id', run_id, '--format', 'json')
    assert report.returncode == 0, report.stdout + report.stderr
    return run_id, json.loads(report.stdout)['run']['workflow_outputs']


def test_first_supported_advantage_and_completed_resume(tmp_path):
    env = setup(tmp_path, [('ADVANTAGE', 'ADVANTAGE'), ('COUNTEREXAMPLE', 'COUNTEREXAMPLE')])
    run_id, result = run(tmp_path, env)
    assert result['status'] == 'DEMO_SUPPORTED'
    assert len(result['history']) == 1
    assert len((tmp_path / 'requests.jsonl').read_text().splitlines()) == 4
    before = (tmp_path / 'requests.jsonl').read_bytes()
    reports = list((tmp_path / 'artifacts/evidence').glob('*/report.json'))
    hashes = {p: p.read_bytes() for p in reports}
    resumed = cli(tmp_path, env, 'resume', run_id)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert (tmp_path / 'requests.jsonl').read_bytes() == before
    assert {p: p.read_bytes() for p in (tmp_path / 'artifacts/evidence').glob('*/report.json')} == hashes


@pytest.mark.parametrize('position', ['COUNTEREXAMPLE', 'NEEDS_EXPERT'])
def test_local_outcome_continues_to_different_supported_claim(tmp_path, position):
    claims = ['Synthetic recovery parity criterion C1', 'Synthetic static composition criterion C2']
    env = setup(tmp_path, [(position, position), ('ADVANTAGE', 'ADVANTAGE')], claims=claims)
    _, result = run(tmp_path, env, 2)
    assert result['status'] == 'DEMO_SUPPORTED'
    first, second = result['history']
    assert [entry['number'] for entry in result['history']] == [1, 2]
    assert [entry['builder']['claim'] for entry in result['history']] == claims
    assert first['skeptic']['position'] == first['builder']['position'] == position
    assert first['evidence']['valid'] and first['intact']
    assert first['evidence']['digest'] != second['evidence']['digest']
    if position == 'NEEDS_EXPERT':
        assert not first['skeptic']['relevant']
        assert first['skeptic']['blockers']
    requests = [json.loads(line) for line in (tmp_path / 'requests.jsonl').read_text().splitlines()]
    assert len(requests) == 8
    for request in requests[4:6]:
        delivered = ' '.join(request)
        for value in (first['builder']['claim'], first['builder']['position'],
                      first['skeptic']['position'], first['evidence']['digest'],
                      first['evidence']['report'], first['proposal']['document'],
                      *first['skeptic']['blockers']):
            assert value in delivered


def test_dissent_revises_and_carries_complete_history(tmp_path):
    env = setup(tmp_path, [('COUNTEREXAMPLE', 'REVISE'), ('ADVANTAGE', 'ADVANTAGE')])
    _, result = run(tmp_path, env)
    assert result['status'] == 'DEMO_SUPPORTED'
    assert [r['number'] for r in result['history']] == [1, 2]
    requests = [json.loads(x) for x in (tmp_path / 'requests.jsonl').read_text().splitlines()]
    assert len(requests) == 8
    assert result['history'][0]['builder']['claim'] in ' '.join(requests[4])


def test_refutations_exhaust_budget_without_terminal_refutation(tmp_path):
    env = setup(tmp_path, [('COUNTEREXAMPLE', 'COUNTEREXAMPLE')] * 4)
    _, result = run(tmp_path, env, 4)
    assert result['status'] == 'INCONCLUSIVE'
    assert [entry['number'] for entry in result['history']] == [1, 2, 3, 4]
    assert all(entry['intact'] and entry['evidence']['valid'] for entry in result['history'])
    assert len((tmp_path / 'requests.jsonl').read_text().splitlines()) == 16


def test_round_budget_never_becomes_impossibility(tmp_path):
    env = setup(tmp_path, [('REVISE','REVISE')] * 2)
    _, result = run(tmp_path, env, 2)
    assert result['status'] == 'INCONCLUSIVE'
    assert len(result['history']) == 2
    assert len((tmp_path / 'requests.jsonl').read_text().splitlines()) == 8


@pytest.mark.parametrize('mutation', ['digest','blocker','fair','relevant','reproduced','claim','expert','invalid_evidence','tamper'])
def test_consensus_cannot_override_evidence_or_unresolved_objections(tmp_path, mutation):
    env = setup(tmp_path, [('ADVANTAGE','ADVANTAGE')], invalid_suite=mutation=='invalid_evidence')
    path = tmp_path / 'plan.json'
    plan = json.loads(path.read_text())
    if mutation == 'digest': plan[3]['evidence_digest'] = 'stale'
    if mutation == 'blocker': plan[3]['blockers'] = ['unanswered objection']
    if mutation in {'fair', 'relevant', 'reproduced'}: plan[3][mutation] = False
    if mutation == 'claim': plan[3]['claim'] = 'a different claim'
    if mutation == 'expert': plan[3]['position'] = 'NEEDS_EXPERT'
    if mutation == 'tamper': plan[3]['_tamper'] = True
    path.write_text(json.dumps(plan))
    _, result = run(tmp_path, env, 1)
    assert result['status'] == 'INCONCLUSIVE'


def test_malformed_provider_result_fails_before_trials(tmp_path):
    env = setup(tmp_path, [('ADVANTAGE','ADVANTAGE')])
    (tmp_path / 'plan.json').write_text(json.dumps([{'document': 123, 'manifest': False}]))
    result = cli(tmp_path, env, 'run', *frontend(), '--input', 'brief=test')
    assert result.returncode != 0
    assert len((tmp_path / 'requests.jsonl').read_text().splitlines()) == 1
    assert not (tmp_path / 'artifacts/evidence').exists()


@pytest.mark.parametrize('limit', [0, 5])
def test_invalid_budget_dispatches_nothing(tmp_path, limit):
    env = setup(tmp_path, [])
    _, result = run(tmp_path, env, limit)
    assert result['status'] == 'INCONCLUSIVE'
    assert result['history'] == []
    assert not (tmp_path / 'requests.jsonl').exists()


def test_resume_after_failed_review_reuses_committed_trials(tmp_path):
    env = setup(tmp_path, [('ADVANTAGE','ADVANTAGE')])
    path = tmp_path / 'plan.json'
    plan = json.loads(path.read_text())
    plan[2]['_fail_once'] = True
    path.write_text(json.dumps(plan))
    first = cli(tmp_path, env, 'run', *frontend(), '--input', 'brief=test')
    assert first.returncode != 0
    run_id = next((tmp_path / '.orchestrate/runs').iterdir()).name
    reports = {p: p.read_bytes() for p in (tmp_path / 'artifacts/evidence').glob('*/report.json')}
    assert len(reports) == 1
    resumed = cli(tmp_path, env, 'resume', run_id)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert {p: p.read_bytes() for p in (tmp_path / 'artifacts/evidence').glob('*/report.json')} == reports
    assert len((tmp_path / 'requests.jsonl').read_text().splitlines()) == 5


def test_static_type_mismatch_is_rejected_before_dispatch(tmp_path):
    env = setup(tmp_path, [])
    path = tmp_path / 'adversarial.orc'
    path.write_text(path.read_text().replace(':round (+ state.round 1)', ':round "wrong type"'))
    result = cli(tmp_path, env, 'compile', *frontend())
    assert result.returncode != 0
    assert not (tmp_path / 'requests.jsonl').exists()
    assert not (tmp_path / 'artifacts/evidence').exists()
