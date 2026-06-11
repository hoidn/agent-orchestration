# Workflow Lisp Route/Readiness Classification Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, machine-checked Workflow Lisp route/readiness registry so checked-in `.orc` examples, representative fixtures, compiler/lowering tests, and migration-parity targets cannot cite stale or legacy-only surfaces as current WCC/default evidence.

**Architecture:** Implement a metadata-only registry and validation layer over existing lowering-route and migration-parity surfaces. The registry records route/readiness labels, validates coverage and route/schema consistency, exposes a narrow CLI check, and gives representative tests a helper that compiles with the registered route or explicitly verifies the default route. It must not change compiler lowering, runtime behavior, semantic IR, executable IR, source maps, promotion gate computation, WCC route selection, or legacy compatibility behavior.

**Tech Stack:** Python dataclasses/enums/JSON, `orchestrator.workflow_lisp.wcc.route.LoweringRoute`, pytest, existing `orchestrator` argparse CLI, Markdown docs.

---

## Governing Context

Read before implementation:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-route-readiness-classification-registry/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`

Key constraints:

- The route enum and route-to-schema mapping remain owned by `orchestrator/workflow_lisp/wcc/route.py`.
- Build artifacts continue to expose only `lowering_schema_version`; do not put route names into manifests, source maps, Semantic IR, executable IR, runtime state, or generated workflow artifacts.
- Migration parity remains the authority for computed `non_regressive` and `eligible_for_primary_surface`. The registry can mark route/readiness identity stale; it must not author promotion results.
- This slice is classification and evidence validation only. Do not change WCC lowering, legacy lowering, parent-drain behavior, command adapter certification, or promotion gate policy.

## File Map

Create:

- `orchestrator/workflow_lisp/route_readiness.py`: registry schema constants, dataclasses, loader, validators, required-surface discovery, migration-target comparison, and test helper.
- `orchestrator/cli/commands/route_readiness.py`: CLI wrapper for registry validation.
- `tests/test_workflow_lisp_route_readiness.py`: focused unit/CLI/helper tests for registry and parity identity validation.
- `docs/workflow_lisp_route_readiness_registry.json`: checked-in v1 registry.

Modify:

- `orchestrator/cli/main.py`: add `workflow-lisp-route-readiness` subcommand and dispatch.
- `orchestrator/cli/commands/__init__.py`: export the new command handler.
- `orchestrator/workflow_lisp/migration_parity.py`: add import-light validation hook callable by tests and future CLI integration; do not change report computation unless tests explicitly exercise the hook.
- `tests/test_workflow_lisp_migration_parity.py`: add route/readiness registry mismatch tests or call the hook from the new route-readiness test module if that keeps ownership cleaner.
- `tests/test_workflow_lisp_examples.py`: convert representative example compile tests to use the registry helper.
- `tests/test_workflow_lisp_build_artifacts.py`: add helper coverage proving route names stay out of artifacts while schema remains checked.
- `workflows/README.md`: add route/readiness label guidance for Workflow Lisp examples.
- `docs/lisp_workflow_drafting_guide.md`: state that `.orc` copy safety comes from registry labels plus migration/parity evidence, not filename recency or prose.

Do not modify:

- `orchestrator/workflow_lisp/wcc/route.py` except if a failing test proves an existing route normalization bug. This plan assumes it is correct.
- Core AST, Semantic IR, executable IR, source-map serializers, WCC lowerers, runtime execution, command adapters, or YAML workflow semantics.

## Initial Required Registry Coverage

`discover_required_orc_surfaces(repo_root)` must require these groups:

- Every direct `.orc` under `workflows/examples/`:
  - `workflows/examples/cycle_guard_demo.orc`
  - `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
  - `workflows/examples/effectful_let_star_normalization.orc`
  - `workflows/examples/effectful_match_arm_normalization.orc`
  - `workflows/examples/kiss_backlog_item.orc`
  - `workflows/examples/review_revise_design_docs.orc`
  - `workflows/examples/review_revise_parametric_design_docs.orc`
  - `workflows/examples/same_file_record_call_binding.orc`
  - `workflows/examples/with_phase_composed_binding.orc`
- Every `.orc` under `workflows/library/lisp_frontend_design_delta/`:
  - `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc`
  - `workflows/library/lisp_frontend_design_delta/drain.orc`
  - `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
  - `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
  - `workflows/library/lisp_frontend_design_delta/selector.orc`
  - `workflows/library/lisp_frontend_design_delta/types.orc`
  - `workflows/library/lisp_frontend_design_delta/work_item.orc`
