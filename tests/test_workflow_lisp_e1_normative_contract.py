"""Target-2.24 E1 normative admission and spec-routing contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_ROOT = REPO_ROOT / "specs"


def _ordinary_source(target: str) -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule e1_target_contract)
  (export Result)
  (defrecord Result
    (status String)))
"""


def _compile(tmp_path: Path, target: str):
    source = tmp_path / "e1_target_contract.orc"
    source.write_text(_ordinary_source(target), encoding="utf-8")
    return compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
    )


def test_ordinary_target_2_24_library_module_compiles_through_the_full_frontend(
    tmp_path: Path,
) -> None:
    result = _compile(tmp_path, "2.24")

    assert result.entry_result.module.target_dsl_version == "2.24"
    assert result.entry_result.lowered_workflows == ()
    assert result.validated_bundles_by_name == {}


def test_target_2_25_remains_fail_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, "2.25")

    assert caught.value.diagnostics[0].code == "target_dsl_unsupported"


def test_normative_specs_route_the_target_2_24_run_ref_contract() -> None:
    dsl = (SPECS_ROOT / "dsl.md").read_text(encoding="utf-8")
    state = (SPECS_ROOT / "state.md").read_text(encoding="utf-8")
    versioning = (SPECS_ROOT / "versioning.md").read_text(encoding="utf-8")
    index = (SPECS_ROOT / "index.md").read_text(encoding="utf-8")

    target_section = re.search(
        r"(?m)^\s*- [^\n]*target 2\.24[^\n]*:$",
        dsl,
    )
    assert target_section is not None
    next_section = dsl.index(
        "\n  - Workflow Lisp WCC child-call argument projection:",
        target_section.start(),
    )
    dsl_2_24 = dsl[target_section.start() : next_section]
    assert "`run-ref`" in dsl_2_24
    assert "RepositoryRevisionId" in dsl_2_24
    assert "RunRefResult" in dsl_2_24
    for authored_marker in (
        ":bundle",
        ":path",
        ":returns",
        ":environment :deterministic-effect-free",
        "run_ref_bundle_capsule.v1",
        "workflow_lisp_compile_diagnostics.v1",
    ):
        assert authored_marker in dsl_2_24
    for diagnostic_code in (
        "trial_source_unresolvable",
        "trial_source_submodules_unsupported",
        "trial_source_lfs_unsupported",
        "trial_source_revision_digest_mismatch",
        "trial_materialization_digest_mismatch",
        "trial_workspace_preexisting",
        "trial_setup_failed",
        "trial_program_missing",
        "trial_program_compile_rejected",
        "trial_program_signature_mismatch",
        "trial_candidate_environment_not_admissible",
        "run_ref_ledger_invalid",
        "run_ref_capsule_invalid",
        "run_ref_child_launch_failed",
        "run_ref_child_result_invalid",
        "run_ref_delta_capture_failed",
        "run_ref_workspace_discard_failed",
    ):
        assert f"`{diagnostic_code}`" in dsl_2_24

    assert "run_ref_attempt_ledger.v1" in state
    assert "completed_pending_parent_commit" in state
    assert "StepResult.run_ref" in state
    assert "reuse_validated_run_ref_result" in state
    assert re.search(r'(?m)^\s*- `schema_version: "2\.1"`$', state)
    assert 'schema_version: "2.2"' not in state

    assert re.search(r"(?m)^\| 2\.24 \|[^\n]*`run-ref`", versioning)
    assert re.search(r"(?m)^# .*v1\.1 through v2\.24", index)
    assert "`run-ref`" in index
