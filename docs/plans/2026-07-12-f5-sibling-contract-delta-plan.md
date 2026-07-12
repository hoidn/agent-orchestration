# F5 Sibling Contract Delta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the route-readiness registry and dedicated stdlib runtime-proof tests with the promoted parent-owned generic `backlog-drain` route without changing executable behavior.

**Architecture:** Add the one missing registry identity, then re-express the existing runtime-proof obligations against the selected entry workflow's structurally located inline repeat. Use one in-memory low-level-boundary source variant to prove the independent validation-profile/lint-policy matrix, and deep-copied lowered mappings to prove generated-private acceptance and authored-ref rejection. Production code, stdlib, fixtures, frozen migration surfaces, baselines, and generated artifacts remain byte-identical.

**Tech Stack:** Python 3.13, pytest, Workflow Lisp `.orc` compiler test helpers, JSON route-readiness registry, git, tmux for broad verification.

---

## Governing Contract And Execution Rules

- Approved design: `docs/plans/2026-07-12-f5-sibling-contract-delta-design.md`.
- Governing roadmap: `docs/plans/2026-07-07-drain-migration-g8-retirement.md`, Phase 1 Task 1.6a.
- Execute from `/home/ollie/Documents/agent-orchestration` with no worktree.
- Use `superpowers:test-driven-development` for each behavior change and `superpowers:subagent-driven-development` for task execution and two-stage review.
- Run `pytest --collect-only` after changing the test module. Run broad pytest as `pytest -q -n 16 --dist=worksteal` in tmux.
- Stage only explicit paths. Never use `git add -A`, `git add -u`, or `git commit -a`.
- Preserve the user's unrelated dirty paths; capture `git status --short` before and after each task.
- Stop after the same verification failure occurs twice. Do not weaken a proof or expand implementation scope to make it green.

### Exact implementation scope

Until Task 3's closure-document step, implementation may modify exactly these two files:

- `docs/workflow_lisp_route_readiness_registry.json`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`

No file under `orchestrator/`, `workflows/`, or `tests/fixtures/` may change. Do not modify `tests/test_workflow_lisp_route_readiness.py`, parity targets/reports, checkpoint baselines, family manifests, generated evidence, or capability/design docs. If the two-file boundary is insufficient, stop and return to design review.

### File responsibility map

| File | Current region | Planned responsibility |
| --- | --- | --- |
| `docs/workflow_lisp_route_readiness_registry.json` | fixture rows near current lines 147–360 | Add one sorted, path-derived row for `design_delta_loop_promoted_hook_phase_ctx.orc`; update only the ordinary document date if the registry carries one. |
| `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py` | imports/helpers around current lines 1–81; runtime-proof cases around 84–285 | Select the parent-owned inline loop structurally; create an in-memory boundary-negative fixture; assert the four-case validation/lint matrix, metadata/source lineage, generated nested acceptance, and authored-whitelist rejection. |
| `docs/plans/2026-07-07-drain-migration-g8-retirement.md` | Phase 1 Tasks 1.6a/1.7 and Phase 1 Ledger | Closure documentation only after every implementation and verification gate passes. |

## Pre-Implementation Broad Baseline

**Files:**

- Create ignored/local evidence only: `tmp/f5-prechange-broad-baseline.txt`
- Do not modify tracked files

- [ ] **Step 1: Capture the fresh broad failure identities before Task 1 edits**

Use the `tmux` skill before launching. From the repository root, start a dedicated session:

```bash
tmux new-session -d -s f5-prechange-baseline \
  "bash -lc 'set -o pipefail; pytest -q -n 16 --dist=worksteal 2>&1 | tee tmp/f5-prechange-broad-baseline.txt; rc=\${PIPESTATUS[0]}; printf \"%s\\n\" \"\$rc\" > tmp/f5-prechange-exit-code.txt; printf \"\\nEXIT_CODE=%s\\n\" \"\$rc\" | tee -a tmp/f5-prechange-broad-baseline.txt; exit \"\$rc\"'"
```

Monitor through tmux until the command exits; do not run a blocking foreground wait. Record
the exit code, totals, and every categorized pytest summary identity whose line begins
`FAILED ` or `ERROR ` and whose payload begins with `tests/`. Application logging lines such
as `ERROR    orchestrator.workflow.executor...` are not pytest identities and must be
excluded. Materialize the identity set deterministically, preserving the category so a
failure-to-error transition is visible and accepting multiple spaces after the category:

```bash
rg '^(FAILED|ERROR) +tests/[^ ]+' tmp/f5-prechange-broad-baseline.txt \
  | sed -E 's/^(FAILED|ERROR) +(tests\/[^ ]+).*/\1 \2/' \
  | sort -u > tmp/f5-prechange-failure-identities.txt
