# Agent Sessions PQ-1a Qualification Record

PQ-1a is the single qualification record for the shared agent-session mechanism and its adapter dispositions
(`docs/design/workflow_lisp_agent_sessions.md`, Architecture, Compatibility And Feasibility). This record holds the
deterministic part, written 2026-10-15 on branch `feat/agent-sessions` (Plan B Task 18), target 2.38.

Scope statement: "deterministic proofs are mechanism proofs, not consumer proofs; no acceptance comparison has run". Every proof below
drives the evaluated runtime with deterministic `codex`/`claude` CLIs (`tests/agent_session_shims.py`) that write each
provider's native-store format. No real provider CLI ran for this record. Neither adapter is advertised as qualified
until the real-provider smokes below are recorded.

## Verification evidence

| Check | Commit | Result |
| --- | --- | --- |
| Broad suite, clean checkout, `pytest -q -n 16 --dist=worksteal` | `c81a290b` | 17 failed / 15895 passed / 6 skipped / 2 xfailed, 708 s |
| Failure attribution | `c81a290b` | 15 are the Plan A pre-existing baseline: 10 in `tests/test_workflow_lisp_use_site_scope.py`, `tests/test_workflow_evaluated_programs.py::test_growth_selectors_take_both_arms_and_counters_change_after_seeds`, 4 nanobragg reference-harness tests. 2 are load flakes in `tests/experiments/test_native_session_cli_probe.py` (slow-overlap and fallback-home parameters) that passed on isolated rerun |
| Regressions | `c81a290b` | None |
| Leaked `orc-observe` tmux sessions after the broad run | `c81a290b` | 0 |
| Cited pinning tests: 89 selectors, `--collect-only` | `3472bef2` | 181 items collected, no missing node id |
| Cited pinning tests run once (`-q -n 8`) | `3472bef2` | 181 passed in 51 s; 0 `orc-observe` sessions after |

`3472bef2` differs from `c81a290b` only by the two opt-in real-smoke modules under `tests/e2e/`, which skip without
`AGENT_SESSION_REAL_SMOKE`.

## Test module key

| Key | Module |
| --- | --- |
| T | `tests/test_agent_session_transport.py` (shim CLIs through the provider executor) |
| NS | `tests/test_provider_native_store.py` (native-store adapters) |
| CL | `tests/test_provider_session_transport_claude.py` |
| SR | `tests/test_workflow_evaluated_provider_session_request.py` |
| ADM | `tests/test_workflow_lisp_agent_turn_admission.py` (frontend admission) |
| AL | `tests/test_workflow_evaluated_agent_allocation.py` |
| CO | `tests/test_workflow_evaluated_agent_composition.py` |
| TU | `tests/test_workflow_evaluated_agent_turns.py` |
| RE | `tests/test_workflow_evaluated_agent_turn_recovery.py` |
| BO | `tests/test_workflow_evaluated_agent_bootstrap.py` |
| IN | `tests/test_workflow_evaluated_agent_invalidate.py` |
| MC | `tests/test_workflow_evaluated_memo_agent_classes.py` (pure reducer) |
| VI | `tests/test_workflow_evaluated_agent_views.py` |
| OB | `tests/test_workflow_evaluated_agent_observation.py` |
| CS | `tests/test_workflow_evaluated_agent_consumer_smoke.py` (public `compile`/`run`/`resume`/`invalidate` on the two-agent `design_review_execute` variant: designer on Claude, reviewer on Codex) |
| CSK | `CS::test_every_kill_point_resumes_to_the_same_value_without_a_turn_running_twice` |

## Failure table

Rows follow the design's Persistence, Recovery And Invalidation table.

