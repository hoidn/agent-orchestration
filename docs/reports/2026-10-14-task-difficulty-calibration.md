# Task-Difficulty Calibration (Plan Task 8)

Status: complete. No rung qualified under the frozen criterion, so the calibrated experiment (plan Task 9) does not run.

Later (2026-10-15): the owner chose rung 3 on the blocker rule alone, and Task 9 ran on it. See the
[E-B2 report](2026-10-15-calibrated-orc-versus-single-call.md). This report's conclusion is unchanged.

Amendment notice (2026-10-15, after Task 9): the owner removed the single-call hidden-acceptance condition from the
calibration rule (ruling R55; `amends_4` in [`calibration.json`](../../experiments/compare/criteria/calibration.json),
replacing the frozen `3149bc36…` this report cites). A task now qualifies when expected review blockers are at least
1. A mean from 1 up to but excluding 1.5 over two patches still needs a third single call and review. Hidden fractions
are still measured and reported, as description only. This report keeps the two-condition criterion it ran under and its
results. Under the new rule, rungs 2 (mean 2.5) and 4 (2.0) meet the threshold on their recorded patches. Rungs 1 and 3
(mean 1.0) are borderline and unresolved: qualification would need a third single call and review, which were never
run. No run was added.

Model disclosure (2026-10-15, after an audit of Claude session files): the Cost section's "No Anthropic agent calls"
counted the registered role calls only. Inside rung 2's two single-call runs (`direct_task/run-3` and `run-4`), the
candidate repository's own tests ran its provider probe. The probe calls `claude -p --model fable`, `fable` being its
default model, through the user's `claude` CLI, which answered with `claude-fable-5-1`.
- 100 sessions: 60 in run-3 and 40 in run-4.
- Each session is one `Say OK only.` probe answered in one assistant message. Together they are 400 output tokens.
- They were not registered role calls. Whether they affected the agents' work was not measured.
- No run was remeasured, and no result changes.

The audit is `agent-orchestration-compare-evidence/calibration/no-fable-experiments/fable-nested-audit.json`. Later runs guard against this: the shims refuse Fable and default nested `claude` to
`claude-opus-5-5`, and the scan flags Fable answers.

## Question And Criterion

The question is which task on a frozen ladder is the first where two conditions hold:
- one call with the control's binding (`gpt-6.1-sol`, effort high, `:timeout-sec 14400`) passes less than half of
  the hidden acceptance tests;
- the treatment reviewer raises on average at least one blocking finding on those single-call patches. This is the
  owner's rule of 2026-10-14: "raise task difficulty until the expected number of review blockers is ≥ 1".

Each rung got `k = 2` single calls and one review per patch, using `reviewed_change`'s reviewer (`review_once`,
`gpt-6-sol`).

- **Criterion:** [`experiments/compare/criteria/calibration.json`](../../experiments/compare/criteria/calibration.json),
  final SHA-256 `3149bc36e6b822eba5e7d735abacad6bb145487259c0d0b090feb837daedab66`.
- **Amendments 1–3:** each was made before its rung's first run. Each added that rung's package and cites the
  previous hash; none changed a definition, a threshold or the ladder's order.
- **Ladder:** [`experiments/compare/tasks/calibration-ladder.md`](../../experiments/compare/tasks/calibration-ladder.md).
  Rungs are ordered smallest first (R43): features on `main` after 2026-07-01, each with at least 1500 changed lines
  under `orchestrator/` and an objective hidden test set.
- **Drops before freezing.** Each package's hidden set keeps only node ids that fail at the base and pass at the
  solution, each run alone. It drops:
  - node ids the stub anchor passes (R49, from rung 2);
  - tests of private signatures the solution changed (R44);
  - fault injection through private helpers (R50);
  - documentation-wording tests.
