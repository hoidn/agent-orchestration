# Workflow Lisp Design/Plan/Impl Stack Parity-Evidence Refresh Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-design-plan-impl-stack-parity-evidence-refresh`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-evidence refresh gap:

- refresh and reconcile the durable `design_plan_impl_stack` migration-parity
  evidence after the prerequisite review-loop, findings, reusable-state,
  promoted-entry, and default slices have landed;
- make the checked-in family entry in
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  reflect the actual post-prerequisite evidence route rather than the older
  generic `review_loop_parity_fixture` selectors;
- regenerate the authoritative family parity JSON report plus its derived
  markdown and aggregate index so they agree with the current family evidence;
- reconcile drain-facing status artifacts that still summarize the family as
  blocked on the old YAML-loop mechanic or use stale execution-target wording;
- preserve the existing migration-parity command/report tool as the authority
  for `non_regressive` computation instead of hand-editing report outcomes.

Out of scope for this slice:

- rewriting the family `.orc` workflows, imported stdlib review-loop lowering,
  structured findings transport, `resume-or-start`, promoted-entry hidden
  binding, workflow defaults, or any other generic Workflow Lisp/runtime
  substrate;
- editing `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`, backlog
  queues, or historical drain event ledgers by hand;
- declaring the family promoted to primary YAML replacement without rerunning
  the existing parity gate;
- adding new command adapters, runtime-native effects, report parsing, or
  pointer-authority exceptions.

This is a bounded implementation architecture for one evidence-reconciliation
gap only. It does not replace the parent migration architecture or reopen the
family implementation slice.

## Problem Statement

The selected migration architecture already established the intended evidence
contract:

- `non_regressive` is computed from deterministic evidence, not authored by
  hand;
- the family parity report, markdown projection, and aggregate index must all
  be derived from the same canonical JSON evidence;
- durable migration evidence must reflect the current family state rather than
  historical blockers that were tied to earlier prerequisite gaps.

The current checkout still violates that contract in four concrete ways:

1. `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json` records
   `workflow-lisp-design-plan-impl-stack-review-loop-parity` as completed on
   `2026-06-03T11:28:02.880267Z`, but the canonical parity surfaces do not
   reflect a post-prerequisite rerun.
2. `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
   and the derived markdown/index still report `non_regressive=false` and
   still carry the older unresolved deprecated mechanic
   `full YAML review-revise loop with carried findings extraction`.
3. The checked-in target manifest entry for `design_plan_impl_stack` still
   points several evidence roles at the generic
   `review_loop_parity_fixture` selector and still lists the older unresolved
   deprecated mechanic, while
   `tests/test_workflow_lisp_migration_parity.py::test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence`
   already expects those stale values to be gone.
4. Drain-facing summaries still carry stale path/status wording, including the
   older execution-target examples from blocked family plans, so the durable
   evidence story disagrees about what the canonical family check actually is.

There is one additional feasibility concern that this slice must surface
explicitly instead of papering over:

- the checked-in family Workflow Lisp source and compile-focused migration tests
  still look like the pre-refresh single-pass family state, so the evidence
  refresh must begin with an audit gate. If the family implementation proofs do
  not actually support the post-prerequisite route, this slice must emit a
  truthful regressive report or hand the blocker back to the owning family
  slice rather than authoring a false promotion-ready report.

The gap is therefore not “make the report green.” The gap is to make the
durable parity evidence truthful, deterministic, and coherent with the current
family implementation state and the existing migration-parity toolchain.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Migration Promotion`
  - `Success Criteria`
  - `Stop / Revise Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 2.2, 18, 45-48, 74-80, 95, 105
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/execution_plan.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep the migration-parity JSON report authoritative and keep markdown,
  aggregate indexes, drain summaries, and execution notes as derived views;
- keep `non_regressive` computed only by `orchestrator migration-parity`;
- keep deterministic evidence commands explicit in the manifest and never
  hidden behind shell pipelines or prose-only notes;
- keep command-step/report authority rules from
  `docs/design/workflow_command_adapter_contract.md` authoritative even though
  this slice should not add adapters or scripts;
- treat a completed drain event as historical evidence, not as sufficient proof
  that the checked-in family implementation or parity report is up to date;
- do not use the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/execution_plan.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-promoted-entry-hidden-reusable-call-binding/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`

### Decisions Reused

- Reuse the migration-promotion slice’s manifest/report/index model and keep
  `orchestrator/workflow_lisp/migration_parity.py` as the authority for
  evidence execution, JSON report writing, markdown rendering, and
  `non_regressive` computation.
- Reuse the family review-loop parity slice as the owner of actual family
  `.orc` behavior changes; this slice only consumes or audits that outcome.
