"""Real-consumer acceptance coverage for the target-2.20 prompt core."""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.prompting import render_prompt_fragment_base
from orchestrator.workflow.prompt_dependency_evidence import (
    validate_fragment_success_evidence,
    validate_terminal_evidence,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.lexical_checkpoints import (
    checkpoint_runtime_program_identity,
    validate_checkpoint_record,
)
from orchestrator.workflow_lisp.typed_prompt_inputs import (
    render_typed_prompt_inputs,
)
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
CONSUMER = REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc"
CONSUMER_INPUTS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "review_revise_design_docs"
)
LEGACY_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "prompt_calculus"
    / "review_revise_design_docs_pre_migration"
)
FIX_PROMPT = "prompts/workflows/review_revise_design_docs/fix.md"
PROVIDERS = {
    "providers.design-docs.review": "codex_gpt55",
    "providers.design-docs.fix": "codex_gpt55",
}


class _ProviderBoundaryInterruption(BaseException):
    pass


def _manifest(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return {str(key): str(value) for key, value in payload.items()}


def _compile(
    source_path: Path,
    *,
    prompt_externs: dict[str, str],
    lowering_route: str,
    workspace_root: Path,
):
    return compile_stage3_module(
        source_path,
        provider_externs=PROVIDERS,
        prompt_externs=prompt_externs,
        validate_shared=True,
        workspace_root=workspace_root,
        lowering_route=lowering_route,
    )


def _bundle(result, suffix: str):
    return next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name.endswith(suffix)
    )


def _provider_step(bundle):
    return next(step for step in bundle.surface.steps if step.kind.value == "provider")


def _provider_policy_projection(step) -> dict[str, object]:
    return {
        "provider": step.provider,
        "provider_params": step.provider_params,
        "provider_call_policy": step.provider_call_policy,
        "managed_jobs": step.managed_jobs,
        "timeout_sec": step.common.timeout_sec,
        "retries": step.common.retries,
        "inject_output_contract": step.inject_output_contract,
        "variant_output": step.common.variant_output,
    }


def _normalize_fragment_template_to_legacy_static(template: str) -> str:
    replacements = {
        "\n\n{review_focus}\n\n": " ",
        "\n\n{context_docs}\n\n": " ",
        "\n\n{checks_report}\n\n": " ",
        "\n\n{review_report_target_path}\n\n": "\n\n",
    }
    normalized = template
    for insertion, legacy_separator in replacements.items():
        assert normalized.count(insertion) == 1
        normalized = normalized.replace(
            insertion,
            legacy_separator,
            1,
        )
    return normalized


def _runtime_manager(
    workspace: Path,
    *,
    source_path: Path,
    bundle,
    run_id: str,
) -> StateManager:
    files = {
        "docs/design/target.md": "TARGET_DOCUMENT_SENTINEL\n",
        "docs/design/context-a.md": "CONTEXT_A_SENTINEL\n",
        "docs/design/context-b.md": "CONTEXT_B_SENTINEL\n",
        "artifacts/work/checks.md": "CHECKS_SENTINEL\n",
    }
    for relative_path, content in files.items():
        target = workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "target_doc": "docs/design/target.md",
            "context_docs": [
                "docs/design/context-a.md",
                "docs/design/context-b.md",
            ],
            "review_focus": "FOCUS_SENTINEL",
            "checks_report": "artifacts/work/checks.md",
            "review_report_target_path": "artifacts/review/review.md",
            "revision_report_target_path": "artifacts/work/revision.md",
            "review_model": "gpt-5.5",
            "review_effort": "high",
            "fix_model": "gpt-5.5",
            "fix_effort": "high",
            "run__run-id": run_id,
        },
        workspace,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        source_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return manager


