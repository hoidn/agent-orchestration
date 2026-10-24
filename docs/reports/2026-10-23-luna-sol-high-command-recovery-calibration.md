# LS11: Sol-High Command-Recovery Difficulty Calibration

**Role:** Captured task-difficulty evidence; not a general model ranking, evaluator qualification or campaign result.

**Result:** This commands-only PRR task passed the owner-confirmed rule. Sol 6.1 high scored 7 and 6 (mean 6.5/8); the two unchanged Luna-high solutions scored 3 and 3 (mean 3/8) under the same fresh blind judgment. The observed gap is **3.5 points**. Canonical close exited 0 after exactly three new calls, reaching 76 overall starts. The [LS11 plan](../plans/2026-10-23-functional-calibration-sol-high-plan.md) preserves the prospective protocol and execution ledger.

## Canonical result

Authority: `/home/ollie/sc-evidence/LS11-20261023/combined-readout.json`, SHA256 `cc8e98be793e4444636416fc9d37423c061aaa1290fd17cfc8fc37b39c85f6c3`. All ratings use the public harness's clone-ID → original-run joins. The judge was one fresh `gpt-6.1-sol` high session, scoring all four anonymous final clones together with the full 18,951-byte task.

| Arm / original run | Anonymous clone | Score /8 | Author elapsed seconds | Capture provenance |
| --- | --- | ---: | ---: | --- |
| Luna high, `direct_task/run-1` | `3f2b8604` | 3 | 2009.99 | Original LS10 capture, unchanged |
| Luna high, `direct_task/run-2` | `946ff9ff` | 3 | 1312.50 | Original LS10 capture, unchanged |
| Sol high, `sol_high/run-1` | `330c3d5f` | 7 | 2100.08 | Fresh LS11 generation |
| Sol high, `sol_high/run-2` | `b40896c1` | 6 | 1737.85 | Fresh LS11 generation |

| Frozen predicate | Observed | Met |
| --- | ---: | --- |
| Sol high mean >= 4 | 6.5 | Yes |
| Sol high mean − Luna mean > 0 | 3.5 | Yes |

Thus `qualified=true` for this task under LS11's rule. There is no upper bound. The owner explicitly confirmed this rule before dispatch; the earlier strict interval and two-point margin remain historical LS10 predicates. All four natural observations are included. Their original `true` delivery values are metadata, not correctness judgments. No hidden tests, synthetic defects, reference/control clones, retries or replacement observations were used.

## What the judge found

The judge credited both Sol-high solutions with integration into normal execution: profile selection, atomic value-free shells, dependency replay, durable-state checks and command recovery. It rated the first 7/8 because its checkpoint filtering and restoration-before-replay were implemented, while its zero-record fallback could accept a literal-only pure projection without the required durable owner. It rated the second 6/8 because its fallback rejected an interruption in the first input-backed pure projection and its replay occurred before checkpoint restoration.

For Luna's first solution, the judge found that replacing active state with persisted shells lost earlier pure values, while recurrent projections also lost bundles they needed to retain. For the second, it found that passing full results to the checkpoint hook defeated pure-checkpoint suppression and that command recovery bypassed required checkpoint validation/restoration. Those defects explain the lower functional ratings despite connected scaffolding. The canonical readout retains each diagnosis and its source locations.

These are the judge's code-inspection findings, not independently reproduced controller diagnoses. The judge made 31 public read/Git/result-writing actions and did not run tests. Authors' extensive test runs and baseline comparisons remain captured evidence; they do not establish a clean full suite. In particular, the retained comparisons used selected failures and locally reconstructed baseline sources. Missing external resources, historical assertions and timing failures limit what can be inferred from those comparisons.

## Interpretation and limits

The same Luna implementations received **4/4 in LS10 and 3/3 in this fresh judgment**. Their code did not change, and their historical scores remain unchanged in the [LS10 report](2026-10-23-luna-sol-command-recovery-calibration.md). This reassessment shows that the judge's absolute scores vary; the cause of that variation is not established. LS11's 3.5-point gap uses only its own four-clone judgment, without importing earlier scores.

