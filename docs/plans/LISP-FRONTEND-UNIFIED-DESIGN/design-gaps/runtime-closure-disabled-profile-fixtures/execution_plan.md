# Runtime Closure Disabled-Profile Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded fixture-only runtime-closure rejection coverage so deferred closure shapes produce stable diagnostics while ordinary Workflow Lisp compilation still emits no runtime-closure payloads, registries, or invocation markers.

**Architecture:** Keep runtime closures disabled in the real compiler/runtime path. Add a small test-only fixture loader and validator that models rejected closure shapes as data, returns deterministic `LispFrontendDiagnostic` objects, and never lowers or executes closure values. Extend existing diagnostic and artifact regressions so current `ProcRef` / `WorkflowRef` transport guards stay authoritative for ordinary Stage 3 compilation, while new closure-specific cases are covered through the fixture harness.

**Tech Stack:** Python 3, Workflow Lisp frontend diagnostics/helpers, `pytest`, YAML fixture loading already used in the repo, existing frontend bundle build helpers, and one public `python -m orchestrator compile ...` smoke check.

---

## Scope And Non-Negotiable Guardrails

- This plan implements only the selected work item from:
  - `docs/design/workflow_lisp_unified_frontend_design.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/1/design-gap-architect/work_item_context.md`
  - `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json`
- The progress ledger is empty, so the plan must fully define scope and verification instead of relying on earlier landed events.
- Preserve the implemented baseline:
  - `ProcRef`, `bind-proc`, and `let-proc` remain compile-time-only.
  - shared validation remains authoritative.
  - no runtime closure syntax, runtime value type, executable IR node, registry, resume executor path, or runtime dispatch is added.
- Do not smuggle callable behavior through helper scripts, inline shell/Python glue, command adapters, or opaque runtime shims. The command-adapter design remains a hard constraint even though this slice does not add adapter work.
- Keep the new surface fixture-only and negative-only. It exists to validate forbidden shapes, not to prove an executable closure design.

## Current Checkout Facts To Treat As Baseline

- `orchestrator/workflow_lisp/type_env.py` already rejects runtime transport of `ProcRef[...]` in nested collections and records with `proc_ref_runtime_transport_forbidden`.
- `orchestrator/workflow_lisp/workflows.py` already rejects workflow-boundary transport of `ProcRef[...]` and `WorkflowRef[...]`.
- `orchestrator/workflow_lisp/loops.py` already rejects `ProcRef` values in loop/runtime state.
- `tests/test_workflow_lisp_loop_recur.py::test_typecheck_loop_recur_rejects_proc_ref_state` is the existing ordinary-state regression that must remain unchanged.
- `tests/test_workflow_lisp_workflow_refs.py::test_workflow_ref_top_level_param_is_allowed_but_nested_return_transport_is_rejected` proves ordinary `WorkflowRef` runtime-transport rejection and must remain unchanged.
- `tests/test_workflow_lisp_workflows.py::test_workflow_boundary_rejects_macro_emitted_proc_ref_runtime_transport` proves macro-generated ordinary ProcRef transport still fails through the normal compiler path.
- `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys` already proves emitted executable IR omits `ProcRef` and `WorkflowRef` payloads.
- `orchestrator/workflow_lisp/diagnostics.py` infers `phase`, `validation_pass`, and `authority_layer` from known code families; new `runtime_closure_*` and `closure_*` codes need explicit classification or they will serialize with the wrong metadata.
- There is currently no `orchestrator/workflow_lisp/runtime_closure_design_fixtures.py`, no fixture matrix under `tests/fixtures/workflow_lisp/runtime_closure_disabled/`, and no dedicated closure-fixture regression module.

## File Map

**Create**

- `orchestrator/workflow_lisp/runtime_closure_design_fixtures.py`
- `tests/fixtures/workflow_lisp/runtime_closure_disabled/case_matrix.yaml`
- `tests/test_workflow_lisp_runtime_closure_fixtures.py`

**Modify**

- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_semantic_ir.py`

**Verify Only**

- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_workflow_refs.py`
- `tests/test_workflow_lisp_workflows.py`

## Behavior Inventory The Implementation Must Prove