printf '%s\n' \
  'FAILED tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates' \
  'FAILED tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry' \
  'FAILED tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_shared_callable_profile_keeps_generated_structured_branch_guard_active' \
  'FAILED tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage' \
  'FAILED tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_accepts_generated_nested_structured_steps_on_child_callable_route' \
  'FAILED tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_rejects_authored_parent_scope_fallback_refs_even_when_metadata_lists_them' \
  | sort -u > tmp/f5-expected-resolved-identities.txt
```

The expected-resolved file is an explicit contract: it contains the two route-readiness and
four stale child-callable runtime-proof failures that F5 is intended to remove. `FAILED` is
part of each identity. A category change to `ERROR` is not interchangeable.

Require fail-closed baseline evidence, verify all six expected removals are actually present,
and derive the only acceptable post-change failure set:

```bash
pre_rc=$(cat tmp/f5-prechange-exit-code.txt)
case "$pre_rc" in 0|1) ;; *) echo "abnormal prechange pytest exit: $pre_rc"; exit 1 ;; esac
rg -q '[0-9]+ (passed|failed|error|errors)(,| in )' \
  tmp/f5-prechange-broad-baseline.txt
if [ "$pre_rc" -ne 1 ]; then
  echo "prechange run must contain the six expected F5 failures"
  exit 1
fi
if [ ! -s tmp/f5-prechange-failure-identities.txt ]; then
  echo "red prechange run has no categorized pytest identities"
  exit 1
fi
if rg -v '^(FAILED|ERROR) tests/[^ ]+$' \
  tmp/f5-prechange-failure-identities.txt; then
  echo "prechange identity extraction contains a non-pytest row"
  exit 1
fi
if [ -n "$(comm -23 \
  tmp/f5-expected-resolved-identities.txt \
  tmp/f5-prechange-failure-identities.txt)" ]; then
  echo "fresh baseline is missing an expected F5 failure identity"
  comm -23 \
    tmp/f5-expected-resolved-identities.txt \
    tmp/f5-prechange-failure-identities.txt
  exit 1
fi
comm -23 \
  tmp/f5-prechange-failure-identities.txt \
  tmp/f5-expected-resolved-identities.txt \
  > tmp/f5-expected-postchange-failure-identities.txt
```

Expected: normal pytest test-failure exit `1`, a normal completion summary, all six exact F5
identities present, and `tmp/f5-expected-postchange-failure-identities.txt` equal to the
fresh baseline minus exactly those six rows. Exit `0`, `2` (interrupt), `3` (internal error),
`4` (usage), `5` (no tests), missing status, missing summary, crash, or OOM is not an
acceptable baseline. These ignored/local files are evidence, not implementation scope, and
must not be staged.

## Task 1: Register The Promoted-Hook Fixture

**Files:**

- Modify: `docs/workflow_lisp_route_readiness_registry.json:147-360` (sorted `tests/fixtures/workflow_lisp/valid` rows)
- Verify only: `tests/test_workflow_lisp_route_readiness.py:112-268`
- Verify only: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` at `test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs`

- [ ] **Step 1: Capture the baseline by full test identity**

Run:

```bash
git status --short
pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected before the registry edit: exactly the known missing-surface failures identify
`tests/fixtures/workflow_lisp/valid/design_delta_loop_promoted_hook_phase_ctx.orc` and/or
`route_readiness_surface_missing`; record full failing node IDs, not only a failure count.
Any different failure is triage input, not permission to change another file.

- [ ] **Step 2: Make the registry requirement explicitly RED**

Run the narrow checked-in registry and CLI cases:

```bash
pytest \
  tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates \
  tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry \
  -q
```

Expected: FAIL because discovery contains the promoted-hook fixture and the registry omits it. If both unexpectedly pass, run the full module from Step 1 and locate the exact existing RED before editing; do not add a redundant row.

- [ ] **Step 3: Add the exact registry row**

Insert the row in path/surface-id sort order alongside adjacent Design Delta fixture rows. Use this exact data:

```json
{
  "copy_safety": "test_evidence_only",
  "evidence": [
    "tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs"
  ],
  "lowering_route": "wcc_m4",
  "lowering_schema_version": 2,
  "path": "tests/fixtures/workflow_lisp/valid/design_delta_loop_promoted_hook_phase_ctx.orc",
  "readiness_label": "leaf_compile_candidate",
  "route_label": "wcc_default",
  "surface_id": "tests.fixtures.workflow_lisp.valid.design_delta_loop_promoted_hook_phase_ctx",
  "surface_kind": "test_fixture"
}
```

Do not cite registry self-validation as evidence and do not change labels, schema, discovery, or the fixture.

- [ ] **Step 4: Validate JSON and turn both route-readiness cases GREEN**

Run:

```bash
python -m json.tool docs/workflow_lisp_route_readiness_registry.json >/dev/null
pytest \
  tests/test_workflow_lisp_route_readiness.py::test_checked_in_registry_loads_and_validates \
  tests/test_workflow_lisp_route_readiness.py::test_cli_route_readiness_check_valid_registry \
  -q
