# Workflow Lisp Judgment Views

- **Status:** implemented and complete for the bounded target-2.23
  explicit-composed sibling and read-only inspection surface at commit
  `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
  `ccec170be8757c9e4fd5ed8ece6f93b04fc03299`; the production target-2.23
  phased call remains Q4-ineligible
- **Kind:** read-only result-plus-provenance inspection design
- **Owner:** Workflow Lisp prompt calculus Q4
- **Depends on:** implemented target-2.22 Q3 prompt-attempt identity and
  evidence
- **Language delta:** no new source form or type; the implemented
  existing-expression WCC composition seam carries `path/join-under` in a
  `list/map-effect` child-call argument
- **First consumer:** the implemented target-2.23 ordinary-composed panel
  sibling in the `review_revise_design_docs` family
- **Implementation evidence:** Tasks 1–8 landed through `000bfcfe`, with the
  separate prompt-asset correction at `187336f7` and implicit-list ecosystem
  correction at `0187392f`; focused verification passed 643 tests, the new
  module collected 91 tests, and the broad closure comparison reported
  11,072 passed, 5 failed, 24 skipped, and 33 warnings
- **Closure-comparison disposition:** the five failures are four inherited
  route/retirement rows plus one xdist-only LSP read-only build-digest race;
  the LSP row passes in isolated replay
- **Review provenance:** ordered external `Q4_TASK_9_SPEC_APPROVED`,
  `Q4_TASK_9_QUALITY_APPROVED`, `Q4_FINAL_SPEC_APPROVED`, then
  `Q4_FINAL_QUALITY_APPROVED` are bound by closure-record SHA-256
  `85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`;
  this document records rather than self-attests them
- **Design review order:** independent `Q4_DESIGN_SPEC_APPROVED`, then
  independent `Q4_DESIGN_QUALITY_APPROVED` (both approved against commit
  `d7fe454902ff2f5b5784a66c37fbb19f9332e4ac`)
- **Related authorities:**
  - `docs/reports/2026-07-27-q4-binding-decision-brief.md`
  - `docs/design/workflow_lisp_prompt_calculus.md`
  - `docs/design/workflow_lisp_prompt_identity_diagnostics.md`
  - `docs/design/workflow_lisp_pure_list_traversal.md`
  - `docs/design/workflow_lisp_program_search_boundaries.md`
  - `docs/design/workflow_language_design_principles.md`, especially
    principles 28, 29, and 30
  - `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`

## Summary

Q4 joins two existing authorities for inspection:

1. the contract-validated provider result committed in reached workflow
   state; and
2. the content-sealed Q3 prompt-attempt record published before that
   provider launched.

Runtime records one closed locator beside the successful result in the same
state mutation. A pure report projector validates that locator against both
authorities and derives judgment rows, matrices, disagreement tables, and
attempt/iteration series.

Q4 does **not** add a Workflow Lisp `Judgment[T]` type, a result envelope, a
runtime prompt/evidence reference, a new outcome union, or report-derived
workflow data. The result remains the semantic judgment. Q4 makes its
provenance inspectable without making provenance authoritative.

The selected consumer uses existing language contracts plus one narrowly
identified WCC composition correction. The outer bounded `list/map-effect`
derives a typed per-lens report target with the already-authored
`path/join-under` expression and passes it to one child workflow call. The
child executes the existing fragment-backed
`review-design-doc -> ReviewDecision`, preserves that full union in its
reached provider step, matches the union to the shared `review_report` path,
and returns `ReviewReportPath`. The map therefore transports
`List[ReviewReportPath]`, not `List[ReviewDecision]`, before one synthesis
call. No recursive record/union collection widening is required or selected.

This makes in-workflow provenance-dependent routing harder: a later consumer
cannot parse Q4 views or receive an implicit `Judgment[T]`. That cost is
intentional because the bound panel needs inspection, not new semantic
authority.

## Governing Decisions

### Adopted consumer binding

The owner-adopted default in
`docs/reports/2026-07-27-q4-binding-decision-brief.md`
binds Q4 to a panel variant of `review_revise_design_docs`:

- the existing `review-design-doc` fragment;
- one runtime list of ordered review lenses;
- bounded `list/map-effect`; and
- one synthesis call over the ordered report list.

The design countersigns that binding. The alternative fixture, frozen
procedure-first workflows, production drains, experiments, and live-provider
groups remain rejected for the reasons in the brief.

The brief's re-entry conditions are resolved against the current tree:

1. target-2.22 WCC compile probes prove that a fragment-backed call reached
   through a child-workflow boundary retains
   `workflow_prompt_attempt_identity.v1`; Q5 subsequently advanced the
   production family module to target 2.23 while preserving an exact
   target-2.21 control, so the implementation-entry recensus below replaces
   the brief's superseded cross-target import premise without changing the
   Q4 identity contract; the remaining path-expression call-argument seam is
   selected explicitly below and is now implemented;
2. Q3 landed with functional-v2/identity-v1 authority;
3. no newer real panel displaced the selected consumer; and
4. no owner routing act selected trial-runs adjudication.

### Implementation-entry Q5 recensus amendment

Q5 commit `bb67f680` advanced the production
`workflows/examples/review_revise_design_docs.orc` module to target 2.23 and
made its existing review call explicitly phased. It also retained the exact
pre-Q5 target-2.21 source at
`tests/fixtures/workflow_lisp/prompt_calculus/review_revise_design_docs_target_2_21.orc`.
That fixture is a byte-frozen compatibility control, not a production import
owner.

Q4 therefore uses a target-2.23 sibling that imports the existing types and
`review-design-doc` fragment from the current production module. Its
fragment-backed review calls specify exact `:delivery :composed`, retaining
identity-v1/functional-v2 and satisfying the unchanged structural eligibility
predicate below. The production entry remains phased identity-v2/evidence-v3
and Q4-ineligible. This amendment changes only the selected consumer/import
binding and its compatibility proof; it changes no locator, view, result,
evidence, report, or language semantics.

### Selected composition shape and proven core

The direct `list/map-effect` body cannot return `ReviewDecision`, because the
implemented target-2.18 collection contract intentionally rejects
`List[Union]`. An inline procedure wrapper is also invalid after WCC expansion
because one map iteration would contain more than one lowered boundary.

The accepted minimal shape is one child workflow call:

```lisp
(list/map-effect ((lens lens_ids)) :max 8
  (call review-one
    :lens lens
    :review_report_target_path
      (path/join-under ReviewReportTargetPath lens)
    :target_doc target_doc
    :context_docs context_docs
    :checks_report checks_report
    :review_model review_model
    :review_effort review_effort))