def _capturing_review_provider(
    workspace: Path,
    captured: dict[str, object],
):
    def prepare(_self, provider_name, *_args, **kwargs):
        prompts = captured.setdefault("prompts", [])
        providers = captured.setdefault("providers", [])
        assert isinstance(prompts, list)
        assert isinstance(providers, list)
        providers.append(provider_name)
        prompts.append(str(kwargs.get("prompt_content", "")))
        captured["preparations"] = int(captured.get("preparations", 0)) + 1
        return SimpleNamespace(
            input_mode="stdin",
            prompt=prompts[-1],
            env=kwargs.get("env") or {},
        ), None

    def execute(_self, invocation, **_kwargs):
        captured["executions"] = int(captured.get("executions", 0)) + 1
        review_report = workspace / "artifacts" / "review" / "review.md"
        review_report.parent.mkdir(parents=True, exist_ok=True)
        review_report.write_text("REVIEW_REPORT_SENTINEL\n", encoding="utf-8")
        findings = workspace / "artifacts" / "work" / "findings.json"
        findings.parent.mkdir(parents=True, exist_ok=True)
        findings.write_text('{"items":[]}\n', encoding="utf-8")
        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = workspace / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "variant": "APPROVE",
                    "review_report": "artifacts/review/review.md",
                    "findings": {
                        "schema_version": "ReviewFindings.v1",
                        "items_path": "artifacts/work/findings.json",
                    },
                },
                sort_keys=True,
            )
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

    return prepare, execute


