# PRR Direct Versus ORC Pilot: Execution Checkpoint

**Role:** Captured evidence for `PRR-P2-20261024`, 2026-10-24. The [pilot plan](../plans/2026-10-23-prr-direct-orc-pilot-plan.md) owns protocol, approval and remaining gates. This report records completed preparation and evaluator validation; the pilot is **RUNNING**, with no comparative outcome yet. It is not a launch recipe or new qualification authority.

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

These costs use the plan's frozen standard short-context list-price convention and retained native receipts; they are not invoices or deployed author costs. Evaluator consumption is complete at two provider starts. Study consumption remains open while authors run; these figures are not final pilot or study totals.

## Pilot checkpoint and limits

The authors declaration is `/home/ollie/sc-evidence/PRR-P2-20261024/authors-declaration.json`. At this checkpoint, the two fresh `gpt-5.6-luna` high direct attempts are running as `20261024T092905Z-c6lo2j` and `20261024T092905Z-98i4e4`. The two ICDR attempts follow in the second wave, with at most two authors active. Four-final integrity review, the single combined blind judgment and comparative closure remain pending. No final author score, arm mean, cost comparison, Pareto result or overall consumption total is reported.

The authorization remains at most eleven new physical starts/87 overall after 76 historical starts, without retries, replacements, Claude, Fable or native children. Every attempt and its actual consumption must remain in closure; missing finals preclude the final quality judge and a smaller-denominator comparison.

The owner-approved transfer of LS11 difficulty evidence applies only to this corrected-fixture pilot. It is an explicit assumption, not new difficulty proof, C1/V2 qualification or campaign admission. Even after complete closure, two runs per arm and unequal possible compute support only a descriptive comparison; any improvement cannot be attributed to orchestration alone.