| # | Boundary / failure | Pinning tests | Status |
| --- | --- | --- | --- |
| 1 | Allocation committed; no delivery intent: first use starts a fresh session | AL::test_allocations_commit_descriptors_with_no_dispatch_and_replay_readonly; TU::test_clean_run_commits_four_turns_on_two_native_sessions (first turn without `--resume`); CSK[started] | Pinned |
| 2 | Attempt reserved, demonstrably not dispatched: evidence kept, next attempt allowed | RE::test_kill_after_intent_before_launch_allocates_the_next_attempt_on_resume; RE::test_kill_between_started_and_attempt_directory_allocates_the_next_attempt; CSK[intent] | Pinned |
| 3 | Intact intent receipt, unknown locator or outcome: reconcile without resend, then bootstrap (first turn) or `agent_turn_unresolved` | RE::test_uncertain_or_advanced_transport_failure_keeps_started_pending_without_failed_or_terminal; RE::test_later_turn_unresolved_refuses_on_resume_and_preserves_the_pending_start; RE::test_codex_overlap_after_an_interrupted_turn_classifies_unresolved; BO::test_reviewer_first_turn_failure_bootstraps_a_fresh_candidate_on_explicit_resume[interrupted]; BO::test_first_turn_killed_after_launch_is_quiesced_and_abandoned; CS::test_reviewer_first_turn_failure_bootstraps_only_a_fresh_reviewer_on_explicit_resume[codex-0-interrupted]; CS::test_later_turn_failure_refuses_on_resume_without_any_write[claude-1-interrupted-agent_turn_unresolved] | Pinned |
| 4 | Adapter proves no dispatch/advance and unchanged predecessor: resume allocates the next attempt; never inferred from missing stdout or nonzero exit | RE::test_timeout_before_any_append_is_an_ordinary_failure_and_resume_retries; RE::test_resume_proves_a_launched_attempt_not_dispatched_and_allocates_the_next; TU::test_transport_failure_closes_failed_only_when_the_adapter_proves_no_advance; RE::test_not_dispatched_needs_a_proven_empty_group_before_any_head_check; CS::test_proven_undispatched_later_turn_failure_resumes_with_the_next_attempt; nonzero exit with an open head stays unresolved: CS::test_later_turn_failure_refuses_on_resume_without_any_write[codex-1-nonzero-agent_turn_unresolved] | Pinned |
| 5 | Completed native turn, missing/invalid typed result: failure recorded; first turn may bootstrap; later turns refuse `agent_turn_result_invalid` | TU::test_invalid_typed_result_closes_failed_with_the_turn_position_code; TU::test_claude_is_error_result_is_never_committed; BO::test_reviewer_first_turn_failure_bootstraps_a_fresh_candidate_on_explicit_resume[invalid-result]; BO::test_later_turn_failures_cannot_bootstrap[invalid-result-agent_turn_result_invalid]; CS::test_reviewer_first_turn_failure_bootstraps_only_a_fresh_reviewer_on_explicit_resume[codex-0-invalid-result]; CS::test_later_turn_failure_refuses_on_resume_without_any_write[claude-1-invalid-result-agent_turn_result_invalid] | Invalid: pinned. Missing: gap G1 |
| 6 | Native completion and valid result, interrupted before prepared proof: recover from adapter-confirmed exact completion and intact result | RE::test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch[completed]; RE::test_timeout_after_adapter_confirmed_completion_recovers_the_same_ordinal_without_redispatch; RE::test_unmapped_exception_after_launch_is_recovered_on_resume_when_the_native_turn_completed; RE::test_orphaned_process_group_is_quiesced_before_recovery; BO::test_recoverable_first_turn_proof_wins_over_bootstrap; CSK[completed] | Pinned |
| 7 | Prepared proof durable, memo not committed: commit the same pending attempt, no append, no new ordinal | RE::test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch[proof]; TU::test_commit_failure_after_the_prepared_proof_keeps_started_pending; CSK[proof] | Pinned |
| 8 | Memo committed, settlement incomplete: settle from the committed proof, no append, no head comparison | RE::test_kill_after_commit_or_settle_reconciles_without_native_append[committed-/ b1]; IN::test_committed_turns_never_need_their_receipts_on_resume; RE::test_replay_ignores_a_receipt_that_disagrees_with_a_committed_proof; CSK[committed] | Pinned |
| 9 | Committed and settled: reuse even with the native session gone | RE::test_completed_run_resumes_readonly_after_native_stores_disappear; CS::test_completed_consumer_replays_readonly_after_native_sessions_and_receipts_disappear; TU::test_completed_run_replays_without_current_session_support; TU::test_completed_resume_is_readonly_and_dispatches_nothing; RE::test_kill_after_commit_or_settle_reconciles_without_native_append[settled-/ a2]; CSK[settled]; a tampered proof still refuses: RE::test_replay_refuses_a_tampered_committed_proof | Pinned |
| 10 | Before a new turn: session missing / advanced elsewhere / configuration incompatible | `agent_session_unavailable`: CS::test_lost_designer_session_refuses_before_dispatch. `agent_session_diverged`: CS::test_external_advancement_of_the_designer_refuses_before_dispatch (Claude), TU::test_native_head_advanced_elsewhere_refuses_before_started (Codex). `agent_policy_mismatch`: TU::test_policy_mismatch_refuses_before_dispatch, TU::test_config_digest_change_refuses_policy_mismatch, TU::test_template_change_between_run_and_resume_refuses_agent_policy_mismatch. No native facts in state/report: VI::test_d1_refusal_reaches_state_and_report_without_native_facts | Pinned |

