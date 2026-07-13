# Procedure-First Stage 4 Design And Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept and route one procedure-first frontend contract, review a complete current reusable-call inventory, and leave independently executable Stage 5 plans for the pilot and migration waves.

**Architecture:** The Workflow Lisp frontend specification remains semantic authority. A focused companion delta records rationale, classification, migration, and non-candidate rules; the stable rules are merged into the parent specification and authoring guide. A machine-readable inventory keeps internal calls separate from public entries, and Stage 5 plans consume that inventory without deriving implementation authority from the historical diagnostic report.

**Tech Stack:** Markdown design/specification documents, JSON inventory, Workflow Lisp `.orc` sources, Python/pytest verification, existing route-readiness and migration-parity tooling.

**Status (2026-07-13): complete.** Tasks 1–4 are committed and independently
reviewed. Holistic Gate S4 review returned `GATE S4 SPEC PASS` and `GATE S4
QUALITY PASS`; the post-closeout status guard matched exactly the seven
protected user-owned paths. The current selector is typed result guidance.

---

## Locked decisions and constraints

- Workflows are durable public run/resume/invocation/publication boundaries; typed procedures are the normal internal reuse unit.
- Use a role-based hybrid lowering model. Procedure-first migrations select `:lowering inline`; `:lowering private-workflow` requires an explicit private state/resume/debug namespace. `auto` remains compatible for identity-free code but is not a stable persisted-route promise.
- Direct and caller-visible transitive effects are distinct. ProcRef resolution and specialization must recompute caller-visible transitive effects before lowering.
- Native transportable returns and direct-root `__result__` carriage are settled; typed result guidance remains the existing Stage 5 wave 2.
- Runtime closures, runtime procedure values, dynamic dispatch, hidden effects, implicit publication, and silent checkpoint remapping remain out of scope.
- Preserve these seven unrelated dirty paths; stage only files named by a task:
  - `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
  - `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
  - `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
  - `tests/test_workflow_non_progress_step_back_demo.py`
  - `workflows/examples/non_progress_step_back_demo.yaml`
  - `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

## Task 1: Publish The Reviewed Reuse Inventory

**Files:**
- Create: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Create: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`

- [x] **Step 1: Generate inventory records from current authored `workflows/` sources**

Record internal calls separately from public entries. Exclude templates, runtime fixtures, generated sources, and test fixtures from actionable totals while retaining exclusion counts.
Record `git rev-parse HEAD` as `source_commit`, the exact `rg`/structured-parser
extraction commands, included roots, and excluded roots. If the source commit
changes before review, regenerate rather than preserving old totals.

- [x] **Step 2: Classify every actionable internal call**

Use exactly `procedure-candidate`, `effect-adapter`, or `legacy-retire` for internal calls. Use `public-boundary` only on separate public-entry records. Every effect adapter must name the missing proof/substrate obligation.

- [x] **Step 3: Validate the JSON and reconcile totals**

Run:

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
```

Expected at source commit `f6da1b89bd7d3fa11281ec57a38b9188e7c51b6e`:
exit 0, with 96 actionable/retained internal calls: 33 procedure candidates,
25 effect adapters, and 38 legacy-retire sites. Reconcile those totals against
the recorded extraction output; a later source commit may change the totals if
the report explains the delta rather than forcing the historical count.

- [x] **Step 4: Document feasibility cases and uncertainty**

The report must include `backlog-drain-proc`, an ordinary non-drain positive candidate, and a negative public boundary. It must identify which classifications are conservative and what evidence can reclassify them.

- [x] **Step 5: Obtain specification and quality reviews and resolve findings**

The specification review checks every actionable source row, classification
vocabulary, public-entry separation, feasibility case, exclusion, count, and
provenance field. The quality review checks reproducibility, schema clarity,
stable IDs, uncertainty, and routing usefulness. Rerun both whole reviews after
fixes until both pass.

- [x] **Step 6: Commit the reviewed inventory only**

```bash
git add docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/plans/2026-07-13-procedure-first-reuse-inventory.md
git commit -m "Inventory procedure-first reuse boundaries"
```

## Task 2: Accept The Procedure-First Frontend Contract

**Files:**
- Create: `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_parametric_type_system.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/design/README.md`

- [x] **Step 1: Write the focused frontend delta**

Define boundary roles, typed-return compatibility, direct versus transitive effects, supported composed effects, lowering/identity policy, migration tests, non-candidates, feasibility evidence, acceptance, and non-goals.

- [x] **Step 2: Merge stable rules into the parent frontend specification**

Update the lifecycle/companion list, `defproc`/`defworkflow` boundary roles, composition/effect rules, elaboration/checkpoint ownership, and procedure-lowering policy. Remove the stale open `WorkflowRef` choice by retaining compile-time-only refs.

- [x] **Step 3: Reconcile stale companion authority**

Clarify that generic procedure declarations retain direct body effects while specialization recomputes caller-visible transitive effects. Revise the drafting guide so reusable/library code does not imply `defworkflow`, and document explicit lowering choices for identity-sensitive routes.

- [x] **Step 4: Update design routing**

Add the accepted delta to `docs/design/README.md` and make the frontend specification the durable semantic owner.

- [x] **Step 5: Run focused consistency checks**

```bash
rg -n "another workflow should call|belongs in a reusable workflow library|Need decide whether workflow references|not folded into the generic.*summar" docs/design/workflow_lisp_frontend_specification.md docs/design/workflow_lisp_parametric_type_system.md docs/lisp_workflow_drafting_guide.md
git diff --check -- docs/design/workflow_lisp_procedure_first_reuse_contract.md docs/design/workflow_lisp_frontend_specification.md docs/design/workflow_lisp_parametric_type_system.md docs/lisp_workflow_drafting_guide.md docs/design/README.md
```

