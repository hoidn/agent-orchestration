# Workflow Lisp Dynamic-Core Evaluation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` for selected execution, with
> `superpowers:test-driven-development` for code and
> `superpowers:verification-before-completion` for evidence claims.
> Track only executed work with checkboxes; a passing test does not select a gate.
> Before selecting or delegating work, follow [upstream synchronization](#upstream-phase-3-synchronization):
> import shared Phase 3 progress from its owner instead of implementing it again.

**Goal:** Decide, through bounded evidence and explicit owner dispositions,
whether an ordinary dynamic core with strict boundary schemas should replace
the prospective typed internal representation of evaluated execution.

**Architecture:** Retain the completed typed compiler and integrated evaluator,
memo, authority and CLI work as the baseline and reusable substrate. Qualify a
versioned dynamic candidate using the same effect owners, then compare full
consumer behavior and authoring utility before authorizing production migration.
No permanent parallel implementation or dynamic facade over specialization is
the intended destination.

**Owner tradeoff amendment, 2026-10-02:** loss of effect tracking and resumability
is acceptable if composition/complexity gains justify it. Evaluate one minimal
candidate that executes fresh from entry; a restart may repeat earlier external
work. Preserve most existing types-to-input/output contract machinery. Static
effect summaries, committed-effect replay, dynamic memo identity and resume are
comparison dimensions, not mandatory feasibility or adoption conditions. Keep
existing targets/runs unchanged and retain actual boundary validation and
execution permissions. Adding recovery later needs its own justified scope.

**Tech Stack:** Existing Python runtime, closed-program admission, pure operators,
boundary validators, command/provider performers, pytest, deterministic fixtures
and public `python -m orchestrator` checks. No new dependency or report framework.

---

## Authority, Selection And Baseline

Read [docs/index](../index.md), the [capability matrix](../capability_status_matrix.md),
[dynamic proposal §8](../design/workflow_lisp_dynamic_core_proposal.md#8-compatibility-and-evidence-required-before-adoption),
[accepted evaluated design §13](../design/workflow_lisp_evaluated_execution.md#13-targets-and-compatibility),
the [parent plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md), and
[Phase 3 plan](2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md).
The proposal owns candidate semantics; existing specs own shipped behavior.

Initial owner amendment, 2026-10-02: select DC-0 qualification followed by a
bounded feasibility spike. The initial integration/planning turn implemented no
candidate. The subsequent owner instruction to start execution activates the
reviewed **DC-1a pure mechanism sub-batch after completed DC-0 qualification**.
Later tranches remain pending behind the gates below; no language-target
allocation, production adoption or live-study budget follows from this start.
Full typed Phase 3 completion is not an entry condition for qualification or the
bounded spike; only the shared contracts actually exercised must be available.

Initial baseline: branch `design/orc-dynamic-core-evaluation` in `.worktrees/orc-dynamic-core`,
from main `c0dacad1` with committed source `7af8ebf6` from
`.worktrees/orc-phase3-r12-control` merged with its dependency-closed history
at merge `3420a690` (parents `c0dacad1`, `7af8ebf6`).
The source's uncommitted edits and untracked control implementation are excluded.
The merge preserves Phase 2 closeout and Phase 3 Tasks 1–5 receipts; it is not
proof of dynamic execution or a completed runtime release. The bounded pure
public run/dry-run path exists; effects still refuse `closed_effect_handler_missing`
and public resume, full views and effectful release remain unfinished.
Retain the recorded six-test red baseline as red; do not recast it as passing.
The source worktree's independently authorized typed work is not rescheduled here.

Coordinator integration receipt: runtime/test trees match the pinned source;
fresh narrow substitution/command checks passed **26**, public CLI/target smoke
checks passed **54**, and the broader impacted run recorded **1497 passed,
6 inherited characterization failures** (`-q -n 16 --dist=worksteal`). The
selectors overlap and are not additive. Logs and exits are in
`/tmp/orc-dynamic-core-integration-8_b5ym95/{narrow.log,impacted.log,results.json}`.
This is baseline integration evidence, not a full-suite pass or dynamic gate.

**Approach and cost:** overlay the existing phase ledger, reuse shared contract
and execution owners, and evaluate the simpler non-resuming candidate. Some
errors move after expensive effects, and restarting can repeat calls, cost and
external writes. Compare those losses with composition gains; preserve old-run
compatibility without rebuilding its checkpoint machinery for the candidate.

## Upstream Phase 3 Synchronization

Shared Phase 3 components retain their upstream implementation owners. Track
`feat/orc-phase3-r12-control` in `.worktrees/orc-phase3-r12-control` and the
integration branch `feat/orc-phase3-execution` in `.worktrees/orc-phase3`.
Prefer reviewed integrated commits with their dependencies; continue tracking
the integration branch after an individual task branch stops advancing. Record
any owner-designated successor here. These are moving sources, not a one-time
baseline import.

**Cadence:** check at every session start/resume, before selecting or delegating
a shared-component task, before each DC tranche or decision gate, and before
integration/closeout. During ongoing execution, check at least once per active
working day even if the current tranche has not ended.

At each checkpoint:

1. Inspect committed upstream heads, changes since the last check, and the
   Phase 3 task/review receipts. Local worktrees share refs; fetch relevant refs
   when progress is published remotely. A dirty source tree is work in progress,
   not reusable committed evidence; never copy it or overwrite its owner.
2. Import relevant reviewed, dependency-complete progress **before implementing
   dependent candidate work**. Merge compatible history, or selectively import
   an independently reusable slice with its prerequisites. Preserve this branch's
   evaluation gates and the upstream typed contracts when resolving conflicts;
   do not replace either plan wholesale. Memo/authority, performers, R12,
   recovery, document transport and readers must not acquire parallel copies.
3. If a required slice is unfinished upstream, coordinate with its existing
   owner and advance independent candidate work meanwhile. Any shared fix needs
   an explicit ownership handoff and return to upstream; its absence is not
   permission to implement a competing copy or substitute a shim. This branch
   owns dynamic-specific adaptations, not a second execution of the Phase 3 list.
4. Inspect the merged diff and run affected narrow checks; include the existing
   public smoke when runtime/boundary behavior changes. Record date, checked
   heads, imported SHA(s), relevant deferred work with reason/owner, and fresh
   verification in this plan until the single evaluation report exists, then
   there. Reuse unchanged evidence and retain known failures as failures.

Keep the moving integration head separate from frozen comparison controls.
Never silently advance a pinned experiment baseline: explicitly re-pin and rerun
affected paired cases after a relevant update. Synchronization neither approves
a DC gate nor requires waiting for all of typed Phase 3.

Latest check, 2026-10-02: reviewed integration `0d7e4bc6` imported at merge
`18a442da`; R12 source `0f1bbc46` and integrated code `a780639c` have the same
stable patch ID. All 14 imported source/test hashes match the upstream receipt.
R12-A is complete; Task 6 overall remains open. Fresh affected checks passed
55 command-template/control cases and three public/helper checks. Exact commands,
metadata and evidence limits are in the single report's synchronization section;
these results do not pass a dynamic gate or advance frozen comparison controls.

## Finite Tranches And Decision Record

| Tranche | Current state | Entry / bounded exit |
| --- | --- | --- |
| DC-0 — qualify exact scope and controls | Complete; independent Design and qualification reviews PASS | Produce the inventory, pinned controls, exact finite case list and reviewed spike patch scope below; do not implement a production target |
| DC-1 — feasibility spike | DC-1a complete and reviewed; DC-1b boundary/dispatch qualification executing; DC-1c authored composition follows immediately | One isolated non-resuming candidate, real strict boundaries and an authored `.orc` specimen, independent review and DC-F evidence; stop at DC-F |
| DC-2 — utility comparison | Pending DC-F continue | Full improve and paired-search protocols, four paired author edits and diagnostic/complexity assessment; stop at DC-U |
| DC-3 — production readiness | Pending DC-U continue | Only the named release scope, approved version contracts and required shared runtime qualification; stop at DC-P |
| Phase 6b / 7 — migration / retirement | Pending DC-P authorization | One selected destination, explicit maintained-consumer and existing-run dispositions |

Each gate records in `docs/reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md`:
tested commits, commands and raw outcomes, supported/adverse/missing evidence,
independent review, and **owner + date + disposition + exact next tranche**.
Create that report only when execution supplies evidence. Keep failures and
proposed controls separate from executable receipts; use this one report rather
than new registries or scoring infrastructure.

- **Continue:** explicitly activates only the named next tranche and its finite
  cases/scope; it never implies a live-study allocation or later gate approval.
- **Revise:** owner names one bounded correction and one reevaluation of the
  affected gate. A remaining failure stops that route unless the owner explicitly
  allocates fresh work; no open-ended revise-until-green loop.
- **Stop:** retain the typed baseline, archive the candidate/evidence, remove
  candidate-only machinery when present, and return to pending typed Phase 3
  Tasks 6–17, Phase 6a and qualified W3/Phase 4/5 work under their existing gates.
  Stop does not undo integrated Phase 2 or Phase 3 Tasks 1–5.

A gate with no owner disposition is **pending** and blocks its successor. It
does not block the qualification/spike/evidence needed to reach that gate.
No result, test count, reviewer recommendation or document publication selects
continue automatically. There is no new machine manifest: machine tranche and
ready/pending/completed/blocked count deltas are all **0**, the five research
units remain unchanged, and no active run is mutated. The human next task is
DC-1b qualification after reviewed DC-0/DC-1a completion, immediately followed
by DC-1c source authoring before DC-F; existing executable selectors have no new
item to consume.

## DC-0: Qualify Scope And Controls

**Artifacts:** update this plan with the exact case inventory and patch ownership;
read existing sources and tests, without editing their semantics:
`orchestrator/workflow/evaluated/{values,machine,calls,memo,authority,runtime}.py`,
`orchestrator/workflow_lisp/closed/{program,check,sites,artifact}.py`,
`orchestrator/contracts/output_contract.py`,
`orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`,
`experiments/mlevolve_pair/{search_compact.orc,leaves.py,README.md}` and
`experiments/orc_vs_single_call/workflows/reviewed_change.orc`.

- [x] Trace all callers of reused owners; classify shared infrastructure versus
  typed-only proofs/specialization. Command implementation **closure means files**
  and content evidence, not lexical function closure support.
- [x] Pin the best executable typed baseline and Python behavior reference; retain
  their real limitations. Inspect `tests/test_workflow_lisp_improve_stdlib.py`,
  `tests/experiments/test_mlevolve_pair_fixture.py` and Phase 3 Tasks 13–15 to
  freeze complete behavioral cases, not a toy approval-only helper.
- [x] Inventory imports, hooks, prompt schemas, document/output roles, path and
  artifact requirements, read-only effect restrictions, and current diagnostics.
  Label proposed W1/W3 examples as proposed when they cannot execute; do not
  require implementing either proposal to start the dynamic comparison.
- [x] Define the smallest command/provider/boundary slice needed by DC-1 and DC-2
  from Phase 3 Tasks 6–7/12–15; check upstream availability and import reviewed
  slices through the synchronization protocol above. Record missing dependencies
  with their upstream owners. Include R12 authored request parity where used;
  do not port views, watchdogs or child runs merely to start the spike.
- [x] Record exact fixture counts, paths and expected observations before coding;
  allocate one finite spike with explicit owner transfers and independent review.
  Amend unresolved semantic details through Design, including representation,
  schema strictness, call context and deterministic budget accounting.

Qualification execution, 2026-10-02: control/source pin `4b69ee00`; the
[single report](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md)
records the owner/caller inventory, actual missing upstream slices and frozen
consumer controls. Fresh collection found 105 cases (20 improve, 76 paired
fixture, nine pure CLI); collection is not runtime proof. On 2026-10-02,
`/root/planning_dynamic_core_sequence` passed the independent Design review and
`/root/design_dynamic_core_roadmap` passed the plan/report review; dispositions
and bounded corrections are recorded in report §5. No shared implementation is copied
or recreated to cover missing upstream performers/recovery.

Owner clarification: retain most existing type declarations/descriptors → prompt
formatting, input rendering, document/output roles, validation, projection and
transport machinery. The candidate changes high-level composition toward ordinary
Scheme-like functions/closures; its initial JSON artifact is an internal seam,
not the final authoring surface. The report names the concrete reused pipeline.

**Bounded first sub-batch DC-1a:** only
`experiments/dynamic_core_evaluation/{program,evaluator}.py` and
`tests/experiments/test_dynamic_core_evaluation.py`; 48 frozen pure/admission/
boundary/budget cases, detailed in report §5. No shared code, parser, public target,
effect shim or durable store. The coordinator selected this independent
sub-batch after both reviews; its three paths are assigned to
`/root/design_dynamic_core_roadmap/impl_code_dynamic_core_pure` (Luna 6 xhigh).
DC-1b reuses real boundary/dispatch owners, checking upstream Tasks 6–7/12 for
reusable progress first. The report's twelve families distinguish required
fresh-execution evidence from accepted tracking/recovery losses. Task 8 and a
dynamic memo/authority bridge are not prerequisites; pure success alone still
cannot select DC-2.

**Exit:** reviewed scope authorizes only DC-1's bounded experiment; no production
version or release admission is inferred. Stop at a concrete unresolved contract
rather than inventing one inside implementation.

## DC-1: Feasibility Spike And Gate DC-F

**DC-1a complete, 2026-10-02:** the three experimental files passed independent
conformity and quality review. Final candidate checks: 48 passed; serialized
closure/generic-helper demo passed; nine unchanged public CLI controls passed.
[Execution evidence](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#6-dc-1a-execution-evidence)
separates these results from the still-pending full DC-F matrix. Next is DC-1b
qualification of fresh leaf execution through existing complete contract owners;
freeze its exact cases/API before implementation. Then execute **DC-1c authored
composition** using the existing S-expression reader, before DC-F: a checked-in
`.orc` specimen must define an ordinary unannotated helper, create/return/store/
select a closure using a real validated leaf result, and call a second typed
boundary. Preserve existing boundary declarations and their contract compiler;
do not introduce another schema language. Its finite frontend contract and case
list are reviewed after the leaf seam is fixed. JSON construction alone cannot
satisfy this source proof or demonstrate authoring utility. Neither slice waits
for full typed Phase 3 or W3 delivery; completing DC-1b proceeds to this visible
source slice under the current continuation instruction. No new gate is passed here.

**DC-1b bounded handoff:** [report §5](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#dc-1b-reviewed-finite-scope)
freezes 24 cases E01a–E12b, exact commands and ownership. Modify only candidate
`program.py`/`evaluator.py`, add `leaf_bridge.py`, `fixtures/leaf.orc`,
`fixtures/scripted_leaf.py`
and `tests/experiments/test_dynamic_core_boundaries.py`. The one shared edit is
optional `document_bytes` forwarding in
`WorkflowExecutor._apply_expected_outputs_contract`, explicitly authorized by
the coordinator and returned as reusable evidence to its upstream owner. Preserve
the default path and all 48 pure cases. Proposal §6.2 passed independent Design
review; Design independently passed the finite case matrix and the coordinator
accepted the final path handoff. The distinct reviewer assessed §6.2 and the
preceding case draft, not this final documentation diff.
Then record actual receipts and continue directly to DC-1c; tests alone do not
select DC-F or DC-2.

**Artifacts:** create `experiments/dynamic_core_evaluation/` only when this task
runs; use a minimal candidate module and `.orc` specimens there, and
`tests/experiments/test_dynamic_core_evaluation.py`. Append actual evidence to the
single report above. Before creation, DC-0 records exact module/fixture paths and
exclusive shared-owner edits. No new production evaluator/CLI route is authorized
merely by these planned paths.

- [ ] Write failing behavioral/admission cases for the matrix below and run
  `python -m pytest --collect-only -q tests/experiments/test_dynamic_core_evaluation.py`.
- [ ] Implement ordinary dynamic values/functions/lexical closures in the bounded
  candidate after importing the required upstream shared progress; reuse the
  pure catalog and admitted effect boundaries. One helper body must work
  with different internal values without specialization.
- [ ] Replace candidate P5 with checked lexical scope/code targets, schema and
  effect bindings and versioned artifact read-back; never disable
  validation or lower dynamic functions back into typed specialization.
- [ ] Run the narrow module, correct only demonstrated defects, run one orchestrator
  or demo integration smoke, and record the exact invocation and limitations.
  Spike-driver evidence is labeled experimental, never public production support.
- [ ] Obtain independent code/design review of feasibility and record DC-F's owner
  disposition. End this tranche even when all tests pass.

| DC-F obligation | Required observations |
| --- | --- |
| Ordinary calls and lexical values | Create, return, store in internal collections and pass closures; select a closure using a validated effect result and capture that value; definition-site values survive later binders |
| Fresh effect execution | Invoke actual shared command/provider transport from dynamic composition. Restart starts from entry with fresh attempt/result locations; record repeated calls and external-work consequences, without claiming committed-result reuse |
| Strict boundary schemas | Inputs checked before launch, outputs before exposure; reject wrong Bool, missing/extra fields, invalid nested/tagged payloads, non-finite numbers and closures at public/provider/command boundaries; preserve document snapshots and required output checks |
| Admission independent of compiler generation | Reject forged code/schema references, undeclared hosts and invalid artifact versions on read-back; honor declared execution permissions; no dynamic eval/import/host-call escape. No static purity/effect-summary guarantee is required |
| Bounded execution | Self-application exhausts a pinned deterministic budget; calls and actual execution consume it, effects do not reset it within an invocation. Restart is a new invocation, not a way to claim resumed progress |
| Honest failure semantics | Invalid/orphan bundles are not consumed as fresh successful results. Report partial external writes and repeated work after a failed invocation; recovery, exactly-once execution and rollback are not promised |

**DC-F:** feasibility requires all applicable rows with fresh evidence. Continue
selects DC-2 only. Revise/stop follow the finite policy above; unproven dynamic
composition, real boundary enforcement or budget safety prevents utility rollout.
Missing effect tracking/resume does not fail this gate; quantify its consequences
in DC-2 instead of restoring it merely to match the incumbent.

## DC-2: Full Utility Comparison And Gate DC-U

**Artifacts:** extend the same candidate/fixtures and report; preserve production
`std/improve` and maintained consumers until a destination is authorized. Reuse
`experiments/orc_repetition_census/variants/` as labeled W1/W3 comparisons.

- [ ] Port full `improve`: APPROVE, REVISE, BLOCKED, EXHAUSTED; latest revised
  candidate and evidence/reason payloads; zero limit rejected before hooks;
  invalid hook output and final-iteration revision failures remain failures;
  imported/inline fresh-run order agrees with the control. Record committed-hook
  reuse as a lost capability of the non-resuming candidate, not a parity failure.
- [ ] Port full paired-search policy: seed ranking, strict improvement/ties,
  invalid evaluation, one same-branch repair, stalls, one fusion, full history,
  budget/score stops, invalid budgets and exhaustion. Run all 72 existing
  scenario/budget pairs (nine scenarios × eight budgets) owned by
  [the fixture](../../tests/experiments/test_mlevolve_pair_fixture.py) against
  the Python reference. Schema-invalid transport
  is not domain `valid=false`; compare ordered decisions, spend and final value.
- [ ] Perform four paired edits: add a state field, change review payload, capture
  context, extract a helper. Record touched sites, duplicated facts, concepts,
  repairs and diagnosis. Preserve useful domain schemas/types instead of counting
  their removal as a gain. State errors found before and after costly effects;
  compare repeated calls/cost and partial outputs after interruption/restart.
- [ ] Compare the best **implemented** typed baseline and the proposed W1/W3
  improvement honestly. If W1/W3 cannot execute, label it a counterfactual and
  narrow the unique-gain claim; no requirement to build both languages first.
- [ ] Inventory actual added/retained/displaced owners, validators, specialization
  paths, identity forms and compatibility costs. Include budget/runtime
  diagnostics, lost static checks/recovery and old-target retention; LOC alone is not a
  complexity or authoring verdict. No paid-provider quality/cost conclusion from
  scripted leaves or an unbudgeted authoring study.
- [ ] Run narrow parity/integration checks and independent utility review; record
  supported, adverse, missing and untested evidence separately, then DC-U.

**DC-U:** owner judges meaningful authoring/reuse benefit beyond the incumbent and
credible W1/W3 gains, preserved fresh-run domain protocols, useful diagnostics
including late errors, and net complexity after compatibility. Explicitly weigh
lost effect tracking and resumability against those gains; neither loss alone
requires rejection. Passing fresh-run parity establishes
correctness only. Continue selects named DC-3 readiness work; stop retains typed
execution and may qualify W3 under its existing plan, without shipping closures.

## DC-3: Production Readiness And Gate DC-P

**Artifacts:** only after DC-U continue, write a bounded production implementation
plan and accepted owner amendments. Exact files and independent verification
belong to that plan; this task does not preallocate a language target or mutate
normative specs. Reuse Phase 3's evidence matrix rather than creating a duplicate.

- [ ] Settle target/IR versions, schema strictness, mixed-version imports,
  stdlib API and existing checkpoint/run dispositions with owners. Define only
  the state the candidate actually retains; no resumable state profile is required.
  Preserve old run pins; never reinterpret typed checkpoints as dynamic captures.
- [ ] Import upstream delivery of the named production slice: shared
  requests/performers and document transport from Tasks 6–7/12; child
  runs/coordinators in Task 9 only when admitted; public views, report,
  dashboard/monitor/watchdog in Tasks 10–11 for the selected release. Implement
  only agreed dynamic-specific adaptations here and requalify the combined
  behavior; route missing shared work to its upstream owner. Resume/invalidation
  and dynamic memo/authority integration are optional later capabilities, not
  release requirements for the explicitly non-resuming profile.
- [ ] Close relevant Tasks 13–15 full fixture/live-provider/artifact/kill/durable
  publication evidence for the admitted release, beyond earlier focused spike
  checks. Mark unavailable credentials or unimplemented classes as missing,
  never satisfied by stand-ins. Test interruption/restart consequences honestly;
  do not require replay/durable-continuation guarantees the selected profile
  omits. Obtain separate allocation for paid/live work.
- [ ] Apply Tasks 16–17 to truthful selected-profile docs and independent closeout;
  retain the original typed checklist as history/fallback. Give each production
  obligation its exact evidence owner; candidate success never checks off a
  typed-only task whose specified implementation was not delivered.
- [ ] Select one maintained-consumer migration destination and list removable
  candidate/old-target machinery, with an explicit existing-run disposition and
  later Phase 7 retirement decision. Do not finance two full migrations.
- [ ] Record independent readiness review and DC-P's explicit owner disposition.

**DC-P:** only a continue disposition explicitly authorizing adoption/migration
activates Phase 6b for the selected target and consumers. Phase 4a/4b capabilities
and Phase 5 parallelism require that target's runtime contract proofs and their
own consumer scope; completing static Phase 3 alone cannot authorize dynamic
parallel effects. Phase 7 still requires completed migration and run-retirement
approval. Stop returns to the typed fallback with no implicit target deletion.

## Verification And Handoff

This planning amendment requires link/anchor checks, stale-route inspection and
`git diff --check`; coordinator-owned integration receipts remain separate.
During future execution, collect any new/renamed test module, run narrow cases
first, then broad/slow/full checks in tmux with `pytest -q -n 16 --dist=worksteal`.
Use the tmux skill and run from the repository root. For runtime/DSL/shared
boundary changes include an orchestrator/demo smoke and public integration check;
record why a spike-only check cannot establish production support. Keep tests on
behavior/contracts/dataflow, never literal prompt wording. Inspect each diff and
fresh result; compare failures against the pinned baseline without weakening it.

After each gate, update this table's task state, the parent/Phase 3 overlay,
roadmap W3/EL-1 routing and repetition-plan entry conditions together. Preserve
all existing completed receipts. Do not mutate unrelated active workflows or
invent a selector to implement a prose-owned decision.
