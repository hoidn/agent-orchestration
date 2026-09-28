# Composition-First Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Steps use checkbox (`- [ ]`) syntax for tracking. Keep one write-capable
> implementer active at a time for overlapping owners.

**Goal:** Deliver the whole composition-first design: value-returning
procedures through generic unions, the `improve` helper, migration of every
`review-revise-loop` consumer, and retirement of the displaced declarations.

**Architecture:** Five phases, each producing working, tested software on its
own. The language and library land first at target 2.33; consumers then
migrate through domain-owned adapters that preserve their validation and
public results; the legacy helper is retired per declaration only when no
consumer remains. No runtime type values, no new evaluator, no history or
budget framework.

**Tech Stack:** Python, Workflow Lisp (`.orc`) frontend and WCC lowering,
shared executable validation, the existing executor and run storage,
pytest/pytest-xdist, command-backed and patched-provider deterministic hooks.

**Spec:** [Composition-first design](../design/workflow_lisp_composition_first.md)
and the [generic-union section](../design/workflow_lisp_parametric_type_system.md#proposed-cf-1-first-order-generic-unions)
of the parametric type-system design. The spec is the authority; this plan is
its argument.

## Global Constraints

- Target **2.33** admits `defunion :forall`, type applications, and
  `std/improve`. Targets up to 2.32 reject them with a required-target
  diagnostic.
- `improve` has exactly the design §3 interface: `:forall (S I F B)`,
  `:where ((S is-record))`, parameters `initial`, `inputs`, `review`,
  `revise`, `limit`, result `Improvement[S F B]`. No `ctx`, no seeds, no
  counter, no positive-limit precondition.
- `EXHAUSTED` carries `value` only. The final permitted iteration may end in
  an unreviewed revision. Runtime failures never become `EXHAUSTED`.
- The provider route is concrete `defprompt` results converted by domain
  adapters. Direct generic `defprompt` results are out of scope.
- Legacy `ReviewFindings.v1` validation runs before findings are published
  and before the fixer consumes them, including after resume. The schema is
  neither tightened nor weakened.
- No compiler branch keyed to `Decision`, `Improvement`, `Outcome`, or
  `std/improve`.
- Retirement is per declaration. `with-phase`, `phase-scope`, path types, and
  other independently used `std/phase` exports stay.
- No checkpoint compatibility between the legacy and new APIs. Old
  checkpoints are not reinterpreted. In-flight runs finish on the source they
  started with.
- Tests assert behavior, contracts, and diagnostic codes, never prompt text or
  message phrasing. Deterministic hooks are command-backed or use a patched
  provider executor; a pure inline hook as a loop-body `match` scrutinee is
  not supported by the frontend.
- Verification order: narrow selectors, then `pytest -q -n 16
  --dist=worksteal` in tmux, then the public compile/run/resume path.
- Commits use pathspec (`git commit -- <paths>`) and carry no assistant
  attribution.

## Review Focus

Conditions the spec implies that a person using this software is most likely
to hit. Each is pinned by a test in the task that owns the code.

1. **`limit` is zero.** Expected: the existing zero-limit runtime outcome; no
   fabricated review, no seed report. Owner: CF-1b Task 5.
2. **The `revise` hook fails in the final permitted iteration.** Expected: a
   runtime failure under the existing recovery contract, not `EXHAUSTED`.
   Owner: CF-1b Task 5.
3. **A findings artifact disappears between a committed review and the
   resumed revision.** Expected: the revision adapter's validation fails
   closed and no fixer runs. Owner: Task 9.
4. **A substituted reviewer's inner review is blocked.** Expected: the
   adjudicating procedure returns `BLOCKED` with the domain blocker, never a
   downgraded `REVISE` or `APPROVE`. Owner: CF-1b Task 6.
5. **A target-2.32 module imports `std/improve`.** Expected: rejection with
   the required-target diagnostic, not a late type error. Owner: CF-1b Task 5.

## Coverage Map

| Design section | Covered by |
| --- | --- |
| §1 Decision | Phases 1–2 |
| §3 Interface, §4 Loop and termination | CF-1b Tasks 5–6; Phase 0 for final-state selection |
| §5 Boundaries: typed feedback, legacy validation | CF-1b Task 5; Tasks 8–10, 12 |
| §5 Boundaries: documents, inputs | Tasks 9–10, 12 (path-bearing subjects keep today's semantics) |
| §6 Language delta | CF-1b Tasks 1–4 |
| §7 Effects | CF-1b Task 5 (forwarding regime); Task 15 (after EL-1) |
| §8 Migration | Tasks 8–10, 12–14 |
| §9 Feasibility obligations | Phase 0; CF-1b Tasks 4–6 |
| §10 Evidence requirements | CF-1b Tasks 5–6; Tasks 9–11 |
| Fixer-side blockage, generic records, snapshots, generic prompt results | Phase 4, entry conditions only |

## Consumer Inventory

Every `std/phase` importer at `26148c7f`, by declaration:

| File | Uses `review-revise-loop` | Other `std/phase` imports | Migrated by |
| --- | --- | --- | --- |
| `workflows/examples/review_revise_design_docs.orc` | yes, `:max 20` | review types | Task 9 |
| `workflows/examples/kiss_backlog_item.orc` | yes, twice, `:max 3` and `:max 5` | review types, `with-phase` | Task 10 |
| `workflows/library/lisp_frontend_design_delta/plan_phase.orc` | yes, `:max 12` | review types, `with-phase` | Task 12 |
| `workflows/library/lisp_frontend_design_delta/implementation_phase.orc` | yes, `:max 40` | review types, `with-phase` | Task 12 |
| `workflows/examples/review_revise_parametric_design_docs.orc` | yes, provider/prompt macro form | `ReviewFindings`, `with-phase` | Task 13 |
| `workflows/library/lisp_frontend_design_delta/types.orc` | no | review types | unchanged |
| `workflows/examples/review_revise_design_docs_judgment_panel.orc` | no | `ReviewReportPath` | target alignment in Task 9 |
| `workflows/examples/with_phase_composed_binding.orc` | no | `with-phase` | unchanged |

---

## Phase 0: Runtime Prerequisites

Owned by [`2026-09-28-cf1-runtime-prerequisites.md`](2026-09-28-cf1-runtime-prerequisites.md).
Not duplicated here. Phase 0 is complete when, on `main`:

- [ ] `tests/test_workflow_lisp_generic_state_exhaustion.py::test_generic_record_state_exhaustion_returns_final_continue`
  passes without an `xfail` marker.
- [ ] An executed `std/phase` review loop with two or more iterations returns
  the final review's metadata on exhaustion.
- [ ] The generic exhaustion path passes after committed-boundary resume.
- [ ] Adjacent loop, rich-value, resume, and structured-control-flow suites
  pass, and the full suite shows no new failures against the recorded
  baseline.

Phase 0 blocks only the exhaustion assertions in CF-1b Tasks 5–6 and
everything in Phases 2–3.

## Phase 1: Language And Library (CF-1b)

Owned by the [CF-1b plan](2026-09-28-cf1b-composition-first-implementation-plan.md),
Tasks 1–7. Not duplicated here. Its SDD ledger is the progress authority.

| Task | Deliverable |
| --- | --- |
| 1 | Target 2.33 registered |
| 2 | `defunion :forall` and type applications, with diagnostics |
| 3 | Argument binding through `ProcRef` signatures; constructor identity |
| 4 | Instantiation through specialization; transport, loop state, resume |
| 5 | `std/improve` module |
| 6 | Structured-value example with public compile/run/resume |
| 7 | Documentation promotion |

Phase 1 is complete when Tasks 1–7 are reviewed, the full suite shows no new
failures, and the branch is merged to `main`.

## Phase 2: Consumer Migration (CF-1c)

Requires owner selection in the roadmap, Phase 0 and Phase 1 on `main`, and a
fresh worktree `.worktrees/cf1c-consumer-migration`. No consumer with a run in
flight is migrated until that run finishes.

**The absence case.** `.orc` has no failure form and the type system cannot
express "the limit is positive", so a consumer that keeps previous-review
metadata on exhaustion must type the case where no review preceded
exhaustion. Each migrated consumer adds one variant to its public result for
that case. It is reachable only with a zero limit.

### Task 8: Review Domain Module

**Files:**
- Create: `orchestrator/workflow_lisp/stdlib_modules/std/review.orc`
- Test: `tests/test_workflow_lisp_review_domain.py`

**Interfaces:**
- Consumes: `std/phase` exports `BlockerClass`, `ReviewFindings`,
  `ReviewReportPath`; command boundary `validate_review_findings_v1`.
- Produces: `std/review` exports `ReviewEvidence`, `ReviewBlocker`,
  `RevisionHistory`, `validate-findings`.

- [ ] **Step 1: Write the failing tests.** In
  `tests/test_workflow_lisp_review_domain.py`, compile a 2.33 module that
  imports `std/review` and: constructs `ReviewEvidence` and `ReviewBlocker`;
  matches `RevisionHistory` exhaustively; calls `validate-findings` on a
  findings carrier whose JSON has an `items` key (passes) and on one whose
  file is missing (fails with `review_findings_missing_artifact`) and one
  without `items` (fails with `review_findings_bundle_schema_invalid`). Use
  `validate_review_findings_v1_binding()` from
  `tests/workflow_lisp_command_boundaries.py` and run through the executor as
  `tests/test_workflow_lisp_generic_state_exhaustion.py` does.
- [ ] **Step 2: Run them and confirm they fail** because `std/review` does
  not resolve. Run: `pytest -q tests/test_workflow_lisp_review_domain.py`.
- [ ] **Step 3: Author the module.**

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule std/review)
  (import std/phase :only (BlockerClass ReviewFindings ReviewReportPath))
  (export ReviewEvidence ReviewBlocker RevisionHistory validate-findings)
  (defrecord ReviewEvidence
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (defrecord ReviewBlocker
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings))
  (defunion RevisionHistory
    (UNREVIEWED)
    (REVISED_FROM
      (evidence ReviewEvidence)))
  (defproc validate-findings
    ((findings ReviewFindings))
    -> ReviewFindings
    :effects ((uses-command validate_review_findings_v1))
    :lowering inline
    (command-result validate_review_findings_v1
      :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" findings.schema_version findings.items_path)
      :returns ReviewFindings)))
