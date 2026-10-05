from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_command_template_scopes import _assert_two_public_resumes
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.authority import publish_run_authority
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated import runtime as runtime_module
from orchestrator.workflow.evaluated.machine import site_classes as command_site_classes
from orchestrator.workflow.evaluated.memo import memo_writer_lock
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.test_workflow_lisp_command_adapters import _typed_adapter_manifest_payload


def _write_command_inputs(root: Path, values: dict) -> Path:
    path = root / "inputs.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def _write_boundaries(root: Path, rows: dict) -> Path:
    path = root / "commands.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _write_probe(root: Path, *, return_kind: str = "int") -> None:
    output = (
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("0", encoding="utf-8")'
        if return_kind == "int"
        else 'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"seen": json.dumps(sys.argv[1:])}), encoding="utf-8")'
    )
    (root / "probe.py").write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        'Path("argv.jsonl").open("a", encoding="utf-8").write(json.dumps(sys.argv[1:]) + "\\n")\n'
        + output + "\n",
        encoding="utf-8",
    )


def _run_entry(root: Path, source: Path, boundaries: Path, *extra: str):
    return _run_cli(
        root,
        str(source),
        "--source-root", str(root / "src"),
        "--entry-workflow", "r12/entry::run",
        "--command-boundaries-file", str(boundaries),
        *extra,
    )


def test_public_templates_keep_legacy_literals_and_runtime_strings_as_data(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "templates.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/templates) (export run)
          (defworkflow run ((n Int) (opaque String)) -> Int
            (command-result emit :argv ("python" "probe.py"
              true
              (let* ((alias true)) alias)
              (if true true false)
              (let* ((slot "${inputs.n}")) slot)
              opaque) :returns Int)))
''',
        encoding="utf-8",
    )
    _write_probe(tmp_path)
    boundaries = _write_boundaries(tmp_path, {
        "emit": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
    })
    inputs = _write_command_inputs(tmp_path, {"n": 7, "opaque": "${inputs.n}"})

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries), "--input-file", str(inputs))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == b'["True", "True", "true", "7", "${inputs.n}"]\n'
    _assert_two_public_resumes(tmp_path, tmp_path / "argv.jsonl")


SURFACE_232_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.32")
(defmodule r12/entry) (export run)
(defrecord Result (seen String))
(defunion Choice (A) (B))
(defproc helper ((state_root String)) -> Result
 :effects ((uses-command echo)) :lowering inline
 (command-result echo :argv ("python" "probe.py" state_root "${inputs.state_root}" ) :returns Result))
(defworkflow run ((state_root String :default "WORKFLOW") (other String :default "PROCEDURE") (choice Choice) (flag Bool :default true)) -> Result
 (loop/recur :max 1 :state (loop-state (i Int 0))
 :on-exhausted (record Result :seen "exhausted")
 (fn (st)
  (let* ((actual (command-result choose :argv ("python" "choose.py") :returns Choice)))(let* ((r (match actual
    ((A a) (if flag (helper other) (helper state_root)))
    ((B b) (helper other)))))
   (done (record Result :seen "finished"))))))))
'''


def test_public_target_232_surface_composition_retarget_keeps_exact_legacy_argv(tmp_path: Path) -> None:
    workspace = tmp_path / "surface232-retargeted"
    source = workspace / "src" / "r12" / "entry.orc"
    source.parent.mkdir(parents=True)
    retargeted = SURFACE_232_SOURCE.replace('(:target-dsl "2.32")', '(:target-dsl "2.35")')
    source.write_text(retargeted, encoding="utf-8")
    assert source.read_text(encoding="utf-8") == retargeted
    _write_probe(workspace, return_kind="record")
    (workspace / "choose.py").write_text(
        'import json, os\nfrom pathlib import Path\n'
        'with Path("choose-dispatches.jsonl").open("a", encoding="utf-8") as marker:\n'
        '    marker.write("dispatch\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant": "A"}), encoding="utf-8")\n',
        encoding="utf-8",
    )
    boundaries = _write_boundaries(workspace, {
        "echo": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]},
        "choose": {"stable_command": ["python", "choose.py"], "closure": ["choose.py"]},
    })
    inputs = _write_command_inputs(workspace, {"choice": {"variant": "A"}})

    result = _run_entry(workspace, source, boundaries, "--input-file", str(inputs))

    assert result.returncode == 0, result.stderr
    assert (workspace / "argv.jsonl").read_bytes() == b'["PROCEDURE", "WORKFLOW"]\n'
    assert (workspace / "choose-dispatches.jsonl").read_bytes() == b"dispatch\n"
    _assert_two_public_resumes(
        workspace, workspace / "argv.jsonl", workspace / "choose-dispatches.jsonl"
    )


