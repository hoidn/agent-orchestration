"""F6 public CLI witnesses with a real holder and retained image/closure membership."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.e2e.run_ref_fixtures import skip_unless_user_manager
from tests.e2e.run_ref_image_fixture import _writable
from tests.e2e.test_e2e_run_ref_confined_child import REPOSITORY, _git

pytestmark = pytest.mark.e2e

BOOTSTRAP = '''
import json, os, sys
from pathlib import Path
from orchestrator.workflow.run_ref import confined_cleanup, holder
capture = Path(os.environ['T8_CAPTURE'])
real_launch = holder.Holder.launch
def launch(self):
    with capture.open('a') as stream: stream.write(json.dumps({'holder': self.unit}) + '\\n')
    return real_launch(self)
holder.Holder.launch = launch
if os.environ.get('T8_FAIL_CLEANUP') == '1':
    def fail(fd): raise OSError('F6 injected cleanup refusal')
    confined_cleanup._delete_contents = fail
from orchestrator.cli.main import main
sys.exit(main(sys.argv[1:]))
'''

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule controller) (export run)
  (defpath Artifact :kind relpath :under "out" :must-exist true)
  (defrecord Paths (tree Artifact) (aliases List[Artifact]))
  (defworkflow candidate-body ((seed Int)) -> Paths
    (let* ((first (command-result produce :argv ("python3" "produce.py") :returns Paths))
           (second (command-result revise :argv ("python3" "revise.py") :returns Int))) first))
  (defworkflow run ((revision String)) -> String
    (let* ((child (run-ref :source (:repo "REPO" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed 1)
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds 300 :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 32 :output-mib 8)))))
      (match child
        ((COMPLETED c) (command-result consume :argv ("python3" "consume.py" c.result.value.tree) :returns String))
        ((FAILED f) f.code)))))'''

PRODUCE = '''import json, os, pathlib, subprocess
subprocess.run(['/usr/local/bin/codex', '--version'], check=True, stdout=subprocess.DEVNULL)
pathlib.Path('out/tree/empty').mkdir(parents=True)
pathlib.Path('out/tree/item').write_text('retained from real child\\n')
json.dump({'tree':'out/tree', 'aliases':['out/tree/item','out/tree/item']}, open(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'],'w'))
'''
REVISE = '''import json, os, pathlib
pathlib.Path('produce.py').write_text('changed after its committed snapshot\\n')
json.dump(1, open(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'],'w'))
'''
CONSUME = '''import json, os, pathlib, sys
root, = pathlib.Path('.orchestrate/runs').iterdir()
rows = [json.loads(line) for line in (root/'run-ref-attempts.jsonl').read_text().splitlines()]
assert rows[-1]['event_kind'] == 'cleanup_complete'
assert not pathlib.Path(rows[-1]['bindings']['workspace_path']).exists()
json.dump((pathlib.Path(sys.argv[1])/'item').read_text(), open(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'],'w'))
'''


@pytest.fixture
def large_image(tmp_path):
    skip_unless_user_manager()
    configured = os.environ.get('RUN_REF_E2E_LARGE_IMAGE_STORE')
    if not configured:
        pytest.skip('set RUN_REF_E2E_LARGE_IMAGE_STORE to an imported image containing native codex')
    source = Path(configured)
    records = list((source / 'records').glob('*.json'))
    if len(records) != 1:
        pytest.fail('large image fixture must identify exactly one imported image')
    record = json.loads(records[0].read_bytes())
    refs = tmp_path / 'refs'
    shutil.copytree(source, refs / 'images', symlinks=True)
    rootfs = refs / 'images/rootfs' / record['image'].rsplit(':', 1)[1]
    assert (rootfs / 'usr/local/bin/codex').stat().st_size > 64 << 20
    yield refs, record['image']
    for path in (refs / 'images', refs / 'withdrawn-images'):
        if path.exists():
            _writable(path)


def _launch(parent, capture, *arguments, fail_cleanup=False):
    return subprocess.run([sys.executable, '-c', BOOTSTRAP, *arguments], cwd=parent, text=True,
        capture_output=True, timeout=600, env={**os.environ, 'PYTHONPATH': str(REPOSITORY),
        'T8_CAPTURE': str(capture), 'T8_FAIL_CLEANUP': str(int(fail_cleanup))})


def _prepare(tmp_path, large_image, *, pending=False):
    refs, image = large_image
    repository = tmp_path / 'candidate'; repository.mkdir()
    _git(repository, 'init', '--quiet'); _git(repository, 'config', 'user.name', 'Run Ref F6')
    _git(repository, 'config', 'user.email', 'run-ref@example.invalid')
    (repository / 'produce.py').write_text(PRODUCE)
    (repository / 'revise.py').write_text(REVISE)
    _git(repository, 'add', '.'); _git(repository, 'commit', '--quiet', '-m', 'candidate')
    commit = _git(repository, 'rev-parse', 'HEAD')
    parent = tmp_path / 'parent'; parent.mkdir()
    source = SOURCE.replace('REPO', repository.as_uri()).replace('IMAGE', image)
    if pending:
        source = source.replace('(command-result consume :argv ("python3" "consume.py" c.result.value.tree) :returns String)', '"retained"')
    (parent / 'controller.orc').write_text(source)
    (parent / 'consume.py').write_text(CONSUME)
    (parent / 'boundaries.json').write_text(json.dumps({
        'produce': dict(stable_command=['python3', 'produce.py'], closure=['/usr/local/bin/codex']),
        'revise': dict(stable_command=['python3', 'revise.py'], closure=['/usr/local/bin']),
        'consume': dict(stable_command=['python3', 'consume.py'], closure=[])}))
    capture = tmp_path / 'holders.jsonl'
    done = _launch(parent, capture, 'run', 'controller.orc', '--entry-workflow', 'controller::run',
        '--command-boundaries-file', 'boundaries.json', '--run-ref-root', str(refs), '--input',
        f'revision={commit}', fail_cleanup=pending)
    assert done.returncode == 0, done.stderr
    (root,) = (parent / '.orchestrate/runs').iterdir()
    authority = load_run_authority(root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    site = next(entry.data for entry in memo.active_commits.values() if entry.data['effect_class'] == 'run_ref')
    clone = Path(site['proof']['settled_result']['workspace_path'])
    evidence = json.loads((clone.parent / 'evidence-manifest.json').read_bytes())
    child = Path(evidence['paths']['control_root'])
    result = dict(run_id=root.name, root=str(root), image=image, commit=commit, clone=str(clone), child=str(child),
        inventory_bytes=(child / 'image-inventory.json').stat().st_size, holders=str(capture),
        status=site['value']['variant'], stdout=done.stdout, stderr=done.stderr)
    (tmp_path / 'evidence.json').write_text(json.dumps(result, indent=2))
    if os.environ.get('T8_EVIDENCE_DIR'):
        target = Path(os.environ['T8_EVIDENCE_DIR']); target.mkdir(parents=True, exist_ok=True)
        (target / ('pending.json' if pending else 'retained.json')).write_text(json.dumps(result, indent=2))
    return parent, capture, authority, memo, site, clone, child


def test_public_parent_consumes_typed_alias_tree_after_cleanup_and_sources_withdrawn(tmp_path, large_image):
    parent, capture, authority, memo, site, clone, child = _prepare(tmp_path, large_image)
    assert memo.terminal.data['value'] == 'retained from real child\n'
    assert not clone.exists() and not (child / 'checkpoint.json').exists()
    value = site['value']['result']['value']
    assert value['aliases'][0] == value['aliases'][1]
    assert (parent / value['tree'] / 'empty').is_dir()
    assert (parent / value['aliases'][0]).read_text() == 'retained from real child\n'
    (clone.parent / 'baseline').rename(clone.parent / 'withdrawn-baseline')
    (large_image[0] / 'images').rename(large_image[0] / 'withdrawn-images')
    before = authority.memo_path.read_bytes(), capture.read_bytes(), (authority.run_root / 'run-ref-attempts.jsonl').read_bytes()
    resumed = _launch(parent, capture, 'resume', authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    report = _launch(parent, capture, 'report', '--run-id', authority.run_root.name, '--format', 'json')
    assert report.returncode == 0, report.stderr
    rendered = json.loads(report.stdout)
    assert rendered['run']['workflow_outputs'] == 'retained from real child\n'
    assert 'run_ref_cleanup' not in rendered['run']
    assert (authority.memo_path.read_bytes(), capture.read_bytes(), (authority.run_root / 'run-ref-attempts.jsonl').read_bytes()) == before


def test_public_completed_resume_retries_cleanup_without_a_holder(tmp_path, large_image):
    parent, capture, authority, memo, site, clone, child = _prepare(tmp_path, large_image, pending=True)
    before = authority.memo_path.read_bytes(), capture.read_bytes()
    pending = _launch(parent, capture, 'resume', authority.run_root.name, fail_cleanup=True)
    assert pending.returncode == 2 and '[run_ref_cleanup_pending]' in pending.stderr
    report = _launch(parent, capture, 'report', '--run-id', authority.run_root.name, '--format', 'json')
    assert report.returncode == 0, report.stderr
    rendered = json.loads(report.stdout)['run']
    assert rendered['status'] == 'completed' and rendered['workflow_outputs'] == 'retained'
    assert rendered['error'] is None and len(rendered['run_ref_cleanup']) == 1
    resumed = _launch(parent, capture, 'resume', authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert (authority.memo_path.read_bytes(), capture.read_bytes()) == before
    assert not clone.exists() and not (child / 'checkpoint.json').exists()
    assert load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl').rows[-1].event_kind == 'cleanup_complete'