- Disabled-profile runtime-closure introduction and invocation reject with `runtime_closure_not_enabled`.
- The fixture harness distinguishes baseline-owned ordinary callable transport from new closure-specific rows:
  - runtime `ProcRef` in loop state stays owned by the existing Stage 3 selector and keeps failing with `proc_ref_runtime_transport_forbidden`;
  - closure-specific rows are handled only by the new fixture validator.
- The design-fixture-only profile can deterministically emit all closure-specific diagnostics named in the target design:
  - `closure_family_unknown`
  - `closure_code_id_invalid`
  - `closure_signature_invalid`
  - `closure_dynamic_code_forbidden`
  - `closure_provider_capture_forbidden`
  - `closure_capture_mode_forbidden`
  - `closure_capture_schema_invalid`
  - `closure_runtime_transport_forbidden`
  - `closure_effect_bound_invalid`
  - `closure_capability_bound_invalid`
  - `closure_write_root_ambiguous`
  - `closure_resume_bundle_mismatch`
  - `closure_resume_code_mismatch`
  - `closure_source_map_missing`
- Diagnostic metadata for those codes is stable when rendered and serialized:
  - `runtime_closure_not_enabled` serializes as frontend validation, not parse fallback.
  - `closure_source_map_missing` serializes through the source-map family.
  - `closure_resume_bundle_mismatch` and `closure_resume_code_mismatch` serialize as executable/resume identity failures.
  - all other `closure_*` codes serialize as frontend validation failures with explicit `validation_pass` / `authority_layer`.
- Ordinary successful frontend builds still omit closure markers from `core_workflow_ast`, `semantic_ir`, `executable_ir`, and `runtime_plan`.
- The fixture module never emits:
  - a runtime closure object,
  - a closure-family registry,
  - an executable invocation node,
  - a compiled artifact consumed by the real build path.

## Proposed Module Contract

Implement the new module as a data-driven test helper, not as part of stage 1 or stage 3 compilation:

```python
@dataclass(frozen=True)
class RuntimeClosureFixtureLocation:
    label: str
    path: str
    line: int
    column: int
    form_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeClosureFixtureCase:
    fixture_id: str
    profile: str
    validation_surface: str
    case_kind: str
    payload: Mapping[str, object]
    primary_location: RuntimeClosureFixtureLocation
    expected_code: str
    expected_message_contains: tuple[str, ...] = ()
    expected_stage3_selector: str | None = None
    creation_location: RuntimeClosureFixtureLocation | None = None
    invocation_location: RuntimeClosureFixtureLocation | None = None
    family_declaration_location: RuntimeClosureFixtureLocation | None = None
    code_body_location: RuntimeClosureFixtureLocation | None = None
    accepted_family_location: RuntimeClosureFixtureLocation | None = None
    effect_bound_location: RuntimeClosureFixtureLocation | None = None
    capability_bound_location: RuntimeClosureFixtureLocation | None = None
    write_root_policy_location: RuntimeClosureFixtureLocation | None = None
    resume_validation_location: RuntimeClosureFixtureLocation | None = None
    capture_locations: tuple[RuntimeClosureFixtureLocation, ...] = ()


def load_runtime_closure_fixture_cases(path: Path) -> tuple[RuntimeClosureFixtureCase, ...]:
    ...


def validate_runtime_closure_fixture_case(
    case: RuntimeClosureFixtureCase,
) -> tuple[LispFrontendDiagnostic, ...]:
    ...
```

Design rules for that contract:

- `validation_surface="fixture_validator"` rows are the only rows accepted by `validate_runtime_closure_fixture_case(...)`.
- `validation_surface="baseline_stage3_selector"` rows must fail fast with a deterministic ownership error that names the recorded selector instead of re-implementing existing ProcRef/WorkflowRef guardrails inside the new module.
- `primary_location` must be the true authored failure site for the diagnostic under test.
- Related authored locations must be preserved in deterministic notes, not dropped into unstructured strings.
- The loader must reject malformed fixture rows with a narrow `ValueError` that includes the offending `fixture_id`.

## Task Checklist

