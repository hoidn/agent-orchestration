"""Real-consumer Q2 acceptance coverage with frozen target-2.20 Q1 controls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.contracts.prompt_contract import (
    render_output_contract_block,
    render_variant_output_contract_block,
)
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
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    canonical_compiler_prompt_fragment_contract_json,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.lexical_checkpoints import (
    checkpoint_runtime_program_identity,
    validate_checkpoint_record,
)
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
CONSUMER = REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc"
Q1_RESUME_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "prompt_q1_target_2_20_resume.orc"
)
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
FROZEN_Q1_FRAGMENT_IDENTITY = (
    "sha256:306ceeaa45d96de5f7a90387d8958e9d6348eb79b2cec8f19a6874c1fa78b5e7"
)
FROZEN_Q1_CARRIER_SHA256 = (
    "a8081747d726424be0b6858d2d9cfec47b1dcf123b12aa91c1c8bd656440cf8f"
)


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
        output_bundle_paths = captured.setdefault("output_bundle_paths", [])
        assert isinstance(prompts, list)
        assert isinstance(providers, list)
        assert isinstance(output_bundle_paths, list)
        providers.append(provider_name)
        prompts.append(str(kwargs.get("prompt_content", "")))
        env = kwargs.get("env") or {}
        output_bundle_paths.append(
            str(env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        )
        captured["preparations"] = int(captured.get("preparations", 0)) + 1
        return SimpleNamespace(
            input_mode="stdin",
            prompt=prompts[-1],
            env=env,
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


def test_target_2_20_q1_fixture_clean_run_freezes_v1_carrier_and_artifacts(
    tmp_path: Path,
) -> None:
    result, _, _, captured, completed = _execute_consumer(
        source_path=Q1_RESUME_FIXTURE,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        workspace=tmp_path,
        run_id="prompt-q1-target-2-20-clean",
    )

    assert result.module.target_dsl_version == "2.20"
    review = _provider_step(_bundle(result, "::review-design-docs.v1"))
    contract = review.compiler_prompt_fragment_contract
    assert contract is not None
    assert contract.schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA
    assert review.compiled_prompt_fragment_identity == (
        FROZEN_Q1_FRAGMENT_IDENTITY
    )
    carrier_bytes = canonical_compiler_prompt_fragment_contract_json(
        contract
    ).encode("utf-8")
    assert hashlib.sha256(carrier_bytes).hexdigest() == (
        FROZEN_Q1_CARRIER_SHA256
    )
    assert not hasattr(contract, "output_positions")
    assert review.common.expected_outputs == ()

    assert completed["status"] == "completed"
    assert captured["preparations"] == captured["executions"] == 1
    assert completed["workflow_outputs"]["return__variant"] == "APPROVED"
    assert completed["workflow_outputs"]["return__review_report"] == (
        "artifacts/review/review.md"
    )
    assert (
        tmp_path / "artifacts" / "review" / "review.md"
    ).read_text(encoding="utf-8") == "REVIEW_REPORT_SENTINEL\n"
    assert json.loads(
        (tmp_path / "artifacts" / "work" / "findings.json").read_text(
            encoding="utf-8"
        )
    ) == {"items": []}


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_real_consumer_migrates_review_report_fill_to_q2_output_position(
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

    assert result.module.target_dsl_version == "2.21"
    prompt = result.prompt_catalog.resolve("review-design-doc")
    assert prompt.declaration.return_spec is not None
    assert prompt.declaration.return_spec.type_name == "ReviewDecision"
    assert tuple(
        (
            slot.declaration.name,
            slot.declaration.kind.value,
            slot.declaration.output_role.value,
            slot.declaration.refinement_type_name,
        )
        for slot in prompt.slots
    ) == (
        ("target_doc", "doc", "none", "DesignDocPath"),
        ("context_docs", "value", "none", "List[DesignDocPath]"),
        ("review_focus", "text", "none", None),
        ("checks_report", "path", "none", "WorkReportPath"),
        (
            "review_report_target_path",
            "path",
            "required_string_file",
            "ReviewReportTargetPath",
        ),
    )
    contract = review.compiler_prompt_fragment_contract
    assert contract is not None
    assert contract.schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2
    assert contract.compiled_prompt_fragment_identity == (
        review.compiled_prompt_fragment_identity
    )
    assert tuple(
        (
            row.slot_name,
            row.output_role,
            dict(row.expected_output),
        )
        for row in contract.output_positions
    ) == (
        (
            "review_report_target_path",
            "required_string_file",
            {
                "name": "review_report_target_path",
                "path": "${inputs.inputs__review_report_target_path}",
                "type": "string",
                "required": True,
            },
        ),
    )
    assert review.common.expected_outputs == tuple(
        dict(row.expected_output) for row in contract.output_positions
    )
    assert review.common.output_bundle is None
    assert review.common.variant_output is not None
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
    assert tuple(
        slot.placeholder_ordinals for slot in contract.rendered_slots
    ) == ((1,), (0,), (2,), (3,))
    assert tuple(
        slot.value_source["binding"]["ref"]
        for slot in contract.rendered_slots
    ) == (
        "inputs.completed__context_docs",
        "inputs.inputs__review_focus",
        "inputs.inputs__checks_report",
        "inputs.inputs__review_report_target_path",
    )
    assert contract.rendered_slots[0].static_type == {
        "kind": "list",
        "item": {
            "kind": "path",
            "name": "DesignDocPath",
            "under": "docs",
            "must_exist_target": True,
        },
    }
    assert tuple(
        (slot.static_type["kind"], slot.static_type.get("name"))
        for slot in contract.rendered_slots[1:]
    ) == (
        ("primitive", "String"),
        ("path", "WorkReportPath"),
        ("path", "ReviewReportTargetPath"),
    )
    assert tuple(
        name
        for _, name in sorted(
            (
                slot.placeholder_ordinals[0],
                slot.name,
            )
            for slot in contract.rendered_slots
        )
    ) == (
        "review_focus",
        "context_docs",
        "checks_report",
        "review_report_target_path",
    )
    assert all(
        contract.template_utf8.count(f"{{{slot.name}}}") == 1
        for slot in contract.rendered_slots
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


def test_real_consumer_q2_contract_matches_classic_and_wcc(
    tmp_path: Path,
) -> None:
    results = {
        route: _compile(
            CONSUMER,
            prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
            lowering_route=route,
            workspace_root=tmp_path / route,
        )
        for route in ("legacy", "wcc_m4")
    }

    def projection(result):
        bundle = _bundle(result, "::review-design-docs.v1")
        review = _provider_step(bundle)
        contract = review.compiler_prompt_fragment_contract
        assert contract is not None
        return {
            "target_dsl": result.module.target_dsl_version,
            "fragment_identity": review.compiled_prompt_fragment_identity,
            "fragment_contract": (
                canonical_compiler_prompt_fragment_contract_json(contract)
            ),
            "expected_outputs": tuple(
                dict(row) for row in review.common.expected_outputs
            ),
            "variant_output": review.common.variant_output,
        }

    assert projection(results["legacy"]) == projection(results["wcc_m4"])


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


def test_real_consumer_composes_dependency_fragment_and_result_contract_once(
    tmp_path: Path,
) -> None:
    result, _, _, captured, completed = _execute_consumer(
        source_path=CONSUMER,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        workspace=tmp_path,
        run_id="prompt-core-composition",
    )

    assert completed["status"] == "completed"
    assert captured["preparations"] == captured["executions"] == 1
    [prompt] = captured["prompts"]
    [output_bundle_path] = captured["output_bundle_paths"]
    review = _provider_step(_bundle(result, "::review-design-docs.v1"))
    fragment_contract = review.compiler_prompt_fragment_contract
    assert fragment_contract is not None
    slot_values = {
        "context_docs": [
            "docs/design/context-a.md",
            "docs/design/context-b.md",
        ],
        "review_focus": "FOCUS_SENTINEL",
        "checks_report": "artifacts/work/checks.md",
        "review_report_target_path": "artifacts/review/review.md",
    }
    fragment = render_prompt_fragment_base(
        fragment_contract,
        resolved_slot_values=slot_values,
    )
    assert fragment == render_prompt_fragment_base(
        fragment_contract,
        resolved_slot_values=slot_values,
    )
    rendered_insertions = (
        "FOCUS_SENTINEL",
        '["docs/design/context-a.md","docs/design/context-b.md"]',
        "artifacts/work/checks.md",
    )
    assert all(fragment.count(value) == 1 for value in rendered_insertions)
    assert all(prompt.count(value) == 1 for value in rendered_insertions)
    assert fragment.count("artifacts/review/review.md") == 1
    assert prompt.count("artifacts/review/review.md") == 2
    assert [fragment.index(value) for value in rendered_insertions] == sorted(
        fragment.index(value) for value in rendered_insertions
    )
    assert prompt.count(fragment) == 1
    dependency_lane, separator, result_contract_lane = prompt.partition(
        fragment
    )
    assert separator == fragment
    assert dependency_lane.count("TARGET_DOCUMENT_SENTINEL") == 1
    assert "TARGET_DOCUMENT_SENTINEL" not in fragment
    assert "TARGET_DOCUMENT_SENTINEL" not in result_contract_lane
    assert prompt.index("TARGET_DOCUMENT_SENTINEL") < prompt.index(fragment)

    rendered_expected_contract = render_output_contract_block(
        [
            {
                "name": "review_report_target_path",
                "path": "artifacts/review/review.md",
                "type": "string",
                "required": True,
            }
        ]
    )
    rendered_result_contract = render_variant_output_contract_block(
        {
            **review.common.variant_output,
            "path": output_bundle_path,
        }
    )
    assert result_contract_lane
    assert result_contract_lane == (
        "\n"
        + rendered_expected_contract
        + "\n\n"
        + rendered_result_contract
    )
    assert prompt.count(rendered_expected_contract) == 1
    assert prompt.count(rendered_result_contract) == 1
    assert prompt.index(fragment) < prompt.index(rendered_result_contract)
    assert prompt.index(fragment) < prompt.index(rendered_expected_contract)
    assert prompt.index(rendered_expected_contract) < prompt.index(
        rendered_result_contract
    )
    assert result_contract_lane.count(output_bundle_path) == 1
    assert all(
        value not in result_contract_lane for value in rendered_insertions
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


@pytest.mark.parametrize(
    "source_path",
    (Q1_RESUME_FIXTURE, CONSUMER),
    ids=("target-2.20-q1-control", "target-2.21-real-consumer"),
)
def test_review_consumer_default_resume_reuses_committed_review_boundary_once(
    tmp_path: Path,
    source_path: Path,
) -> None:
    result = _compile(
        source_path,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path,
    )
    bundle = _bundle(result, "::review-revise-design-docs")
    manager = _runtime_manager(
        tmp_path,
        source_path=source_path,
        bundle=bundle,
        run_id=f"prompt-core-resume-{source_path.stem}",
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
    committed = json.loads(manager.state_file.read_text(encoding="utf-8"))
    committed_review = next(
        step
        for step in committed["steps"].values()
        if step.get("artifacts", {}).get("return__variant") == "APPROVED"
    )
    assert committed_review["artifacts"]["return__review_report"] == (
        "artifacts/review/review.md"
    )
    assert (
        tmp_path / "artifacts" / "review" / "review.md"
    ).read_text(encoding="utf-8") == "REVIEW_REPORT_SENTINEL\n"
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
    assert resumed["workflow_outputs"]["return__review_report"] == (
        "artifacts/review/review.md"
    )
    if source_path == Q1_RESUME_FIXTURE:
        review = _provider_step(_bundle(result, "::review-design-docs.v1"))
        contract = review.compiler_prompt_fragment_contract
        assert contract is not None
        assert contract.schema_version == COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA
        assert not hasattr(contract, "output_positions")
        assert review.common.expected_outputs == ()


def test_target_2_20_q1_checkpoint_rejects_q2_projected_contract_drift(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    q1_result, _, q1_manager, _, q1_state = _execute_consumer(
        source_path=Q1_RESUME_FIXTURE,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        workspace=workspace,
        run_id="prompt-q1-q2-program-drift",
    )
    assert q1_state["status"] == "completed"

    q2_source = tmp_path / "q2-source" / Q1_RESUME_FIXTURE.name
    q2_source.parent.mkdir(parents=True)
    q1_text = Q1_RESUME_FIXTURE.read_text(encoding="utf-8")
    assert q1_text.count('(:target-dsl "2.20")') == 1
    assert q1_text.count(
        "(review_report_target_path :path ReviewReportTargetPath)"
    ) == 1
    q2_source.write_text(
        q1_text.replace('(:target-dsl "2.20")', '(:target-dsl "2.21")').replace(
            "(review_report_target_path :path ReviewReportTargetPath)",
            "(review_report_target_path :path :out ReviewReportTargetPath)",
        ),
        encoding="utf-8",
    )
    q2_result = _compile(
        q2_source,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=workspace,
    )
    q1_review = _bundle(q1_result, "::review-design-docs.v1")
    q2_review = _bundle(q2_result, "::review-design-docs.v1")
    q1_step = _provider_step(q1_review)
    q2_step = _provider_step(q2_review)
    assert q1_step.compiler_prompt_fragment_contract.schema_version == (
        COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA
    )
    assert q2_step.compiler_prompt_fragment_contract.schema_version == (
        COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2
    )
    assert q1_step.compiled_prompt_fragment_identity != (
        q2_step.compiled_prompt_fragment_identity
    )
    [q1_point] = q1_review.runtime_plan.lexical_checkpoint_points
    [q2_point] = q2_review.runtime_plan.lexical_checkpoint_points
    assert q2_point.checkpoint_id == q1_point.checkpoint_id

    [record_path] = (
        q1_manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "records"
        / q1_point.checkpoint_id
    ).glob("*.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    q1_identity = checkpoint_runtime_program_identity(
        state_manager=q1_manager,
        runtime_plan=q1_review.runtime_plan,
        workflow_path=Q1_RESUME_FIXTURE,
    )
    q2_identity = checkpoint_runtime_program_identity(
        state_manager=q1_manager,
        runtime_plan=q2_review.runtime_plan,
        workflow_path=q2_source,
    )
    validate_checkpoint_record(
        record,
        expected_program_identity=q1_identity,
    )
    assert q2_identity["source_module_digest"] != (
        q1_identity["source_module_digest"]
    )
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        validate_checkpoint_record(
            record,
            expected_program_identity=q2_identity,
        )


def test_real_consumer_live_boundary_rejects_q2_projected_contract_drift(
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
        run_id="prompt-q2-live-contract-drift",
    )
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    )
    review_bundle = _bundle(result, "::review-design-docs.v1")
    provider_node = next(
        node
        for node in review_bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    )
    config = provider_node.execution_config
    object.__setattr__(
        config,
        "common",
        replace(config.common, expected_outputs=()),
    )
    captured: dict[str, object] = {}
    prepare, execute = _capturing_review_provider(tmp_path, captured)

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute,
    ), pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        executor.execute(on_error="stop")

    assert captured == {}
    assert manager.state is not None
    assert manager.state.provider_attempt_allocations == {}


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
        "review-design-doc",
        "providers.design-docs.review",
        "prompts.design-docs.review",
        "prompts/workflows/review_revise_design_docs/review.md",
        "review_report_target_path",
        "prompt_q1_target_2_20_resume",
    )
    generic_roots = (
        REPO_ROOT / "orchestrator" / "contracts",
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
