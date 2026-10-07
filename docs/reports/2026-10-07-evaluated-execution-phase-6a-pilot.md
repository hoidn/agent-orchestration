# Evaluated Execution Phase 6a Pilot

Status: proposal independently reviewed PASS; final reviewed-change caller is frozen for independent review after the nested-control compiler correction; W3 is not started.

## Entry and baseline

This pilot starts from delivered Phase 3 commit `06130a53193e42dc1fdc2e9aa4575220bb43d707`, recorded by the coordinator after verifying the Task 17 delivery report and fast-forward/push. Phase 3 verification remains attached to its original source hashes; this cut reuses it and does not rerun the full suite, watchdog handoff campaign, or live-provider evidence.

The pre-edit source/helper SHA-256 values and byte/line counts are in the [baseline manifest](../../.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/evidence-proposal/baseline-source-hashes.json). The count was produced by the repository's existing `experiments/orc_repetition_census/count_lines.py` before any source or test edit:

| Maintained source | Header | Types | Prompts | Procedures | Other | Total | Annotation lines | Constructor type names |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Proposal (`2.33`) | 6 | 8 | 0 | 46 | 0 | 60 | 8 | 3 |
| Reviewed change (`2.28`) | 6 | 20 | 16 | 55 | 0 | 97 | 0 | 5 |
| `std/improve` | 5 | 8 | 0 | 24 | 0 | 37 | 4 | 3 |

The proposal path currently has a typed workflow input `question`, builds `ExperimentBrief(question)`, calls pure `propose`, passes the brief through `std/improve` to both provider hooks, then calls `execute` once for every terminal outcome. The helper keeps the generic `Decision`/`Improvement` loop and a limit of three; `review-proposal` and `revise-proposal` own separate provider effects, while `execute` owns the launcher command effect. The proposed edit adds review-only information to the explicit brief and review provider input, leaving the revision input list and launcher contract intact. The explicit brief still crosses both hooks, so its additional field is a forwarding cost that remains visible in the measurement.

## Edit ledger

| Edit | Files/declarations | Failed attempts and cause | Correction | Result | Independent review |
| --- | --- | --- | --- | --- | --- |
| Proposal: use `review_focus` only in the review hook on the `2.35` evaluated route | `phase6a_proposal.orc.txt`: `ExperimentBrief`, `review-proposal`, `run-experiment`; six cases cover two focuses and three terminal outcomes. | RED: `compile --diagnostics-json` exited 0; `run --dry-run` exited 2 with `Validation error: Workflow input binding failed`. This was the missing binding on the initial `2.35` copy. | Added `review_focus` to the context record and workflow signature, bound it in the brief constructor, and added it only to `review-proposal`'s provider input list. | The six-case proposal campaign passed. Each case compiled, dry-ran, stopped after the first committed review (75), resumed (0), and completed replay (0) with byte-identical workspace state. | PASS for the bounded proposal cut; see the independent review in C6. |
| Reviewed-change final caller using shipped `std/improve` | `phase6a_reviewed_change.orc.txt`; six existing scenarios in `test_workflow_evaluated_phase6a_pilot.py`. | The provisional direct generic source was blocked by missing `type_env` propagation in command-control leaf discovery. The compiler correction was independently reviewed and integrated before this final caller. A prior behavioral RED without a final-round guard dispatched an extra coder request and failed resume with `[provider_exit_nonzero]`. | The final caller uses `Decision[Review Outcome]`, carries the public `Review` payload as evidence/feedback, uses public `Outcome` for terminal blocked reasons, and guards both round-3 rejection variants before revise. It has no `ReviewSignal`, `ReviewBlock`, `ReviewTerminal`, or unused current-change state field. | Six public scenarios passed against the maintained 2.28 route. Each new route compiled, dry-ran, paused at the committed first review, resumed, and completed replay with exit sequence 0/0/75/0/0. | Pending independent review of the final caller. |
| W3 qualification | Not in this bounded cut. | Not started. | Not started. | Not started. | Not started. |

The historical 92/93-line comparison for the census variants remains separate; those variants are not executable parity baselines and are not edited here.

## Proposal cut

The variant is a 2.35 measurement source installed only by the focused test. Its declarations changed in three places: `ExperimentBrief` now carries `review_focus`; `run-experiment` binds the added workflow input into that record; and `review-proposal` includes the field in its typed provider inputs. Both hooks still receive the explicit brief through `std/improve`, but `revise-proposal` does not expose the focus to its provider. The comparison verifies the complete normalized reviser request against the 2.33 baseline, including rendered inputs, while normalizing only the target-specific output-bundle path and site key.

The test reuses the existing deterministic proposal plans and launcher probe. It compares the original `{"question":"warmup"}` input on target 2.33 with the same question plus one focus sentinel on the 2.35 variant. Each of two distinct sentinels exercises all three terminal outcomes:

| Outcome | Reviewer/reviser requests per route | 2.35 memo rows | Launcher output |
| --- | ---: | ---: | --- |
| APPROVED | 3 | 9 | Same approved proposal and argv as the maintained route |
| BLOCKED | 3 | 9 | Same blocked outcome, reason, and argv as the maintained route |
| EXHAUSTED | 6 | 15 | Same final revised proposal and argv as the maintained route |

For all six cases, the sentinel appears in every review request and in no revision request. The 2.35 route pauses with one committed review request, resumes through the public CLI, verifies committed result bytes, and completes without redispatch; a second completed resume changes no workspace bytes. The returned value and launcher log match the target-2.33 route. Request logs contain fixture prompts and dynamic sentinel values, not real provider output.

The proposal source still has 60 nonblank, noncomment lines under the existing line counter, the same category totals as the maintained source. `std/improve` remains 37 lines and unchanged. At the proposal freeze, the shared test module was 159 physical lines; the current module is 289 lines after adding the reviewed-change cases. Radon 6.0.1 reports every helper in the current module below CC 12 (maximum 9). The proposal cut changed no production runtime or shared helper; the reviewed-change cut uses the separately reviewed nested-control correction described below.

## Reviewed-change final caller

The candidate uses target 2.35, the shipped `std/improve`, and independent reviewer/coder provider hooks. The `Review` provider union, `ReviewReport`, public `Outcome`, prompts, provider policies, and call ordering remain unchanged. The six scenarios reuse the maintained route's deterministic fixtures and add first-review approval and a final-round WRONG_APPROACH rejection. The latter checks that the final decision becomes `UNRESOLVED` without invoking the coder again. NEEDS_HUMAN remains `ESCALATED`, and REQUEST_CHANGES and WRONG_APPROACH continue to use their distinct fix and redo requests.

The final caller keeps `ReviewContext(task, intent, repo)` and `ReviewState(round, account, replies)`, without a current-change field that the loop never reads. It instantiates the shipped helper as `Decision[Review Outcome]`: the provider's existing `Review` value passes directly as APPROVE evidence or REVISE feedback, while terminal BLOCKED reasons use the public `Outcome` union. REQUEST_CHANGES and WRONG_APPROACH each return BLOCKED with the matching `UNRESOLVED` reason and round at round 3; NEEDS_HUMAN returns `ESCALATED`. The workflow returns a blocked `Outcome` directly and keeps an exhaustive match over approved evidence. That match includes the other `Review` variants because the generic helper does not refine the evidence type to APPROVE; each defensive arm maps to the corresponding public unresolved/escalated outcome. This trades one explicit total match for removing the internal signal/block adapters.

The source counter reports 135 nonblank, noncomment lines versus 97 for the maintained 2.28 workflow (+38): header 7 vs 6, types 28 vs 20, prompts 16 vs 16, procedures 84 vs 55. `std/improve` remains unchanged at 37 lines. The separately integrated compiler correction (`d6adb627`) passes the already selected typed environment to evaluated nested-result leaf discovery and preserves the legacy context-free path. The reviewed-change caller itself adds no compiler/runtime or stdlib changes.

The instrumented source with signature `Decision[ReviewSignal ReviewTerminal]` was rejected with `collection_element_type_unsupported` for `ReviewTerminal`. The earlier `Decision[Review ReviewTerminal]` rejection concerned `Review` and is retained separately without a captured stack. A scratch-only monkeypatch recorded the stack and the local values at the diagnostic: `_structured_result_field_definition` had `type_env=None`, `allow_nested_structures=False`, and `type_ref=ReviewTerminal`; `_flatten_structured_result_field` also had `type_env=None`. The stack reaches that call from `_shared_variant_structured_result_fields` during `derive_union_workflow_boundary_projection`, itself reached by output-leaf discovery in `command_control_summary` while preparing an inline command. The missing environment prevents the target 2.35 nested-structure allowance from being applied. The error therefore reflects dropped compiler context, not a language restriction. The exact source, stack, hook, and raw compile output are retained under C6.

Other compile attempts are retained with their diagnostics: a redundant `:returns` annotation on a prompt raised `prompt_return_redeclaration_forbidden`; reading `report` before matching the `Review` union raised `variant_ref_unproved`; an intermediate malformed source had an extra closing parenthesis; and direct nested union/record generic forms were rejected at the same type-environment propagation point. These attempts were corrected or superseded without production edits. A separate behavioral RED removed the final-round guard: the final WRONG_APPROACH caused one more coder dispatch, so the 2.35 route had seven requests against six on 2.28 and public resume exited 1 with `[provider_exit_nonzero]`. The final guard returns BLOCKED before `std/improve` invokes revise on a final rejection.

For all six final cases, normalized request records, provider order/count, terminal value, report files, repository bytes, and request lineage match the maintained route. The 2.35 public CLI sequence is compile 0, dry-run 0, stop after the committed review marker `review-for-improve` 75, resume 0, and completed replay 0. The last replay changes no workspace bytes and redispatches no provider. The final focused result is 6 passed, 6 deselected in 100.98 seconds. A fresh collect-only log is retained at C6 and records all 12 module cases in 2.90 seconds. The final module is 289 physical lines and the variant is 150, both below 500; Radon 6.0.1 reports all helpers below CC 12, with a maximum of 9.

The proposal evidence remains in `evidence-proposal/`; the prior flat comparison and compiler diagnostics remain immutable in `evidence-reviewed-change/`. The final caller's collect-only output, six-case focused run, per-case public CLI traces, source/input hashes, stop identities, run IDs, memo/request counts, and artifact bytes are in `evidence-reviewed-final/`. Its receipt is stored at the C6 root outside the final evidence hash manifest.

## Evidence

Raw baseline count output and the exact command are retained under the [physical C6 evidence root](../../.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/raw/baseline-count-lines.txt). The proposal cut remains independently reviewed PASS. The final reviewed-change caller is ready for independent review; the earlier flat comparison and corrected compiler evidence remain available without being rewritten. This cut does not close Phase 6a.
