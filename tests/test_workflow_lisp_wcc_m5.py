from __future__ import annotations

from pathlib import Path


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
    assert result.typed_program.producer_lowering_schema == 2


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
    assert result.entry_result.typed_program.producer_lowering_schema == 2


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
    assert result.typed_program.producer_lowering_schema == 2
    assert result.typed_program.producer_lowering_schema == 2


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
    assert result.entry_result.typed_program.producer_lowering_schema == 2