Expected: no stale rule remains; the scoped whitespace check exits 0.

- [x] **Step 6: Obtain specification and quality reviews and resolve findings**

The specification review checks the complete Stage 4 contract, authority
placement, effect algebra, identity rules, migration/non-candidate tests, and
native-return compatibility. The quality review checks coherence, duplication,
stale wording, and drafting-guide usability. Rerun both whole reviews after
fixes until both pass.

- [x] **Step 7: Commit the accepted contract only**

```bash
git add docs/design/workflow_lisp_procedure_first_reuse_contract.md docs/design/workflow_lisp_frontend_specification.md docs/design/workflow_lisp_parametric_type_system.md docs/lisp_workflow_drafting_guide.md docs/design/README.md
git commit -m "Define the procedure-first reuse contract"
```

## Task 3: Write Independently Executable Stage 5 Plans

**Files:**
- Create: `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
- Create: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Create conditionally: `docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md`
- Inspect: `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`

- [x] **Step 1: Rebaseline the existing typed-guidance substrate plan**

Confirm it remains the first pending Stage 5 implementation wave and that no Stage 4 decision changes direct-root or guidance semantics. Record any owner-anchor updates in the roadmap rather than duplicating its tasks.

- [x] **Step 2: Write the pilot implementation plan**

Use one small non-public `.orc` workflow family with real effects and typed returns. Require TDD, explicit `:lowering inline`, output/artifact/source-map/effect/checkpoint comparison, compile plus dry-run, an end-to-end usage check, and preservation of the public wrapper.

- [x] **Step 3: Write the migration-waves plan**

Consume inventory records in order: pure/library procedure candidates, effect-adapter reclassification, production families, then compatibility retirement. Each family must have computed migration parity and public-boundary negative coverage.

- [x] **Step 4: Audit and separately plan any proven substrate gaps**

Compare each `effect-adapter` obligation with implemented procedure effect
joining, lowering, source-map, checkpoint, publication, and child-workflow
tests. If an independently testable implementation gap remains, create
`docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md` with TDD tasks
that land before the pilot. If no code gap remains, record a path-by-path
evidence table in the migration-waves plan and explicitly select no Stage 5
step-3 implementation wave; do not manufacture substrate work from stale prose.

- [x] **Step 5: Review plan independence and exact commands**

Each plan must name exact files, tests, red/green steps, parity evidence, commit boundaries, and stop conditions. Do not combine shared compiler substrate changes with a family migration.

- [x] **Step 6: Obtain specification and quality reviews and resolve findings**

The specification review checks Stage 5 ordering, substrate disposition,
public-wrapper preservation, exact family scope, and all migration evidence.
The quality review checks task granularity, runnable commands, TDD ordering,
commit scope, and handoff usability. Rerun both whole reviews after fixes until
both pass.

- [x] **Step 7: Commit the reviewed Stage 5 plans only**

```bash
git add docs/plans/2026-07-13-procedure-first-pilot-plan.md docs/plans/2026-07-13-procedure-first-migration-waves-plan.md
# Add docs/plans/2026-07-13-procedure-first-substrate-gaps-plan.md only if the audited gap exists.
git commit -m "Plan procedure-first pilot and migration waves"
```

## Task 4: Close Gate S4 And Advance The Roadmap

**Files:**
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-13-procedure-first-stage4-design-and-planning.md`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md`

- [x] **Step 1: Obtain final independent specification and quality reviews**

Review the committed delta, parent merge, inventory, and implementation plans
against every Gate S4 clause. This is a holistic gate review in addition to the
pre-commit task reviews. Resolve issues in explicit review-fix commits scoped
to the affected Task 1–3 files, then rerun both full reviews until both pass.

- [x] **Step 2: Record the reviewed Gate S4 evidence**

Mark Tasks 1–3 complete only from committed files and fresh validation. Record review results, exact inventory totals, compatibility with native returns/guidance, and any intentional deferred substrate work.

- [x] **Step 3: Advance the current selector**

Set the live selector to Stage 5 wave 2, typed result guidance. Do not select the pilot before the guidance plan completion gate.

- [x] **Step 4: Update routing and capability status**

Route the accepted procedure-first contract and inventory from `docs/index.md`; add or update the capability matrix row to distinguish accepted language contract from family adoption.

- [x] **Step 5: Run final documentation and routing checks**

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
rg -n "current selector|Stage 4|Stage 5|procedure-first" docs/index.md docs/capability_status_matrix.md docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md
git diff --check -- docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-13-procedure-first-stage4-design-and-planning.md docs/index.md docs/capability_status_matrix.md
```

Expected: S4 is consistently satisfied, the current selector is typed result
guidance, and the four closeout files pass the scoped whitespace check before
staging.

- [x] **Step 6: Commit the S4 closeout only**

```bash
git add docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-13-procedure-first-stage4-design-and-planning.md docs/index.md docs/capability_status_matrix.md
git diff --cached --check
git commit -m "Close procedure-first design gate"
```

- [x] **Step 7: Verify the post-commit protected-tree baseline**

```bash
git status --short
```

Expected: the four closeout files are absent and the output matches the initial
guard baseline exactly: only the seven protected user-owned paths remain
unstaged/dirty. Do not restore or rewrite them.