Rules stated under the table:

| Rule | Pinning tests | Status |
| --- | --- | --- |
| Quiesce before reconciliation or append; unprovable stop is `agent_turn_unresolved` | RE::test_orphaned_process_group_is_quiesced_before_recovery; RE::test_not_dispatched_needs_a_proven_empty_group_before_any_head_check; RE::test_quiesce_never_signals_a_reused_pgid | Partial: gap G2 |
| Receipt corruption or missing required evidence is `memo_inconsistent`, never a retry | CS::test_corrupt_receipt_of_a_pending_turn_refuses_on_resume_without_any_write; IN::test_unreadable_required_receipt_is_memo_inconsistent; IN::test_resume_refuses_a_pending_receipt_that_disagrees_with_its_started_row; IN::test_resume_refuses_a_bootstrap_restart_without_its_abandoned_marker; AL::test_malformed_receipt_field_is_refused_on_read_and_write | Pinned |
| Unresolved keeps `started` pending, with no `failed`/`terminal` | RE::test_uncertain_or_advanced_transport_failure_keeps_started_pending_without_failed_or_terminal; TU::test_unmapped_exception_after_launch_keeps_started_pending_as_unresolved; TU::test_unmapped_exception_during_projection_keeps_started_pending_with_a_completed_receipt (R4); TU::test_failed_unknown_receipt_write_still_keeps_started_pending; MC::test_terminal_waits_for_the_turn_settlement | Pinned |
| Bootstrap order: quiesce, abandon, `failed agent_bootstrap_restarted`, new `started`; never adopted, never duplicated | BO::test_kill_between_abandonment_failure_and_next_start_keeps_ordering_valid; BO::test_first_turn_killed_after_launch_is_quiesced_and_abandoned; MC::test_bootstrap_restart_closes_the_attempt_before_the_next_ordinal | Pinned; sub-points gap G3 |
| Later turns (A2/B2) never bootstrap | BO::test_later_turn_failures_cannot_bootstrap; CS::test_later_turn_failure_refuses_on_resume_without_any_write | Pinned |
| C8: a suffix with a committed agent turn refuses `invalidate_coordinator_committed` before any write | IN::test_suffix_with_a_committed_turn_refuses_coordinator_committed_without_writes; IN::test_committed_turns_after_a_bootstrap_still_protect_the_suffix; MC::test_invalidation_anchor_before_a_committed_turn_is_refused_on_replay; CS::test_invalidating_feedback_is_refused_after_revised_committed_but_the_baseline_consumer_allows_it | Pinned |
| C8: an advanced/uncertain attempt affected by the cut refuses `invalidate_agent_session_advanced` (allocate A, command X writes a file, turn T advances: invalidating X refuses) | IN::test_upstream_command_feeding_an_advanced_uncommitted_turn_refuses_session_advanced; IN::test_pending_turn_after_a_kill_is_refused_by_preflight_and_the_row_would_not_reduce; IN::test_failed_row_with_a_receipt_past_intent_refuses_cut; MC::test_invalidation_cut_over_a_dispatched_agent_attempt_is_inconsistent | Pinned |
| C8: unused allocations and proven-undispatched attempts follow ordinary C8 | IN::test_unused_allocation_tail_invalidates_and_resume_reallocates; IN::test_failed_before_dispatch_turn_may_be_cut_by_preflight_and_reducer_alike; MC::test_invalidation_cut_over_an_undispatched_agent_failure_is_admitted | Pinned |