- Every `.orc` candidate referenced by `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`.
- Every `.orc` under `tests/fixtures/workflow_lisp/characterization/sources/`:
  - `design_delta_union_match_projection.orc`
  - `wcc_ifexpr_loop_body.orc`
  - `wcc_ifexpr_non_tail_binding.orc`
  - `wcc_ifexpr_tail.orc`
  - `wcc_m2_straight_line_effects.orc`
  - `wcc_m3_branch_local_ref_leak.orc`
  - `wcc_m3_nested_join_inside_arm.orc`
  - `wcc_m3_nested_non_tail_match.orc`
  - `wcc_m4_implementation_phase_full_fixture.orc`
  - `wcc_m4_loop_under_case.orc`
- Checked-in Design Delta valid fixtures:
  - `tests/fixtures/workflow_lisp/valid/design_delta_nested_branch_scope_collision.orc`
  - `tests/fixtures/workflow_lisp/valid/design_delta_nested_implementation_phase.orc`
  - `tests/fixtures/workflow_lisp/valid/design_delta_nested_imported_branch_effects.orc`
  - `tests/fixtures/workflow_lisp/valid/design_delta_nested_same_file_call_local_record.orc`
  - `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_implementation_phase.orc`
  - `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc`
  - all `.orc` under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`.

Ordinary invalid fixtures under `tests/fixtures/workflow_lisp/invalid/` are not registry-required unless a doc, parity target, or registry-covered test cites them as evidence. If cited, register them as `historical_negative` with the expected diagnostic in `evidence` or `notes`.

Use conservative labels. Do not mark a surface `wcc_default` unless a test or CLI compile path proves it under `DEFAULT_LOWERING_ROUTE`. Use `legacy_schema1_compat`, `migration_candidate`, `historical_negative`, or `stale_needs_update` when the current evidence is legacy-only, mid-migration, expected-negative, or stale.

## Registry Contract

The JSON file is:

```json
{
  "schema_version": "workflow_lisp_route_readiness_registry.v1",
  "updated": "2026-06-10",
  "surfaces": []
}
```

Each `surfaces[]` entry requires:

- `surface_id`: unique stable dotted id.
- `path`: repo-relative path.
- `surface_kind`: `workflow_example`, `library_workflow`, `test_fixture`, `compiler_test`, `migration_target`, or `migration_evidence`.
- `route_label`: `wcc_default`, `legacy_schema1_compat`, `historical_negative`, `migration_candidate`, or `stale_needs_update`.
- `evidence`: non-empty list of pytest selectors, CLI commands, reports, or diagnostic names.

Route-bearing entries also require:

- `lowering_route`: one of `legacy`, `wcc_m1`, `wcc_m2`, `wcc_m3`, `wcc_m4`.
- `lowering_schema_version`: `1` for `legacy`, `2` for WCC routes.

Migration entries and `migration_candidate` entries also require:

- `readiness_label`: `leaf_compile_candidate`, `leaf_runtime_candidate`, `parent_callable_candidate`, `family_non_regressive`, or `promotion_eligible`.

Stale entries require one of:

- `owner`
- `replacement_or_retirement_path`

Recommended fields:

- `entry_workflow`
- `source_roots`
- `copy_safety`
- `notes`
- `parity_constrained`

Route rules:

- `wcc_default` must use `DEFAULT_LOWERING_ROUTE` and its schema.
- `legacy_schema1_compat` must use `LoweringRoute.LEGACY` and schema `1`.
- `historical_negative` may omit route/schema only when the surface is intentionally parse/type/lint failing.
- Preview routes `wcc_m1`, `wcc_m2`, and `wcc_m3` may appear only as historical, compatibility, or explicitly scoped evidence; they are not default-route evidence.

## Task 1: Add Failing Registry Module Tests

**Files:**

- Create: `tests/test_workflow_lisp_route_readiness.py`
- Later create: `orchestrator/workflow_lisp/route_readiness.py`

- [ ] **Step 1: Write tests for the public registry API**

Add tests that import:

```python
from orchestrator.workflow_lisp.route_readiness import (
    ROUTE_READINESS_SCHEMA_VERSION,
    RouteReadinessError,
    compile_registered_route_case,
    discover_required_orc_surfaces,
    load_route_readiness_registry,
    registry_entry_for_path,
    validate_migration_targets_against_route_readiness,
    validate_route_readiness_registry,
)
```

Test cases:

- checked-in `docs/workflow_lisp_route_readiness_registry.json` loads and validates.
- `discover_required_orc_surfaces(REPO_ROOT)` includes all initial required paths listed above.
- missing registry coverage emits `route_readiness_surface_missing`.
- unknown `surface_kind`, `route_label`, `readiness_label`, or `lowering_route` emits the matching stable code.
- `legacy` with schema `2` emits `route_readiness_schema_mismatch`.
- `wcc_default` with any route other than `DEFAULT_LOWERING_ROUTE` emits `route_readiness_default_route_mismatch`.
- `stale_needs_update` without `owner` or `replacement_or_retirement_path` emits `route_readiness_stale_surface_without_owner`.
- duplicate `surface_id` and duplicate `path` fail deterministically.
- `registry_entry_for_path` returns the normalized entry for a repo-relative path and returns `None` for unknown paths.

Use helper writers inside the test module to build temporary registry JSON payloads rather than mutating the checked-in registry.

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected: fails because `orchestrator.workflow_lisp.route_readiness` does not exist yet.

## Task 2: Implement `route_readiness.py`

**Files:**

- Create: `orchestrator/workflow_lisp/route_readiness.py`
- Test: `tests/test_workflow_lisp_route_readiness.py`

- [ ] **Step 1: Add dataclasses and constants**

Implement these names:

```python
ROUTE_READINESS_SCHEMA_VERSION = "workflow_lisp_route_readiness_registry.v1"

