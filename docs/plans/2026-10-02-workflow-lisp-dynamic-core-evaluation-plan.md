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

Latest import, 2026-10-02: reviewed integration `b7d82fa1` imported at
`bcc4ee13`, including attempt allocation and interpreter-pin design. Eleven
narrow attempt checks passed in 2.56s (tool transcript only); the 370-case
integration and final affected ten-case supplement are recorded in the report's
DC-U packet. The frozen comparator remains `4b69ee00`; moving runtime revisions
are separate. Earlier reviewed integration `c3162d42` imported at
`820a12a9`, adding opt-in attempt capture and R12-B compiler-local lexical facts.
Fresh narrow checks passed 11; affected integration checks passed 254, including
complete dynamic improve/search and the public typed helper controls. Earlier
integration `f572a82a` imported at merge `a55a035d`
after independent code review PASS. Its captured-document validation extraction
preserves the existing public wrappers; 17 narrow and 127 integrated cases
passed, including real public helper run/resume. Earlier `9bb4b207` at
`d4dc1ea7` retains producer lowering schema in typed snapshots (12 affected
cases passed); R12-A `0d7e4bc6` at `18a442da` passed 55 command-template/control
cases and three public/helper checks. Task 6 overall remains open. Exact source pins, commands,
metadata and evidence limits are in the single report's synchronization section;
these results do not pass a dynamic gate or advance frozen comparison controls.

## Finite Tranches And Decision Record

| Tranche | Current state | Entry / bounded exit |
| --- | --- | --- |
| DC-0 — qualify exact scope and controls | Complete; independent Design and qualification reviews PASS | Produce the inventory, pinned controls, exact finite case list and reviewed spike patch scope below; do not implement a production target |
| DC-1 — feasibility spike | Complete; DC-F owner continue on 2026-10-02 | One isolated non-resuming candidate, real strict boundaries and an authored `.orc` specimen, independent review and DC-F evidence; stop at DC-F |
| DC-2 — utility comparison | All 110 cases executed; code/conformity PASS at `4728b14e`; independent document/utility review PASS; owner decision pending | Full protocols and edits/diagnostics recorded in the existing report's DC-U packet; owner disposition pending |
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
DC-U owner disposition on the independently reviewed packet;
DC-F continue was explicitly selected by the owner on 2026-10-02. Existing
executable selectors have no new item to consume.

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
separates the pure results from the later combined DC-F evidence in report §7. DC-1b's fixed
compiled-leaf seam and DC-1c's source grammar/cases were subsequently qualified.
**DC-1c authored composition is now implemented and independently reviewed**:
the [runnable specimen](../../experiments/dynamic_core_evaluation/README.md)
defines unannotated helpers, returns/stores/selects closures using a real
validated leaf result and calls a second typed boundary. Existing declarations,
reader and contract compiler retain their owners. This source proof precedes
full typed Phase 3 or W3 delivery; it does not establish full consumer utility.
The combined evidence passed: 84 candidate cases, nine public CLI controls and
71 documentation-routing cases, plus the exact README demonstration. Code is
committed at `53032343`; the single report records independent review and
limitations. On 2026-10-02 the owner explicitly selected **continue to DC-2**
after reviewing this decision packet. This completes DC-F and activates only
the finite utility comparison; DC-U/DC-P and adoption remain pending.

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
Record actual receipts with DC-1c's source/leaf integration evidence; tests alone
do not select DC-F or DC-2.