python -m orchestrator workflow-lisp-route-readiness \
  --registry docs/workflow_lisp_route_readiness_registry.json \
  --check
```

Expected: JSON parsing succeeds; both tests pass; CLI exits 0 with no missing required surface. Confirm the fixture path and `surface_id` each occur exactly once:

```bash
rg -c 'design_delta_loop_promoted_hook_phase_ctx' docs/workflow_lisp_route_readiness_registry.json
```

Expected: `3` textual occurrences (evidence test, path, and `surface_id`), all within one row.

- [ ] **Step 5: Run the independent proving evidence and full registry module**

Run:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs -q
pytest tests/test_workflow_lisp_route_readiness.py -q
```

Expected: PASS. The cited feasibility test—not the registry test—compiles the real linked route and proves the promoted hook's phase-context bridge inputs.

- [ ] **Step 6: Audit scope and capture evidence**

Run:

```bash
git diff --check -- docs/workflow_lisp_route_readiness_registry.json
git diff --name-only
git status --short
```

Expected attributable diff: only `docs/workflow_lisp_route_readiness_registry.json`; the pre-existing user-owned dirty paths remain unchanged.

- [ ] **Step 7: Commit the registry cycle**

```bash
git add docs/workflow_lisp_route_readiness_registry.json
git diff --cached --check
git diff --cached --name-only
git commit -m "Register promoted drain hook route"
```

Expected staged path: exactly the registry file. Record the commit SHA and fresh test outputs.

## Task 2: Re-Express Runtime Proofs On The Parent-Owned Generic Route

**Files:**

- Modify: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py:1-285`
- Do not modify: `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_stdlib.orc`
- Do not modify: any file under `orchestrator/`

### Required helper shape

Use stable `ENTRY_WORKFLOW_NAME` only. Never select `std/drain::backlog-drain`, a digest-bearing specialization name, or a fixed step index. The implementation may adapt names, but it must preserve this behavior:

```python
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT


def _walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_nodes(child)


_DRAIN_REPEAT_OUTPUTS = {
    "status",
    "state__items-processed",
    "state__progress-report-path",
    "result__variant",
    "result__items_processed",
    "result__progress_report_path",
    "result__blocker_class",
}


def _inline_repeat_candidates(authored_mapping):
    candidates = []
    for node in _walk_nodes(authored_mapping):
        repeat = node.get("repeat_until")
        if not isinstance(repeat, dict) or not isinstance(repeat.get("steps"), list):
            continue
        outputs = repeat.get("outputs")
        exhausted = repeat.get("on_exhausted", {}).get("outputs", {})
        if (
            isinstance(outputs, dict)
            and _DRAIN_REPEAT_OUTPUTS <= set(outputs)
            and exhausted.get("status") == "DONE"
            and exhausted.get("result__variant") == "EXHAUSTED"
        ):
            candidates.append((node, repeat))
    return candidates


def _selected_inline_repeat(authored_mapping):
    candidates = _inline_repeat_candidates(authored_mapping)
    assert len(candidates) == 1, (
        f"expected one parent-owned inline drain repeat, found {len(candidates)}"
    )
    return candidates[0]
```

The required output vocabulary and exhausted terminal are the stable drain-loop shape; the
metadata test below separately joins selected owners to source/procedure provenance. Tests
must not match by a generated digest or silently choose `steps[N]`. Callers receive both the
outer step node and repeat mapping so mutations can preserve the actual selected owner.

Provide a deep-copy mutation helper so both validator probes mutate only test-local mappings:

```python
def _replace_entry_workflow(result, replacement):
    return tuple(
        replacement
        if item.typed_workflow.definition.name == ENTRY_WORKFLOW_NAME
        else item
        for item in result.entry_result.lowered_workflows
    )
```

Provide this in-memory source-variant helper. It reads `DRAIN_STDLIB_FIXTURE`, inserts
exactly one otherwise-unused `(state-root Path.state-root)` parameter in the entry workflow
parameter list, writes only under `tmp_path`, and calls the existing linked compiler helper.
Do not add a checked-in fixture.

```python
_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))"""
_LOW_LEVEL_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (state-root Path.state-root)
     (max-iterations Int))"""


def _compile_low_level_boundary_variant(*, tmp_path: Path, **compile_kwargs: object):
    source = DRAIN_STDLIB_FIXTURE.read_text(encoding="utf-8")
    assert source.count(_ENTRY_PARAMS) == 1
    variant_source = source.replace(_ENTRY_PARAMS, _LOW_LEVEL_ENTRY_PARAMS, 1)
    variant_path = tmp_path / "low_level_boundary_variant.orc"
    variant_path.write_text(variant_source, encoding="utf-8")
    return _compile_linked_fixture(
        variant_path,
        tmp_path=tmp_path,
        **compile_kwargs,
    )
