from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLES = WORKFLOWS / "examples"
MIGRATION_INPUTS = EXAMPLES / "inputs" / "workflow_lisp_migrations"
LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_short_name(name: str) -> str:
    return name.rsplit("::", 1)[-1]


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
    hidden_inputs = tuple(
        name for name in workflow_input_contracts(bundle) if isinstance(name, str) and name.startswith("__write_root__")
    )
    assert len(hidden_inputs) == 1
    hidden_input_name = hidden_inputs[0]

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    output_bundle_relpath = "state/cycle-guard-result.json"
    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-runtime")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
            hidden_input_name: output_bundle_relpath,
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


def test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    result = compile_stage3_module(
        EXAMPLES / "design_plan_impl_review_stack_v2_call.orc",
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )

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
    body_steps = repeat_step["repeat_until"]["steps"]

    def _walk_steps(steps):
        for step in steps:
            yield step
            match_block = step.get("match")
            if isinstance(match_block, dict):
                for case in match_block.get("cases", {}).values():
                    if isinstance(case, dict):
                        yield from _walk_steps(case.get("steps", []))

    review_workflow = next(
        workflow
        for workflow in result.lowered_workflows
        if any(step.get("provider") == "fake-review" for step in workflow.authored_mapping["steps"])
    )
    fix_workflow = next(
        workflow
        for workflow in result.lowered_workflows
        if any(step.get("provider") == "fake-fix" for step in workflow.authored_mapping["steps"])
    )
    review_calls = [step for step in _walk_steps(body_steps) if step.get("call") == review_workflow.typed_workflow.definition.name]
    fix_calls = [step for step in _walk_steps(body_steps) if step.get("call") == fix_workflow.typed_workflow.definition.name]
    assert len(review_calls) == 1
    assert len(fix_calls) == 1
    assert any(
        step.get("provider") == "fake-review"
        for workflow in result.lowered_workflows
        for step in workflow.authored_mapping["steps"]
    )
    assert any(
        step.get("provider") == "fake-fix"
        for workflow in result.lowered_workflows
        for step in workflow.authored_mapping["steps"]
    )

    frame_checkpoint = next(
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.checkpoint_kind == "repeat_until_frame"
    )
    assert frame_checkpoint.presentation_key == repeat_step["name"]
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
    hidden_inputs = tuple(
        sorted(
            {
                name
                for name in workflow_input_contracts(bundle)
                if isinstance(name, str) and name.startswith("__write_root__")
            }
            | {
                match
                for match in re.findall(r"\$\{inputs\.(__write_root__[^}]+)\}", json.dumps(authored))
            }
        )
    )

    run_id = "phase-stdlib-review-loop-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        fixture.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "completed__execution_report_path": "artifacts/work/seed_execution_report.md",
            "inputs__design_review_prompt": "artifacts/work/design_review_prompt.md",
            "inputs__fix_plan_prompt": "artifacts/work/fix_plan_prompt.md",
            **{
                hidden_input: f".orchestrate/generated/{hidden_input}.json"
                for hidden_input in hidden_inputs
            },
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
            _touch("artifacts/work/review_round_1.md")
            _write_bundle(
                bundle_path,
                {
                    "variant": "REVISE",
                    "revise_review_report": "artifacts/work/review_round_1.md",
                },
            )
            return _success()
        if not control["resume_mode"]:
            return _failure("forced review interruption")
        _touch("artifacts/work/checks_report.md")
        _touch("artifacts/work/review_round_2.md")
        _write_bundle(
            bundle_path,
            {
                "variant": "APPROVED",
                "checks_report": "artifacts/work/checks_report.md",
                "review_report": "artifacts/work/review_round_2.md",
                "review_decision": "APPROVE",
            },
        )
        return _success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
        assert first_run["status"] == "failed"

        persisted = json.loads((tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
        assert persisted["repeat_until"][repeat_step["name"]]["current_iteration"] == 1
        assert persisted["repeat_until"][repeat_step["name"]]["completed_iterations"] == [0]

        control["resume_mode"] = True
        resumed_state = WorkflowExecutor(
            bundle,
            tmp_path,
            StateManager(workspace=tmp_path, run_id=run_id),
            retry_delay_ms=0,
        ).execute(run_id=run_id, resume=True)

    assert resumed_state["status"] == "completed"
