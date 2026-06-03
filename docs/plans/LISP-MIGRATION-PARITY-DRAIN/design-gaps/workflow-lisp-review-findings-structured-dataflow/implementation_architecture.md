# Workflow Lisp Review Findings Structured Dataflow Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-review-findings-structured-dataflow`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- define one bounded Workflow Lisp carried-findings contract for review loops:
  a typed carrier record plus a path-safe JSON artifact location, without
  requiring first-class list-valued findings in the frontend type system;
- validate review findings before they become loop state or terminal result
  authority;
- revalidate carried findings on resume-sensitive consumption edges before fix
  or other resumed loop logic consumes persisted findings state;
- thread validated findings through `review-revise-loop` internal decision
  routing, loop-frame outputs, terminal result projection, and revise/fix
  consumption;
- keep the validator as an explicit certified command adapter boundary rather
  than hidden Python, shell, or markdown parsing glue;
- preserve the prior review-loop generic-composition and compiler-owned
  managed-bundle-path decisions rather than redesigning them here.

Out of scope for this slice:

- replacing or re-arguing the imported-stdlib `review-revise-loop`
  architecture itself;
- broad `resume-or-start` reusable-state design, reusable phase summaries, or
  migration promotion policy;
- first-class collection types for findings items, generic schema-language
  execution, or runtime polymorphism;
- renaming the existing review-loop report-path vocabulary to the future ideal
  names in the parent design;
- changing runtime command bundle-path injection, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`,
  or public/internal managed-write-root ownership;
- any report parsing, pointer-as-authority compatibility, inline shell/Python
  glue, or runtime-native promotion.

This is a bounded implementation architecture for one gap only. It does not
replace the parent parity architecture, the umbrella frontend specification, or
the prior review-loop composition slice.

## Problem Statement

The selected target design already established the intended carried-findings
contract:

- findings are structured authority, not markdown prose;
- until list types are sufficient, findings may be carried as a validated JSON
  artifact path plus schema version;
- validation must happen before publication and again after resume before
  resumed logic consumes findings;
- revise/fix must receive findings in structured form;
- terminal review-loop results must preserve validated findings, including the
  exhaustion path.

The current checkout still falls short in four concrete ways:

1. `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` exports only
   `ReviewDecision` plus the review-loop macro; there is no stdlib
   `ReviewFindings` carrier contract.
2. The focused review-loop fixture and tests still model `ReviewLoopResult`
   without findings fields, so the carried-findings contract is neither
   typechecked nor lowered.
3. `_validate_review_loop_result_contract(...)` and the current review-loop
   lowering only enforce report/blocker/reason fields. They do not require,
   materialize, or project findings through the loop state.
4. The frontend has `defschema` as an authoring surface, but the current
   checkout does not provide a generic runtime schema-validation execution path
   for findings JSON. Using raw provider output or ad hoc inline parsing would
   violate the command-adapter contract and the target design.

The remaining gap is therefore not "invent review loops" and not "add generic
lists first." The gap is to introduce one bounded validated findings carrier
that fits the current Workflow Lisp and runtime substrate, and to thread it
through review-loop state and fix consumption without reopening unrelated
language work.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `Required Generic .orc Support`
  - `New or completed authoring syntax`
  - `Compiler And Lowering Layer`
  - `Review Loop Contract`
  - `Evidence And Implementation Boundaries`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 7.4-7.6, 16-18, 22-27, 50-57, 63, 66, 74, 85, 95, 102-104
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `specs/dsl.md`
- `specs/io.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep structured bundles and typed artifact values authoritative;
- keep reports as views and forbid markdown extraction as semantic authority;
- keep any executable findings validator behind an explicit certified adapter
  contract with fixtures, source maps, and path-safety metadata;
- keep provider, prompt, and procedure refs compile-time-only;
- keep compiler-generated bundle roots runtime/compiler-owned rather than
  public entrypoint API;
