# LS10: Command-Recovery Difficulty Calibration

**Role:** Captured evidence, not a general model ranking or campaign qualification.

**Result:** The commands-only PRR task did not qualify. Both Luna-high solutions scored 4/8 and both Sol-low solutions scored 2/8 under the frozen blind functional rubric. The five selected calls completed; canonical close exited 0 at 73 overall starts. The [LS10 plan](../plans/2026-10-23-functional-calibration-command-recovery-plan.md) preserves the prospective rule and incidents. The [Sol-high successor plan](../plans/2026-10-23-functional-calibration-sol-high-plan.md) owns the next comparison.

## Canonical result

Authority: `/home/ollie/sc-evidence/LS10-20261023/combined-readout.json`, SHA256 `6034b107d509352d76fdac140ec4dbf858cfacb9dcb0c1d489c16e89ae5c3e3e`. Ratings below come from the public harness's clone-ID → original-run joins, not inferred labels or delivery Booleans.

| Original arm/run | Anonymous clone | Functional score /8 | Original delivery value | Author elapsed seconds |
| --- | --- | ---: | --- | ---: |
| Luna high, `direct_task/run-1` | `a5cb93f0` | 4 | true | 2009.99 |
| Luna high, `direct_task/run-2` | `b66a8d01` | 4 | true | 1312.50 |
| Sol low, `sol_low/run-1` | `b278412b` | 2 | false | 132.80 |
| Sol low, `sol_low/run-2` | `f4253f2d` | 2 | false | 123.06 |

The generation models were exactly `gpt-5.6-luna` high and `gpt-6.1-sol` low; one fresh `gpt-6.1-sol` high session judged all four anonymous clones. All four observations remain in the denominator, including both naturally incomplete Sol deliveries. A delivered Boolean is not a functional-quality verdict.

| Frozen predicate | Observed | Met |
| --- | ---: | --- |
| Sol mean − Luna mean >= 2 | −2 | No |
| Sol mean > 3 | 2 | No |
| Sol mean < 5 | 2 | Yes |

Thus `qualified=false`. No hidden tests, reference/control clones, retries or replacement observations were used. This is a new task and four new solutions; it is not a controlled estimate of the effect of reducing LS9's task scope.

## What explains the ratings, and what remains unknown

The blind judge credited Sol's profile validation, value-free shells, visit primitives and frame-loading changes, but found the dependency index, replay runtime and normal execution/resume integration missing. Both authors' public final reports independently acknowledged those unfinished areas. Luna implemented more of the execution and resume paths, but the judge identified material defects in pure-value caching, checkpoint selection/emission, recurrence handling, authority validation and recovery. These are the judge's code-inspection findings; the controller did not independently reproduce every diagnosis or adopt authors' test-success claims as proof.

The separate mechanics review found identical public author prompts after normalizing only the output path, identical task/AGENTS/configuration/grants and the same 14,400-second timeout. Native Sol sessions closed without error in about 132 and 122 seconds, after explicitly writing `false` and describing partial work. No observed timeout, permission/approval denial, context exhaustion or runner-imposed short budget explains their exit. The first-pair collection incident occurred after those native executions ended.

Native model defaults are a real comparability limit: base-instruction hashes and several catalog settings differ by model, while matching each model's frozen catalog entry exactly. Observed coding actions used the same `exec` tool, with no delegation. This does not establish literally identical system prompts/full tool schemas or isolate model weights from native configuration. Raw provider finish/stop reasons and remote internal budgets are not recorded; the review does not prove why Sol stopped early or that low effort alone caused it. Two observations and one related-model judge do not establish a general model ordering or evaluator reliability.

## Preserved execution incidents

The original operator tried canonical intake before scan adjudication and stopped after the first pair with 43/6 pending hits. Original completion records retain `capture:null` and their original errors. Independent reviews justified those hits; root changed only scan verdicts and wrote separate admissions. A reviewed operator revision then ran only the untouched second pair and paused for admission before pooling. Both second-pair captures completed without mechanical errors. No provider call was repeated.

Continuation freezing also detected that the host's declared Codex package had changed from 0.163.0 to 0.164.0. The failed freeze and changed hashes remain recorded. Root retained a complete 0.164.0 package copy, reinstalled the exact official npm 0.163.0 version at the original prefix, and verified all 48 package files plus Node against their frozen hashes before the second pair. All four native headers identify CLI 0.163.0. This restoration does not erase the host-drift incident or establish a broader environment guarantee.

The judge performed 27 read/Git/result-writing actions, with no test execution and zero scan hits. Its original result and scan remained byte-identical through canonical close; no judge verdict amendment was needed.

## Consumption and evidence

Exactly four generations plus one judge were added to 68 historical starts: **5 new / 73 overall**. The inventory found no extra roots, native children, forbidden models or Claude/Fable calls.

| Native session | Cumulative total tokens | Cached input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Luna high 1 | 50,381,229 | 49,772,416 | 111,077 |
| Luna high 2 | 28,016,070 | 27,535,488 | 80,030 |
| Sol low 1 | 414,132 | 368,000 | 5,558 |
| Sol low 2 | 753,298 | 706,688 | 6,945 |
| Sol high judge | 2,470,008 | 2,336,512 | 7,418 |

These are cumulative native usage counters across a session, not context-window sizes. Receipts use complete native transcripts and the frozen price table; Luna/Sol prices remain **unavailable**, not zero. There is no monetary total or quality/cost Pareto claim.

The evidence root is `/home/ollie/sc-evidence/LS10-20261023`. Key records:

- Criterion: `/home/ollie/sc-evidence/freeze-functional-command-recovery-20261023/criterion.json`, SHA256 `e4374721188fe02d76276907cd80a923d3643b1b2cc95a04beef4cc77c26efbc`.
- Judging packet: `judging-admitted-packet.json` in that freeze root, SHA256 `5623ebbb634072b7874c50dd7b8511ed205bf31e9e7c3551c749eeaf30bd3e2f`; declaration `budget-declaration-judging-admitted.json` in the evidence root, SHA256 `4833475d549620b49230670d863173a2621f0dc38b8e32b7f69f9fb705fffbd3`.
- Generation integrity: `pair-1-generation-integrity-review.json` SHA256 `6ec06fb9694ba4111f9a2a660aaecdf63fea5f0b70d29f8d5fecb969f7bf7def`; `pair-2-generation-integrity-review.json` SHA256 `f7062f7b258fb57fc06259d399900092669bad89eada7a96a636395ef606075d`. Their snapshots, public adjudications and four separate admission receipts preserve the originals.
- Mechanics: `author-mechanics-independent-review.json`, SHA256 `7f608bb503e63187f05217af442df76b166251b10d2e7b75fab1ae89866c91f3`.
- Judge integrity: `judgment-integrity-review.json`, SHA256 `a67c0655131bd17522bd4da8c753c5e1d871942cf3a19b286173157336bbc343`; original-result crosswalk `judgment-pre-adjudication/crosswalk.json`, SHA256 `faf381751df5405a16c875335da17af0fe925408390c360bab2b9352e44552c4`.
- Corrected sequencing, original operator/packet ancestry, exact CLI restoration and reviewed continuation commands: `/home/ollie/sc-evidence/preparation/LS10-preparation-verification/continuation-offline-handoff.json`, SHA256 `bd2a5c222ceb8f89ccdaa2f920decb757ce3e4f578e7811056dee6f5e3e6241f`.

RPI, evaluator qualification, the sealed split, validation-package requirements and C1 remain separate. The owner's subsequent Sol-high direction changes the prospective successor study, not these ratings or failed predicates.