```

Use this owner-resolution helper for metadata checks. It derives names from the real
authored mapping and joins their concrete ids to origin-map entries; it does not parse
generated-name text. Return the node as well as its origin because compiler-generated
projection-anchor assertion nodes currently retain a `defworkflow` form path while their
source span still points into the imported `std/drain.orc` procedure body.

```python
def _source_mapped_owner_records(lowered):
    records = {}
    for node in _walk_nodes(lowered.authored_mapping):
        name = node.get("name")
        step_id = node.get("id")
        if not isinstance(name, str) or not isinstance(step_id, str):
            continue
        origin = lowered.origin_map.step_spans.get(step_id)
        if origin is not None:
            records[name] = (node, origin)
    return records


def _assert_generated_stdlib_owner(node, origin) -> None:
    assert Path(origin.span.start.path).as_posix().endswith(
        "orchestrator/workflow_lisp/stdlib_modules/std/drain.orc"
    )
    assert (
        origin.form_path[-2:] == ("defproc", "backlog-drain-proc")
        or (
            "assert" in node
            and origin.form_path[-2:] == ("defworkflow", "drain")
        )
    )
```

- [ ] **Step 1: Capture the runtime-proof baseline by full identity**

Run:

```bash
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
```

Expected before editing: the four known stale child-callable cases fail by full node ID while the already-generic cases remain green. Record actual identities; the historical count is not an oracle.

- [ ] **Step 2: Write RED structural-selector and normal-route assertions**

First change tests so the shared/default and dedicated/default normal fixture expect the parent-owned route:

```python
lowered = _selected_lowered_workflow(result)
repeat_owner, inline_repeat = _selected_inline_repeat(lowered.authored_mapping)
assert inline_repeat["steps"]
assert not any(
    step.get("call") == "std/drain::backlog-drain"
    for step in lowered.authored_mapping["steps"]
)
```

For the unmodified promoted fixture, assert:

```python
assert result.entry_result.retained_non_promotable_diagnostics == ()
```

Add
`test_parent_owned_inline_route_selector_fails_closed_on_ambiguous_shape`. Deep-copy the
real authored mapping, append a deep copy of the selected repeat owner to top-level `steps`,
and require `_selected_inline_repeat` to raise `AssertionError` matching
`found 2`. Also require an empty mapping to raise with `found 0`.

Run:

```bash
pytest \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_shared_callable_profile_keeps_generated_structured_branch_guard_active \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_parent_owned_inline_route_selector_fails_closed_on_ambiguous_shape \
  -q
```

Expected RED before the helper replacement: the first two fail on stale child-call/diagnostic
assumptions and the new selector case fails because `_selected_inline_repeat` is absent or
does not reject zero/two candidates. After implementing the complete helpers above, rerun
the exact command and expect all three PASS.

- [ ] **Step 3: Implement the minimal structural selector and source-lineage assertions**

Delete `_selected_child_lowered_workflow`. Add the bounded recursive walker and fail-closed unique inline-repeat selector. Retarget source-lineage assertions behaviorally:

- compiler intrinsic count remains zero;
- `ENTRY_WORKFLOW_NAME` owns a non-empty inline repeat and post-loop terminal work;
- no top-level step calls `std/drain::backlog-drain`;
- `origin_map.step_spans` covers the selected loop/terminal semantic owners;
- `origin_map.generated_path_spans` carries generated write-root/terminal paths without asserting full digest-bearing IDs;
- normal-fixture retained diagnostics are empty.

Run the exact three-node command from Step 2. Expected: PASS.

- [ ] **Step 4: Write the RED four-case validation/lint policy matrix**

Add these four explicit tests using the same in-memory low-level-boundary variant:

- `test_dedicated_runtime_proof_default_lint_retains_low_level_boundary_variant`
- `test_shared_callable_default_lint_retains_low_level_boundary_variant`
- `test_shared_callable_strict_lint_rejects_low_level_boundary_variant`
- `test_dedicated_runtime_proof_strict_lint_rejects_low_level_boundary_variant`

| Validation input | Lint input | Expected |
| --- | --- | --- |
| `validation_profile="DEDICATED_RUNTIME_PROOF"` | default | compile succeeds, executable entry bundle exists, finding retained |
| `validate_shared=True` (`SHARED_CALLABLE`) | default | compile succeeds, finding retained |
| `validate_shared=True` | `LINT_PROFILE_STRICT` | `LispFrontendCompileError` with the finding |
| `validation_profile="DEDICATED_RUNTIME_PROOF"` | `LINT_PROFILE_STRICT` | `LispFrontendCompileError` with the finding |

Use a small assertion helper for the retained finding:

```python
def _assert_low_level_boundary_diagnostic(diagnostic) -> None:
    assert diagnostic.code == "low_level_state_path_in_high_level_module"
    assert diagnostic.validation_pass == "contract"
    assert diagnostic.authority_layer == "frontend"
    assert diagnostic.form_path
    assert diagnostic.span is not None