WCC_234_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
(defmodule r12/entry) (export run)
(defrecord Result (seen String)) (defunion Choice (A) (B))
(defproc helper ((state_root String)) -> Result
 :effects ((uses-command echo)) :lowering inline
 (command-result echo :argv ("python" "probe.py" state_root "${inputs.state_root}") :returns Result))
(defproc brancher ((state_root String) (flag Bool)) -> Result
 :effects ((uses-command echo) (uses-command choose)) :lowering inline
 (let* ((choice (command-result choose :argv ("python" "choose.py") :returns Choice)))
 (match choice
  ((A a) (if flag (helper state_root) (helper state_root)))
  ((B b) (helper state_root)))))
(defworkflow run ((state_root String :default "WORKFLOW") (other String :default "PROCEDURE") (flag Bool :default true)) -> Result
 (brancher other flag)))
'''


def test_public_default_wcc_guarded_composition_uses_selected_arm(tmp_path: Path) -> None:
    workspace = tmp_path / "wcc-guarded"
    source = workspace / "src" / "r12" / "entry.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        WCC_234_SOURCE.replace('(:target-dsl "2.34")', '(:target-dsl "2.35")'),
        encoding="utf-8",
    )
    _write_probe(workspace, return_kind="record")
    (workspace / "choose.py").write_text(
        'import json, os\nfrom pathlib import Path\n'
        'with Path("choose-dispatches.jsonl").open("a", encoding="utf-8") as marker:\n'
        '    marker.write("dispatch\\n")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant": "A"}), encoding="utf-8")\n',
        encoding="utf-8",
    )
    boundaries = _write_boundaries(workspace, {
        "echo": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]},
        "choose": {"stable_command": ["python", "choose.py"], "closure": ["choose.py"]},
    })

    result = _run_entry(workspace, source, boundaries)

    assert result.returncode == 0, result.stderr
    assert (workspace / "argv.jsonl").read_bytes() == b'["PROCEDURE", "WORKFLOW"]\n'
    assert (workspace / "choose-dispatches.jsonl").read_bytes() == b"dispatch\n"
    _assert_two_public_resumes(
        workspace, workspace / "argv.jsonl", workspace / "choose-dispatches.jsonl"
    )


@pytest.mark.parametrize(
    "choice,expected_exit,expected_argv",
    [({"variant": "A", "i": 6}, 0, b'["6"]\n'), ({"variant": "B"}, 1, None)],
    ids=["active-field", "inactive-field"],
)
def test_union_slot_selects_active_field_before_suffix_or_dispatch(
    tmp_path: Path, choice: dict, expected_exit: int, expected_argv: bytes | None
) -> None:
    source = tmp_path / "evaluated" / "union_slot.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/union_slot) (export run)
          (defunion Choice (A (i Int)) (B))
          (defworkflow run ((choice Choice)) -> Int
            (command-result emit :argv ("python" "probe.py" "${inputs.choice__i}") :returns Int)))
''',
        encoding="utf-8",
    )
    _write_probe(tmp_path)
    boundaries = _write_boundaries(tmp_path, {
        "emit": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
    })
    inputs = _write_command_inputs(tmp_path, {"choice": choice})

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries), "--input-file", str(inputs))

    assert result.returncode == expected_exit, result.stderr
    if expected_argv is None:
        assert "[undefined_variables]" in result.stderr
        assert not (tmp_path / "argv.jsonl").exists()
        (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
        records = [json.loads(line) for line in (run_root / "memo.jsonl").read_text().splitlines()]
        assert [row["record"] for row in records] == ["terminal"]
    else:
        assert (tmp_path / "argv.jsonl").read_bytes() == expected_argv
        _assert_two_public_resumes(tmp_path, tmp_path / "argv.jsonl")


def test_public_command_uses_explicit_workspace_when_state_dir_is_external(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "external_state.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/external_state) (export run)
          (defworkflow run () -> Int
            (command-result emit :argv ("python" "probe.py") :returns Int)))
''',
        encoding="utf-8",
    )
    _write_probe(tmp_path)
    boundaries = _write_boundaries(tmp_path, {
        "emit": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
    })
    state_dir = tmp_path.parent / f"{tmp_path.name}-state"

    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries), "--state-dir", str(state_dir))

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "argv.jsonl").read_bytes() == b"[]\n"
    (run_root,) = state_dir.iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(run_root / "memo.jsonl", command_site_classes(authority.program))
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == 0
    _assert_two_public_resumes(
        tmp_path, tmp_path / "argv.jsonl", state_dir=state_dir
    )


def _assert_certified_package_result(run_root: Path) -> None:
    authority = load_run_authority(run_root)
    snapshot = read_memo(run_root / "memo.jsonl", command_site_classes(authority.program))
    commit = next(entry.data for entry in snapshot.entries if entry.data["record"] == "committed")
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/findings.json",
    }
    assert commit["input_parts"]["argv"] == canonical_sha256([
        "python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
        "artifacts/work/carrier.json",
    ])
    assert commit["input_digest"] == canonical_sha256(commit["input_parts"])
    package_rows = [
        (json.loads(key), row)
        for key, row in commit["implementation_files"].items()
    ]
    assert any(key[0] == "package:orchestrator" and key[1] == "." for key, _row in package_rows)


def test_public_certified_adapter_uses_package_closure_without_bytecode_cache(tmp_path: Path) -> None:
    source = tmp_path / "evaluated" / "certified_adapter.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/certified_adapter) (export run)
          (defpath ReviewFindingsJsonPath :kind relpath :under "artifacts/work" :must-exist true)
          (defrecord ReviewFindings (schema_version String) (items_path ReviewFindingsJsonPath))
          (defworkflow run ((items ReviewFindingsJsonPath)) -> ReviewFindings
            (command-result validate_review_findings_v1
              :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items)
              :returns ReviewFindings)))
''',
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts" / "work"
    artifacts.mkdir(parents=True)
    (artifacts / "carrier.json").write_text(
        json.dumps({
            "schema_version": "ReviewFindings.v1",
            "items_path": "artifacts/work/findings.json",
        }),
        encoding="utf-8",
    )
    (artifacts / "findings.json").write_text('{"items": []}', encoding="utf-8")

    package_root = Path(runtime_module.__file__).resolve().parents[2]
    adapter_caches = package_root / "workflow_lisp" / "adapters" / "__pycache__"
    before_cache = sorted(path.name for path in adapter_caches.glob("validate_review_findings_v1*.pyc"))
    result = _run_cli(tmp_path, str(source), "--input", "items=artifacts/work/carrier.json")

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in adapter_caches.glob("validate_review_findings_v1*.pyc")) == before_cache
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    _assert_certified_package_result(run_root)
    _assert_two_public_resumes(tmp_path)