- Reuse the command-result/public-input/default/reusable-state prerequisite
  slices as already-selected semantic evidence sources rather than reopening
  their implementation.
- Reuse the current CLI surface
  `python -m orchestrator migration-parity --target design_plan_impl_stack`
  rather than inventing a separate report-refresh tool.

### New Decisions In This Slice

- Add one explicit audit gate before report regeneration: the family evidence
  refresh is allowed to proceed only after running the focused family/proof
  checks that distinguish “post-prerequisite family implementation exists” from
  “run-state completion is stale.”
- Treat the `design_plan_impl_stack` manifest entry as part of the durable
  evidence contract, not merely test data. Its command selectors, deprecated
  mechanics, and dry-run inputs must match the actual family proof route.
- Reconcile all family status summaries to the authoritative parity JSON report;
  no drain-facing note may keep the old YAML-loop blocker once the refreshed
  report names a different outcome.
- Normalize the family execution-target wording to the manifest-backed canonical
  dry-run path/default route instead of older blocked-plan example paths.

### Conflicts Or Revisions

The earlier family parity architecture owned both behavior changes and evidence
refresh in one slice. The current selected gap revises that scope split
narrowly:

- the prior family slice remains the owner of real Workflow Lisp family
  implementation;
- this slice owns only the evidence audit, manifest alignment, regenerated
  parity artifacts, and drain-facing reconciliation that must happen after that
  implementation is supposedly complete.

This slice also revises one implicit assumption present in some drain artifacts:

- a `completed` event in `run_state.json` is not enough to justify editing the
  parity report to success;
- the authoritative refresh must come from rerun deterministic evidence, and it
  may still yield a regressive report if the family implementation proof is not
  actually present in the checkout.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, family review-loop behavior, and
runtime execution ownership remain with their existing owners.

## Ownership Boundaries

This slice owns:

- the `design_plan_impl_stack` entry in
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`;
- evidence-facing assertions in `tests/test_workflow_lisp_migration_parity.py`
  and any narrowly required family-evidence selectors in
  `tests/test_workflow_lisp_key_migrations.py`;
- regenerated family parity artifacts:
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- historical or drain-facing summary docs that cite the family parity outcome,
  specifically `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`,
  if their current text conflicts with the regenerated canonical report.

This slice intentionally does not own:

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc` or the
  library `.orc` family modules, except to inspect them during the audit gate;
- generic parity engine design, unless a narrow implementation defect in the
  existing parity command prevents truthful family refresh;
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`,
  backlog manifests, or progress ledgers;
- new adapters, scripts, runtime effects, or Workflow Lisp semantics.

## Current Checkout Facts

The current checkout already contains the main substrate this slice should
reuse:

- `orchestrator/workflow_lisp/migration_parity.py` exists, loads the checked-in
  manifest, executes deterministic evidence commands, writes per-family JSON
  reports and derived markdown/index views, and computes `non_regressive`.
- `orchestrator/cli/commands/migration_parity.py` already supports
  `--target design_plan_impl_stack`, so the family report can be refreshed in
  isolation.
- `tests/test_workflow_lisp_migration_parity.py` already contains a focused
  family manifest expectation,
  `test_design_plan_impl_stack_manifest_uses_defaulted_dry_run_and_family_specific_evidence`,
  that encodes the intended post-refresh evidence route.
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is still empty, so
  no later ledger event supersedes the selector rationale.

The same checkout also shows the exact evidence debt still present:

- `run_state.json` records the family implementation gap as completed, but the
  canonical parity report remains stale and regressive.
- the current family manifest still uses the older generic
  `review_loop_parity_fixture` selectors and still lists the old unresolved
  YAML-loop mechanic in `deprecated_yaml_mechanics`.
- the current parity markdown still says `Non-regressive: false` and still
  renders the unresolved older blocker text.
- the current execution summary doc still says the family is regressive.
- the current family source and compile-focused migration test still resemble
  the older single-pass family state, so a truthful refresh cannot skip the
  audit step and cannot assume promotion-ready family behavior from the
  run-state event alone.

This makes the slice feasible without broad new code: the parity tool exists,
the family-specific expectation already exists in tests, and the main missing
work is to realign checked-in evidence surfaces to the actual family proof
state.

## Proposed Architecture

### 1. Add An Evidence Audit Gate Before Any Report Rewrite

Refreshing the parity report is only safe if the evidence reflects the current
family implementation rather than historical assumptions.

The implementation should therefore start with one explicit audit phase:

- run the focused family migration/parity tests and the deterministic family
  `migration-parity` command path;
- inspect whether the family-specific evidence route expected by
  `tests/test_workflow_lisp_migration_parity.py` actually exists in the
  checkout;
- if the family implementation proof is absent or fails, stop and either:
  - keep `non_regressive=false` with the actual current blocker recomputed by
    the parity tool; or
  - hand the blocker back to the owning family implementation slice if the
    checkout still lacks the intended ordinary `.orc` review-loop behavior.

This audit gate is the required feasibility proof for the selected refresh
slice. It prevents a false success report driven only by run-state history.

### 2. Make The Family Manifest Entry Match The Actual Evidence Route

The checked-in `design_plan_impl_stack` manifest entry is part of the durable
parity contract. It must be updated so it describes the current family proof
path rather than older generic fixtures.

Required manifest behavior after the refresh:

- `dry_run` uses the defaulted wrapper route expected by the parity tests, not
  an explicit list of business inputs if those defaults are now part of the
  family boundary contract;
- `smoke_or_integration`, `output_contract_parity`,
  `terminal_state_parity`, and `artifact_parity` use family-specific evidence
  selectors and stop pointing at the generic `review_loop_parity_fixture`
  selector once the family has its own proof;
- `resume_parity` points at the approved reusable-state family proof route;
- `deprecated_yaml_mechanics` lists only mechanics still unresolved after the
  audit. The older
  `full YAML review-revise loop with carried findings extraction` entry must be
  removed once the family proof genuinely stops depending on that blocker.

If the audit proves the family implementation is still old, the manifest must
still be refreshed to describe the truthful blocker/evidence route rather than
keep obsolete selectors that no longer match the intended family proof.

### 3. Regenerate Canonical Parity Artifacts Only Through The Existing CLI

Do not hand-edit generated report files.

The implementation should use only:

```bash
python -m orchestrator migration-parity \
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity \
  --target design_plan_impl_stack