- **Runtime:** `/home/ollie/calib-runtime`. It was at `2b9efd81` for rung 1. Later rungs used commits that differ from
  it only in task packages and criteria. Every run ran under the bubblewrap sandbox (private `/tmp`, `/dev/shm` and
  process list, empty `/var/tmp`).
- **Live smoke:** on `eb-repl`, before freezing, for mechanics only. It is not a rung. `direct_task` completed;
  `review_once` returned APPROVE with 0 blockers.

## Results

| rung | task | single calls' hidden acceptance | blockers per review | mean blockers | anchors | qualifies |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `cf1-generic-unions` | 149/164 (0.91) / 148/164 (0.90) | 1 / 1 | 1.0 | stub 0.01, upstream 1.00 | no |
| 2 | `resume-projection-integrity` | 88/119 (0.74) / 87/119 (0.73) | 1 / 4 | 2.5 | stub 0.00, upstream 1.00 | no |
| 3 | `adopted-attempt-lineage` | 27/52 (0.52) / 16/52 (0.31) | 1 / 1 | 1.0 | stub 0.00, upstream 1.00 | no |
| 4 | `pure-result-replay` | 85/134 (0.63) / 87/134 (0.65) | 2 / 2 | 2.0 | stub 0.00, upstream 1.00 | no |

Hidden fractions are measured in a calibration pool with no judge, each node alone. The upstream anchor passes 100% and
the stub at most 1% in every rung, so every pool is valid.

- **The owner's blocker condition held at every rung.** The mean was 1.0, 2.5, 1.0 and 2.0. Every one of the 8 reviews
  returned `REQUEST_CHANGES`, and each finding names a concrete input that goes wrong (listed below).
- **The single-call condition never held.** One `gpt-6.1-sol` call passed 90% of rung 1's hidden tests, 73–74% of
  rung 2's, 52% and 31% of rung 3's, and 63–65% of rung 4's. Rung 3 missed by one node id: 27 of 52 against at most
  25.
- **Wall clock.** Single calls took 13–58 minutes, well inside the 4-hour limit. Reviews took 2–6 minutes.

## Review Findings (verbatim)

- Rung 1, review_once/run-1 (on direct_task/run-1), REQUEST_CHANGES:
  - An exported Tree[T] with a Tree[T] payload causes compile_stage1_entrypoint to recurse indefinitely during import canonicalization, even when the importer never instantiates Tree; preserve the template and report generic_union_instantiation_cycle only at an actual use.
- Rung 1, review_once/run-2 (on direct_task/run-2), REQUEST_CHANGES:
  - orchestrator/workflow/loops.py:827-873: A valid target 2.12 repeat_until with ordinary body steps producing status and state__count, max_iterations=2, a false condition, and an on_exhausted status override raises LoopStateIntegrityError instead of publishing EXHAUSTED and the final count. Restrict compiled snapshot lookup to generated loop/recur frames and preserve ordinary repeat_until behavior.
- Rung 2, review_once/run-3 (on direct_task/run-3), REQUEST_CHANGES:
  - A persisted call frame with status set to a private string, or current_step.step_id set to one, is rejected but copies the complete value into resume_projection_integrity_error.context.offending_value. Limit emitted values to bounded approved identities and omit malformed non-identity values.
- Rung 2, review_once/run-4 (on direct_task/run-4), REQUEST_CHANGES:
  - A valid call_step_id with a foreign call-frame key such as foreign::visit::999 passes the root audit and is resumed by the reached call.
  - A Workflow Lisp retry frame with a 5,000-digit ordinal raises raw ValueError instead of resume_projection_integrity_error.
  - A completed frame occupying the derived resume ID returns routable contract_violation, so failure routing can continue execution.
  - Malformed persisted identity strings are copied verbatim into the diagnostic without a privacy or size bound.
- Rung 3, review_once/run-5 (on direct_task/run-5), REQUEST_CHANGES:
  - After publishing an archive file but before removing its source, or after moving one of multiple rows, _logical_view rejects the exact partial state and replayed apply fails with attempt_row_state_invalid. Accept exact v1 replay states in the logical view and test both interruption points.