No additional prompt/environment repair was selected after the LS10 mechanics audit found no demonstrated forced early cutoff. LS11 retained the exact task, seed, runtime, public prompt, CLI and execution limits, and changed the fresh strong arm to high effort. Sol-high authors worked for about 35 and 29 minutes and delivered the integrated implementations described above. LS10's low-effort authors had delivered partial work after about two minutes. This supports the bounded observation that the new high-effort solutions performed better against the fixed weak baseline; it does not isolate a causal effort effect or explain every earlier low-effort failure.

Both predetermined Luna captures were reused verbatim, without quality filtering or score carryover, and their starts count only in history. The fresh strong calls occurred later. Two observations per arm, one related-model judge, different native model defaults and a time-separated baseline do not establish a reliable general model ranking. RPI, separate evaluator qualification, sealed-task/validation requirements and C1 remain separate. This result selects no further provider spend or campaign by itself.

## Consumption and integrity

Exactly two fresh `gpt-6.1-sol` high generations and one fresh `gpt-6.1-sol` high judge were added to 73 historical starts: **3 new / 76 overall**. Complete native inventory found no extra roots, native children, forbidden models or Claude/Fable calls.

| Fresh native session | Cumulative total tokens | Cached input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Sol high 1 | 21,666,691 | 21,270,656 | 95,737 |
| Sol high 2 | 18,160,707 | 17,713,024 | 76,104 |
| Sol high judge | 3,744,251 | 3,554,944 | 8,842 |

Fresh cumulative total: 43,571,649 tokens. These are session-wide native counters, not context-window sizes. Reused Luna receipts retain their original provenance and are not counted again as fresh consumption. The frozen table has no Luna/Sol prices: cost is **unavailable**, not zero, and no monetary or quality/cost Pareto claim follows.

Evidence root: `/home/ollie/sc-evidence/LS11-20261023`.

- Criterion: `/home/ollie/sc-evidence/freeze-functional-sol-high-20261023/criterion.json`, SHA256 `733fa4a9cdde115c0851e6ae90794a595acba3f5db4321ca699cbd4cdef3a904`.
- Judging packet in that freeze root: SHA256 `63e5f4752d4a3a4b9563a8387c1ad92b32cbc58b78417317d78f42566c492edb`; independent packet review `judging-independent-review.json`, SHA256 `44056548ba4c9aeb50b8c5962c401707b4a3cb8106cbb86473c094685c6f0114`.
- Generation integrity: `generation-integrity-review.json`, SHA256 `78e55553a4dc5f3e1ad9656d5532226da422131743129996d2b4d0dbd9e2de91`. All 141 scan hits were explained by public skill literals, own isolated sockets and one historical path printed by a test assertion. Root changed only scan verdicts and retained separate admissions plus the original record/result/patch/completion snapshots.
- Judge integrity: `judgment-integrity-review.json`, SHA256 `b3d97d8aefd7ddb9d94e0003dbfafa936ff8a6badc95111529b5d1ab3be31755`; zero hits, no scan-verdict amendment. Original-result crosswalk: `judgment-pre-adjudication/crosswalk.json`, SHA256 `d9b6758614928fe19a8b4d1f7dec7cd3fa46028c16fef23c44ec05a4e13f0cd2`.
- Original three-call declaration: `budget-declaration-generation.json`, SHA256 `d7d3306c52cb87565e7807842cd0bea2bbafdfa375cb03a0e90e25f564bda183`; final-judge declaration: `budget-declaration-judging.json`, SHA256 `9324dab8038d1391a9718fecd8e8cddbff63ca536e9c0ac417d73516980e738b`.

Accepted apparatus, fixture and native-tool proofs were reused. New accounting/reuse/effort/sequence checks, actual-unit inert checks and independent packet/capture reviews passed. The preserved initial offline binding rejection and its LS11-only correction are recorded in the plan; no provider call was spent on that preparation failure.
