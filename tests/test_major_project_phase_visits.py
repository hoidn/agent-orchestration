import json
from pathlib import Path

from workflows.library.scripts.major_project_phase_visits import (
    allocate_phase_visit,
    init_phase_visits,
    prepare_phase_visit,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_allocate_initial_plan_visit_writes_ledger_and_bundle(tmp_path: Path):
    item_root = tmp_path / "state/item"
    phase_base = item_root / "plan-phase"
    bundle_path = item_root / "plan_visit.json"

    payload = allocate_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        allocation_key="initial-plan",
        reason="initial_plan",
        output_bundle=bundle_path,
    )

    ledger = _read_json(item_root / "phase_visit_ledger.json")
    assert payload["phase_state_root"] == (phase_base / "visits/0000").as_posix()
    assert payload["phase_visit_ledger_path"] == (item_root / "phase_visit_ledger.json").as_posix()
    assert ledger["current"]["plan"]["state_root"] == payload["phase_state_root"]
    assert ledger["current"]["plan"]["visit_index"] == 0
    assert _read_json(bundle_path) == payload


def test_allocate_reentry_visit_uses_next_index(tmp_path: Path):
    item_root = tmp_path / "state/item"
    phase_base = item_root / "plan-phase"

    first = allocate_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        allocation_key="initial-plan",
        reason="initial_plan",
    )
    second = allocate_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        allocation_key="implementation-escalate-replan-1",
        reason="implementation_escalate_replan",
    )

    ledger = _read_json(item_root / "phase_visit_ledger.json")
    plan_visits = [visit for visit in ledger["visits"] if visit["phase"] == "plan"]
    assert first["phase_state_root"] == (phase_base / "visits/0000").as_posix()
    assert second["phase_state_root"] == (phase_base / "visits/0001").as_posix()
    assert second["phase_state_root"] != phase_base.as_posix()
    assert [visit["visit_index"] for visit in plan_visits] == [0, 1]


def test_allocate_same_key_is_idempotent_for_resume(tmp_path: Path):
    item_root = tmp_path / "state/item"
    phase_base = item_root / "implementation-phase"

    first = allocate_phase_visit(
        item_state_root=item_root,
        phase="implementation",
        phase_state_root_base=phase_base,
        allocation_key="after-plan-0-implementation",
        reason="after_plan_approval",
    )
    second = allocate_phase_visit(
        item_state_root=item_root,
        phase="implementation",
        phase_state_root_base=phase_base,
        allocation_key="after-plan-0-implementation",
        reason="after_plan_approval",
    )

    ledger = _read_json(item_root / "phase_visit_ledger.json")
    implementation_visits = [visit for visit in ledger["visits"] if visit["phase"] == "implementation"]
    assert second == first
    assert len(implementation_visits) == 1


def test_allocate_same_key_with_changed_payload_fails(tmp_path: Path):
    item_root = tmp_path / "state/item"
    allocate_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=item_root / "plan-phase",
        allocation_key="shared-key",
        reason="initial_plan",
    )

    try:
        allocate_phase_visit(
            item_state_root=item_root,
            phase="plan",
            phase_state_root_base=item_root / "alternate-plan-phase",
            allocation_key="shared-key",
            reason="initial_plan",
        )
    except ValueError as exc:
        assert "Conflicting phase visit allocation" in str(exc)
    else:
        raise AssertionError("same allocation key with changed base root should fail")


def test_init_phase_visits_preserves_existing_ledger(tmp_path: Path):
    item_root = tmp_path / "state/item"
    init_phase_visits(item_state_root=item_root)
    allocate_phase_visit(
        item_state_root=item_root,
        phase="big_design",
        phase_state_root_base=item_root / "big-design-phase",
        allocation_key="initial-big-design",
        reason="initial_big_design",
    )

    init_phase_visits(item_state_root=item_root)

    ledger = _read_json(item_root / "phase_visit_ledger.json")
    assert len(ledger["visits"]) == 1
    assert ledger["schema"] == "major_project_phase_visits.v1"


def test_prepare_phase_visit_reuses_pending_current_visit(tmp_path: Path):
    item_root = tmp_path / "state/item"
    phase_base = item_root / "plan-phase"

    first = prepare_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        reason="plan_visit",
    )
    second = prepare_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        reason="plan_visit",
    )

    ledger = _read_json(item_root / "phase_visit_ledger.json")
    assert second == first
    assert len([visit for visit in ledger["visits"] if visit["phase"] == "plan"]) == 1


def test_prepare_phase_visit_allocates_next_after_final_decision(tmp_path: Path):
    item_root = tmp_path / "state/item"
    phase_base = item_root / "plan-phase"

    first = prepare_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        reason="plan_visit",
    )
    (Path(first["phase_state_root"]) / "final_plan_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")

    second = prepare_phase_visit(
        item_state_root=item_root,
        phase="plan",
        phase_state_root_base=phase_base,
        reason="plan_visit",
    )

    assert second["phase_state_root"] == (phase_base / "visits/0001").as_posix()
    assert (item_root / "current_plan_phase_state_root.txt").read_text(encoding="utf-8").strip() == second[
        "phase_state_root"
    ]