```

`LispFrontendDiagnostic` currently owns these exact fields. Do not assert literal human
message wording. Use this exact successful-case shape:

```python
result = _compile_low_level_boundary_variant(
    tmp_path=tmp_path,
    validation_profile="DEDICATED_RUNTIME_PROOF",  # shared/default uses validate_shared=True
)
findings = [
    item
    for item in result.entry_result.retained_non_promotable_diagnostics
    if item.code == "low_level_state_path_in_high_level_module"
]
assert len(findings) == 1
_assert_low_level_boundary_diagnostic(findings[0])
```

Use this strict-case shape, changing only the validation input for the dedicated case:

```python
with pytest.raises(LispFrontendCompileError) as excinfo:
    _compile_low_level_boundary_variant(
        tmp_path=tmp_path,
        validate_shared=True,
        lint_profile=LINT_PROFILE_STRICT,
    )
findings = [
    item
    for item in excinfo.value.diagnostics
    if item.code == "low_level_state_path_in_high_level_module"
]
assert len(findings) == 1
_assert_low_level_boundary_diagnostic(findings[0])
```

Create the four test bodies calling `_compile_low_level_boundary_variant` before defining
that helper, then run:

```bash
pytest \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_dedicated_runtime_proof_default_lint_retains_low_level_boundary_variant \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_shared_callable_default_lint_retains_low_level_boundary_variant \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_shared_callable_strict_lint_rejects_low_level_boundary_variant \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_dedicated_runtime_proof_strict_lint_rejects_low_level_boundary_variant \
  -q
```

Expected RED: all four fail with `NameError: name '_compile_low_level_boundary_variant' is
not defined`. A compiler-policy failure at this point is not the intended RED; finish the
test helper before interpreting policy behavior.

- [ ] **Step 5: Make the four-case matrix GREEN**

Implement the temporary source variant exactly as shown above and invoke it with the policy
inputs in the table. For successful dedicated/default, additionally call
`validate_executable_workflow` on `validated_bundles[ENTRY_WORKFLOW_NAME].ir`. For both
successful default-lint cases, locate exactly one relevant retained finding and assert all
structured provenance. For both strict cases, assert the same code and provenance in
`excinfo.value.diagnostics`.

Run the exact four-node command from Step 4. Expected: all PASS. This is lint-policy
evidence; do not claim `SHARED_CALLABLE` with default lint rejects.

- [ ] **Step 6: Write RED tests for compiler-owned metadata and source ownership**

Add
`test_runtime_proof_metadata_resolves_to_source_mapped_generated_owners`. On a normal
dedicated-profile result, call the not-yet-defined
`_source_mapped_owner_records(lowered)` and assert these collections are non-empty:

```python
assert lowered.runtime_proof_nested_structured_step_names
assert lowered.runtime_proof_shared_validation_parent_ref_allowances
assert lowered.runtime_proof_executable_parent_ref_allowances
```

Then require every nested-step name and every owner from both allowance collections to be
present in the records and pass `_assert_generated_stdlib_owner(*records[owner])`. This
accepts the current compiler-generated projection-anchor lineage only when the node is
actually an assertion node, its form path is the parent `defworkflow`, and its source span
still points to the imported stdlib body. Assertions must join metadata to
`origin_map`/generated provenance, not merely check strings are non-empty.

Run:

```bash
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_metadata_resolves_to_source_mapped_generated_owners -q
```

Expected RED: `NameError: name '_source_mapped_owner_records' is not defined`.

- [ ] **Step 7: Make metadata/source ownership GREEN**

Add `_source_mapped_owner_records` and `_assert_generated_stdlib_owner` exactly as shown in
Required helper shape. For each nested-step name and each `(owner, ref)` allowance owner,
look up the record and call the assertion helper. Keep refs opaque except where the negative
probe fabricates one.

Run:

```bash
pytest \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_metadata_resolves_to_source_mapped_generated_owners \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_dedicated_runtime_proof_profile_builds_validated_entry_bundle_for_imported_stdlib_drain \
  -q
