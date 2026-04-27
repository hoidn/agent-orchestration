import json
from pathlib import Path

from workflows.library.scripts.major_project_escalation_state import (
    INACTIVE_UPSTREAM_CONTEXT,
    activate_upstream,
    clear_upstream,
    init_upstream,
    reset_ledger_on_design_approval,
    terminal_cleanup,
    write_implementation_iteration_context,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _archive_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_init_upstream_writes_inactive_context_and_archive(tmp_path: Path):
    item_root = tmp_path / "state/item"

    payload = init_upstream(item_state_root=item_root, output_bundle=item_root / "bundle.json")

    assert _read_json(item_root / "upstream_escalation_context.json") == INACTIVE_UPSTREAM_CONTEXT
    assert (item_root / "upstream_escalation_context_archive.jsonl").is_file()
    assert _read_json(item_root / "bundle.json") == payload


def test_activate_upstream_archives_previous_active_context(tmp_path: Path):
    item_root = tmp_path / "state/item"
    init_upstream(item_state_root=item_root)
    first = {
        "active": True,
        "source_phase": "implementation",
        "decision": "ESCALATE_REPLAN",
        "recommended_next_phase": "plan",
        "reason_summary": "first",
        "must_change": ["plan"],
        "evidence_paths": {},
    }
    second = {**first, "decision": "ESCALATE_REDESIGN", "reason_summary": "second"}
    source = tmp_path / "source.json"
    source.write_text(json.dumps(first), encoding="utf-8")
    activate_upstream(item_state_root=item_root, source_context_path=source)
    source.write_text(json.dumps(second), encoding="utf-8")

    activate_upstream(item_state_root=item_root, source_context_path=source)

    assert _read_json(item_root / "upstream_escalation_context.json")["decision"] == "ESCALATE_REDESIGN"
    rows = _archive_rows(item_root / "upstream_escalation_context_archive.jsonl")
    assert rows[-1]["resolution"] == "replaced_by_new_escalation"
    assert rows[-1]["payload"]["decision"] == "ESCALATE_REPLAN"


def test_write_iteration_context_tracks_threshold_and_preserves_count(tmp_path: Path):
    state_root = tmp_path / "state/item/implementation-phase"

    first = write_implementation_iteration_context(
        implementation_phase_state_root=state_root,
        phase_iteration_index=0,
        soft_threshold=2,
        max_phase_iterations=40,
    )
    second = write_implementation_iteration_context(
        implementation_phase_state_root=state_root,
        phase_iteration_index=1,
        soft_threshold=2,
        max_phase_iterations=40,
    )

    assert first["cumulative_review_iterations_since_design_approval"] == 1
    assert first["threshold_crossed"] is False
    assert second["cumulative_review_iterations_since_design_approval"] == 2
    assert second["threshold_crossed"] is True
    assert _read_json(state_root / "implementation_iteration_ledger.json") == {
        "design_epoch": 1,
        "cumulative_review_iterations_since_design_approval": 2,
    }


def test_reset_ledger_archives_and_increments_design_epoch(tmp_path: Path):
    state_root = tmp_path / "state/item/implementation-phase"
    write_implementation_iteration_context(
        implementation_phase_state_root=state_root,
        phase_iteration_index=0,
        soft_threshold=10,
        max_phase_iterations=40,
    )

    reset_ledger_on_design_approval(implementation_phase_state_root=state_root)

    assert _read_json(state_root / "implementation_iteration_ledger.json") == {
        "design_epoch": 2,
        "cumulative_review_iterations_since_design_approval": 0,
    }
    rows = _archive_rows(state_root / "implementation_iteration_ledger_archive.jsonl")
    assert rows[-1]["resolution"] == "reset_on_design_approval"
    assert rows[-1]["payload"]["cumulative_review_iterations_since_design_approval"] == 1


def test_clear_and_terminal_cleanup_archive_active_state(tmp_path: Path):
    item_root = tmp_path / "state/item"
    implementation_root = item_root / "implementation-phase"
    init_upstream(item_state_root=item_root)
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "active": True,
                "source_phase": "plan",
                "decision": "ESCALATE_REDESIGN",
                "recommended_next_phase": "design",
                "reason_summary": "needs design",
                "must_change": ["design"],
                "evidence_paths": {},
            }
        ),
        encoding="utf-8",
    )
    activate_upstream(item_state_root=item_root, source_context_path=source)
    clear_upstream(item_state_root=item_root, resolution="consumed_by_redesign")
    write_implementation_iteration_context(
        implementation_phase_state_root=implementation_root,
        phase_iteration_index=0,
        soft_threshold=10,
        max_phase_iterations=40,
    )

    terminal_cleanup(
        item_state_root=item_root,
        implementation_phase_state_root=implementation_root,
        resolution="tranche_completed",
    )

    assert _read_json(item_root / "upstream_escalation_context.json") == INACTIVE_UPSTREAM_CONTEXT
    context_rows = _archive_rows(item_root / "upstream_escalation_context_archive.jsonl")
    assert context_rows[0]["resolution"] == "consumed_by_redesign"
    ledger_rows = _archive_rows(implementation_root / "implementation_iteration_ledger_archive.jsonl")
    assert ledger_rows[-1]["resolution"] == "tranche_completed"