### Task 1: Add The Rejection Matrix And Its First Failing Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/runtime_closure_disabled/case_matrix.yaml`
- Create: `tests/test_workflow_lisp_runtime_closure_fixtures.py`

- [ ] **Step 1: Write the rejected-shape matrix**

Create `tests/fixtures/workflow_lisp/runtime_closure_disabled/case_matrix.yaml` with one explicit row per required class. Do not rely on prose-only coverage.

Required rows:

- `baseline-proc-ref-state`
- `disabled-authored-closure-value`
- `disabled-let-proc-runtime-closure`
- `disabled-direct-closure-invoke`
- `design-invoke-without-accepted-family`
- `design-invalid-accepted-code-id`
- `design-signature-mismatch`
- `design-provider-produced-code`
- `design-command-produced-code`
- `design-artifact-transport`
- `design-workflow-output-transport`
- `design-provider-role-capture`
- `design-mutable-state-capture`
- `design-capture-closure-value`
- `design-effect-bound-violation`
- `design-capability-bound-violation`
- `design-write-root-ambiguity`
- `design-resume-bundle-mismatch`
- `design-resume-code-mismatch`
- `design-source-map-missing`

Each row must carry the authored locations relevant to that failure class. At minimum:

- creation and invocation locations for invocation failures,
- accepted-family-list location for `closure_family_unknown`,
- capture locations for capture failures,
- family/body locations for code-identity failures,
- bound locations for effect/capability failures,
- write-root policy location for write-root ambiguity,
- resume validation location for resume and source-map rows.

Use one baseline-owned row to document the ordinary ProcRef state rejection:

```yaml
- fixture_id: baseline-proc-ref-state
  profile: disabled
  validation_surface: baseline_stage3_selector
  case_kind: runtime_value
  expected_code: proc_ref_runtime_transport_forbidden
  expected_stage3_selector: tests/test_workflow_lisp_loop_recur.py::test_typecheck_loop_recur_rejects_proc_ref_state
```

- [ ] **Step 2: Add failing tests that lock the fixture inventory and ownership split**

Create `tests/test_workflow_lisp_runtime_closure_fixtures.py` with failing tests before any implementation code exists.

Minimum tests:

```python
def test_runtime_closure_fixture_matrix_contains_required_inventory() -> None:
    cases = {
        case.fixture_id: case
        for case in load_runtime_closure_fixture_cases(FIXTURE_ROOT / "case_matrix.yaml")
    }
    assert set(cases) >= {
        "baseline-proc-ref-state",
        "disabled-authored-closure-value",
        "disabled-let-proc-runtime-closure",
        "disabled-direct-closure-invoke",
        "design-invoke-without-accepted-family",
        "design-invalid-accepted-code-id",
        "design-signature-mismatch",
        "design-provider-produced-code",
        "design-command-produced-code",
        "design-artifact-transport",
        "design-workflow-output-transport",
        "design-provider-role-capture",
        "design-mutable-state-capture",
        "design-capture-closure-value",
        "design-effect-bound-violation",
        "design-capability-bound-violation",
        "design-write-root-ambiguity",
        "design-resume-bundle-mismatch",
        "design-resume-code-mismatch",
        "design-source-map-missing",
    }
    assert cases["baseline-proc-ref-state"].validation_surface == "baseline_stage3_selector"
    assert (
        cases["baseline-proc-ref-state"].expected_stage3_selector
        == "tests/test_workflow_lisp_loop_recur.py::test_typecheck_loop_recur_rejects_proc_ref_state"
    )


def test_fixture_validator_rejects_baseline_owned_rows() -> None:
    baseline_case = _case("baseline-proc-ref-state")
    with pytest.raises(ValueError, match="baseline_stage3_selector"):
        validate_runtime_closure_fixture_case(baseline_case)


@pytest.mark.parametrize(
    ("fixture_id", "expected_code"),
    [
        ("disabled-authored-closure-value", "runtime_closure_not_enabled"),
        ("disabled-let-proc-runtime-closure", "runtime_closure_not_enabled"),
        ("disabled-direct-closure-invoke", "runtime_closure_not_enabled"),
        ("design-invoke-without-accepted-family", "closure_family_unknown"),
        ("design-invalid-accepted-code-id", "closure_code_id_invalid"),
        ("design-signature-mismatch", "closure_signature_invalid"),
        ("design-provider-produced-code", "closure_dynamic_code_forbidden"),
        ("design-command-produced-code", "closure_dynamic_code_forbidden"),
        ("design-artifact-transport", "closure_runtime_transport_forbidden"),
        ("design-workflow-output-transport", "closure_runtime_transport_forbidden"),
        ("design-provider-role-capture", "closure_provider_capture_forbidden"),
        ("design-mutable-state-capture", "closure_capture_mode_forbidden"),
        ("design-capture-closure-value", "closure_capture_schema_invalid"),
        ("design-effect-bound-violation", "closure_effect_bound_invalid"),
        ("design-capability-bound-violation", "closure_capability_bound_invalid"),
        ("design-write-root-ambiguity", "closure_write_root_ambiguous"),
        ("design-resume-bundle-mismatch", "closure_resume_bundle_mismatch"),
        ("design-resume-code-mismatch", "closure_resume_code_mismatch"),
        ("design-source-map-missing", "closure_source_map_missing"),
    ],
)
def test_fixture_validator_emits_expected_code(fixture_id: str, expected_code: str) -> None:
    diagnostic = validate_runtime_closure_fixture_case(_case(fixture_id))[0]
    assert diagnostic.code == expected_code
```