## Kill points

CSK asserts, per kill point, a successful public `resume`, the clean-run final value and exactly one dispatch per
turn (`claude, codex, claude, codex`).

| Kill point | Pinning tests | Resume outcome |
| --- | --- | --- |
| After `started`, before attempt directory / intent | CSK[started]; RE::test_kill_between_started_and_attempt_directory_allocates_the_next_attempt | Attempt closes `failed provider_preparation_failed` (R5); next ordinal |
| After intent, before launch | CSK[intent]; RE::test_kill_after_intent_before_launch_allocates_the_next_attempt_on_resume | Receipt `not_dispatched`; next ordinal |
| After launch, before native append | RE::test_resume_proves_a_launched_attempt_not_dispatched_and_allocates_the_next[once], [crash-after-receipt]; BO::test_first_turn_killed_after_launch_is_quiesced_and_abandoned | Group quiesced; later turn: next ordinal; first turn: abandoned, bootstrap |
| During the native turn (orchestrator dies, CLI group survives) | RE::test_orphaned_process_group_is_quiesced_before_recovery | Group stopped under the writer lock; recovered without redispatch |
| After native completion, before prepared proof | CSK[completed]; RE::test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch[completed] | Same ordinal committed, zero redispatch |
| After prepared proof, before memo commit | CSK[proof]; RE::test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch[proof] | Same ordinal committed, zero redispatch |
| After memo commit, before settlement | CSK[committed]; RE::test_kill_after_commit_or_settle_reconciles_without_native_append[committed-/ b1] | Settled by `reconcile`; no append |
| After settlement | CSK[settled]; RE::test_kill_after_commit_or_settle_reconciles_without_native_append[settled-/ a2] | Replay only |
| Bootstrap: after the `abandoned` receipt, before `failed` | BO::test_kill_between_abandonment_failure_and_next_start_keeps_ordering_valid[receipt-env0-0] | One `failed agent_bootstrap_restarted`; attempt 2; old candidate not adopted |
| Bootstrap: after `failed`, before the next `started` | BO::test_kill_between_abandonment_failure_and_next_start_keeps_ordering_valid[record-env1-1] | `failed` not duplicated; attempt 2 |

## Other design verification items

| Item | Pinning tests |
| --- | --- |
| Clean A1/B1/A2/B2: two native identities, four typed results, predecessor lineage, updated result destinations, exactly four requests, read-only resume | CS::test_clean_consumer_run_four_turns_two_sessions_lineage_and_readonly_resume |
| Factory calls, branch aliases, sequential/loop reuse, per-iteration construction | CO::test_factory_agents_are_distinct_and_a_branch_alias_and_loop_reuse_continue_one; CO::test_agent_constructed_in_a_loop_body_is_a_new_agent_per_iteration; CO::test_only_the_selected_branch_allocates_and_invokes_and_the_join_keeps_its_handle |
| Nested aggregate escape and parallel sharing refused before dispatch | ADM::test_agent_cannot_escape_its_run_local_positions; ADM::test_checker_refuses_agent_effect_reached_from_a_parallel_worker |
| Old-turn replay after later commits uses the logical cursor | TU::test_unconsumed_predecessor_is_a_dependency_and_replays_on_the_logical_cursor; CSK[committed] |
| Fresh-session orphan: bootstrap opens a new session, never resumes the abandoned one | CS::test_reviewer_first_turn_failure_bootstraps_only_a_fresh_reviewer_on_explicit_resume |
| Diagnostics, state and report carry logical identities only | VI::test_no_locator_or_position_reaches_state_or_report; VI::test_pending_unresolved_turn_is_running_and_report_succeeds |
| One view per agent; crash/resume; observation never affects execution | OB::test_each_agent_has_one_view_across_its_turns_and_ordinary_calls_keep_one_pane; OB::test_crash_and_resume_opens_new_views_without_redispatch; OB::test_observation_failure_never_changes_execution; OB::test_failed_agent_views_open_no_fallback_panes; OB::test_views_never_enter_memo_state_or_report |

