"""Public preparation preserves distinct imported owners of the same asset path."""

import hashlib
import json
import os

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_providers import (
    _assert_cli_resumes_unchanged,
    _cli,
    _fixture,
    _orchestrate_snapshot,
    _requests,
)


def test_public_cli_selects_distinct_import_assets_without_redispatch(tmp_path, monkeypatch):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((message String)) -> Int
        (let* ((left_value (call left))
               (right_value (call right)))
          (+ left_value right_value))))'''
    fixture = _fixture(tmp_path, source)
    imports = {}
    asset_bytes = {"left": b"LEFT IMPORT ASSET\n", "right": b"RIGHT IMPORT ASSET\n"}
    for side, content in asset_bytes.items():
        producer_root = tmp_path / side
        producer_root.mkdir()
        producer = producer_root / f"{side}.orc"
        producer.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule {side}/{side}) (export get)
          (defworkflow get () -> Int
            (provider-result providers.review :prompt prompts.base
              :inputs () :returns Int)))''')
        (producer_root / "prompt.md").write_bytes(content)
        imports[side] = {"kind": "compiled", "path": producer.relative_to(tmp_path).as_posix(),
                         "entry_workflow": "get"}
    imports_path = tmp_path / "imports.json"
    imports_path.write_text(json.dumps(imports))
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS", json.dumps([
        '1', '2',
    ]))
    result = _cli(tmp_path, fixture,
                  extra=("--imported-workflow-bundles-file", str(imports_path)), payload='1')
    assert result.returncode == 0, result.stderr
    requests = _requests(tmp_path)
    assert len(requests) == 2

    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    commits = list(snapshot.active_commits.values())
    assert snapshot.terminal.data["value"] == 3
    assert len(commits) == len(requests)
    assert commits[0].data["identity"] != commits[1].data["identity"]
    for entry, request, content in zip(commits, requests, asset_bytes.values(), strict=True):
        assert entry.data["input_parts"]["source:asset_file:prompt.md"] == "sha256:" + hashlib.sha256(content).hexdigest()
        assert content.decode() in request["prompt"]

    before = _orchestrate_snapshot(tmp_path)
    request_bytes = (tmp_path / "requests.jsonl").read_bytes()
    _assert_cli_resumes_unchanged(tmp_path, run_root.name, before, request_bytes, count=2)
