#!/usr/bin/python3
"""Exercise the deployed criteria search with deterministic fake providers only."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_runner import fixture

    identifier = uuid.uuid4().hex
    work = ROOT / 'artifacts/criteria-revision-20261023' / ('smoke-' + identifier)
    work.mkdir(parents=True)
    _, _, first_sources = fixture(work)
    claims = ['Synthetic recovery parity criterion C1', 'Synthetic static composition criterion C2']
    plan = []
    for number, claim in enumerate(claims, 1):
        sources = work / 'artifacts' / f'round-{number}'
        if number > 1:
            shutil.copytree(first_sources, sources)
        proposal = str((sources / 'proposal.json').relative_to(ROOT))
        challenge = str((sources / 'challenge.json').relative_to(ROOT))
        data = json.loads((ROOT / proposal).read_text())
        data['scope'] = claim
        (ROOT / proposal).write_text(json.dumps(data))
        data = json.loads((ROOT / challenge).read_text())
        data['proposal'] = proposal
        (ROOT / challenge).write_text(json.dumps(data))
        dossier = sources / 'dossier.md'
        dossier.write_text(f'Synthetic control-flow criterion only: {claim}\n')
        submission = {'document': str(dossier.relative_to(ROOT)), 'manifest': proposal}
        counter = dict(submission, manifest=challenge)
        vote = {'position': 'COUNTEREXAMPLE' if number == 1 else 'ADVANTAGE', 'claim': claim,
                'evidence_digest': '$CURRENT', 'fair': True, 'relevant': True,
                'reproduced': True, 'blockers': [], 'reason': 'Control-flow fixture only',
                'report': str(dossier.relative_to(ROOT))}
        plan.extend([submission, counter, vote, vote])
    (work / 'plan.json').write_text(json.dumps(plan))
    fake_bin = work / 'bin'
    fake_bin.mkdir()
    shim = fake_bin / 'codex'
    shim.write_text('''#!/usr/bin/python3
import hashlib,json,os,re,sys
from pathlib import Path
work=Path(__file__).resolve().parents[1]
args=sys.argv[1:]
assert args[0]=='exec', args
assert args[args.index('--model')+1]=='gpt-6.1-sol', args
assert 'model_reasoning_effort=high' in args, args
prompt=sys.stdin.read()
assert prompt
log=work/'requests.jsonl'
previous=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
index=len(previous)
value=json.loads((work/'plan.json').read_text())[index]
paths=set(re.findall(r'artifacts/evidence/[0-9a-f]{32}/report.json',prompt))
if index in (4,5):
    for earlier in previous[2:4]:
        for field in ('claim','position','evidence_digest','report'):
            assert earlier['result'][field] in prompt
        assert all(path in prompt for path in earlier['evidence_paths'])
if value.get('evidence_digest')=='$CURRENT':
    candidates=[Path(path) for path in paths
                if json.loads(Path(path).read_text())['proposal']['scope']==value['claim']]
    assert len(candidates)==1, candidates
    value['evidence_digest']=json.loads(candidates[0].read_text())['experiment_digest']
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(json.dumps(value))
with log.open('a') as stream:
    stream.write(json.dumps({'argv':args,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                             'result':value,'evidence_paths':sorted(paths),
                             'history_checked':index in (4,5)})+'\\n')
''')
    shim.chmod(0o755)
    state = work / 'state'
    env = {'PATH': f'{fake_bin}:{ROOT}/.venv/bin:/usr/bin:/bin',
           'HOME': str(work), 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1'}
    command = [str(ROOT / '.venv/bin/python'), '-m', 'orchestrator', 'run',
               'adversarial_live.orc', '--entry-workflow', 'adversarial_live::run',
               '--provider-externs-file', 'deployment/providers.json',
               '--prompt-externs-file', 'prompts.json',
               '--command-boundaries-file', 'deployment/commands.json',
               '--input', 'brief=Synthetic deployment control-flow check; no quality claim',
               '--input', 'round_limit=2', '--state-dir', str(state)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
    (work / 'run.stdout.txt').write_text(result.stdout)
    (work / 'run.stderr.txt').write_text(result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    runs = list(state.iterdir())
    assert len(runs) == 1
    report = subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'orchestrator', 'report',
                             '--runs-root', str(state), '--run-id', runs[0].name, '--format', 'json'],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    (work / 'report.json').write_text(report.stdout)
    outcome = json.loads(report.stdout)['run']['workflow_outputs']
    assert outcome['status'] == 'DEMO_SUPPORTED', outcome
    assert [entry['builder']['claim'] for entry in outcome['history']] == claims
    assert [entry['builder']['position'] for entry in outcome['history']] == ['COUNTEREXAMPLE', 'ADVANTAGE']
    assert all(entry['evidence']['valid'] and entry['intact'] for entry in outcome['history'])
    requests = [json.loads(line) for line in (work / 'requests.jsonl').read_text().splitlines()]
    assert len(requests) == 8
    assert all(request['history_checked'] for request in requests[4:6])
    reports = [entry['evidence']['report'] for entry in outcome['history']]
    trials = sum(len(json.loads((ROOT / path).read_text())['trials']) for path in reports)
    assert trials == 12
    summary = {'synthetic_control_only': True, 'provider_calls': 8, 'real_provider_calls': 0,
               'status': outcome['status'], 'trials': trials, 'run_id': runs[0].name,
               'state_dir': str(state.relative_to(ROOT)), 'history_claims': claims,
               'evidence_reports': reports, 'next_round_history_checked': True}
    (work / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS: deployed workflow, eight fake Sol/high calls, twelve confined trials, '
          'preserved history, refutation then different supported criterion')
    print('Evidence: ' + str(work / 'summary.json'))


if __name__ == '__main__':
    main()