SURFACE_KINDS = frozenset({
    "workflow_example",
    "library_workflow",
    "test_fixture",
    "compiler_test",
    "migration_target",
    "migration_evidence",
})

ROUTE_LABELS = frozenset({
    "wcc_default",
    "legacy_schema1_compat",
    "historical_negative",
    "migration_candidate",
    "stale_needs_update",
})

READINESS_LABELS = frozenset({
    "leaf_compile_candidate",
    "leaf_runtime_candidate",
    "parent_callable_candidate",
    "family_non_regressive",
    "promotion_eligible",
})
```

Use frozen dataclasses for parsed entries and validation issues. Keep the raw optional fields accessible for docs/tests.

- [ ] **Step 2: Implement loader and pure validation**

Functions:

```python
def load_route_readiness_registry(path: Path) -> RouteReadinessRegistry: ...
def validate_route_readiness_registry(registry: RouteReadinessRegistry, repo_root: Path) -> RouteReadinessValidation: ...
def discover_required_orc_surfaces(repo_root: Path) -> set[str]: ...
def registry_entry_for_path(registry: RouteReadinessRegistry, path: str) -> RouteReadinessEntry | None: ...
```

Validation should accumulate issues in a result object instead of raising for ordinary invalid registry content. Raise `RouteReadinessError` only for unreadable/malformed JSON or an invalid top-level schema shape. The CLI will use this distinction for exit code `2` versus `1`.

Stable issue codes:

- `route_readiness_registry_schema_invalid`
- `route_readiness_surface_missing`
- `route_readiness_path_unknown`
- `route_readiness_label_invalid`
- `route_readiness_route_unknown`
- `route_readiness_schema_mismatch`
- `route_readiness_default_route_mismatch`
- `route_readiness_migration_target_missing`
- `route_readiness_migration_target_mismatch`
- `route_readiness_stale_surface_without_owner`
- `route_readiness_evidence_self_referential`
- `route_readiness_test_route_unpinned`

- [ ] **Step 3: Implement required-surface discovery**

Use `Path.glob` / `Path.rglob`; do not shell out.

Discovery details:

- examples: `(repo_root / "workflows/examples").glob("*.orc")`
- design-delta library: `(repo_root / "workflows/library/lisp_frontend_design_delta").rglob("*.orc")`
- parity candidates: parse `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` and include `candidate` values ending in `.orc`
- WCC characterization: `(repo_root / "tests/fixtures/workflow_lisp/characterization/sources").glob("*.orc")`
- Design Delta valid fixtures: `(repo_root / "tests/fixtures/workflow_lisp/valid").glob("design_delta*.orc")` plus `(repo_root / "tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime").rglob("*.orc")`

Normalize all paths with POSIX separators relative to `repo_root`.

- [ ] **Step 4: Implement route/schema validation**

Import only:

```python
from orchestrator.workflow_lisp.wcc.route import (
    DEFAULT_LOWERING_ROUTE,
    LoweringRoute,
    lowering_schema_for_route,
    normalize_lowering_route,
)
```

Rules:

- Unknown route string produces `route_readiness_route_unknown`.
- If `lowering_route` is present, `lowering_schema_version` is required and must equal `lowering_schema_for_route(route)`.
- `wcc_default` must normalize to `DEFAULT_LOWERING_ROUTE`.
- `legacy_schema1_compat` must normalize to `LoweringRoute.LEGACY`.
- If `route_label` is not `historical_negative`, route/schema are required.
- If `route_label` is `migration_candidate`, `readiness_label` is required and valid.
- If `readiness_label` is `promotion_eligible`, the entry should not have `copy_safety` indicating stale or not-copy-safe guidance.

- [ ] **Step 5: Run the focused tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected: module tests still fail until the checked-in registry exists; pure validation tests pass.

## Task 3: Add the Initial Registry

**Files:**

- Create: `docs/workflow_lisp_route_readiness_registry.json`
- Test: `tests/test_workflow_lisp_route_readiness.py`

- [ ] **Step 1: Seed a complete registry**

Create a sorted, deterministic JSON file:

```json
{
  "schema_version": "workflow_lisp_route_readiness_registry.v1",
  "updated": "2026-06-10",
  "surfaces": [
    {
      "surface_id": "workflows.examples.effectful_match_arm_normalization",
      "path": "workflows/examples/effectful_match_arm_normalization.orc",
      "surface_kind": "workflow_example",
      "route_label": "wcc_default",
      "readiness_label": "leaf_runtime_candidate",
      "lowering_route": "wcc_m4",
      "lowering_schema_version": 2,
      "copy_safety": "preferred_current_guidance",
      "evidence": [
        "tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation"
      ]
    }
  ]
}
```

Add one entry for every required path from the coverage list. The example above is a pattern, not the only row.

Classification rules for the initial seed:

- Prefer `wcc_default` only where an existing or converted test verifies default WCC/schema-2 compilation.
- Use `legacy_schema1_compat` for examples currently compiled only through explicit legacy compatibility.
- Use `migration_candidate` for Design Delta family library workflows and parity-target candidates. Use the most accurate readiness label from current evidence: leaf compile/runtime for leaves, `parent_callable_candidate` for `workflows/library/lisp_frontend_design_delta/drain.orc` as recorded in `parity_targets.json`, and do not invent `family_non_regressive` or `promotion_eligible`.
- Use `historical_negative` for characterization fixtures whose evidence is an expected unsupported-route diagnostic.
- Use `stale_needs_update` only when the surface is known not to represent current guidance; include `owner` or `replacement_or_retirement_path`.

- [ ] **Step 2: Run registry validation**

Run:

```bash
python -m pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected: checked-in registry validation passes; malformed-registry tests pass.

