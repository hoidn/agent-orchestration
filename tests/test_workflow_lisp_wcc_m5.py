from __future__ import annotations

import json
import ast
import re
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.state import StateManager
import orchestrator.workflow_lisp.lowering.control_loops as legacy_control_loops
import orchestrator.workflow_lisp.lowering.control_match as legacy_control_match
import orchestrator.workflow_lisp.lowering.effects as legacy_effects
import orchestrator.workflow_lisp.wcc.defunctionalize as wcc_defunctionalize
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.route import (
    DEFAULT_LOWERING_SCHEMA,
    DEFAULT_LOWERING_ROUTE,
    LOWERING_SCHEMA_LEGACY,
    LOWERING_SCHEMA_WCC,
    LoweringRoute,
    lowering_route_for_schema,
    lowering_schema_for_route,
    normalize_lowering_route,
)
from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding
from tests.workflow_lisp_characterization import build_behavior_observation, load_characterization_cases


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "workflow_lisp"


def _m5_provider_externs() -> dict[str, str]:
    return {
        "providers.execute": "fake-execute",
        "providers.review": "fake-review",
        "providers.fix": "fake-fix",
    }


def _m5_prompt_externs() -> dict[str, str]:
    return {
        "prompts.implementation.execute": "prompts/implementation/execute.md",
        "prompts.implementation.review": "prompts/implementation/review.md",
        "prompts.implementation.fix": "prompts/implementation/fix.md",
    }


def _m5_command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_checks": ExternalToolBinding(
            name="run_checks",
            stable_command=("python", "scripts/run_checks.py"),
        ),
        "validate_review_findings_v1": validate_review_findings_v1_binding(),
    }


def _m5_resume_command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        **_m5_command_boundaries(),
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
    }


