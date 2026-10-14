import json
from pathlib import Path

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = ROOT / "tests/fixtures/workflow_lisp/verified_drain_legacy"
ORC_WORKFLOW = LEGACY_ROOT / "verified_iteration_drain/drain.orc"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY_WORKFLOW = "verified_iteration_drain/drain::drain"
PREPARE_SCRIPT = "workflows/library/scripts/prepare_verified_iteration.py"
RECORD_SCRIPT = "workflows/library/scripts/record_verified_iteration.py"
HISTORY_ROOT = "artifacts/work/verified/ledger-inputs"
EXTERNAL_LEDGER_EDIT = b"EXTERNAL_LEDGER_EDIT\n"


def _compile_verified_orc():
    assert ORC_WORKFLOW.is_file(), f"verified Workflow Lisp candidate is absent: {ORC_WORKFLOW}"
    return compile_stage3_entrypoint(
        ORC_WORKFLOW,
        source_roots=(LEGACY_ROOT,),
        entry_workflow=ENTRY_WORKFLOW,
        provider_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.providers.json").read_text()
        ),
        prompt_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.prompts.json").read_text()
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(
                (MIGRATION_INPUTS / "verified_iteration_drain.commands.json").read_text()
            ),
            manifest_path=MIGRATION_INPUTS / "verified_iteration_drain.commands.json",
        ),
        workspace_root=ROOT,
        lowering_route="wcc_m4",
    )






























def test_verified_orc_compiles_with_exact_public_contract() -> None:
    result = _compile_verified_orc()

    assert result.entry_result.module.target_dsl_version == "2.15"














def test_verified_extern_manifests_bind_existing_assets() -> None:
    providers = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.providers.json").read_text())
    prompts = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.prompts.json").read_text())
    commands = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.commands.json").read_text())

    assert providers == {
        "providers.worker.codex": "codex_unrestricted_workspace",
        "providers.worker.claude": "claude_unrestricted_workspace",
        "providers.reviewer.codex": "codex_unrestricted_workspace",
        "providers.reviewer.claude": "claude_unrestricted_workspace",
    }
    assert prompts == {
        "prompts.verified-iteration.work": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/work.md"
        },
        "prompts.verified-iteration.review-iteration": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/review_iteration.md"
        },
        "prompts.verified-iteration.review-done": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/review_done.md"
        },
    }
    assert commands == {
        "prepare_verified_iteration": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/prepare_verified_iteration.py"],
            "closure": ["workflows/library/scripts/prepare_verified_iteration.py"],
        },
        "run_verified_iteration_checks": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/run_verified_iteration_checks.py"],
            "closure": ["workflows/library/scripts/run_verified_iteration_checks.py"],
        },
        "record_verified_iteration": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/record_verified_iteration.py"],
            "closure": ["workflows/library/scripts/record_verified_iteration.py"],
        },
    }
    for row in [*prompts.values(), *commands.values()]:
        relpath = row.get("input_file") or row["stable_command"][1]
        assert (ROOT / relpath).is_file()










def test_legacy_verified_post_promotion_fixture_preserves_contract(tmp_path: Path) -> None:
    registry = json.loads(
        (ROOT / "docs/workflow_lisp_route_readiness_registry.json").read_text()
    )
    route = next(
        row
        for row in registry["surfaces"]
        if row["path"] == "workflows/library/verified_iteration_drain/drain.orc"
    )
    assert route["surface_kind"] == "library_workflow"
    assert route["route_label"] == "evaluated_execution"
    assert route["readiness_label"] == "promotion_eligible"
    assert route["entry_workflow"] == ENTRY_WORKFLOW