**DC-1c bounded handoff:** proposal §6.3 owns the experimental source grammar;
[report §5](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#dc-1c-source-scope)
records twelve source cases and four new paths. Reuse the existing reader and
DC-1b leaves; infer captures and lower to the same checked artifact. Qualify
this scope while DC-1b executes. Independent source lowering may proceed in
parallel against the frozen artifact contract, on its four exclusive paths;
combined source/leaf verification follows DC-1b review. Its runnable specimen
and before/after excerpt are required before
DC-F; public syntax, full consumer migration and production adoption remain
outside this slice. Independent source-contract and finite-scope review passed;
ordinary call arity remains a runtime check, with explicit S08 evidence.

**Artifacts:** create `experiments/dynamic_core_evaluation/` only when this task
runs; use a minimal candidate module and `.orc` specimens there, and
`tests/experiments/test_dynamic_core_evaluation.py`. Append actual evidence to the
single report above. Before creation, DC-0 records exact module/fixture paths and
exclusive shared-owner edits. No new production evaluator/CLI route is authorized
merely by these planned paths.

- [x] Write failing behavioral/admission cases for the matrix below and run
  `python -m pytest --collect-only -q tests/experiments/test_dynamic_core_evaluation.py`.
- [x] Implement ordinary dynamic values/functions/lexical closures in the bounded
  candidate after importing the required upstream shared progress; reuse the
  pure catalog and admitted effect boundaries. One helper body must work
  with different internal values without specialization.
- [x] Replace candidate P5 with checked lexical scope/code targets, schema and
  effect bindings and versioned artifact read-back; never disable
  validation or lower dynamic functions back into typed specialization.
- [x] Run the narrow module, correct only demonstrated defects, run one orchestrator
  or demo integration smoke, and record the exact invocation and limitations.
  Spike-driver evidence is labeled experimental, never public production support.
- [x] Obtain independent code/design review of feasibility and record DC-F's owner
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

**Selected, 2026-10-02:** owner answered “Continuar a DC-2 (recomendado)” to
the completed DC-F packet at code `53032343` / evidence `40fbdf8f`. Qualify and
execute the finite cases below with independent review; do not request another
start authorization. Effect tracking/resume remain accepted losses. No paid
calls, public target or adoption are authorized. Entry synchronization found
integration `9bb4b207` and source `0f1bbc46` unchanged; both are already imported.

**Artifacts:** extend the same candidate/fixtures and report; preserve production
`std/improve` and maintained consumers until a destination is authorized. Reuse
`experiments/orc_repetition_census/variants/` as labeled W1/W3 comparisons.

### Finite Execution Handoff

The [proposal §6.4](../design/workflow_lisp_dynamic_core_proposal.md#64-bounded-complete-consumer-comparison)
owns the additional experimental semantics. The [report §8](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#8-dc-2-finite-utility-scope)
is the sole case inventory: **110 new logical cases**, including the fixed
72-search vector. Its case inventory is preserved alongside actual execution
receipts and the DC-U packet; planned rows alone are not passed tests. Its case
IDs must appear in test names or parameter IDs; keep any implementation-level
parameterization count separately in the execution receipt.

**Approach and cost:** extend the existing evaluator only for the collection
operations and explicit failure needed by these protocols; reuse recursion,
closures and compiled boundary owners. This keeps full module/import support,
source maps and recovery out of this experiment; source assembly remains driver
tooling, and errors/restarts can occur after external work.

Keep qualification pin `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` and the
105-control inventory in report §1 unchanged. `f9c75e93` records DC-2 selection,
not a new comparator pin. Compare the control source content against that pin
before execution; if an upstream import changes relevant behavior, explicitly
record and review the re-pin and rerun affected comparisons. The coordinator
owns synchronization and final integration; no implementer edits upstream
worktrees or manufactures a replacement performer.

DC-0 collected all 105 controls but did not run every case. DC-2 must execute
all 20 improve, 76 paired-fixture and nine CLI controls using their frozen source
files and record the exact current runtime revision separately. The combined
check below includes all three modules. Preserve the 84 existing DC-1 candidate
tests as regression evidence, with their original case IDs/files unchanged;
neither count absorbs the 110 new observations. Known unrelated inherited
failures remain documented and no global-suite PASS is claimed.

| Sequential batch and role | Exclusive writable implementation paths | Required cases and completion |
| --- | --- | --- |
| DC-2a — code implementation, bounded core; complete at `e7da6fd2` | `experiments/dynamic_core_evaluation/{program,source,evaluator,leaf_bridge}.py`; `tests/experiments/test_dynamic_core_utility_core.py` | UC01–UC12, including the two bridge groups; `/3` additions with frozen `/1` and `/2` admission; existing certified command adapter reaches the current compiler/executor |
| DC-2b — code implementation, improve; complete at `18121c76` | `experiments/dynamic_core_evaluation/fixtures/improve.orc`; `experiments/dynamic_core_evaluation/fixtures/utility_leaves.orc`; `tests/experiments/test_dynamic_core_utility_improve.py` | UI01–UI11; full outcomes, payloads, failures and hook order; typed domain contracts retained |
| DC-2c — code implementation, search; complete at `e31e8282` | `experiments/dynamic_core_evaluation/fixtures/search.orc`; the same `fixtures/utility_leaves.orc` after DC-2b releases it; `tests/experiments/test_dynamic_core_utility_search.py`; improve test `_dynamic_run` binding setup only | US01's 72 pairs plus US02–US06; complete values, ordered requests, spend and exhaustion; rerun UI01–UI11 after shared-module integration |
| DC-2d — code implementation, paired edits and diagnostics; complete at `4728b14e` | `tests/experiments/test_dynamic_core_utility_edits.py`; the two new consumer test modules only for small reused setup functions; `experiments/dynamic_core_evaluation/README.md` | UE01–UE04 and UD01–UD06; corrected receipts, final 10 passed in 8.89s, code/conformity PASS; exact full-consumer demo passed |
| DC-2e — independent code/utility review and coordinator integration; independent reviews PASS | This plan and the same report; corrections return to the relevant implementer | Code findings closed; coordinator inspected final diff/receipts; 370-case integration plus affected ten-case supplement; DC-U packet independently reviewed and awaiting owner disposition |

No new helper framework, test registry, report family, schema converter, public
CLI route or production stdlib migration belongs to these batches. The utility
leaf module retains search's `Candidate` name for its existing adapter binding,
uses `Draft` for improve, and imports existing `Decision`/`Improvement`
declarations. Its adapter bindings reuse
`experiments/mlevolve_pair/commands_compact.json`; scripted fixture response
data and Python reference logic stay owned by the frozen control tests.

DC-2c setup handoff, 2026-10-02: the compiler validates every workflow in the
shared module, including unselected adapter leaves. The improve test's
`_dynamic_run` therefore also loads the exact existing adapter bindings and
leaf files via `compact_controller(root)`, merging them with its probe bindings.
This narrow adjacent setup edit is authorized; no module rename is needed.
A fresh direct-adapter compile disproved the initial supposed `owner_module`
equality restriction. Preserve the original manifest and all improve behavior;
verify the eleven improve cases again when adding the search leaves.

`fixtures/improve.orc` contains the shared ordinary helper definitions; the
experiment driver explicitly assembles these with a caller/header. Compare
assembled and inline source as tooling, never as implemented dynamic imports.
`fixtures/search.orc` contains the complete authored search controller. Preserve
precise result/domain schemas at their boundaries; do not use `Value` to evade
an outcome contract. Any required wire-field reconstruction is visible authored
code and part of the authoring cost.

For each batch, use the AGENTS implementation model and a distinct review model.
Write the listed failing cases, run collection and narrow failures, implement
the smallest fix, run the narrow module and obtain independent review before
the next batch changes its files. Return bounded corrections to the author;
new semantic decisions return to Design. No second owner start approval is
needed. Required command shapes, from the worktree root:

```bash
# Collect new/renamed cases once their modules exist.
python -m pytest --collect-only -q tests/experiments/test_dynamic_core_utility_core.py tests/experiments/test_dynamic_core_utility_improve.py tests/experiments/test_dynamic_core_utility_search.py tests/experiments/test_dynamic_core_utility_edits.py
# Narrow red/green selection, replacing UC with UI, US, UE or UD as appropriate.
python -m pytest -q tests/experiments/test_dynamic_core_utility_core.py
python -m pytest -q tests/experiments/test_dynamic_core_utility_improve.py
python -m pytest -q tests/experiments/test_dynamic_core_utility_search.py
python -m pytest -q tests/experiments/test_dynamic_core_utility_edits.py
```

Run slower consumer matrices and the following combined impacted check in tmux,
using the tmux skill and `-n 16 --dist=worksteal`. Narrow selectors come first;
reuse valid receipts unless subsequent changes affect them.

```bash
python -m pytest -q -n 16 --dist=worksteal tests/experiments/test_dynamic_core_evaluation.py tests/experiments/test_dynamic_core_boundaries.py tests/experiments/test_dynamic_core_source.py tests/experiments/test_dynamic_core_utility_core.py tests/experiments/test_dynamic_core_utility_improve.py tests/experiments/test_dynamic_core_utility_search.py tests/experiments/test_dynamic_core_utility_edits.py tests/test_workflow_lisp_improve_stdlib.py tests/experiments/test_mlevolve_pair_fixture.py tests/test_workflow_evaluated_cli.py tests/test_workflow_lisp_drain_roadmap_routing.py
```

DC-2d supplies the exact full-consumer README command; the coordinator must run
it and retain its fresh output in this report before claiming completion. It
must admit the disk-written source artifact and exercise real local compiled
leaves, with no paid calls. Existing public improve run/resume and evaluated CLI
tests are public-route controls; the new demo remains an experimental route.
Record exact revisions, commands, collected counts, exits, comparison outputs
and independent review findings. Do not total overlapping selectors as distinct
coverage or interpret a green parity matrix as a utility/adoption decision.

### DC-U Completion Checklist

- [x] Port full `improve`: APPROVE, REVISE, BLOCKED, EXHAUSTED; latest revised
  candidate and evidence/reason payloads; zero limit rejected before hooks;
  invalid hook output and final-iteration revision failures remain failures;
  imported/inline fresh-run order agrees with the control. Record committed-hook
  reuse as a lost capability of the non-resuming candidate, not a parity failure.
- [x] Port full paired-search policy: seed ranking, strict improvement/ties,
  invalid evaluation, one same-branch repair, stalls, one fusion, full history,
  budget/score stops, invalid budgets and exhaustion. Run all 72 existing
  scenario/budget pairs (nine scenarios × eight budgets) owned by
  [the fixture](../../tests/experiments/test_mlevolve_pair_fixture.py) against
  the Python reference. Schema-invalid transport
  is not domain `valid=false`; compare ordered decisions, spend and final value.
- [x] Perform four paired edits: add a state field, change review payload, capture
  context, extract a helper. Record touched sites, duplicated facts, concepts,
  repairs and diagnosis. Preserve useful domain schemas/types instead of counting
  their removal as a gain. State errors found before and after costly effects;
  compare repeated calls/cost and partial outputs after interruption/restart.
- [x] Compare the best **implemented** typed baseline and the proposed W1/W3
  improvement honestly. If W1/W3 cannot execute, label it a counterfactual and
  narrow the unique-gain claim; no requirement to build both languages first.
- [x] Inventory actual added/retained/displaced owners, validators, specialization
  paths, identity forms and compatibility costs. Include budget/runtime
  diagnostics, lost static checks/recovery and old-target retention; LOC alone is not a
  complexity or authoring verdict. No paid-provider quality/cost conclusion from
  scripted leaves or an unbudgeted authoring study.
- [x] Run narrow parity/integration checks and independent utility review; record
  supported, adverse, missing and untested evidence separately, then DC-U.

Execution receipts are in the [report's DC-U packet](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#dc-u-evidence-packet):
370 passed in 12.54s at synchronized runtime `bcc4ee13`, followed by final
10 passed in 8.89s after two evidence-only test corrections, code `4728b14e`.
The full-consumer README demo passed with 196 steps and four real local calls.
These checks do not erase the inherited red baseline or establish a full-suite
PASS. The packet records mixed author-edit costs, late error detection and
8 dynamic versus 6 typed calls across interruption/completion, plus zero
production owners removed. Independent document/utility review by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh) passed with no blocking
findings. Final routing verification is recorded with the packet; this review
does not select DC-U continue.

**DC-U:** owner judges meaningful authoring/reuse benefit beyond the incumbent and
credible W1/W3 gains, preserved fresh-run domain protocols, useful diagnostics
including late errors, and net complexity after compatibility. Explicitly weigh
lost effect tracking and resumability against those gains; neither loss alone
requires rejection. Passing fresh-run parity establishes
correctness only. Continue selects named DC-3 readiness work; stop retains typed
execution and may qualify W3 under its existing plan, without shipping closures.

**Owner disposition: PENDING.** The packet recommends continue only to bounded
DC-3 readiness qualification. Its proposed named scope is a readiness plan for
the complete-consumer dynamic profile: target/artifact/import/stdlib and old-run
owner contracts; one named maintained-consumer destination; actual removal and
compatibility inventory; needed shared runtime and public execution/inspection
qualification. The owner must select that finite scope before it executes.
This recommendation allocates no production target, migration, live/paid calls,
parallel effects or child-run expansion. Revise or stop remain available under
the existing finite gate policy.

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