def test_public_certified_document_is_delivered_and_included_in_input_digest(tmp_path: Path) -> None:
    source = tmp_path / "src" / "r12" / "entry.orc"
    source.parent.mkdir(parents=True)
    fixture = Path(__file__).parent / "fixtures/workflow_lisp/valid/certified_adapter_call.orc"
    source.write_text(
        fixture.read_text(encoding="utf-8").replace(
            '(:target-dsl "2.14")',
            '(:target-dsl "2.35")\n  (defmodule r12/entry) (export normalize-summary)',
        ),
        encoding="utf-8",
    )
    report_paths = ["artifacts/work/exécution.json", "artifacts/work/review.json"]
    (tmp_path / "artifacts/work").mkdir(parents=True)
    for report in report_paths:
        (tmp_path / report).write_text("{}", encoding="utf-8")
    inputs = _write_command_inputs(tmp_path, {
        "completed": {"execution_report": report_paths[0]},
        "approved": {"review_report": report_paths[1]},
    })
    adapter = _typed_adapter_manifest_payload()["normalize_result"]
    adapter["closure"] = ["scripts/normalize_result.py"]
    boundaries = _write_boundaries(tmp_path, {"normalize_result": adapter})
    script = tmp_path / "scripts/normalize_result.py"
    script.parent.mkdir()
    script.write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        'document = sys.argv[-1].encode("utf-8")\n'
        'Path("adapter-document.bin").write_bytes(document)\n'
        'with Path("adapter-dispatches.jsonl").open("a", encoding="utf-8") as marker:\n'
        '    marker.write("dispatch\\n")\n'
        'Path("artifacts/work/summary.json").write_text("{}", encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('
        'json.dumps({"report": "artifacts/work/summary.json"}), encoding="utf-8")\n',
        encoding="utf-8",
    )

    result = _run_cli(
        tmp_path, str(source), "--source-root", str(tmp_path / "src"),
        "--entry-workflow", "r12/entry::normalize-summary",
        "--command-boundaries-file", str(boundaries), "--input-file", str(inputs),
    )

    assert result.returncode == 0, result.stderr
    expected_document = (
        '{"execution_report":"artifacts/work/exécution.json",'
        '"review_report":"artifacts/work/review.json"}'
    ).encode("utf-8")
    assert (tmp_path / "adapter-document.bin").read_bytes() == expected_document
    assert (tmp_path / "adapter-dispatches.jsonl").read_bytes() == b"dispatch\n"
    (run_root,) = (tmp_path / ".orchestrate/runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(run_root / "memo.jsonl", command_site_classes(authority.program))
    commit = next(entry.data for entry in snapshot.entries if entry.data["record"] == "committed")
    assert commit["input_parts"]["document"] == "sha256:" + hashlib.sha256(expected_document).hexdigest()
    assert commit["input_parts"]["argv"] == canonical_sha256([
        "python", "scripts/normalize_result.py", expected_document.decode("utf-8")
    ])
    assert commit["input_digest"] == canonical_sha256(commit["input_parts"])
    assert snapshot.terminal is not None and snapshot.terminal.data["outcome"] == "completed"
    _assert_two_public_resumes(
        tmp_path, tmp_path / "adapter-dispatches.jsonl", tmp_path / "adapter-document.bin"
    )


class _InterruptedAfterCommit(BaseException):
    pass


def test_committed_must_exist_path_can_be_rendered_after_artifact_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "evaluated" / "path_replay.orc"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule evaluated/path_replay) (export run)
          (defpath ArtifactPath :kind relpath :under "artifacts/work" :must-exist true)
          (defrecord Produced (path ArtifactPath))
          (defproc consume-path ((path ArtifactPath)) -> Int
            :effects ((uses-command consume)) :lowering private-workflow
            (command-result consume :argv ("python" "consume.py" "${inputs.path}") :returns Int))
          (defworkflow run () -> Int
            (let* ((produced (command-result produce :argv ("python" "produce.py") :returns Produced)))
              (consume-path produced.path))))