```

`review-one` owns the fragment-backed provider result and a pure match:

```lisp
(let* ((decision
         (provider-result providers.design-docs.review
           :prompt
             (review-design-doc
               :target_doc target_doc
               :context_docs context_docs
               :review_focus lens
               :checks_report checks_report
               :review_report_target_path
                 review_report_target_path)
           :delivery :composed
           :model review_model
           :effort review_effort
           :timeout-sec 3600)))
  (match decision
    ((APPROVE approved) approved.review_report)
    ((REVISE revise) revise.review_report)
    ((BLOCKED blocked) blocked.review_report)))
```

The child workflow returns the existing path type. Its internal provider
`StepResult` retains the complete authoritative union and Q3 evidence locator.
The outer map sees exactly one workflow call and returns the already-supported
`List[ReviewReportPath]`.

The historical child-workflow and cross-target import compile probes are
design feasibility results, not implementation evidence. The child-boundary
identity result remains relevant, but Q5 superseded the probed import
topology. The implementation lands a maintained same-target import proof
against the current production module and separately preserves the frozen
compatibility control.

### Required existing-expression composition seam

The complete panel does not compile on the current tree. Four tempting shapes
have been checked and rejected:

- placing `path/join-under` directly in the fragment fill is outside the
  fragment identity grammar (`prompt_fill_identity_unsupported`);
- binding the join inside the child before the fragment application is outside
  the current phase translation body (`phase_translation_body_invalid`);
- passing the join as the outer map call argument is rejected by WCC's current
  export projection (`workflow_return_not_exportable`); and
- hiding the join in a pure helper remains unsupported in WCC lowering
  (`wcc_lowering_route_unsupported` for `FunctionCallExpr`).

Q4 selects the smallest generic correction: WCC map call-argument projection
must carry the already-typed, already-authored `PathJoinUnderExpr` to the child
call, evaluate it in the caller's iteration scope, and bind the resulting
`ReviewReportTargetPath` as an ordinary child input. This adds no syntax,
operator, hidden value, implicit conversion, or prompt-identity exception.
Classic and WCC must agree on the typed path value and existing
`path_join_under_child_invalid` / `path_join_under_escape` refusals.

The implementation must prove this generic expression route independently of
the panel names. If it requires broadening fragment-fill identity, adding a
new list operator, or weakening WCC's one-boundary map rule, implementation
stops and returns to design.

### No source marker

Q4 adds no `:inspection`, annotation, prompt kind, or target version. A call is
eligible only when all of these structural facts hold:

- it is a direct fragment-backed provider call with a compiled fragment
  contract;
- its effective delivery is ordinary composed delivery: omitted on the
  pre-2.23 surface or exact `:delivery :composed`, never `:phased`;
- its compiled carrier is exact
  `workflow_prompt_attempt_identity.v1`;
- its published evidence record is exact
  `workflow_prompt_fragment_snapshot.functional.v2` and embeds that same
  identity-v1 schema;
- it has a root-owned provider-attempt scope and one unique canonical Q3
  record at the deterministic scope-and-ordinal path;
  and
- it has one validated committed provider result.

Target version alone never establishes eligibility. In particular, a
target-2.23 phased call carries identity v2 and fails this predicate before
locator construction; it neither receives a binding nor appears later as a
missing-binding Q4 row. A target-2.23 composed call remains eligible because
it retains the ordinary identity-v1/evidence-v2 structure. Unknown delivery,
identity, or evidence versions are ineligible rather than guessed.

Every newly executed eligible call records the generic result locator below.
The read-only report exposes structurally comparable rows without claiming
that arbitrary provider output has a domain-specific score. No workflow,
module, prompt, provider, step name, field spelling, or family name controls
eligibility.

This keeps target-2.20/2.21 compiler, runtime, state, checkpoint, and resume
behavior unchanged and avoids inventing a language version for an
observability-only association. The report surface changes additively for all
runs by gaining the stable Q4 sibling, including its empty projection.

## Authority Boundaries

Q4 consumes these owners directly:

- the compiler-owned result contract;
- the reached `StepResult` and its already-validated `json`/artifact values;
- the root-owned `provider_attempt_allocations` scope and ordinal;
- the exact immutable evidence file derived from that scope and ordinal;
- the content-sealed Q3 functional-v2 record at its deterministic path;
- the Q3 identity validator and canonical digests; and
- existing call-frame and loop coordinates.

Q4 must not:

- parse `orchestrator report`;
- reconstruct a prompt identity from final prompt text;
- reopen injected dependency files;
- infer a provider attempt from proximity or allocation order;
- parse stdout/stderr or provider panes;
- copy the result into a second authority file; or
- make missing inspection data invalidate an otherwise compatible completed
  result.

The Q3 report and Q4 report are siblings over the same persisted authorities.
Neither is input to the other.

### Persisted result-contract authority

Both bundle-backed and state-only report paths resolve the exact result
contract from the run-bound, content-addressed compiled surface graph. The
owner is
`orchestrator.dashboard.compiled_workflow.load_persisted_compiled_workflow_surface`,
anchored by
`state.runtime_observability.compiled_frontend.persisted_workflow_surface`
and its build-manifest digest. The persisted surface retains provider output
contracts, call structure, and imported-workflow aliases needed to resolve a
reached result without consulting mutable source.

The projector traverses call frames through their persisted `import_alias`,
then requires one unique persisted step contract for the reached runtime
coordinate. That contract supplies the declared result shape and exact
result-contract digest. State-only `orchestrator report` must use the same
resolution path as bundle-backed reporting.

Q4 never recompiles retained or current source, trusts an unbound live bundle,
or synthesizes a contract from the result value. A missing, digest-invalid,
ambiguous, or coordinate-inconsistent persisted graph yields
`judgment_result_contract_mismatch` or
`judgment_result_coordinate_invalid` for that row; it does not weaken
validation and does not invalidate the completed workflow result.

## Prompt-Attempt Result Locator

### Closed schema

For every successfully validated result satisfying the complete ordinary
composed identity-v1 eligibility predicate above, runtime attaches this closed
locator at the exact
`StepResult.debug.prompt_attempt_result_binding` key:

```json
{
  "prompt_attempt_result_binding": {
    "schema_version": "workflow_prompt_attempt_result_binding.v1",
    "scope_sha256": "sha256:...",
    "attempt_ordinal": 1,
    "evidence_relative_path": "workflow_lisp/prompt_dependencies/...json",
    "evidence_file_sha256": "sha256:...",
    "record_kind": "prompt_snapshot"
  }
}
```

The shown outer key is the debug member, not part of the closed locator schema;
other independently owned debug members remain admissible. The locator
contains no result value, prompt bytes, role projection, score, provider text,
or report data.

The fields bind:

- `scope_sha256` to the existing canonical
  `ProviderAttemptScope.key`;
- `attempt_ordinal` to the exact successful provider attempt;
- path, digest, and record kind to the exact immutable evidence file at the
  deterministic path for that scope/ordinal.

The locator is generic prompt-attempt machinery. Its implementation and schema
contain no Q4 consumer, workflow, family, module, provider, or result-type
names.

### Atomic persistence

The ordinary composed-provider execution path already retains:

- the exact scope and ordinal;
- the `PublicationResult` returned by Q3 evidence publication; and
- the final result after output-bundle and Q2 output-position validation.

After validation succeeds, runtime attaches the locator to that same result
dictionary before returning it to the normal state commit. Existing
`StepResult` conversion preserves `debug`. Top-level, nested call-frame, and
generated loop-step persistence write the result value/artifacts and debug
locator in the same state mutation.

No separate root-state "result committed" event is added. That would create a
cross-file partial-commit problem for nested calls. Co-persistence with the
validated reached result is the atomic boundary.

The order is:

1. allocate the attempt;
2. compose and publish Q3 evidence before launch;
3. execute the provider;
4. validate the structured bundle and every Q2 output position;
5. validate the publication locator against the retained scope/ordinal;
6. attach the locator to the successful result; and
7. commit the result and locator together through the existing reached-state
   mutation.

If any earlier step fails, no committed binding exists. If state commit fails,
neither the reached result nor its locator becomes available at that boundary.

### Retry and resume

- Every attempted launch retains ordinary Q3 evidence.
- Only the attempt whose validated result commits receives a locator.
- A failed-then-successful provider retry binds only the successful ordinal.
- More than one locator on one reached result is invalid; the projector never
  chooses one.
- A completed-boundary resume reuses the existing result and locator without
  preparing a provider or reading evidence.
- A pre-Q4 otherwise-eligible completed result has no locator. It remains
  reusable; its judgment view is unavailable and is never backfilled by
  choosing the last attempt.
- Missing or damaged evidence after completion affects the view only.
- Existing `list/map-effect` checkpoint and exactly-once behavior remain
  unchanged.

## Read-Only Judgment Projection

### Stable top-level shape

The existing JSON status report gains the exact top-level sibling
`judgment_views`:

```json
{
  "judgment_views": {
    "schema_version": "workflow_judgment_views.v1",
    "judgments": [],
    "matrices": [],
    "disagreements": [],
    "iteration_series": []
  }
}
```

The nested object and every row object below are closed; unknown keys or
unknown schema versions fail report validation. Runs without eligible results
retain the exact empty nested shape. The Markdown report gains a sibling
`Judgment views` section derived from this same projection. The projector is
pure and read-only. Execution and resume modules do not import it, and no
workflow parser or runtime path consumes its output.

### Coordinate authority

Every repeated `coordinate` object is derived without names or filesystem
inference:

- `root_workflow_identity` is the root run state's exact persisted
  `workflow_checksum`. It must be a canonical `sha256:` digest and must bind
  the same root run/build whose content-addressed persisted surface graph is
  used for contract resolution.
- `call_frame_path` is the exact outermost-to-innermost tuple from
  `ProviderAttemptScope.resume_scope.call_frame_ids`. Every element is one
  non-empty persisted call-frame ID. Its comparison bytes are canonical JSON
  UTF-8 for that string array using `ensure_ascii=False` and separators
  `(",", ":")`; IDs are never split or path-normalized.
- `runtime_step_id`, `enclosing_step_id`, and `enclosing_visit` are the exact
  validated `ProviderAttemptScope.runtime_step_id` and
  `enclosing_step.step_id` / `visit_count`.
- `loop` is null when `ProviderAttemptScope.loop_iteration` is null.
  Otherwise `kind` is exactly `for_each` or `repeat_until`, `step_id` is an
  exact rename of persisted `loop_iteration.loop_step_id`, and `iteration` is
  its nonnegative integer. The projector does not derive these fields by
  parsing `runtime_step_id`.

Any mismatch between that scope, reached state, call frame, loop state, root
checksum, or persisted compiled-surface anchor yields
`judgment_result_coordinate_invalid`; it is never repaired from display
names.

### Available judgment row

An available row has this exact shape:

```json
{
  "schema_version": "workflow_judgment_inspection.v1",
  "status": "available",
  "coordinate": {
    "root_workflow_identity": "sha256:...",
    "call_frame_path": [],
    "runtime_step_id": "root.review",
    "enclosing_step_id": "root.review",
    "enclosing_visit": 1,
    "loop": null
  },
  "attempt_ordinal": 2,
  "result": {
    "declared_shape": "union_value",
    "contract_sha256": "sha256:...",
    "value_sha256": "sha256:...",
    "value": {"variant": "APPROVE", "value": {}},
    "comparison": {
      "kind": "union_variant",
      "value": "APPROVE"
    }
  },
  "provenance": {
    "evidence_record_sha256": "sha256:...",
    "identity_schema_version": "workflow_prompt_attempt_identity.v1",
    "role_sha256": {
      "fragment_program": "sha256:...",
      "resolved_bindings": "sha256:...",
      "injected_dependencies": "sha256:...",
      "runtime_contributions": "sha256:...",
      "provider_policy": "sha256:..."
    },
    "final_prompt_sha256": "sha256:...",
    "composition_sha256": "sha256:...",
    "comparison": {
      "status": "available",
      "previous_attempt_ordinal": 1,
      "classifications": ["input_drift"],
      "reason": null
    }
  }
}
```

`coordinate.loop` is either null or the closed object
`{"kind": "...", "step_id": "...", "iteration": 0}`. `declared_shape` is
exactly `root_value`, `record_value`, or `union_value`.
`result.comparison` is null or the closed object shown; its `kind` is exactly
`canonical_value` or `union_variant`. The provenance comparison reuses the
closed Q3 comparison shape and reason set byte-for-byte.

The result value is read from its authoritative reached state and revalidated
against the compiled contract. It is not copied from the locator or provider
stdout.

### Unavailable row

When a structurally eligible reached result cannot validate its association,
the projector emits:

```json
{
  "schema_version": "workflow_judgment_inspection.v1",
  "status": "unavailable",
  "coordinate": {
    "root_workflow_identity": "sha256:...",
    "call_frame_path": [],
    "runtime_step_id": "root.review",
    "enclosing_step_id": "root.review",
    "enclosing_visit": 1,
    "loop": null
  },
  "reason": "judgment_result_binding_missing"
}
```

The unavailable object has exactly those four keys and the coordinate schema
above. The reason belongs to the closed set under Diagnostics. Unavailable
rows stay in matrix/member order but never count as votes.

### Structural comparison keys

The projector derives a comparison key only when the declared result shape is
unambiguous without domain interpretation:

| Result shape | Comparison key |
| --- | --- |
| `Bool`, `Int`, `Float`, `String`, enum | exact canonical value |
| union | exact selected variant name |
| record, list, map, path, `Value`, other structured root | none |

Every available row retains its canonical result digest. For a non-comparable
shape, different digests remain visible through each matrix member's
`result_value_sha256` while the classification stays `not_comparable`; Q4
does not add a separate byte-difference status or semantic disagreement.

The projector never selects a field named `decision`, `score`, `approved`, or
another conventional spelling. That would make identifier spelling semantic
authority and violate principles 28 and 29.

### Grouping and matrices

Rows group only by structural compiler/runtime coordinates:

```text
(root workflow identity, runtime step ID)
```

Call-frame path, visit, and loop iteration identify members within the group.
Display names are not gates.

Each matrix is the closed object:

```json
{
  "schema_version": "workflow_judgment_matrix.v1",
  "group": {
    "root_workflow_identity": "sha256:...",
    "runtime_step_id": "root.review"
  },
  "members": [
    {
      "coordinate": {
        "root_workflow_identity": "sha256:...",
        "call_frame_path": [],
        "runtime_step_id": "root.review",
        "enclosing_step_id": "root.review",
        "enclosing_visit": 1,
        "loop": null
      },
      "status": "comparable",
      "comparison": {
        "kind": "union_variant",
        "value": "APPROVE"
      },
      "result_value_sha256": "sha256:...",
      "evidence_record_sha256": "sha256:...",
      "reason": null
    }
  ]
}
```

`coordinate` is the exact judgment coordinate object. Matrix-member `status`
is exactly `comparable`, `not_comparable`, or `unavailable`. A comparable
member has a non-null comparison and both digests; a not-comparable member has
null comparison, both digests, and null reason; an unavailable member has
null comparison/digests and one closed Q4 reason.

Judgments and matrix members are ordered by:

1. root workflow identity bytes;
2. runtime step ID UTF-8 bytes;
3. canonical call-frame path bytes;
4. enclosing step ID UTF-8 bytes;
5. enclosing visit;
6. loop kind and step ID UTF-8 bytes, with non-loop before loop;
7. loop iteration;
8. attempt ordinal, with a missing ordinal before every positive ordinal; and
9. canonical result digest bytes, with a missing digest before every digest.

The `matrices` array is ordered by the first two group coordinates. The
`judgments` array uses the full member order above, not discovery order. Each
matrix cell exposes the comparison key or its exact non-comparable/unavailable
state plus result and provenance digests. Filesystem order and provider
completion timing cannot reorder either array.

### Disagreement tables

Each matrix has one closed disagreement row:

```json
{
  "schema_version": "workflow_judgment_disagreement.v1",
  "group": {
    "root_workflow_identity": "sha256:...",
    "runtime_step_id": "root.review"
  },
  "status": "agree",
  "available_member_count": 2,
  "comparable_member_count": 2,
  "not_comparable_member_count": 0,
  "unavailable_member_count": 0,
  "distinct_comparison_key_count": 1
}
```

The classification is total and mutually exclusive:

1. fewer than two available rows is `insufficient_members`;
2. otherwise, any available row without a comparison key is
   `not_comparable`;
3. otherwise, all available rows are comparable: one distinct canonical key
   is `agree`; and
4. otherwise, two or more distinct canonical keys is `disagree`.

Unavailable rows are counted and listed in the corresponding matrix but are
excluded from `available_member_count` and the classification. The
`disagreements` array has exactly one row per matrix in matrix order.

These strings are report data, not a new Workflow Lisp outcome union. They
never route, retry, settle, promote, score, or mutate a workflow.

### Attempt and iteration series

For each exact provider-attempt scope, the series is:

```json
{
  "schema_version": "workflow_judgment_iteration_series.v1",
  "scope_sha256": "sha256:...",
  "coordinate": {
    "root_workflow_identity": "sha256:...",
    "call_frame_path": [],
    "runtime_step_id": "root.review",
    "enclosing_step_id": "root.review",
    "enclosing_visit": 1,
    "loop": null
  },
  "attempts": [
    {
      "attempt_ordinal": 1,
      "record_status": "snapshot",
      "record_sha256": "sha256:...",
      "comparison": {
        "status": "unavailable",
        "previous_attempt_ordinal": null,
        "classifications": [],
        "reason": "no_predecessor"
      },
      "committed_result_status": "bound"
    }
  ]
}
```

Attempt rows reuse Q3's exact closed `record_status`, record-digest, and
comparison contract. `committed_result_status` is exactly:

- `bound` for the one ordinal selected by a fully validated Q4 locator;
- `not_bound` only when a valid locator binds another ordinal in the same
  scope, or reached state proves that the scope has no committed provider
  result; or
- `unknown_pre_q4` when an otherwise-compatible reached result predates Q4
  and has no locator, so no ordinal may be asserted as the committer.

At most one ordinal is `bound`. When one is bound, every other ordinal in that
scope is `not_bound`; when the compatible pre-Q4 case applies, every ordinal
is `unknown_pre_q4`. Attempts are ordered by ascending ordinal. The
`iteration_series` array is ordered by the full coordinate order above and
then scope digest bytes.

This distinguishes:

- prior failed attempts;
- Q3 prompt/input/dependency/runtime/policy drift;
- the one attempt whose result committed; and
- separate child-workflow/list iterations.

The projector does not infer that the newest or last successful-looking
attempt produced the result.

### Fail-closed validation

The projector validates:

- the closed locator schema and canonical field values;
- exact scope key and ordinal agreement;
- one unique deterministic evidence association;
- exact evidence relative path, file digest, and record kind;
- canonical Q3 evidence and identity;
- reached call-frame/loop coordinates;
- exact compiled result contract; and
- the reached canonical result value.

A missing, duplicate, ambiguous, unreadable, noncanonical, mismatched, or
tampered component yields one unavailable row. The projector never falls back
to:

- the last allocated ordinal;
- matching workflow/provider/step names;
- prompt-context report output;
- nearby evidence files;
- a result digest without its committed typed value; or
- stdout, stderr, logs, panes, or prose.

## Selected Generic-Reviewer Panel

### Module and target

The implementation preserves the current target-2.23
`review-revise-design-docs` entry's phased prompt, result, identity-v2,
functional-v3, and runtime behavior. The required layout is a target-2.23
sibling module in the same example family that imports the existing
`review-design-doc` declaration and uses it only from an explicit ordinary
`:delivery :composed` call. The current production module may add only the
four names required by the maintained compile proof to its export surface:

```lisp
(export
  review-revise-design-docs
  DesignDocPath
  ReviewReportTargetPath
  WorkReportPath
  review-design-doc)
