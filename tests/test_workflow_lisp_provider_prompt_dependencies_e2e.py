"""Functional end-to-end coverage for typed prompt dependencies."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.prompt_dependency_evidence import (
    evidence_relative_path,
    validate_index,
    validate_success_evidence,
    validate_terminal_evidence,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "provider_prompt_dependencies"
    / "mixed.orc"
)


class _ProviderBoundaryInterruption(BaseException):
    pass


class _AttemptInterruption(BaseException):
    pass


@contextmanager
def _guard_prior_evidence_access(prior_paths: set[Path]):
    """Reject runtime reads or enumeration of an earlier attempt's evidence."""

    prior = {os.path.abspath(os.fspath(path)) for path in prior_paths}
    enumeration_roots: set[str] = set()
    for path in prior_paths:
        parent = path.parent
        while True:
            enumeration_roots.add(os.path.abspath(os.fspath(parent)))
            if parent.name == "prompt_dependencies" or parent.parent == parent:
                break
            parent = parent.parent

    def _absolute(value) -> str | None:
        if not isinstance(value, (str, os.PathLike)):
            return None
        return os.path.abspath(os.fspath(value))

    def _reject_read(value) -> None:
        if _absolute(value) in prior:
            raise AssertionError("prior evidence read")

    def _reject_enumeration(value) -> None:
        if _absolute(value) in enumeration_roots:
            raise AssertionError("prior evidence enumeration")

    original_path_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_iterdir = Path.iterdir
    original_glob = Path.glob
    original_rglob = Path.rglob
    original_builtin_open = builtins.open
    original_os_open = os.open
    original_listdir = os.listdir
    original_scandir = os.scandir

    def _path_open(path: Path, *args, **kwargs):
        _reject_read(path)
        return original_path_open(path, *args, **kwargs)

    def _read_bytes(path: Path):
        _reject_read(path)
        return original_read_bytes(path)

    def _read_text(path: Path, *args, **kwargs):
        _reject_read(path)
        return original_read_text(path, *args, **kwargs)

    def _iterdir(path: Path):
        _reject_enumeration(path)
        return original_iterdir(path)

    def _glob(path: Path, *args, **kwargs):
        _reject_enumeration(path)
        return original_glob(path, *args, **kwargs)

    def _rglob(path: Path, *args, **kwargs):
        _reject_enumeration(path)
        return original_rglob(path, *args, **kwargs)

    def _builtin_open(file, *args, **kwargs):
        _reject_read(file)
        return original_builtin_open(file, *args, **kwargs)

    def _os_open(path, flags, *args, **kwargs):
        if flags & os.O_ACCMODE != os.O_WRONLY:
            _reject_read(path)
        return original_os_open(path, flags, *args, **kwargs)

    def _listdir(path="."):
        _reject_enumeration(path)
        return original_listdir(path)

    def _scandir(path="."):
        _reject_enumeration(path)
        return original_scandir(path)

    with ExitStack() as stack:
        stack.enter_context(patch.object(Path, "open", _path_open))
        stack.enter_context(patch.object(Path, "read_bytes", _read_bytes))
        stack.enter_context(patch.object(Path, "read_text", _read_text))
        stack.enter_context(patch.object(Path, "iterdir", _iterdir))
        stack.enter_context(patch.object(Path, "glob", _glob))
        stack.enter_context(patch.object(Path, "rglob", _rglob))
        stack.enter_context(patch.object(builtins, "open", _builtin_open))
        stack.enter_context(patch.object(os, "open", _os_open))
        stack.enter_context(patch.object(os, "listdir", _listdir))
        stack.enter_context(patch.object(os, "scandir", _scandir))
        yield