''',
        encoding="utf-8",
    )
    producer = tmp_path / "produce.py"
    producer.write_text(
        'import json, os\nfrom pathlib import Path\n'
        'Path("artifacts/work").mkdir(parents=True, exist_ok=True)\n'
        'Path("artifacts/work/output.json").write_text("{}", encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('
        'json.dumps({"path": "artifacts/work/output.json"}), encoding="utf-8")\n',
        encoding="utf-8",
    )
    consumer = tmp_path / "consume.py"
    consumer.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        'Path("received-path.txt").write_text(sys.argv[1], encoding="utf-8")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("9", encoding="utf-8")\n',
        encoding="utf-8",
    )
    boundaries = {
        name: ExternalToolBinding(
            name=name,
            stable_command=("python", f"{name}.py"),
            closure=(f"{name}.py",),
        )
        for name in ("produce", "consume")
    }
    program = build_closed_program(compile_typed_program(
        source,
        entry_workflow="evaluated/path_replay::run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries=boundaries,
    ))
    run_root = tmp_path / ".state" / "runs" / "run-1"
    with publish_run_authority(
        run_root,
        program,
        run_id="run-1",
        workflow_file="path_replay.orc",
        workflow_checksum="sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        resume_request={"source_roots": [], "entry_workflow": None,
            "provider_externs_path": None, "prompt_externs_path": None,
            "imported_workflow_bundles_path": None, "command_boundaries_path": None,
            "input_file": None, "input_overrides": {}},
        bound_inputs={},
    ) as authority:
        real_append = runtime_module.append_record
        interrupted = False

        def stop_after_first_commit(path, record, **kwargs):
            nonlocal interrupted
            entry = real_append(path, record, **kwargs)
            if record.get("record") == "committed" and not interrupted:
                interrupted = True
                raise _InterruptedAfterCommit()
            return entry

        with monkeypatch.context() as patched:
            patched.setattr(runtime_module, "append_record", stop_after_first_commit)
            with pytest.raises(_InterruptedAfterCommit):
                runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    authority = load_run_authority(run_root)
    checked_classes = command_site_classes(program)
    prior = read_memo(authority.memo_path, checked_classes)
    producer_commit = next(
        entry.data for entry in prior.entries if entry.data["record"] == "committed"
    )
    artifact = tmp_path / "artifacts/work/output.json"
    assert artifact.is_file()
    dispatches_before = prior.raw
    real_reuse = runtime_module._reuse_effect_commit

    def remove_artifact_before_path_reuse(*args, **kwargs):
        if inspect.signature(real_reuse).bind(*args, **kwargs).arguments["node"]["boundary"] == "produce":
            artifact.unlink()
        return real_reuse(*args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(runtime_module, "_reuse_effect_commit", remove_artifact_before_path_reuse)
        with memo_writer_lock(authority.run_root):
            exit_code, value = runtime_module.execute_pure_run(
                authority, {}, run_id="run-1", workspace=tmp_path
            )

    after = read_memo(authority.memo_path, checked_classes)
    commits = [entry.data for entry in after.entries if entry.data["record"] == "committed"]
    assert (exit_code, value) == (0, 9)
    assert not artifact.exists()
    assert (tmp_path / "received-path.txt").read_text(encoding="utf-8") == "artifacts/work/output.json"
    assert len(commits) == 2
    assert commits[0] == producer_commit
    assert commits[1]["input_parts"]["argv"] == canonical_sha256([
        "python", "consume.py", "artifacts/work/output.json"
    ])
    assert commits[1]["input_digest"] == canonical_sha256(commits[1]["input_parts"])
    assert commits[1]["depends_on"] == [commits[0]["identity"]]
    assert after.raw.startswith(dispatches_before)
    assert after.terminal is not None and after.terminal.data["value"] == 9