## Adapter dispositions proved deterministically

Adapters: Codex `codex_exec_jsonl_stdout`, Claude `claude_stream_json_stdout`. The shim store formats follow the
native CLI probe (`docs/reports/2026-10-13-native-session-cli-live.md`) and, for the Claude plain stream-json form,
the mini-probe (`docs/reports/2026-10-14-claude-plain-form-mini-probe.md`: completion marker `end_turn`, 3/3 turns
bind after `02a0067b`).

| Disposition | Codex | Claude | Pinning tests |
| --- | --- | --- | --- |
| Lazy creation | Proved | Proved | AL::test_allocations_commit_descriptors_with_no_dispatch_and_replay_readonly; CO::test_only_the_selected_branch_allocates_and_invokes_and_the_join_keeps_its_handle; T::test_fresh_then_resume_advance_one_native_store[codex], [claude] |
| Sequential append | Proved | Proved, including split final rows | T::test_fresh_then_resume_advance_one_native_store; TU::test_clean_run_commits_four_turns_on_two_native_sessions; NS::test_claude_sequential_turns_after_a_split_final_bind_in_order |
| Completion identification from the store, not stdout | Proved | Proved | NS::test_head_and_completed_turn_follow_the_store; NS::test_open_turn_and_ambiguity_are_reported_not_guessed; NS::test_codex_turn_without_final_answer_is_not_bound; NS::test_codex_turn_followed_by_another_turn_is_not_bound; NS::test_claude_split_final_binds_its_last_row; T::test_interrupted_turn_leaves_an_open_head_and_no_terminal; T::test_timeout_reports_124_and_only_a_completed_store_shows_the_turn (Codex); TU::test_claude_is_error_result_is_never_committed |
| Turn-local contracts (per-turn prompt, inputs, typed-result validation, fresh result destination) | Proved runtime-side | Proved runtime-side | TU::test_input_parts_bind_agent_and_predecessor; TU::test_invalid_typed_result_closes_failed_with_the_turn_position_code; TU::test_agent_turn_result_exposes_its_committed_bundle_path; CS::test_clean_consumer_run_four_turns_two_sessions_lineage_and_readonly_resume; SR::test_delivery_name_is_structural_and_matches_the_ordinary_path; ADM::test_agent_turn_rejects_overrides_and_unbounded_options (overrides and phased delivery refused) |
| Compatible policy | Proved | Proved | TU::test_policy_mismatch_refuses_before_dispatch; TU::test_config_digest_change_refuses_policy_mismatch; TU::test_template_change_between_run_and_resume_refuses_agent_policy_mismatch; TU::test_allocation_model_and_effort_win_over_turn_policy; CL::test_claude_unrestricted_workspace_declares_session_support_without_changing_its_command |
| Exact-locator loss rejection | Proved | Proved | T::test_lost_locator_is_rejected_by_the_native_cli_and_absent_from_the_store[codex], [claude]; NS::test_locate_rejects_a_locator_that_is_not_a_plain_id; CL::test_resume_must_match_requested_session_and_rejects_mixed_ids; CS::test_lost_designer_session_refuses_before_dispatch |
| Quiescence after timeout/cancel: executor reap of the process group | Provider-independent | Provider-independent | T::test_nonzero_before_append_leaves_no_native_trace_and_a_lingering_grandchild_is_refused_and_reaped; T::test_timeout_reports_124_and_only_a_completed_store_shows_the_turn |
| Quiescence on resume: `quiesce` | Provider-independent | Provider-independent | RE::test_orphaned_process_group_is_quiesced_before_recovery; RE::test_resume_proves_a_launched_attempt_not_dispatched_and_allocates_the_next; BO::test_first_turn_killed_after_launch_is_quiesced_and_abandoned; RE::test_quiesce_never_signals_a_reused_pgid; RE::test_not_dispatched_needs_a_proven_empty_group_before_any_head_check |
| External divergence detected before append (D1) | Proved | Proved | T::test_overlapping_external_append_moves_the_head_before_our_turn[codex], [claude]; TU::test_native_head_advanced_elsewhere_refuses_before_started; CS::test_external_advancement_of_the_designer_refuses_before_dispatch |