- keep the frontend package/runtime package ownership split:
  Workflow Lisp authoring/lowering in `orchestrator/workflow_lisp/`,
  shared execution/state validation in `orchestrator/workflow/`;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

### Decisions Reused

- Reuse the imported-stdlib review-loop route and its thin specialization model
  rather than reintroducing a compiler-special review-loop primitive.
- Reuse the compiler-owned managed-write-root policy for generated result
  bundles and validator bundle paths.
- Reuse compile-time-only `ProcRef` review/fix specialization; no runtime
  procedure/provider/prompt transport is added.
- Reuse the existing certified-adapter registration model in
  `compiler.py` and the command-boundary manifest/source-map pipeline.
- Reuse the rule that carried evidence identities such as checks artifacts come
  from workflow state or consumed artifacts, not from review-provider-authored
  replacement paths.

### New Decisions In This Slice

- Standardize one bounded carried-findings surface for review loops:
  `ReviewFindings(schema_version, items_path)` where `items_path` is a
  path-safe JSON artifact and `schema_version` must validate as
  `ReviewFindings.v1`.
- Add one certified adapter boundary,
  `validate_review_findings_v1`, as the executable validator for the current
  checkout because runtime `defschema` execution is not yet available.
- Require `review-revise-loop` terminal result contracts to carry a `findings`
  field compatible with `ReviewFindings`, while preserving the existing
  caller-supplied `:returns` surface and current report-path vocabulary.
- Thread findings through loop-frame outputs and into revise/fix inputs only
  after validation, and revalidate persisted findings on resume-sensitive
  consumption edges.

### Conflicts Or Revisions

The prior review-loop generic-composition slice intentionally deferred
repo-wide review-findings schema/validator design and kept the existing review
result vocabulary narrow. This slice revises that deferral, but only for the
bounded carried-findings obligation selected by the drain:

- `review-revise-loop` now gains one standard findings carrier contract;
- the lowering contract now includes one certified adapter dependency for
  findings validation;
- the slice still does not reopen report-field renames, collection-type
  expansion, or a repo-wide generic schema execution system.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- the stdlib carried-findings authoring contract in
  `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`;
- review-findings contract helpers in
  `orchestrator/workflow_lisp/contracts.py`;
- review-loop findings contract validation in
  `orchestrator/workflow_lisp/typecheck.py`;
- review-loop lowering changes that insert validator steps, materialize
  validated findings into loop-frame outputs, and pass findings into fix
  consumption in `orchestrator/workflow_lisp/lowering.py`;
- stdlib contract metadata updates in
  `orchestrator/workflow_lisp/stdlib_contracts.py`;
- one certified adapter binding and module for findings validation in
  `orchestrator/workflow_lisp/compiler.py` and
  `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`;
- focused fixtures and tests for findings validation, carried findings
  consumption, resume-sensitive revalidation, and command-boundary manifests.

This slice intentionally does not own:

- the broader imported-stdlib review-loop specialization route;
- generic runtime execution of `defschema`;
- `resume-or-start` reusable-state summaries or the reusable-phase validator;
- runtime command bundle-path injection semantics under `specs/io.md`;
- broader migration promotion reports, smoke policy, or YAML deprecation;
- first-class findings collection types beyond the bounded path-backed carrier.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- the frontend can declare `defschema`, `defrecord`, `defunion`, `command-result`,
  and certified command boundaries;
- `compiler.py` already augments command-boundary environments with built-in
  certified adapters for resource transition and reusable-state validation;
- the review-loop fixture already proves generated repeat-loop outputs and
  exhaustion projection for reports, but not for findings;
- the command-adapter contract already explicitly allows structured validator
  adapters, including validators for review findings.

The current checkout also shows the exact missing carried-findings behavior:

- `std/phase.orc` exports only `ReviewDecision` and `review-revise-loop`;
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc` defines
  `ReviewLoopResult` variants without findings;
- `_validate_review_loop_result_contract(...)` currently requires:
  - `APPROVED`: `checks_report`, `review_report`, `review_decision`
  - `BLOCKED`: `progress_report`, `blocker_class`
  - `EXHAUSTED`: `last_review_report`, `reason`
- current lowering assertions cover `state__last_review_report` and terminal
  projection, but there is no `latest_findings` loop output;
- `orchestrator/workflow_lisp/adapters/` contains no findings validator;
- the progress ledger for this drain remains empty, so no later recorded event
  supersedes the selector rationale.

This makes the slice feasible without inventing new runtime primitives. The
missing pieces are one bounded findings contract, one certified validator
boundary, and one review-loop lowering/typecheck update that uses them.

## Proposed Architecture

### 1. Add One Bounded Stdlib Findings Carrier

Extend `std/phase.orc` with a minimal carried-findings surface that matches the
parent parity design but stays within the current type system:

- `ReviewFindingsJsonPath`
  - `relpath`
  - under `artifacts/work`
  - `must-exist true`
- `ReviewFindings`
  - `schema_version String`
  - `items_path ReviewFindingsJsonPath`

This slice does not require first-class list-typed findings items in Workflow
Lisp. The authoritative findings content remains a JSON artifact stored at
`items_path`; the carrier record makes that artifact typed, source-mapped, and
path-constrained.

The contract is intentionally narrow:

- `schema_version` must validate as `ReviewFindings.v1`;
- `items_path` is the authoritative artifact value, not a pointer file;
- callers and generated review/fix helpers may consume the carrier record, not
  raw `Json` or markdown prose.

The slice may optionally add a pure constant helper or schema alias in
`std/phase.orc` for `ReviewFindings.v1`, but it must not widen into a general
schema-language runtime.

### 2. Use A Certified Validator Adapter, Not Runtime `defschema` Execution

Because the current checkout does not yet provide generic executable
`defschema` validation, findings validation should use one explicit certified
adapter:

- binding name: `validate_review_findings_v1`
- stable command:
  `python -m orchestrator.workflow_lisp.adapters.validate_review_findings_v1`
- input contract:
  a structured object equivalent to the `ReviewFindings` record
- output type:
  `ReviewFindings`
- effects:
  `structured_result`
- path safety:
  workspace-relative relpath validation
- source-map behavior:
  ordinary command-step origin
- fixtures:
  at least one positive fixture and negative fixtures for malformed JSON,
  path escape, pointer-as-authority, wrong schema version, and missing file

This is the smallest compliant executable surface for the current tranche:

- it satisfies `docs/design/workflow_command_adapter_contract.md`;
- it keeps validation explicit and testable;
- it avoids inventing a hidden Python branch inside review-loop lowering;
- it preserves a clean replacement path if future runtime `defschema`
  execution supersedes the adapter.

The adapter should validate:

- `schema_version == "ReviewFindings.v1"`;
- `items_path` is a non-empty workspace-relative path with no absolute or `..`
  escape;
- the target JSON exists and parses as an object compatible with
  `ReviewFindings.v1`;
- the JSON is not a pointer-path string or other non-object payload.

Its structured bundle output should echo the validated carrier record rather
than inventing a second semantic state shape.

### 3. Tighten Review-Loop Contract Validation Around Findings

The public `review-revise-loop` surface continues to accept caller-supplied
`:returns`, but typechecking must now enforce that every terminal variant
includes a validated findings carrier.

Implementation direction:

- keep `_validate_review_loop_result_contract(...)` as the boundary checker for
  the caller-supplied return union;
- add a compatibility helper in `contracts.py` that recognizes whether a field
  type is exactly `std/phase.ReviewFindings` or an equivalent imported alias;
- require:
  - `APPROVED` to include `findings`;
  - `BLOCKED` to include `findings`;
  - `EXHAUSTED` to include `findings`;
- preserve the current report-path/result-vocabulary requirements already owned
  by the prior review-loop slice in this tranche.

This slice deliberately does not force the entire target-design terminal shape
yet. It narrows only the findings obligation. Existing required fields such as
`checks_report`, `progress_report`, or `review_decision` may remain until a
later parity-normalization slice removes or renames them.

The same compatibility rule applies to the internal review decision contract
used by the generated review step:

- `APPROVE`, `REVISE`, and `BLOCKED` must all carry `findings ReviewFindings`;
- blocker-specific fields remain variant-specific as today;
- review-provider output that omits findings is an output-contract failure, not
  a best-effort fallback.

### 4. Validate Findings Before They Become Loop State

Review findings must not be written into loop-frame state directly from raw
provider output.

The generated/private review-loop workflow should route each review iteration
as:

1. review provider step emits a structured review-decision bundle;
2. a generated validator call runs `validate_review_findings_v1` on the
   review-decision `findings` carrier;
3. only the validated findings output is written into loop-frame outputs or
   terminal result projection;
4. `match` routes on the review decision after the validated findings carrier
   is available to the branch.

This preserves the target design's authority model:

- raw review-provider prose is not semantic authority;
- raw review-provider JSON is not enough until its findings payload validates;
- loop-frame findings are authoritative only after the validator step succeeds.

Lowering impact:

- add generated loop outputs for the validated carrier, for example
  `state__latest_findings__schema_version` and
  `state__latest_findings__items_path`;
- materialize those values on each completed review iteration alongside the
  existing last-review-report outputs;
- make final projection read findings from the validated loop outputs rather
  than from the first review step's raw bundle.

### 5. Revalidate Persisted Findings On Resume-Sensitive Consumption Edges

The selected target-design gap explicitly requires validation after resume
before resumed logic consumes carried findings.

In this slice, that rule applies to every edge where persisted loop-frame
findings are consumed after the runtime may resume from saved loop state:

- the `REVISE -> fix` edge;
- the exhaustion/final-projection edge when it reads the last loop-frame
  findings rather than same-iteration validator output.

Implementation direction:

- the generated workflow should insert a second validator call whenever it is
  about to consume `state.latest_findings` from persisted loop outputs rather
  than same-iteration review output;
- fix wrappers receive only the revalidated carrier record;
- exhausted final projection reads findings from the revalidated persisted
  carrier if the projection occurs from resumed loop state.

This keeps the slice bounded:

- no new reusable-state subsystem is introduced;
- no generic resume hook is required in the runtime;
- the review-loop generated workflow simply makes findings revalidation an
  ordinary explicit step on consumption paths that depend on persisted state.

If implementation proves that exhausted final projection always executes in the
same checkpoint context as the already validated last iteration and cannot
observe mutated findings artifacts, that narrower proof may justify skipping
the second exhausted-path validation. Absent that proof, the architecture
should keep the revalidation explicit.

### 6. Pass Validated Findings Into Fix Consumption Explicitly

Revise/fix logic must receive structured findings as input, not recover them
from markdown or from an implicit filesystem convention.

The public `review-revise-loop` macro surface does not need a new authored
argument for this slice. Instead, the generated monomorphic fix helper should
accept a validated findings parameter in its specialized internal signature.

Required behavior:

- same-iteration `REVISE` passes the validator output directly into the fix
  wrapper;
- resumed `REVISE` passes the revalidated persisted findings carrier into the
  fix wrapper;
- no fix path consumes raw JSON strings, raw artifact paths without validation,
  or markdown findings prose.

This decision reuses the prior generic-composition slice:

- provider/prompt refs remain compile-time-only;
- the only new runtime-visible value is the validated `ReviewFindings`
  record carrier;
- executable state still contains no runtime procedure values.

### 7. Update Stdlib Contract Metadata And Build Evidence

Because the review loop now includes a findings validator boundary,
`stdlib_contracts.py` and build artifacts must reflect that explicitly.

Required updates:

- the `review-revise-loop` stdlib contract records a certified-adapter backend
  dependency in addition to provider-driven steps already owned by the prior
  slice;
- adapter binding names include `validate_review_findings_v1`;
- command-boundary manifests include the generated validator step with fixture
  metadata and source-map lineage;
- source maps preserve:
  - the authored `review-revise-loop` call site;
  - the stdlib definition origin;
  - the generated validator step origin;
  - the generated managed bundle path origin for the validator result.

This keeps the adapter visible in the same provenance surfaces already used for
other certified adapters such as resource transition and reusable-state
validation.

## Package And File Footprint

Primary owned files:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_key_migrations.py`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `specs/dsl.md`
- `specs/io.md`