```

Expected: both PASS.

- [ ] **Step 8: Write RED generated-nested mutation against the real inline loop**

Retarget `test_runtime_proof_profile_accepts_generated_nested_structured_steps_on_child_callable_route` (rename it to say `parent_owned_inline_route`) so it:

1. compiles the normal fixture;
2. selects `ENTRY_WORKFLOW_NAME`;
3. deep-copies `authored_mapping`;
4. structurally locates the unique repeat body;
5. copies an existing structured `if`/branch node found by shape, gives it a unique test-local name/id, and appends it to that body;
6. adds that exact generated owner name to `runtime_proof_nested_structured_step_names`; and
7. calls `validate_lowered_workflows` over `_replace_entry_workflow(...)` with `Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF`.

Rename the test first but leave its old child selector/body in place, then run:

```bash
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_accepts_generated_nested_structured_steps_on_parent_owned_inline_route -q
```

Expected RED: `StopIteration` from `_selected_child_lowered_workflow` because the generic
route has no `std/drain::backlog-drain` child.

- [ ] **Step 9: Make the generated-nested mutation GREEN**

Use this adaptable implementation shape; it relies only on structured-node keys and never a
list position:

```python
authored = deepcopy(lowered.authored_mapping)
_, repeat = _selected_inline_repeat(authored)
structured = [step for step in repeat["steps"] if "if" in step and "when" not in step]
assert len(structured) == 1
nested = deepcopy(structured[0])
nested["name"] = f"{ENTRY_WORKFLOW_NAME}__runtime_proof_scope_guard"
nested["id"] = "runtime_proof_scope_guard"
repeat["steps"].append(nested)
mutated = replace(
    lowered,
    authored_mapping=authored,
    runtime_proof_nested_structured_step_names=(
        *lowered.runtime_proof_nested_structured_step_names,
        nested["name"],
    ),
)
validate_lowered_workflows(
    _replace_entry_workflow(result, mutated),
    workspace_root=tmp_path,
    imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
    validation_profile=Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF,
)
```

If the current generic route has more than one unguarded `if`, refine the predicate by its
branch output keys and document that stable shape; do not choose the first match. Run the
exact single-node command from Step 8. Expected: PASS with
`validate_lowered_workflows` returning without error.

- [ ] **Step 10: Write RED authored-whitelist negative on the inline loop**

Retarget `test_runtime_proof_profile_rejects_authored_parent_scope_fallback_refs_even_when_metadata_lists_them` to the selected parent. Append a fabricated authored materialization step to a deep-copied inline repeat body. Add its `(owner, ref)` pair to both runtime-proof allowance tuples, then validate with the dedicated profile.

The test must expect `LispFrontendCompileError` with stable code
`workflow_boundary_type_invalid` and associate the diagnostic structurally with the
fabricated owner/form path; it must not assert exact message prose. Run:

```bash
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_runtime_proof_profile_rejects_authored_parent_scope_fallback_refs_even_when_metadata_lists_them -q
```

Expected RED before retargeting: `StopIteration` from the removed child selector.

- [ ] **Step 11: Make the authored-whitelist negative GREEN**

Build the fabricated ref from the selected repeat owner's `name`, then deliberately target
the nonexistent historical fallback child beneath that owner. The `__current_loop_state`
step and `acc__items-processed` artifact are intentionally absent from the parent-owned
generic route; deriving the prefix from the selected owner avoids pinning a digest while
preserving the boundary-negative shape:

```python
authored_ref = (
    f"parent.steps.{repeat_owner['name']}__current_loop_state."
    "artifacts.acc__items-processed"
)
```

Append this complete shape to the selected repeat body:

```python
authored_owner = f"{ENTRY_WORKFLOW_NAME}__runtime_proof_parent_scope_guard"
repeat["steps"].append(
    {
        "name": authored_owner,
        "id": "runtime_proof_parent_scope_guard",
        "materialize_artifacts": {
            "values": [{
                "name": "copied_items_processed",
                "source": {"ref": authored_ref},
                "contract": {"kind": "scalar", "type": "integer"},
            }]
        },
    }
)
```

Add `(authored_owner, authored_ref)` to both allowance collections with `replace`, then call
`validate_lowered_workflows(_replace_entry_workflow(result, mutated), ...)`. Expected:
validation rejects with `workflow_boundary_type_invalid` even though both collections list
the pair. Assert exactly one matching diagnostic with:

```python
matching = [
    item
    for item in excinfo.value.diagnostics
    if item.code == "workflow_boundary_type_invalid"
    and item.validation_pass == "shared_validation"
    and item.authority_layer == "shared_validation"
    and item.form_path[-2:] == ("defproc", "backlog-drain-proc")
    and Path(item.span.start.path).as_posix().endswith(
        "orchestrator/workflow_lisp/stdlib_modules/std/drain.orc"
    )
]
assert len(matching) == 1
```

This proves stable code and source/form provenance without asserting message prose. Run the
exact single-node command from Step 10 and expect PASS.

- [ ] **Step 12: Preserve the normal fixture and remaining existing obligations**

Confirm these existing tests remain explicit and green:

- dedicated profile builds and validates the executable entry bundle;
- intrinsic `backlog-drain` lowering count is zero;
- frontend-only profile has no validated bundle;
- certified placeholder command-boundary coverage remains bounded by `EXPECTED_PLACEHOLDER_BOUNDARIES`;
- serialized validation-profile values are accepted.

Do not delete a test merely because its old child identity is obsolete.

- [ ] **Step 13: Collect and run the full runtime-proof module**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
pytest tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
```

Expected: collection succeeds; every case passes. Record total collected/passed and full identities of any failure. A failure requiring production, fixture, or frozen-surface edits triggers Stop/Revise.

- [ ] **Step 14: Run focused adjacent canaries**

Run:

```bash
pytest tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_loop_promoted_hook_carries_phase_ctx_bridge_inputs -q
```

Expected: PASS.