```

That command remains the sole authority for:

- rerunning compile, dry-run, smoke/integration, output-contract, terminal,
  artifact, and resume evidence;
- computing `non_regressive`;
- writing the authoritative JSON report;
- projecting the derived markdown report and aggregate index entry.

The refresh slice should treat the generated JSON as canonical and verify that
the derived markdown and `index.json` exactly agree on:

- `workflow_family`
- `candidate`
- `yaml_primary`
- `non_regressive`
- promotion eligibility
- blocker or deprecated-mechanic summary

### 4. Reconcile Drain-Facing And Historical Summaries To The Canonical Report

After the JSON/markdown/index refresh, any checked-in status summary that still
describes the family must be reconciled to that canonical report.

This includes two kinds of stale wording:

- stale outcome wording:
  e.g. “family remains regressive because of the old YAML review-revise loop
  blocker” when the refreshed report names a different outcome;
- stale execution-target wording:
  e.g. blocked-plan example paths such as
  `provider-session-resume-execution-report.md` when the canonical family
  parity route is the manifest-backed dry-run/default path.

This reconciliation is documentation/status alignment only. It must not rewrite
run-state history or fabricate a completed family implementation that the audit
did not prove.

### 5. Keep Failure Handling Truthful And Narrow

The refresh slice must not broaden into code implementation work simply because
the audit may expose one more family inconsistency.

If the audit shows:

- the family `.orc` implementation is still pre-refresh, or
- the family-specific proof route is absent, or
- the parity engine cannot truthfully express the new family state,

then the implementation should:

- keep the regenerated evidence regressive or blocked with the actual current
  reason; and
- return that blocker to the owning family or parity-tool slice instead of
  patching unrelated frontend/runtime behavior here.

## Verification Strategy

Use deterministic, visible checks only.

Required verification shape:

1. collect the focused evidence test modules;
2. run the focused parity-manifest assertion for `design_plan_impl_stack`;
3. run the focused family migration proofs needed to justify the refresh;
4. rerun the family-only `migration-parity` command;
5. inspect the regenerated JSON/index/markdown for coherence and blocker text.

The refreshed slice is verified only when the report outcome is demonstrably
recomputed from the current evidence route rather than copied from prior
artifacts.

## Acceptance Conditions

- the `design_plan_impl_stack` manifest entry no longer contains stale generic
  selectors or obsolete deprecated-mechanic text that contradict the intended
  post-prerequisite family proof route;
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  is regenerated through `orchestrator migration-parity` and becomes the
  authoritative family status source;
- the derived markdown and aggregate index agree with that JSON report;
- drain-facing or historical summaries that mention this family no longer
  contradict the regenerated canonical report on status or canonical
  execution-target wording;
- if the family implementation audit still fails, the refreshed evidence names
  that real blocker instead of preserving the older YAML-loop blocker or
  authoring a false success state;
- no manual `non_regressive` edits, run-state edits, adapter additions, or
  frontend/runtime redesign are introduced.