```

`DesignDocPath`, `ReviewReportTargetPath`, and `WorkReportPath` are referenced
by the fragment's closed fill contract; exporting the fragment without those
types is not a viable import surface. The production module's target, existing
entry body, and phased behavior remain unchanged.

The export line necessarily changes the production source bytes. Task 2
characterization found that the current compiler carries that source change
through two distinct kinds of lineage:

- the exact source SHA-256 appears in the workflow checksum, the prompt
  dependency contract, and digests derived from those values; and
- the additional export bytes shift later source offsets. The current
  parametric-specialization identity includes those offsets, so the parent
  loop's generated specialization, WCC, step, checkpoint, allocation, and
  source-map subject identifiers are consistently alpha-renamed.

Q4 does not migrate that compiler-wide identity scheme and does not normalize
the changed parent identities into a compatibility claim. They are a
disclosed cross-source-revision incompatibility. The implementation gate owns
the closed test projection `q4_task2_export_compatibility.v1`, containing
exactly:

- `schema_version = "q4_task2_export_compatibility.v1"`;
- the target DSL;
- the production entry name, public inputs, and public result contract;
- the phased helper's provider-call policy, compiled fragment identity,
  prompt-attempt identity version, canonical fragment contract, expected
  outputs, and variant result contract;
- the phased helper's complete runtime plan and complete source-map row; and
- the parent entry's ordered checkpoint point kinds and authored form
  paths/line/column coordinates, with generated subject keys excluded.

That projection must be byte-identical before and after the export edit. It
does not contain the module export catalog, raw source digests, generated
parent identities, or digests derived from those identities, and therefore
makes no claim about them.

The helper bundle has one separately closed source-lineage exception. A
recursive canonical diff must contain exactly six changed leaves, all named
`compiler_prompt_dependency_contract.source_workflow_sha256`, at these
authoritative locations:

1. `surface.steps[0]`;
2. `core_workflow_ast._surface_workflow.steps[0]`;
3. `core_workflow_ast.body[0]`;
4. `core_workflow_ast.body[0]._surface_step`;
5. the helper provider node's executable-IR `execution_config`; and
6. the helper prompt surface in semantic IR.

Every before value is the bound old source SHA-256 and every after value is
the bound new source SHA-256. Any seventh leaf, different field name,
different value, or missing row fails the gate. This exact diff is the
source-lineage characterization; Q4 adds no reusable normalizer or digest
manifest.

The source-position relation is exact. The old and new production sources are
8,079 and 8,149 bytes respectively. Apart from the intentionally changed
export span, every current-production position before that span remains
exact; every position after it retains the same path, line, and column and
has `after.offset == before.offset + 70`. Imported and prelude positions
remain exact. The gate checks this relation over every source position
reachable from the selected compiled projection, including the type
references that seed specialization identity.

The gate additionally requires, without normalization:

- the target, public inputs and result contract, phased delivery,
  materialization-attempt count, prompt fragment identity-v2, functional-v3
  schema, provider configuration, and phased-helper checkpoint/runtime plan
  to remain exact;
- the complete named projection, the exact six-leaf helper diff, parent
  checkpoint topology and point kinds, every authored form path, and the
  complete source-position relation above, to remain exact; and
- the frozen target-2.21 fixture to remain byte-identical to the pre-Q5 source
  retained by `bb67f680` and remain absent from the sibling's import graph.

This is not a claim that a run compiled from the pre-export source can resume
against the post-export source. Ordinary workflow-checksum validation rejects
that cross-source-revision resume before lexical restoration, and Q4 does not
weaken it. The Task 0 census established that no active Q5 orchestrator or
provider attempt is stranded by landing the source revision. Any semantic
delta in the named projection, any helper diff outside the exact six leaves,
any phased-helper checkpoint/runtime-plan delta, any
source-position-relation delta, or any frozen-control delta stops
implementation and returns to Q4 design. Copying the fragment under a new
identity or changing compiler/runtime checksum semantics is not a fallback.

### Lens contract

The panel input is an ordered `List[String]` of lens identifiers. Each
identifier is:

- non-empty;
- a safe relative child accepted by `path/join-under`;
- meaningful as the `review_focus` text shown to the reviewer; and
- pairwise distinct within one panel invocation.

The outer iteration derives its typed Q2 report target and passes it to the
child with:

```lisp
(path/join-under ReviewReportTargetPath lens)
```

Unsafe or escaping identifiers fail through the existing
`path_join_under_child_invalid` or `path_join_under_escape` rule before that
child provider launches.

Pairwise uniqueness is an explicit caller precondition, not a runtime claim.
The current language has no distinctness/set operator, and existing Q2
destination collision validation compares positions within one provider
invocation, not destinations across separate list iterations. Q4 does not
weaken or misdescribe that boundary. The public example ships a checked,
pairwise-distinct default lens set, documents that overriding callers must
preserve uniqueness, and tests the observed duplicate-destination behavior as
a contract limitation. Adding runtime distinctness or a paired
`List[Record]` input is a separately reviewed language change, not a hidden
Q4 prerequisite.

### Per-lens and synthesis behavior

For each ordered lens:

1. the outer `list/map-effect :max 8` makes exactly one child workflow call;
2. the child executes the existing fragment-backed review provider;
3. the provider returns the existing `ReviewDecision` and writes its Q2-bound
   report;
4. the child matches every existing variant to `review_report`; and
5. the child returns `ReviewReportPath`.

The ordered map result is exact `List[ReviewReportPath]`. One synthesis
provider consumes only that report-path list and the ordinary review subject.
The sibling declares the load-bearing final record:

```lisp
(defrecord DesignDocPanelResult
  (reports List[ReviewReportPath])
  (synthesis ReviewReportPath))
