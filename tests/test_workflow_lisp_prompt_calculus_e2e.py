"""Real-consumer Q2 acceptance coverage with frozen target-2.20 Q1 controls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from enum import Enum
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
    FRAGMENT_SUCCESS_SCHEMA_V2,
    FRAGMENT_SUCCESS_SCHEMA_V3,
    validate_fragment_success_evidence,
    validate_terminal_evidence,
)
from orchestrator.workflow.prompt_context_report import (
    PROMPT_CONTEXT_REPORT_SCHEMA,
    project_prompt_context,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    canonical_compiler_prompt_fragment_contract_json,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.lexical_checkpoints import (
    checkpoint_runtime_program_identity,
    validate_checkpoint_record,
)
from orchestrator.workflow_lisp.source_map import (
    SourceMapEntry,
    build_source_map_document,
)
from orchestrator.workflow_lisp.spans import SourcePosition
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
CONSUMER = REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc"
JUDGMENT_PANEL = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "review_revise_design_docs_judgment_panel.orc"
)
JUDGMENT_PANEL_INPUTS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
JUDGMENT_PANEL_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)
Q1_RESUME_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "prompt_q1_target_2_20_resume.orc"
)
Q2_COMPOSED_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "prompt_calculus"
    / "review_revise_design_docs_target_2_21.orc"
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
    "providers.design-docs.review": "codex",
    "providers.design-docs.fix": "codex_gpt55",
}
FROZEN_Q1_FRAGMENT_IDENTITY = (
    "sha256:306ceeaa45d96de5f7a90387d8958e9d6348eb79b2cec8f19a6874c1fa78b5e7"
)
FROZEN_Q1_CARRIER_SHA256 = (
    "a8081747d726424be0b6858d2d9cfec47b1dcf123b12aa91c1c8bd656440cf8f"
)
FROZEN_Q2_SOURCE_SHA256 = (
    "157211801379b7290c7881d8e37b82da14a3ee66eb0fdfd135a4dba1277fb743"
)
PRE_Q4_SOURCE_SIZE = 8_079
Q4_SOURCE_SIZE = 8_149
PRE_Q4_SOURCE_SHA256 = (
    "89176c15dcaf29b5212441ad4776593d919880784fe0f531c9034b8a177640d7"
)
Q4_SOURCE_SHA256 = (
    "8784501577c4f162f584a2ae17d1644a6bc4ea0c8bfbd18cdb0c1b7fd24a0598"
)
PRE_Q4_EXPORT_DECLARATION = b"  (export review-revise-design-docs)\n"
Q4_EXPORT_DECLARATION = (
    b"  (export review-revise-design-docs DesignDocPath "
    b"ReviewReportTargetPath WorkReportPath review-design-doc)\n"
)


class _ProviderBoundaryInterruption(BaseException):
    pass


def _manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return {str(key): value for key, value in payload.items()}


def _compile(
    source_path: Path,
    *,
    prompt_externs: dict[str, str],
    lowering_route: str,
    workspace_root: Path,
):
    compile_source_path = source_path
    if source_path == Q2_COMPOSED_FIXTURE:
        compile_source_path = (
            workspace_root
            / "q2-composed-control"
            / "review_revise_design_docs.orc"
        )
        compile_source_path.parent.mkdir(parents=True, exist_ok=True)
        compile_source_path.write_bytes(source_path.read_bytes())
    return compile_stage3_module(
        compile_source_path,
        provider_externs=PROVIDERS,
        prompt_externs=prompt_externs,
        validate_shared=True,
        workspace_root=workspace_root,
        lowering_route=lowering_route,
    )


def _compile_judgment_panel(workspace_root: Path):
    return compile_stage3_entrypoint(
        JUDGMENT_PANEL,
        source_roots=(CONSUMER.parent,),
        entry_workflow=(
            "review-revise-design-docs-judgment-panel"
        ),
        provider_externs=_manifest(
            JUDGMENT_PANEL_INPUTS / "providers.json"
        ),
        prompt_externs=_manifest(
            JUDGMENT_PANEL_INPUTS / "prompts.json"
        ),
        validate_shared=True,
        workspace_root=workspace_root,
        lowering_route="wcc_m4",
    )


def _bundle(result, suffix: str):
    return next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name.endswith(suffix)
    )


def _provider_step(bundle):
    return next(step for step in bundle.surface.steps if step.kind.value == "provider")


def _plain_compiled_projection(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain_compiled_projection(
                getattr(value, field.name)
            )
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _plain_compiled_projection(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_plain_compiled_projection(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_plain_compiled_projection(item) for item in value),
            key=repr,
        )
    return value


def _compiled_source_map(result, *, entry_name: str):
    return build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name={"__main__": result},
            validated_bundles_by_name=result.validated_bundles,
        ),
        selected_name=entry_name,
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )


def _authored_source_coordinates(value) -> tuple[tuple[object, ...], ...]:
    coordinates: set[tuple[object, ...]] = set()

    def visit(candidate) -> None:
        if isinstance(candidate, SourceMapEntry):
            coordinates.add(
                (
                    tuple(candidate.form_path),
                    candidate.path,
                    candidate.line,
                    candidate.column,
                    candidate.end_line,
                    candidate.end_column,
                )
            )
            return
        if is_dataclass(candidate) and not isinstance(candidate, type):
            for field in fields(candidate):
                visit(getattr(candidate, field.name))
            return
        if isinstance(candidate, Mapping):
            for item in candidate.values():
                visit(item)
            return
        if isinstance(candidate, (list, tuple)):
            for item in candidate:
                visit(item)

    visit(value)
    return tuple(sorted(coordinates, key=repr))


def _source_position_rows(value) -> set[tuple[str, int, int, int]]:
    positions: set[tuple[str, int, int, int]] = set()
    seen: set[int] = set()

    def visit(candidate) -> None:
        if isinstance(candidate, SourcePosition):
            positions.add(
                (
                    candidate.path,
                    candidate.line,
                    candidate.column,
                    candidate.offset,
                )
            )
            return
        if not (
            (is_dataclass(candidate) and not isinstance(candidate, type))
            or isinstance(candidate, Mapping)
            or isinstance(candidate, (list, tuple, set, frozenset))
        ):
            return
        identity = id(candidate)
        if identity in seen:
            return
        seen.add(identity)
        if is_dataclass(candidate) and not isinstance(candidate, type):
            for field in fields(candidate):
                visit(getattr(candidate, field.name))
        elif isinstance(candidate, Mapping):
            for item in candidate.values():
                visit(item)
        else:
            for item in candidate:
                visit(item)

    visit(value)
    return positions


def _assert_q4_source_position_relation(
    before,
    after,
    *,
    source_path: Path,
) -> None:
    before_rows = _source_position_rows(before)
    after_rows = _source_position_rows(after)
    before_by_coordinate = {
        (path, line, column): offset
        for path, line, column, offset in before_rows
    }
    after_by_coordinate = {
        (path, line, column): offset
        for path, line, column, offset in after_rows
    }
    canonical_source = source_path.resolve().as_posix()
    compared_exact = 0
    compared_shifted = 0
    for coordinate in sorted(
        set(before_by_coordinate) | set(after_by_coordinate)
    ):
        path, line, _column = coordinate
        if path == canonical_source and line == 8:
            continue
        assert coordinate in before_by_coordinate
        assert coordinate in after_by_coordinate
        before_offset = before_by_coordinate[coordinate]
        after_offset = after_by_coordinate[coordinate]
        if path == canonical_source and line > 8:
            assert after_offset == before_offset + 70
            compared_shifted += 1
        else:
            assert after_offset == before_offset
            compared_exact += 1
    assert compared_exact > 0
    assert compared_shifted > 0


def _leaf_differences(
    before,
    after,
    *,
    path: tuple[object, ...] = (),
) -> tuple[tuple[tuple[object, ...], object, object], ...]:
    differences: list[tuple[tuple[object, ...], object, object]] = []
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        assert set(before) == set(after)
        for key in sorted(before):
            differences.extend(
                _leaf_differences(
                    before[key],
                    after[key],
                    path=(*path, key),
                )
            )
        return tuple(differences)
    if isinstance(before, list) and isinstance(after, list):
        assert len(before) == len(after)
        for index, (before_item, after_item) in enumerate(
            zip(before, after, strict=True)
        ):
            differences.extend(
                _leaf_differences(
                    before_item,
                    after_item,
                    path=(*path, index),
                )
            )
        return tuple(differences)
    if before != after:
        differences.append((path, before, after))
    return tuple(differences)


def _pre_q4_consumer_source_bytes() -> bytes:
    current = CONSUMER.read_bytes()
    if PRE_Q4_EXPORT_DECLARATION in current:
        assert current.count(PRE_Q4_EXPORT_DECLARATION) == 1
        return current
    assert current.count(Q4_EXPORT_DECLARATION) == 1
    return current.replace(
        Q4_EXPORT_DECLARATION,
        PRE_Q4_EXPORT_DECLARATION,
    )


def _target_2_23_phased_entry_projection(
    result,
) -> bytes:
    entry_name = "review_revise_design_docs::review-revise-design-docs"
    entry = _bundle(result, "::review-revise-design-docs")
    helper = _bundle(result, "::review-design-docs.v1")
    review = _provider_step(helper)
    contract = review.compiler_prompt_fragment_contract
    assert contract is not None
    typed_entry = next(
        workflow
        for workflow in result.typed_workflows
        if workflow.definition.name == entry_name
    )
    authored_input_names = tuple(
        name for name, _type_ref in typed_entry.signature.params
    )
    source_map = _compiled_source_map(
        result,
        entry_name=entry_name,
    )
    helper_source_map = source_map.workflows[helper.surface.name]
    parent_source_map = source_map.workflows[entry_name]
    projection = {
        "schema_version": "q4_task2_export_compatibility.v1",
        "target_dsl": result.module.target_dsl_version,
        "entry": {
            "name": entry.surface.name,
            "inputs": {
                name: entry.surface.inputs[name]
                for name in authored_input_names
            },
            "outputs": entry.surface.outputs,
        },
        "phased_review": {
            "provider_call_policy": review.provider_call_policy,
            "compiled_prompt_fragment_identity": (
                review.compiled_prompt_fragment_identity
            ),
            "prompt_attempt_identity_version": (
                review.prompt_attempt_identity_version
            ),
            "compiler_prompt_fragment_contract": (
                canonical_compiler_prompt_fragment_contract_json(contract)
            ),
            "expected_outputs": review.common.expected_outputs,
            "variant_output": review.common.variant_output,
            "runtime_plan": helper.runtime_plan,
            "source_map": helper_source_map,
        },
        "parent_checkpoint_point_kinds": tuple(
            point.point_kind
            for point in entry.runtime_plan.lexical_checkpoint_points
        ),
        "parent_authored_source_coordinates": (
            _authored_source_coordinates(parent_source_map)
        ),
    }
    return json.dumps(
        _plain_compiled_projection(projection),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


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
    result, _, manager, captured, completed = _execute_consumer(
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
    prompt_context = project_prompt_context(
        manager._read_state_from_disk().to_dict(),
        manager.run_root,
    )
    assert prompt_context["schema_version"] == (
        PROMPT_CONTEXT_REPORT_SCHEMA
    )
    assert len(prompt_context["attempts"]) == 1
    [attempt] = prompt_context["attempts"]
    assert attempt["record_status"] == "legacy_snapshot"
    assert attempt["identity"] is None
    assert attempt["comparison"] == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": "legacy_snapshot_only",
    }


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

    assert result.module.target_dsl_version == "2.23"
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


def test_target_2_23_export_delta_preserves_selected_phased_entry_projection(
    tmp_path: Path,
) -> None:
    source_path = (
        tmp_path / "q4-export-control" / "review_revise_design_docs.orc"
    )
    source_path.parent.mkdir(parents=True)
    before_source = _pre_q4_consumer_source_bytes()
    after_source = CONSUMER.read_bytes()
    assert len(before_source) == PRE_Q4_SOURCE_SIZE
    assert len(after_source) == Q4_SOURCE_SIZE
    assert (
        hashlib.sha256(before_source).hexdigest()
        == PRE_Q4_SOURCE_SHA256
    )
    assert hashlib.sha256(after_source).hexdigest() == Q4_SOURCE_SHA256
    assert (
        before_source.replace(
            PRE_Q4_EXPORT_DECLARATION,
            Q4_EXPORT_DECLARATION,
        )
        == after_source
    )

    source_path.write_bytes(before_source)
    before = _compile(
        source_path,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path,
    )

    source_path.write_bytes(after_source)
    after = _compile(
        source_path,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        lowering_route="wcc_m4",
        workspace_root=tmp_path,
    )

    _assert_q4_source_position_relation(
        before,
        after,
        source_path=source_path,
    )
    before_projection = _target_2_23_phased_entry_projection(before)
    after_projection = _target_2_23_phased_entry_projection(after)
    assert after_projection == before_projection

    projection = json.loads(after_projection)
    assert set(projection) == {
        "schema_version",
        "target_dsl",
        "entry",
        "phased_review",
        "parent_checkpoint_point_kinds",
        "parent_authored_source_coordinates",
    }
    assert (
        projection["schema_version"]
        == "q4_task2_export_compatibility.v1"
    )
    assert projection["target_dsl"] == "2.23"
    phased_review = projection["phased_review"]
    assert set(phased_review) == {
        "provider_call_policy",
        "compiled_prompt_fragment_identity",
        "prompt_attempt_identity_version",
        "compiler_prompt_fragment_contract",
        "expected_outputs",
        "variant_output",
        "runtime_plan",
        "source_map",
    }
    assert phased_review["provider_call_policy"]["delivery"] == "phased"
    assert (
        phased_review["provider_call_policy"]["materialization_attempts"]
        == 2
    )
    assert (
        phased_review["prompt_attempt_identity_version"]
        == "workflow_prompt_attempt_identity.v2"
    )
    assert phased_review["compiled_prompt_fragment_identity"].startswith(
        "sha256:"
    )
    assert (
        json.loads(
            phased_review["compiler_prompt_fragment_contract"]
        )["schema_version"]
        == "compiler_prompt_fragment_contract.v2"
    )
    assert FRAGMENT_SUCCESS_SCHEMA_V3 == (
        "workflow_prompt_fragment_snapshot.functional.v3"
    )
    assert phased_review["expected_outputs"] == [
        {
            "name": "review_report_target_path",
            "path": "${inputs.inputs__review_report_target_path}",
            "required": True,
            "type": "string",
        }
    ]
    assert phased_review["variant_output"]["discriminant"]["allowed"] == [
        "APPROVE",
        "REVISE",
        "BLOCKED",
    ]
    assert (
        phased_review["runtime_plan"]["lexical_checkpoint_points"][0][
            "checkpoint_id"
        ]
        == "ckpt:d2553c2c3a954e553e791195"
    )
    assert phased_review["source_map"]["workflow_name"].endswith(
        "::review-design-docs.v1"
    )
    assert phased_review["source_map"]["workflow_origin"]["form_path"] == [
        "workflow-lisp",
        "defproc",
        "review-design-docs",
    ]
    assert projection["parent_checkpoint_point_kinds"] == [
        "effect_boundary",
        "loop_back_edge",
    ]
    assert projection["parent_authored_source_coordinates"]

    before_helper = _bundle(before, "::review-design-docs.v1")
    after_helper = _bundle(after, "::review-design-docs.v1")
    before_review = _provider_step(before_helper)
    after_review = _provider_step(after_helper)
    assert before_review.step_id == after_review.step_id
    before_prompt_keys = tuple(before_helper.semantic_ir.prompt_surfaces)
    after_prompt_keys = tuple(after_helper.semantic_ir.prompt_surfaces)
    assert before_prompt_keys == after_prompt_keys
    assert len(before_prompt_keys) == 1
    helper_differences = _leaf_differences(
        _plain_compiled_projection(before_helper),
        _plain_compiled_projection(after_helper),
    )
    dependency_leaf = (
        "compiler_prompt_dependency_contract",
        "source_workflow_sha256",
    )
    expected_helper_paths = {
        ("surface", "steps", 0, *dependency_leaf),
        (
            "core_workflow_ast",
            "_surface_workflow",
            "steps",
            0,
            *dependency_leaf,
        ),
        ("core_workflow_ast", "body", 0, *dependency_leaf),
        (
            "core_workflow_ast",
            "body",
            0,
            "_surface_step",
            *dependency_leaf,
        ),
        (
            "ir",
            "nodes",
            before_review.step_id,
            "execution_config",
            *dependency_leaf,
        ),
        (
            "semantic_ir",
            "prompt_surfaces",
            before_prompt_keys[0],
            *dependency_leaf,
        ),
    }
    assert len(helper_differences) == 6
    assert {
        path for path, _before_value, _after_value in helper_differences
    } == expected_helper_paths
    assert {
        before_value
        for _path, before_value, _after_value in helper_differences
    } == {f"sha256:{PRE_Q4_SOURCE_SHA256}"}
    assert {
        after_value
        for _path, _before_value, after_value in helper_differences
    } == {f"sha256:{Q4_SOURCE_SHA256}"}

    assert (
        hashlib.sha256(Q2_COMPOSED_FIXTURE.read_bytes()).hexdigest()
        == FROZEN_Q2_SOURCE_SHA256
    )


def test_judgment_panel_retains_composed_child_and_unfragmented_synthesis(
    tmp_path: Path,
) -> None:
    result = _compile_judgment_panel(tmp_path)
    entry_result = result.entry_result
    child = _bundle(entry_result, "::review-one")
    entry = _bundle(
        entry_result,
        "::review-revise-design-docs-judgment-panel",
    )
    review = _provider_step(child)
    synthesis = _provider_step(entry)
    source_map = _compiled_source_map(
        entry_result,
        entry_name=entry.surface.name,
    )
    child_source_map = source_map.workflows[child.surface.name]

    assert review.provider == "codex"
    assert review.provider_call_policy is not None
    assert review.provider_call_policy["delivery"] == "composed"
    assert (
        review.prompt_attempt_identity_version
        == "workflow_prompt_attempt_identity.v1"
    )
    assert review.compiled_prompt_fragment_identity is not None
    assert review.compiler_prompt_fragment_contract is not None
    assert (
        review.compiler_prompt_fragment_contract.schema_version
        == "compiler_prompt_fragment_contract.v2"
    )
    assert FRAGMENT_SUCCESS_SCHEMA_V2 == (
        "workflow_prompt_fragment_snapshot.functional.v2"
    )
    assert tuple(
        dict(row) for row in review.common.expected_outputs
    ) == (
        {
            "name": "review_report_target_path",
            "path": "${inputs.review_report_target_path}",
            "type": "string",
            "required": True,
        },
    )
    assert review.common.output_bundle is None
    assert review.common.variant_output is not None
    assert tuple(
        review.common.variant_output["discriminant"]["allowed"]
    ) == ("APPROVE", "REVISE", "BLOCKED")
    assert set(review.common.variant_output["variants"]) == {
        "APPROVE",
        "REVISE",
        "BLOCKED",
    }
    assert dict(child.surface.outputs["__result__"].definition) == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/review",
        "must_exist_target": True,
        "from": {
            "ref": (
                "root.steps."
                "review_revise_design_docs_judgment_panel::"
                "review-one__match_decision.artifacts.__result__"
            )
        },
    }
    assert child_source_map.workflow_origin.form_path == (
        "workflow-lisp",
        "defworkflow",
        "review-one",
    )
    assert (
        Path(child_source_map.workflow_origin.path)
        == JUDGMENT_PANEL
    )

    assert synthesis.provider == "codex"
    assert synthesis.input_file == (
        "prompts/workflows/review_revise_design_docs/synthesize.md"
    )
    assert synthesis.asset_file is None
    assert synthesis.compiler_prompt_fragment_contract is None
    assert synthesis.compiled_prompt_fragment_identity is None
    assert synthesis.prompt_attempt_identity_version is None
    assert synthesis.compiler_prompt_attempt_binding_plan is None
    assert synthesis.compiler_prompt_dependency_contract is None
    assert "delivery" not in dict(
        synthesis.provider_call_policy or {}
    )
    assert [
        row["binding_name"]
        for row in synthesis.typed_prompt_inputs
    ] == ["target_doc", "reports"]
    assert [
        row["value_type_name"]
        for row in synthesis.typed_prompt_inputs
    ] == [
        "DesignDocPath",
        "List[std/phase::ReviewReportPath]",
    ]
    assert synthesis.common.variant_output is None
    assert synthesis.common.output_bundle is not None
    [root_field] = synthesis.common.output_bundle["fields"]
    assert root_field["name"] == "__result__"
    assert root_field["json_pointer"] == ""
    assert root_field["type"] == "relpath"
    assert root_field["under"] == "artifacts/review"
    assert root_field["must_exist_target"] is True
    assert set(entry.surface.outputs) == {
        "return__reports",
        "return__synthesis",
    }
    assert (
        entry.surface.outputs["return__reports"].definition["items"]
        == {
            "type": "relpath",
            "under": "artifacts/review",
            "must_exist_target": True,
        }
    )


@pytest.mark.parametrize("lowering_route", ("legacy", "wcc_m4"))
def test_real_consumer_migration_preserves_fix_call_and_provider_policy(
    tmp_path: Path,
    lowering_route: str,
) -> None:
    assert hashlib.sha256(Q2_COMPOSED_FIXTURE.read_bytes()).hexdigest() == (
        FROZEN_Q2_SOURCE_SHA256
    )
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
    assert migrated_review.provider == legacy_review.provider == "codex"
    assert migrated_review.provider_params == legacy_review.provider_params
    assert migrated_review.common.timeout_sec == (
        legacy_review.common.timeout_sec
    ) == 3600
    legacy_policy = dict(legacy_review.provider_call_policy or {})
    migrated_policy = dict(migrated_review.provider_call_policy or {})
    assert {
        key: migrated_policy[key]
        for key in legacy_policy
    } == legacy_policy
    assert set(migrated_policy) - set(legacy_policy) == {
        "delivery",
        "materialization_attempts",
    }
    assert migrated_policy["delivery"] == "phased"
    assert migrated_policy["materialization_attempts"] == 2


def test_real_consumer_composes_dependency_fragment_and_result_contract_once(
    tmp_path: Path,
) -> None:
    result, _, _, captured, completed = _execute_consumer(
        source_path=Q2_COMPOSED_FIXTURE,
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
        source_path=Q2_COMPOSED_FIXTURE,
        prompt_externs=_manifest(CONSUMER_INPUTS / "prompts.json"),
        workspace=tmp_path,
        run_id="prompt-core-real-consumer",
    )

    assert completed["status"] == "completed"
    assert captured["preparations"] == captured["executions"] == 1
    assert captured["providers"] == ["codex"]
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
    prompt_context = project_prompt_context(
        manager._read_state_from_disk().to_dict(),
        manager.run_root,
    )
    assert prompt_context["schema_version"] == (
        PROMPT_CONTEXT_REPORT_SCHEMA
    )
    assert len(prompt_context["attempts"]) == 1
    [attempt] = prompt_context["attempts"]
    assert attempt["record_status"] == "legacy_snapshot"
    assert attempt["identity"] is None
    assert attempt["comparison"]["reason"] == "legacy_snapshot_only"
    assert completed["workflow_outputs"]["return__variant"] == "APPROVED"
    assert (
        completed["workflow_outputs"]["return__review_report"]
        == "artifacts/review/review.md"
    )


@pytest.mark.parametrize(
    "source_path",
    (Q1_RESUME_FIXTURE, Q2_COMPOSED_FIXTURE),
    ids=("target-2.20-q1-control", "target-2.21-q2-control"),
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
