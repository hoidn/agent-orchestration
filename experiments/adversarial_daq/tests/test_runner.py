import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def runner():
    path = ROOT / 'scripts' / 'run_trials.py'
    assert path.exists(), 'paired evidence runner has not been implemented'
    spec = importlib.util.spec_from_file_location('run_trials', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture(tmp_path):
    p = tmp_path / 'artifacts' / 'round-1'
    p.mkdir(parents=True)
    (p / 'orc.py').write_text('NAME="orc"\n')
    (p / 'baseline.py').write_text('NAME="baseline"\n')
    (p / 'suite.py').write_text('''import json,sys
from pathlib import Path
arm, seed, out = sys.argv[1:]
json.dump({"arm":arm,"seed":int(seed),"cases":[
 {"id":c,"checks":{"safe":True,"recovered":arm=="orc"},
  "metrics":{"expensive_operations":2,"recovery_ticks":3}}
 for c in ("stale","transition")]}, open(out,"w"))
''')
    common = {'version': 1, 'scope': 'test only', 'files': ['suite.py', 'orc.py'],
              'suite': 'suite.py', 'cases': ['stale', 'transition'],
              'checks': ['safe', 'recovered'], 'metrics': ['expensive_operations', 'recovery_ticks'],
              'seeds': [11, 23, 47], 'timeout_sec': 10}
    (p / 'proposal.json').write_text(json.dumps(common))
    (p / 'challenge.json').write_text(json.dumps({'version': 1, 'files': ['baseline.py'],
        'proposal': 'artifacts/round-1/proposal.json'}))
    return 'artifacts/round-1/proposal.json', 'artifacts/round-1/challenge.json', p


def test_paired_trials_keep_failures_as_data_not_invalid_evidence(tmp_path):
    proposal, challenge, _ = fixture(tmp_path)
    result = runner().evaluate(tmp_path, proposal, challenge)
    assert result['valid'] is True
    report = json.loads((tmp_path / result['report']).read_text())
    assert len(report['trials']) == 6
    assert {x['seed'] for x in report['trials'] if x['arm'] == 'orc'} == {11, 23, 47}
    assert report['totals']['orc']['failed_checks'] == 0
    assert report['totals']['baseline']['failed_checks'] == 6
    assert result['digest'] == report['experiment_digest']
    assert (tmp_path / result['report']).parent.joinpath('source', 'suite.py').is_file()


def test_incomplete_or_fabricated_trial_identity_fails_closed(tmp_path):
    proposal, challenge, p = fixture(tmp_path)
    (p / 'suite.py').write_text('import json,sys\njson.dump({"arm":"orc","seed":0,"cases":[]},open(sys.argv[3],"w"))\n')
    result = runner().evaluate(tmp_path, proposal, challenge)
    assert result['valid'] is False


@pytest.mark.parametrize('bad', ['../escape.py', '/tmp/escape.py'])
def test_manifest_cannot_import_paths_outside_submission(tmp_path, bad):
    proposal, challenge, p = fixture(tmp_path)
    data = json.loads((p / 'challenge.json').read_text())
    data['files'] = [bad]
    (p / 'challenge.json').write_text(json.dumps(data))
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


def test_skeptic_cannot_replace_builder_files(tmp_path):
    proposal, challenge, p = fixture(tmp_path)
    data = json.loads((p / 'challenge.json').read_text())
    data['files'] = ['orc.py']
    (p / 'challenge.json').write_text(json.dumps(data))
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


def test_nonzero_exit_and_source_mutation_are_invalid(tmp_path):
    proposal, challenge, p = fixture(tmp_path)
    (p / 'suite.py').write_text('raise SystemExit(3)\n')
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False
    (p / 'suite.py').write_text('from pathlib import Path\nPath("orc.py").write_text("changed")\n')
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


@pytest.mark.parametrize('which', ['proposal', 'challenge'])
def test_bad_manifest_root_becomes_invalid_evidence(tmp_path, which):
    proposal, challenge, p = fixture(tmp_path)
    (p / f'{which}.json').write_text('[]')
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


def test_metric_overflow_becomes_invalid_evidence(tmp_path):
    proposal, challenge, p = fixture(tmp_path)
    suite = p / 'suite.py'
    suite.write_text(suite.read_text().replace('"recovery_ticks":3', '"recovery_ticks":1e308'))
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


@pytest.mark.parametrize('target', ['report', 'source', 'log', 'manifest'])
def test_post_review_evidence_tampering_is_rejected(tmp_path, target):
    proposal, challenge, _ = fixture(tmp_path)
    mod = runner()
    evidence = mod.evaluate(tmp_path, proposal, challenge)
    assert hasattr(mod, 'verify'), 'post-review integrity check is not implemented'
    assert mod.verify(tmp_path, evidence['report'], evidence['digest']) is True
    report_path = tmp_path / evidence['report']
    if target == 'report':
        data = json.loads(report_path.read_text())
        data['totals']['baseline']['failed_checks'] = 0
        report_path.write_text(json.dumps(data))
    if target == 'source': (report_path.parent / 'source/orc.py').write_text('changed')
    if target == 'log': (report_path.parent / '0-orc/stdout.txt').write_text('changed')
    if target == 'manifest': (report_path.parent / 'proposal.json').write_text('{}')
    assert mod.verify(tmp_path, evidence['report'], evidence['digest']) is False


def test_explicit_model_transport_is_equal_and_secret_is_not_recorded(tmp_path, monkeypatch):
    proposal, challenge, p = fixture(tmp_path)
    monkeypatch.setenv('DAQ_TRIAL_ENV', 'DAQ_MODEL_API_KEY,DAQ_MODEL_NAME')
    monkeypatch.setenv('DAQ_MODEL_API_KEY', 'test-secret-never-record')
    monkeypatch.setenv('DAQ_MODEL_NAME', 'test-model')
    suite = p / 'suite.py'
    suite.write_text('import os\nassert os.environ.get("DAQ_MODEL_API_KEY") == "test-secret-never-record"\n'
                     + suite.read_text())
    result = runner().evaluate(tmp_path, proposal, challenge)
    assert result['valid'] is True
    report = (tmp_path / result['report']).read_text()
    assert 'test-secret-never-record' not in report
    assert json.loads(report)['forwarded_environment_names'] == ['DAQ_MODEL_API_KEY','DAQ_MODEL_NAME']


def test_arbitrary_environment_forwarding_is_refused(tmp_path, monkeypatch):
    proposal, challenge, _ = fixture(tmp_path)
    monkeypatch.setenv('DAQ_TRIAL_ENV', 'HOME')
    assert runner().evaluate(tmp_path, proposal, challenge)['valid'] is False


def test_hung_trial_is_bounded_and_retains_logs(tmp_path):
    proposal, challenge, p = fixture(tmp_path)
    data = json.loads((p / 'proposal.json').read_text())
    data['timeout_sec'] = 1
    (p / 'proposal.json').write_text(json.dumps(data))
    (p / 'suite.py').write_text('import time\nprint("started",flush=True)\ntime.sleep(30)\n')
    result = runner().evaluate(tmp_path, proposal, challenge)
    assert result['valid'] is False
    report_path = tmp_path / result['report']
    assert 'trial timeout' in report_path.read_text()
    assert (report_path.parent / '0-orc/stdout.txt').read_text() == 'started\n'
