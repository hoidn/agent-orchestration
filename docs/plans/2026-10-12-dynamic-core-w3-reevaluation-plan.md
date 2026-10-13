# Dynamic Core Versus Implemented W3 Reevaluation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`. The coordinator integrates and verifies; a distinct Sol 6.1 high reviewer checks this plan before implementation.

**Goal:** compare implemented upstream W3/2.36 with native dynamic/3.0 and prepare the existing owner DC-P decision with current execution evidence.

**Architecture:** run the two pinned runtimes in separate processes/checkouts, sharing deterministic input/leaf protocols and existing result/trace oracles. Add one bounded comparison test module and one small authored W3 improve fixture; reuse maintained native fixtures and retarget a temporary copy of upstream search. No language/runtime changes or benchmark framework.

**Tradeoff:** independent pins make setup and provenance checks necessary; they avoid importing W3 into the candidate. Scripted local calls cannot measure provider quality, paid cost, human editing speed or production performance.

**Tech stack:** existing Python/pytest, public orchestrator compile/run/resume, `.orc`, Git objects, local command probes.

**Execution status:** full campaign executed all 100 logical observations,
98 PASS and two genuine parity FAIL, plus a passing provenance guard:
101 collected, 99 PASS, 2 FAIL, exit 1, 176.94s. The
[dated packet](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#implemented-w3-reevaluation--2026-10-12)
binds original module SHA-256
`7a98215a1a7bbdc6f9e096c24a804273b85ebc2cb7300b9fc6ee7bc6325eec49`.
Accepted receipt refinements ran eight affected rows; its faulty intermediate
E04 is superseded by a corrected final one-row/dataflow check. Seven unchanged
rows retain applicable proof; final Sol code conformity PASS / quality APPROVED
is recorded in the packet. Final Astra document conformity PASS / quality
APPROVED is also recorded; the decision packet is delivered. Root commit,
postcommit checks and push remain pending. Final module SHA-256 is
`607bb07c0c44bd95df8d6a65303ab07a5ba2ba4deb3b8d963de8989ed3634d2d`.
Keep runtime limit-zero and malformed-Bool discrepancies RED. The fixed-consumer
recommendation does not stop broader dynamic work or select a DC-P disposition.

## Authority and fixed scope

Read [docs routing](../index.md), [capability matrix](../capability_status_matrix.md), [design routing](../design/README.md), [evaluation gates and synchronization](2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md), [native profile](../../specs/versioning.md#branch-qualified-target-30), [proposal §9](../design/workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate), and the completed readiness handoff. The [existing evaluation report](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md) remains the single evidence-summary authority; this document owns only this finite execution tranche.

Owner “execute” selects the comparison and decision preparation, not adoption. No live/paid calls, production-language changes, bulk main merge, consumer migration, default change or retirement. Loss of effect tracking/resume remains an accepted candidate tradeoff to measure, not a defect to repair. `experiments/mlevolve_pair/search_compact.orc::run-search` remains the sole possible later migration destination, conditional on explicit DC-P authorization; Phase 7 remains later.

| Role | Inspected committed source |
| --- | --- |
| Native 3.0 runtime/control | `b0b05d504d4b1be7b1cbaebfadf47ffdc3e66012`, candidate `/var/tmp/agent-orchestration-orc-dynamic-core`; reviewed three-fix shared import already qualified with 961 PASS |
| Actual W3 runtime/control | `47e85a9c7e452bfd367275a15d5e97b928efa5ca`, clean detached `/home/ollie/Documents/agent-orchestration/.worktrees/orc-w3-dynamic-comparator-20261012`; implementation `8e6e06b215c86fd08fd533aec3909481a6e1ccf6`, closeout `d6f7695017992793a27dcab4f703e040f4e85bc3` |
| Frozen historical evidence | DC-2 comparator `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`, spike `3a7f8efd`, byte-pin control `26bc796f`; no edits, replacement receipts or advanced pins |

The native code pin is distinct from the comparison packet's Git HEAD.
Native descendant commits containing only documentation and authorized
comparison test/fixture changes are allowed only when the frozen
runtime/stdlib and all reused helpers and consumer/source bytes remain equal
to `b0b05d504d4b1be7b1cbaebfadf47ffdc3e66012`; record both HEAD and the code
pin with byte-equality evidence. This does not advance the native runtime pin.
Within the protected `tests/` tree, the only permitted new file is
`tests/fixtures/workflow_lisp/w3_dynamic_reevaluation/improve.orc`; the opt-in
comparison module lives outside that default test tree. All reused test helpers
and fixtures remain frozen to the native code pin.
The typed comparator must remain clean at exact HEAD
`47e85a9c7e452bfd367275a15d5e97b928efa5ca`; descendant HEADs are not allowed.

Upstream inspection covered committed `specs/versioning.md`, `docs/design/workflow_lisp_write_once.md` §6, W3 plan/closeout, `orchestrator/workflow_lisp/stdlib_modules/w3/std/improve.orc`, maintained proposal/reviewed-change consumers, W3 target/let-proc tests and public evaluated-consumer/source helpers. W3 2.36 selects four-argument `std/improve` by entry graph; its builtin source still declares 2.33. It supplies inferred captures, grouped locals and bounded expected signatures, not runtime closures or W1/W2. Branch docs saying “proposed” describe branch availability/historical controls, not current upstream delivery. Keep upstream closeout's bounded evidence and known RED full-suite status qualified.

Read the pinned [committed W3 design §6](https://github.com/hoidn/agent-orchestration/blob/47e85a9c7e452bfd367275a15d5e97b928efa5ca/docs/design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context) and [bounded W3 closeout](https://github.com/hoidn/agent-orchestration/blob/47e85a9c7e452bfd367275a15d5e97b928efa5ca/docs/reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md). The same committed bytes are present in the clean comparator above; inspect them there if remote access is unavailable.

At entry, before each delegation/tranche and at closeout, follow the parent synchronization cadence: inspect/fetch committed heads and shared-fix scope, record changed heads. Do not silently move either comparison pin; if a relevant change is required, record/review it and rerun affected rows. Never read executable control bytes from dirty main.

## Files and ownership

| Sequential owner | Exclusive writable files | Purpose |
| --- | --- | --- |
| Planning/revision | This file | Plan and completion checkboxes |
| Code implementation, Luna 6 xhigh; distinct Sol 6.1 high code review | `experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py`; `tests/fixtures/workflow_lisp/w3_dynamic_reevaluation/improve.orc` | Opt-in finite paired public execution, edit/diagnostic receipts, small fair W3 improve source |
| Documentation revision, Sol 6.1 high; distinct review | `docs/index.md`; `docs/capability_status_matrix.md`; `docs/design/README.md`; `docs/design/workflow_lisp_dynamic_core_proposal.md`; `docs/design/workflow_lisp_write_once.md`; `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md`; `docs/plans/2026-09-29-workflow-lisp-repetition-reduction-plan.md`; `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`; this plan after planning ownership releases; `docs/reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md` and `docs/plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md` after actual comparison qualification; append-only current reproduction in `experiments/dynamic_core_evaluation/README.md` | Correct current routing/status first; append the actual comparison/decision packet only after execution. Preserve history and candidate availability; do not claim local W3 delivery |

Read/reuse without modifying: `tests/fixtures/workflow_lisp/dynamic/{improve,search,consumer_types}.orc`; `tests/test_workflow_dynamic_{improve,search,edits,improve_interruptions}.py`; existing improve probe sources; `tests/experiments/test_mlevolve_pair_fixture.py` scenario/budget/trace oracles; both pins' local search leaf scripts/manifests. W3 source/harness authorities are upstream `workflows/examples/improve_experiment_proposal.orc`, `tests/test_workflow_evaluated_consumers.py`, `tests/workflow_evaluated_program_sources.py`, and the W3 builtin above. Do not add a second dynamic implementation, copy the historical evaluator, or patch existing frozen case IDs. Production callers/config/exports remain outside this test/docs-only scope.

Concrete helper reuse: native `_stage_dynamic`, `_write_probes`, `_events` and `_expected_events`, plus edit probes/mutations and `_save_receipt`; W3 search `install`, `public_run`, `reference`, `observe_requests`, and `compile_public`/`checked_run` from `tests/workflow_evaluated_totality_helpers.py`. Invoke helpers within their identified runtime process. Avoid W3 `exercise()` for fresh rows because it adds pause/resume; reserve recovery setup for RW-D05–D06. The new interface is only a small subprocess/evidence adapter, not another controller, oracle or probe generator.

## Task 1: Establish the real paired route

- [x] Coordinator records pin/cleanliness/import provenance and reviews this plan. Delegate code implementation only after distinct plan review passes.
- [x] Require the explicitly supplied clean pinned W3 checkout listed above. Check its exact HEAD and relevant source bytes; fail clearly if unavailable, dirty or mismatched. No checkout/archive materialization, network fetch/install or silently skipped comparator inside pytest. Keep generated workspaces outside either source checkout.
- [x] Launch each runtime with its own pinned import root/interpreter and staged workspace; record resolved `orchestrator.__file__` and command argv/cwd. Do not import two runtime versions into one interpreter. Native packet HEAD may be a descendant containing only documentation and authorized comparison test/fixture changes under the byte-equality rule above; runtime/stdlib and reused helpers/consumer/source bytes must match the native code pin. Typed HEAD must equal its exact clean pin. Fail provenance checks before any effects if mismatched.
- [x] Add W3 improve with the same Draft/Feedback/Blocker contracts and probe protocol as native improve: outer `goal`/`rubric`, inferred captures, one four-argument `improve` call, minimally annotated local review/revise hooks. Reuse staged domain declarations with target admission adjusted explicitly. No context-only Brief wrapper, forwarding parameter or unnecessary signatures. Retain legitimate domain schemas in both.
- [x] Stage upstream `experiments/mlevolve_pair/search_compact.orc` and change only its target 2.33 to 2.36 for the search control (plus the explicitly tested loop-bound edit). Use actual public compilation/execution, never `compact_controller`'s spike executor. Preserve source hashes and the exact authored delta.
- [x] Smoke one approval and one search case through public `compile` and `run` in both runtimes. Assert target/artifact route, declared domain result and ordered probe requests. Persist separate raw outputs/state rather than disguising wire differences. Small result decoding in the test is allowed; no policy reconstruction or Python performer masquerading as W3.

Every distinct source variant must compile through its runtime's public route before execution. Reuse existing public helpers and compile evidence keyed by actual distinct source bytes, runtime pin and boundary configuration for repeated deterministic scenario/budget variants; every pair still executes publicly. Existing Python reference code is an oracle only. Use public command handlers or `python -m orchestrator` inside isolated subprocesses; tiny subprocess glue may invoke existing helpers but must identify the public entry used. No generic runner/cache framework is needed.

## Task 2: Complete fresh-run policy parity

Use new `RW-*` IDs in test names/parameter IDs; preserve historical `UI/US/UE/UD` inventories unchanged. The fixed inventory is **100 logical observations** below: 11 improve + 77 search + 4 edits + 6 diagnostics/recovery + 2 composition. Parameter expansion, both runtimes and regression controls are separately counted, never added as unique observations.

| Cases | Required assertions on both public runtimes |
| --- | --- |
| RW-I01–I11 | Reproduce native UI01–UI11 semantics: initial approval/evidence; revised BLOCKED/reason; limit exhaustion/latest revision/no extra review; malformed review fails before revision; final permitted revision failure stays failure; imported wrapper; imported/inline approval, blocked and exhaustion; zero limit/no hooks; declared blocked output. Exact domain payloads and ordered hook argv must match, not just exit status. Refusal phase may differ and is recorded. |
| RW-S01: 72 pairs | Reuse all nine existing `SCENARIOS` × eight `BUDGETS`. Compare both public executions independently to `_reference`, and to each other: complete SearchResult/history, ordered full command inputs, evaluation spend, stop reason. Covers ranking, strict improvement/ties, invalid-domain evaluation, one same-branch repair, stalls, one fusion and score/budget stops. |
| RW-S02–S06 | Existing real-local-leaf ten-evaluation trace; invalid budget/no effects and strict Bool-vs-Int input refusal; malformed candidate bundle/failed prefix; malformed evaluation schema distinct from valid=false repair; lowered controller bound gives `loop_bound_exhausted`, not budget exhaustion. No scripted success replaces missing policy branches. |

- [x] Collect the new module, run the narrow smoke first, then the improve rows and search matrix. A typed W3 failure is a finding to diagnose, not permission to revert to the old spike or weaken the oracle. No runtime fix is authorized by this plan.
- [x] Preserve failed-run output/failed effect prefix; reject orphan/invalid bundles as successful values. Assert no leaked live providers and local-only command manifests.

## Task 3: Four edits, remaining composition and losses

Perform edits on staged source variants. Save before/after `.orc` bytes and a small JSON receipt in the pytest evidence directory; report exact sites with file/symbol/role, required declarations, duplicated facts, repairs, diagnostic code/location/phase, completed effects before failure and repeated calls after correction. Count boundary-schema and internal-authoring changes separately. Record nonblank authored lines only as secondary evidence; no elapsed-time productivity or performance claim.

| Cases | Concrete edit/check |
| --- | --- |
| RW-E01 | Add external Draft/Candidate `origin: String`: both sides change the same boundary schema, initial construction and affected producer/consumer arguments. Omit initialization in a red variant, then repair; verify origin survives the revised/exhausted result. The internal-only subcase adds a `history_size` counter to the existing private typed `SearchState` and native state: initialize to 2, increment beside each evaluation-count update, and use it at the existing proposal counter reads. Keep external schemas unchanged and check complete results/traces against the reference, including fusion. No new carrier or logical observation; useful boundary schemas remain. |
| RW-E02 | Rename Feedback `note` to `message`; update producer and revision access, preserve approval evidence and revised value. Exercise stale producer and stale consumer separately; compare where validation stops and which calls already ran. |
| RW-E03 | Start from the no-rubric staged variant (`_base_source()` in the existing edit module), since maintained native improve already includes rubric; use the equivalent W3 baseline. Add rubric used only by review while revise retains goal. Both candidates capture outer values directly. Assert review argv includes rubric, revise does not, and no context-forwarding declaration is needed by W3. Credit an equal edit cost if observed. |
| RW-E04 | Extract pure feedback-to-revision-input helper; call it before revise. Preserve exact feedback/result and effect order; count legitimate typed signature versus dynamic definition, without contrived wrapper scaffolding. |
| RW-D01 | Unbound lexical name: compile refusal, located error and zero calls on both. |
| RW-D02 | Wrong local-call arity before effects and after a completed review: W3 static refusal versus observed dynamic failure point; repair one site and compare final value/request trace. |
| RW-D03 | Missing internal field after review: record static/late detection and wasted completed calls; one-site correction must preserve semantics. |
| RW-D04 | Exhaust the dynamic evaluation budget after a completed effect, then fresh restart with sufficient budget; quantify repeats and old-run immutability. W3 has no equivalent operation-budget promise: record this asymmetry, do not invent a typed failure or equal-budget performance comparison. |
| RW-D05–D06 | Public interruption after one committed review/revise pair, then W3 public resume versus dynamic fresh run; repeat with captured workflow goal. Reuse existing event probes, process cleanup and checkpoint instrumentation, adapting only the test seam to W3 evaluated commit authority. Assert final value/context, retained committed requests versus repeated dynamic pair, old dynamic-run bytes unchanged, and actual total call counts (expected 6 W3 / 8 dynamic for three revisions, subject to verified boundary). No sleeps as evidence of a committed checkpoint. |
| RW-C01 | Native existing returned-hook factories versus the idiomatic W3 local-hook equivalent: same capture/result/request behavior and explicit source/annotation cost. W3 lacking returned runtime closures does not imply it cannot implement this consumer. |
| RW-C02 | A bounded runtime choice between two captured ordinary functions, called through the chosen value. Execute both choices natively. Try the closest valid fully annotated W3 ProcRef spelling; if refused, record the located restriction and execute W3's ordinary branch-at-call-site alternative with the same outputs/effect count. Distinguish runtime function-value composition from consumer behavior and quantify duplication only if actually required. |

- [x] Implement/run these bounded rows and inspect saved sources against actual diffs. Do not assert literal prompt wording or exact whole diagnostic prose.
- [x] Reuse prior Q1–Q5/fault/provider/readers, the 961-PASS native/shared-import proof and the fresh 22-PASS W3 baseline with explicit unchanged-owner/contract qualification and their exact receipt links. Do not rerun unchanged native modules or W3 baseline selectors. Existing interruption tests compare an older typed route; they do not substitute for fresh W3 restart rows in the new module. Do not claim adopted machinery was removed: this tranche removes zero production owners, and retained static machinery/compatibility remains part of the decision.

## Task 4: Verification, review and finite handoff

Run from the candidate repository root with the pinned W3 checkout explicitly
supplied to the test setup. The comparison requires that external checkout and
retains genuine RED discrepancies, so its module is opt-in under
`experiments/dynamic_core_evaluation/`, outside the unchanged default pytest
`testpaths = ["tests"]`. The module resolves the repository with
`ROOT = Path(__file__).resolve().parents[2]`; the improve fixture stays under
`tests/fixtures/`. No config change, marker, skip or fallback hides unavailable
setup or failed rows; an explicit invocation without the required environment
variable fails. Earlier command/receipt paths remain historical evidence.
All fresh paired observations live in the new module. Collection and narrow
selectors precede its full check:

```bash
export ORC_W3_REEVALUATION_TYPED_ROOT=/home/ollie/Documents/agent-orchestration/.worktrees/orc-w3-dynamic-comparator-20261012
python -m pytest --collect-only -q experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py
python -m pytest -q experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py -k 'RW_I01 or RW_S02'
```

Use the tmux skill for the complete comparison:

```bash
python -m pytest -q -n 16 --dist=worksteal experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py
```

Reuse the existing [961-PASS native proof](/tmp/orc-dc3-upstream-20261012/verification.json) and [22-PASS W3 baseline](/tmp/orc-w3-dynamic-reevaluation-20261012/baseline-typed.json), including the maintained public W3 consumer evidence, after confirming the relevant owners remain unchanged. Record receipt hashes/pins in the final report. Broaden verification only for a relevant change, failure or unresolved concern; record the reason and narrow affected selectors first.

- [x] Record actual interpreter/env, pins/source hashes, commands, collection counts, exits, raw evidence location and hashes, including failures. Retain the public two-runtime smoke artifact/result/request receipt from Task 1; unit-only green is insufficient. No full-suite PASS claim; reuse unchanged reviewed broad evidence without retotaling it.
- [x] Distinct Sol 6.1 high code reviewer checks provenance, public routes, full policy coverage, fixture fairness, failed-prefix/restart assertions and absence of runtime edits. Coordinator independently inspects complete diff and fresh results. Return bounded corrections to the author; a runtime/architecture blocker is reported, not silently repaired or hidden by skipping. Final conformity PASS / quality APPROVED at `607bb07c…`; exact review/source hashes are in the packet.
- [x] Documentation author appends a dated W3 reevaluation section to the single report: case table/results, four-edit comparison, specific W3 benefits, remaining dynamic value, adverse/lost guarantees, compatibility/owner cost and evidence limits. Update the index, matrix and parent plan to distinguish implemented upstream W3 from unavailable candidate-branch 2.36; link this tranche and preserve historical proposed-counterfactual statements as history.
- [x] Review documentation/links, run `git diff --check`, inspect changed refs at final synchronization checkpoint and reconcile only evidence relevant to this comparison. Final Astra conformity PASS / quality APPROVED; exact review/hash is in the packet. Root independently checked the complete diff and receipt hashes; remaining parity discrepancies and owner DC-P decision stay explicit.
- [x] Finish with a recommendation among retain typed W3, select the qualified dynamic profile, or one explicitly bounded correction. Supply concrete evidence and the conditional next step. Only an explicit owner DC-P adoption/migration disposition permits `search_compact` migration; no further start confirmation is needed to finish this comparison.

**Stop condition:** all 100 logical observations have evidence or an explicitly diagnosed blocking result, reviews and routing are complete, and the owner decision packet is delivered. A blocker does not count as passed parity/readiness. Do not extend the matrix, build both migration paths, restore effect tracking/resume, or start retirement while waiting for the disposition.
