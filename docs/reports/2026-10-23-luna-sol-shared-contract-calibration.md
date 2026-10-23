# LS9: Shared-Contract Reassessment Of The LS8 Natural Solutions

**Role:** Historical captured evidence. This report records a completed task-difficulty calibration reassessment; it does not select future runs or qualify the evaluator, C1, a sealed task, or an ORC advantage.

**Outcome: neither task qualifies.** With the complete original solver contract supplied to the judge, RPI has Luna mean 4 and Sol mean 5.5 (gap 1.5); PRR has Luna mean 3.5 and Sol mean 2 (gap −1.5). The stronger hypothesis is observed ahead only on RPI, and neither task satisfies the frozen gap and difficulty interval.

## What was corrected

[The LS9 plan](../plans/2026-10-23-functional-calibration-shared-contract-rejudging-plan.md) selected two fresh blind judgments of all eight unchanged [LS8 captures](2026-10-23-luna-sol-filesystem-isolation-calibration.md). Original tasks, generation inputs, models, tools, limits, patches, receipts and terminal outcomes were preserved. Both PRR Sol attempts still have their original `false` delivery value. No natural observation was omitted or regenerated.

Each new `score-inputs.intent` equals the complete corresponding solver `task.txt`, with byte equality checked against all eight original delivered inputs and prompts. This repairs the confirmed RPI discrepancy between the solver contract and the prior abbreviated judging brief. Each judge was `gpt-6.1-sol` high, one sequential call per task, with four anonymous natural clones and the unchanged functional S0–S8 rubric. There were no controls, references or hidden tests.

## Canonical ratings

All values below come from the harness clone-ID joins. `run-1` and `run-2` identify the original LS8 observations; LS9 did not create new generations.

| Task | Arm | Original observation | LS9 clone ID | Functional score /8 |
| --- | --- | --- | --- | ---: |
| RPI | Luna high | run-1 | `7c7df870` | 4 |
| RPI | Luna high | run-2 | `e0d2b3ae` | 4 |
| RPI | Sol low | run-1 | `992b9c8e` | 5 |
| RPI | Sol low | run-2 | `e8d4c45a` | 6 |
| PRR | Luna high | run-1 | `e7ec962f` | 4 |
| PRR | Luna high | run-2 | `0970e0c1` | 3 |
| PRR | Sol low | run-1 | `45846424` | 2 |
| PRR | Sol low | run-2 | `0ed815ed` | 2 |

| Task | Luna mean | Sol mean | Sol − Luna ≥ 2 | Sol > 3 | Sol < 5 |
| --- | ---: | ---: | --- | --- | --- |
| RPI | 4 | 5.5 | FAIL: 1.5 | PASS | FAIL |
| PRR | 3.5 | 2 | FAIL: −1.5 | FAIL | PASS |

All three predicates are required separately for each task. There is no aggregate-score substitution or threshold change. RPI is above the selected strong-arm difficulty interval; PRR is below it and reverses the hypothesized ordering.

The judge's RPI Sol deductions now concern loop auditing/sticky failure handling and nested-call validation precedence, rather than the incompatible restrictions in the old brief. On PRR, the judge credits working additive profile/state APIs but reports that both Sol solutions leave automatic CLI selection and executor settlement/replay integration disconnected. Luna's PRR solutions connect more of the normal execution path but retain important recovery and persistence defects. These are the judge's code-inspection findings, not independently reproduced functional results.

## Relation to the previous judgments

Keep LS8's raw scores unchanged: RPI Luna 3/4 and Sol 5/6; PRR Luna 4/3 and Sol 0/0. LS9 records RPI Luna 4/4 and Sol 5/6; PRR Luna 4/3 and Sol 2/2. The task contract supplied to the judge changed and fresh judgments were drawn, so these differences do not isolate a causal effect or establish judge reliability. They do not demonstrate improvement in the solutions: every solution is unchanged.

## Execution, usage and limits

Both workflows completed with exit zero, as did canonical close. Inventory records two fresh LS9 starts plus 66 historical starts = 68 overall, with one call/root per new judge, no native children, extra roots, Claude, Fable or delegation. RPI had zero scan hits. PRR's 16 hits were printed `pytest` instructions in the clones' public `AGENTS.md`; independent structured-action review found no test execution. Only its scan verdict was adjudicated through the public harness; original scan/result bytes were retained. Pool patches and clone indexes remained intact.

Both new judges have complete metered native receipts. Recorded token totals are 2,534,831 for RPI and 2,638,354 for PRR, including 2,371,584 and 2,460,800 cached input tokens respectively; these are cumulative session usage, not context-window sizes. The frozen table has no model price, so full deployed cost remains **unavailable**, not zero. No quality/cost Pareto claim follows.

This is a small exploratory calibration with two natural observations per arm/task and one fresh judge per task. The tasks are related members of the same family. Judge inspection did not execute candidate tests. Task qualification failed; independent evaluator qualification, disjoint validation and downstream campaign gates remain open.

## Evidence

- Canonical readout: `/home/ollie/sc-evidence/LS9-20261023/combined-readout.json`, SHA256 `d85986050ae087d8625cc63c660c3d1a1af3d8638160ef0104d758e3969f4de2`.
- Criterion: `/home/ollie/sc-evidence/freeze-functional-shared-contract-20261023/criterion.json`, SHA256 `02b46e5f0709c03cfbf1b0d1dc5bcd89df974744fc29aa2c544e6785d431e637`.
- Final packet: the same freeze root's `judging-packet-complete.json`, SHA256 `4db541a949118a93d43198d68f291d6fdccc75bf9ec4b6f13c10b33aa82f67be`; independent packet review `89ba68945988833c093f5f7c194a4d07e44b6074f73f6c377f2e3b87bde9ebdd`.
- Judge integrity reviews in the LS9 evidence root: `rpi-judgment-integrity-review.json`, SHA256 `b7d46b1fb1f0fb01cb71350c62a8ae01e987597940816d30e73b6e68309f55c9`; `prr-judgment-integrity-review.json`, SHA256 `95810913ba10a2f5b9f8274ef9085b0d8504bd34c77c7af6924349ee4ee22e1e`. Their crosswalks preserve original results and scans; separate admission records document intake.
- `judging-operator.exit` and `close.exit` are both `0`. Original LS8 readout SHA256 remains `6a25688dcae71d5246c38a6cda77e3b64662707efbce1407ade6598bf4c450c8`.

## Continuation

The [command-recovery plan](../plans/2026-10-23-functional-calibration-command-recovery-plan.md) records the coordinator-selected prospective, smaller PRR rung: retain pure-result replay and qualified in-place recovery of ordinary commands, while keeping historical call recovery/retry behavior. New task data and public checks must agree before any fresh generation. This is an exploratory difficulty adjustment with fresh natural solutions; it assumes neither monotonic scores nor a Sol advantage. RPI and all LS8/LS9 evidence remain unchanged.
