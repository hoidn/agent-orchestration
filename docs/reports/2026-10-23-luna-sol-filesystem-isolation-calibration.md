# LS8: Luna/Sol Functional Calibration With Filesystem Isolation

Status: historical captured result. Execution is complete and recorded qualification is false. A confirmed RPI judge-brief contradiction limits interpretation of its ratings.

This report records LS8's eight fresh generation observations and two blind judgments. It is a view of the [canonical readout](/home/ollie/sc-evidence/LS8-20261023/combined-readout.json), SHA256 `6a25688dcae71d5246c38a6cda77e3b64662707efbce1407ade6598bf4c450c8`, produced by canonical close with [exit 0](/home/ollie/sc-evidence/LS8-20261023/close.exit). The [filesystem-isolation plan](../plans/2026-10-23-functional-calibration-filesystem-isolation-plan.md) and frozen criterion own the selection and rule. This is not a launch recipe; the prospective reassessment direction below requires a separate concrete plan and declaration.

## Frozen protocol and execution

The [criterion](/home/ollie/sc-evidence/freeze-functional-filesystem-isolation-20261023/criterion.json), SHA256 `233dc2acab942fd7ec16f6d2beb083b7f2692a860c5d1b643509f134c963719a`, retains the byte-identical LS7 `*-inplace-failure` packages, one functional 0–8 score, two observations per arm/task and these roles:

- `direct_task`: `gpt-5.6-luna`, high effort.
- `sol_low`: `gpt-6.1-sol`, low effort.
- One blind `gpt-6.1-sol`, high-effort judge per task, inspecting four anonymous clones without references or controls.

Generations ran at most two concurrently with the frozen 14,400-second limit; the two judges ran sequentially with the 3,600-second limit. All ten units used one physical call. The final readout records **10 new + 56 historical = 66 total starts**, zero native children, extra roots, Claude sessions, spawn actions or forbidden model/delegation hits. No observations were replaced or carried over from LS7.

The [reviewed judging packet](/home/ollie/sc-evidence/freeze-functional-filesystem-isolation-20261023/judging-packet.json), SHA256 `5d6a9051ef6cccc3f0e2e82beb231011f06810c6efc04ea6e86d9c78e7385682`, passed [independent readiness review](/home/ollie/sc-evidence/LS8-20261023/judging-packet-independent-review.json). Its [declaration](/home/ollie/sc-evidence/LS8-20261023/budget-declaration-judging.json) binds the same ten-start selection and original generation declaration. Both actual judge sandboxes passed [inert-backend qualification](/home/ollie/sc-evidence/LS8-20261023/judging-sandbox-smoke.json) before paid judging.

## Historical recorded ratings and frozen predicates

The unchanged historical ratings below come from the readout's raw-rating → anonymous clone ID → original run joins. RPI means `resume-projection-integrity-inplace-failure`; PRR means `pure-result-replay-inplace-failure`. Attempt numbers are original per-arm run numbers; no runs or judges were excluded.

| Task | Arm | Attempt 1: score / clone ID | Attempt 2: score / clone ID | Mean |
| --- | --- | --- | --- | ---: |
| RPI | Luna high | 3 / `89e4d56e` | 4 / `7d70167c` | 3.5 |
| RPI | Sol low | 5 / `12fe53d0` | 6 / `aa124cce` | 5.5 |
| PRR | Luna high | 4 / `ecc72432` | 3 / `982d6eb6` | 3.5 |
| PRR | Sol low | 0 / `882214f5` | 0 / `d29925d0` | 0 |

Every task must satisfy all three predicates separately:

| Task | Sol mean − Luna mean ≥ 2 | Sol mean > 3 | Sol mean < 5 | Qualifies |
| --- | --- | --- | --- | --- |
| RPI | 2: pass | 5.5: pass | 5.5: fail | No |
| PRR | −3.5: fail | 0: fail | 0: pass | No |

