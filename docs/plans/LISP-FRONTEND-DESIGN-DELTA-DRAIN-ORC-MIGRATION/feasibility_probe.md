# Lisp Frontend Design Delta Drain .orc Feasibility Probe

Status: complete for first pass
Created: 2026-06-09
Plan task: `2. Feasibility Probe For .orc Imports, Calls, And Existing Stdlib Forms`

## Purpose

This probe records the compiler facts needed before creating the domain type
module for the design-delta drain `.orc` migration.

It does not translate the drain. It verifies that the planned migration route
has enough current frontend support to begin a principled candidate.

## Probe Results

| Probe | Result | Evidence |
| --- | --- | --- |
| Existing real design-doc review `.orc` compiles | pass | CLI compile produced zero diagnostics for `workflows/examples/review_revise_design_docs.orc` |
| Planned nested library import layout compiles | pass | `test_design_delta_migration_nested_library_import_layout_compiles` |
| `.orc` can call YAML only through imported workflow bundle manifest interop | pass | `test_design_delta_migration_yaml_call_interop_is_manifest_bundle_not_source_import` |
| stdlib `review-revise-loop` fixture compiles | pass | `test_design_delta_migration_stdlib_review_revise_loop_fixture_compiles` |
| provider-backed union/match projection compiles | pass | `test_design_delta_migration_union_match_projection_compiles` |

## CLI Compile Evidence

Command:

```bash
python -m orchestrator compile workflows/examples/review_revise_design_docs.orc \
  --source-root workflows/examples \
  --entry-workflow review-revise-design-docs \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Observed result:

- diagnostic count: `0`
- entry workflow: `review_revise_design_docs::review-revise-design-docs`
- build fingerprint: `07010d3030f6fa36`

## Test Evidence

Command:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

Observed result:

```text
4 passed in 0.29s
```

Collection check:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

Observed result:

```text
4 tests collected in 0.19s
```

## Findings

The planned nested module family shape is viable. A package such as
`lisp_frontend_design_delta/types`, `lisp_frontend_design_delta/selector`, and
`lisp_frontend_design_delta/entry` compiles through `compile_stage3_entrypoint`
with `source_roots`.

YAML-call interop exists through imported workflow bundle manifests. This is
useful as an interop checkpoint, but it is not a principled final migration of
the design-delta drain family because the YAML callee remains the semantic
owner.

The stdlib review/revise route is available through `std/phase.orc`.

Provider-backed union/match projection works. Pure in-memory match probes were
not used as evidence because Stage 3 currently requires match subjects in this
surface to be step-backed; that constraint matches the migration target, whose
important union values come from provider or command structured results.

## Next Step

Proceed to the domain type module for the candidate package layout.