## Task 4: Validate Migration-Parity Target Identity

**Files:**

- Modify: `orchestrator/workflow_lisp/migration_parity.py`
- Modify or create tests in: `tests/test_workflow_lisp_route_readiness.py`
- Optional modify: `tests/test_workflow_lisp_migration_parity.py`

- [ ] **Step 1: Add validation hook**

Add a function callable after `load_parity_targets(...)`:

```python
def validate_parity_targets_against_route_readiness(
    targets: Sequence[ParityTarget],
    registry: object,
    repo_root: Path,
) -> list[Mapping[str, object]]:
    ...
```

To avoid a runtime dependency cycle, import `route_readiness` inside the function body. Return issue dictionaries using the stable route-readiness codes instead of mutating target objects.

Checks:

- every target `candidate` path has a registry entry;
- if target `readiness_label` is present, it equals the registry `readiness_label`;
- if target `lowering_route` is present, it equals the registry `lowering_route`;
- if target `lowering_schema_version` is present, it equals the registry schema;
- targets with `required_family_evidence_roles` cannot point to registry entries whose readiness is only `leaf_compile_candidate` or `leaf_runtime_candidate`;
- registry `promotion_eligible` must agree with `target.promotion_eligibility["eligible_for_primary_surface"] is True`.

- [ ] **Step 2: Add mismatch tests**

Test:

