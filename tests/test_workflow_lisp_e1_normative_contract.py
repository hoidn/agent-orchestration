"""Historical E1 wire contract and current run-ref admission routing."""

from __future__ import annotations

import re
from pathlib import Path


from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_ROOT = REPO_ROOT / "specs"


def _assert_doc_routes(owner: Path, *destinations: Path) -> str:
    document = owner.read_text(encoding="utf-8")
    links = {
        owner.parent.joinpath(href.partition("#")[0]).resolve()
        for href in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document)
        if not href.startswith(("https:", "http:", "#"))
    }
    for destination in destinations:
        assert destination.resolve() in links, (owner, destination)
        assert destination.is_file(), destination
    return document


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


def test_ordinary_current_library_module_compiles_through_the_full_frontend(
    tmp_path: Path,
) -> None:
    result = _compile(tmp_path, "2.35")

    assert result.entry_result.module.target_dsl_version == "2.35"








def test_historical_e1_contract_routes_to_current_run_ref_admission() -> None:
    dsl = (SPECS_ROOT / "dsl.md").read_text(encoding="utf-8")
    state = (SPECS_ROOT / "state.md").read_text(encoding="utf-8")
    versioning = (SPECS_ROOT / "versioning.md").read_text(encoding="utf-8")
    master_path = SPECS_ROOT / "index.md"
    index = _assert_doc_routes(
        master_path,
        SPECS_ROOT / "versioning.md",
        SPECS_ROOT / "cli.md",
    )

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

    historical_scope = state.split("## Execution and historical-format scope", 1)[1].split(
        "\n## Derived Pure-Result Persistence Profile", 1
    )[0]
    assert re.search(r'(?m)^\s*- `schema_version: "2\.1"`$', historical_scope)
    run_ref_state = state.split(
        "## Target 2.24 `run-ref` State, Settlement, And Resume", 1
    )[1].split("\n## ", 1)[0]
    assert "run_ref_attempt_ledger.v1" in run_ref_state
    assert "completed_pending_parent_commit" in run_ref_state
    assert "StepResult.run_ref" in run_ref_state
    assert "reuse_validated_run_ref_result" in run_ref_state
    assert 'schema_version: "2.2"' not in run_ref_state

    evaluated_state = state.split(
        "## Evaluated Execution Persistence Profile (target 2.35)", 1
    )[1].split("\n## Durable Host Input State And Recovery", 1)[0]
    assert '`schema_version: "3.0"`' in evaluated_state
    assert "`memo.jsonl`" in evaluated_state
    assert "the only authority for results" in evaluated_state
    _assert_doc_routes(
        SPECS_ROOT / "state.md",
        SPECS_ROOT / "cli.md",
        REPO_ROOT / "docs/design/workflow_lisp_executor_retirement.md",
    )

    assert re.search(r"(?m)^\| 2\.24 \|[^\n]*`run-ref`", versioning)
    current_scope = index.split("- Version history and current target extensions", 1)[0]
    assert re.search(r"targets\s+2\.35[–-]2\.39", current_scope)

    trial_runs_path = REPO_ROOT / "docs/design/workflow_lisp_trial_runs.md"
    trial_runs = _assert_doc_routes(
        trial_runs_path,
        REPO_ROOT / "docs/design/workflow_lisp_evaluated_execution.md",
        REPO_ROOT / "docs/design/workflow_lisp_executor_retirement.md",
        SPECS_ROOT / "cli.md",
    )
    normalized_trial_runs = " ".join(trial_runs.split())
    assert "Path-mode run references retain their pure-child" in normalized_trial_runs
    assert "bundle/trial effects are excluded" in normalized_trial_runs
