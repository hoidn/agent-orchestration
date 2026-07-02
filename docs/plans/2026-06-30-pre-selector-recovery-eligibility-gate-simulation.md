# Pre-Selector Recovery Eligibility Gate Simulation

Date: 2026-06-30
Compared proposal: updated `docs/plans/2026-06-30-pre-selector-recovery-eligibility-gate-plan.md`
Decision: `ADOPT_AS_WRITTEN`

## Inputs And Exclusions

Inputs inspected:

- `docs/plans/2026-06-30-pre-selector-recovery-eligibility-gate-plan.md`
- `workflows/library/scripts/workflow_recovery_dependencies.py`
- `workflows/library/scripts/project_lisp_frontend_selector_manifest.py`
- `workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py`
- current failure class: a blocked dependent remained selectable while waiting on an incomplete prerequisite.

Excluded from authority:

- generated historical `state/`, `artifacts/`, and `.orchestrate/` contents;
- provider prose from old runs;
- stale checklist/evidence wording.

Those files may explain incidents, but this simulation treats them as generated run history rather than as design authority.

## Compared Versions

`current`:

- selector manifest exposes known design gaps even when a blocked gap has an incomplete recovery dependency;
- prerequisite selection trusts the pre-selection pointer and broad manifest;
- missing dependency targets are not clearly separated from selectable work.

`updated_plan`:

- adds deterministic recovery eligibility projection;
- emits `eligible_items`, `eligible_design_gaps`, `priority_recovery_work`, `hidden_work`, `hidden_summary`, and `mechanics_errors`;
- requires prerequisite selection to use eligible or priority work;
- returns precise missing-dependency errors instead of auto-drafting missing prerequisite work;
- keeps normal target-design gap discovery available.

## Scenario Setup

Five synthetic scenarios were simulated:

1. `target_help_A_waits_on_B`: blocked `A` requires available `B`; independent `X` exists.
2. `hard_chain_A_waits_B_waits_missing_C`: blocked `A` requires blocked `B`; `B` requires missing `C`; independent `X` exists.
3. `small_no_dependency`: normal available work with no recovery dependencies.
4. `completed_prereq_B_releases_A`: blocked `A` waits on `B`, and `B` is completed.
5. `missing_C_no_auto_create`: blocked `B` requires missing `C`.

## Evidence Ledger

- Observed: current `project_lisp_frontend_selector_manifest.py` emits `items`, `design_gaps`, and `dependency_edges`, but no eligible/hidden split.
- Observed: current `write_lisp_frontend_prerequisite_selection.py` selects from pre-selection state and manifest rows, not from eligibility-filtered rows.
- Specified by updated plan: blocked dependents waiting on incomplete prerequisites should be absent from selectable manifest fields.
- Specified by updated plan: missing prerequisite targets become mechanics errors, not auto-drafted work.
- Inferred: removing forbidden choices before provider selection should reduce myopic selector choices and post-selector recovery churn.

## Deterministic Workflow Delta

The updated plan moves one decision from provider judgment into deterministic projection:

```text
known work + run-state dependency edges
-> eligible work / hidden work / priority recovery / mechanics errors
-> selector sees only selectable known work
```

The updated plan deliberately does not add automatic work creation:

```text
missing dependency
-> mechanics error or blocked handoff
-> normal target-design gap discovery remains separate
```

That is the right boundary. Filtering known work is deterministic routing. Creating new design-gap files is architecture judgment and should not happen as a side effect of eligibility projection.

## Simulated Event Log

### Scenario 1: A waits on B

Current:

```json
{"selectable": ["A", "B", "X"], "hidden": [], "priority": [], "errors": []}
```

Trace:

- Selector receives blocked dependent `A`.
- Provider may choose `A` again.
- Workflow can re-enter the same blocked path.

Updated plan:

```json
{"selectable": ["B", "X"], "hidden": ["A"], "priority": ["B"], "errors": []}
```

Trace:

- Deterministic projection hides `A`.
- `B` is visible as priority recovery work.
- Selector cannot choose the known-forbidden dependent.

### Scenario 2: A waits on B, B waits on missing C

Current:

```json
{"selectable": ["A", "B", "X"], "hidden": [], "priority": [], "errors": []}
```

Trace:

- Selector can choose either blocked dependent.
- Missing dependency is not surfaced clearly.

Updated plan:

```json
{
  "selectable": ["X"],
  "hidden": ["A", "B"],
  "priority": ["B"],
  "errors": [{"code": "missing_dependency_target", "missing": {"source": "DESIGN_GAP", "id": "C"}}]
}
```

