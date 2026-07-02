---
priority: 1
plan_path: ""
check_commands:
  - python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k "pointer or materialize or expected_outputs or call"
  - python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
  - python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run
prerequisites:
  - 2026-06-05-workflow-lisp-design-delta-drain-orc-migration
related_target_designs:
  - docs/design/workflow_lisp_runtime_native_drain_authoring.md
  - docs/design/workflow_lisp_frontend_specification.md
  - docs/design/workflow_lisp_key_migration_parity_architecture.md
signals_for_selection:
  - Promoted Workflow Lisp routes should pass typed values, artifact refs, provider outputs, resource transition results, and publication/bridge declarations directly.
  - Pointer files such as plan_path.txt, selection-bundle-path.json, drain_status.txt, and local *_path.txt files are still used as semantic glue in YAML-era library workflows and tests.
  - Call isolation moved many pointer files into generated call-local roots, exposing that tests and helper scripts still assume pointer files are the internal contract.
blocking_signals:
  - Do not remove pointer files that are still required by current YAML primary workflows without a compatibility bridge or replacement contract.
  - Do not weaken artifact lineage, expected-output validation, provider structured-output validation, or resume behavior to hide pointer-file use.
  - Do not treat a rendered report, pointer file, or debug bundle as semantic authority in promoted Workflow Lisp routes.
---

# Backlog Item: Retire Pointer Files From Workflow Lisp Internal Semantics

## Problem

Workflow Lisp is moving toward typed composition, private runtime context,
typed provider request/output records, resource transitions, and boundary-owned
publication/bridges. The current Design Delta drain stack still contains many
YAML-era pointer-file contracts, including files such as:

- `plan_path.txt`;
- `plan_review_report_path.txt`;
- `selection-bundle-path.json`;
- `drain_status.txt`;
- local `*_path.txt` materialization files.

These files remain useful as compatibility surfaces for existing YAML
workflows, helper scripts, and provider/output validation. They should not be
the semantic glue for promoted `.orc` composition.

Recent call isolation made the debt visible: the runtime correctly moved
callee write roots under generated call-local paths, but tests and fakes still
needed to hunt for or mirror pointer files. That means too much internal logic
still treats pointer files as the contract rather than as compatibility
materializations of typed state.

## Desired Outcome

Promoted Workflow Lisp routes do not depend on pointer files for internal
routing, typed value return, child workflow composition, provider result
transport, resource transition state, or resume/checkpoint authority.

Pointer files may remain only as explicitly declared boundary surfaces:

- compatibility bridges for legacy YAML or scripts;
- public/publication artifacts whose contract intentionally exposes a file;
- provider write-target materializations when no typed output-target substrate
  exists yet;
- low-level YAML compatibility while YAML remains primary.

## Scope

Inventory and retire pointer-file use from the Workflow Lisp Design Delta
family and its immediate runtime-native authoring path:

- `workflows/library/lisp_frontend_design_delta/*.orc`;
- `workflows/library/lisp_frontend_design_delta_*.v214.yaml`;
- Design Delta migration fixtures under `tests/fixtures/workflow_lisp/`;
- helper scripts that read/write pointer files as internal semantic state;
- tests that assume authored roots instead of typed/call-local contracts.

For each pointer-file use, classify it as:

- internal semantic glue to remove;
- provider/output-target compatibility to replace with typed output contracts;
- publication/bridge boundary to keep temporarily with owner and retirement
  condition;
- YAML-primary compatibility outside this item's deletion scope.

## Non-Goals

- Do not delete all pointer files globally.
- Do not redesign artifact lineage from scratch.
- Do not remove current YAML primary behavior before parity evidence exists.
- Do not replace pointer files with opaque Python helper state.
- Do not make parity depend on reproducing YAML's internal pointer-file layout
  or update order.

## Suggested Direction

1. Add a pointer-file census for the Design Delta Workflow Lisp family.
2. Replace internal pointer-file reads with typed values, artifact refs, or
   direct child-call return values where those contracts already exist.
3. Replace terminal status and summary pointer files with typed return values
   plus explicit publication or bridge declarations.
4. Replace provider output target pointers with typed provider output-target
   fields or runtime-owned structured-output bindings.
5. Keep remaining pointer files only at declared compatibility boundaries with
   owner, consumer, schema/renderer if applicable, and retirement condition.
6. Update tests so they verify typed contracts and boundary declarations rather
   than hard-coded pointer-file locations.

## Acceptance Criteria

- A checked-in census identifies all Design Delta pointer-file uses and their
  authority class.
- Promoted `.orc` internal composition does not consume pointer files as
  semantic state.
- Child workflow returns and terminal projections work through typed values,
  not `*_path.txt` handoffs.
- Resource transitions and resume/checkpoint behavior do not require authored
  pointer files.
- Remaining pointer files are limited to declared public/legacy boundary
  surfaces or YAML-primary compatibility.
- Tests cover call-local write-root isolation without assuming old authored
  pointer roots.
- Migration parity compares typed/public behavior, not pointer-file mechanics.

## Related Context

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/backlog/done/2026-05-09-dsl-v214-pointer-authority-clarification.md`
- `docs/backlog/active/2026-02-28-dsl-pointer-ownership-invariants.md`
- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- `workflows/library/lisp_frontend_design_delta/`
- `workflows/library/lisp_frontend_design_delta_*.v214.yaml`