```

The synthesis boundary is exact and deliberately not Q4-eligible:

```lisp
(provider-result providers.design-docs.synthesize
  :prompt prompts.design-docs.synthesize
  :inputs (target_doc reports)
  :model synthesis_model
  :effort synthesis_effort
  :timeout-sec 3600
  :returns ReviewReportPath)
```

`prompts.design-docs.synthesize` is an extern prompt, not a `defprompt`
fragment application. It therefore has no compiled fragment contract or
identity-v1 Q3 carrier and fails the Q4 eligibility predicate before locator
construction. It writes and returns the ordinary domain synthesis report but
does not create a second judgment row or matrix. The panel returns
`DesignDocPanelResult` containing the ordered per-lens paths and synthesis
path.

Q3/Q4 digests, locator fields, matrix layout, and disagreement statuses never
enter the synthesis prompt under principle 30. Making synthesis
fragment-backed or judgment-inspectable would be a separate Q4 design
extension, not an implementation choice.

The panel does not revise the target document. Existing
`review-revise-loop` semantics remain in the original entry. A panel-driven
revision policy would require a separate design.

## Diagnostics

The Q4 association/view refusal set is:

| Code | Refusal |
| --- | --- |
| `judgment_result_binding_missing` | eligible completed result has no locator |
| `judgment_result_binding_invalid` | locator shape or field value is invalid |
| `judgment_result_binding_ambiguous` | more than one locator/evidence association claims one result |
| `judgment_result_scope_mismatch` | locator and allocator scope disagree |
| `judgment_result_attempt_mismatch` | locator ordinal is not allocated in the exact scope |
| `judgment_result_evidence_invalid` | evidence is missing, unreadable, noncanonical, digest-mismatched, or Q3-invalid |
| `judgment_result_contract_mismatch` | reached result does not validate against the exact compiled contract |
| `judgment_result_value_mismatch` | committed value and its canonical projection disagree |
| `judgment_result_coordinate_invalid` | call-frame, visit, loop, or runtime-step coordinate is missing or contradictory |
| `judgment_view_group_invalid` | structural group/member coordinates are ambiguous or contradictory |

Runtime locator construction failures attach to the exact provider step and
attempt scope and fail that result before commit. Report-time failures produce
unavailable rows and do not mutate run status.

Existing Q3, fragment, result-contract, Q2 output-position,
`list/map-effect`, path, checkpoint, and resume diagnostics remain
authoritative where their rules apply.

## Compatibility And Migration

- Target-2.20/2.21 compiler, prompt, runtime, state, checkpoint, and resume
  bytes remain unchanged.
- The JSON and Markdown report APIs change additively for every target by
  gaining the closed `judgment_views` sibling/section; an ineligible or empty
  run emits the stable empty projection rather than preserving pre-Q4 report
  bytes.
- Q4 adds no source syntax and reserves no identifier.
- New eligible ordinary composed identity-v1 fragment executions add one
  optional runtime-owned debug locator beside successful results.
- Existing otherwise-eligible state without the locator remains loadable and
  resumable; its Q4 row is unavailable rather than inferred.
- The locator does not participate in program, checkpoint, result-contract,
  or completed-boundary compatibility.
- Missing/damaged evidence never invalidates a compatible completed result.
- The existing Q3 public prompt-context projection remains unchanged.
- The Q4 sibling report is additive and has the stable closed empty shape
  defined above.
- Classic and WCC must project the same eligible results. The real panel and
  resume proof use WCC because `list/map-effect` erases through that route.
- The current production target-2.23 phased entry remains independent and
  excluded from Q4 v1; the target-2.23 panel's explicit composed review calls
  remain eligible through identity-v1/functional-v2. Q4 does not interpret Q5
  phase ledgers or identity-v2 evidence.

## Implementation Ownership

Expected ownership includes:

- the WCC `list/map-effect` call-argument projection path, solely to carry the
  existing typed `PathJoinUnderExpr` as an ordinary child input;
- the ordinary composed-provider finalization path, to retain Q3's
  `PublicationResult` and attach the closed locator after result validation;
- existing `StepResult`/call-frame/loop persistence characterization, with no
  new persistence layer;
- a new pure judgment-view projector factored beside, not through, the Q3
  prompt-context projector;
- the persisted compiled-surface loader and call-alias traversal as the sole
  result-contract authority for both bundle-backed and state-only reporting;
- existing JSON/Markdown report integration;
- the target-2.23 ordinary-composed panel consumer, provider bindings,
  deterministic fixtures,
  docs, specs, and routing tests.

The implementation plan must assign normative deltas before runtime edits:

- `specs/state.md` owns the optional co-persisted locator and compatibility of
  pre-Q4 completed state;
- `specs/observability.md` owns the stable read-only projection, unavailable
  rows, and state-only/bundle-backed parity;
- `specs/providers.md` owns the successful-attempt/result association and its
  retry boundary; and
- `specs/dsl.md` owns any clarification needed for carrying an existing typed
  expression through a WCC child-call argument.

`specs/io.md` remains the authority for the unchanged Q2 artifact/result
validation boundary. The design and roadmap route these contracts; they do not
replace them.

The minimal consumer and locator do not touch Q5's interactive adapter,
provider registry, phased coordinator, or phase ledger. The read-only
projection shares prompt-attempt/report ownership adjacent to Q5, so Q4
implementation must not start while a Q5 acceptance attempt is live. The
docs-only implementation plan may be completed concurrently.

M1 estate shrink remains separately queued and is not selected here.

## Verification Strategy

Implementation follows TDD and proves both directions.

### Composition and compatibility

1. a maintained target-2.23 WCC fixture proves the outer map body contains one
   child call boundary and each fragment-backed review call is explicitly
   composed;
2. caller-scoped `path/join-under` reaches that child as an ordinary typed
   input in Classic and WCC, while invalid/escaping children retain their
   existing refusals;
3. the child provider retains the existing fragment contract,
   `workflow_prompt_attempt_identity.v1`, result union, Q2 output position, and
   source-map owner;
4. the child returns `ReviewReportPath` and the outer map returns
   `List[ReviewReportPath]`;
5. the extern-backed synthesis consumes that list, returns
   `ReviewReportPath`, remains Q4-ineligible, and the public entry returns
   `DesignDocPanelResult`;
6. direct `List[ReviewDecision]` and inline multi-boundary wrappers retain
   their existing refusals;
7. exporting the exact three path types plus fragment compiles the sibling
   while the current target-2.23 phased workflow retains its byte-identical
   closed projection, exactly six characterized
   `compiler_prompt_dependency_contract.source_workflow_sha256` leaf changes,
   the complete offset-shift source-position relation, and the byte-identical
   frozen target-2.21 control; ordinary checksum validation still rejects
   cross-source-revision resume.

### Locator

1. one successful eligible provider result commits one exact locator;
2. provider, bundle, contract, or Q2 output-position failure commits none;
3. failed-then-successful retry binds only the successful ordinal;
4. interruption before reached-state commit leaves no result/locator pair;
5. top-level, child-call, and `list/map-effect` iteration results co-persist
   value/artifacts and locator;
6. completed-boundary resume reuses the pair without provider/evidence access;
7. missing, duplicate, scope/ordinal/path/digest/record-kind tamper fails
   closed and is never guessed.

### Views

1. empty and non-Q3 runs emit the stable empty shape;
2. state-only and bundle-backed reports resolve the same exact contract from
   the bound persisted compiled surface without source recompilation;
3. missing, tampered, ambiguous, or coordinate-inconsistent persisted
   surfaces make only the affected row unavailable;
4. scalar, enum, union, record, and unavailable rows yield the exact
   comparison key or `not_comparable`;
5. grouping and order are independent of filesystem enumeration and provider
   completion timing;
6. `agree`, `disagree`, `not_comparable`, and `insufficient_members` are
   covered in both directions;
7. attempt series distinguishes prior failures, one locator-bound result, and
   the explicit pre-Q4 unknown-binding state;
8. JSON and Markdown derive from the same validated projection;
9. execution/resume modules do not import the projector and no workflow/parser
   consumes report output.

### Consumer and integration

1. compile-only import/export feasibility uses the current target-2.23
   production module, preserves its phased entry projection, and independently
   preserves the frozen target-2.21 control;
2. the public pairwise-distinct default lens identifiers yield ordered reports
   and one extern-backed synthesis call, whose lack of a compiled fragment/Q3
   carrier is regression-locked as Q4-ineligible;
3. unsafe/escaping lenses fail before their provider;
4. duplicate lens destinations are characterized and never claimed to be
   rejected by current cross-iteration Q2 validation;
5. deterministic clean and interrupted/resumed panel runs produce identical
   typed results, artifact bytes, provider event identities, and judgment
   views without replay;
6. one bounded real-provider panel smoke proves the public consumer and report
   route after deterministic gates;
7. genericity scans reject workflow/family/module/provider/result-name
   branches in mechanism code.

Narrow selectors precede the broad non-security suite. New or renamed test
modules run `pytest --collect-only`. No test asserts literal prompt wording.

## Declarative Acceptance Scenario

Given a target-2.23 ordinary-composed panel with three ordered, path-safe,
pairwise-distinct lens identifiers:

1. WCC executes exactly three child workflow calls under
   `list/map-effect :max 8`;
2. each child executes the existing fragment-backed review once;
3. each provider returns an existing `ReviewDecision`, writes its distinct
   Q2-bound report, and commits one exact result locator beside that union;
4. each child returns the union's common report path;
5. extern-backed synthesis receives the ordinary target plus ordered
   three-path list, receives no Q3/Q4 projection, returns one
   `ReviewReportPath`, and the workflow returns `DesignDocPanelResult`;
6. the report projector validates each reached result, locator, allocator
   scope/ordinal, and deterministic Q3 record from source authority;
7. JSON and Markdown show exactly one ordered matrix for the per-lens
   fragment-backed step, exact union-variant agreement/disagreement, and
   per-attempt series; synthesis creates no second matrix; and
8. no Q4 judgment-view value appears in workflow state, checkpoint identity,
   provider input, routing, retry, or promotion.

If one evidence record is removed after completion, the workflow result
remains compatible and reusable while that judgment row becomes unavailable
with `judgment_result_evidence_invalid`.

## Non-Goals

Q4 does not add:

- a source-level `Judgment`, `Judgment[T]`, prompt value, attempt reference,
  evidence reference, report value, annotation, or target version;
- recursive record/union list carriage, structural union coercion, open record
  admissibility, implicit `Value` conversion, or a result envelope;
- a new result/outcome union or authored failure channel;
- higher-order mapping, lambdas, `ProcRef` mapping, nested effectful maps,
  unbounded panels, or dynamic provider groups;
- provider-result selection, majority routing, scoring, fitness, promotion,
  search, mutation, or revival of the parked evolution roadmap;
- semantic interpretation of arbitrary record fields or identifier spellings;
- Q4 judgment-view report parsing by workflows, runtime, resume, synthesis
  prompts, or provider coordination;
- phased, live-supervision, peer-group, non-fragment, or cross-run judgment
  inspection;
- prompt-body persistence or provider transcript capture;
- a panel-driven revision policy;
- M1 estate shrink, Q5 acceptance changes, or unrelated roadmap work.

## Success Criteria

The design is implementation-ready only when ordered independent review
confirms:

1. the adopted consumer is represented using the proven child-workflow,
   same-target production import, explicit composed-delivery shape, and
   explicitly scoped existing-expression composition seam, with no
   speculative collection widening;
2. the result locator co-persists atomically with the validated result and is
   never treated as authority;
3. views validate existing result and Q3 authorities directly, fail closed,
   and remain outside workflow semantics;
4. grouping and disagreement are structural, deterministic, and name-agnostic;
5. principles 28, 29, and 30 are satisfied;
6. the current target-2.23 phased consumer, the Q4 target-2.23 composed
   sibling, and the frozen target-2.21 control remain distinct; and
7. the implementation plan includes complete TDD, integration, resume,
   docs/spec, broad-gate, and ordered-review sequencing.

Implementation must stop and return to design if:

- one result/locator state mutation cannot be achieved for a generated
  `list/map-effect` child call;
- WCC cannot carry the existing typed `PathJoinUnderExpr` as a child-call
  argument without changing prompt identity, widening the map body, or adding
  syntax;
- the panel requires `List[ReviewDecision]`, hidden `Value` conversion, a new
  result envelope, or a family-name branch;
- Q4 would need to parse another report or infer the latest attempt;
- the child-workflow boundary loses Q3 identity, Q2 output ownership,
  checkpoint/resume identity, or source mapping; or
- synthesis or routing requires Q3/Q4 provenance data.
