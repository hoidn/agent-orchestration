# PRR Direct Versus ORC Pilot: Closed Incomplete

**Role:** Captured evidence for `PRR-P2-20261024`, closed **INCOMPLETE** on 2026-10-24. The [pilot plan](../plans/2026-10-23-prr-direct-orc-pilot-plan.md) preserves the original protocol, approval and bounded offline follow-up. Preparation and evaluator validation completed; two direct attempts delivered, neither ORC attempt started and no final judge ran. Canonical closure and reporting are complete, but the original comparison is incomplete and supplies no arm-quality result or continuation launch.

## Preparation

Implementation `4a9aaee1`, index correction `119bdeb5` and prompt-visibility clarification `1686abc7` were merged. Final preparation binds source commit `1686abc76ccdaf77bd95f3a7d035bf2a746ada2b` in `/home/ollie/sc-evidence/PRR-P2-20261024/prepared.json`; the final freeze is `/home/ollie/sc-evidence/freeze-prr-direct-orc-20261024`.

Focused verification passed 43 checks: 19 runner, 23 workflow and one pool check. The 23 workflow checks were rerun after the three prompt clarifications. Both initial arm prompts and the repair prompt expose the same already-approved immutable-input restriction, covering 21 protected public-check inputs; task text, evaluator gate and model bindings did not change. Inert orchestrator checks exercised direct execution, check pass/failure, integrity refusal and diagnosis auditing. Verification and independent code review are retained under `/home/ollie/sc-evidence/preparation/PRR-P2-preparation-verification/`, including `prompt-visibility-v2/`.

The initial zero-call preparation was retired with its bytes preserved under `/home/ollie/sc-evidence/preparation/PRR-P2-prelaunch-v1`. Original task freezes, RT8, LS11 scores and the [inconclusive P1 control report](2026-10-23-prr-pilot-control-preflight.md) remain unchanged.

## Evaluator result

Exactly two independent `gpt-6.1-sol` high sessions judged anonymous copies of the untouched feature-absent baseline and first naturally produced LS11 Sol partial solution using the unchanged functional 0–8 rubric. The study-local gate recomputed original ratings through canonical clone-ID joins:

| Repetition | Baseline (/8) | Natural partial (/8) | Gap | Margin-one gate |
| --- | ---: | ---: | ---: | --- |
| Evaluator 1 | 0 | 6 | 6 | PASS |
| Evaluator 2 | 0 | 6 | 6 | PASS |

Canonical admission: `/home/ollie/sc-evidence/PRR-P2-20261024/evaluator-admission.json`, SHA256 `021ec15d51ec1a575625775796a5f829602264d4e6b46e9773927c23698b4a38`. Both complete repetitions pass. Generic harness results omit the `calibration` key; this is a study-local verdict only. The check demonstrates coarse absent-versus-working-partial discrimination, without validating small differences between working implementations or establishing the stopped Sol/Luna ordering.

The first summary refused five unadjudicated scan matches in evaluator 1. Ordinary public adjudication traced all five `pytest` matches to source printed by two read-only native actions; tests had not been executed. The same two judgments were then summarized without rescoring, new calls, changed ratings or changed rules. `/home/ollie/sc-evidence/PRR-P2-20261024/evaluator-failed.json` preserves that closure-readiness incident, not a failed quality margin or excluded observation. The evidence chain is in `evaluator-closure-note.json` and `evaluator-1-scan-adjudication.json` in the same evidence root.

| Evaluator overhead | Normalized USD | Elapsed seconds |
| --- | ---: | ---: |
| Evaluator 1 | 0.492548 | 222.6234 |
| Evaluator 2 | 0.4177204 | 232.5061 |

These costs use the plan's frozen standard short-context list-price convention and retained native receipts; they are not invoices or deployed author costs. Evaluator consumption is complete at two provider starts. The final consumption accounting below includes these as evaluation overhead, separately from direct generation.

## Author stop and incomplete closure

The two fresh `gpt-5.6-luna` high direct attempts, `20261024T092905Z-c6lo2j` and `20261024T092905Z-98i4e4`, delivered terminal `DONE` results. Delivery is not correctness evidence. Before the second author wave, integrity verification refused a change to the bound private `.codex/config.toml`. The original `/home/ollie/sc-evidence/PRR-P2-20261024/authors-incident-1792835485668158445.json` records that mismatch without retry. Neither ICDR attempt started. The exact config delta is an own-candidate project stanza with `trust_level = "trusted"`: native startup added the entry before the first session metadata and about 3.5 seconds before the first author tool action. Harness runtime/shim sources write the initial config without project entries, and no author action writes this config. This identifies startup behavior without attributing an unobserved internal function.

