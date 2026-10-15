"""Public retirement boundaries refuse before changing retained data."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
PROGRAM = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule retired) (export run)
  (defworkflow run () -> Bool true))
'''


def tree(root):
    return {
        str(p.relative_to(root)): (
            stat.S_IMODE(p.lstat().st_mode),
            p.lstat().st_mtime_ns,
            "symlink" if p.is_symlink() else "file" if p.is_file() else "directory" if p.is_dir() else "other",
            os.fsencode(p.readlink()) if p.is_symlink() else p.read_bytes() if p.is_file() else None,
        )
        for p in [root, *sorted(root.rglob("*"))]
    }


def cli(root, *argv):
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *argv], cwd=root,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)


RETIRED_IMPORT_BLOCKER = r'''
import importlib.abc
import sys

_RETIRED_EXACT = {
    "orchestrator.workflow.executor",
    "orchestrator.workflow.pure_result_replay",
    "orchestrator.workflow.lowering",
    "orchestrator.workflow_lisp.wcc.lower",
    "orchestrator.workflow_lisp.wcc.defunctionalize",
}
_BLOCKED_IMPORTS = []

def _retired_import(name):
    return (any(name == module or name.startswith(module + ".")
            for module in _RETIRED_EXACT)
        or name.startswith("orchestrator.workflow_lisp.lowering")
        or name.startswith("orchestrator.workflow_lisp.lexical_checkpoint"))

class _RetiredImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if _retired_import(fullname):
            _BLOCKED_IMPORTS.append(fullname)
            raise AssertionError("retired module import attempted: " + fullname)

assert not any(name == "orchestrator" or name.startswith("orchestrator.")
    for name in sys.modules)
sys.meta_path.insert(0, _RetiredImportBlocker())
'''


def cold_python(root, body):
    script = RETIRED_IMPORT_BLOCKER + f'''
try:
    exec({body!r}, globals())
finally:
    _loaded_retired = [name for name in sys.modules if _retired_import(name)]
    assert not _BLOCKED_IMPORTS and not _loaded_retired, {{
        "attempted": _BLOCKED_IMPORTS, "loaded": _loaded_retired
    }}
'''
    return subprocess.run(
        [sys.executable, "-B", "-c", script, str(root)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=120,
    )


@pytest.mark.parametrize("target", ["2.24", "2.34"])
@pytest.mark.parametrize("command", ["compile", "run", "dry-run"])
def test_old_entry_refuses_before_build_or_run_publication(tmp_path, target, command):
    source = tmp_path / "retired.orc"
    source.write_text(PROGRAM.format(target=target))
    argv = ["compile", str(source), "--diagnostics-json"] if command == "compile" else ["run", str(source)]
    if command == "dry-run":
        argv.append("--dry-run")
    before = tree(tmp_path)
    result = cli(tmp_path, *argv)
    assert result.returncode == 2, result.stdout + result.stderr
    if command == "compile":
        document = json.loads(result.stdout)
        assert document["status"] == "rejected"
        diagnostic = document["diagnostics"][0]
        assert diagnostic["code"] == "workflow_execution_target_retired"
        assert diagnostic["line"] == 3
    else:
        assert "workflow_execution_target_retired" in result.stderr
    assert tree(tmp_path) == before


def test_frontend_executable_build_refuses_but_old_type_analysis_remains(tmp_path):
    from orchestrator.workflow_lisp import build
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint, compile_stage3_entrypoint
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    source = tmp_path / "retired.orc"
    source.write_text(PROGRAM.format(target="2.34"))
    assert compile_stage1_entrypoint(source).entry_module.target_dsl_version == "2.34"
    analysis = compile_stage3_entrypoint(source)
    assert analysis.entry_result.typed_program.target == "2.34"
    assert analysis.entry_result.typed_workflows
    assert not hasattr(analysis, "validated_bundles_by_name")
    assert not hasattr(analysis.entry_result, "lowered_workflows")
    assert not hasattr(build, "build_frontend_bundle")
    before = tree(tmp_path)
    with pytest.raises(LispFrontendCompileError) as caught:
        build_closed_program_bundle(build.FrontendBuildRequest(source_path=source, workspace_root=tmp_path))
    assert caught.value.diagnostics[0].code == "workflow_execution_target_retired"
    assert tree(tmp_path) == before


@pytest.mark.parametrize("target", ["2.34", "2.35", "2.36", "2.37", "2.38"])
def test_explain_flat_views_refuse_without_build_or_export_writes(tmp_path, target):
    source = tmp_path / "retired.orc"
    source.write_text(PROGRAM.format(target=target))
    before = tree(tmp_path)
    result = cli(tmp_path, "explain", str(source), "--emit-executable-ir", "export.json")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "workflow_explain_retired" in result.stderr
    assert "Traceback" not in result.stderr
    assert tree(tmp_path) == before


def test_frontend_publication_checks_the_compiled_source_target(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp import build
    from orchestrator.workflow_lisp.closed import artifact
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    source = tmp_path / "retired.orc"
    source.write_text(PROGRAM.format(target="2.35"))
    compile_typed = artifact.compile_typed_program_with_result

    def change_before_compile(source_path, **kwargs):
        source.write_text(PROGRAM.format(target="2.34"))
        return compile_typed(source_path, **kwargs)

    monkeypatch.setattr(artifact, "compile_typed_program_with_result", change_before_compile)
    with pytest.raises(LispFrontendCompileError) as caught:
        artifact.build_closed_program_bundle(build.FrontendBuildRequest(source_path=source, workspace_root=tmp_path))
    assert caught.value.diagnostics[0].code == "workflow_execution_target_retired"
    assert caught.value.diagnostics[0].span.start.line == 3
    assert not (tmp_path / ".orchestrate").exists()


@pytest.mark.parametrize("header", [None, {"schema_version": "2.1"},
    {"schema_version": "2.1", "result_persistence_profile": "derived_pure_replay.v1"}])
@pytest.mark.parametrize("command", ["resume", "force-restart", "invalidate"])
def test_old_profile_refuses_before_any_lock_or_write(tmp_path, header, command):
    run = tmp_path / ".orchestrate" / "runs" / "historical"
    run.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"schema_version": "2.1", "run_id": "historical", "status": "running"}))
    (run / "state.json").chmod(0o640)
    if header is not None:
        (run / "run.json").write_text(json.dumps(header))
        (run / "run.json").chmod(0o400)
    before = tree(tmp_path)
    argv = ["invalidate", "historical", "absent"] if command == "invalidate" else ["resume", "historical"]
    if command == "force-restart":
        argv.append("--force-restart")
    result = cli(tmp_path, *argv)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "workflow_execution_profile_retired" in result.stderr
    assert tree(tmp_path) == before


@pytest.mark.parametrize(
    "command,arguments",
    [
        ("answer", ["00000000-0000-4000-8000-000000000001", "--text", "yes"]),
        ("cancel", ["00000000-0000-4000-8000-000000000001"]),
    ],
    ids=["answer", "cancel"],
)
def test_historical_human_input_settlement_refuses_before_lock_or_write(tmp_path, command, arguments):
    run = tmp_path / ".orchestrate" / "runs" / "historical"
    run.mkdir(parents=True)
    record = {
        "request_id": "00000000-0000-4000-8000-000000000001",
        "resume_scope": {"root_workflow_file": "retired.yaml", "call_frame_ids": []},
        "runtime_step_id": "request",
        "enclosing_step": {"step_name": "request", "step_id": "request", "visit_count": 1},
        "loop_iteration": None,
        "question": "Continue?",
        "status": "pending",
    }
    state = {
        "schema_version": "2.1",
        "run_id": "historical",
        "workflow_file": "retired.yaml",
        "workflow_checksum": "0" * 64,
        "started_at": "2026-10-01T00:00:00+00:00",
        "updated_at": "2026-10-01T00:00:00+00:00",
        "status": "suspended",
        "human_input": record,
    }
    state_file = run / "state.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    state_file.chmod(0o640)

    before = tree(tmp_path)
    queried = cli(tmp_path, "input", "get", "historical")
    assert queried.returncode == 0, queried.stderr
    assert json.loads(queried.stdout) == record
    assert tree(tmp_path) == before

    result = cli(tmp_path, "input", command, "historical", *arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert "workflow_execution_profile_retired" in result.stderr
    assert "separately retained complete release/environment" in result.stderr
    assert tree(tmp_path) == before


@pytest.mark.parametrize("replacement, code", [
    ('{"schema_version":"2.1"}', "workflow_execution_profile_retired"),
    ('{"schema_version":"2.1","result_persistence_profile":"derived_pure_replay.v1"}', "workflow_execution_profile_retired"),
    ('{"schema_version":"unknown"}', "memo_inconsistent"),
    ('{bad-json}', "memo_inconsistent"),
])
def test_resume_header_swap_under_lock_preserves_refusal_code(tmp_path, monkeypatch, caplog, replacement, code):
    from contextlib import contextmanager
    from orchestrator.cli.commands import resume
    from tests.test_workflow_evaluated_resume import _completed
    _, run_root = _completed(tmp_path)
    original_lock = resume.run_writer_lock
    retained = None

    @contextmanager
    def swap_under_lock(root):
        nonlocal retained
        with original_lock(root) as fd:
            (run_root / "run.json").write_text(replacement)
            retained = tree(run_root)
            yield fd

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(resume, "run_writer_lock", swap_under_lock)
    assert not hasattr(resume, "_resume_workflow_with_writer_lock_held")
    assert resume.resume_workflow(run_root.name) == 2
    assert any(record.getMessage().startswith(f"[{code}]") for record in caplog.records)
    if code != "memo_inconsistent":
        assert not any(record.getMessage().startswith("[memo_inconsistent]") for record in caplog.records)
    assert tree(run_root) == retained


@pytest.mark.parametrize("arguments", [
    ["run", "--prompt", "test", "--provider", "omp"],
    ["run", "--prompt", "test", "--provider", "omp", "--returns", '"String"'],
    ["run", "--prompt-file", "missing", "--provider", "omp", "--output", "answer"],
    ["run", "--scaffold", "missing"],
    ["import", "session", "--provider", "omp"],
    ["import", "session", "--reuse-run-contract"],
])
@pytest.mark.parametrize("occupied", [False, True])
def test_prompt_creation_refuses_before_inputs_scaffold_or_session_writes(tmp_path, arguments, occupied):
    if occupied:
        (tmp_path / "workflows" / "generated").mkdir(parents=True)
        (tmp_path / "workflows" / "generated" / "sentinel").write_bytes(b"historical scaffold")
        (tmp_path / ".orchestrate" / "runs" / "existing").mkdir(parents=True)
        (tmp_path / ".orchestrate" / "runs" / "existing" / "state.json").write_bytes(b"retained")
    before = tree(tmp_path)
    result = cli(tmp_path, "prompt", *arguments)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "prompt_execution_retired" in result.stderr
    assert tree(tmp_path) == before


@pytest.mark.parametrize("reuse", [False, True])
def test_direct_prompt_import_handler_has_the_same_refusal(tmp_path, monkeypatch, capsys, reuse):
    from orchestrator.cli.commands.prompt_import import prompt_import_workflow
    from orchestrator.cli.main import create_parser
    args = create_parser().parse_args(["prompt", "import", "absent", *(["--reuse-run-contract"] if reuse else ["--provider", "omp"])])
    monkeypatch.chdir(tmp_path)
    before = tree(tmp_path)
    assert prompt_import_workflow(args) == 2
    assert "prompt_execution_retired" in capsys.readouterr().err
    assert tree(tmp_path) == before


def test_evaluated_parent_refuses_old_child_without_child_run(tmp_path):
    from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture
    parent, source, refs = _public_fixture(tmp_path, child_target="2.24")
    result = cli(parent, "run", str(source), "--run-ref-root", str(refs))
    assert result.returncode != 0
    authority, memo = _authority(parent)
    assert memo.terminal.data["outcome"] == "failed"
    assert not memo.active_commits
    assert memo.terminal.data["code"] == "trial_program_compile_rejected"
    assert not list(refs.rglob("state.json"))
    assert not list(refs.rglob("run.json"))


def test_staged_child_refuses_before_decode_stage_or_execution(tmp_path):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref import child
    assert not hasattr(child, "_target_bundle")
    before = tree(tmp_path)
    with pytest.raises(ValueError) as caught:
        child.execute_request(SimpleNamespace())
    assert caught.value.code == "workflow_execution_target_retired"
    assert tree(tmp_path) == before


def test_retired_python_execution_exports_and_trial_sdk(tmp_path):
    import importlib.util
    import orchestrator.workflow as workflow
    import orchestrator.workflow_lisp as frontend
    from orchestrator.state import StateManager
    assert "WorkflowExecutor" not in workflow.__all__
    assert not hasattr(workflow, "WorkflowExecutor")
    assert "lower_workflow_definitions" not in frontend.__all__
    assert not hasattr(frontend, "lower_workflow_definitions")
    assert importlib.util.find_spec("orchestrator.workflow.trial.sdk") is None
    assert importlib.util.find_spec("orchestrator.workflow.executor") is None
    assert not hasattr(StateManager, "initialize")


def test_trial_cli_refuses_before_source_reads_or_publication(tmp_path):
    before = tree(tmp_path)
    result = cli(tmp_path, "trial", "missing.orc", "--entry-workflow", "run",
                 "--run-ref-root", str(tmp_path / "children"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "workflow_execution_target_retired" in result.stderr
    assert "Traceback" not in result.stderr
    assert tree(tmp_path) == before


def test_public_historical_report_derives_status_without_self_healing(tmp_path):
    from datetime import datetime, timedelta, timezone
    run = tmp_path / ".orchestrate" / "runs" / "historical"
    run.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"schema_version": "2.1", "run_id": "historical",
        "workflow_file": "missing.orc", "status": "running", "context": {},
        "updated_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "steps": {"task": {"status": "pending"}}}))
    (run / "state.json").chmod(0o640)
    before = tree(tmp_path)
    result = cli(tmp_path, "report", "--run-id", "historical", "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run"]["status"] == "failed"
    assert tree(tmp_path) == before


def test_supported_public_evaluated_lifecycle_has_no_retired_imports(tmp_path):
    from tests.test_workflow_evaluated_invalidate import _fixture

    _fixture(tmp_path, 20)
    result = cold_python(tmp_path, r'''
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
os.chdir(root)
from orchestrator.cli.main import main

def invoke(arguments):
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(StringIO()):
        status = main(arguments)
    return status, output.getvalue()

source = str(root / "invalidate_public.orc")
boundaries = str(root / "commands.json")
assert invoke(["compile", source, "--command-boundaries-file", boundaries])[0] == 0
assert invoke(["run", source, "--command-boundaries-file", boundaries])[0] == 0
run_root, = (root / ".orchestrate" / "runs").iterdir()
rows = [json.loads(line) for line in (run_root / "memo.jsonl").read_text().splitlines()]
commits = [row for row in rows if row["record"] == "committed"]
assert len(commits) == 3
assert invoke(["resume", run_root.name])[0] == 0

status, output = invoke(["report", "--run-id", run_root.name, "--format", "json"])
assert status == 0
assert json.loads(output)["run"]["status"] == "completed"

status, output = invoke(["invalidate", run_root.name, commits[1]["identity"]])
assert status == 0
assert json.loads(output)["record"] == "invalidated"
status, output = invoke(["report", "--run-id", run_root.name, "--format", "json"])
assert status == 0
assert json.loads(output)["run"]["status"] == "interrupted"

assert invoke(["resume", run_root.name])[0] == 0
assert (root / "dispatches.txt").read_text().splitlines() == [
    "prefix", "writer", "reader", "writer", "reader"
]
status, output = invoke(["report", "--run-id", run_root.name, "--format", "json"])
assert status == 0
assert json.loads(output)["run"]["status"] == "completed"
''')
    assert result.returncode == 0, result.stdout + result.stderr


def test_historical_state_profiles_and_report_are_cold_and_read_only(tmp_path):
    runs_root = tmp_path / ".orchestrate" / "runs"
    for label in ("absent", "exact", "unknown", "null"):
        run_id = "historical-" + label
        run_root = runs_root / run_id
        run_root.mkdir(parents=True)
        state = {
            "schema_version": "2.1",
            "run_id": run_id,
            "workflow_file": "source-not-present.orc",
            "workflow_checksum": "sha256:historical",
            "started_at": "2026-10-01T00:00:00+00:00",
            "updated_at": "2026-10-01T00:00:01+00:00",
            "status": "completed",
            "steps": {"Kept": {"status": "completed", "output": "retained"}},
            "call_frames": {"child": {"workflow_name": "child::run"}},
            "artifact_versions": {"result": [{"version": 1, "value": "retained"}]},
        }
        if label != "absent":
            state["result_persistence_profile"] = {
                "exact": "derived_pure_replay.v1",
                "unknown": "derived_pure_replay.v2",
                "null": None,
            }[label]
        state_file = run_root / "state.json"
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        state_file.chmod(0o640)

    before = tree(tmp_path)
    result = cold_python(tmp_path, r'''
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
from orchestrator.state import StateManager

expected = {
    "absent": None,
    "exact": "derived_pure_replay.v1",
    "unknown": "derived_pure_replay.v2",
    "null": None,
}
for label, profile in expected.items():
    run_id = "historical-" + label
    manager = StateManager(root, run_id=run_id)
    try:
        state = manager.load()
    except ValueError as exc:
        assert label in {"unknown", "null"}
        assert "profile" in str(exc)
    else:
        assert label in {"absent", "exact"}
        assert state.result_persistence_profile == profile
        assert state.steps["Kept"]["output"] == "retained"
        assert state.call_frames["child"]["workflow_name"] == "child::run"
        assert state.artifact_versions["result"][0]["value"] == "retained"

from orchestrator.cli.main import main
for label in expected:
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(StringIO()):
        status = main(["report", "--run-id", "historical-" + label,
            "--runs-root", str(root / ".orchestrate" / "runs"), "--format", "json"])
    assert status == 0
    report = json.loads(output.getvalue())
    assert report["run"]["run_id"] == "historical-" + label
    assert report["run"]["status"] == "completed"
    assert report["steps"][0]["name"] == "Kept"
''')
    assert tree(tmp_path) == before
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("module", ["orchestrator.prompt_session", "orchestrator.prompt_scaffold",
    "orchestrator.prompt_resume", "orchestrator.prompt_resume_preflight", "orchestrator.cli.main"])
def test_native_prompt_imports_do_not_load_workflow_compiler_or_executor(tmp_path, module):
    from tests.test_workflow_closed_program_isolation import BLOCK_COMPILER
    script = BLOCK_COMPILER + '''
import importlib
module = importlib.import_module(sys.argv[1])
assert "orchestrator.workflow.executor" not in sys.modules
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, module], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_prompt_cli_tty_gate_without_compiler_or_executor(tmp_path):
    from tests.test_workflow_closed_program_isolation import BLOCK_COMPILER
    script = BLOCK_COMPILER + '''
from orchestrator.cli.main import main
assert main(["prompt", "resume", "absent"]) == 1
assert "orchestrator.workflow.executor" not in sys.modules
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
'''
    before = tree(tmp_path)
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prompt_resume_tty_required" in result.stderr
    assert tree(tmp_path) == before


@pytest.mark.parametrize("provider", ["omp", "omp_unrestricted_workspace", "omp_no_tools", "omp_conf"])
def test_native_historical_fixture_setup_lookup_and_verifiers_under_blocker(tmp_path, provider):
    from tests.test_workflow_closed_program_isolation import BLOCK_COMPILER
    script = BLOCK_COMPILER + '''
class RetiredNativeOwnerBlocker(CompilerImportBlocker):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"orchestrator.workflow.executor", "orchestrator.workflow.pure_result_replay",
                "orchestrator.workflow.lowering"}:
            raise ModuleNotFoundError("retired native dependency blocked: " + fullname)
        return super().find_spec(fullname, path, target)
sys.meta_path.insert(0, RetiredNativeOwnerBlocker())
for name in ("orchestrator.workflow.executor", "orchestrator.workflow.pure_result_replay",
        "orchestrator.workflow.lowering"):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:
        assert "retired native dependency blocked" in str(exc)
    else:
        raise AssertionError("native blocker missed " + name)
from pathlib import Path
import os
from tests.test_prompt_resume import _resume_setup
from orchestrator.prompt_session import resolve_prompt_session
from orchestrator.prompt_session_scaffold import verify_private_scaffold, verify_captured_occupant
manager, setup = _resume_setup(Path(sys.argv[1]), provider=sys.argv[2])
resolved = resolve_prompt_session(manager.run_root.parent, "run-1")
assert resolved.link.document["provider"]["name"] == sys.argv[2]
private = os.open(manager.run_root / "prompt-inputs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
public = os.open(setup[1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    verification = verify_private_scaffold(private, resolved.link)
    verify_captured_occupant(private, verification, private=True)
    verify_captured_occupant(public, verification, private=False)
finally:
    os.close(private)
    os.close(public)
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
assert not any(name in sys.modules for name in ("orchestrator.workflow.executor",
    "orchestrator.workflow.pure_result_replay", "orchestrator.workflow.lowering"))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(tmp_path), provider], cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("in_place", [False, True], ids=["fork", "in-place"])
def test_native_prompt_resume_real_cli_dispatch_under_compiler_blocker(tmp_path, in_place):
    import select
    from tests.test_workflow_closed_program_isolation import BLOCK_COMPILER
    from tests.test_prompt_resume import _bridge_env, _records
    from types import SimpleNamespace
    from tests.test_prompt_resume_child import PRIMARY, _launcher

    prepare = subprocess.run([sys.executable, "-B", "-c", BLOCK_COMPILER +
        "\nfrom pathlib import Path\nfrom tests.test_prompt_resume import _resume_setup\n_resume_setup(Path(sys.argv[1]))\n"
        "assert not any(name.startswith('orchestrator.workflow_lisp') for name in sys.modules)\n"
        "assert 'orchestrator.workflow.executor' not in sys.modules\n", str(tmp_path)], cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr
    manager = SimpleNamespace(workspace=tmp_path / "workspace",
        run_root=tmp_path / "workspace" / ".orchestrate" / "runs" / "run-1")
    live = manager.run_root / "provider_sessions" / "task__v1"
    source = (live / PRIMARY).read_bytes()
    fake = tmp_path / "fake-omp"
    fake.write_bytes(_launcher().read_bytes())
    fake.chmod(0o500)
    script = BLOCK_COMPILER + '''
import hashlib
from dataclasses import replace
from pathlib import Path
import orchestrator.prompt_resume as bridge
from orchestrator.cli.main import main
fake = sys.argv[1]
bridge.OMP_BINARY_PIN = replace(bridge.OMP_BINARY_PIN,
    executable_sha256=hashlib.sha256(Path(fake).read_bytes()).hexdigest())
bridge.resolve_omp_binary = lambda env: fake
code = main(["prompt", "resume", "run-1", *sys.argv[2:]])
assert "orchestrator.workflow.executor" not in sys.modules
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
raise SystemExit(code)
'''
    env = {**_bridge_env(tmp_path), "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    master_in, slave_in = os.openpty()
    master_out, slave_out = os.openpty()
    proc = subprocess.Popen([sys.executable, "-B", "-c", script, str(fake), *(["--in-place"] if in_place else [])],
        cwd=manager.workspace, env=env, stdin=slave_in, stdout=slave_out, stderr=slave_out, close_fds=True)
    os.close(slave_in)
    os.close(slave_out)
    output = b""
    try:
        os.write(master_in, b'{"fake":1,"id":"99999999-9999-7999-8999-999999999999"}\n')
        while proc.poll() is None:
            ready, _, _ = select.select([master_out], [], [], 30)
            assert ready, "native prompt CLI did not settle"
            try:
                chunk = os.read(master_out, 1 << 16)
            except OSError:
                break
            output += chunk
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        os.close(master_in)
        os.close(master_out)
    assert proc.returncode == 0, output.decode(errors="replace")
    assert b"FAKE_DONE 1" in output
    (record_path,) = _records(manager)
    record = json.loads(record_path.read_bytes())
    assert record["status"] == "success"
    assert record["mode"] == ("in_place" if in_place else "fork")
    assert record["source"]["journal_sha256"] == hashlib.sha256(source).hexdigest()
    result_bytes = (live / record["result"]["primary_basename"]).read_bytes()
    assert record["result"]["journal_sha256"] == hashlib.sha256(result_bytes).hexdigest()
    if in_place:
        assert record["result"]["primary_basename"] == PRIMARY
        assert result_bytes.startswith(source) and len(result_bytes) > len(source)
    else:
        assert (live / PRIMARY).read_bytes() == source
        assert record["result"]["primary_basename"] != PRIMARY