## Failure Modes And Diagnostics

Compile/typecheck failures:

- caller-supplied `ReviewLoopResult` omits `findings` on any terminal variant;
- `findings` uses a non-compatible type instead of `ReviewFindings`;
- generated review/fix helper signatures fail to accept the validated carrier.

Adapter/runtime validation failures:

- `schema_version` is not `ReviewFindings.v1`;
- `items_path` is absolute, escapes the workspace, or points at a pointer-like
  scalar payload;
- findings JSON is missing, malformed, or violates the `ReviewFindings.v1`
  schema;
- review provider returns a nominal decision variant but malformed findings,
  causing output-contract failure rather than semantic `APPROVE`/`REVISE`/
  `BLOCKED`.

Authority failures preserved by design:

- markdown findings extraction remains invalid;
- fix cannot treat pointer files or report prose as findings authority;
- review provider cannot replace carried evidence identities such as checks
  artifacts by returning alternate paths in findings payloads.

## Verification Strategy

Positive fixtures and tests should prove:

- `std/phase.orc` exports the carried-findings contract alongside
  `review-revise-loop`;
- review-loop typecheck requires `findings` on every terminal variant;
- lowering emits validator steps and loop-frame outputs for validated findings;
- `REVISE -> fix -> APPROVE` passes validated findings to fix exactly once per
  iteration;