```

- [ ] **Step 4: Run the tests and confirm they pass.** Also run
  `pytest -q tests/test_workflow_lisp_phase_stdlib.py
  tests/test_workflow_lisp_modules.py`.
- [ ] **Step 5: Commit.** `git commit -m "feat: add std/review domain module" --
  orchestrator/workflow_lisp/stdlib_modules/std/review.orc
  tests/test_workflow_lisp_review_domain.py`

### Task 9: Migrate The Design-Docs Example

**Files:**
- Modify: `workflows/examples/review_revise_design_docs.orc`
- Modify: `workflows/examples/review_revise_design_docs_judgment_panel.orc`
  (target only, so the same-target importer keeps compiling)
- Test: `tests/test_workflow_lisp_examples.py`,
  `tests/test_workflow_lisp_design_docs_improve_e2e.py` (create)

**Interfaces:**
- Consumes: `std/improve` (`Decision`, `Improvement`, `improve`); `std/review`
  (Task 8); the unchanged procedures `review-design-docs` and
  `fix-design-doc`.
- Produces: the workflow `review-revise-design-docs` with its existing inputs
  and a result union that keeps `APPROVED`, `BLOCKED`, and `EXHAUSTED` with
  their current fields and adds `(EXHAUSTED_UNREVIEWED (reason String))`.

- [ ] **Step 1: Write the failing tests.** In the new e2e module, with a
  patched provider executor as in
  `tests/test_workflow_lisp_rich_loop_values_e2e.py`: (a) first review
  approves, result `APPROVED` with that review's report and findings;
  (b) reviewer blocks, result `BLOCKED` with report, findings, and blocker
  class; (c) twenty `REVISE` decisions, result `EXHAUSTED` whose
  `last_review_report` and `findings` are the twentieth review's, which is the
  feedback the final revision responded to; (d) findings without `items` fail
  at the adapter and no fixer call is recorded; (e) **Review Focus 3:**
  interrupt after the first committed review, delete the findings file, resume,
  and assert the run fails with `review_findings_missing_artifact` and no
  fixer call is recorded. Keep the existing example tests unchanged.
- [ ] **Step 2: Run them and confirm they fail.**
  Run: `pytest -q tests/test_workflow_lisp_design_docs_improve_e2e.py`.
- [ ] **Step 3: Migrate the source.** Set `(:target-dsl "2.33")` in both
  files. Replace the `std/phase` import of `ReviewLoopResult` and
  `review-revise-loop` with imports of `std/improve` and `std/review`. Add:

```lisp
  (defrecord ReviewedDesignDoc
    (subject DesignDocReviewSubject)
    (history RevisionHistory))

  (defproc review-design-docs-decision
    ((reviewed ReviewedDesignDoc)
     (inputs DesignDocReviewInputs))
    -> Decision[ReviewEvidence ReviewBlocker]
    :effects ((uses-provider providers.design-docs.review)
              (uses-command validate_review_findings_v1))
    :lowering inline
    (let* ((decision (review-design-docs reviewed.subject inputs)))
      (match decision
        ((APPROVE approved)
         (let* ((validated (validate-findings approved.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] APPROVE
             :evidence (record ReviewEvidence
                         :review_report approved.review_report
                         :findings validated))))
        ((REVISE revised)
         (let* ((validated (validate-findings revised.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] REVISE
             :feedback (record ReviewEvidence
                         :review_report revised.review_report
                         :findings validated))))
        ((BLOCKED blocked)
         (let* ((validated (validate-findings blocked.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] BLOCKED
             :reason (record ReviewBlocker
                       :review_report blocked.review_report
                       :blocker_class blocked.blocker_class
                       :findings validated)))))))

  (defproc revise-design-doc
    ((reviewed ReviewedDesignDoc)
     (inputs DesignDocReviewInputs)
     (evidence ReviewEvidence))
    -> ReviewedDesignDoc
    :effects ((uses-provider providers.design-docs.fix)
              (uses-command validate_review_findings_v1))
    :lowering inline
    (let* ((validated (validate-findings evidence.findings))
           (revised (fix-design-doc reviewed.subject inputs validated)))
      (record ReviewedDesignDoc
        :subject revised
        :history (variant RevisionHistory REVISED_FROM :evidence evidence))))
```

  Add `(EXHAUSTED_UNREVIEWED (reason String))` to
  `DesignDocReviewLoopResult`. In the workflow body remove the
  `build-review-runtime-owned` call and the `runtime-owned` binding, and
  replace the macro call and its `match` with:

```lisp
           (improvement
             (improve
               (record ReviewedDesignDoc
                 :subject completed
                 :history (variant RevisionHistory UNREVIEWED))
               inputs
               (proc-ref review-design-docs-decision)
               (proc-ref revise-design-doc)
               20)))
      (match improvement
        ((APPROVED approved)
         (variant DesignDocReviewLoopResult APPROVED
           :checks_report inputs.checks_report
           :review_report approved.evidence.review_report
           :findings approved.evidence.findings))
        ((BLOCKED blocked)
         (variant DesignDocReviewLoopResult BLOCKED
           :progress_report blocked.reason.review_report
           :blocker_class blocked.reason.blocker_class
           :findings blocked.reason.findings))
        ((EXHAUSTED exhausted)
         (match exhausted.value.history
           ((REVISED_FROM revised)
            (variant DesignDocReviewLoopResult EXHAUSTED
              :last_review_report revised.evidence.review_report
              :reason "max_iterations_reached"
              :findings revised.evidence.findings))
           ((UNREVIEWED unreviewed)
            (variant DesignDocReviewLoopResult EXHAUSTED_UNREVIEWED
              :reason "exhausted_before_first_review")))))
```

  Delete `ReviewRuntimeOwned` and `build-review-runtime-owned` if nothing else
  references them. If the generic-union syntax accepted by CF-1b differs from
  the spelling above, use the accepted spelling and record the difference in
  the task report.
- [ ] **Step 4: Run the tests and confirm they pass.** Run the new module,
  `pytest -q tests/test_workflow_lisp_examples.py`, and the README compile
  command for this example.
- [ ] **Step 5: Commit** the two example files and the new test module by
  pathspec.

### Task 10: Migrate The Backlog-Item Example

**Files:**
- Modify: `workflows/examples/kiss_backlog_item.orc`
- Test: `tests/test_workflow_lisp_examples.py`, `tests/test_workflow_lisp_cli.py`,
  `tests/test_workflow_lisp_backlog_item_improve_e2e.py` (create)

**Interfaces:**
- Consumes: `std/improve`, `std/review`; unchanged procedures `review-plan`,
  `fix-plan`, `review-implementation`, `fix-implementation`, whose subject is
  `ReviewableSurfaceResult` and inputs `ReviewContextInputs`.
- Produces: workflow `run-backlog-item` with its existing inputs.
  `ReviewSurfaceResult` becomes a union
  `(REVIEWED (report_path ReviewReportPath)) (UNREVIEWED (reason String))`,
  and `BacklogItemResult` becomes
  `(REVIEWED (summary_path ReviewReportPath)) (UNREVIEWED (reason String))`.

- [ ] **Step 1: Write the failing tests.** With a patched provider executor:
  plan review approves then implementation review exhausts after five
  `REVISE` decisions, result `REVIEWED` with the fifth implementation review's
  report; plan reviewer blocks, the plan review surface is `REVIEWED` with the
  blocking report. Update the compile test and the CLI dry-run test for the
  two union-typed results.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Migrate the source.** Set `(:target-dsl "2.33")`. Import
  `std/improve` and `std/review`; keep `with-phase`. Add one wrapper and four
  adapters:

```lisp
  (defrecord ReviewedSurface
    (subject ReviewableSurfaceResult)
    (history RevisionHistory))

  (defproc review-plan-decision
    ((reviewed ReviewedSurface)
     (inputs ReviewContextInputs))
    -> Decision[ReviewEvidence ReviewBlocker]
    :effects ((uses-provider providers.plan-review)
              (uses-command validate_review_findings_v1))
    :lowering inline
    (let* ((decision (review-plan reviewed.subject inputs)))
      (match decision
        ((APPROVE approved)
         (let* ((validated (validate-findings approved.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] APPROVE
             :evidence (record ReviewEvidence
                         :review_report approved.review_report
                         :findings validated))))
        ((REVISE revised)
         (let* ((validated (validate-findings revised.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] REVISE
             :feedback (record ReviewEvidence
                         :review_report revised.review_report
                         :findings validated))))
        ((BLOCKED blocked)
         (let* ((validated (validate-findings blocked.findings)))
           (variant Decision[ReviewEvidence ReviewBlocker] BLOCKED
             :reason (record ReviewBlocker
                       :review_report blocked.review_report
                       :blocker_class blocked.blocker_class
                       :findings validated)))))))

  (defproc revise-plan-surface
    ((reviewed ReviewedSurface)
     (inputs ReviewContextInputs)
     (evidence ReviewEvidence))
    -> ReviewedSurface
    :effects ((uses-provider providers.plan-fix)
              (uses-command validate_review_findings_v1))
    :lowering inline
    (let* ((validated (validate-findings evidence.findings))
           (revised (fix-plan reviewed.subject inputs validated)))
      (record ReviewedSurface
        :subject revised
        :history (variant RevisionHistory REVISED_FROM :evidence evidence))))
```

  `review-implementation-decision` and `revise-implementation-surface` have
  the same bodies with `review-implementation`, `fix-implementation`, and the
  providers `providers.implementation-review` and
  `providers.implementation-fix`.
  Add one projection used by both loops:

```lisp
  (defproc review-surface
    ((improvement Improvement[ReviewedSurface ReviewEvidence ReviewBlocker]))
    -> ReviewSurfaceResult
    :effects ()
    :lowering inline
    (match improvement
      ((APPROVED approved)
       (variant ReviewSurfaceResult REVIEWED
         :report_path approved.evidence.review_report))
      ((BLOCKED blocked)
       (variant ReviewSurfaceResult REVIEWED
         :report_path blocked.reason.review_report))
      ((EXHAUSTED exhausted)
       (match exhausted.value.history
         ((REVISED_FROM revised)
          (variant ReviewSurfaceResult REVIEWED
            :report_path revised.evidence.review_report))
         ((UNREVIEWED unreviewed)
          (variant ReviewSurfaceResult UNREVIEWED
            :reason "exhausted_before_first_review"))))))
```

  Replace each macro call with `improve` over a `ReviewedSurface` seeded with
  `UNREVIEWED`, limits `3` and `5`, inside the existing `with-phase` forms,
  followed by `(review-surface improvement)`. Project the final
  `BacklogItemResult` by matching the implementation review surface.
- [ ] **Step 4: Run the tests and confirm they pass**, plus
  `pytest -q tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_cli.py
  tests/test_workflow_lisp_route_readiness.py`.
- [ ] **Step 5: Commit** by pathspec.

### Task 11: Utility Evaluation

**Files:**
- Modify: `workflows/examples/improve_experiment_proposal.orc` (from CF-1b
  Task 6) and its test
- Create: `docs/reports/<YYYY-MM-DD of execution>-cf1c-composition-utility.md`

**Interfaces:**
- Consumes: the merged results of CF-1b Task 6 and Tasks 9–10.
- Produces: the qualitative record that the roadmap's CF-1c consequence
  decision reads.

- [ ] **Step 1: Make one realistic change.** Add a typed field
  `sample_count Int` to the example's `ExperimentProposal` record, have the
  `revise` hook set it, and have the deterministic executor consume it.
  Write the failing test first: the executor output reflects the revised
  `sample_count`.
- [ ] **Step 2: Record what the change touched.** List every edited file and
  line count, and whether any edit was transport or execution plumbing rather
  than the record, the hook, and the consumer.
- [ ] **Step 3: Record what the migrations removed and added.** From the
  Task 9 and Task 10 diffs: restated result unions, re-wrap arms, seed and
  context arguments removed; wrapper records, adapters, and absence variants
  added. State net lines per consumer.
- [ ] **Step 4: Compare with the ordinary-code control.** Use the reusable
  Python `review_completion` control recorded in the C1 report as the
  comparison for the same change. Judge programmability, reuse, and diagnosis
  separately. Untested axes stay untested. No productivity score.
- [ ] **Step 5: Commit** the example change, its test, and the report.

### Task 12: Migrate The Design-Delta Library Phases

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- Test: `tests/test_workflow_lisp_design_delta_smoke.py`,
  `tests/test_workflow_lisp_family_profiles.py`,
  `tests/test_workflow_lisp_procedure_first_migrations.py`,
  `tests/test_workflow_lisp_checkpoint_identity_comparison.py`,
  `tests/test_lisp_frontend_autonomous_drain_runtime.py`

**Entry condition:** Task 11's record supports continuing, the owner confirms
that no design-delta drain run is in flight, and the library's target bump
from 2.14 to 2.33 is accepted. This is a promoted primary workflow family; its
program identity changes with its source.

**Interfaces:**
- Consumes: `std/improve`, `std/review`; unchanged hooks
  `review-plan ((completed PlanSubject) (inputs PlanPhaseInputs)) -> ReviewDecision`,
  `revise-plan (... (findings ReviewFindings)) -> PlanSubject`,
  `review-implementation ((completed PrivateImplementationReviewSubject) (inputs ImplementationReviewInputs)) -> ReviewDecision`,
  `fix-implementation (... (findings ReviewFindings)) -> PrivateImplementationReviewSubject`.
- Produces: `run-plan-phase` and the implementation phase workflow with
  unchanged inputs. `DesignDeltaPlanPhaseResult` and the implementation phase
  result keep their `APPROVED`, `BLOCKED`, and `EXHAUSTED` fields and each
  gains `(EXHAUSTED_UNREVIEWED (reason String))`.

- [ ] **Step 1: Write the failing tests.** For each phase, with patched
  providers: approval, blockage with the materialized progress report, and
  exhaustion at the phase's limit (`12` for plan, `40` for implementation)
  whose published `last_*_review_report_path`, `reason`, and findings are the
  final review's. Assert the materialized progress-report view content for
  `BLOCKED` and `EXHAUSTED` is unchanged.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Migrate each file.** Add wrapper records `ReviewedPlan
  {subject PlanSubject, history RevisionHistory}` and
  `ReviewedImplementation {subject PrivateImplementationReviewSubject,
  history RevisionHistory}`. Add adapters `review-plan-decision`,
  `revise-plan-reviewed`, `review-implementation-decision`,
  `revise-implementation-reviewed` with the Task 9 adapter bodies, substituting
  the hook, subject, and inputs names above and the providers
  `providers.plan.review`, `providers.plan.fix`,
  `providers.implementation.review`, and `providers.implementation.fix`. Replace each macro call
  with `improve` at the same limit. In each result projection read
  `approved.evidence.review_report`, `approved.evidence.findings`,
  `blocked.reason.review_report`, `blocked.reason.blocker_class`,
  `blocked.reason.findings`, and, under `EXHAUSTED`, match
  `exhausted.value.history` exactly as in Task 9, keeping the existing
  `materialize-view` calls and the literal reason `max_iterations_reached`.
  `completed.plan_path` becomes `approved.value.subject.plan_path` and its
  `BLOCKED` and `EXHAUSTED` equivalents.
- [ ] **Step 4: Run the listed test modules and the design-delta smoke
  check.** Refresh frozen identity snapshots only where the test names this
  library's source; record each refreshed snapshot in the task report.
- [ ] **Step 5: Commit** by pathspec.

### Task 13: Convert The Parametric Design-Docs Example

**Files:**
- Modify: `workflows/examples/review_revise_parametric_design_docs.orc`
- Modify: `tests/test_workflow_lisp_examples.py`

- [ ] **Step 1: Replace the source-shape test** with a compile test through
  the documented compile command's code path and an executed approval case
  with patched providers.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Convert the macro's provider form.** Replace
  `:review-provider`, `:fix-provider`, and `:returns` with two hook
  procedures that call `provider-result` with the example's existing prompts,
  then wrap them with the Task 9 adapters and call `improve`. Add
  `EXHAUSTED_UNREVIEWED` to `ParametricDesignReviewLoopResult`.
- [ ] **Step 4: Run the tests and confirm they pass.**
- [ ] **Step 5: Commit** by pathspec.

### Task 14: Retire The Displaced Declarations

**Entry condition:** `grep -rn "review-revise-loop" workflows orchestrator
--include=*.orc` returns only `std/phase.orc` itself.

**Files:**
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Modify: `orchestrator/workflow_lisp/form_registry.py` (the
  `review-revise-loop` form entry)
- Modify: tests that pin the macro: find them with
  `grep -rln "review-revise-loop" tests`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`,
  `docs/lisp_workflow_drafting_guide.md`, `docs/capability_status_matrix.md`

- [ ] **Step 1: Write the failing test:** a 2.33 module using
  `review-revise-loop` is rejected with a diagnostic that names `std/improve`
  as the replacement; a module importing `with-phase`, `phase-scope`, and the
  path types from `std/phase` still compiles.
- [ ] **Step 2: Run it and confirm it fails.**
- [ ] **Step 3: Remove** `review-revise-loop`, `review-revise-loop-proc`, and
  `ReviewLoopResult` from `std/phase.orc` and its export list. Keep
  `ReviewDecision`, `ReviewFindings`, the path types, `BlockerClass`,
  `PhaseScopeTargets`, `with-phase`, and `phase-scope`. Remove the form
  registry entry and any lowering reachable only from it; find it with
  `grep -rn "review-revise-loop\|review_revise_loop" orchestrator --include=*.py`.
- [ ] **Step 4: Update or delete** tests that pinned the removed macro, keeping
  every test of the retained exports. Update the three documents.
- [ ] **Step 5: Run** the narrow selectors, then the full suite in tmux, and
  compare with the recorded baseline failure set.
- [ ] **Step 6: Commit** by pathspec.

## Phase 3: Effects Alignment

EL-1's contract and implementation belong to the
[effect ledger design](../design/workflow_lisp_effect_ledger_simplification.md)
and its roadmap section, not to this plan. One task here depends on it.

### Task 15: Move The New Modules To Inference-Default Effects

**Entry condition:** EL-1b is implemented on `main` at its own target.

**Files:**
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`,
  `orchestrator/workflow_lisp/stdlib_modules/std/review.orc`
- Test: `tests/test_workflow_lisp_improve_stdlib.py`

- [ ] **Step 1: Write the failing tests:** with the clause omitted, the
  specialized summary of `improve` still lists the selected adapters'
  provider and command effects; a caller that declares an explicit nonempty
  ceiling naming one review provider is rejected when the selected hook uses a
  different provider.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Replace** the forwarding `:effects ()` clause on `improve`
  with omission under the EL-1 regime, keep the explicit
  `uses-command validate_review_findings_v1` on `validate-findings`, and keep
  old-target controls.
- [ ] **Step 4: Run the tests and confirm they pass.**
- [ ] **Step 5: Commit** by pathspec.

## Phase 4: Extensions By Named Caller

Not planned in detail. Each opens only when a maintained caller needs it and
gets its own plan through the owner named here.

| Extension | Entry condition | Owner |
| --- | --- | --- |
| Fixer-side blockage (sibling helper whose `revise` returns a value-carrying union) | A caller must report partial progress with a blocker | Standard library |
| Generic records | A caller needs a reusable value-plus-metadata record that a union cannot express | Parametric type system |
| Direct generic `defprompt` results | The adapter route is shown to cost more than instantiation-before-contract-generation | Prompt contracts and type system |
| Document snapshot or version references | A caller must publish approval of fixed contents | Artifact allocator and that caller's adapter |
| Subjects that are not records | A named use and proof at the loop-state and exhaustion boundaries | Loop and type owners |
| Pure inline hooks as loop-body `match` scrutinees | Deterministic pure hooks are needed in tests or callers | Frontend (WCC elaboration) |

## Closeout

- [ ] After each phase: update the roadmap CF-1 section, the capability
  matrix row, the design index row, and `docs/index.md` with the supported
  contract and its limits.
- [ ] After Phase 2: record the CF-1c consequence decision in the roadmap:
  retain, narrow, or improve, from the Task 11 report.
- [ ] After Task 14: the design's migration section is rewritten to describe
  the single remaining API.