def _assert_default_wcc_does_not_reach_surface_dispatcher(
    tmp_path: Path,
    fixture_name: str,
    *,
    command_boundaries: dict[str, ExternalToolBinding] | None = None,
) -> None:
    def _raise_surface_dispatcher(*_args, **_kwargs):
        raise RuntimeError("legacy surface dispatcher reached from WCC default")

    with patch.object(
        wcc_defunctionalize,
        "_control_lower_expression_impl",
        side_effect=_raise_surface_dispatcher,
        create=True,
    ):
        result = compile_stage3_module(
            FIXTURES / "valid" / fixture_name,
            provider_externs=_m5_provider_externs(),
            prompt_externs=_m5_prompt_externs(),
            command_boundaries=command_boundaries or _m5_command_boundaries(),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert result.lowering_schema_version == 2
    assert result.validated_bundles


def test_wcc_m5_default_route_and_schema_are_wcc_after_readiness_gate() -> None:
    assert DEFAULT_LOWERING_ROUTE is LoweringRoute.WCC_M4
    assert DEFAULT_LOWERING_SCHEMA == LOWERING_SCHEMA_WCC == 2
    assert LOWERING_SCHEMA_WCC == 2
    assert LOWERING_SCHEMA_LEGACY == 1
    assert normalize_lowering_route(None) is LoweringRoute.WCC_M4


def test_design_delta_review_findings_fixture_binding_carries_g0_metadata() -> None:
    binding = validate_review_findings_v1_binding()

    assert binding.retirement_class == "validation"
    assert binding.retirement_label == "keep_bridge"
    assert binding.bridge_owner == "std/phase"
    assert binding.evidence_refs


def test_lowering_schema_mapping_is_route_neutral() -> None:
    assert lowering_schema_for_route(LoweringRoute.LEGACY) == 1
    assert lowering_schema_for_route(LoweringRoute.WCC_M4) == 2
    assert lowering_schema_for_route("legacy") == 1
    assert lowering_schema_for_route("wcc_m4") == 2
    assert lowering_route_for_schema(1) is LoweringRoute.LEGACY
    assert lowering_route_for_schema(2) is LoweringRoute.WCC_M4


def test_compile_stage3_module_wcc_candidate_uses_schema_2(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
        lowering_route=LoweringRoute.WCC_M4,
        provider_externs=_m5_provider_externs(),
        prompt_externs=_m5_prompt_externs(),
        command_boundaries=_m5_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.lowering_schema_version == 2
    assert result.validated_bundles


def test_compile_stage3_entrypoint_wcc_candidate_uses_schema_2_for_module_graph(
    tmp_path: Path,
) -> None:
    source_root = FIXTURES / "modules" / "valid" / "imported_loop_recur_on_exhausted"
    result = compile_stage3_entrypoint(
        source_root / "entry.orc",
        source_roots=(source_root,),
        lowering_route=LoweringRoute.WCC_M4,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.entry_result.lowering_schema_version == 2
    assert result.entry_result.validated_bundles


def test_compile_stage3_module_defaults_to_wcc_schema_2(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
        provider_externs=_m5_provider_externs(),
        prompt_externs=_m5_prompt_externs(),
        command_boundaries=_m5_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.lowering_schema_version == 2
    assert result.validated_bundles


def test_compile_stage3_entrypoint_defaults_to_wcc_schema_2_for_module_graph(
    tmp_path: Path,
) -> None:
    source_root = FIXTURES / "modules" / "valid" / "imported_loop_recur_on_exhausted"
    result = compile_stage3_entrypoint(
        source_root / "entry.orc",
        source_roots=(source_root,),
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.entry_result.lowering_schema_version == 2
    assert result.entry_result.validated_bundles


def test_run_workflow_lisp_stamps_lowering_schema_2_in_run_state(tmp_path: Path, monkeypatch) -> None:
    workflow_path = FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc"
    providers_path = tmp_path / "providers.json"
    prompts_path = tmp_path / "prompts.json"
    commands_path = tmp_path / "commands.json"
    review_findings_binding = validate_review_findings_v1_binding()
    providers_path.write_text(json.dumps(_m5_provider_externs()), encoding="utf-8")
    prompts_path.write_text(json.dumps(_m5_prompt_externs()), encoding="utf-8")
    commands_path.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                },
                "validate_review_findings_v1": {
                    "kind": "external_tool",
                    "stable_command": list(review_findings_binding.stable_command),
                    "retirement_class": review_findings_binding.retirement_class,
                    "retirement_label": review_findings_binding.retirement_label,
                    "replacement_surface": review_findings_binding.replacement_surface,
                    "bridge_owner": review_findings_binding.bridge_owner,
                    "expiry_condition": review_findings_binding.expiry_condition,
                    "evidence_refs": list(review_findings_binding.evidence_refs),
                },
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        workflow=str(workflow_path),
        source_root=[str(workflow_path.parent)],
        entry_workflow=None,
        provider_externs_file=str(providers_path),
        prompt_externs_file=str(prompts_path),
        imported_workflow_bundles_file=None,
        command_boundaries_file=str(commands_path),
        emit_debug_yaml=False,
        state_dir=None,
        log_level="ERROR",
        debug=False,
        quiet=True,
        verbose=False,
        clean_processed=False,
        archive_processed=None,
        dry_run=False,
        input=None,
        input_file=None,
        context=None,
        context_file=None,
        backup_state=False,
        stream_output=False,
        max_retries=1,
        retry_delay=1000,
        on_error="stop",
        step_summaries=False,
        summary_mode=None,
        summary_profile=None,
        live_agent_notes=False,
        summary_timeout_sec=30,
        summary_max_input_chars=12000,
    )

    monkeypatch.chdir(tmp_path)
    with patch(
        "orchestrator.cli.commands.run.WorkflowExecutor.execute",
        return_value={"status": "completed"},
    ), patch("orchestrator.cli.commands.run.bind_workflow_inputs", return_value={}):
        result = run_workflow(args)

    assert result == 0
    run_roots = list((tmp_path / ".orchestrate" / "runs").iterdir())
    assert len(run_roots) == 1
    state_payload = StateManager(workspace=tmp_path, run_id=run_roots[0].name).load().to_dict()
    assert state_payload["context"]["workflow_lisp"]["lowering_schema_version"] == 2


def test_wcc_default_denylist_does_not_touch_covered_legacy_lowerers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_legacy_path(*_args, **_kwargs):
        raise AssertionError("legacy direct lowerer reached")

    monkeypatch.setattr(legacy_control_match, "_lower_match_expr", _raise_legacy_path)
    monkeypatch.setattr(legacy_control_loops, "_lower_loop_recur", _raise_legacy_path)
    monkeypatch.setattr(legacy_effects, "_lower_provider_result", _raise_legacy_path)
    monkeypatch.setattr(legacy_effects, "_lower_command_result", _raise_legacy_path)

    result = compile_stage3_module(
        FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
        provider_externs=_m5_provider_externs(),
        prompt_externs=_m5_prompt_externs(),
        command_boundaries=_m5_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.lowering_schema_version == 2
    assert result.validated_bundles


def test_promoted_lowering_modules_classify_covered_surface_form_branches() -> None:
    covered_forms = {
        "MatchExpr",
        "LoopRecurExpr",
        "ProviderResultExpr",
        "CommandResultExpr",
    }
    promoted_modules = [
        "orchestrator/workflow_lisp/lowering/core.py",
        "orchestrator/workflow_lisp/lowering/control_dispatch.py",
        "orchestrator/workflow_lisp/lowering/control_match.py",
        "orchestrator/workflow_lisp/lowering/control_loops.py",
        "orchestrator/workflow_lisp/lowering/effects.py",
        "orchestrator/workflow_lisp/lowering/phase_scope.py",
        "orchestrator/workflow_lisp/lowering/phase_flow.py",
        "orchestrator/workflow_lisp/lowering/phase_resource.py",
        "orchestrator/workflow_lisp/lowering/phase_drain.py",
        "orchestrator/workflow_lisp/lowering/procedures.py",
    ]
    allowed_markers = ("schema1_compatibility", "emitter")
    violations: list[str] = []

    def _names(node: ast.AST) -> set[str]:
        return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}

    for module_path in promoted_modules:
        path = Path(module_path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=module_path)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            matched_forms = covered_forms & _names(node.test)
            if not matched_forms:
                continue
            start = max(0, node.lineno - 3)
            end = min(len(lines), getattr(node, "end_lineno", node.lineno) + 2)
            nearby_source = "\n".join(lines[start:end])
            if any(marker in nearby_source for marker in allowed_markers):
                continue
            forms = ", ".join(sorted(matched_forms))
            violations.append(f"{module_path}:{node.lineno}: unclassified {forms} branch")

    assert violations == []


@pytest.mark.parametrize(
    ("fixture_name", "command_boundaries"),
    (
        ("phase_stdlib_run_provider_phase.orc", None),
        ("phase_stdlib_resume_or_start.orc", _m5_resume_command_boundaries()),
    ),
)
def test_wcc_default_phase_stdlib_forms_do_not_reach_legacy_surface_dispatcher(
    tmp_path: Path,
    fixture_name: str,
    command_boundaries: dict[str, ExternalToolBinding] | None,
) -> None:
    _assert_default_wcc_does_not_reach_surface_dispatcher(
        tmp_path,
        fixture_name,
        command_boundaries=command_boundaries,
    )


def test_wcc_defunctionalizer_does_not_import_legacy_surface_dispatcher() -> None:
    source = Path(wcc_defunctionalize.__file__).read_text(encoding="utf-8")

    assert "_control_lower_expression_impl" not in source
    assert "perform_kind == \"frontend_effect\"" not in source


def test_wcc_supported_effects_lower_from_typed_wcc_operands_not_frontend_expression_bridges() -> None:
    source = Path(wcc_defunctionalize.__file__).read_text(encoding="utf-8")
    forbidden = [
        "command_result_frontend",
        "RunProviderPhaseExpr",
        "ProduceOneOfExpr",
        "ResumeOrStartExpr",
        "isinstance(expr, CommandResultExpr)",
    ]

    assert [token for token in forbidden if token in source] == []


def test_wcc_default_uses_wcc_defunctionalizer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_wcc_path(*_args, **_kwargs):
        raise RuntimeError("wcc defunctionalizer reached")

    monkeypatch.setattr(wcc_defunctionalize, "_lower_wcc_workflow_definitions", _raise_wcc_path)

    with pytest.raises(RuntimeError, match="wcc defunctionalizer reached"):
        compile_stage3_module(
            FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
            provider_externs=_m5_provider_externs(),
            prompt_externs=_m5_prompt_externs(),
            command_boundaries=_m5_command_boundaries(),
            validate_shared=True,
            workspace_root=tmp_path,
        )


def _allocation_identities_for_full_fixture(workspace_root: Path, source_path: Path | None = None) -> list[str]:
    result = compile_stage3_module(
        source_path or FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
        provider_externs=_m5_provider_externs(),
        prompt_externs=_m5_prompt_externs(),
        command_boundaries=_m5_command_boundaries(),
        validate_shared=True,
        workspace_root=workspace_root,
    )
    return [
        allocation.stable_identity
        for lowered in result.lowered_workflows
        for allocation in lowered.generated_path_allocations
    ]


def test_variant_scoped_identity_for_wcc_generated_allocations_is_schema_and_branch_scoped(
    tmp_path: Path,
) -> None:
    stable_identities = _allocation_identities_for_full_fixture(tmp_path)

    assert stable_identities
    assert len(stable_identities) == len(set(stable_identities))
    assert any("schema:2" in identity for identity in stable_identities)
    assert any("match_attempt" in identity or "review" in identity for identity in stable_identities)


def test_variant_scoped_identity_is_stable_across_formatting_only_changes(tmp_path: Path) -> None:
    source = FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc"
    reformatted = tmp_path / "wcc_m4_implementation_phase_full_fixture.orc"
    reformatted.write_text(
        source.read_text(encoding="utf-8").replace("(defrecord RunCtx", "\n\n  (defrecord RunCtx"),
        encoding="utf-8",
    )

    def normalize_specialization_hashes(values: list[str]) -> list[str]:
        return [
            re.sub(
                r"%parametric_call\.std\.phase\.review_revise_loop_proc\.[0-9a-f]+\.[0-9a-f]+",
                "%parametric_call.std.phase.review_revise_loop_proc.<hash>",
                value,
            )
            for value in values
        ]

    assert normalize_specialization_hashes(_allocation_identities_for_full_fixture(tmp_path / "original")) == normalize_specialization_hashes(_allocation_identities_for_full_fixture(
        tmp_path / "formatted",
        source_path=reformatted,
    ))


def test_command_boundary_metadata_survives_wcc_default_full_fixture(tmp_path: Path) -> None:
    result = compile_stage3_module(
        FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc",
        provider_externs=_m5_provider_externs(),
        prompt_externs=_m5_prompt_externs(),
        command_boundaries=_m5_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    payload = json.dumps(
        [lowered.authored_mapping for lowered in result.lowered_workflows],
        sort_keys=True,
    )

    assert "run_checks" in payload
    assert "validate_review_findings_v1" in payload
    assert "lowering_route" not in payload


def test_implementation_phase_full_fixture_behavior_smokes_under_default_wcc_route(tmp_path: Path) -> None:
    case = {
        case.case_id: case
        for case in load_characterization_cases()
    }["wcc_m4_implementation_phase_full_fixture"]
    actual = build_behavior_observation(case, tmp_path, lowering_route=None)
    payload = json.dumps(actual, sort_keys=True)

    assert actual["status"] == "completed"
    assert actual["state"]["context"]["workflow_lisp"]["lowering_schema_version"] == 2
    assert "lowering_route" not in payload