def test_prior_evidence_guard_blocks_reads_hash_inputs_and_enumeration(
    tmp_path: Path,
) -> None:
    evidence_dir = (
        tmp_path
        / "workflow_lisp"
        / "prompt_dependencies"
        / "step"
        / "visit"
    )
    evidence_dir.mkdir(parents=True)
    prior = evidence_dir / "attempt-000001.json"
    prior.write_bytes(b"prior evidence")
    fresh = evidence_dir / "attempt-000002.json"

    with _guard_prior_evidence_access({prior}):
        with pytest.raises(AssertionError, match="prior evidence read"):
            prior.read_bytes()
        with pytest.raises(AssertionError, match="prior evidence read"):
            hashlib.sha256(prior.read_bytes()).hexdigest()
        with pytest.raises(AssertionError, match="prior evidence enumeration"):
            list(evidence_dir.iterdir())
        with pytest.raises(AssertionError, match="prior evidence enumeration"):
            list((tmp_path / "workflow_lisp" / "prompt_dependencies").rglob("*.json"))
        fresh.write_bytes(b"fresh evidence")

    assert fresh.read_bytes() == b"fresh evidence"


def _compile_mixed_e2e(workspace: Path, *, resumable: bool = False):
    module_path = workspace / "provider_prompt_dependencies" / "mixed.orc"
    module_path.parent.mkdir(parents=True)
    source = FIXTURE.read_text(encoding="utf-8")
    entry_workflow = "mixed-e2e"
    if resumable:
        entry_workflow = "mixed-resume-e2e"
        source = source.replace(
            "invoke-provider mixed mixed-e2e)",
            "invoke-provider mixed mixed-e2e mixed-resume-e2e)",
            1,
        )
        assert source.endswith(")\n")
        source = source[:-2] + """
  (defworkflow mixed-resume-e2e
    ((inputs E2eDependencyInputs))
    -> WorkResult
    (let* ((seed-value
             (command-result seed
               :argv ("python" "seed.py")
               :returns Bool))
           (provider-result-value
             (provider-result providers.execute
               :prompt prompts.execute
               :inputs (seed-value)
               :prompt-dependencies
                 (:required
                    (inputs.required_a
                     inputs.required_b
                     inputs.required_c
                     inputs.required_d)
                  :optional (inputs.optional)
                  :position append
                  :instruction "Use the supplied dependency set.")
               :returns WorkResult)))
      (command-result finish
        :argv ("python" "finish.py")
        :returns WorkResult))))
"""
    module_path.write_text(source, encoding="utf-8")
    (workspace / "finish.py").write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        'target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        'target.write_text(json.dumps({"approved": True, '
        '"summary": "DOWNSTREAM_RESULT_SENTINEL"}) + "\\n", encoding="utf-8")\n',
        encoding="utf-8",
    )
    (workspace / "seed.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        'target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        'target.write_text("true\\n", encoding="utf-8")\n',
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={"providers.execute": "capturing-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        command_boundaries={
            "seed": ExternalToolBinding(
                name="seed",
                stable_command=("python", "seed.py"),
            ),
            "finish": ExternalToolBinding(
                name="finish",
                stable_command=("python", "finish.py"),
            )
        },
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = next(
        candidate
        for name, candidate in result.validated_bundles_by_name.items()
        if name == entry_workflow or name.endswith(f"::{entry_workflow}")
    )
    return module_path, bundle


def _compile_call_frame_e2e(workspace: Path):
    module_root = workspace / "provider_prompt_dependencies"
    module_root.mkdir(parents=True)
    module_path = module_root / "mixed.orc"
    module_path.write_bytes(FIXTURE.read_bytes())
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        entry_workflow="dependency-call-root",
        provider_externs={"providers.execute": "capturing-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )
    bundle = next(
        candidate
        for name, candidate in result.validated_bundles_by_name.items()
        if name == "dependency-call-root" or name.endswith("::dependency-call-root")
    )
    return module_path, bundle


def _bind_inputs(bundle, workspace: Path) -> dict[str, object]:
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    return bind_workflow_inputs(
        contracts,
        {
            "inputs__required_a": "artifacts/work/a.md",
            "inputs__required_b": "artifacts/work/b.md",
            "inputs__required_c": "artifacts/work/c.md",
            "inputs__required_d": "artifacts/work/d.md",
            "inputs__optional": "artifacts/context/absent.md",
        },
        workspace,
    )


@pytest.mark.parametrize("relative_workflow_file", [False, True])
def test_real_orc_two_level_call_publishes_root_owned_attempt_scope(
    tmp_path: Path,
    relative_workflow_file: bool,
) -> None:
    module_path, bundle = _compile_call_frame_e2e(tmp_path)
    (module_path.parent / "prompt.md").write_text(
        "CALL_BASE_SENTINEL\n", encoding="utf-8"
    )
    required = tmp_path / "artifacts" / "work" / "required.md"
    required.parent.mkdir(parents=True)
    required.write_text("CALL_REQUIRED_SENTINEL\n", encoding="utf-8")
    optional = tmp_path / "artifacts" / "context" / "optional.md"
    optional.parent.mkdir(parents=True)
    optional.write_text("CALL_OPTIONAL_SENTINEL\n", encoding="utf-8")

    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "inputs__required": "artifacts/work/required.md",
            "inputs__optional": "artifacts/context/optional.md",
        },
        tmp_path,
    )
    manager = StateManager(tmp_path, run_id="two-level-call-scope")
    workflow_file = (
        module_path.relative_to(tmp_path).as_posix()
        if relative_workflow_file
        else module_path.as_posix()
    )
    manager.initialize(
        workflow_file,
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    def _prepare(_self, *_args, **kwargs):
        return SimpleNamespace(
            input_mode="stdin",
            prompt=kwargs.get("prompt_content", ""),
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "CALL_RESULT_SENTINEL"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        completed = WorkflowExecutor(
            bundle, tmp_path, manager, retry_delay_ms=0
        ).execute(on_error="stop")

    assert completed["status"] == "completed"
    outer_call = next(
        node for node in bundle.ir.nodes.values() if node.kind == ExecutableNodeKind.CALL_BOUNDARY
    )
    middle = bundle.imports[outer_call.call_alias]
    inner_call = next(
        node for node in middle.ir.nodes.values() if node.kind == ExecutableNodeKind.CALL_BOUNDARY
    )
    leaf = middle.imports[inner_call.call_alias]
    provider = next(
        node for node in leaf.ir.nodes.values() if node.kind == ExecutableNodeKind.PROVIDER
    )
    first_frame = f"{outer_call.step_id}::visit::1"
    second_frame = f"{first_frame}.{inner_call.step_id}::visit::1"

    root_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    allocation = next(iter(root_state["provider_attempt_allocations"].values()))
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    assert scope.resume_scope.root_workflow_file == root_state["workflow_file"]
    assert scope.resume_scope.call_frame_ids == (first_frame, second_frame)
    assert scope.runtime_step_id == provider.step_id
    assert scope.enclosing_step.to_dict() == {
        "step_name": provider.presentation_name,
        "step_id": provider.step_id,
        "visit_count": 1,
    }
    assert scope.loop_iteration is None
    assert scope.adjudication_subject is None
    assert allocation["last_allocated_ordinal"] == 1
    assert [event["event"] for event in allocation["events"]] == [
        "allocated",
        "evidence_published",
    ]
    middle_state = root_state["call_frames"][first_frame]["state"]
    leaf_state = middle_state["call_frames"][second_frame]["state"]
    assert "provider_attempt_allocations" not in middle_state
    assert "provider_attempt_allocations" not in leaf_state
    publication = allocation["events"][1]
    record_path = manager.run_root / publication["relative_path"]
    assert record_path.is_file()
    assert not (Path(middle_state["run_root"]) / publication["relative_path"]).exists()
    assert not (Path(leaf_state["run_root"]) / publication["relative_path"]).exists()
    terminal = validate_terminal_evidence(manager.run_root, manager.state_file)
    assert len(terminal.index["publications"]) == 1


def test_real_orc_mixed_dependencies_execute_and_validate_terminal_evidence(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path)
    (module_path.parent / "prompt.md").write_text(
        "BASE_PROMPT_SENTINEL\n", encoding="utf-8"
    )
    for name, sentinel in (
        ("a.md", "DEPENDENCY_A_SENTINEL"),
        ("b.md", "DEPENDENCY_B_SENTINEL"),
        ("c.md", "DEPENDENCY_C_SENTINEL"),
        ("d.md", "DEPENDENCY_D_SENTINEL"),
    ):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sentinel + "\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id="mixed-e2e")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    captured: dict[str, object] = {"preparations": 0, "executions": 0}

    def _prepare(_self, *_args, **kwargs):
        captured["preparations"] = int(captured["preparations"]) + 1
        captured["prompt"] = kwargs.get("prompt_content", "")
        captured["env"] = kwargs.get("env") or {}
        return SimpleNamespace(
            input_mode="stdin",
            prompt=captured["prompt"],
            env=captured["env"],
        ), None

    def _execute(_self, invocation, **_kwargs):
        captured["executions"] = int(captured["executions"]) + 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "RESULT_SENTINEL"}) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"provider-observability",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    prompt = str(captured["prompt"])
    ordered_sentinels = [
        "BASE_PROMPT_SENTINEL",
        "DEPENDENCY_A_SENTINEL",
        "DEPENDENCY_B_SENTINEL",
        "DEPENDENCY_C_SENTINEL",
        "DEPENDENCY_D_SENTINEL",
    ]
    assert all(prompt.count(sentinel) == 1 for sentinel in ordered_sentinels)
    assert [prompt.index(sentinel) for sentinel in ordered_sentinels] == sorted(
        prompt.index(sentinel) for sentinel in ordered_sentinels
    )
    assert captured["preparations"] == 1
    assert captured["executions"] == 1
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__approved": True,
        "return__summary": "RESULT_SENTINEL",
    }

    allocations = json.loads(manager.state_file.read_text(encoding="utf-8"))[
        "provider_attempt_allocations"
    ]
    assert len(allocations) == 1
    allocation = next(iter(allocations.values()))
    publications = [
        event for event in allocation["events"] if event["event"] == "evidence_published"
    ]
    assert allocation["last_allocated_ordinal"] == 1
    assert len(publications) == 1
    record_path = manager.run_root / publications[0]["relative_path"]
    record = validate_success_evidence(json.loads(record_path.read_text(encoding="ascii")))
    assert [row["status"] for row in record["authored_rows"]] == [
        "present",
        "present",
        "present",
        "present",
        "absent",
    ]
    assert record["injection"]["position"] == "append"
    assert record["final_prompt"] == {
        "bytes": len(prompt.encode("utf-8")),
        "sha256": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }
    compiler_contract = next(
        node.execution_config.compiler_prompt_dependency_contract
        for node in bundle.ir.nodes.values()
        if node.execution_config.compiler_prompt_dependency_contract is not None
    )
    assert record["compiler_contract"]["source_workflow_sha256"] == (
        "sha256:" + hashlib.sha256(module_path.read_bytes()).hexdigest()
    )
    assert record["compiler_contract"]["normalized_contract_sha256"] == (
        compiler_contract.normalized_contract_sha256
    )

    terminal = validate_terminal_evidence(manager.run_root, manager.state_file)
    assert validate_index(json.loads(terminal.payload)) == terminal.index
    assert len(terminal.index["publications"]) == 1
    assert terminal.index["allocation_only_gaps"] == []


@pytest.mark.parametrize("evidence_disposition", ["deleted", "corrupt"])
def test_completed_provider_boundary_reuse_ignores_prior_evidence_and_dependencies(
    tmp_path: Path,
    evidence_disposition: str,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "RESUME_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"RESUME_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id=f"completed-reuse-{evidence_disposition}")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    calls = {"preparations": 0, "executions": 0}

    def _prepare(_self, *_args, **kwargs):
        calls["preparations"] += 1
        return SimpleNamespace(
            input_mode="stdin",
            prompt=kwargs.get("prompt_content", ""),
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        calls["executions"] += 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "REUSED_RESULT_SENTINEL"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    original_emit = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def _interrupt_after_provider(self, state, step_name, step, finalized):
        original_emit(self, state, step_name, step, finalized)
        if finalized.get("artifacts", {}).get("summary") == "REUSED_RESULT_SENTINEL":
            raise _ProviderBoundaryInterruption

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        _interrupt_after_provider,
    ):
        with pytest.raises(_ProviderBoundaryInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    publication = next(
        event
        for allocation in persisted["provider_attempt_allocations"].values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    )
    record_path = manager.run_root / publication["relative_path"]
    if evidence_disposition == "deleted":
        record_path.unlink()
    else:
        record_path.write_bytes(b"accidental partial write")
    (tmp_path / "artifacts" / "work" / "a.md").unlink()
    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()

    with _guard_prior_evidence_access({record_path}), patch.object(
        StateManager,
        "allocate_provider_attempt",
        side_effect=AssertionError("completed boundary must not allocate"),
    ), patch(
        "orchestrator.workflow.executor.snapshot_content_dependencies",
        side_effect=AssertionError("completed boundary must not snapshot"),
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError("completed boundary must not prepare"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("completed boundary must not execute"),
    ):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(
            resume=True,
            on_error="stop",
        )

    assert calls == {"preparations": 1, "executions": 1}
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {
        "return__approved": True,
        "return__summary": "DOWNSTREAM_RESULT_SENTINEL",
    }
    with pytest.raises(ValueError, match="missing|corrupt"):
        validate_terminal_evidence(manager.run_root, manager.state_file)


def test_resume_after_allocation_gap_uses_fresh_snapshot_and_next_ordinal(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "CRASH_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"CRASH_OLD_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id="allocation-gap-resume")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    import orchestrator.workflow.executor as executor_module

    original_snapshot = executor_module.snapshot_content_dependencies
    snapshot_calls = 0

    def _interrupt_first_snapshot(*args, **kwargs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 1:
            raise _AttemptInterruption
        return original_snapshot(*args, **kwargs)

    captured: dict[str, object] = {"preparations": 0, "executions": 0}

    def _prepare(_self, *_args, **kwargs):
        captured["preparations"] = int(captured["preparations"]) + 1
        captured["prompt"] = kwargs.get("prompt_content", "")
        return SimpleNamespace(
            input_mode="stdin",
            prompt=captured["prompt"],
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        captured["executions"] = int(captured["executions"]) + 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "CRASH_PROVIDER_RESULT"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(
        executor_module,
        "snapshot_content_dependencies",
        _interrupt_first_snapshot,
    ), patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        with pytest.raises(_AttemptInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    interrupted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    allocation = next(iter(interrupted["provider_attempt_allocations"].values()))
    assert allocation["last_allocated_ordinal"] == 1
    assert [event["event"] for event in allocation["events"]] == ["allocated"]
    (tmp_path / "artifacts" / "work" / "b.md").write_text(
        "CRASH_FRESH_B_SENTINEL\n", encoding="utf-8"
    )

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        executor_module,
        "snapshot_content_dependencies",
        _interrupt_first_snapshot,
    ), patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert captured["preparations"] == 1
    assert captured["executions"] == 1
    assert "CRASH_FRESH_B_SENTINEL" in str(captured["prompt"])
    assert "CRASH_OLD_b.md_SENTINEL" not in str(captured["prompt"])
    terminal = validate_terminal_evidence(resume_manager.run_root, resume_manager.state_file)
    assert [row["attempt_ordinal"] for row in terminal.index["allocation_only_gaps"]] == [1]
    assert [row["attempt_ordinal"] for row in terminal.index["publications"]] == [1]
    assert (
        terminal.index["allocation_only_gaps"][0]["scope_sha256"]
        != terminal.index["publications"][0]["scope_sha256"]
    )


@pytest.mark.parametrize("evidence_disposition", ["deleted", "corrupt"])
def test_pending_resume_ignores_accidentally_unreadable_prior_evidence(
    tmp_path: Path,
    evidence_disposition: str,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "PENDING_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"PENDING_OLD_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id=f"pending-evidence-{evidence_disposition}")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    calls = {"preparations": 0, "executions": 0}
    captured: dict[str, str] = {}

    def _prepare(_self, *_args, **kwargs):
        calls["preparations"] += 1
        if calls["preparations"] == 1:
            raise _AttemptInterruption
        captured["prompt"] = kwargs.get("prompt_content", "")
        return SimpleNamespace(
            input_mode="stdin",
            prompt=captured["prompt"],
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        calls["executions"] += 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "PENDING_PROVIDER_RESULT"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        with pytest.raises(_AttemptInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    interrupted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    prior_publication = next(
        event
        for allocation in interrupted["provider_attempt_allocations"].values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    )
    prior_record = manager.run_root / prior_publication["relative_path"]
    if evidence_disposition == "deleted":
        prior_record.unlink()
    else:
        prior_record.write_bytes(b"accidental partial write")
    (tmp_path / "artifacts" / "work" / "c.md").write_text(
        "PENDING_FRESH_C_SENTINEL\n", encoding="utf-8"
    )

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with _guard_prior_evidence_access({prior_record}), patch.object(
        ProviderExecutor, "prepare_invocation", _prepare
    ), patch.object(ProviderExecutor, "execute", _execute):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert calls == {"preparations": 2, "executions": 1}
    assert "PENDING_FRESH_C_SENTINEL" in captured["prompt"]
    assert "PENDING_OLD_c.md_SENTINEL" not in captured["prompt"]
    completed = json.loads(resume_manager.state_file.read_text(encoding="utf-8"))
    publications = [
        event
        for allocation in completed["provider_attempt_allocations"].values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    ]
    assert len(publications) == 2
    with pytest.raises(ValueError, match="missing|corrupt"):
        validate_terminal_evidence(resume_manager.run_root, resume_manager.state_file)


def test_resume_ignores_orphan_record_created_before_publication_event(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "ORPHAN_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"ORPHAN_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id="orphan-record-resume")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    original_record = (
        StateManager._record_provider_attempt_publication_already_process_locked
    )
    record_calls = 0

    def _interrupt_before_event(self, *args, **kwargs):
        nonlocal record_calls
        record_calls += 1
        if record_calls == 1:
            raise _AttemptInterruption
        return original_record(self, *args, **kwargs)

    with patch.object(
        StateManager,
        "_record_provider_attempt_publication_already_process_locked",
        _interrupt_before_event,
    ):
        with pytest.raises(_AttemptInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    interrupted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    allocation = next(iter(interrupted["provider_attempt_allocations"].values()))
    assert [event["event"] for event in allocation["events"]] == ["allocated"]
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    orphan = manager.run_root / evidence_relative_path(scope, 1)
    assert orphan.is_file()

    calls = {"preparations": 0, "executions": 0}

    def _prepare(_self, *_args, **kwargs):
        calls["preparations"] += 1
        return SimpleNamespace(
            input_mode="stdin",
            prompt=kwargs.get("prompt_content", ""),
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        calls["executions"] += 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "ORPHAN_PROVIDER_RESULT"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with _guard_prior_evidence_access({orphan}), patch.object(
        ProviderExecutor, "prepare_invocation", _prepare
    ), patch.object(ProviderExecutor, "execute", _execute):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert calls == {"preparations": 1, "executions": 1}
    with pytest.raises(ValueError, match="orphan prompt dependency evidence"):
        validate_terminal_evidence(resume_manager.run_root, resume_manager.state_file)
    validated_indexes = (
        resume_manager.run_root
        / "workflow_lisp"
        / "prompt_dependencies"
        / "validated-indexes"
    )
    assert not validated_indexes.exists() or not list(validated_indexes.iterdir())


def test_resume_after_failed_allocation_persistence_reuses_first_ordinal(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "ALLOCATE_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"ALLOCATE_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id="allocation-persistence-resume")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    real_persist = manager._persist_state_durably
    interrupted = False

    def _interrupt_allocation_write():
        nonlocal interrupted
        assert manager.state is not None
        if not interrupted and manager.state.provider_attempt_allocations is not None:
            interrupted = True
            raise _AttemptInterruption
        real_persist()

    with patch.object(manager, "_persist_state_durably", _interrupt_allocation_write):
        with pytest.raises(_AttemptInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    disk_after_crash = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert "provider_attempt_allocations" not in disk_after_crash
    calls = {"preparations": 0, "executions": 0}

    def _prepare(_self, *_args, **kwargs):
        calls["preparations"] += 1
        return SimpleNamespace(
            input_mode="stdin",
            prompt=kwargs.get("prompt_content", ""),
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        calls["executions"] += 1
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "ALLOCATE_PROVIDER_RESULT"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert calls == {"preparations": 1, "executions": 1}
    terminal = validate_terminal_evidence(resume_manager.run_root, resume_manager.state_file)
    assert terminal.index["allocation_only_gaps"] == []
    assert [row["attempt_ordinal"] for row in terminal.index["publications"]] == [1]


def test_resume_after_provider_execution_interruption_uses_new_attempt_snapshot(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_mixed_e2e(tmp_path, resumable=True)
    (module_path.parent / "prompt.md").write_text(
        "EXECUTION_BASE_SENTINEL\n", encoding="utf-8"
    )
    for name in ("a.md", "b.md", "c.md", "d.md"):
        target = tmp_path / "artifacts" / "work" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"EXECUTION_OLD_{name}_SENTINEL\n", encoding="utf-8")

    manager = StateManager(tmp_path, run_id="execution-interruption-resume")
    manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bind_inputs(bundle, tmp_path),
    )
    calls = {"preparations": 0, "executions": 0}
    prompts: list[str] = []

    def _prepare(_self, *_args, **kwargs):
        calls["preparations"] += 1
        prompt = kwargs.get("prompt_content", "")
        prompts.append(prompt)
        return SimpleNamespace(
            input_mode="stdin",
            prompt=prompt,
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        calls["executions"] += 1
        if calls["executions"] == 1:
            raise _AttemptInterruption
        output = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"approved": True, "summary": "EXECUTION_PROVIDER_RESULT"})
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        with pytest.raises(_AttemptInterruption):
            WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute(
                on_error="stop"
            )

    interrupted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    prior_records = {
        manager.run_root / event["relative_path"]
        for allocation in interrupted["provider_attempt_allocations"].values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    }
    assert len(prior_records) == 1
    (tmp_path / "artifacts" / "work" / "d.md").write_text(
        "EXECUTION_FRESH_D_SENTINEL\n", encoding="utf-8"
    )
    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with _guard_prior_evidence_access(prior_records), patch.object(
        ProviderExecutor, "prepare_invocation", _prepare
    ), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        resumed = WorkflowExecutor(
            bundle, tmp_path, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert calls == {"preparations": 2, "executions": 2}
    assert "EXECUTION_OLD_d.md_SENTINEL" in prompts[0]
    assert "EXECUTION_FRESH_D_SENTINEL" in prompts[1]
    assert "EXECUTION_OLD_d.md_SENTINEL" not in prompts[1]
    terminal = validate_terminal_evidence(resume_manager.run_root, resume_manager.state_file)
    assert terminal.index["allocation_only_gaps"] == []
    assert [row["attempt_ordinal"] for row in terminal.index["publications"]] == [1, 1]
    assert len({row["scope_sha256"] for row in terminal.index["publications"]}) == 2