- Rung 3, review_once/run-6 (on direct_task/run-6), REQUEST_CHANGES:
  - When one exact archive file has been published and the remaining rows are still in their pre-move state, v2 validate and apply raise attempt_row_state_invalid because _adopted_logical_view requires an all-pre or all-post state.
- Rung 4, review_once/run-7 (on direct_task/run-7), REQUEST_CHANGES:
  - Malformed or symlinked checkpoint sidecars bypass the established safe reader; malformed JSON raises an uncaught JSONDecodeError instead of pure_result_replay_unavailable, and invalid entries may be skipped.
  - A current_step cursor with an eligible pure step’s execution index but different name and step ID is accepted as unrelated, so contradictory progress can be classified derived_complete.
- Rung 4, review_once/run-8 (on direct_task/run-8), REQUEST_CHANGES:
  - A profiled resume with an invalid durable replay input changes state.json and creates observation artifacts before pure_result_replay_unavailable; preflight replay before any CLI or executor write.
  - A malformed JSON record in the current run's eligible pure checkpoint family is skipped by the audit, allowing invalid durable checkpoint evidence to coexist with resume.

## Interpretation

- **On this repository's feature history, task size is not what limits a single call.** Each rung's `task.txt` has to
  name every entry point and literal the hidden tests check. With that text, one call delivers most of a 2000- to
  4000-line feature.
- **The single call still leaves real defects behind.** Every patch drew at least one blocker from the reviewer. These
  are the defects a review-and-revise workflow exists to fix.
- **The two conditions measure different things.** The hidden-acceptance condition asks whether the task is
  unfinishable in one call. The blocker condition asks whether review has work to do. The owner's rule is the second
  one, and it is met from rung 1 on.

## Cost

- **Agent calls:**
  - 8 `gpt-6.1-sol` single calls and 8 `gpt-6-sol` reviews on the ladder;
  - 1 single call and 1 review for the smoke.
- **Codex:** the weekly window went from 96% to 100% during calibration. After that the calls used credits: the
  balance fell from 29795.96 to 28550.95, so 1245.01 credits were spent (R8 allows credits to cover the designed
  runs).
- **No Anthropic agent calls.** The rung packages were prepared by an Opus subagent.

## Limits

- **`k = 2` per rung** is a small sample. The reviewer's variance is unmeasured beyond these 8 reviews.
- **Prescriptive task texts.** Rungs 1, 2 and 4 needed long task texts, because their hidden tests pin internal names
  and messages (R46, R51). That may make single calls easier than an open-ended specification would.
- **Contamination is detected, not prevented**, for home, transcripts and the network. Every run's scan hits were
  adjudicated (own tmux sockets; paths committed at the base appearing in pytest output).

## What Follows

The frozen criterion stops here, and Task 9 does not run. The owner has to choose what comes next:
- **Rungs 5–6.** These are the ladder's largest features (`dsl-232-composition`, 10478 lines; `provider-peer-messaging`,
  12835 lines). Running them goes beyond the stop rule and needs approval and an amendment.
- **Qualify on the owner's blocker rule alone.** Rung 2 (mean 2.5 blockers) or rung 4 (2.0) would then carry Task 9.
  Its primary measure would be `reviewed_change`'s paired hidden gain, not the gap to the single call, because the
  single call already passes most hidden tests.
- **Change how tasks are specified,** so the hidden tests do not need every internal literal named. For example, use
  behavioural tests written for the calibration against the public CLI. Then re-run the ladder.

## Reproduce

Run records, pools, per-node hidden results and reviews are in the evidence directory beside the repository
(`agent-orchestration-compare-evidence/calibration/`, `rung-<n>-calibration.json`). The commands are those of the
harness README (`run`, `collect`, `scan`, `pool`, `review_once`), with the criterion's definitions.