Trace:

- `A` and `B` are hidden from normal selection.
- Missing `C` becomes a mechanics error.
- Independent `X` remains selectable.
- If dependency completion is mandatory for progress, the workflow can block with a precise reason instead of selecting bad work.

One caveat: the simulated priority list still contains `B` while `B` is hidden by its own missing prerequisite. The implementation should ensure `priority_recovery_work` only includes runnable prerequisites. The plan already says that; tests should cover this exact chain.

### Scenario 3: Small no-dependency case

Current:

```json
{"selectable": ["I", "X"], "hidden": [], "priority": [], "errors": []}
```

Updated plan:

```json
{"selectable": ["X", "I"], "hidden": [], "priority": [], "errors": []}
```

Trace:

- Eligibility projection is effectively a no-op.
- Expected overhead is low if implemented as a pure helper.
- Existing ordering may change unless the projection preserves original order; implementation should preserve order when possible.

### Scenario 4: Completed prerequisite releases retry target

Current:

```json
{"selectable": ["A", "X"], "hidden": [], "priority": [], "errors": []}
```

Updated plan:

```json
{"selectable": ["A", "X"], "hidden": [], "priority": [], "errors": []}
```

Trace:

- Completed `B` satisfies `A`'s dependency.
- `A` remains eligible for retry.
- The gate does not permanently suppress blocked work after the prerequisite is complete.

### Scenario 5: Missing C is not auto-created

Current:

```json
{"selectable": ["B"], "hidden": [], "priority": [], "errors": []}
```

Updated plan:

```json
{
  "selectable": [],
  "hidden": ["B"],
  "priority": [],
  "errors": [{"code": "missing_dependency_target", "missing": {"source": "DESIGN_GAP", "id": "C"}}]
}
```

Trace:

- Workflow cannot select blocked `B`.
- Missing `C` is explicit.
- No new gap is auto-created from recovery metadata.

## Decision Rationale

The updated plan improves routing because it removes known-invalid choices before a provider sees them. This should reduce repeated selection of blocked dependents and reduce selector myopia.

The updated plan also removes the previous high-risk behavior: materializing missing prerequisites as new design-gap files. That eliminates the likely zombie-gap/churn path from the earlier version.

## Comparison

| Version | Expected benefit | Churn risk | Brittleness risk | Runtime cost |
| --- | --- | --- | --- | --- |
| Current | None for this failure | High | High | Low |
| Updated plan | High for dependency misselection | Low | Low to medium | Low |

The remaining brittleness risk is not from the concept. It is from implementation details:

- priority recovery must not include hidden/ineligible prerequisites;
- selector context must not continue presenting legacy `design_gaps` as selectable authority;
- missing-dependency errors must not cause the provider to improvise from old artifacts.

## Assumptions And Falsifiers

Assumptions:

- dependency edges in run state are accurate enough to hide known dependents;
- selector prompt consumes filtered fields or the workflow passes a filtered manifest;
- normal target-design gap discovery remains possible when no known eligible work exists;
- the helper preserves current work order where there is no dependency reason to reorder.

Falsifiers:

- existing prompt still reads legacy `design_gaps` and ignores `eligible_design_gaps`;
- eligibility hides all work when independent work should remain selectable;
- `priority_recovery_work` includes an ineligible prerequisite in a dependency chain;
- missing dependency becomes a new provider-driven gap despite the plan's no-auto-create rule.

## Regression Risks

- If both old `design_gaps` and new `eligible_design_gaps` are present, providers may still choose from the old field unless prompt/context is tightened.
- If priority recovery ordering is too strong, normal target-design work may be starved.
- If completed/retired status detection is wrong, valid retry targets could be hidden.
- If missing-dependency errors are routed to a provider instead of deterministic blocked handling, the workflow may still churn.

## Recommendation

`ADOPT_AS_WRITTEN`, with two implementation checks treated as blocking:

1. In chained dependencies, `priority_recovery_work` must include only runnable prerequisites. For `A requires B` and `B requires missing C`, `B` should not be selectable until `C` is resolved.
2. The selector must consume `eligible_items` and `eligible_design_gaps` as the selectable known-work surface. Legacy `items` and `design_gaps` may remain for diagnostics, but they must not be presented as the primary selection list.

The updated plan should improve workflow performance and reduce churn. It is no longer carrying the earlier auto-materialization behavior that would likely have made the workflow more brittle.