## Limits

| Limit | Statement |
| --- | --- |
| D1 operator window | Exclusive continuation is runtime-owned: the run writer lock and one active turn per agent prevent internal overlapping appends, and before every append the adapter compares the native head with the predecessor's recorded committed position. An external writer (an operator resuming the same native session from their own shell) that appends between that check and our append is not refused by that turn; the advancement is detected at the next turn as `agent_session_diverged`. The adapter also refuses to bind a completion that is not the unique turn after the recorded position. Documented operator limit, not a qualification blocker. Codex native active-writer exclusion is defense in depth; Claude has none (probe: overlapping native appends accepted). |
| R3 quiescence | `quiesce` identifies the group by `pgid` plus the leader's start time (`/proc/<pid>/stat` field 22, recorded in the receipt at `launching`) and never signals a live leader whose start time differs. Residual: a leader that exec-replaced itself keeps an identical start time and is still signalled (accepted by R3). On a platform without `/proc` the start time is unavailable and `quiesce` falls back to process-group liveness alone (`killpg(pgid, 0)`). The start-time check is not repeated between SIGTERM and SIGKILL. |
| Attempt directory deleted by hand after launch | A first turn redispatches without an abandonment record; later turns are backstopped by D1. Tampering, outside the failure table. |

## Real-provider evidence still required

| Disposition | Real evidence |
| --- | --- |
| Lazy creation, sequential append, completion identification, turn-local contracts, compatible policy, receipt `fresh` then `resume` with a recorded `pgid` | Tasks 19 (Claude, `haiku`/`low`) and 20 (Codex, `gpt-6-luna`/`low`): one two-turn context-retention smoke each, `tests/e2e/test_agent_session_real_claude.py`, `tests/e2e/test_agent_session_real_codex.py`. The Codex smoke model differs from the consumer's default (coordinator ruling) |
| Exact-locator loss rejection, quiescence after cancel | Observed for both CLIs in the 2026-10-13 native CLI probe, outside this runtime; Tasks 19–20 do not exercise them |
| External divergence on a real store | Not exercised by Tasks 19–20 |
| Exact interrupted-turn recovery | Inconclusive in the 2026-10-13 probe; not exercised by Tasks 19–20 |
| Acceptance comparison against the artifact-handoff baseline (clean and failed/resumed) | Not run; authorized separately by the owner (D8) |

## Gaps

| Id | Row / kill point | Missing pin |
| --- | --- | --- |
| G1 | Failure row 5, missing typed result | Only an invalid payload (`invalid-result` shim mode) and a Claude `is_error` result are pinned; no test completes the native turn and leaves the result file absent |
| G2 | Quiescence failure is `agent_turn_unresolved` | Pinned at unit level only (an unprovable group never proves non-dispatch); no public `resume` refusal on an `unprovable` group |
| G3 | Bootstrap kill sub-points | No kill after `abandoned.json` before `failed` (the receipt kill stops before `abandoned.json`), and none at the `launching` to `unknown` write before `abandoned` |

## Real-provider smokes (Tasks 19–20)

Pending: appended by the coordinator after the bounded paid runs.
