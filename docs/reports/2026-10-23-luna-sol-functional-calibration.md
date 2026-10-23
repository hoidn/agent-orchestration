# Luna high / Sol low functional calibration: both tasks exceed the target

Role: captured LS5 methods, results and limitations. This report grants no new
spend and is not a launch recipe. The
[functional calibration plan](../plans/2026-10-22-functional-calibration-plan.md)
owns current selection; its frozen criterion and the canonical clone-id joins
own these measurements. Earlier reports and frozen inputs remain unchanged.

**The two-task set is not calibrated.** Both tasks meet the two-point mean-gap
rule, but the Sol-low mean is 6 on each, above the strict target interval
`3 < mean < 5`. Both receive `too_easy`; `two_task_qualification` is false.
LS5 execution and canonical closure completed successfully: three new physical
calls plus forty historical starts reached the declared total cap of 43.

## Method and recovery selection

For each of `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR),
two `direct_task` observations use exact `gpt-5.6-luna` high and two `sol_low`
observations use exact `gpt-6.1-sol` low. Both use `control/direct_task.orc`,
identical task packages, seeded bases, tools and a 14,400-second limit. Stronger
and weaker are treatment hypotheses; the ordering was not assumed.

One exact `gpt-6.1-sol` high blind judge per task rated four anonymous clones
in one batch, with a 3,600-second limit. `score_functional.orc` assigns one
functional `quality` score S0–S8: working required behavior through normal entry
points, without independent points for organization, scaffolding or tidy
incomplete code. Judges inspect code without executing tests or using archived
test results. No reference, artificial control, deliberate defect or hidden-test
run enters this pilot. Both tasks must pass all three frozen predicates:

- Sol mean minus Luna mean ≥2;
- Sol mean >3;
- Sol mean <5.

Seven generation observations were carried with their original bytes and
source-specific receipts; one Sol PRR observation was fresh. The lineage is:

| Task / arm | Original observation sources |
| --- | --- |
| RPI Luna high, two observations | LS1 |
| RPI Sol low, two observations | LS3 |
| PRR Luna high, two observations | LS4 |
| PRR Sol low, two observations | LS5 sample 1; LS4 sample 2 |

Earlier detector interruptions, the LS3 host-storage failure and all original
spend remain historical evidence. LS4 Sol PRR sample 1 ended with native
`server_overloaded`. Its original failed terminal, raw patch and complete receipt
pass mechanical natural intake, but the external truncation confounds difficulty.
It remains in LS4 accounting and received no quality score. LS5 prospectively
replaced only that slot, retaining every valid nonexternally aborted observation,
before any scores were admitted. Selection therefore follows the external abort,
not implementation quality. Legitimate failed deliveries remain eligible under
the unchanged terminal-single-call intake; all eight retained deliveries here
have completed outcomes.

The owner removed the routine ask-before-spend rule. The coordinator declared
the bounded LS5 continuation and bound its criterion/packets to that policy;
this does not claim a numeric owner approval of cap 43 or alter LS4's cap-42
approval. One physical call per fresh unit, no automatic retry and sequential
judges remained enforced.

## Canonical results

`E/combined-readout.json` SHA256 is
`2ba7325deb023dd254071348efef6bb3baee7d44738ab1a9f1bed0929e503486`.
Scores below come from its original clone/run joins, with all four observations
per task present and neither judge excluded.

| Task | Luna high scores / mean | Sol low scores / mean | Gap ≥2 | Sol >3 | Sol <5 | Result |
| --- | --- | --- | --- | --- | --- | --- |
| RPI | 4, 4 / 4 | 6, 6 / 6 | 2: pass | Pass | Fail | `too_easy` |
| PRR | 3, 4 / 3.5 | 6, 6 / 6 | 2.5: pass | Pass | Fail | `too_easy` |

All scores are out of eight. This pilot observes the declared separation on both
tasks, but fails the complete task-difficulty qualification rule. It does not
qualify the task family or the quality evaluator, establish general model
superiority, or open a workflow/campaign quality comparison or quality–cost
Pareto claim. Separate evaluator-control qualification remains required by the
[measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md).

These are new functional-rubric scores. The
[LH report](2026-10-22-luna-effort-task-difficulty-calibration.md) retains its
original additive-component scores and failures; totals across the two rubrics
are not numerically comparable and no historical observation was rescored.

The owner's instruction to iterate until the target is met points next to
naturally harder tasks, keeping these exact model roles, functional rubric and
three thresholds. A concrete revised task/seed design, prospective freeze and
bounded iteration budget are not fixed by this result. No new numeric cap or
campaign selection follows from this report.

## Frozen lineage and integrity

Evidence (`E`) is `/home/ollie/sc-evidence/LS5-20261023`; freeze (`F`) is
`/home/ollie/sc-evidence/freeze-functional-capacity-recovery-20261023`.
Runtime `/home/ollie/sc-runtime-functional-calibration` is pinned to commit
`b2d217acfbead475080847f16c82b1fae901aec5`.

| Artifact | SHA256 |
| --- | --- |
| `F/criterion.json` | `bd3a82099bb9645a1beab9f5efeb94ebbb6d483d7c9385528c5f76ffe46cd3ae` |
| `F/carryover.json` | `0a9b1e101a5d9ecf6b00e12679d851bb5737689a84f9525329628acd967e2871` |
| `F/generation-packet.json` | `874aa0aa4510ea475750f2ca531ce235c47d6a0f7b86d80a28144df19798a952` |
| `F/judging-packet.json` | `f9ecf9db12e0f51052910cf91b1f8437666dd7aebb835aa37315457cb0621b25` |
| `E/budget-declaration-generation.json` | `057699a5bfcd6feab6ca28d4f5ce8dcca4133672a2f2803f608c8ee18d932dfe` |
| `E/budget-declaration-judging.json` | `d84375db735d5bc6fb465e951305a1b6365114df9d77e9e6ddcb7cb6ea8c4745` |
| LS4 `incident-accounting.json` | `6109000ff9f1f223d7dd8f2b58ddf2ca6953819ad92d10a20c639137d46ef976` |
| `E/rpi-judgment-integrity-review.json` | `760b434667fde20fa9ae2d2396d11fc8bbf690b3d7abc7668d5fc1055cf3bc30` |
| `E/rpi-judgment-adjudication.json` | `21bd959133d510eedf8965b8a1f2fa986ec824e5a9454eed9e28c3037bb94817` |
| `E/prr-judgment-integrity-review.json` | `6d000a8daf575e8101f0927cac962ca32d86fac1f4c86611bf89686e7960a559` |
| `E/prr-judgment-adjudication.json` | `10e92ea76f385fc54559ddbca1b30bf5c45fe8947a0c0979a24d8c4ca5bb14a4` |
| `E/closure-independent-review.json` | `12741dc301f195526eb43c00beb17e163cfbb4c0c3f94028f82c19fd8c730ad1` |

Both completed judge-integrity reviews passed. Their audits cover 25 RPI and
35 PRR structured actions, with 29 and 33 original scan hits. Public adjudication
cleared only scan verdicts, preserving original hits, ratings, delivery artifacts
and pre-adjudication snapshots. Honest Git review baselines exclude the protected
archive before each exact raw patch is applied; two actual Bubblewrap/fake-CLI
checks verified all eight clone views before judging. Canonical close exited zero.
The independent closure audit passed 67 reference checks, all eight original
clone-id ratings/reasons and raw patch/index joins, three scan crosswalks and
all ten receipts. It independently confirmed the failed threshold arithmetic
without replacing a score or rerunning a provider.
No Claude/Fable session, native child, extra root or spawn action was observed in
the LS5 inventory; no hidden tests were executed. These absence findings concern
retained native metadata and structured inputs, not universal prevention of
arbitrary direct APIs or deliberate bypasses.

## Deployed consumption and limits

The readout retains three fresh and seven carried positive, complete single-call
receipts. The following sums their charge-token categories; cache-write tokens
are zero. These ten represented calls cover eight generation observations and
two judges. Seven are already within the forty historical starts and must not be
added again to LS5's three new calls. Generation times are original per-sample
wall-clock seconds, not native receipt duration.

| Task / role | Represented calls | Uncached input | Cache read | Output | Generation seconds, samples 1 / 2 |
| --- | --- | --- | --- | --- | --- |
| RPI Luna high | 2 | 866,537 | 64,481,792 | 173,453 | 891.71 / 920.30 |
| RPI Sol low | 2 | 402,652 | 25,644,800 | 123,204 | 1,885.28 / 1,877.70 |
| RPI Sol high judge | 1 | 131,175 | 2,056,320 | 8,631 | Not a generation |
| PRR Luna high | 2 | 740,800 | 58,842,880 | 148,858 | 809.03 / 1,376.49 |
| PRR Sol low | 2 | 392,185 | 25,728,384 | 117,218 | 1,787.67 / 2,496.53 |
| PRR Sol high judge | 1 | 166,788 | 3,598,976 | 10,736 | Not a generation |

Luna and Sol prices are unavailable in the frozen price table. The known-price
subtotal of zero is not zero expenditure; full monetary cost is **unavailable**.
No model-aware deployed-cost dominance is established.

Two observations per arm/task and one judge per task are a pilot, not a reliability
estimate. Sol-high judging shares the Sol-low model family; anonymous provenance
does not remove that potential bias. Historical host-interrupted native logs have
incomplete NUL-tailed evidence, and nine historical `/tmp` verification artifacts
are missing after the incident/reboots. Their exact absence inventory and original
manifests remain preserved; surviving hashes do not restore the missing bytes or
prove lasting host-storage health.
