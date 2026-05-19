from orchestrator.workflow_lisp.stage7_metrics import (
    REPORT_PATH,
    measure_stage7_metrics,
    write_stage7_recommendation_report,
)


def test_stage7_metrics_report_is_generated_from_measured_sources() -> None:
    measurement = measure_stage7_metrics(run_behavioral_suite=True)

    assert measurement["metrics"] == {
        "authored_loc": {"baseline": 3170, "orc": 465},
        "semantic_outer_workflow_loc": {"baseline": None, "orc": 59},
        "manual_state_path_count": {"baseline": 150, "orc": 0},
        "pointer_file_count": {"baseline": 140, "orc": 0},
        "pointer_materialization_surface_count": {"baseline": 48, "orc": 0},
        "candidate_path_count": {"baseline": 0, "orc": 0},
        "variant_boilerplate_count": {"baseline": 28, "orc": 0},
        "markdown_text_extractor_count": {"baseline": 32, "orc": 0},
        "glue_command_helper_surface_count": {"baseline": 90, "orc": 7},
        "string_status_gate_pattern_count": {"baseline": 118, "orc": 3},
        "remaining_imported_yaml_dependency_count": {"baseline": 12, "orc": 4},
    }
    assert measurement["remaining_yaml_dependencies"] == [
        {
            "alias": "roadmap-sync",
            "workflow": "workflows/library/neurips_backlog_roadmap_sync.v214.yaml",
            "reason": "Stage 7 selected-item still relies on the YAML roadmap-sync phase surface.",
        },
        {
            "alias": "implementation-phase",
            "workflow": "workflows/library/neurips_backlog_implementation_phase.v214.yaml",
            "reason": "Stage 7 reuses the YAML implementation-phase wrapper around the translated implementation-attempt core.",
        },
        {
            "alias": "selector",
            "workflow": "workflows/library/neurips_backlog_selector.v214.yaml",
            "reason": "Stage 7 top-level drain still depends on the YAML selector role target.",
        },
        {
            "alias": "gap-drafter",
            "workflow": "workflows/library/neurips_backlog_gap_drafter.v214.yaml",
            "reason": "Stage 7 top-level drain still depends on the YAML gap-drafter role target.",
        },
    ]
    assert measurement["behavioral_equivalence"]["status"] == "PASS"
    assert measurement["recommendation"] == "revise"

    report_path = write_stage7_recommendation_report(measurement)

    assert report_path == REPORT_PATH
    report_text = report_path.read_text(encoding="utf-8")
    assert "| Authored lines | 3170 | 465 | Pass |" in report_text
    assert "Remaining imported YAML migration debt" in report_text
    assert "`workflows/library/neurips_backlog_selector.v214.yaml`" in report_text
    assert "| Behavioral equivalence suite | n/a | PASS | PASS |" in report_text
    assert "`revise`" in report_text
