from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile, compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
from tests.test_workflow_lisp_stdlib_form_migration import DRAIN_STDLIB_FIXTURE, _command_boundary_environment


ENTRY_WORKFLOW_NAME = "drain_stdlib_backlog_drain_stdlib::drain"
EXPECTED_PLACEHOLDER_BOUNDARIES = frozenset(
    {"select_next_item", "draft_gap_item", "execute_selected_item", "apply_resource_transition"}
)


def _compile_linked_fixture(
    path: Path,
    *,
    tmp_path: Path,
    **compile_kwargs: object,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundary_environment().bindings_by_name,
        workspace_root=tmp_path,
        **compile_kwargs,
    )


_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))"""
_LOW_LEVEL_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (state-root Path.state-root)
     (max-iterations Int))"""


def _compile_low_level_boundary_variant(*, tmp_path: Path, **compile_kwargs: object):
    source = DRAIN_STDLIB_FIXTURE.read_text(encoding="utf-8")
    assert source.count(_ENTRY_PARAMS) == 1
    variant_source = source.replace(_ENTRY_PARAMS, _LOW_LEVEL_ENTRY_PARAMS, 1)
    variant_path = tmp_path / "low_level_boundary_variant.orc"
    variant_path.write_text(variant_source, encoding="utf-8")
    return _compile_linked_fixture(
        variant_path,
        tmp_path=tmp_path,
        **compile_kwargs,
    )






_DRAIN_REPEAT_OUTPUTS = {
    "status",
    "state__items-processed",
    "state__progress-report-path",
    "result__variant",
    "result__items_processed",
    "result__progress_report_path",
    "result__blocker_class",
}














def _assert_low_level_boundary_diagnostic(
    diagnostic,
    *,
    expected_severity: str,
) -> None:
    assert diagnostic.code == "low_level_state_path_in_high_level_module"
    assert diagnostic.severity == expected_severity
    assert diagnostic.validation_pass == "contract"
    assert diagnostic.authority_layer == "frontend"
    assert diagnostic.form_path[-2:] == ("defworkflow", "drain")
    assert diagnostic.span is not None
    assert Path(diagnostic.span.start.path).as_posix().endswith(
        "/drain_stdlib_backlog_drain_stdlib.orc"
    )












def test_runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )


    assert result.entry_result.retained_non_promotable_diagnostics == ()




def test_dedicated_runtime_proof_default_lint_retains_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    result = _compile_low_level_boundary_variant(
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    findings = [
        item
        for item in result.entry_result.retained_non_promotable_diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0], expected_severity="warn")


def test_shared_callable_default_lint_retains_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    result = _compile_low_level_boundary_variant(
        tmp_path=tmp_path,
        validate_shared=True,
    )
    findings = [
        item
        for item in result.entry_result.retained_non_promotable_diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0], expected_severity="warn")


def test_shared_callable_strict_lint_rejects_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_low_level_boundary_variant(
            tmp_path=tmp_path,
            validate_shared=True,
            lint_profile=LINT_PROFILE_STRICT,
        )
    findings = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    assert excinfo.value.diagnostics == tuple(findings)
    _assert_low_level_boundary_diagnostic(findings[0], expected_severity="error")


def test_dedicated_runtime_proof_strict_lint_rejects_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_low_level_boundary_variant(
            tmp_path=tmp_path,
            validation_profile="DEDICATED_RUNTIME_PROOF",
            lint_profile=LINT_PROFILE_STRICT,
        )
    findings = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    assert excinfo.value.diagnostics == tuple(findings)
    _assert_low_level_boundary_diagnostic(findings[0], expected_severity="error")












def test_validation_profile_accepts_serialized_enum_value(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="dedicated_runtime_proof",
    )

    assert result.entry_result.validation_profile is Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF
