# Evaluated Execution Phase 6a Pilot

Status: proposal cut frozen for independent review; reviewed-change and W3 cuts not started.

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
| Proposal: use `review_focus` only in the review hook on the `2.35` evaluated route | `phase6a_proposal.orc.txt`: `ExperimentBrief`, `review-proposal`, `run-experiment`; `test_workflow_evaluated_phase6a_pilot.py` covers the two focuses and three terminal outcomes. | RED: `compile --diagnostics-json` exited 0; `run --dry-run` exited 2 with `Validation error: Workflow input binding failed`. The public CLI did not expose a structured diagnostic code or source location. This was the expected missing workflow input binding on the initial `2.35` copy, not a fixture setup failure. | Added `review_focus` to the context record and workflow signature, bound it in the brief constructor, and added it only to `review-proposal`'s provider input list. The revision provider input list, `std/improve`, prompt assets, manifests, and launcher contract remain unchanged. | Final six-case module: 6 passed. Each case compiled and dry-ran successfully, stopped after the committed first review with exit 75, resumed with exit 0, and completed replay with exit 0 and a byte-identical workspace. Details below and in C6. | Pending. |
| Reviewed-change variant and W3 qualification | Not in this bounded cut. | Not started. | Not started. | Not started. | Not started. |

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

The proposal source still has 60 nonblank, noncomment lines under the existing line counter, the same category totals as the maintained source. `std/improve` remains 37 lines and unchanged. The new test module is 159 physical lines; Radon 6.0.1 reports every new function at CC 1–7, below the default-CC limit of 12. No production runtime or shared helper was modified.

The final six-case pytest log, prior RED and single-case GREEN records, static metrics, per-case command traces, input/source hashes, run IDs, memo/request counts, request logs, and launcher logs are retained in C6. The final owner hashes are in the [after-source manifest](../../.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/evidence-proposal/after-source-hashes.json), and the per-run ledger is in [run-ledger.json](../../.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/evidence-proposal/final/run-ledger.json).

## Evidence

Raw baseline count output and the exact command are retained under the [physical C6 evidence root](../../.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/raw/baseline-count-lines.txt). New proposal test/CLI output and before/after source hashes will be added there as the cut progresses.
