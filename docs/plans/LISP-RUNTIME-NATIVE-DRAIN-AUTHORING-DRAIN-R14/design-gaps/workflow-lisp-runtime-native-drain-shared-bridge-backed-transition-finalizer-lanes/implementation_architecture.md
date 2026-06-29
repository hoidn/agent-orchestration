# Shared Bridge-Backed Transition Finalizer Lanes Implementation Architecture

## Scope

This slice exists to unblock the no-internal-compatibility-carrier work by
repairing one source-level boundary problem:

- imported `finalize-selected-item` should return typed terminal values;
- retained run-state or summary files must be boundary effects, not ordinary
  values carried through `.orc` composition; and
- the parent Design Delta drain must compile without restoring
  `run_state_path` or summary-path transport to selected-item payloads,
  loop-state records, child-call signatures, or provider prompt subjects.

This is not a promotion, parity, manifest, or conformance-profile slice.
Those artifacts may be refreshed during closeout, but they do not define this
implementation's completion unless they are direct runtime inputs or prove that
the source behavior is still wrong.

## Governing Constraints

The target design is
`docs/design/workflow_lisp_runtime_native_drain_authoring.md`. The baseline
compatibility contract is
`docs/design/workflow_lisp_frontend_specification.md`. The command-adapter
contract remains authoritative for retained command backends.

The slice must preserve these rules:

- typed values, structured bundles, transitions, and Semantic IR are semantic
  authority;
- reports, pointer files, run-state files, summary files, and debug YAML are
  views unless a boundary contract says otherwise;
- `resource-transition` is the authored surface for durable mutation;
- publication and compatibility bridges are boundary effects over typed
  values, not return mechanics; and
- compatibility values must not be reintroduced into internal composition just
  to keep old YAML-era files alive.

## Current Failure

The live route is broken before any evidence question matters:

- `work_item.orc` calls `project-selected-compat` without the required
  `run_state_path`;
- `work_item.orc`, `stdlib_payloads.orc`, and `stdlib_adapters.orc` also have
  latent `project-compat-run-state` calls with the same carrier-removal shape;
  and
- `drain.orc` imports these routes directly, so the parent drain compile is the
  first required proof.

The fix must finish removing that carrier from internal composition. It must
not satisfy the typechecker by adding `run_state_path` back to public/domain
payloads or child-call boundaries.

## Architecture

The intended shape is:

```lisp
(let* ((terminal (finalize-selected-item selected result)))
  terminal)
```

If a public summary, legacy file, or durable state update is still needed, it is
a separate effect over `terminal`:

```lisp
(let* ((terminal (finalize-selected-item selected result))
       (_ (publish-selected-summary terminal))
       (_ (record-selected-transition selected terminal)))
  terminal)
```

The first form must work without the second form. Returning the typed terminal
value must not depend on body-owned materialization, report parsing, pointer
files, compatibility bundle rereads, or hidden `StateExisting` transport.

Allowed retained durability:

- boundary publication from a typed terminal value;
- declared compatibility bridge for a named legacy consumer;
- typed `resource-transition` or certified transition backend for durable
  mutation; and
- runtime-owned checkpoint/resume state, outside authored workflow data.

Forbidden fixes:

- adding `run_state_path`, summary paths, pointer paths, or generated roots to
  user-facing/domain records;
- moving the same path carrier into a differently named wrapper type;
- making publication or bridge generation a prerequisite for typed return;
- parsing reports or pointer files as semantic input; or
- special-casing the Design Delta family in compiler/runtime code.

## Implementation Surface

Expected source files:

- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/work_item_bridge_support.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- mirrored runtime fixtures only when their authoritative source changes

Shared Python helpers should change only if the source fix exposes a generic
compile/runtime defect. Do not change helper code merely to serialize better
reports.

## Verification

Required source behavior checks:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_compiles_with_hidden_private_context -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Add the narrowest relevant runtime smoke if the route can run locally after it
compiles. Add one outside-use check only when a shared production helper is
changed.

Do not make broad conformance, parity, manifest, inventory, or generated-report
refresh a blocking gate for this slice.

## Acceptance

This slice is complete when:

- the parent Design Delta drain compiles through the repaired route;
- imported `finalize-selected-item` returns typed terminal values without
  depending on summary materialization or compatibility bundle rereads;
- ordinary internal composition no longer carries `run_state_path` or summary
  paths merely to make typed return work; and
- focused tests cover the repaired behavior.

Closeout artifacts may still need refresh after this slice. That is follow-up
work unless stale artifacts are direct runtime inputs or reveal a current
behavior defect.