Using the recorded ratings, RPI meets the declared gap but exceeds the strict upper bound; PRR has a negative gap and misses the lower bound. The readout retains `two_task_qualification=false`. Its `too_easy` and `too_hard` directions are nominal, mechanically computed labels, not justified next difficulty decisions. In particular, the confirmed briefing contradiction below prevents using the RPI scores/gap as a reliable basis for difficulty adjustment under the full task contract. No corrected score or stronger-arm ordering is inferred.

All eight generation workflows have original outcome `completed`. Both PRR/Sol workflows retain original terminal value **false**, as verified by the [PRR/Sol capture review](/home/ollie/sc-evidence/LS8-20261023/prr-sol-generation-integrity-review.json) and [adjudication crosswalk](/home/ollie/sc-evidence/LS8-20261023/prr-sol-generation-adjudication.json). Completion describes the workflow terminal status; those false values were neither rewritten nor treated as successful task delivery. Original patches, receipts and pre-adjudication snapshots remain bound.

## Confirmed solver/judge contract mismatch

The coordinator's [immutable diagnosis](/home/ollie/sc-evidence/LS8-20261023/judge-brief-contract-mismatch.json), SHA256 `36e3ecaa58f46872405a97e280f0b17aa5753057099f5acf8584d935ce1a5487`, confirms a contradiction between RPI's solver contract and judge briefing. The full frozen `task.txt` lines 10, 41 and 42 permit ordinary parent call-start publication, ordinary ancestor failure snapshots for reached-callee rejection, and configured finalization. The frozen `intent.txt`, which exactly equals `score-inputs.intent`, instead demands no mutation or effect at every reached call and changes only to root `status`, `error` and `updated_at`.

Both recorded Sol deductions (`12fe53d0`: 5; `aa124cce`: 6) invoke that incompatible summary. Execution, transport and capture integrity remain accepted; this input-contract defect does not alter the original ratings, means, gaps or six predicate outcomes. It does prevent a reliable RPI difficulty conclusion under the full task. Separate evaluator qualification remains absent.

The coordinator's **prospective LS9 direction, not executed**, is to reassess the same eight untouched generation captures with the identical full task contract delivered to solvers and judges: two new Sol-high judgments, no new generations, and no change to the functional rubric or thresholds. The [shared-contract rejudging plan](../plans/2026-10-23-functional-calibration-shared-contract-rejudging-plan.md) owns that selection and requires its concrete packet and declaration before dispatch. No replacement ratings or new difficulty adjustment are recorded here.

## Evidence and limits

The [RPI judgment integrity review](/home/ollie/sc-evidence/LS8-20261023/rpi-judgment-integrity-review.json) and [PRR judgment integrity review](/home/ollie/sc-evidence/LS8-20261023/prr-judgment-integrity-review.json) verify original rating shape, permitted access, unchanged clone indexes and raw-patch joins. Both judges inspected code; neither executed candidate tests. Their scores are code-inspection assessments under the functional rubric, **not independent functional test results**. Integrity review does not independently regrade candidate correctness.

Hidden acceptance tests were not executed; no hidden, reference or control scores contribute. The existing [runtime verification](/home/ollie/sc-evidence/preparation/LS8-runtime-verification/verification.json) and [independent runtime review](/home/ollie/sc-evidence/preparation/LS8-runtime-verification/review.json) establish the completed offline apparatus checks for runtime `6e75c90ceeac6b027557e5da80f8250ccc62a3b4` and its reviewed backport from main `caffd0afefdaa5f4e9f0a59bb7bf23333ce09f2d`. They do not establish these candidates' functional correctness. No new verification tests were run to write this report.

Complete native usage receipts for all ten calls are retained in the canonical readout. Both model prices and full monetary cost are **unavailable, not zero**; its known-priced subtotal is not a total-cost estimate. No model-aware quality/cost Pareto claim follows.

Two observations per arm/task and one related-family judge per task do not estimate reliability or judge bias. This completed run does not establish separate evaluator qualification, C1/V2 admission, ORC benefit, campaign or Phase 2 readiness, or reopen sealed-task gates. Historical reports, rubrics and scores remain unchanged. The prospective same-capture LS9 direction above does not authorize execution or change difficulty. Its concrete plan/declaration and any later difficulty decision remain with the coordinator.