- exhaustion terminal projection carries the last validated findings;
- resumed review-loop consumption revalidates persisted findings before fix or
  equivalent resumed consumption;
- command-boundary manifests and source maps record the findings validator step;
- migration-facing review-loop fixtures compile with the carried-findings
  contract.

Negative fixtures and tests should prove:

- malformed findings JSON fails as output-contract/adaptor failure, not as a
  semantic review decision;
- wrong `schema_version` fails validation;
- a pointer-like string payload fails pointer-authority validation;
- caller-supplied terminal result unions without findings fail typecheck;
- fix paths cannot consume raw findings paths without the validator boundary.

## Sequencing

Recommended sequencing for implementation:

1. Reuse or land the command-result managed-write-root slice so validator bundle
   paths stay compiler/runtime-owned.
2. Extend `std/phase.orc` and review-loop contract checking with the bounded
   `ReviewFindings` carrier.
3. Add the certified `validate_review_findings_v1` adapter binding and module.
4. Thread findings validation and revalidation through review-loop lowering and
   fix helper specialization.
5. Update fixtures, command-boundary manifests, and migration-facing tests.

This keeps the carried-findings slice additive and avoids mixing it with the
separate work of removing all remaining compiler-special review-loop plumbing.

## Bottom Line

The selected gap is not a generic collections project and not a second review
loop redesign. It is one bounded authority slice:

- define a typed path-backed findings carrier;
- validate it through an explicit certified adapter;
- store only validated findings in loop state;
- revalidate persisted findings before resumed consumption;
- project findings through terminal review-loop results and fix inputs.

That is the narrowest implementation architecture that satisfies the target
parity design's carried-findings requirement while staying coherent with the
existing review-loop and command-boundary slices.
