# Backlog Item: Migrate Lisp Frontend Design Delta Drain To Workflow Lisp

- Status: active
- Created on: 2026-06-05
- Priority: P2
- Plan: none yet

## Problem

The recently completed Lisp frontend design-delta drain still runs from YAML:

`workflows/examples/lisp_frontend_design_delta_drain.yaml`

That workflow now exercises the most important Workflow Lisp migration use
cases: selector routing, design-gap drafting, work-item execution,
recover-before-select blocked recovery, prerequisite recovery, target-design
revision, same-gap retry, run-state bookkeeping, and drain summary publication.

Keeping it YAML-only means the active Workflow Lisp compiler work is still
managed by a workflow that does not itself prove the `.orc` authoring model for
complex autonomous drains.

## Desired Outcome

Create a Workflow Lisp `.orc` migration candidate for the Lisp frontend
design-delta drain and prove it is non-regressive against the YAML primary.

Candidate path:

`workflows/examples/lisp_frontend_design_delta_drain.orc`

The `.orc` version should express the same high-level behavior as the YAML
primary:

- initialize or preserve durable drain run state;
- recover existing blocked design gaps before normal selection;
- use the existing selector for normal work and prerequisite-context work;
- draft missing design-gap architectures when selected;
- run selected backlog/design-gap work items;
- record completed, blocked, recovered, and retry-ready states;
- keep recoverable blockers nonterminal unless genuine user intervention is
  required;
- publish the final drain summary and workflow outputs.

## Migration Constraints

The YAML workflow remains authoritative until parity evidence is computed.

Do not:

- replace the YAML primary merely because the `.orc` version compiles;
- weaken recovery behavior to make the migration easier;
- collapse provider-owned semantic decisions into deterministic Python rules;
- reintroduce terminal blocking as the default for recoverable prerequisite or
  design-revision cases;
- hide run-state updates, selector effects, provider calls, command adapters,
  artifact paths, or recovery routing from generated Core AST, Semantic IR,
  source maps, validation, or runtime artifacts;
- delete or bypass the existing library workflows before the `.orc` route has
  parity evidence.

## Suggested Implementation Direction

1. Inventory the YAML workflow's public boundary:
   - inputs and outputs;
   - imported library workflows;
   - selector and recovery routes;
   - run-state scripts;
   - provider prompts;
   - artifact roots and summary paths;
   - repeat/termination semantics.
2. Split the migration into reusable `.orc` modules rather than one huge file:
   - drain iteration;
   - recovery-before-selection;
   - normal/prerequisite selection;
   - selected work execution;
   - blocked recovery recording;
   - final drain summary.
3. Reuse existing library workflows or command adapters where they remain the
   shared contract. Do not inline their behavior unless the `.orc` language has
   the typed stdlib support to express it cleanly.
4. Add the migration target to
   `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`.
5. Add compile, dry-run, output-contract parity, terminal-state parity,
   artifact parity, and resume/recovery parity checks.
6. Measure authored LOC for the YAML primary plus imported YAML libraries
   against the `.orc` candidate plus imported `.orc` modules.
7. Record remaining unsupported frontend/stdlib gaps rather than papering them
   over with YAML-shaped Lisp.

## Acceptance Criteria

- `workflows/examples/lisp_frontend_design_delta_drain.orc` compiles through
  Workflow Lisp.
- Generated Core AST, Semantic IR, source map, and debug projection are
  inspectable.
- Shared validation accepts the generated workflow.
- Dry-run succeeds with the same required inputs as the YAML primary.
- A deterministic smoke or mocked-provider test covers at least one full drain
  iteration.
- Recovery parity tests cover:
  - existing blocked gap before normal selection;
  - target-design revision followed by prerequisite selection;
  - prerequisite completion followed by retry of the original gap;
  - same-gap retry after `RETRY_READY`;
  - genuine terminal user-intervention case.
- Output contract parity, terminal-state parity, artifact parity, and
  resume/reuse parity pass against the YAML primary.
- The parity report computes `non_regressive=true` before any recommendation to
  make the `.orc` version primary.
- Remaining verbosity is classified as semantic declaration, required recovery
  contract, migration parity obligation, or missing frontend/stdlib ergonomics.

## Related Context

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/backlog/active/2026-05-28-lisp-migrate-key-workflows.md`
- `docs/backlog/active/2026-06-05-workflow-lisp-design-plan-stack-review-loop-stdlib-consumption.md`