- [ ] **Step 3: Add failing tests for location coverage and malformed fixture handling**

Add focused assertions that prove the matrix captures the designed authored surfaces instead of only raw codes.

Suggested tests:

```python
def test_invocation_fixture_cases_preserve_creation_and_invocation_locations() -> None:
    case = _case("design-invoke-without-accepted-family")
    assert case.creation_location is not None
    assert case.invocation_location is not None
    assert case.accepted_family_location is not None


def test_resume_and_source_map_cases_include_resume_validation_location() -> None:
    for fixture_id in (
        "design-resume-bundle-mismatch",
        "design-resume-code-mismatch",
        "design-source-map-missing",
    ):
        assert _case(fixture_id).resume_validation_location is not None


def test_fixture_loader_rejects_malformed_case_rows(tmp_path: Path) -> None:
    bad_fixture = tmp_path / "bad.yaml"
    bad_fixture.write_text("cases:\\n  - fixture_id: broken\\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken"):
        load_runtime_closure_fixture_cases(bad_fixture)
```

- [ ] **Step 4: Collect the new test module**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_runtime_closure_fixtures.py -q
```

Expected: collection succeeds and lists the new tests, even though they still fail at runtime because the implementation module does not exist yet.

- [ ] **Step 5: Run the new module to confirm failure**

Run:

```bash
pytest tests/test_workflow_lisp_runtime_closure_fixtures.py -q
```

Expected: FAIL because `orchestrator.workflow_lisp.runtime_closure_design_fixtures` does not exist yet, or because the validator contract is not implemented.

### Task 2: Implement The Fixture Loader And Validator

**Files:**

- Create: `orchestrator/workflow_lisp/runtime_closure_design_fixtures.py`

- [ ] **Step 1: Implement the dataclasses and YAML loader**

Add the new module with:

- the location/case dataclasses from the contract above,
- a YAML reader that loads `cases`,
- deterministic tuple conversion for `form_path`, `expected_message_contains`, and `capture_locations`,
- validation for required fields by `case_kind`,
- a small private `_location_from_mapping(...)` helper.

Implementation direction:

```python
def load_runtime_closure_fixture_cases(path: Path) -> tuple[RuntimeClosureFixtureCase, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError(f"{path}: expected `cases` list")
    return tuple(_case_from_mapping(index, raw_case, path) for index, raw_case in enumerate(raw_cases))
```

- [ ] **Step 2: Implement the fixture validator as a mapping table, not a compiler path**

The validator must:

- reject baseline-owned rows up front,
- map disabled-profile introduction/invocation rows to `runtime_closure_not_enabled`,
- map design-fixture-only rows to the exact code recorded in the fixture,
- construct `LispFrontendDiagnostic` objects with explicit metadata and stable notes,
- never call stage 1, stage 3, lowering, or artifact emission helpers.

Use a small table instead of free-form string logic:

```python
_FIXTURE_CODE_METADATA = {
    "runtime_closure_not_enabled": {"validation_pass": "type", "authority_layer": "frontend"},
    "closure_family_unknown": {"validation_pass": "type", "authority_layer": "frontend"},
    "closure_source_map_missing": {"validation_pass": "source_map", "authority_layer": "frontend"},
    "closure_resume_bundle_mismatch": {"validation_pass": "executable", "authority_layer": "frontend"},
}
```

- [ ] **Step 3: Implement stable notes for multi-location failures**

For cases with related locations, include deterministic notes that call out the authored relationship:

```python
notes = (
    f"closure creation site: {render_location(case.creation_location)}",
    f"closure invocation site: {render_location(case.invocation_location)}",
    f"accepted family list: {render_location(case.accepted_family_location)}",
)
```

Rules:

- invocation failures use the invocation site as the primary span;
- capture failures use the capture site as primary;
- resume/source-map failures use the resume validation site or missing-source-map surface as primary;
- when both creation and invocation matter, preserve both in notes.

- [ ] **Step 4: Run the new test module until it passes**

Run:

```bash
pytest tests/test_workflow_lisp_runtime_closure_fixtures.py -q
```

Expected: PASS.

### Task 3: Register Diagnostic Metadata And Document The Boundary

**Files:**

- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `orchestrator/workflow_lisp/README.md`

- [ ] **Step 1: Extend diagnostic classification for the new code family**

Update `orchestrator/workflow_lisp/diagnostics.py` so the new closure codes serialize with the intended `phase`, `validation_pass`, and `authority_layer`.

Recommended split:

- source-map family:
  - `closure_source_map_missing`
- executable family:
  - `closure_resume_bundle_mismatch`
  - `closure_resume_code_mismatch`
- type/front-end validation family:
  - `runtime_closure_not_enabled`
  - the remaining `closure_*` codes for this slice

Do not let these codes fall back to parse metadata.

- [ ] **Step 2: Add targeted diagnostic serialization tests before or alongside the code change**

Extend `tests/test_workflow_lisp_diagnostics.py` so the new metadata is locked in.

Suggested additions:

```python
@pytest.mark.parametrize(
    ("code", "expected_phase", "expected_validation_pass"),
    [
        ("runtime_closure_not_enabled", "typecheck", "type"),
        ("closure_family_unknown", "typecheck", "type"),
        ("closure_resume_bundle_mismatch", "executable", "executable"),
        ("closure_resume_code_mismatch", "executable", "executable"),
        ("closure_source_map_missing", "source_map", "source_map"),
    ],
)
def test_serialize_diagnostic_infers_runtime_closure_metadata(
    code: str,
    expected_phase: str,
    expected_validation_pass: str,
) -> None:
    ...
```

If the existing parameterized test is easier to extend than adding a new one, extend it directly.

- [ ] **Step 3: Update the package README to describe the new seam accurately**

Add one short paragraph that says:

- runtime closures remain deferred,
- `runtime_closure_design_fixtures.py` is test-only,
- ordinary compilation must not emit runtime-closure artifacts,
- `let-proc` remains compile-time-only.

- [ ] **Step 4: Run focused diagnostic tests**

Run:

```bash
pytest tests/test_workflow_lisp_diagnostics.py -k "runtime_closure or serialize_diagnostic_infers_validation_metadata_from_code" -q
```

Expected: PASS.

### Task 4: Extend No-Leak Artifact Regressions

**Files:**

- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_semantic_ir.py`

- [ ] **Step 1: Extend the executable-IR omission test with closure markers**

Update `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys` so it also proves emitted executable IR omits closure markers:

```python
for marker in (
    "workflow_lisp_runtime_closure",
    "closure_families",
    "InvokeClosure",
    "Closure[",
    "runtime_closure",
):
    assert marker not in serialized
```

Keep the existing `ProcRef` / `WorkflowRef` assertions in place.

- [ ] **Step 2: Extend the build-artifact regression across all emitted artifact files**

Update `tests/test_workflow_lisp_build_artifacts.py::test_build_emits_required_artifacts_and_deferred_status_entries` or add a sibling test that reads:

- `core_workflow_ast.json`
- `semantic_ir.json`
- `executable_ir.json`
- `runtime_plan.json`

and asserts that none of those serialized payloads contain the closure markers listed above.

Suggested helper:

```python
def _assert_no_runtime_closure_markers(serialized: str) -> None:
    for marker in (
        "workflow_lisp_runtime_closure",
        "closure_families",
        "InvokeClosure",
        "Closure[",
        "runtime_closure",
    ):
        assert marker not in serialized
```

- [ ] **Step 3: Collect modified test modules**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_build_artifacts.py -q
pytest --collect-only tests/test_workflow_semantic_ir.py -q
```

Expected: both modules collect successfully after the new assertions are added.

- [ ] **Step 4: Run the focused no-leak regressions**

Run:

```bash
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_build_emits_required_artifacts_and_deferred_status_entries \
  tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys \
  -q
```

Expected: PASS.

### Task 5: Prove Separation From The Existing Compiler Guards And Run End-To-End Verification

**Files:**

- Verify only: all files above

- [ ] **Step 1: Re-run the ordinary callable transport regressions unchanged**

Run:

```bash
pytest \
  tests/test_workflow_lisp_loop_recur.py::test_typecheck_loop_recur_rejects_proc_ref_state \
  tests/test_workflow_lisp_workflow_refs.py::test_workflow_ref_top_level_param_is_allowed_but_nested_return_transport_is_rejected \
  tests/test_workflow_lisp_workflows.py::test_workflow_boundary_rejects_macro_emitted_proc_ref_runtime_transport \
  -q
```

Expected: PASS. This proves the new fixture suite did not replace or weaken the current Stage 3 guardrails.

- [ ] **Step 2: Run the closure-fixture, diagnostics, and artifact selectors together**

Run:

```bash
pytest \
  tests/test_workflow_lisp_runtime_closure_fixtures.py \
  tests/test_workflow_lisp_diagnostics.py -k "runtime_closure or serialize_diagnostic_infers_validation_metadata_from_code" \
  tests/test_workflow_lisp_build_artifacts.py::test_build_emits_required_artifacts_and_deferred_status_entries \
  tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run one public CLI compile smoke check**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc \
  --entry-workflow orchestrate \
  --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json \
  --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json \
  --emit-debug-yaml .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/expanded.debug.yaml \
  --emit-core-ast .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/core_workflow_ast.json \
  --emit-semantic-ir .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/semantic_ir.json \
  --emit-executable-ir .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/executable_ir.json \
  --emit-runtime-plan .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/runtime_plan.json \
  --emit-source-map .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/source_map.json
```

Expected: the public compile path succeeds and emits the requested artifacts.

- [ ] **Step 4: Scan the emitted artifacts for forbidden closure markers**

Run:

```bash
rg -n \
  -e 'closure_families' \
  -e 'InvokeClosure' \
  -e 'workflow_lisp_runtime_closure' \
  -e 'runtime_closure' \
  -e 'Closure\\[' \
  .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/core_workflow_ast.json \
  .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/semantic_ir.json \
  .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/executable_ir.json \
  .orchestrate/tmp/runtime-closure-disabled-profile-fixtures/runtime_plan.json
```

Expected: no output and exit status `1`.

- [ ] **Step 5: Record implementation evidence**

Capture in the implementation summary or PR notes:

- the created fixture ids,
- the exact pytest selectors run,
- the exact CLI compile command,
- the no-match `rg` scan result,
- confirmation that the progress ledger had no pre-existing events and all scope/verification came from this plan and the consumed design docs.

## Definition Of Done

- The repo contains a fixture-only runtime-closure rejection module and matrix.
- The new module is not wired into ordinary stage 1, stage 3, lowering, or runtime execution.
- Closure-specific diagnostics serialize with explicit metadata instead of parse fallback.
- Existing ProcRef/WorkflowRef runtime-transport regressions remain unchanged and passing.
- Ordinary frontend build artifacts remain free of runtime-closure markers.
- The public CLI compile smoke plus explicit artifact scan both pass.