- [ ] **Step 15: Audit prohibited paths and commit**

Run:

```bash
git diff --check -- tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py
git diff --name-only HEAD~1
git status --short
```

Expected attributable uncommitted diff: only the runtime-proof module. Then:

```bash
git add tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py
git diff --cached --check
git diff --cached --name-only
git commit -m "Align stdlib runtime proofs with generic drain route"
```

Record the SHA and all Task-2 evidence.

## Task 3: Integration Gates, Scope Audit, Ledger Closure, And Reviews

**Files:**

- Verify: the two implementation files from Tasks 1–2
- Modify only after all gates pass: `docs/plans/2026-07-07-drain-migration-g8-retirement.md` in the Task 1.6a entry and Phase 1 Ledger
- Review: approved design, this plan, and the pinned implementation commits

- [ ] **Step 1: Run both directly affected modules together**

```bash
pytest tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
```

Expected: PASS, no deselection.

- [ ] **Step 2: Run the required four-suite drain integration gate**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_parent_drain_census_alignment.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: PASS at the Task-1.6 closure baseline, with no deselection and no new failure identity.

- [ ] **Step 3: Run checkpoint-identity and composition/procedure canaries**

```bash
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py \
  tests/test_workflow_lisp_procedures.py -q
```

Expected: identity `3 passed`; composition plus procedures `151 passed` unless the current checked-in suite count has legitimately changed. In all cases require zero failure and record the fresh counts; do not regenerate checkpoint baselines.

- [ ] **Step 4: Run broad pytest in tmux**

Use the `tmux` skill. From the repository root, launch a distinct post-change session and
capture output:

```bash
tmux new-session -d -s f5-postchange-verification \
  "bash -lc 'set -o pipefail; pytest -q -n 16 --dist=worksteal 2>&1 | tee tmp/f5-postchange-broad-verification.txt; rc=\${PIPESTATUS[0]}; printf \"%s\\n\" \"\$rc\" > tmp/f5-postchange-exit-code.txt; printf \"\\nEXIT_CODE=%s\\n\" \"\$rc\" | tee -a tmp/f5-postchange-broad-verification.txt; exit \"\$rc\"'"
```

After the session exits, compare full identities mechanically:

```bash
rg '^(FAILED|ERROR) +tests/[^ ]+' tmp/f5-postchange-broad-verification.txt \
  | sed -E 's/^(FAILED|ERROR) +(tests\/[^ ]+).*/\1 \2/' \
  | sort -u > tmp/f5-postchange-failure-identities.txt
if rg -v '^(FAILED|ERROR) tests/[^ ]+$' \
  tmp/f5-postchange-failure-identities.txt; then
  echo "postchange identity extraction contains a non-pytest row"
  exit 1
fi
pre_rc=$(cat tmp/f5-prechange-exit-code.txt)
post_rc=$(cat tmp/f5-postchange-exit-code.txt)
case "$pre_rc" in 0|1) ;; *) echo "abnormal prechange pytest exit: $pre_rc"; exit 1 ;; esac
case "$post_rc" in 0|1) ;; *) echo "abnormal postchange pytest exit: $post_rc"; exit 1 ;; esac
rg -q '[0-9]+ (passed|failed|error|errors)(,| in )' \
  tmp/f5-postchange-broad-verification.txt
if [ -s tmp/f5-expected-postchange-failure-identities.txt ]; then
  expected_post_rc=1
else
  expected_post_rc=0
fi
if [ "$post_rc" -ne "$expected_post_rc" ]; then
  echo "postchange pytest exit does not match expected remaining failure set"
  exit 1
fi
if ! cmp -s \
  tmp/f5-expected-postchange-failure-identities.txt \
  tmp/f5-postchange-failure-identities.txt; then
  echo "postchange FAILED/ERROR identities do not equal baseline minus the six F5 failures"
  diff -u \
    tmp/f5-expected-postchange-failure-identities.txt \
    tmp/f5-postchange-failure-identities.txt
  exit 1
fi
```

Expected: both runs have normal pytest summaries. The post-change categorized set must equal
the pre-change set minus exactly the six named F5 failures—no additions, unrelated removals,
or `FAILED`/`ERROR` category changes. Every compared row must match
`^(FAILED|ERROR) tests/`; application `ERROR` logs never enter either set. Post-change exit
must be `0` iff that expected set is empty, otherwise `1`. The generated-nested test is
renamed during Task 2; its old failing node id is still one of the six expected removals,
while its new passing node id does not enter any failure set. Any abnormal/no-summary
termination, truncated output, missing exit file, crash, interrupt, signal, OOM, identity
diff, or unexpected unrelated fix leaves the broad gate red until fixed or the design is
revised. Never weaken or silently accept it. Save both tmux commands, exit codes, totals,
and identity files in the evidence record. Do not stage the ignored/local `tmp/` files.

- [ ] **Step 5: Audit the pinned implementation range for prohibited diffs**

