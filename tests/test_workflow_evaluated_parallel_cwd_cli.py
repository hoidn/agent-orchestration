"""Public CLI witnesses for the 2.37 parallel item cwd protocol."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.closure_evidence import command_evidence_key
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_providers import _cli as _provider_cli, _fixture as _provider_fixture
from tests.test_workflow_evaluated_resume import _resume_cli


COMMAND_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel/cwd-cli) (export run)
  (defpath Findings :kind relpath :under "artifacts/work" :must-exist true)
  (defrecord Seen (item String) (data String) (finding String) (cwd String)
    (root String) (document_absolute Bool) (document_external Bool) (result_absolute Bool))
  (defworkflow run ((items Findings)) -> List[Seen]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result fetch :argv ("python" SCRIPT "data.txt" repo)
        :inputs ((items items)) :returns Seen))))
'''

ADAPTER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel/adapter-cli) (export run)
  (defpath Findings :kind relpath :under "artifacts/work" :must-exist true)
  (defrecord ReviewFindings (schema_version String) (items_path Findings))
  (defworkflow run ((items Findings)) -> List[ReviewFindings]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result validate_review_findings_v1
        :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items)
        :returns ReviewFindings))))
'''

INLINE_ADAPTER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel/inline-adapter-cli) (export run)
  (defpath Findings :kind relpath :under "artifacts/work" :must-exist true)
  (defrecord ReviewFindings (schema_version String) (items_path Findings))
  (defworkflow run ((items Findings)) -> List[ReviewFindings]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result validate_review_findings_v1
        :adapter validate_review_findings_v1
        :inputs ((schema_version "ReviewFindings.v1") (items_path items))
        :returns ReviewFindings))))
'''

OUTSIDE_CWD_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel/outside-cwd) (export run)
  (defrecord Seen (cwd String) (data String) (root String))
  (defworkflow run ((repo String)) -> List[Seen]
    (list/map-effect ((place (list repo))) :max 1 :parallel 1 :workspace place
      (command-result fetch :argv ("python" "probe.py" "data.txt") :returns Seen))))
'''

COMMAND_PROBE = '''import json, os, sys
from pathlib import Path
root = Path(os.environ["ORCHESTRATOR_WORKSPACE_ROOT"])
document = Path(sys.argv[-1])
result_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
typed = json.loads(document.read_text())
carrier = json.loads((root / typed["items"]).read_text())
finding = (root / carrier["items_path"]).read_text()
value = {"item": sys.argv[2], "data": Path(sys.argv[1]).read_text(),
    "finding": finding, "cwd": Path.cwd().relative_to(root).as_posix(),
    "root": str(root), "document_absolute": document.is_absolute(),
    "document_external": not document.is_relative_to(root),
    "result_absolute": result_path.is_absolute()}
result_path.write_text(json.dumps(value))
'''

PARALLEL_INDEX_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel/index-cli) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result fetch :argv ("python" SCRIPT repo "${loop.index}") :returns Int))))
'''

PROVIDER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defpath Findings :kind relpath :under "artifacts/work" :must-exist true)
  (defrecord ReviewFindings (schema_version String) (items_path Findings))
  (defworkflow run ((message String)) -> List[ReviewFindings]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace repo
      (provider-result providers.review :prompt prompts.base :inputs (message)
        :model "chosen-model" :effort "low" :returns ReviewFindings))))
'''


def _run_root(state_dir):
    (root,) = state_dir.iterdir()
    return root


def _expected_command_values(workspace):
    return [
        {"item": item, "data": f"{item}-only", "finding": "outer finding",
         "cwd": f"{item}/work", "root": str(workspace), "document_absolute": True,
         "document_external": True, "result_absolute": True}
        for item in ("alpha", "beta")
    ]


def _committed_rows(snapshot):
    return [row.data for row in snapshot.entries if row.data["record"] == "committed"]


def _assert_command_run(state_dir, workspace, script_argument, script_path):
    run_root = _run_root(state_dir)
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data["value"] == _expected_command_values(workspace)
    commits = _committed_rows(snapshot)
    assert len(commits) == 2
    for commit in commits:
        item = commit["value"]["item"]
        files = commit["implementation_files"]
        assert command_evidence_key("workspace", f"{item}/work/data.txt", 2) in files
        assert command_evidence_key("workspace", script_path.format(item=item), 1) in files
        assert command_evidence_key("workspace", "declared.txt") in files
        assert command_evidence_key("workspace", f"{item}/work/declared.txt") not in files
        assert commit["input_parts"]["argv"] == canonical_sha256([
            "python", script_argument, "data.txt", item,
        ])
        result_path = run_root / commit["result_path"]
        assert json.loads(result_path.read_text()) == commit["value"]
        assert not result_path.is_relative_to(workspace)


def _assert_adapter_run(run_root, expected):
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data["value"] == expected
    for row in snapshot.entries:
        if row.data["record"] != "committed":
            continue
        commit = row.data
        assert commit["value"] == expected[0]
        assert commit["input_parts"]["argv"] == canonical_sha256([
            "python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            "artifacts/work/carrier.json",
        ])
        assert json.loads((run_root / commit["result_path"]).read_text()) == expected[0]


def _write_adapter_fixture(workspace):
    artifacts = workspace / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    (artifacts / "carrier.json").write_text(json.dumps({
        "schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"
    }))
    (artifacts / "findings.json").write_text('{"items": []}')
    for item in ("alpha", "beta"):
        work = workspace / item / "work" / "artifacts" / "work"
        work.mkdir(parents=True)
        (work / "carrier.json").write_text("not the outer carrier")
        (work / "findings.json").write_text("not valid findings")


def test_public_parallel_item_index_reaches_command_and_completed_resume_reuses_results(tmp_path):
    source = tmp_path / "parallel" / "index-cli.orc"
    source.parent.mkdir(parents=True)
    probe = tmp_path / "index_probe.py"
    probe.write_text('''import json, os, sys
from pathlib import Path
item, index = sys.argv[1], int(sys.argv[2])
with (Path.cwd() / "index.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"item": item, "index": index}) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(index))
''')
    source.write_text(PARALLEL_INDEX_SOURCE.replace("SCRIPT", json.dumps(str(probe))))
    for item in ("alpha", "beta"):
        (tmp_path / item / "work").mkdir(parents=True)
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"fetch": {
        "stable_command": ["python", str(probe)], "closure": []
    }}))

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries))

    assert result.returncode == 0, result.stderr
    run_root = _run_root(tmp_path / ".orchestrate" / "runs")
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data["value"] == [0, 1]
    logs = {item: tmp_path / item / "work" / "index.jsonl" for item in ("alpha", "beta")}
    assert {
        item: [json.loads(row) for row in path.read_text().splitlines()]
        for item, path in logs.items()
    } == {
        "alpha": [{"item": "alpha", "index": 0}],
        "beta": [{"item": "beta", "index": 1}],
    }
    before = {item: path.read_bytes() for item, path in logs.items()}

    resumed = _resume_cli(tmp_path, run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert {item: path.read_bytes() for item, path in logs.items()} == before


@pytest.mark.parametrize("script_mode", ["absolute", "relative"])
def test_public_parallel_commands_keep_outer_authority_with_external_state(
    tmp_path, monkeypatch, script_mode
):
    source = tmp_path / "parallel" / "cwd-cli.orc"
    source.parent.mkdir(parents=True)
    outer_script = tmp_path / "outer.py"
    script_argument = str(outer_script) if script_mode == "absolute" else "worker.py"
    script_path = "outer.py" if script_mode == "absolute" else "{item}/work/worker.py"
    if script_mode == "absolute":
        outer_script.write_text(COMMAND_PROBE)
    source.write_text(COMMAND_SOURCE.replace("SCRIPT", json.dumps(script_argument)))
    for item, content in (("alpha", "alpha-only"), ("beta", "beta-only")):
        work = tmp_path / item / "work"
        work.mkdir(parents=True)
        (work / "data.txt").write_text(content)
        (work / "outer.py").write_text("raise SystemExit(55)\n")
        (work / "worker.py").write_text(COMMAND_PROBE)
        (work / "declared.txt").write_text("item decoy")
    (tmp_path / "data.txt").write_text("outer-only")
    (tmp_path / "worker.py").write_text("raise SystemExit(55)\n")
    artifacts = tmp_path / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    (artifacts / "carrier.json").write_text(json.dumps({
        "schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"
    }))
    (artifacts / "findings.json").write_text("outer finding")
    (tmp_path / "declared.txt").write_text("outer declared closure")
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"fetch": {
        "stable_command": ["python", script_argument, "data.txt"],
        "closure": ["declared.txt"],
    }}))
    state_dir = tmp_path.parent / f"{tmp_path.name}-state"
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "/ambient/poison")

    result = _run_cli(tmp_path, str(source), "--input", "items=artifacts/work/carrier.json",
        "--command-boundaries-file", str(boundaries), "--state-dir", str(state_dir))

    assert result.returncode == 0, result.stderr
    _assert_command_run(state_dir, tmp_path, script_argument, script_path)


def test_public_parallel_command_accepts_one_absolute_item_cwd_outside_workspace(tmp_path):
    source = tmp_path / "parallel" / "outside-cwd.orc"
    source.parent.mkdir(parents=True)
    source.write_text(OUTSIDE_CWD_SOURCE)
    (tmp_path / "probe.py").write_text("raise SystemExit(55)\n")
    (tmp_path / "data.txt").write_text("workspace decoy")
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"fetch": {
        "stable_command": ["python", "probe.py", "data.txt"], "closure": []
    }}))

    with TemporaryDirectory(prefix=f"{tmp_path.name}-item-", dir=tmp_path.parent) as outside_name:
        outside = Path(outside_name)
        (outside / "data.txt").write_text("outside item")
        (outside / "probe.py").write_text('''import json, os
from pathlib import Path
root = Path(os.environ["ORCHESTRATOR_WORKSPACE_ROOT"])
value = {"cwd": str(Path.cwd()), "data": Path("data.txt").read_text(), "root": str(root)}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))
''')
        result = _run_cli(tmp_path, str(source), "--input", f"repo={outside}",
            "--command-boundaries-file", str(boundaries))

        assert result.returncode == 0, result.stderr
        run_root = _run_root(tmp_path / ".orchestrate" / "runs")
        authority = load_run_authority(run_root)
        snapshot = read_memo(authority.memo_path, site_classes(authority.program))
        assert snapshot.terminal.data["value"] == [
            {"cwd": str(outside), "data": "outside item", "root": str(tmp_path)}
        ]
        commit, = _committed_rows(snapshot)
        files = commit["implementation_files"]
        assert command_evidence_key("absolute", str(outside / "probe.py"), 1) in files
        assert command_evidence_key("absolute", str(outside / "data.txt"), 2) in files
        assert commit["input_parts"]["launch_cwd"] == canonical_sha256(str(outside))


def test_public_parallel_builtin_adapter_reads_carrier_from_logical_root(tmp_path):
    source = tmp_path / "parallel" / "adapter-cli.orc"
    source.parent.mkdir(parents=True)
    source.write_text(ADAPTER_SOURCE)
    _write_adapter_fixture(tmp_path)

    result = _run_cli(tmp_path, str(source), "--input", "items=artifacts/work/carrier.json")

    assert result.returncode == 0, result.stderr
    state_dir = tmp_path / ".orchestrate" / "runs"
    run_root = _run_root(state_dir)
    expected = [{"schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"}] * 2
    _assert_adapter_run(run_root, expected)
    artifacts = tmp_path / "artifacts" / "work"
    before = sorted(path.relative_to(tmp_path).as_posix() for path in artifacts.rglob("*"))
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert sorted(path.relative_to(tmp_path).as_posix() for path in artifacts.rglob("*")) == before


def test_public_parallel_inline_adapter_uses_explicit_certified_input_signature(tmp_path):
    source = tmp_path / "parallel" / "inline-adapter-cli.orc"
    source.parent.mkdir(parents=True)
    source.write_text(INLINE_ADAPTER_SOURCE)
    artifacts = tmp_path / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    (artifacts / "findings.json").write_text('{"items": []}')
    for item in ("alpha", "beta"):
        decoy = tmp_path / item / "work" / "artifacts" / "work" / "findings.json"
        decoy.parent.mkdir(parents=True)
        decoy.write_text("not valid findings")
    boundary = {
        "kind": "certified_adapter",
        "stable_command": [
            "python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"
        ],
        "closure": [str(Path(__file__).resolve().parents[1] / "orchestrator")],
        "input_contract": {"type": "object"},
        "output_type_name": "ReviewFindings",
        "effects": ["structured_result"],
        "path_safety": {"kind": "workspace_relpath"},
        "source_map_behavior": "step",
        "fixture_ids": ["review_findings_valid"],
        "negative_fixture_ids": ["review_findings_wrong_schema_version"],
        "behavior_class": "structured_result",
        "input_signature": [
            {"name": "schema_version", "type_name": "String", "required": True,
             "transport_key": "schema_version"},
            {"name": "items_path", "type_name": "Findings", "required": True,
             "transport_key": "items_path"},
        ],
        "artifact_contracts": ["review_findings_bundle"],
        "state_writes": [],
        "error_codes": ["review_findings_bundle_schema_invalid"],
        "owner_module": "std/phase",
        "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
        "retirement_class": "validation",
        "retirement_label": "keep_bridge",
        "replacement_surface": "typed review findings validation bridge",
        "bridge_owner": "std/phase",
        "expiry_condition": (
            "retain until typed review-findings validation parity replaces the command bridge"
        ),
        "evidence_refs": ["validate_review_findings_v1"],
    }
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"validate_review_findings_v1": boundary}))

    result = _run_cli(tmp_path, str(source), "--input", "items=artifacts/work/findings.json",
        "--command-boundaries-file", str(boundaries))

    assert result.returncode == 0, result.stderr
    run_root = _run_root(tmp_path / ".orchestrate" / "runs")
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    expected = [{"schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"}] * 2
    assert snapshot.terminal.data["value"] == expected
    commits = _committed_rows(snapshot)
    assert len(commits) == 2
    assert all(commit["value"] == expected[0] for commit in commits)


def _provider_cli_fixture(workspace):
    fixture = _provider_fixture(workspace, source=PROVIDER_SOURCE)
    binary = workspace / "bin" / "codex"
    binary.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
from pathlib import Path
prompt = sys.stdin.read()
root = Path(os.environ["ORCHESTRATOR_WORKSPACE_ROOT"])
item = Path.cwd().name
relative = f"artifacts/work/{item}.json"
(root / relative).write_text('{"items":[]}')
Path("provider-location.json").write_text(json.dumps({"cwd": str(Path.cwd()),
    "root": str(root), "prompt": prompt}))
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({
    "schema_version": "ReviewFindings.v1", "items_path": relative}))
''')
    binary.chmod(0o700)
    (workspace / "alpha").mkdir()
    (workspace / "beta").mkdir()
    (workspace / "artifacts" / "work").mkdir(parents=True)
    return fixture


def _assert_provider_run(workspace, fixture):
    result = _provider_cli(workspace, fixture)
    assert result.returncode == 0, result.stderr
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data["value"] == [
        {"schema_version": "ReviewFindings.v1", "items_path": f"artifacts/work/{item}.json"}
        for item in ("alpha", "beta")
    ]
    for item in ("alpha", "beta"):
        location = json.loads((workspace / item / "provider-location.json").read_text())
        assert location["cwd"] == str(workspace / item)
        assert location["root"] == str(workspace)
        assert str(workspace) not in location["prompt"]
        assert (workspace / "artifacts" / "work" / f"{item}.json").is_file()
        assert not (workspace / item / "artifacts" / "work" / f"{item}.json").exists()


def test_separate_public_parallel_provider_runs_keep_their_workspace_coordinates(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", "/ambient/poison")
    for name in ("first", "second"):
        workspace = tmp_path / name
        workspace.mkdir()
        _assert_provider_run(workspace, _provider_cli_fixture(workspace))