The author scan evidence is preserved. Independent review classified all 144 matches: 141 concern each unit's own private tmux socket, with separate physical backing sockets and creation before reads; three model matches arise from absent custom `inputs.model` metadata causing the scanner's Terra fallback, while actual native evidence identifies approved Luna high. No foreign-session access or delegation bypass was observed, all 21 protected public inputs remained intact and collected final patches equal the original raw captures. Proof: `/home/ollie/sc-evidence/PRR-P2-20261024/direct-generation-scan-independent-review.json`, SHA256 `dabd92b9ea32fb3963efdeeab91b184544dd827f40e8fbc8bc9a83818cd352bc`. This bounded review did not adjudicate, clear, rescan or mutate the original scans, whose verdicts remain unset; the model matches are mechanically non-clearable under the existing API. These integrity findings neither repair the bound-source mismatch nor admit a pool or quality judgment.

Canonical `/home/ollie/sc-evidence/PRR-P2-20261024/pilot-readout.json`, SHA256 `176dc88112e0ed479ec47af195d82b7238d0d06d2f59d3be0138774167882ba1`, records `complete: false`, `comparison: unavailable`: four usable finals and a prepared final judge are unavailable. Two of four author attempts completed; no final judge was prepared or dispatched, and no smaller-denominator comparison was made. All declared attempts remain in the readout, including the two unstarted ORC attempts.

Independent read-only closure verification is retained at `/home/ollie/sc-evidence/PRR-P2-20261024/closure-verification.json`, SHA256 `b5d6578047ddded148569a9ac0cc4c0181046e5a4decbdbe0f178ad155999efd`. It confirms four complete native roots with exactly the allowed models/efforts, no child/model incidents, unchanged evaluator admission, untouched original author scans with unset verdicts, and no prepared final judge.

## Final consumption and limits

| Recorded unit | Standard USD equivalent | Run seconds | Delivery |
| --- | ---: | ---: | --- |
| Direct 1 | 0.68722872 | 1338.7156546115875 | DONE, unjudged |
| Direct 2 | 0.62501804 | 778.884824514389 | DONE, unjudged |
| Both ICDR attempts | 0 | 0 | Not started |
| Direct subtotal | 1.31224676 | 2117.6004791259766 | Two delivered attempts |
| Evaluator overhead | 0.9102684 | 455.1295795440674 | Two judgments |
| Study total | 2.22251516 | 2572.730058670044 | Four physical starts |

Prices are normalized standard short-context list-price equivalents under the frozen convention, not invoices. Seconds are summed run durations, **not elapsed study timeline**; concurrent sessions overlap. Zero ICDR consumption records that no ORC generation occurred and supports no efficiency comparison.

The study used exactly **four new/80 overall physical starts** after 76 historical starts. Seven authorized slots were unused; the closed no-retry protocol supplies no continuation or replacement launch. No Claude, Fable, native children, retries or final quality-judge call were added. There are no author quality scores, arm means, Pareto result or ORC-versus-direct quality/cost claim.

The prospective offline correction pre-seeds the own-directory trust entry before freeze and binds the declared model through typed scanner inputs, retaining full-file hash verification. Handoff `/home/ollie/sc-evidence/preparation/PRR-P2-author-incident-correction/handoff.json`, SHA256 `61d9d8fd02c1d8126bb2ecc828b96f58deb13266e021eaef3aa89159cd2b8c27`, records 46 collected tests, three final trust regressions passing, and two focused render/inert ORC smoke checks passing; the inert ORC path used three fake calls. Forty related checks passed before the final test-only strengthening of tamper rejection, and the three focused trust cases passed after it; production code did not change between those checks. This is offline evidence with zero real provider calls, not live validation. Frozen packets, original incident/scans and historical results remain unchanged; the correction authorizes no continuation or provider spend.

The owner-approved transfer of LS11 difficulty evidence remains limited to this corrected-fixture pilot. It is an explicit assumption, not new difficulty proof, C1/V2 qualification or campaign admission. The evaluator PASS establishes only coarse absent-versus-working-partial discrimination. The incomplete original comparison supplies no evidence of orchestration benefit.
