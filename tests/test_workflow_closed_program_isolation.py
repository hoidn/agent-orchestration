"""Compiler preparation and source-free execution have separate process boundaries."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BLOCK_COMPILER = '''
import importlib.abc
import importlib
import sys

class CompilerImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "orchestrator.workflow_lisp" or fullname.startswith("orchestrator.workflow_lisp."):
            raise ModuleNotFoundError("compiler import blocked: " + fullname)

assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
sys.meta_path.insert(0, CompilerImportBlocker())
try:
    importlib.import_module("orchestrator.workflow_lisp")
except ModuleNotFoundError as exc:
    assert "compiler import blocked" in str(exc)
else:
    raise AssertionError("compiler blocker did not reject its control")
'''

PREPARE_IO = '''
def reader_document(reader):
    return {"workflow_path": str(reader.workflow_path),
        "imports": {name: reader_document(value) for name, value in reader.imports.items()},
        "workflows": {name: reader_document(value) for name, value in reader.workflows.items()},
        "source_paths": {name: str(value) for name, value in reader.source_paths.items()}}

def io_document(io):
    return {"entry": {"owner": io.entry.owner, "reader": reader_document(io.entry.reader)},
        "calls": [[list(coordinate), {"callee": call.callee, "reader": call.reader,
            "references": [[list(path), route] for path, route in call.references.items()]}]
            for coordinate, call in io.calls.items()],
        "sites": sorted(io.sites), "program_digest": io.program_digest}
'''

LOAD_IO = '''
from orchestrator.workflow.evaluated.provider_io import (
    ProviderIOActivation, ProviderIOCall, ProviderIOContext, WorkflowIOReader,
)

def reader_from_document(row):
    return WorkflowIOReader(Path(row["workflow_path"]),
        {name: reader_from_document(value) for name, value in row["imports"].items()},
        {name: reader_from_document(value) for name, value in row["workflows"].items()},
        {name: Path(value) for name, value in row["source_paths"].items()})

def route_from_document(value):
    return tuple(route_from_document(part) for part in value) if isinstance(value, list) else value

def io_from_document(row, program):
    entry = ProviderIOActivation(row["entry"]["owner"], reader_from_document(row["entry"]["reader"]))
    calls = {tuple(coordinate): ProviderIOCall(call["callee"], route_from_document(call["reader"]),
        {tuple(path): route_from_document(route) for path, route in call["references"]})
        for coordinate, call in row["calls"]}
    return ProviderIOContext(entry, calls, frozenset(tuple(site) for site in row["sites"]),
        row["program_digest"]).bind(program)
'''

RETAIN_AUTHORITY = '''
from contextlib import ExitStack
from orchestrator.run_lock import run_writer_lock
from orchestrator.workflow.workspace_files import WorkspaceFiles

def retained_authority(run_root):
    stack = ExitStack()
    fd = stack.enter_context(run_writer_lock(run_root))
    files = WorkspaceFiles(run_root, root_fd=fd)
    stack.callback(files.close)
    return stack, load_run_authority(run_root, run_files=files)
'''


def _python(script, *arguments):
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, *(str(value) for value in arguments)],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_compiled_artifact_load_check_and_pure_evaluation_without_compiler(tmp_path):
    _python('''
from pathlib import Path
import sys
from tests.test_workflow_evaluated_cli import _build
from tests.test_workflow_lisp_closed_program_artifact import _closed, _typed_call_tree, _nested_record_tree
import json
root = Path(sys.argv[1])
_, program = _build(root)
(root / "artifact.json").write_text(program.artifact())
(root / "semantic.json").write_text(json.dumps({"calls": _closed(_typed_call_tree()).artifact(),
    "nominal": _closed(_nested_record_tree()).artifact()}))
''', tmp_path)
    _python(BLOCK_COMPILER + '''
from pathlib import Path
from copy import deepcopy
import json
from orchestrator.workflow.evaluated import runtime
from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
program = ClosedProgram.from_artifact((Path(sys.argv[1]) / "artifact.json").read_text())
assert evaluate_closed_program(program, {"score": 0.75, "threshold": 0.5}).json_value() == {"accepted": True, "score": 0.75}
semantic = json.loads((Path(sys.argv[1]) / "semantic.json").read_text())
calls = ClosedProgram.from_artifact(semantic["calls"])
nominal = ClosedProgram.from_artifact(semantic["nominal"])
changed = []
tree = deepcopy(program.tree)
tree["params"][0][1] = {"kind": "primitive", "name": "Bool"}
changed.append(tree)
tree = deepcopy(program.tree)
tree["target"] = "2.34"
changed.append(tree)
tree = deepcopy(program.tree)
tree["sites"].append([tree["entry"], "invented"])
changed.append(tree)
tree = deepcopy(calls.tree)
next(node for node in _ast_nodes(tree["body"]) if node["k"] == "call")["callee"] = "workflow:missing::run"
changed.append(tree)
tree = deepcopy(nominal.tree)
tree["result"]["name"] = "other::Outer"
changed.append(tree)
for tree in changed:
    try:
        ClosedProgram.from_artifact(json.dumps(tree))
    except ClosedProgramInvalid as exc:
        assert exc.rule not in {"json", "digest"}
    else:
        raise AssertionError("semantic tampering was accepted")
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path)


def test_real_command_performer_and_readers_without_compiler(tmp_path):
    _python('''
from pathlib import Path
import sys
from tests.test_workflow_evaluated_cli import test_public_run_dispatches_command_once_and_commits_typed_result
test_public_run_dispatches_command_once_and_commits_typed_result(Path(sys.argv[1]))
''', tmp_path)
    _python(BLOCK_COMPILER + RETAIN_AUTHORITY + '''
from pathlib import Path
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo, invalidate_suffix
from orchestrator.workflow.evaluated.runtime import execute_pure_resume
from orchestrator.workflow.evaluated.views import load_evaluated_view, report_snapshot
root = Path(sys.argv[1])
run_root, = (root / ".orchestrate" / "runs").iterdir()
stack, authority = retained_authority(run_root)
classes = site_classes(authority.program)
before = read_memo(authority.memo_path, classes)
commit, = before.active_commits.values()
invalidate_suffix(authority.memo_path, commit.data["identity"], classes,
    run_files=authority.run_files, checked_authority=authority)
assert execute_pure_resume(authority, authority.header["bound_inputs"], run_id=run_root.name,
    workspace=root) == (0, {"ok": True})
assert (root / "dispatches.txt").read_text().splitlines() == ["emit", "emit"]
stable = authority.memo_path.read_bytes()
assert execute_pure_resume(authority, authority.header["bound_inputs"], run_id=run_root.name,
    workspace=root) == (0, {"ok": True})
assert authority.memo_path.read_bytes() == stable
view = load_evaluated_view(run_root)
assert view["status"] == "completed"
assert report_snapshot(view, run_root)
stack.close()
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path)


def test_real_provider_transport_binding_and_freshness_without_compiler(tmp_path):
    _python(PREPARE_IO + '''
from pathlib import Path
import sys, json
from tests.test_workflow_evaluated_providers import _fixture, _cli
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
root = Path(sys.argv[1])
fixture = _fixture(root)
result = _cli(root, fixture)
assert result.returncode == 0, result.stderr
built = build_closed_program_bundle(fixture[3])
(root / "io.json").write_text(json.dumps(io_document(built.provider_io)))
''', tmp_path)
    _python(BLOCK_COMPILER + RETAIN_AUTHORITY + '''
from pathlib import Path
import os, json
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo, invalidate_suffix
from orchestrator.workflow.evaluated.runtime import execute_pure_resume
''' + LOAD_IO + '''
root = Path(sys.argv[1])
os.environ["PATH"] = str(root / "bin") + os.pathsep + os.environ["PATH"]
run_root, = (root / ".orchestrate" / "runs").iterdir()
stack, authority = retained_authority(run_root)
io = io_from_document(json.loads((root / "io.json").read_text()), authority.program)
classes = site_classes(authority.program)
commit, = read_memo(authority.memo_path, classes).active_commits.values()
invalidate_suffix(authority.memo_path, commit.data["identity"], classes,
    run_files=authority.run_files, checked_authority=authority)
assert execute_pure_resume(authority, authority.header["bound_inputs"], run_id=run_root.name,
    workspace=root, provider_io=io) == (0, {"ok": True})
assert len((root / "requests.jsonl").read_text().splitlines()) == 2
stable = authority.memo_path.read_bytes(), (root / "requests.jsonl").read_bytes()
(root / "prompt.md").write_text("different required source bytes")
assert execute_pure_resume(authority, authority.header["bound_inputs"], run_id=run_root.name,
    workspace=root, provider_io=io)[0] == 2
assert (authority.memo_path.read_bytes(), (root / "requests.jsonl").read_bytes()) == stable
stack.close()
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path)


def test_imported_reader_routes_and_binding_refusals_without_compiler(tmp_path):
    _python(PREPARE_IO + '''
from pathlib import Path
import sys, json
from tests.test_workflow_evaluated_provider_io import _stages, _typed, _checked, WREF
root = Path(sys.argv[1])
_, imports = _stages(root)
checked, io = _checked(_typed(root, WREF, imports))
(root / "artifact.json").write_text(checked.artifact())
(root / "io.json").write_text(json.dumps(io_document(io)))
''', tmp_path)
    _python(BLOCK_COMPILER + '''
from pathlib import Path
from dataclasses import replace
import json
from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.sites import _ast_nodes
''' + LOAD_IO + '''
root = Path(sys.argv[1])
program = ClosedProgram.from_artifact((root / "artifact.json").read_text())
io = io_from_document(json.loads((root / "io.json").read_text()), program)
calls = [node for node in _ast_nodes(program.tree["body"]) if node["k"] == "call"]
for outer, side in zip(calls, ("left", "right"), strict=True):
    activation = io.call(program.tree["entry"], outer["frame"], io.entry)
    inner, = [node for node in _ast_nodes(program.tree["definitions"][activation.owner]["body"]) if node["k"] == "call"]
    child = io.call(activation.owner, inner["frame"], activation)
    assert child.reader.workflow_path.is_relative_to(root / side)
for broken in (replace(io, calls={}), replace(io, program_digest="sha256:" + "0" * 64)):
    try:
        broken.bind(program)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched IO carrier accepted")
try:
    io.effect("wrong-owner", "wrong-site", io.entry)
except ValueError:
    pass
else:
    raise AssertionError("wrong IO owner accepted")
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path)


@pytest.mark.parametrize("child_target", ["2.24", "2.35"])
@pytest.mark.parametrize("operation", ["settle", "reconcile"])
def test_real_child_parent_settlement_without_compiler(tmp_path, child_target, operation):
    _python('''
from pathlib import Path
import sys, json
from pytest import MonkeyPatch
from tests.test_workflow_evaluated_run_ref import _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap
root = Path(sys.argv[1])
parent, source, refs = _public_fixture(root, child_target=sys.argv[2])
with MonkeyPatch.context() as patch:
    authority, _ = _commit_gap(patch, parent, source, refs)
(root / "prepared.json").write_text(json.dumps({"run_root": str(authority.run_root),
    "workspace": str(parent), "refs": str(refs)}))
''', tmp_path, child_target)
    _python(BLOCK_COMPILER + RETAIN_AUTHORITY + '''
from pathlib import Path
from copy import deepcopy
import json
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated import run_ref as adapter
from orchestrator.workflow.evaluated.runtime import execute_pure_resume
from orchestrator.workflow.run_ref.ledger import settled_result_binding_from_record
from orchestrator.workflow.run_ref.runtime import (
    PreparedRunRefSettlement, RunRefChildProcessResult, RunRefRuntimeError, _child_result_document,
    validate_run_ref_memo_authority,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
root = Path(sys.argv[1])
prepared = json.loads((root / "prepared.json").read_text())
workspace, refs = Path(prepared["workspace"]), Path(prepared["refs"])
stack, authority = retained_authority(Path(prepared["run_root"]))
classes = site_classes(authority.program)
snapshot = read_memo(authority.memo_path, classes)
commit, = snapshot.active_commits.values()
identity = commit.data["identity"]
node = site_nodes(authority.program)[identity]
resolved, _ = adapter.resolve_run_ref_input(node, ())
request = adapter._request(authority, resolved, identity, commit.data["attempt"], workspace)
proof = commit.data["proof"]
settled = settled_result_binding_from_record(proof["settled_result"])
child_files = sorted(str(path) for path in refs.rglob("child-request.json"))
assert len(child_files) == 1
bad = deepcopy(proof["settled_result"])
bad["workspace_path"] = str(refs / "missing-child")
try:
    validate_run_ref_memo_authority(request, settled_result=bad, artifacts=proof["artifacts"], allow_pending=True)
except ValueError:
    pass
else:
    raise AssertionError("tampered parent settlement proof accepted")
failure = {"schema_version": "run_ref_child_diagnostic.v1", "status": "rejected",
    "code": "run_ref_child_launch_failed", "reason": "request_invalid"}
try:
    _child_result_document(request, launch=None,
        process=RunRefChildProcessResult(1, b"", canonical_json_bytes(failure), 0))
except RunRefRuntimeError as exc:
    assert exc.code == failure["code"]
else:
    raise AssertionError("failed child diagnostic ignored")
adapter.validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, settled=False)
if sys.argv[2] == "settle":
    pending = PreparedRunRefSettlement(commit.data["value"], proof["artifacts"], settled,
        request.ledger_path, settled.workspace_path.parent / "evidence-manifest.json")
    adapter.settle_evaluated_run_ref(authority, resolved, identity, commit.data["attempt"], workspace,
        classes, pending, commit.data)
else:
    adapter.reconcile_evaluated_run_ref(authority, resolved, identity, workspace, commit, classes)
after = read_memo(authority.memo_path, classes)
assert after.active_commits[identity] == commit
assert (identity, commit.data["attempt"]) in after.settlements
assert after.entries[-1].data["by"] == sys.argv[2]
adapter.validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, settled=True)
assert execute_pure_resume(authority, authority.header["bound_inputs"], run_id=authority.run_root.name,
    workspace=workspace) == (0, True)
assert sorted(str(path) for path in refs.rglob("child-request.json")) == child_files
stack.close()
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path, operation)


def test_shared_compile_diagnostics_and_structural_failure_without_compiler(tmp_path):
    _python('''
from pathlib import Path
import json, sys
from unittest.mock import patch
from orchestrator.workflow_lisp import diagnostics
from tests.test_workflow_lisp_diagnostics import test_compile_diagnostics_document_has_closed_accepted_and_rejected_shapes
original = diagnostics.build_compile_diagnostics_document
documents = []
def capture(**kwargs):
    document = original(**kwargs)
    documents.append(document)
    return document
with patch.object(diagnostics, "build_compile_diagnostics_document", capture):
    test_compile_diagnostics_document_has_closed_accepted_and_rejected_shapes()
(Path(sys.argv[1]) / "diagnostics.json").write_text(json.dumps(documents))
''', tmp_path)
    _python(BLOCK_COMPILER + '''
from pathlib import Path
from copy import deepcopy
import json
from orchestrator.workflow.run_ref.wire import _validated_compile_diagnostics, validate_child_diagnostic_document
from orchestrator.workflow.run_ref.contracts import canonical_sha256, compute_compiler_runtime_identity
documents = json.loads((Path(sys.argv[1]) / "diagnostics.json").read_text())
for document in documents:
    assert _validated_compile_diagnostics(document) == document
accepted = next(row for row in documents if row["status"] == "accepted")
rejected = next(row for row in documents if row["status"] == "rejected")
broken = deepcopy(accepted)
identity = broken["normalized_program_identity"]
identity["module_source_revisions"].append(deepcopy(identity["module_source_revisions"][0]))
identity["digest"] = canonical_sha256({key: value for key, value in identity.items() if key != "digest"})
try:
    _validated_compile_diagnostics(broken)
except ValueError:
    pass
else:
    raise AssertionError("rehashed noncanonical identity accepted")
failure = {"schema_version": "run_ref_child_diagnostic.v1", "status": "rejected",
    "code": "trial_program_compile_rejected", "reason": "path_compile_rejected",
    "rejected_value": {}, "secondary_causes": ["type_unknown"], "compile_diagnostics": rejected}
assert validate_child_diagnostic_document(failure) == failure
try:
    validate_child_diagnostic_document({**failure, "secondary_causes": ["type_unknown", "type_unknown"]})
except ValueError:
    pass
else:
    raise AssertionError("duplicate failure causes accepted")
assert compute_compiler_runtime_identity().digest.startswith("sha256:")
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
''', tmp_path)