Let `<task1-parent>` be the parent of the Task-1 registry commit and
`<implementation-tip>` be the current Task-2 implementation SHA. Record both values before
any review or documentation commit. Run:

```bash
git diff --name-only <task1-parent>..<implementation-tip>
git diff --check <task1-parent>..<implementation-tip>
git diff <task1-parent>..<implementation-tip> -- orchestrator workflows tests/fixtures \
  tests/test_workflow_lisp_route_readiness.py \
  workflows/examples/inputs/workflow_lisp_migrations \
  artifacts
```

Expected first output: exactly
`docs/workflow_lisp_route_readiness_registry.json` and
`tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`.
Expected prohibited diff command: empty.

Also audit for brittle identities:

```bash
rg -n 'std/drain::backlog-drain|\["steps"\]\[[0-9]+\]|[0-9a-f]{8,}' \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py
```

Expected: no child-workflow selector, fixed list index, or digest-pinned assertion. A literal child name is allowed only in the negative assertion that no top-level child call exists; explain each surviving hit. If a review fix adds an implementation commit, update only `<implementation-tip>` to that SHA and rerun Steps 1–5; this audit never includes a documentation commit.

- [ ] **Step 6: Request specification-compliance review**

Dispatch a fresh reviewer with only:

- approved design path;
- this implementation plan path;
- pinned implementation range `<task1-parent>..<implementation-tip>`;
- test evidence from Steps 1–4;
- explicit two-file implementation boundary.

Reviewer must check every preserved proof obligation, exact registry identity, four-case
policy matrix, independent diagnostic provenance, structural selection, and no
production/frozen diff. If issues are found, return to the owning task, fix with TDD, rerun
Steps 1–5 with the new implementation tip, and re-request full spec review. Do not edit or
check off the roadmap while review is pending.

- [ ] **Step 7: Request code-quality review**

After specification review passes, dispatch a fresh quality reviewer over the same pinned
implementation range. Require review for brittle generated names, fixed indexes, weak
candidate selection, shared mutable state, message-text assertions, metadata treated as
authority, and scope leakage. If issues are found, fix with TDD, rerun Steps 1–5, then rerun
spec review before requesting quality review again. Continue until both reviews approve the
same final `<implementation-tip>`.

- [ ] **Step 8: Close Task 1.6a in the governing ledger after gates and both reviews pass**

Update `docs/plans/2026-07-07-drain-migration-g8-retirement.md`:

- change Task 1.6a's checkbox/status from pending to complete;
- record both implementation SHAs;
- record route-readiness, cited feasibility, runtime-proof collection/module, two-module, four-suite, identity, composition/procedure, and broad-worksteal results;
- state that the implementation range changed exactly the two permitted files;
- state that production, stdlib, fixtures, frozen migration surfaces, parity/checkpoint baselines, and generated evidence remained unchanged;
- state that the normal fixture is boundary-clean while the in-memory variant retains under default lint and rejects under strict lint for both shared and dedicated validation profiles;
- record specification and quality review approval against the final pinned implementation range;
- do not make Task 1.7 or Gate P2 completion claims.

Run:

```bash
git diff --check -- docs/plans/2026-07-07-drain-migration-g8-retirement.md
git add docs/plans/2026-07-07-drain-migration-g8-retirement.md
git diff --cached --name-only
git commit -m "Record F5 sibling contract evidence"
```

Expected staged path: only the governing roadmap.

- [ ] **Step 9: Record review results without overstating roadmap status**

Verify the closure commit contains the final implementation SHAs, fresh evidence, and both
review approvals. Task 1.7 remains next and must reconcile the G5E current-evidence note;
Gate P2 remains blocked until Task 1.7 and every listed P2 condition are freshly recorded.

## Machine-Readable Routing Audit

This roadmap is sequenced directly by prose tasks and the Gate Ledger in
`docs/plans/2026-07-07-drain-migration-g8-retirement.md`. Repository search found no
machine-readable manifest, selector input, active workflow queue, or generated routing file
that enumerates its Phase 1 task numbers. The JSON manifests under `state/` belong to
historical or separate workflow drains and do not reference this roadmap; modifying them
would rewrite provenance rather than update live routing. Therefore this sequencing change
has no machine-readable companion edit.

`docs/index.md` already links the governing drain plan from the durable Procedure-First
Roadmap section. The new F5 design and implementation plan are linked from the governing
Task 1.6a, so an additional index entry would duplicate component-level routing and is not
required.

## Stop / Revise Conditions

Stop and return to design review if any of these occurs:

- any implementation file beyond the exact two-file scope is needed;
- the parent-owned loop cannot be selected structurally without a digest or fixed index;
- dedicated validation cannot produce an executable entry bundle;
- the default-lint boundary variant loses the structured finding;
- either strict-lint case accepts the boundary variant;
- the authored-ref mutation becomes valid through allowance metadata;
- the generated nested mutation cannot validate on the real parent route; or
- broad verification finds a new attributable failure identity.
