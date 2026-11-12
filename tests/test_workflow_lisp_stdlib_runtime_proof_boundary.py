from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile, compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


# An effectful workflow, so the low-level state-path lint applies to its parameters.
_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule proof_boundary)
  (export drain)
  (defrecord Count (n Int))
  (defworkflow drain
    ({params}(max-iterations Int))
    -> Count
    (command-result count :argv ("python" "count.py" max-iterations) :returns Count)))
"""
_LOW_LEVEL_PARAM = "(state-root Path.state-root)\n     "


def _compile_linked_fixture(*, tmp_path: Path, low_level: bool = False, **compile_kwargs: object):
    module_path = tmp_path / "proof_boundary.orc"
    module_path.write_text(_SOURCE.format(params=_LOW_LEVEL_PARAM if low_level else ""), encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries={"count": ExternalToolBinding(name="count", stable_command=("python", "count.py"))},
        workspace_root=tmp_path,
        **compile_kwargs,
    )


def _compile_low_level_boundary_variant(*, tmp_path: Path, **compile_kwargs: object):
    return _compile_linked_fixture(tmp_path=tmp_path, low_level=True, **compile_kwargs)


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
        "/proof_boundary.orc"
    )












def test_runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
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
        tmp_path=tmp_path,
        validation_profile="dedicated_runtime_proof",
    )

    assert result.entry_result.validation_profile is Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF
