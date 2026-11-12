# Structural search measurement calibration ledger

## Preparation — 2026-10-19

The owner requested integration followed by experiment execution. Offline
preparation and Step A are selected: owner approval is recorded in main commit
`ac58e0bacb786c7a53692a7fb3981d801c9a9733` (8 calls, cap 10).
No new live call has launched yet; A′, B, B2 and C retain separate budget gates.
The implementation plan is
`docs/plans/2026-10-19-orc-structural-search-measurement-plan.md`.

| Decision or evidence | Record |
| --- | --- |
| Integrate module delivery before calibration preparation | `main` advanced to `62e3776fd68bfebeadace79f28627c16ef9d6879`; existing local changes preserved |
| Verify merged code | 977 tests passed in 154.01 seconds at `9adcf56c`; exit 0; `/tmp/structural-merge-suite.log` |
| Adapt the calibration plan to current interfaces | `1710e99b306ca565285ffaa5d399a8b05820e33e`; independent plan review approved Tasks 1–5 |
| Preserve historical evidence | Existing criteria, provider bindings and `score.orc` stay unchanged; use a new family amendment and reference rubric |
| Keep qualification scopes distinct | Generic comparison calibration uses the new rubric; structural V1 remains closed to it; V2 integration awaits a later selected study |
| Reuse receipt and pricing code | Read-only historical audit found complete native receipts for both two-call judge runs; details in `preparation/historical-receipt-audit.json`; no new calls |
| Verify official rates before freezing | Four model rates and official source URLs in `preparation/official-prices-2026-10-19.json`; standard list-price equivalents, not billed spend |
| Reuse applicable existing patches | RPI: 11 of 20; PRR: 19 of 19. Applicable hashes are all distinct within each task; exact paths, hashes, seeded commits and refusal reasons in `preparation/applicable-fillers.json` |
| Promote runnable visible checks | RPI also needs the historical context helper already bundled with its hidden tests; PRR's base already supplies it. Seeded check commands retain their executable and options, with the lifecycle file as the first test target |
| Account for preparation errors | Initial target placement and missing RPI helper are setup failures, not partial/mutant control attempts; Task 3 manifest retains them |
| Keep hidden tests secondary | Construction diagnostics only; judge calibration uses the frozen rubric and P1/P2/P3/spread rules |
| Prohibit Fable | All experiment stages retain the model guard and native-session scan |

The repository writer is implementing Tasks 1–2. Control construction uses
separate task copies under `preparation/task3/`. Runtime, controls, fillers,
criteria and price table are not yet frozen for a live run.

Task 1 was committed at `21d35fd3c0f609e76527190537e8a28f713a1057`.
Independent spec review approved it. The scripted suite, including both scoring
workflows, passed 185 tests in 76.60 seconds. A necessary V1 dispatch correction
rejects a selected reference rubric even if a historical qualification proof is
otherwise valid; its qualification/scoring selector passed 105 tests in
8.69 seconds. Code-quality review and Task 2 remain in progress.

Paid sequence remains A → optional A′ → B → B2 → C, with separate approvals.
The planned count is 32 calls without A′; the maximum across the declared caps
is 50. Step A is 8 judge calls, cap 10. No quality comparison is authorized by
this ledger.

## Owner model cap — 2026-10-19

The owner requires only mid/low tier models (at most Sonnet and Terra) for every
experimental role, including judges, reviewers and nested agents. No live call
has been launched. The new measurement selects `claude-sonnet-5-5` and
`gpt-5.6-terra`; previous proposed Opus/Sol bindings are superseded before freeze.
Historical results, provider files and frozen criteria remain evidence.

Local read-only CLI verification: `codex --disable multi_agent --disable
multi_agent_v2 --disable multi_agent_v2_dynamic_tools features list` reports
all three features false. This supports disabling native delegation in the
experiment guard; it is not yet evidence that the guard implements the restriction.
Guarded PATH prevention and native-session model audits still require implementation
and scripted verification. Absolute CLI paths/direct APIs remain a disclosed boundary.

Task 1 reference integrity fix `b864724f` passed independent review. Task 2 was
committed at `f8d0ce7b196cdfb47013477da0968f5cf1d02bd2`: 267 scripted tests passed
in 23.52 s, 24 new tests collected. Independent Task 2 review is in progress.

Original partial construction limits are exhausted for both tasks, with no
in-band control. RPI has a valid first mutant (73/111 nodes; visible check passes).
PRR exhausted its three mutant attempts (116/129, 111/129, 106/129), none in band.
Exact records are in preparation/task3/manifest.json. These outcomes do not
constitute calibration success. No extra construction attempt is authorized.
The control disposition is under design review before any freeze or judge call.

## Control-construction amendment — before judge data

The original bounded construction protocol is closed as unsuccessful: neither
task produced an in-band partial, and PRR did not produce an in-band mutant.
All 12 attempts and hidden-node fractions remain recorded. No additional
construction attempt is selected. This revision occurs after observing those
fractions and before any judge call or quality outcome.

Accepted design recommendation: replace hidden-fraction selection bands with
semantic adequacy for existing candidates only. Review candidates in original
construction order and select the first satisfying the following obligations.
A partial must preserve one required behavior and omit another, with concrete
executable evidence upstream passes the omitted behavior and the partial fails,
and that the partial retains the stated implemented behavior. A mutant must
contain one behavior-breaking edit affecting an explicit requirement, retain
at least 95% of upstream added lines, and have a functional counterexample that
passes upstream and fails in the mutant. Import, collection and infrastructure
errors do not establish adequacy. Reuse recorded exact-node/JUnit evidence when
it suffices; extra checks may verify unchanged candidates but may not modify them.

Independent review must confirm requirement/edit/counterexample lineage before
freeze. If no existing candidate qualifies, stop that task. Hidden fractions
remain descriptive, including failures against the superseded bands. P1/P2/P3,
spread, complete declared denominator, family qualification, gate 3 and proposed
call budgets are unchanged. This is a changed construction protocol, not success
under the original protocol. The eventual spend packet must disclose the change.
Authority: AGENTS.md permits recording other offline experiment decisions; this
amendment does not grant provider spend.

Task 2 independently passed spec and code-quality reviews at f8d0ce7b. Task 4 reuses existing native-receipt and pricing APIs; historical native coverage audit plus the prior full 977-test suite cover receipt normalization. A focused offline assert check prices the two selected model receipts together correctly and preserves unavailable for incomplete/unknown-model coverage; see preparation/capped-model-pricing-check.json. No duplicate metering API or forced implementation change is needed.

Independent coordinator review APPROVED existing control semantic adequacy for package integration. Proof hash eae7669a73755809e3e096b44ab8ed82008e364d98645a1716a26aa5714345d5; exact checks in preparation/task3/semantic-review.json. Selected first partials omit calls.py (RPI) and executor.py (PRR); selected first mutants add a single early return in scope audit and required boundary closure respectively. This does not claim judge calibration. Final external package hashes: RPI b2c9cfcae5b8e8b91ac115af518f90c092b7fbd245d253d70dea0bb001879136; PRR 08696557c2de2d8d2e521b7e9fed8c05f365c058df43bf5813910ad6a4645278. Seeds remain unchanged.

Step C preliminary source copy prepared outside the repository at preparation/measure-free-seed/: only the diagnosis model changes from Sol6 to Terra; the original seed and provider bytes remain unchanged. Public compile accepted build 1d42f62749828355, program digest sha256:f44a24b3722383e967e78151b271c61f182c7763cb9aafc3d601c87ded0a59e7. Compiled policies are two Sonnet-medium sites and one Terra-high site. This is compile evidence only; final-runtime scripted four-evaluation smoke and criterion freeze remain pending.

Historical rubric compatibility correction 639d7fae6bf005c384092ce234ad568e8aba8a31: the original phase2 criterion contains a descriptive string in rubric. A shared normalizer now treats historical strings/missing fields as score.orc metadata and mappings as explicit selectors, with invalid types refused. Coordinator reviewed the complete production diff and regression tests; V1 still refuses reference selection. Fresh scoped suite including Phase 2, qualification and both public scoring workflows passed 176 tests in 28.86 s; 11 new tests collected. No frozen evidence was changed. Guard review separately found and queued two bounded corrections (app-server dispatch and comma-separated main model IDs); final broad integration remains pending.

## Model-cap verification closed — before final integration

Guard corrections committed at `9b8785637776063f22fac77379153143fee2107b`.
Independent quality re-review approved the app-server refusal and exact primary
model validation; 14 targeted tests passed in 0.40 s and Bash syntax passed.
Coordinator inspected the correction diff. Author evidence: 82 narrow checks,
2 public scripted smoke checks, and 99 affected cases verified across the suite
and its corrected final selector. Final full integration remains pending Task 3.
There were no live provider calls.

Task 4 reuses existing native-receipt discovery and `pricing.cost`; the historical
receipt audit and `preparation/capped-model-pricing-check.json` establish the
reporting inputs without a duplicate API. The selected Sonnet/Terra synthetic
mixed receipt prices at USD 0.000899; incomplete and unknown-model coverage stays
`unavailable`. These are apparatus checks, not predicted or actual live spend.

## Existing Step-A approval discovered during integration

Main advanced independently to `ac58e0bacb786c7a53692a7fb3981d801c9a9733`.
Its only delta records the owner's Step-A approval (8 calls, cap 10), with
A′/B/B2/C separately gated. The coordinator read the exact committed change and
will preserve it in the merge. Earlier no-approval statements describe the
pre-discovery preparation state and are superseded for A only. No repeat
approval is required. Offline verification, exact I/F freeze, the current
Sonnet/Terra cap and disclosed semantic control amendment still precede launch.
Latest local quota observation is retained in preparation/quota-observation.json;
it reports 26% remaining in the weekly window at 2026-10-20T04:54:24.930Z.

## Controller/package verification

Task 3 commits `2f495d0a`/`3655c6f4` passed independent code review.
Root ran the implemented controller on a clean detached checkout for all six
base/upstream/stub cases and all 30 applicable retained fillers. Both task bases
and stubs failed; both upstream anchors passed. Every retained filler failed
the promoted check: RPI 11/11, PRR 19/19. These are historical patches produced
without the promoted check, so the figures are upper-bound estimates, not the
live Step-C gate. No patch-application or controller-report failure was counted.
The production pool.applicable helper reproduced the exact 11/20 and 19/19
applicability lists. Full results and per-patch identities are in
`preparation/controller-checks/results.json`; command exit0.

Purpose=calibration now skips new hidden-test executions in summaries; controls'
existing exact-node diagnostics remain descriptive. Normal/historical summary
behavior is unchanged. This prospective decision was made before I/F or any new
judge call, consistent with the owner's optional/secondary hidden-test policy.

Step-C offline CLI smoke: four completed evaluations, zero episodes, 12 scripted
CLI calls, three per evaluation, exact Sonnet-medium/Terra-high bindings and
matching mask/holdout roots. Run04 and the separate corrected argv-parser check
are retained under `preparation/taskc-smoke/`; all earlier setup attempts remain.
No quality evidence or real provider calls were produced.

## Final broad implementation verification

The corrected full suite at `3ce4ea72` passed **1124 tests in 228.63 s**, exit0. Command: `python -m pytest -q -n 16 --dist=worksteal tests/experiments/ tests/test_workflow_evaluated_compare_score.py`. The earlier full run had two stale anchor-inventory test expectations (fixed without touching historical criteria) and one native quiescence failure that passed both isolated and in this complete rerun. Evidence: `preparation/final-verification.json`. No real provider calls. Main concurrently added cumulative campaign design `a363c2ae`; its documentation-only merge remains to be incorporated into final I. Independent design review confirmed no change to the approved A contract.

Implementation I is frozen at `25ca21e1476f5c060feb04a838e1a6cbf844c63b`, before criterion generation. It includes the reviewed documentation merge from main; code is identical to the 1124-test verified `3ce4ea72`. Runtime `/home/ollie/sc-runtime` is detached at I.

Final-I scripted verification passed: `score_ref.orc` public compile/run/resume and invalid-rating rejection, 3 passed in17.09s with a scripted Sonnet binding; external C smoke completed four evaluations and exactly12 scripted calls with all17 mask/binding/lineage assertions true. Final C evidence: `preparation/taskc-smoke/run-final-I/verification.json`. Frozen identity/config/model/price checks passed (`preparation/freeze-field-check.json`); no new criteria exist in I. No live provider calls yet.

## Verified freeze and approved Step-A packet

Freeze F `cc5464acc0aa7bebe07964f073886bfda09114ba` copies exactly the independently reviewed external family and judge criteria. I remains `25ca21e1476f5c060feb04a838e1a6cbf844c63b`; runtime stays detached at I. Independent verdict `preparation/freeze-review.json` is PASS. Exact identities are in `criterion.sha256`. Subsequent main commits added only proposed/unselected C1 pilot documentation; they do not change runtime I or this calibration.

Step A is the already approved 8-call experiment, cap10 (`ac58e0ba`), with exact Sonnet/Terra high judges and two batches per task. Control construction uses the disclosed semantic amendment after the original fraction bands failed, before any judge data; fractions stay descriptive, no new hidden tests run. There are11/19 applicable unique retained fillers; A selects10/task,5/batch by frozen seed20261019. P1/P2/P3/spread and full judge×batch denominator decide success. Prices are frozen standard list equivalents, not billed spend. Latest local quota record `preparation/quota-before-A.json` reports21% remaining and credit availability; no fresh server request. Overall prospective maximum50 calls includes separately gated A′/B/B2/C, none of which is approved here. No real calls have launched at this packet freeze.

Step A launched after main integration and all offline gates. Operator: `preparation/run_A.py`, private tmux `calibration-A`; periodic state watcher `calibration-watch` records `A/status.json`. First actual run ID `20261020T052257Z-b3ovah` (RPI/Sonnet). Native metadata confirms Sonnet; two batch calls are now initiated. Every judge has cap2 for the initial8; no automatic replacement/rerun or model substitution. Explicit extra masks hide main/runtime/operator evidence, prior study roots, pool records and other judges; exact masks and commands are in `A/*.launch.json`. Full membership/source hashes recorded independently of ratings in `A/pool-membership.json`.

Maintained preparation status commit `a75f67cb` integrated into main during A. Original21 local tracked edits preserved; the index edit was checked by its exact added/deleted lines because its surrounding roadmap context intentionally changed. Temporary path-only stash restored and dropped; index remains clean. Runtime I and frozen criteria are unchanged.

RPI A completed with4 real CLI calls. Both judge scans manually cleared with provenance: Sonnet read only its own persisted git-diff output; Terra printed a Markdown row containing pytest, without running tests. All20 clones unchanged. Frozen summarize join returned calibrationFAIL: every P1/P2/P3 pair passes, but Terra mutant0vs4 gives spread4>2. Sonnet controls stable8/0/6/5; Terra upstream/stub/partial stable8/0/5. Both Terra reasons identify the early return; they disagree about credit for retained behavior. Full36 reasons read and equality claims counted in `A/resume-projection-integrity-reason-audit.json`. Complete the already planned PRR A calls; do not change any frozen rule or launch B.

Step A CLOSED: operator exit0, all four runs terminal completed, exactly8calls, no replacements/refusals. Both judge scans per task manually adjudicated; all20clones/task verified after each judge. Final PRR Terra43 scanner hits are printed source (3plan excerpts,40AGENTS test guidance), no test invocations;54native exec commands audited. PRR calibrationPASS (all P1/P2/P3, maximumspread1); RPI calibrationFAIL (Terra mutantspread4>2), so combinedAFAIL. All72reasons read, equality assertion totalsSonnet4/Terra2 descriptiveonly. All8receipts complete; native models onlySonnet5.5/Terra; no newhidden tests. Combined readout A/combined-readout.json: list-priceequivalentUSD7.8836138, elapsed2088.6876seconds. No ORC effectiveness conclusion. A-prime preparation uses predeclared alternativeb with same judges/rules/controls/fillers, no disclosedreference, newcriterionandruntime; separatelyowner-gated8calls/cap10. Remainingstagecaps40, realizedAplusworstremaining48; unusedAreserve2nottransferred.

A-prime workflow eb2b0636 independently reviewed; focused92pass, reviewer4pass. Broadrerun1128passed227.79seconds; originaltimingfailure and narrowrerun preserved under preparation/a2-verification. No production/test weakening.

## Owner steering after completed Step A (2026-10-19, America/Los_Angeles)

No further Claude experiment calls today. All eight Step A calls had completed before this instruction; no experiment provider is active. A′ retains its predeclared Sonnet/Terra pair and may be prepared offline, but cannot launch today and still needs separate owner approval. Do not silently replace Sonnet, switch to a one-judge protocol, or launch B while calibration is failed.

Read main through 389fc9da: cumulative campaigns design, Stage C1 pilot plan, roadmap Phase 2/2b and decision points, boundaries invariant 4/change note, and superseded Phase 2 plan. C1 consumes stable measurement interfaces: pool.rubric/write_pool; scoring.fillers_per_batch/read_pool with V1 qualification proof and clone-ID join; metering.receipts/pricing.cost with frozen prices; capped seed copies and unchanged historical seeds. No campaign/store/reservoir or qualification V2 code is selected here. Rung 1 remains sealed, absent from judge pools and mutator work; a qualified validation package, such as rung 3 after its third sample, and split amendments are separately owner-gated C1 work.

Coordination conflict, retained rather than silently resolved: C1 Task 6 currently admits V2 only with the reference rubric and names the original judge-calibration file, whereas measurement's predeclared A′ removes the reference and creates successor criterion identities. If A′ passes, C1 must explicitly consume that accepted measure under a coordinated revision; this measurement task neither edits C1 nor implements V2. Routing discrepancy also retained: cumulative Staging And Gates is the single authoritative ten-item list and names Step A, while C1 Task 8 calls its gate a union/items 1–8 and allows approved A′. These words need coordinator alignment; they grant no spend or workaround here. Protected cumulative design/C1 plan/roadmap Phase 2/boundaries text is not edited by this task; only existing measurement-status routing is updated.

## A′ offline packet complete; no launch selected

I_A2 `49cd27e6d3c059092e38fcf9836aa4bc50ae8b52` is detached at `/home/ollie/sc-runtime-a2`; F2 `f58d70dba4ce2e857e9e5951f76821a20d4efc22` commits the exact independently reviewed judge/family bytes. New judge criterion SHA `6b0c4610ff276fa81177107d9fab54652ead0b3d83b4d564b2999d216370fd10`; family SHA `9296362093716b66349d817ccd83b95192fd9450720a726f0e8fe80b56c1fbcb`. Review SHA `66a152d2db8c25b141dd23e1b106897129c9c3c33ff9ffb18bf707ba4900cf25`. C metadata/config are rebound to I_A2 with unchanged capped seed bytes and reused valid scripted C smoke; no new C calls. Public absolute scoring CLI smoke on I_A2 passed 3 tests in 15.84 s using fake providers only. Original I/F/A remain unchanged.

A2 pools prepared after F2 integration, four dry-runs passed, zero provider calls and no live run headers. Each task has 18 fresh-ID clones in two nine-clone batches: four blind controls and the exact five A fillers per batch, no reference. Root verified exact patch membership, model/runtime/criterion/input bindings and all 36 clone trees. Evidence `/home/ollie/sc-evidence/A2/pool-verification.json`, SHA `509649034a217f6417168cfd9af8db1c649e02ed21385c193f3e1eb1a4cf1e4f`. This is preparation, not a calibration result or spend approval; the 2026-10-19 no-Claude directive prevents launch today. Separate approval remains mandatory on any later date.

Main integrated through 112c8068 with all 21 tracked user edits and 6807 untracked paths preserved; index clean. Concurrent C1 design round 3 at3f8d6ac8 is documentation only and does not repin I_A2. Its extra-package amends_6/fresh-qualification direction is outside this measurement's amends_5 scope; owner handoff wording about a third historical rung-3 sample is retained as a coordination item, not silently used to qualify anything.

Final integration: main and measurement branch at f7d6534b34956ed177b25c5b785c14822616b672. Final owned worktree clean; main index clean and21tracked useredits/6807untrackedpaths preserved (preparation/final-main-preservation.json). Both detached runtimes and all original/new criterion hashes reverified. A remains8completedcalls, A2zero calls. No further experimental spend, no push, no automatic future launch. Fullcode verification1128passed; finalpublicCLI3passed;4pooldryruns and36cloneintegrity checks passed. Later stages remain separatelyowner-gated and Claude remains prohibited on2026-10-19.

## 2026-10-20 — A′ preparation resumed after code-first integration

The owner instructed “execute the calibration and experiments” after C1 offline Tasks 1–7 were implemented, independently reviewed, checked and integrated in main at `a92eeeeaf12da90c7e136a1c6db8324b746fc8d2`. Resume the accepted single-Terra A′ design under the existing conditional authorization (4 planned calls, cap 10, within the earlier 8/cap-10 envelope). No Claude or Fable experiment call is permitted, without an assumed expiry. This is the same sole predeclared alternative (b), not A3. No provider call has run at this entry.

Prospective packet: new `E/freeze-at`, new `P/<task>/AT`; I_A2 remains detached `49cd27e6d3c059092e38fcf9836aa4bc50ae8b52`. Operator implementation/review must prove empty Claude allowlists at launch/resume, non-clearable actual-Claude metadata violations and positive per-call native Terra model evidence. Historical A/A2/freeze files have 220 file hashes captured in `E/preparation/AT-historical-before.json`. Original F2 remains unexecuted.

Capacity: `E/preparation/quota-before-AT.json` records the latest local native event (2026-10-20T17:11:39.099Z), weekly used 41%; this is not a fresh server quota query. Fresh `codex features list` baseline has multi_agent=true; the frozen guard-equivalent explicit `--disable` flags make all three native multiagent features false, recorded in `E/preparation/AT-native-agent-features.json`. No global settings were changed.

## 2026-10-20 — AT frozen, verified and authorized launch

Git freeze `997374d8`; criterion SHA `2963e39670c32962ac226fa4f8646029de5815f29d03eb1c0cea5bf66362de60`; runtime I_A2 `49cd27e6d3c059092e38fcf9836aa4bc50ae8b52`. Independent `E/AT/prelaunch-review.json` approves operator and both actual pools/dry runs: 36 intact fresh-ID clones, 2×9 per task, one Terra-high judge, four declared pairs, zero references. Root mask-mount smoke passes for both121-root masks with `/bin/true`, zero providers. Ten selfchecks and frozen script hashes passed; 220 historical file hashes unchanged.

The existing no-Claude conditional authority funds four planned calls, cap10. `operator_audit.per_run_call_cap=2` is the initial per-task allocation; the frozen, independently reviewed operator permits explicit same-run mechanical recovery of pending effects within globalcap10, never a rerating of committed observations. Zero-pending finalization grants no dispatch allowance. This interpretation was reviewed before launch and changes no criterion bytes, scientific rule or budget. Remaining worst-case is realized A8 plus caps10+14+4+12=48; no A reserve is transferred.

Launch root exclusively: `python E/preparation/run_AT.py`, tmux `sc-at`; readonly periodic monitor `monitor_AT.py`, tmux `sc-at-monitor`. Both Claude allowlists are explicitly empty at every launch/resume. Positive native Terra receipt proof is required before more work and closure. Frozen-harness join failure or excluded sole judge is failure/incomplete, never a selective rerun.

## 2026-10-20 — AT mechanical parser recovery

RPI run `20261020T173518Z-q3mlyj` completed both batches (two native Terra calls, USD1.8673224 list equivalent). Frozen operator exit1 occurred afterward because its effect-identity parser omitted `/ else /`; no score or candidate is changed. Original scripts, criterion and failure logs remain intact. Independent review approved the minimal external `preparation/recovery_AT.py` adapter SHA `a3a3716c254ef6251747ce231e93abeb0aa36eb67d8039c5329331ee1e078aa9`, bound by `AT/operator-correction.json`. Root public live-pool verification passes, scanner zero hits and both native receipts complete. Missing completion event is explicitly reconciled from terminal memo mtime/hash; subprocess exit code remains unknown. Continue only PRR two pending batches under unchanged four-call plan/cap10. This is mechanical recovery, not another scientific alternative.

## 2026-10-20 — native-agent control incident, paid work stopped

PRR run `20261020T175209Z-66dgq7` first batch spawned three actual native Terra child sessions despite all three frozen multiagent feature flags being false. Root stopped the operator/provider process tree at17:53:19UTC; continuation exit143, PRR zero committed effects and no rating result. `AT/native-agent-incident.json` preserves exact parent/child lineage, action and token evidence. All four PRR sessions used Terra; no Claude/Fable, tests, candidate edits or forbidden solution reads observed. Standard shim receipts omit native children, and interrupted final consumption is unavailable: retain last recorded totals only as lower bounds. Count conservatively3CLI+3children=6dispatches; two pending batches would bring8underoriginalcap10. No further dispatch until independently reviewed mechanical enforcement of `agents.enabled=false`; frozencriterion/scripts/runtime remain unchanged. RPI passes frozenrules (8/6upstream,0/0stub,5/5partial,4/2mutant,maxspread2); this is not a combined pass.

## 2026-10-20 — independently reviewed pending-only PRR recovery

`AT/native-agent-correction.json` SHA `066bb025e776b54ac83eb6a947cf6da62c7cb926b5bdde74351956a5de4e7fe3` binds the external2-line wrapper, realCLIentry/binary and provider-free effective-context/guard/stdio/nestedPATH checks. It enforces `agents.enabled=false` after the unchanged frozen guard. Independent review PASS; runtime, rubric, scoring inputs, criterion and originalscripts unchanged. Root rechecked exact3children with no later records and budget3CLI+3children+2pending=8<=10; no other dispatch authorized. Resume only PRR `20261020T175209Z-66dgq7`, absoluteCLIlimit3, identical masks and emptyClaudeallowlists. Retain invalid interrupted attempt and lower-boundcost accounting, deduplicating root session; RPI advertised unused collaboration while recoveredPRR suppresses it, so do not claim empirically identical context. No scientific rerun or A3. Every further recovery requires explicitrootpreflight counting children.

## 2026-10-20 — AT stopped incomplete at cap10

Second PRR attempt also created3nativeTerrachildren; root stopped its process tree at18:03:04UTC. Exact scoped lineage gives4CLI+6children=10dispatches, approvedcap10 exhausted; all10nativecontexts Terrahigh. RPI retains2completed batches and frozenPASS; PRR0committed batches, so combinedcalibrationOPEN and no B/B2/C. Frozenclose refuses incompletePRR (close-attempt.exit1); no fabricatedcombined-pass readout. `AT/interrupted-readout.json` records full4-pairdenominator/2missing and deduplicated nativeaccounting: completeRPI USD1.8673224; all interruptedPRR totals are lowerbounds, completeATcostunavailable. All36clones intact, scans0hits, historical220hashes unchanged. Sharedguardflag code cbb6e679 passes83focused/318broader checks and I3CLIintegration1, but these prove configurationmechanics, not effective liveprevention. PriorprelaunchPASS is superseded by appended incidentreviews; actualresolvedbackendargv was notcaptured, so neitherCLIflagignored norwrapperomitted is proven. No morepaidwork and no A3; enforce/verify actualdispatch and accounting before any concrete newownerbudget.

Final integration: main and measurement branch at `4f0d13b4981ad4a86e1a8188d0d1d1fb8762ee1c`; AT criterion/preparation, shared guard configuration request and reviewed interrupted report/status routing integrated. Mainindexclean; original21tracked useredits preserved (index own4rowchange separated) and6807untracked paths unchanged. No push. Cap10 exhausted; no experiment active, no furtherpaidworkselected. Detailed state remainsAT/interrupted-readout.json, fullcostunavailable.

## 2026-10-20 — AT offline configuration-scope diagnosis

No additional remote model requests. Public run/resume with an inert backend reached the wrapper; a native CLI probe with network egress disabled reproduced top-level configuration being discarded when exec supplies its own --config. Commit `96cdc622` moves maintained guard settings into exec scope and is integrated in main. Independent review passed; 88 focused tests, 88 collected cases, one public-CLI integration test, and 323 broader tests passed. Evidence: `AT/offline-public-dispatch-trace.json`, `AT/offline-exec-config-scope.json`, `AT/offline-config-scope-review.json`, and `AT/offline-config-scope-integration.json`. Frozen artifacts and 220 historical hashes preserved. Cap remains 10/10, RPI passed, PRR incomplete, combined calibration OPEN_NOT_QUALIFIED; live native-agent prevention remains unqualified.
