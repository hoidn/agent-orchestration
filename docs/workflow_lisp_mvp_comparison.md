# Workflow Lisp MVP Comparison

This page is the quick, user-facing comparison for the Workflow Lisp MVP.

It answers one question: does the Lisp frontend make a real workflow slice
clearer, or does it only replace YAML punctuation with parentheses?

Short answer: for the MVP slice, it is a real improvement. The Lisp version is
shorter and removes several brittle authoring details from the workflow source.

## The Two Files

Open these side by side:

- Lisp MVP slice:
  [`tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`](../tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc)
- YAML equivalent slice:
  [`workflows/library/neurips_backlog_implementation_phase.v214.yaml`](../workflows/library/neurips_backlog_implementation_phase.v214.yaml)

The equivalent YAML slice is the implementation-attempt portion:

- `ExecuteImplementation`
- `SelectImplementationOutcome`
- `PublishCompletedExecutionReport`
- `PublishBlockedProgressReport`

In the YAML file, that starts at `ExecuteImplementation` and ends at
`PublishBlockedProgressReport`.

## What Changed

| Concern | YAML v2.14 slice | Lisp MVP slice |
| --- | --- | --- |
| Authored size | About 143 lines for the comparable slice. | 75 lines including type declarations. |
| Variant selection | Hand-authored `select_variant_output`. | Typed union return from `provider-result`. |
| Variant proof | Manual `when` plus `requires_variant`. | `match` creates the proof context. |
| Pointer files | Explicit pointer-writing Python blocks. | No pointer files in authored source. |
| State paths | Manual `${inputs.state_root}/...` paths. | Phase context owns derived state targets. |
| Blocker extraction | Markdown line-prefix extraction. | Structured union field. |
| Inline glue | Inline `python -c` publish wrappers. | No inline command glue in the source. |

## Where The Concision Comes From

The YAML slice is close to the runtime protocol. That is useful for
implementation work because every step is visible, but it makes authors spell
out details that are mostly consequences of a smaller semantic idea:

```text
Run the implementation provider.
It returns either COMPLETED or BLOCKED.
Expose only the fields that belong to the selected variant.
```

The Lisp slice makes that smaller idea explicit. The compiler then lowers it
into the v2.14 protocol pieces that YAML currently has to author directly.

| Authoring problem | YAML expression | Lisp expression | Why the Lisp stays smaller |
| --- | --- | --- | --- |
| Declare the possible provider outcomes. | Repeat the discriminant, enum values, JSON pointers, field contracts, and per-variant fields inside `select_variant_output`. | Define one `ImplementationAttempt` union. | The union is the single source of truth for the discriminant and variant fields. |
| Capture evidence for which outcome happened. | Add `pre_snapshot`, candidate refs, snapshot evidence, and `select_variant_output` wiring. | Return `ImplementationAttempt` from `provider-result`. | Snapshot and selection mechanics are generated from the typed provider result. |
| Use a variant-specific field. | Write a `when` condition and a matching `requires_variant` guard before referencing the field. | Use the field inside the matching `match` arm. | The branch itself is the proof that the field is available. |
| Manage phase-local state paths. | Thread `${inputs.state_root}/...` paths through steps and bundle outputs. | Use `with-phase`, `phase-target`, and typed phase context fields. | Canonical state and target paths are derived from phase context instead of repeated in the workflow body. |
| Publish selected report paths. | Run inline Python to check a selected path and write a pointer file, then publish that pointer-backed output. | Refer to the typed path value selected by the union branch. | The artifact value remains authoritative; pointer materialization is not part of normal authoring. |
| Record structured blocker data. | Extract `Blocker Class:` from a markdown candidate. | Make `blocker_class` a typed field on the `BLOCKED` variant. | The provider result is validated as structured state; the report remains a human-readable view. |
| Diagnose mismatches. | Debug drift across refs, JSON pointers, snapshot names, guards, and pointer paths. | Debug a typed source form. | The compiler can attach errors to the form that introduced the invalid type, field, or branch. |

This is the meaningful abstraction boundary: YAML describes the execution
protocol directly; `.orc` describes typed workflow intent and relies on shared
lowering code to produce the protocol. The frontend is useful only where that
lowering is deterministic, validated, and source-mapped.

## YAML Shape

The YAML version has to spell out runtime mechanics directly:

```yaml
- name: SelectImplementationOutcome
  select_variant_output:
    path: ${inputs.state_root}/implementation_state.json
    discriminant:
      name: implementation_state
      allowed: ["COMPLETED", "BLOCKED"]
    variants:
      COMPLETED:
        fields:
          - name: execution_report_path
      BLOCKED:
        fields:
          - name: progress_report_path
          - name: blocker_class
    evidence:
      mode: snapshot_diff
      snapshot:
        ref: root.steps.ExecuteImplementation.snapshots.implementation_outcome_before
    extract:
      from: candidate_path
      line_prefix: "Blocker Class:"

- name: PublishCompletedExecutionReport
  when:
    compare:
      left:
        ref: self.steps.SelectImplementationOutcome.artifacts.implementation_state
      op: eq
      right: COMPLETED
  requires_variant:
    step: SelectImplementationOutcome
    value: COMPLETED
  command:
    - python
    - -c
    - |
      ...
```

This is explicit, but authors have to manually keep the snapshot, variant
selection, proof, pointer-writing, and publication logic aligned.

## Lisp Shape

The Lisp version keeps the semantic intent in the source:

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (implementation_state ImplementationStateTag)
    (execution_report_path WorkReport))
  (BLOCKED
    (implementation_state ImplementationStateTag)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)))

(defworkflow run-implementation-attempt
  ((phase-ctx ImplementationAttemptPhaseCtx)
   (inputs ImplementationAttemptInputs))
  -> ImplementationAttemptSurfaceResult
  (with-phase phase-ctx implementation
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (inputs.design
                        inputs.plan
                        (phase-target execution-report)
                        (phase-target progress-report))
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (record ImplementationAttemptSurfaceResult
           :implementation_state completed.implementation_state
           :implementation_state_bundle_path
             phase-ctx.implementation_state_bundle_path))
        ((BLOCKED blocked)
         (record ImplementationAttemptSurfaceResult
           :implementation_state blocked.implementation_state
           :implementation_state_bundle_path
             phase-ctx.implementation_state_bundle_path)))))))
```

The compiler owns the lowering details. The author writes the typed outcome and
the routing over that outcome.

## Why This Is Better

The improvement is not just fewer lines. The important change is that the Lisp
source removes repeated correctness obligations from the author:

- no manual pairing of `when` and `requires_variant`;
- no pointer-file path as semantic authority;
- no markdown parsing for `blocker_class`;
- no inline Python to republish path values;
- no hand-managed implementation-state path in the workflow body.

The MVP evidence is summarized in:

[`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/mvp_metrics_recommendation_report.md`](plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/mvp_metrics_recommendation_report.md)

## Boundary

This comparison proves only the MVP implementation-attempt slice. It does not
prove that the full Lisp frontend is complete or that the entire NeurIPS drain
stack is better after translation.

For the implementation contract and remaining design, see:

- [`docs/design/workflow_lisp_frontend_mvp_specification.md`](design/workflow_lisp_frontend_mvp_specification.md)
- [`docs/design/workflow_lisp_frontend_specification.md`](design/workflow_lisp_frontend_specification.md)
