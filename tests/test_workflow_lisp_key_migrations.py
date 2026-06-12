from __future__ import annotations

import hashlib
import json
import tempfile
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts, workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    validate_reusable_phase_state,
    write_reusable_phase_state_v1,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLES = WORKFLOWS / "examples"
MIGRATION_INPUTS = EXAMPLES / "inputs" / "workflow_lisp_migrations"
LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
LISP_INVALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"
EXPERIMENT_CTX_FIXTURE = LISP_FIXTURES / "context_generalization_experiment_ctx.orc"
RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE = LISP_FIXTURES / "context_generalization_runctx_only_drain_entry.orc"
STD_CONTEXT_IMPORT_FIXTURE = LISP_FIXTURES / "context_generalization_std_context_import.orc"
ANCHORLESS_STATE_PATH_FIXTURE = LISP_INVALID_FIXTURES / "context_generalization_anchorless_state_path.orc"
ROLELESS_BINDING_FIXTURE = LISP_INVALID_FIXTURES / "context_generalization_roleless_binding.orc"


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_short_name(name: str) -> str:
    return name.rsplit("::", 1)[-1]


def _workflow_public_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_public_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_context_inputs(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_context_inputs",
        lambda _: (),
    )
    return helper(bundle)


def _iter_nested_steps(steps):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case in match_block.get("cases", {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps", []))
        repeat_block = step.get("repeat_until")
        if isinstance(repeat_block, dict):
            yield from _iter_nested_steps(repeat_block.get("steps", []))
            exhausted_block = repeat_block.get("on_exhausted")
            if isinstance(exhausted_block, dict):
                yield from _iter_nested_steps(exhausted_block.get("steps", []))
        then_block = step.get("then")
        if isinstance(then_block, dict):
            yield from _iter_nested_steps(then_block.get("steps", []))
        else_block = step.get("else")
        if isinstance(else_block, dict):
            yield from _iter_nested_steps(else_block.get("steps", []))


def _structured_contract_fingerprint(
    *,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    return_type_name: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(structured_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"2.14:{return_type_name}:{structured_contract_kind}:{digest}"


def test_cycle_guard_demo_orc_compiles_with_bounded_loop(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered) == {"cycle-guard-demo"}
    mapping = lowered["cycle-guard-demo"]
    assert mapping["version"] == "2.14"
    assert len(mapping["steps"]) == 1
    assert mapping["steps"][0]["command"][:2] == ["python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"]
    hidden_inputs = [name for name in mapping["inputs"] if name.startswith("__write_root__")]
    assert len(hidden_inputs) == 1
    assert mapping["outputs"]["return__terminal_status"]["type"] == "string"
    assert mapping["outputs"]["return__guard_cycles"]["type"] == "integer"


def test_cycle_guard_demo_orc_runtime_materializes_output_bundle(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_inputs = workflow_managed_write_root_inputs(bundle)
    assert len(hidden_inputs) == 1
    assert hidden_inputs[0].endswith("__result_bundle")
    assert hidden_inputs[0] not in _workflow_public_input_contracts(bundle)

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    output_bundle_relpath = (
        Path(".orchestrate")
        / "workflow_lisp"
        / "entry"
        / "cycle-guard-orc-runtime"
        / "cycle-guard-demo"
        / f"{hidden_inputs[0]}.json"
    )
    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-runtime")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    bundle_path = tmp_path / output_bundle_relpath
    assert bundle_path.is_file()
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {
        "terminal_status": "FAILED_CLOSED_BY_GUARD",
        "guard_cycles": 2,
    }


def test_cycle_guard_demo_orc_runtime_rejects_stdout_only_structured_command(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_inputs = workflow_managed_write_root_inputs(bundle)
    assert len(hidden_inputs) == 1

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_text = adapter_source.read_text(encoding="utf-8").replace(
        '\n    if bundle_path_raw:\n        bundle_path = Path(bundle_path_raw)\n        if bundle_path.is_absolute() or ".." in bundle_path.parts:\n            raise SystemExit("unsafe ORCHESTRATOR_OUTPUT_BUNDLE_PATH")\n        bundle_path.parent.mkdir(parents=True, exist_ok=True)\n        bundle_path.write_text(json.dumps(payload) + "\\n", encoding="utf-8")',
        "",
        1,
    )
    adapter_dest.write_text(adapter_text, encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-stdout-only")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()
    step_state = state["steps"]["cycle-guard-demo__emit_cycle_guard_summary"]

    assert state["status"] == "failed"
    assert step_state["error"]["type"] == "contract_violation"
    assert step_state["error"]["context"]["violations"] == [
        {
            "context": {
                "path": (
                    ".orchestrate/workflow_lisp/entry/cycle-guard-orc-stdout-only/"
                    "cycle-guard-demo/"
                    f"{hidden_inputs[0]}.json"
                )
            },
            "message": "Expected output bundle file was not created",
            "type": "missing_bundle_file",
        }
    ]
    assert not (
        tmp_path
        / ".orchestrate"
        / "workflow_lisp"
        / "entry"
        / "cycle-guard-orc-stdout-only"
        / "cycle-guard-demo"
        / f"{hidden_inputs[0]}.json"
    ).exists()


def test_cycle_guard_demo_orc_rejects_user_override_of_runtime_owned_write_root(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_input_name = workflow_managed_write_root_inputs(bundle)[0]

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-override")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
            hidden_input_name: "state/user-owned-result.json",
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "managed_write_root_override"
    assert state["error"]["context"]["input"] == hidden_input_name


def test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    result = compile_stage3_entrypoint(
        EXAMPLES / "design_plan_impl_review_stack_v2_call.orc",
        source_roots=(WORKFLOWS,),
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    lowered_by_short_name = {
        _workflow_short_name(name): mapping for name, mapping in lowered.items()
    }

    assert set(lowered_by_short_name) == {
        "tracked-design-phase",
        "tracked-plan-phase",
        "design-plan-impl-implementation-phase",
        "design-plan-impl-review-stack",
    }

    assert lowered_by_short_name["tracked-design-phase"]["steps"][0]["provider"] == "codex"
    assert lowered_by_short_name["tracked-plan-phase"]["steps"][0]["provider"] == "codex"
    assert lowered_by_short_name["design-plan-impl-implementation-phase"]["steps"][0]["provider"] == "codex"

    stack_outputs = lowered_by_short_name["design-plan-impl-review-stack"]["outputs"]
    output_names = {name.removeprefix("return__") for name in stack_outputs}
    assert output_names == {
        "design_path",
        "design_review_report_path",
        "design_review_decision",
        "plan_path",
        "plan_review_report_path",
        "plan_review_decision",
        "execution_report_path",
        "implementation_review_report_path",
        "implementation_review_decision",
    }


def _execute_design_plan_impl_stack_single_pass_runtime() -> tuple[Path, dict[str, object], dict[str, str]]:
    workflow_relpath = Path("workflows/examples/design_plan_impl_review_stack_v2_call.orc")
    workspace = Path(tempfile.mkdtemp(prefix="design-plan-impl-stack-", dir="/tmp"))
    workflow_path = workspace / workflow_relpath
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text((REPO_ROOT / workflow_relpath).read_text(encoding="utf-8"), encoding="utf-8")

    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")
    for prompt_relpath in prompt_externs.values():
        prompt_path = workspace / prompt_relpath
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text((REPO_ROOT / prompt_relpath).read_text(encoding="utf-8"), encoding="utf-8")

        nested_prompt_path = workflow_path.parent / prompt_relpath
        nested_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        nested_prompt_path.write_text(
            (REPO_ROOT / prompt_relpath).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    brief_relpath = "workflows/examples/inputs/major_project_brief.md"
    brief_path = workspace / brief_relpath
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        (REPO_ROOT / brief_relpath).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(workspace / "workflows",),
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
    ).entry_result
    bundle = result.validated_bundles[
        "examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack"
    ]

    bound_inputs = {
        "brief_path": brief_relpath,
        "design_target_path": "docs/plans/runtime-design.md",
        "design_review_report_target_path": "artifacts/review/runtime-design-review.md",
        "plan_target_path": "docs/plans/runtime-plan.md",
        "plan_review_report_target_path": "artifacts/review/runtime-plan-review.md",
        "execution_report_target_path": "artifacts/work/runtime-execution-report.md",
        "implementation_review_report_target_path": "artifacts/review/runtime-implementation-review.md",
    }
    output_paths = {
        "design_path": bound_inputs["design_target_path"],
        "design_review_report_path": bound_inputs["design_review_report_target_path"],
        "plan_path": bound_inputs["plan_target_path"],
        "plan_review_report_path": bound_inputs["plan_review_report_target_path"],
        "execution_report_path": bound_inputs["execution_report_target_path"],
        "implementation_review_report_path": bound_inputs["implementation_review_report_target_path"],
    }

    state_manager = StateManager(workspace=workspace, run_id="design-plan-impl-stack-runtime")
    state_manager.initialize(
        workflow_relpath.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    provider_steps = [
        {
            "artifacts": [(output_paths["design_path"], "# Runtime Design\n")],
            "bundle": {
                "design_path": output_paths["design_path"],
            },
        },
        {
            "artifacts": [(output_paths["design_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "design_review_report_path": output_paths["design_review_report_path"],
                "design_review_decision": "APPROVE",
            },
        },
        {
            "artifacts": [(output_paths["plan_path"], "# Runtime Plan\n")],
            "bundle": {
                "plan_path": output_paths["plan_path"],
            },
        },
        {
            "artifacts": [(output_paths["plan_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "plan_review_report_path": output_paths["plan_review_report_path"],
                "plan_review_decision": "APPROVE",
            },
        },
        {
            "artifacts": [(output_paths["execution_report_path"], "# Runtime Execution Report\n")],
            "bundle": {
                "execution_report_path": output_paths["execution_report_path"],
            },
        },
        {
            "artifacts": [(output_paths["implementation_review_report_path"], "APPROVE\n")],
            "bundle": {
                "variant": "APPROVE",
                "implementation_review_report_path": output_paths["implementation_review_report_path"],
                "implementation_review_decision": "APPROVE",
            },
        },
    ]
    provider_control = {"index": 0}

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, **_kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt_content or "",
                provider_name=provider_name,
            ),
            None,
        )

    def _bundle_path_from_prompt(prompt: str) -> Path:
        match = re.search(r"(?m)^-?\s*path: (.+)$", prompt)
        assert match is not None, prompt
        return workspace / match.group(1).strip()

    def _write_bundle(bundle_path: Path, payload: dict[str, object]) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _success():
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    def _execute(_self, invocation, **_kwargs):
        provider_index = provider_control["index"]
        provider_control["index"] += 1
        spec = provider_steps[provider_index]
        for relpath, content in spec["artifacts"]:
            target = workspace / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        _write_bundle(_bundle_path_from_prompt(getattr(invocation, "prompt", "")), spec["bundle"])
        return _success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute()

    assert provider_control["index"] == len(provider_steps)
    return workspace, state, output_paths


def test_design_plan_impl_stack_orc_runtime_smoke_executes_single_pass_stack() -> None:
    _workspace, state, _output_paths = _execute_design_plan_impl_stack_single_pass_runtime()

    assert state["status"] == "completed"


def test_design_plan_impl_stack_orc_runtime_output_contract_matches_stack_outputs() -> None:
    _workspace, state, output_paths = _execute_design_plan_impl_stack_single_pass_runtime()

    assert state["workflow_outputs"] == {
        "return__design_path": output_paths["design_path"],
        "return__design_review_report_path": output_paths["design_review_report_path"],
        "return__design_review_decision": "APPROVE",
        "return__plan_path": output_paths["plan_path"],
        "return__plan_review_report_path": output_paths["plan_review_report_path"],
        "return__plan_review_decision": "APPROVE",
        "return__execution_report_path": output_paths["execution_report_path"],
        "return__implementation_review_report_path": output_paths["implementation_review_report_path"],
        "return__implementation_review_decision": "APPROVE",
    }


def test_design_plan_impl_stack_orc_runtime_completes_with_expected_terminal_state() -> None:
    _workspace, state, _output_paths = _execute_design_plan_impl_stack_single_pass_runtime()

    assert state["status"] == "completed"
    assert state.get("error") is None


def test_design_plan_impl_stack_orc_runtime_materializes_expected_artifacts() -> None:
    workspace, state, output_paths = _execute_design_plan_impl_stack_single_pass_runtime()

    assert state["status"] == "completed"
    for relpath in output_paths.values():
        assert (workspace / relpath).is_file(), relpath


def test_library_orc_variants_compile_independently(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    library_targets = [
        WORKFLOWS / "library" / "tracked_design_phase.orc",
        WORKFLOWS / "library" / "tracked_plan_phase.orc",
        WORKFLOWS / "library" / "design_plan_impl_implementation_phase.orc",
    ]

    expected = {
        "tracked_design_phase.orc": "tracked-design-phase",
        "tracked_plan_phase.orc": "tracked-plan-phase",
        "design_plan_impl_implementation_phase.orc": "design-plan-impl-implementation-phase",
    }

    for target in library_targets:
        result = compile_stage3_module(
            target,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )
        lowered_names = {
            _workflow_short_name(workflow.typed_workflow.definition.name)
            for workflow in result.lowered_workflows
        }
        assert lowered_names == {expected[target.name]}


def test_promoted_entry_experiment_ctx_bootstraps_without_name_table_edits(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        EXPERIMENT_CTX_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_experiment_ctx::entry"
    bundle = result.validated_bundles[workflow_name]
    binding = bundle.provenance.private_exec_context_bindings[0]
    public_inputs = set(_workflow_public_input_contracts(bundle))
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))

    assert public_inputs == set()
    assert hidden_context_inputs == {
        "ctx__run__run-id",
        "ctx__run__state-root",
        "ctx__run__artifact-root",
    }
    assert binding.context_family == "RunCtxAnchored"
    assert binding.projection_hints == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "ctx__run__run-id": "run_anchor:run-id",
            "ctx__run__state-root": "run_anchor:state-root",
            "ctx__run__artifact-root": "run_anchor:artifact-root",
        },
    }

    state_manager = StateManager(workspace=tmp_path, run_id="experiment-ctx-run")
    state_manager.initialize(
        EXPERIMENT_CTX_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__run_id": "experiment-ctx-run",
        "return__state_root": "state/run",
        "return__artifact_root": "artifacts/run",
    }


def test_promoted_entry_runctx_only_entry_constructs_drainctx_in_language(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_runctx_only_drain_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    public_inputs = set(_workflow_public_input_contracts(bundle))

    assert hidden_context_inputs == {
        "run__run-id",
        "run__state-root",
        "run__artifact-root",
    }
    assert public_inputs == {"manifest", "ledger"}
    assert hidden_context_inputs.isdisjoint(public_inputs)

    manifest_path = tmp_path / "state" / "manifest.json"
    ledger_path = tmp_path / "state" / "ledger.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    ledger_path.write_text("{}\n", encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="drain-run")
    state_manager.initialize(
        RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "manifest": "state/manifest.json",
            "ledger": "state/ledger.json",
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__run_id": "drain-run",
        "return__state_root": "state/run",
        "return__manifest": "state/manifest.json",
        "return__ledger": "state/ledger.json",
    }


def test_std_context_imported_phase_ctx_supports_hidden_binding(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        STD_CONTEXT_IMPORT_FIXTURE,
        source_roots=(LISP_FIXTURES,),
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "context_generalization_std_context_import::entry"
    bundle = result.validated_bundles[workflow_name]
    binding = bundle.provenance.private_exec_context_bindings[0]

    assert set(_workflow_public_input_contracts(bundle)) == set()
    assert set(_workflow_runtime_context_inputs(bundle)) == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert binding.context_family == "PhaseCtx"

    state_manager = StateManager(workspace=tmp_path, run_id="std-context-phase")
    state_manager.initialize(
        STD_CONTEXT_IMPORT_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__phase_name": "imported-phase",
        "return__state_root": "state/imported-phase",
    }


def test_context_generalization_anchorless_state_path_fixture_rejects_low_level_state_boundary(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            ANCHORLESS_STATE_PATH_FIXTURE,
            source_roots=(LISP_INVALID_FIXTURES,),
            command_boundaries={
                "emit_state_root": ExternalToolBinding(
                    name="emit_state_root",
                    stable_command=("python", "scripts/emit_state_root.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lint_profile=LINT_PROFILE_STRICT,
        )

    assert excinfo.value.diagnostics[0].code == "low_level_state_path_in_high_level_module"


def test_context_generalization_roleless_binding_fixture_reports_unsupported_bootstrap(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            ROLELESS_BINDING_FIXTURE,
            source_roots=(LISP_INVALID_FIXTURES,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert "ctx__experiment-root" in diagnostic.message


def test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    workspace = Path(tempfile.mkdtemp(prefix="orc-pe-", dir="/tmp"))
    monkeypatch.chdir(workspace)
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=workspace,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    imported_resume_bundle = bundle.imports[
        "library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper::resume-plan-gate-wrapper"
    ]
    validator_step = imported_resume_bundle.surface.steps[0]
    assert validator_step.command[:3] == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state",
    )
    validator_payload = json.loads(validator_step.command[-1])
    public_inputs = _workflow_public_input_contracts(bundle)
    assert set(public_inputs) == {
        "inputs__resume_from",
        "inputs__design",
        "inputs__plan",
        "inputs__report_path",
    }
    assert all("phase-ctx__" not in name for name in public_inputs)
    assert all("run-id" not in name for name in public_inputs)
    assert all("state-root" not in name for name in public_inputs)
    assert all("artifact-root" not in name for name in public_inputs)
    assert workflow_managed_write_root_inputs(bundle) == ()
    assert set(_workflow_runtime_context_inputs(bundle)) == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert all(name not in public_inputs for name in _workflow_runtime_context_inputs(bundle))

    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name
        == "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    )
    call_step = next(step for step in authored["steps"] if step.get("call"))
    assert call_step["call"].endswith("::resume-plan-gate-wrapper")
    assert {
        name: call_step["with"][name]
        for name in (
            "phase-ctx__run__run-id",
            "phase-ctx__run__state-root",
            "phase-ctx__run__artifact-root",
            "phase-ctx__phase-name",
            "phase-ctx__state-root",
            "phase-ctx__artifact-root",
        )
    } == {
        "phase-ctx__run__run-id": {"ref": "inputs.phase-ctx__run__run-id"},
        "phase-ctx__run__state-root": {"ref": "inputs.phase-ctx__run__state-root"},
        "phase-ctx__run__artifact-root": {"ref": "inputs.phase-ctx__run__artifact-root"},
        "phase-ctx__phase-name": {"ref": "inputs.phase-ctx__phase-name"},
        "phase-ctx__state-root": {"ref": "inputs.phase-ctx__state-root"},
        "phase-ctx__artifact-root": {"ref": "inputs.phase-ctx__artifact-root"},
    }

    design_path = workspace / "docs" / "design" / "selected-item-design.md"
    plan_path = workspace / "docs" / "plans" / "selected-item-plan.md"
    report_path = workspace / "artifacts" / "work" / "selected-item-execution.md"
    for target in (design_path, plan_path, report_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    bundle_path = workspace / "state" / "selected-item" / "plan-gate.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(
            {
                "variant": "APPROVED",
                "report_path": "artifacts/work/selected-item-execution.md",
            }
        ),
        encoding="utf-8",
    )

    payload = {
        **validator_payload,
        "bundle_path": "state/selected-item/plan-gate.json",
        "resume_from": "state/selected-item/plan-gate.json",
        "current_public_inputs": {
            "phase-ctx__phase-name": "plan-gate-wrapper",
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
        "source_run_id": "promoted-entry-bootstrap",
        "source_step_id": "resume-plan-gate-wrapper",
        "source_call_frame_id": "root",
        "phase_id": "plan-gate-wrapper",
        "created_at": "2026-06-03T00:00:00Z",
    }
    payload_path = workspace / "state" / "payloads" / "promoted_entry_plan_gate_wrapper.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    assert write_reusable_phase_state_v1.main(
        ["write_reusable_phase_state_v1", payload_path.as_posix()]
    ) == 0
    capsys.readouterr()
    assert validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    ) == 0
    reusable_payload = json.loads(capsys.readouterr().out)
    assert reusable_payload["variant"] == "REUSABLE"

    script_path = workspace / "scripts" / "resolve_plan_gate.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "report_path = Path(sys.argv[1])",
                "report_path.parent.mkdir(parents=True, exist_ok=True)",
                "report_path.write_text('approved\\n', encoding='utf-8')",
                "bundle_path = Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])",
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                "bundle_path.write_text(",
                "    json.dumps(",
                    "        {",
                    "            'variant': 'APPROVED',",
                    "            'shared_report_path': report_path.as_posix(),",
                    "        }",
                "    ) + '\\n',",
                "    encoding='utf-8',",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state_manager = StateManager(workspace=workspace, run_id="promoted-entry-bootstrap")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
    )
    state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    outputs = state["workflow_outputs"]
    assert outputs["return__report_path"] == "artifacts/work/selected-item-execution.md"
    assert report_path.read_text(encoding="utf-8") == "seed\n"


def test_public_phase_ctx_entry_inputs_do_not_require_hidden_context_provenance(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "public_phase_ctx.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord WorkflowOutput",
                "    (report_path WorkReportTarget))",
                "  (defworkflow entry",
                "    ((phase-ctx PhaseCtx)",
                "     (report-path WorkReportTarget))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :report_path report-path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        workflow_path,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["entry"]
    assert _workflow_runtime_context_inputs(bundle) == ()

    state_manager = StateManager(workspace=tmp_path, run_id="public-phase-ctx")
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report-path": "artifacts/work/report.md",
            "phase-ctx__run__run-id": "user-run",
            "phase-ctx__run__state-root": "state/user",
            "phase-ctx__run__artifact-root": "artifacts/user",
            "phase-ctx__phase-name": "implementation",
            "phase-ctx__state-root": "state/phase",
            "phase-ctx__artifact-root": "artifacts/phase",
        },
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__report_path": "artifacts/work/report.md",
    }


def test_promoted_entry_hidden_context_override_fails(tmp_path: Path) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert "phase-ctx__phase-name" in hidden_context_inputs

    state_manager = StateManager(workspace=tmp_path, run_id="promoted-entry-hidden-context-override")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
            "phase-ctx__phase-name": "forged-phase-name",
        },
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "promoted_entry_hidden_context_override"
    assert state["error"]["context"]["input"] == "phase-ctx__phase-name"
    assert state["error"]["context"]["expected"] == "plan-gate-wrapper"


def test_promoted_entry_hidden_context_metadata_missing_fails(tmp_path: Path) -> None:
    fixture = LISP_FIXTURES / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(LISP_FIXTURES,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    bundle = result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert "phase-ctx__phase-name" in hidden_context_inputs

    broken_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            runtime_context_inputs=(),
            private_exec_context_bindings=(),
        ),
    )
    assert _workflow_runtime_context_inputs(broken_bundle) == ()
    assert hidden_context_inputs.issubset(workflow_input_contracts(broken_bundle))

    state_manager = StateManager(workspace=tmp_path, run_id="promoted-entry-hidden-context-metadata-missing")
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(broken_bundle),
        bound_inputs={
            "inputs__resume_from": "state/selected-item/plan-gate.json",
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
    )

    state = WorkflowExecutor(broken_bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["reason"] == "promoted_entry_hidden_context_metadata_missing"
    assert set(state["error"]["context"]["inputs"]) == hidden_context_inputs


def test_promoted_entry_hidden_context_metadata_rebinds_without_flattened_defaults(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "private_exec_context_phase_entry.orc"
    script_path = tmp_path / "scripts" / "emit_phase_result.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                "_, label, phase_name = sys.argv",
                "bundle_path = os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']",
                "with open(bundle_path, 'w', encoding='utf-8') as handle:",
                "    json.dump({'label': label, 'phase_name': phase_name}, handle)",
                "    handle.write('\\n')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name String))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (command-result emit_phase_result",
                "        :argv (\"python\" \"scripts/emit_phase_result.py\" label phase-ctx.phase-name)",
                "        :returns Result)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(tmp_path,),
        command_boundaries={
            "emit_phase_result": ExternalToolBinding(
                name="emit_phase_result",
                stable_command=("python", "scripts/emit_phase_result.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result
    workflow_name = "private_exec_context_phase_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    hidden_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    assert hidden_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }

    stripped_inputs = dict(bundle.surface.inputs)
    for input_name in hidden_context_inputs:
        contract = stripped_inputs[input_name]
        contract_definition = dict(contract.definition)
        contract_definition.pop("default", None)
        stripped_inputs[input_name] = replace(contract, definition=contract_definition)
    stripped_bundle = replace(
        bundle,
        surface=replace(bundle.surface, inputs=stripped_inputs),
    )
    legacy_binding = replace(
        bundle.provenance.private_exec_context_bindings[0],
        projection_hints={},
    )
    legacy_compatibility_bundle = replace(
        stripped_bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(legacy_binding,),
        ),
    )

    def _execute(candidate_bundle, *, run_id: str) -> dict[str, object]:
        state_manager = StateManager(workspace=tmp_path, run_id=run_id)
        state_manager.initialize(
            workflow_path.as_posix(),
            context=bundle_context_dict(candidate_bundle),
            bound_inputs={"label": "selected-item"},
        )
        return WorkflowExecutor(candidate_bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    original_state = _execute(bundle, run_id="promoted-entry-defaults")
    stripped_state = _execute(stripped_bundle, run_id="rid-123")
    legacy_compatibility_state = _execute(
        legacy_compatibility_bundle,
        run_id="rid-legacy-compat",
    )

    assert original_state["status"] == "completed"
    assert stripped_state["status"] == "failed"
    assert stripped_state["error"]["context"]["reason"] == "private_exec_context_bootstrap_unsupported"
    assert legacy_compatibility_state["status"] == "completed"
    assert original_state["workflow_outputs"] == {
        "return__label": "selected-item",
        "return__phase_name": "plan-gate-wrapper",
    }
    assert legacy_compatibility_state["workflow_outputs"] == original_state["workflow_outputs"]
    assert legacy_compatibility_state["bound_inputs"]["phase-ctx__run__run-id"] == "rid-legacy-compat"
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__phase-name"]
        == original_state["bound_inputs"]["phase-ctx__phase-name"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__run__state-root"]
        == original_state["bound_inputs"]["phase-ctx__run__state-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__run__artifact-root"]
        == original_state["bound_inputs"]["phase-ctx__run__artifact-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__state-root"]
        == original_state["bound_inputs"]["phase-ctx__state-root"]
    )
    assert (
        legacy_compatibility_state["bound_inputs"]["phase-ctx__artifact-root"]
        == original_state["bound_inputs"]["phase-ctx__artifact-root"]
    )


@pytest.mark.parametrize("context_name", ["SelectionCtx", "RecoveryCtx"])
def test_promoted_entry_reserved_private_context_families_report_unsupported_bootstrap(
    tmp_path: Path,
    context_name: str,
) -> None:
    workflow_path = tmp_path / f"private_exec_context_{context_name.lower()}.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                f"  (defmodule private_exec_context_{context_name.lower()})",
                "  (export entry use-context)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                f"  (defrecord {context_name}",
                "    (run RunCtx)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (state_root Path.state-root))",
                "  (defworkflow entry",
                "    ()",
                "    -> Result",
                "    (call use-context))",
                "  (defworkflow use-context",
                f"    ((ctx {context_name}))",
                "    -> Result",
                "    (record Result :state_root ctx.state-root))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception) as excinfo:
        compile_stage3_entrypoint(
            workflow_path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostics = getattr(excinfo.value, "diagnostics", ())
    assert diagnostics, "expected frontend diagnostics"
    diagnostic = diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert context_name in diagnostic.message


def test_resume_or_start_plan_gate_reusable_state_parity_path(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    design_path = tmp_path / "docs" / "design" / "selected-item-design.md"
    plan_path = tmp_path / "docs" / "plans" / "selected-item-plan.md"
    report_path = tmp_path / "artifacts" / "work" / "selected-item-execution.md"
    for target in (design_path, plan_path, report_path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    bundle_path = tmp_path / "state" / "selected-item" / "plan-gate.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "variant": "APPROVED",
        "execution_report_path": "artifacts/work/selected-item-execution.md",
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    structured_contract = {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [],
        "variants": {
            "APPROVED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "blocker_class",
                        "json_pointer": "/blocker_class",
                        "type": "string",
                    },
                ]
            },
        },
    }
    payload = {
        "bundle_path": "state/selected-item/plan-gate.json",
        "resume_from": "state/selected-item/plan-gate.json",
        "target_dsl_version": "2.14",
        "return_type_name": "PlanGateResult",
        "structured_contract_kind": "union",
        "expected_contract_fingerprint": _structured_contract_fingerprint(
            structured_contract_kind="union",
            structured_contract=structured_contract,
            return_type_name="PlanGateResult",
        ),
        "structured_contract": structured_contract,
        "summary_schema": "ReusablePhaseState.v1",
        "summary_version": "v1",
        "sidecar_suffix": ".reusable_state.json",
        "canonical_bundle_digest_field": "canonical_bundle_sha256",
        "reusable_variants": ["APPROVED"],
        "artifact_requirements": {
            "APPROVED": [
                {
                    "field_path": ["execution_report_path"],
                    "under": "artifacts/work",
                }
            ]
        },
        "public_input_hash_basis": [
            "inputs__design",
            "inputs__plan",
            "inputs__report_path",
        ],
        "current_public_inputs": {
            "inputs__design": "docs/design/selected-item-design.md",
            "inputs__plan": "docs/plans/selected-item-plan.md",
            "inputs__report_path": "artifacts/work/selected-item-execution.md",
        },
        "producer_fingerprint_basis": {
            "workflow_name": "selected-item::plan-gate",
            "return_type_name": "PlanGateResult",
            "structured_contract_kind": "union",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="union",
                structured_contract=structured_contract,
                return_type_name="PlanGateResult",
            ),
            "target_dsl_version": "2.14",
            "compiler_version": "0.1.0",
            "reusable_variants": ["APPROVED"],
            "public_input_hash_basis": [
                "inputs__design",
                "inputs__plan",
                "inputs__report_path",
            ],
        },
        "source_run_id": "selected-item-run",
        "source_step_id": "plan-gate",
        "source_call_frame_id": "root",
        "phase_id": "plan-gate",
        "created_at": "2026-06-02T00:00:00Z",
    }
    payload_path = tmp_path / "state" / "payloads" / "selected_item_plan_gate.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path.as_posix()]) == 0
    capsys.readouterr()

    reusable_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path.as_posix()])
    reusable_payload = json.loads(capsys.readouterr().out)
    assert reusable_exit == 0
    assert reusable_payload["variant"] == "REUSABLE"

    load_exit = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": reusable_payload["source_bundle_path"],
                    "target_dsl_version": "2.14",
                    "return_type_name": "PlanGateResult",
                    "expected_contract_fingerprint": payload["expected_contract_fingerprint"],
                    "structured_contract_kind": "union",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": reusable_payload["source_bundle_sha256"],
                }
            ),
        ]
    )
    loaded = json.loads(capsys.readouterr().out)
    assert load_exit == 0
    assert loaded == bundle

    stale_payload = dict(payload)
    stale_payload["current_public_inputs"] = {
        "inputs__design": "docs/design/selected-item-design-v2.md",
        "inputs__plan": "docs/plans/selected-item-plan.md",
        "inputs__report_path": "artifacts/work/selected-item-execution.md",
    }
    stale_payload_path = tmp_path / "state" / "payloads" / "selected_item_plan_gate_stale.json"
    stale_payload_path.write_text(json.dumps(stale_payload), encoding="utf-8")
    stale_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", stale_payload_path.as_posix()])
    stale_result = json.loads(capsys.readouterr().out)
    assert stale_exit == 0
    assert stale_result == {"variant": "STALE"}

    report_path.unlink()
    missing_exit = validate_reusable_phase_state.main(["validate_reusable_phase_state", payload_path.as_posix()])
    missing_result = json.loads(capsys.readouterr().out)
    assert missing_exit == 0
    assert missing_result == {"variant": "MISSING_ARTIFACT"}


def test_resume_or_start_plan_gate_reusable_state_parity_path_wrapper_union_contract(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "phase_stdlib_resume_or_start_reusable_wrapper.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_resume_or_start_reusable_wrapper.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = compile_stage3_module(
        fixture,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if _workflow_short_name(workflow.typed_workflow.definition.name) == "resume-plan-gate-wrapper"
    )
    validator_step = authored["steps"][0]
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("match", {}).get("ref")
        == f"root.steps.{validator_step['name']}.artifacts.variant"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    call_step = next(
        step
        for step in _iter_nested_steps(start_steps)
        if step.get("call") == "wrap-plan-gate"
    )

    assert call_step["call"] == "wrap-plan-gate"
    assert "load_canonical_phase_result__PlanGateWrapperResult" in result.command_boundary_environment.bindings_by_name
    assert "resume-plan-gate-wrapper" in {
        _workflow_short_name(workflow.typed_workflow.definition.name) for workflow in result.lowered_workflows
    }


def test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "phase_stdlib_review_loop.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_review_loop.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")
    result = compile_stage3_module(
        fixture,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["phase_stdlib_review_loop::review-revise-loop-demo"]
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    seed_step = next(step for step in authored["steps"] if step["name"].endswith("__seed"))
    body_steps = repeat_step["repeat_until"]["steps"]
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }

    nested_steps = list(_iter_nested_steps(body_steps))
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::run-review.v1")
        for step in nested_steps
    )
    assert any(
        isinstance(step.get("call"), str) and step["call"].endswith("::apply-fix.v1")
        for step in nested_steps
    )
    assert any(
        any(step.get("provider") == provider for step in workflow.authored_mapping.get("steps", ()))
        for provider in ("fake-review", "fake-fix")
        for workflow in result.lowered_workflows
    )
    assert authored["outputs"]["return__review_report"]["under"] == "artifacts/review"
    assert authored["outputs"]["return__last_review_report"]["under"] == "artifacts/review"
    assert authored["outputs"]["return__findings__items_path"]["under"] == "artifacts/work"
    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }

    frame_checkpoint = next(
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.checkpoint_kind == "repeat_until_frame"
    )
    loop_node_id = next(
        node_id
        for node_id, projection in bundle.projection.repeat_until_nodes.items()
        if projection.frame_key == repeat_step["name"]
    )
    assert frame_checkpoint.presentation_key == repeat_step["name"]
    assert bundle.projection.repeat_until_frame_key(loop_node_id) == repeat_step["name"]
    assert frame_checkpoint.step_id.startswith("root.")


def test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint(tmp_path: Path) -> None:
    fixture = tmp_path / "phase_stdlib_review_loop.orc"
    fixture.write_text(
        (LISP_FIXTURES / "phase_stdlib_review_loop.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
        "artifacts/work/seed_execution_report.md",
        "artifacts/work/design_review_prompt.md",
        "artifacts/work/fix_plan_prompt.md",
        "artifacts/work/placeholder.txt",
        "artifacts/work/loop-placeholder.txt",
        "artifacts/review/placeholder.txt",
        "artifacts/review/loop-placeholder.txt",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    result = compile_stage3_module(
        fixture,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["phase_stdlib_review_loop::review-revise-loop-demo"]
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    loop_node_id = next(
        node_id
        for node_id, projection in bundle.projection.repeat_until_nodes.items()
        if projection.frame_key == repeat_step["name"]
    )
    frame_key = bundle.projection.repeat_until_frame_key(loop_node_id)

    run_id = "phase-stdlib-review-loop-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "completed__execution_report_path": "artifacts/work/seed_execution_report.md",
            "inputs__design_review_prompt": "artifacts/work/design_review_prompt.md",
            "inputs__fix_plan_prompt": "artifacts/work/fix_plan_prompt.md",
        },
    )

    control = {"resume_mode": False, "review_calls": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _bundle_path_from_prompt(prompt: str) -> Path:
        match = re.search(r"(?m)^-?\s*path: (.+)$", prompt)
        assert match is not None, prompt
        return tmp_path / match.group(1).strip()

    def _write_bundle(bundle_path: Path, payload: dict[str, object]) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _touch(relpath: str) -> None:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("artifact\n", encoding="utf-8")

    def _write_findings(relpath: str) -> str:
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"items": []}, indent=2) + "\n", encoding="utf-8")
        return relpath

    def _success():
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    def _failure(message: str):
        return SimpleNamespace(
            exit_code=1,
            stdout=b"",
            stderr=message.encode("utf-8"),
            duration_ms=1,
            error={"type": "execution_error", "message": message},
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    def _execute(_self, invocation, **_kwargs):
        prompt = getattr(invocation, "prompt", "")
        bundle_path = _bundle_path_from_prompt(prompt)
        if "## Variant Output Contract" not in prompt:
            _touch("artifacts/work/execution_report_revised.md")
            _write_bundle(
                bundle_path,
                {"execution_report_path": "artifacts/work/execution_report_revised.md"},
            )
            return _success()

        control["review_calls"] += 1
        if control["review_calls"] == 1:
            _touch("artifacts/review/review_round_1.md")
            _write_bundle(
                bundle_path,
                {
                    "variant": "REVISE",
                    "review_report": "artifacts/review/review_round_1.md",
                    "revise_review_report": "artifacts/review/review_round_1.md",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": _write_findings("artifacts/work/review_round_1_findings.json"),
                    },
                },
            )
            return _success()
        if not control["resume_mode"]:
            return _failure("forced review interruption")
        _touch("artifacts/work/checks_report.md")
        _touch("artifacts/review/review_round_2.md")
        _write_bundle(
            bundle_path,
            {
                "variant": "APPROVE",
                "checks_report": "artifacts/work/checks_report.md",
                "review_report": "artifacts/review/review_round_2.md",
                "review_decision": "APPROVE",
                "findings": {
                    "schema_version": "ReviewFindings.v1",
                    "items_path": _write_findings("artifacts/work/review_round_2_findings.json"),
                },
            },
        )
        return _success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
        assert first_run["status"] == "failed"
        frame_result = first_run["steps"][repeat_step["name"]]
        assert frame_result["error"]["message"] == "repeat_until body step failed"
        assert frame_result["error"]["context"]["iteration"] == 1

        persisted = json.loads(
            (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8")
        )
        assert persisted.get("error") is None
        assert persisted["repeat_until"][frame_key]["current_iteration"] == 1
        assert persisted["repeat_until"][frame_key]["completed_iterations"] == [0]
        assert frame_key in persisted["steps"]

        control["resume_mode"] = True
        resumed_state = WorkflowExecutor(
            bundle,
            tmp_path,
            StateManager(workspace=tmp_path, run_id=run_id),
            retry_delay_ms=0,
        ).execute(run_id=run_id, resume=True)

    assert resumed_state["status"] == "completed"
    assert resumed_state["repeat_until"][frame_key]["completed_iterations"] == [0, 1]
    assert frame_key in resumed_state["steps"]
