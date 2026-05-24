# Stage 7 Migration Experiment Recommendation Report

## Scope

This report covers the bounded Stage 7 Workflow Lisp frontend slice for:

- `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`
- `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`
- `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`

The YAML baselines are:

- `workflows/library/neurips_selected_backlog_item.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/examples/neurips_steered_backlog_drain.legacy.yaml`

## Metrics

| Metric | YAML baseline | `.orc` slice | Result |
| --- | ---: | ---: | --- |
| Authored lines | 3170 | 465 | Pass |
| Semantic outer workflow lines | n/a | 59 | Measured |
| Manual state-path occurrences | 150 | 0 | Pass |
| Pointer-file occurrences | 140 | 0 | Pass |
| Pointer/materialization surface | 48 | 0 | Pass |
| Candidate-path occurrences | 0 | 0 | Flat |
| Manual variant boilerplate | 28 | 0 | Pass |
| Markdown/text extractors | 32 | 0 | Pass |
| Shell/Python glue surfaces | 90 | 7 | Pass |
| String status/gate patterns | 118 | 3 | Pass |
| Remaining imported YAML dependencies | 12 | 4 | Pass |
| Behavioral equivalence suite | n/a | PASS | PASS |

## Evidence Notes

- Behavioral equivalence status: `PASS`.
- Behavioral evidence commands:
  - `python -m pytest tests/test_workflow_lisp_stage7_translation.py -k neurips_plan_gate_resume or neurips_selected_item or neurips_remaining_drain or run_item_boundary -q` -> exit `0`; `8 passed in 0.27s`
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k resume_or_start or union_start_workflow_call -q` -> exit `0`; `12 passed, 34 deselected in 0.25s`
  - `python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k finalize_selected_item -q` -> exit `0`; `5 passed, 15 deselected in 0.20s`
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k backlog_drain or run_item_contract or providers_rebinding -q` -> exit `0`; `3 passed, 10 deselected in 0.20s`
  - `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k selected_item_fresh_plan or selected_item_reuses_approved_plan -q` -> exit `0`; `2 passed, 15 deselected in 2.09s`
  - `python -m pytest tests/test_neurips_steered_backlog_runtime.py -k drain_continues_to_next_iteration or drain_gap_draft or drain_blocked -q` -> exit `0`; `3 passed, 6 deselected in 3.77s`
- Remaining imported YAML migration debt:
  - `roadmap-sync` -> `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`. Stage 7 selected-item still relies on the YAML roadmap-sync phase surface.
  - `implementation-phase` -> `workflows/library/neurips_backlog_implementation_phase.v214.yaml`. Stage 7 reuses the YAML implementation-phase wrapper around the translated implementation-attempt core.
  - `selector` -> `workflows/library/neurips_backlog_selector.v214.yaml`. Stage 7 top-level drain still depends on the YAML selector role target.
  - `gap-drafter` -> `workflows/library/neurips_backlog_gap_drafter.v214.yaml`. Stage 7 top-level drain still depends on the YAML gap-drafter role target.

## Recommendation

`revise`
