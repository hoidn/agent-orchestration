# YAML Workflow Estate Triage (DRAFT)

Generated 2026-07-07 for the user-facing YAML retirement sweep.
Classification column is a DRAFT heuristic — review before acting.
Machine-readable migration state should graduate into the route-readiness registry pattern.

| path | last commit | yaml importers | .orc twin | run/docs evidence | draft class |
|---|---|---|---|---|---|
| workflows/examples/adjudicated_provider_demo.yaml | 2026-04-19 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/assert_gate_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/backlog_plan_execute_v0.yaml | 2026-02-25 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml | 2026-02-26 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml | 2026-02-26 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml | 2026-03-10 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/bad_processed.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/call_subworkflow_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/claude_basic.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/claude_with_model.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/cli_test.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/conditional_demo.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/cycle_guard_demo.yaml | 2026-03-08 | 0 | yes | no | example — port one exemplar or archive |
| workflows/examples/depends_on_inject_imported_v2_call.yaml | 2026-03-10 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/design_plan_impl_review_stack_v2_call.yaml | 2026-03-10 | 0 | yes | no | example — port one exemplar or archive |
| workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml | 2026-03-08 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml | 2026-03-10 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml | 2026-03-10 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/dsl_review_first_fix_loop.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/dsl_review_first_fix_loop_provider_session.yaml | 2026-03-09 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/dsl_tracked_plan_review_loop.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/env_literal.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/finally_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/for_each_demo.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/generic_run_watchdog.yaml | 2026-06-15 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/generic_task_plan_execute_review_loop.yaml | 2026-03-06 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/injection_demo.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/library/repeat_until_review_loop.yaml | 2026-03-10 | 1 | no | no | library — retires with its importing family |
| workflows/examples/lisp_frontend_autonomous_drain.yaml | 2026-07-01 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/lisp_frontend_design_delta_drain.yaml | 2026-07-06 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml | 2026-05-28 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml | 2026-04-28 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml | 2026-04-28 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml | 2026-04-27 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/major_project_tranche_drain_stack_v2_call.yaml | 2026-04-27 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/managed_provider_jobs_demo.yaml | 2026-05-04 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/match_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml | 2026-04-22 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/neurips_steered_backlog_drain.legacy.yaml | 2026-06-17 | 0 | no | no | delete |
| workflows/examples/neurips_steered_backlog_drain.yaml | 2026-07-01 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/non_progress_step_back_demo.yaml | 2026-07-01 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/observability_runtime_config_demo.yaml | 2026-02-27 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/output_capture_demo.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/prompt_audit_demo.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml | 2026-03-03 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/ralph_lisp_forever.yaml | 2026-05-19 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/repeat_until_demo.yaml | 2026-03-08 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/repeat_until_exhaustion_escalation_demo.yaml | 2026-04-27 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/retry_demo.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/revision_study_priority_design_plan_impl_stack_v2_call.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/scalar_bookkeeping_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/score_gate_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/structured_if_else_demo.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/test_fix_loop_v0.yaml | 2026-02-19 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/typed_predicate_routing.yaml | 2026-03-07 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml | 2026-03-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/unit_of_work_plus_test_fix_v0.yaml | 2026-02-19 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/verified_iteration_drain.yaml | 2026-07-02 | 0 | no | yes | production — needs .orc port + promotion evidence |
| workflows/examples/wait_for_example.yaml | 2025-09-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/examples/workflow_signature_demo.yaml | 2026-03-10 | 0 | no | no | example — port one exemplar or archive |
| workflows/library/backlog_item_design_plan_impl_stack.yaml | 2026-03-10 | 2 | no | no | library — retires with its importing family |
| workflows/library/depends_on_inject_imported_review.yaml | 2026-03-10 | 1 | no | no | library — retires with its importing family |
| workflows/library/design_plan_impl_implementation_phase.yaml | 2026-04-13 | 5 | yes | no | library — retires with its importing family |
| workflows/library/follow_on_implementation_phase.yaml | 2026-03-10 | 1 | no | no | library — retires with its importing family |
| workflows/library/follow_on_plan_phase.yaml | 2026-03-10 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml | 2026-07-01 | 2 | no | no | library — retires with its importing family |
| workflows/library/lisp_frontend_design_delta_done_review.v214.yaml | 2026-07-07 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml | 2026-07-07 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_delta_selector.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_delta_work_item.v214.yaml | 2026-07-07 | 2 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_design_gap_architect.v214.yaml | 2026-06-28 | 1 | no | no | library — retires with its importing family |
| workflows/library/lisp_frontend_implementation_phase.v214.yaml | 2026-07-07 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_plan_phase.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/lisp_frontend_selector.v214.yaml | 2026-07-01 | 1 | no | no | library — retires with its importing family |
| workflows/library/lisp_frontend_work_item.v214.yaml | 2026-07-07 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/major_project_roadmap_phase.yaml | 2026-05-06 | 2 | no | no | library — retires with its importing family |
| workflows/library/major_project_roadmap_revision_phase.yaml | 2026-04-27 | 1 | no | no | library — retires with its importing family |
| workflows/library/major_project_tranche_design_plan_impl_stack.yaml | 2026-04-28 | 3 | no | no | library — retires with its importing family |
| workflows/library/major_project_tranche_drain_iteration.yaml | 2026-04-28 | 2 | no | no | library — retires with its importing family |
| workflows/library/major_project_tranche_implementation_phase.yaml | 2026-04-28 | 1 | no | no | library — retires with its importing family |
| workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml | 2026-04-28 | 1 | no | no | library — retires with its importing family |
| workflows/library/major_project_tranche_plan_phase.yaml | 2026-04-28 | 1 | no | no | library — retires with its importing family |
| workflows/library/neurips_backlog_gap_drafter.v214.yaml | 2026-05-19 | 1 | no | no | library — retires with its importing family |
| workflows/library/neurips_backlog_gap_drafter.yaml | 2026-05-04 | 1 | no | no | library — retires with its importing family |
| workflows/library/neurips_backlog_implementation_phase.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_implementation_phase.yaml | 2026-06-15 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_roadmap_sync.v214.yaml | 2026-05-09 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_roadmap_sync_phase.yaml | 2026-04-29 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_seeded_plan_phase.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_backlog_selector.v214.yaml | 2026-05-19 | 1 | no | no | library — retires with its importing family |
| workflows/library/neurips_backlog_selector.yaml | 2026-04-29 | 1 | no | no | library — retires with its importing family |
| workflows/library/neurips_selected_backlog_item.v214.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/neurips_selected_backlog_item.yaml | 2026-07-01 | 1 | no | yes | production — needs .orc port + promotion evidence |
| workflows/library/review_fix_loop.yaml | 2026-03-10 | 1 | no | no | library — retires with its importing family |
| workflows/library/revision_study_design_phase.yaml | 2026-04-12 | 1 | no | no | library — retires with its importing family |
| workflows/library/revision_study_design_plan_impl_monolith.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/library/revision_study_design_plan_impl_stack.yaml | 2026-04-12 | 0 | no | no | example — port one exemplar or archive |
| workflows/library/revision_study_implementation_phase.yaml | 2026-04-12 | 1 | no | no | library — retires with its importing family |
| workflows/library/revision_study_plan_phase.yaml | 2026-04-12 | 1 | no | no | library — retires with its importing family |
| workflows/library/revision_study_priority_design_plan_impl_stack.yaml | 2026-04-12 | 1 | no | no | library — retires with its importing family |
| workflows/library/roadmap_seeded_plan_phase.yaml | 2026-04-22 | 1 | no | no | library — retires with its importing family |
| workflows/library/roadmap_tranche_selector.yaml | 2026-04-22 | 1 | no | no | library — retires with its importing family |
| workflows/library/seeded_design_plan_impl_stack.yaml | 2026-04-22 | 0 | no | no | example — port one exemplar or archive |
| workflows/library/tracked_big_design_phase.yaml | 2026-04-27 | 1 | no | no | library — retires with its importing family |
| workflows/library/tracked_design_phase.yaml | 2026-04-13 | 2 | yes | no | library — retires with its importing family |
| workflows/library/tracked_plan_phase.yaml | 2026-04-13 | 2 | yes | no | library — retires with its importing family |
| workflows/templates/autonomous_drain_with_work_instructions.v214.yaml | 2026-05-22 | 0 | no | no | example — port one exemplar or archive |

## Draft class counts

- delete: 1
- example — port one exemplar or archive: 51
- library — retires with its importing family: 29
- production — needs .orc port + promotion evidence: 28
