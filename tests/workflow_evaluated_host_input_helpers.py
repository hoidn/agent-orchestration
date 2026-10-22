"""Real public lifecycle fixtures for serial durable host requests."""
from pathlib import Path
import json

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo


def build(root: Path, *, options=':timeout-sec 60', declarations='', question='question', params='', inputs=(), body=None, state_dir=None, answer_type='Approval'):
    source = root / 'host' / 'entry.orc'
    source.parent.mkdir(exist_ok=True)
    source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED) {declarations}
      (defworkflow run ((question String :default "Approve?"){params}) -> HostReply[{answer_type}]
        {body or f'(let* ((before (command-result emit :argv ("python" "probe.py") :returns Int))) (request-input {question} :returns {answer_type} {options}))'}))''')
    (root / 'probe.py').write_text('''import os
from pathlib import Path
with Path('dispatches.txt').open('a') as target:
    target.write('emit\\n')
Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text('7')
''')
    manifest = root / 'commands.json'
    manifest.write_text(json.dumps({'emit': {'stable_command': ['python', 'probe.py'], 'closure': ['probe.py']}}))
    arguments = ['run', str(source), '--source-root', str(root), '--command-boundaries-file', str(manifest)]
    for value in inputs:
        arguments += ['--input', value]
    if state_dir is not None:
        arguments += ['--state-dir', str(state_dir)]
    return source, create_parser().parse_args(arguments)


def start(root, monkeypatch, **kwargs):
    monkeypatch.chdir(root)
    source, args = build(root, **kwargs)
    result = run_workflow(args)
    return source, result


def snapshot(run_root):
    authority = load_run_authority(run_root)
    return read_memo(authority.memo_path, site_classes(authority.program))


def rows(run_root):
    return [entry.data for entry in snapshot(run_root).entries]


def resume(run_root, state_dir=None):
    return resume_workflow(run_root.name, state_dir=str(state_dir) if state_dir else None)


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and p.name not in {'run.lock', 'workspace.lock', 'workspace.guard'}}