def _execute_consumer(
    *,
    source_path: Path,
    prompt_externs: dict[str, str],
    workspace: Path,
    run_id: str,
):
    result = _compile(
        source_path,
        prompt_externs=prompt_externs,
        lowering_route="wcc_m4",
        workspace_root=workspace,
    )
    bundle = _bundle(result, "::review-revise-design-docs")
    manager = _runtime_manager(
        workspace,
        source_path=source_path,
        bundle=bundle,
        run_id=run_id,
    )
    captured: dict[str, object] = {}
    prepare, execute = _capturing_review_provider(workspace, captured)
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(ProviderExecutor, "execute", execute):
        completed = WorkflowExecutor(
            bundle,
            workspace,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    return result, bundle, manager, captured, completed


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_real_consumer_migrates_review_to_five_slot_prompt_fragment(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    prompt_externs = _manifest(CONSUMER_INPUTS / "prompts.json")
    assert prompt_externs == {"prompts.design-docs.fix": FIX_PROMPT}

    result = _compile(
        CONSUMER,
        prompt_externs=prompt_externs,
        lowering_route=lowering_route,
        workspace_root=tmp_path,
    )
    review = _provider_step(
        _bundle(result, "::review-design-docs.v1")
    )

    contract = review.compiler_prompt_fragment_contract
    assert contract is not None
    assert contract.schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA
    assert contract.compiled_prompt_fragment_identity == (
        review.compiled_prompt_fragment_identity
    )
    assert tuple(slot.name for slot in contract.rendered_slots) == (
        "context_docs",
        "review_focus",
        "checks_report",
        "review_report_target_path",
    )
    assert tuple(slot.kind for slot in contract.rendered_slots) == (
        "value",
        "text",
        "path",
        "path",
    )
    assert tuple(slot.renderer_id for slot in contract.rendered_slots) == (
        "canonical-json",
        "raw-utf8-string",
        "posix-path-line",
        "posix-path-line",
    )
    assert review.depends_on == {
        "required": ("${inputs.completed__target_doc}",),
        "optional": (),
        "inject": {
            "mode": "content",
            "position": "prepend",
        },
    }
    dependency_contract = review.compiler_prompt_dependency_contract
    assert dependency_contract is not None
    assert dependency_contract.origin_kind.value == "workflow_lisp_prompt_fragment"
    assert dependency_contract.required_binding_refs == (
        "inputs.completed__target_doc",
    )
    assert dependency_contract.optional_binding_refs == ()
    assert review.asset_file is None
    assert review.input_file is None
    assert review.common.timeout_sec == 3600
    assert review.common.variant_output["discriminant"]["allowed"] == (
        "APPROVE",
        "REVISE",
        "BLOCKED",
    )
    frozen_legacy = (
        LEGACY_FIXTURE
        / "prompts"
        / "workflows"
        / "review_revise_design_docs"
        / "review.md"
    ).read_text(encoding="utf-8")
    assert _normalize_fragment_template_to_legacy_static(
        contract.template_utf8
    ) == frozen_legacy


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_real_consumer_migration_preserves_fix_call_and_provider_policy(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    legacy = _compile(
        LEGACY_FIXTURE / "review_revise_design_docs.orc",
        prompt_externs=_manifest(LEGACY_FIXTURE / "prompts.json"),
        lowering_route=lowering_route,
        workspace_root=tmp_path / "legacy",
    )
    migrated = _compile(
        CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route=lowering_route,
        workspace_root=tmp_path / "migrated",
    )

    legacy_fix = _provider_step(_bundle(legacy, "::fix-design-doc.v1"))
    migrated_fix = _provider_step(_bundle(migrated, "::fix-design-doc.v1"))
    assert migrated_fix == legacy_fix
    assert migrated_fix.asset_file == FIX_PROMPT
    assert migrated_fix.compiler_prompt_fragment_contract is None
    assert migrated_fix.compiled_prompt_fragment_identity is None

    legacy_review = _provider_step(_bundle(legacy, "::review-design-docs.v1"))
    migrated_review = _provider_step(
        _bundle(migrated, "::review-design-docs.v1")
    )
    assert _provider_policy_projection(migrated_review) == (
        _provider_policy_projection(legacy_review)
    )


def test_real_consumer_composed_prompt_preserves_legacy_static_and_stable_lanes(
    tmp_path: Path,
) -> None:
    legacy_workspace = tmp_path / "legacy"
    migrated_workspace = tmp_path / "migrated"
    legacy_workspace.mkdir()
    migrated_workspace.mkdir()
    legacy_result, _, _, legacy_capture, legacy_state = _execute_consumer(
        source_path=LEGACY_FIXTURE / "review_revise_design_docs.orc",
        prompt_externs=_manifest(LEGACY_FIXTURE / "prompts.json"),
        workspace=legacy_workspace,
        run_id="prompt-core-legacy-composition",
    )
    migrated_result, _, _, migrated_capture, migrated_state = (
        _execute_consumer(
            source_path=CONSUMER,
            prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
            workspace=migrated_workspace,
            run_id="prompt-core-migrated-composition",
        )
    )
    assert legacy_state["status"] == migrated_state["status"] == "completed"
    [legacy_prompt] = legacy_capture["prompts"]
    [migrated_prompt] = migrated_capture["prompts"]
    legacy_review = _provider_step(
        _bundle(legacy_result, "::review-design-docs.v1")
    )
    migrated_review = _provider_step(
        _bundle(migrated_result, "::review-design-docs.v1")
    )
    legacy_base = (
        LEGACY_FIXTURE
        / "prompts"
        / "workflows"
        / "review_revise_design_docs"
        / "review.md"
    ).read_text(encoding="utf-8")
    fragment_contract = migrated_review.compiler_prompt_fragment_contract
    assert fragment_contract is not None
    migrated_base = render_prompt_fragment_base(
        fragment_contract,
        resolved_slot_values={
            "context_docs": [
                "docs/design/context-a.md",
                "docs/design/context-b.md",
            ],
            "review_focus": "FOCUS_SENTINEL",
            "checks_report": "artifacts/work/checks.md",
            "review_report_target_path": "artifacts/review/review.md",
        },
    )
    normalized_migrated_base = migrated_base
    for insertion, legacy_separator in (
        ("\n\nFOCUS_SENTINEL\n\n", " "),
        (
            '\n\n["docs/design/context-a.md","docs/design/context-b.md"]\n\n',
            " ",
        ),
        ("\n\nartifacts/work/checks.md\n\n", " "),
        ("\n\nartifacts/review/review.md\n\n", "\n\n"),
    ):
        assert normalized_migrated_base.count(insertion) == 1
        normalized_migrated_base = normalized_migrated_base.replace(
            insertion,
            legacy_separator,
            1,
        )
    assert normalized_migrated_base == legacy_base

    legacy_prefix, separator, legacy_tail = legacy_prompt.partition(legacy_base)
    assert separator == legacy_base
    migrated_prefix, separator, migrated_tail = migrated_prompt.partition(
        migrated_base
    )
    assert separator == migrated_base
    assert migrated_prefix == legacy_prefix

    legacy_typed_block, _ = render_typed_prompt_inputs(
        legacy_review.typed_prompt_inputs,
        resolved_typed_values={
            "target_doc": "docs/design/target.md",
            "review_focus": "FOCUS_SENTINEL",
            "checks_report": "artifacts/work/checks.md",
            "review_report_target_path": "artifacts/review/review.md",
        },
        workflow_name="legacy-normalization",
        step_id="legacy-review",
    )
    assert legacy_tail.startswith("\n" + legacy_typed_block)
    legacy_contract = legacy_tail[len("\n" + legacy_typed_block) :]
    assert legacy_contract.startswith("\n\n")
    assert migrated_tail.startswith("\n")
    migrated_contract = migrated_tail[1:]
    legacy_contract = re.sub(
        r"(?m)^- path: .+$",
        "- path: <runtime-output-bundle-path>",
        legacy_contract[2:],
        count=1,
    )
    migrated_contract = re.sub(
        r"(?m)^- path: .+$",
        "- path: <runtime-output-bundle-path>",
        migrated_contract,
        count=1,
    )
    assert migrated_contract == legacy_contract
    assert _provider_policy_projection(migrated_review) == (
        _provider_policy_projection(legacy_review)
    )


def test_real_consumer_runtime_validates_prompt_owned_result_and_snapshot(
    tmp_path: Path,
) -> None:
    result, bundle, manager, captured, completed = _execute_consumer(
        source_path=CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        workspace=tmp_path,
        run_id="prompt-core-real-consumer",
    )

    assert completed["status"] == "completed"
    assert captured["preparations"] == captured["executions"] == 1
    assert captured["providers"] == ["codex_gpt55"]
    [prompt] = captured["prompts"]
    assert prompt.count("TARGET_DOCUMENT_SENTINEL") == 1
    assert prompt.count("FOCUS_SENTINEL") == 1
    assert prompt.count("docs/design/context-a.md") == 1
    assert prompt.count("docs/design/context-b.md") == 1
    assert prompt.count("artifacts/work/checks.md") == 1
    assert prompt.count("artifacts/review/review.md") >= 1

    review_bundle = _bundle(result, "::review-design-docs.v1")
    provider_node = next(
        node
        for node in review_bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    identity = provider_node.execution_config.compiled_prompt_fragment_identity
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    publications = [
        event
        for allocation in persisted["provider_attempt_allocations"].values()
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    ]
    assert len(publications) == 1
    publication = publications[0]
    record = validate_fragment_success_evidence(
        json.loads(
            (manager.run_root / publication["relative_path"]).read_text(
                encoding="ascii"
            )
        )
    )
    assert record["record_kind"] == "prompt_snapshot"
    assert record["compiled_prompt_fragment_identity"] == identity
    terminal = validate_terminal_evidence(
        manager.run_root,
        manager.state_file,
    )
    assert terminal.index["allocation_only_gaps"] == []
    assert [row["record_kind"] for row in terminal.index["publications"]] == [
        "prompt_snapshot"
    ]
    assert completed["workflow_outputs"]["return__variant"] == "APPROVED"
    assert (
        completed["workflow_outputs"]["return__review_report"]
        == "artifacts/review/review.md"
    )


def test_real_consumer_default_resume_reuses_committed_review_boundary_once(
    tmp_path: Path,
) -> None:
    result = _compile(
        CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path,
    )
    bundle = _bundle(result, "::review-revise-design-docs")
    manager = _runtime_manager(
        tmp_path,
        source_path=CONSUMER,
        bundle=bundle,
        run_id="prompt-core-resume",
    )
    captured: dict[str, object] = {}
    prepare, execute = _capturing_review_provider(tmp_path, captured)
    original_emit = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )

    def interrupt_after_review_boundary(
        self,
        state,
        step_name,
        step,
        finalized,
    ):
        original_emit(self, state, step_name, step, finalized)
        artifacts = finalized.get("artifacts", {})
        if (
            artifacts.get("return__variant") == "APPROVED"
            and "__review__%proc-ref-call." in step_name
            and step_name.endswith("__result")
        ):
            raise _ProviderBoundaryInterruption

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_review_boundary,
    ):
        with pytest.raises(_ProviderBoundaryInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    assert captured["preparations"] == captured["executions"] == 1
    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError(
            "committed review boundary must not prepare again"
        ),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError(
            "committed review boundary must not execute again"
        ),
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(
            resume=True,
            on_error="stop",
        )

    assert resumed["status"] == "completed"
    assert captured["preparations"] == captured["executions"] == 1
    assert resumed["workflow_outputs"]["return__variant"] == "APPROVED"


def test_real_consumer_legacy_checkpoint_program_identity_is_rejected(
    tmp_path: Path,
) -> None:
    legacy_result, _, legacy_manager, _, legacy_state = _execute_consumer(
        source_path=LEGACY_FIXTURE / "review_revise_design_docs.orc",
        prompt_externs=_manifest(LEGACY_FIXTURE / "prompts.json"),
        workspace=tmp_path,
        run_id="prompt-core-legacy-identity",
    )
    assert legacy_state["status"] == "completed"
    migrated_result = _compile(
        CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path,
    )
    legacy_review = _bundle(legacy_result, "::review-design-docs.v1")
    migrated_review = _bundle(migrated_result, "::review-design-docs.v1")
    [legacy_point] = legacy_review.runtime_plan.lexical_checkpoint_points
    [migrated_point] = migrated_review.runtime_plan.lexical_checkpoint_points
    assert migrated_point.checkpoint_id == legacy_point.checkpoint_id

    [record_path] = (
        legacy_manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "records"
        / legacy_point.checkpoint_id
    ).glob("*.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    legacy_identity = checkpoint_runtime_program_identity(
        state_manager=legacy_manager,
        runtime_plan=legacy_review.runtime_plan,
        workflow_path=LEGACY_FIXTURE / "review_revise_design_docs.orc",
    )
    migrated_identity = checkpoint_runtime_program_identity(
        state_manager=legacy_manager,
        runtime_plan=migrated_review.runtime_plan,
        workflow_path=CONSUMER,
    )
    validate_checkpoint_record(
        record,
        expected_program_identity=legacy_identity,
    )
    assert migrated_identity["source_module_digest"] != (
        legacy_identity["source_module_digest"]
    )
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        validate_checkpoint_record(
            record,
            expected_program_identity=migrated_identity,
        )


def test_real_consumer_unchanged_migration_has_stable_fragment_and_checkpoint_identity(
    tmp_path: Path,
) -> None:
    first = _compile(
        CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path / "first",
    )
    second = _compile(
        CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path / "second",
    )
    first_review = _bundle(first, "::review-design-docs.v1")
    second_review = _bundle(second, "::review-design-docs.v1")
    first_step = _provider_step(first_review)
    second_step = _provider_step(second_review)
    assert first_step.compiled_prompt_fragment_identity == (
        second_step.compiled_prompt_fragment_identity
    )
    assert first_step.compiler_prompt_fragment_contract == (
        second_step.compiler_prompt_fragment_contract
    )
    assert tuple(
        point.checkpoint_id
        for point in first_review.runtime_plan.lexical_checkpoint_points
    ) == tuple(
        point.checkpoint_id
        for point in second_review.runtime_plan.lexical_checkpoint_points
    )
    manager = StateManager(tmp_path, run_id="prompt-core-stable-identity")
    assert checkpoint_runtime_program_identity(
        state_manager=manager,
        runtime_plan=first_review.runtime_plan,
        workflow_path=CONSUMER,
    ) == checkpoint_runtime_program_identity(
        state_manager=manager,
        runtime_plan=second_review.runtime_plan,
        workflow_path=CONSUMER,
    )


def test_prompt_core_generic_machinery_contains_no_consumer_identity() -> None:
    forbidden = (
        "review_revise_design_docs",
        "review-design-docs",
        "providers.design-docs.review",
        "prompts.design-docs.review",
        "prompts/workflows/review_revise_design_docs/review.md",
    )
    generic_roots = (
        REPO_ROOT / "orchestrator" / "workflow",
        REPO_ROOT / "orchestrator" / "workflow_lisp",
        REPO_ROOT / "orchestrator" / "providers",
    )
    offenders: list[str] = []
    for root in generic_roots:
        for path in sorted(root.rglob("*.py")):
            content = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in content:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{token}"
                    )
    assert offenders == []