- missing registry entry for target candidate produces `route_readiness_migration_target_missing`;
- target route differs from registry route produces `route_readiness_migration_target_mismatch`;
- target readiness differs from registry readiness produces `route_readiness_migration_target_mismatch`;
- parent-family evidence roles on a leaf-only registry entry produce `route_readiness_migration_target_mismatch`;
- current checked-in `parity_targets.json` and registry agree.

- [ ] **Step 3: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_migration_parity.py -k "route_identity or readiness_label or promotable or non_regressive or route_readiness" -q
```

Expected: route/readiness target identity tests pass. Existing parity behavior remains unchanged.

## Task 5: Add the CLI Validation Command

**Files:**

- Create: `orchestrator/cli/commands/route_readiness.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Test: `tests/test_workflow_lisp_route_readiness.py`

- [ ] **Step 1: Add CLI handler**

Implement:

```python
def route_readiness_workflow(args: Namespace) -> int:
    ...
```

Behavior:

- load `Path(args.registry).resolve()`;
- validate against `Path.cwd()`;
- print one JSON object with sorted keys;
- return `0` when `overall_pass` is true;
- return `1` when validation issues exist;
- return `2` for unreadable file, malformed JSON, or top-level schema errors.

Summary fields:

- `schema_version`
- `registry_path`
- `surfaces_checked`
- `missing_required_surfaces`
- `route_schema_mismatches`
- `migration_target_mismatches`
- `overall_pass`
- `issues`

- [ ] **Step 2: Wire argparse**

In `orchestrator/cli/main.py`, add:

```python
route_readiness_parser = subparsers.add_parser(
    'workflow-lisp-route-readiness',
    help='Validate Workflow Lisp route/readiness registry'
)
route_readiness_parser.add_argument(
    '--registry',
    default='docs/workflow_lisp_route_readiness_registry.json',
    help='Path to Workflow Lisp route/readiness registry JSON'
)
route_readiness_parser.add_argument(
    '--check',
    action='store_true',
    help='Validate registry and exit nonzero on stale or invalid labels'
)
```

Dispatch it in `main()` and export it from `orchestrator/cli/commands/__init__.py`.

- [ ] **Step 3: Add CLI tests**

Use `subprocess.run` or direct handler invocation. Cover:

- valid checked-in registry returns `0` and `overall_pass=true`;
- temp registry with missing coverage returns `1`;
- malformed JSON returns `2`.

- [ ] **Step 4: Run CLI check**

Run:

```bash
python -m orchestrator workflow-lisp-route-readiness --registry docs/workflow_lisp_route_readiness_registry.json --check
```

Expected: exit `0`; JSON summary has `overall_pass: true`.

## Task 6: Add Registered Route Test Helper And Convert Representative Tests

**Files:**

- Modify: `orchestrator/workflow_lisp/route_readiness.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Optional modify: `tests/workflow_lisp_characterization.py` and `tests/test_workflow_lisp_wcc_characterization.py` if converting characterization helpers is small and low-risk.

- [ ] **Step 1: Implement helper**

Add:

```python
def compile_registered_route_case(
    registry_id: str,
    *,
    source_path: Path,
    repo_root: Path,
    default_route_check: bool = False,
    compile_func=None,
    registry_path: Path | None = None,
    **compile_kwargs,
):
    ...
```

Behavior:

- load the registry from the default path unless supplied;
- find entry by `surface_id` and verify `source_path` matches entry path;
- if `default_route_check` is false, pass the entry's `lowering_route` to `compile_func`;
- if `default_route_check` is true, assert the entry route equals `DEFAULT_LOWERING_ROUTE` and do not pass `lowering_route`;
- call `compile_func` or default to `orchestrator.workflow_lisp.compiler.compile_stage3_module`;
- assert the compile result exposes `lowering_schema_version` equal to the registry schema. If the result is a bundle wrapper, check `entry_result.lowering_schema_version` first, then `lowering_schema_version`.
- return `(compile_result, registry_entry)`.

- [ ] **Step 2: Convert representative example tests**

In `tests/test_workflow_lisp_examples.py`, remove the file-level helper that silently defaults every compile to legacy for the converted tests. For each converted test, call `compile_registered_route_case(...)`.

Start with:

- `test_effectful_match_arm_normalization_orc_compiles_with_shared_validation`
- `test_effectful_let_star_normalization_orc_compiles_with_shared_validation`
- `test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack`
- `test_same_file_record_call_binding_orc_compiles_with_shared_validation`

If a converted test must remain legacy, the registry row must say `legacy_schema1_compat`; the test should pass the registered legacy route explicitly through the helper.

- [ ] **Step 3: Preserve route-neutral artifact tests**

In `tests/test_workflow_lisp_build_artifacts.py`, add or adjust tests so helper-compiled WCC/default cases still assert:

- manifest has `lowering_schema_version == 2`;
- manifest JSON does not contain `lowering_route` or route names;
- source map JSON does not contain `lowering_route` or route names.

- [ ] **Step 4: Run converted test selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py -k "route or schema or example" -q
```

Expected: converted examples compile with their registered route, default-route tests exercise the default without overriding it, and artifact route-name leakage tests still pass.

## Task 7: Update Documentation Views

**Files:**

- Modify: `workflows/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`

- [ ] **Step 1: Update workflow index guidance**

Add a short "Workflow Lisp Route/Readiness Labels" section to `workflows/README.md`:

- registry path is `docs/workflow_lisp_route_readiness_registry.json`;
- registry labels, not filenames or recency, determine copy-safety;
- `wcc_default` is current WCC/schema-2 guidance;
- `legacy_schema1_compat` is compatibility evidence, not new authoring guidance;
- `migration_candidate` needs migration parity before promotion claims;
- `stale_needs_update` must not be cited as current evidence.

If the README has rows for `.orc` examples, add the registry label beside those rows or point to the registry as the authoritative source. Do not make README prose the route authority.

- [ ] **Step 2: Update Lisp drafting guide**

In `docs/lisp_workflow_drafting_guide.md`, add a narrow guidance paragraph:

- before copying an `.orc` example, check the registry label;
- compiler/lowering tests must pin `LoweringRoute` explicitly unless they intentionally test the default route;
- route identity and lowering schema version are evidence freshness fields;
- leaf compile/runtime labels are not promotable family evidence.

- [ ] **Step 3: Add doc assertions if practical**

Add a small test in `tests/test_workflow_lisp_route_readiness.py` that checks both docs mention the registry path. Do not assert exact wording.

## Task 8: Final Verification

**Files:**

- All modified files above.

- [ ] **Step 1: Run collect-only for touched test modules**

Run exactly:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: collection succeeds.

- [ ] **Step 2: Run focused registry tests**

Run exactly:

```bash
python -m pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected: all pass.

- [ ] **Step 3: Run migration parity route/readiness band**

Run exactly:

```bash
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "route_identity or readiness_label or promotable or non_regressive" -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run example/build route band**

Run exactly:

```bash
python -m pytest tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py -k "route or schema or example" -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run CLI registry check**

Run exactly:

```bash
python -m orchestrator workflow-lisp-route-readiness --registry docs/workflow_lisp_route_readiness_registry.json --check
```

Expected: exit `0`, JSON `overall_pass` is `true`.

- [ ] **Step 6: Run whitespace check**

Run exactly:

```bash
git diff --check
```

Expected: no output and exit `0`.

## Acceptance Checklist

- [ ] `docs/workflow_lisp_route_readiness_registry.json` exists, uses schema `workflow_lisp_route_readiness_registry.v1`, and covers every required `.orc` path listed in this plan.
- [ ] Registry validation fails closed for missing coverage, unknown labels, route/schema mismatch, stale entries without owner/replacement, and migration target mismatch.
- [ ] `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` cannot disagree with the registry for route/readiness identity when the validation hook is called.
- [ ] Representative compiler/lowering tests either compile with the registered route or intentionally verify the default route without overriding it.
- [ ] No semantic artifact gains lowering-route names; route names remain registry/evidence metadata only.
- [ ] `workflows/README.md` and `docs/lisp_workflow_drafting_guide.md` direct authors to registry labels for `.orc` copy-safety.
- [ ] The exact commands from `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json` pass with fresh output.

## Non-Goals To Recheck Before Commit

- [ ] No WCC or legacy lowering behavior changed.
- [ ] No Core AST, Semantic IR, executable IR, source-map, runtime-state, or artifact schema changed to include route names.
- [ ] No parent backlog-drain or parent-callable parity behavior changed beyond registry identity validation.
- [ ] No command adapter certification or helper script behavior changed.
- [ ] No broad repo-wide lint was introduced outside this selected registry slice.
