# YAML Loader / Shared Validation Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not create a worktree; repository
> policy requires execution in the existing checkout.

**Goal:** Isolate authored YAML/YML text and file parsing behind the legacy
frontend while making one shared in-memory mapping-to-`LoadedWorkflowBundle`
validation service authoritative for both YAML and Workflow Lisp lowering.

**Status:** Complete. The final implementation and broad-regression-correction
tree is `7cc6f1d2`; independent specification review returned PASS and
code-quality review returned APPROVED for that exact HEAD. Stage 6 YAML
retirement Task 4 is now the exclusive current selector. YAML remains
`Legacy`, and Task 7 still owns fresh YAML rejection and parser removal.

**Architecture:** `orchestrator/loader.py` remains the compatibility import and
the only authored-workflow YAML parsing/file-recursion owner. A new
`orchestrator/workflow/validation.py` owns normalization, mapping validation,
surface elaboration, and bundle construction from frontend-produced in-memory
mappings plus either explicit imported bundles or the legacy import-resolver
callback. Workflow Lisp calls that service directly and retains source-span
diagnostic remapping; it must not instantiate or reach through `WorkflowLoader`.

**Tech Stack:** Python 3, immutable `LoadedWorkflowBundle` / `SurfaceWorkflow`,
PyYAML only in the legacy loader, pytest, Workflow Lisp stage-3 compiler and CLI.

**Task 2 closeout binding:**
`TASK2_CLOSEOUT_COMMIT=2b6001c7c8e78cc6a0cc1dd4e7d969549347aeab`.
The commit is an ancestor of this plan, selects Stage 6 Task 3, keeps YAML
`Legacy`, includes both final Task 2 reviews, and leaves every Task 2-owned path
clean.

---

## Governing contract and scope

This plan implements only Stage 6 Task 3 from
`docs/plans/2026-07-07-yaml-retirement-program.md`:

1. move normalization and validation used by both authoring frontends into a
   shared module;
2. keep authored YAML/YML parsing and recursive file loading isolated behind
   the legacy loader;
3. redirect Workflow Lisp lowered mappings to the shared validator without
   changing surface, Core AST, Semantic IR, executable IR, runtime-plan,
   diagnostic, or runtime semantics; and
4. prove the boundary with focused loader/lowering/characterization tests,
   collection checks, and one fresh `.orc` route smoke.

Normative DSL behavior remains owned by `specs/dsl.md`. Typed surface and IR
semantics remain owned by the existing elaboration/lowering contracts and the
Workflow Lisp frontend design documents routed through `docs/index.md` and
`docs/capability_status_matrix.md`. This implementation plan may relocate code;
it does not revise a language rule.

### Explicit non-goals

- Do not remove fresh YAML/YML execution or the PyYAML dependency; Stage 6 Task
  7 owns rejection and parser removal.
- Do not change `.orc` syntax, typechecking, lowering, generated identity,
  source maps, build fingerprints, runtime plans, or validation policy.
- Do not change YAML import path semantics, duplicate-key diagnostics,
  `PreservingLoader` boolean behavior, same-version import checks, or error
  ordering.
- Do not edit the Stage 6 Task 2 dashboard implementation while executing this
  plan.
- Do not make dashboard persisted-typed-surface loading or any other
  persisted-build consumer feed its immutable DTO or wire payload back through
  fresh source validation.
- Do not introduce a generic “load any frontend” API in this task. Fresh YAML
  parsing and fresh `.orc` compilation remain separate frontend entry points;
  they converge only at the in-memory validation boundary.

### Task 2 persisted typed-surface boundary and sequencing gate

Task 2 emits `persisted_workflow_surface.json` directly from an already
validated `LoadedWorkflowBundle`. Its canonical bytes decode to the immutable
`PersistedWorkflowSurfaceGraph` DTO; they are not executable IR and must never
be converted back into a fresh validation request. The complete closed anchor
`{schema_version, path, entry_workflow, sha256}` is byte-for-byte identical in
the content-addressed build manifest and final run state. A dashboard read is
authoritative only after it verifies the final state anchor, the corresponding
manifest anchor, the bound artifact path, the SHA-256 digest, canonical JSON,
and graph topology in that order.

That persisted DTO is a terminal read model. Loading it must call no Workflow
Lisp compiler or parser, YAML parser, macro expander, surface elaborator,
mapping validator, bundle constructor/lowerer, executable validator, runtime
plan derivation, or authored `.orc` source reader. Artifact JSON reads are
required and remain allowed. Conversely, Task 3's shared validator accepts only
fresh frontend-produced in-memory mappings plus explicit validation metadata;
it does not accept a `PersistedWorkflowSurfaceGraph` or its wire payload.

Task 3 begins only after the Task 2 plan has met its completion criteria, both
independent reviews have approved the final tree, and the reviewed Task 2
closeout commit is an ancestor of `HEAD`. The executor must record that exact
commit as `TASK2_CLOSEOUT_COMMIT`, verify it selects Stage 6 Task 3 while YAML
remains `Legacy`, and verify every Task 2-owned path listed below is clean
before committing or executing this plan. A working-tree implementation,
uncommitted approval, or commit that predates either final review does not
satisfy this gate.

Task 3 adds its cross-boundary trap in
`tests/test_workflow_shared_validation.py` without editing Task 2-owned files.
The test must load the final state/manifest/digest-bound
`PersistedWorkflowSurfaceGraph`, trap every fresh compiler/parser/elaborator/
lowerer/validator entry point, and trap reads of the exact bound `.orc` source
path while allowing the bound manifest and `persisted_workflow_surface.json`
reads. The complete Task 2 dashboard/CLI regression lane and this trap are both
mandatory.

## Architecture boundary and future cost

The shared entry point should have this shape (names may change only during
review if the replacement is equally explicit):

```python
@dataclass(frozen=True)
class WorkflowImportResolutionResult:
    bundles: Mapping[str, LoadedWorkflowBundle]
    errors: tuple[ValidationError, ...] = ()


class WorkflowImportResolver(Protocol):
    def __call__(
        self,
        imports: Any,
        *,
        version: str,
        workflow_path: Path,
    ) -> WorkflowImportResolutionResult: ...


@dataclass(frozen=True)
class WorkflowMappingValidationOptions:
    workspace_root: Path
    boundary_validation_policy: WorkflowBoundaryValidationPolicy
    supported_versions: frozenset[str] = DEFAULT_SUPPORTED_VERSIONS
    version_order: tuple[str, ...] = DEFAULT_VERSION_ORDER
    supported_output_types: frozenset[str] = DEFAULT_SUPPORTED_OUTPUT_TYPES
    private_collection_output_types: frozenset[str] = DEFAULT_PRIVATE_COLLECTION_OUTPUT_TYPES
    string_contract_version: str = DEFAULT_STRING_CONTRACT_VERSION
    env_var_pattern: Pattern[str] = DEFAULT_ENV_VAR_PATTERN
    input_ref_pattern: Pattern[str] = DEFAULT_INPUT_REF_PATTERN
    allow_private_collection_output_schemas: bool = False
    allow_generated_repeat_until_on_exhausted_refs: bool = False
    generated_repeat_until_on_exhausted_refs: Mapping[str, Mapping[str, str]] = field(
        default_factory=dict
    )
    dedicated_runtime_proof_nested_structured_step_names: frozenset[str] = frozenset()
    dedicated_runtime_proof_parent_ref_allowances: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class WorkflowMappingBuildRequest:
    authored_mapping: Mapping[str, Any]
    workflow_path: Path
    imported_bundles: Mapping[str, LoadedWorkflowBundle] = field(default_factory=dict)
    import_resolver: WorkflowImportResolver | None = None
    expected_version: str | None = None
    workflow_is_imported: bool = False
    frontend_kind: str | None = None
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = ()
    lexical_checkpoint_points: tuple[Mapping[str, Any], ...] = ()
    managed_write_root_inputs: tuple[str, ...] = ()
    runtime_context_inputs: tuple[str, ...] = ()
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    private_artifact_ids: tuple[str, ...] = ()
    runtime_proof_parent_ref_allowances: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class WorkflowMappingValidationResult:
    bundle: LoadedWorkflowBundle | None
    errors: tuple[ValidationError, ...]


class _WorkflowMappingValidator(SurfaceWorkflowValidationBackend):
    """Private, request-scoped implementation behind the public coordinator."""

    def __init__(
        self,
        request: WorkflowMappingBuildRequest,
        options: WorkflowMappingValidationOptions,
    ) -> None:
        ...  # derive all mutable validation state from request/options only


def validate_workflow_mapping(
    request: WorkflowMappingBuildRequest,
    *,
    options: WorkflowMappingValidationOptions,
) -> WorkflowMappingValidationResult:
    ...
```

The service must copy and normalize the supplied mapping, elaborate it through
`elaborate_surface_workflow`, attach `frontend_kind` to provenance when
provided, construct the bundle through `build_loaded_workflow_bundle`, and
return structured `ValidationError` values without frontend-specific rendering.
The YAML frontend raises the existing `WorkflowValidationError`; Workflow Lisp
passes the errors to `_raise_remapped_validation_error`.

The version and output-type policy fields are intentionally explicit. The
legacy facade populates them from its compatibility class attributes; Workflow
Lisp uses the shared module defaults. This preserves callers that temporarily
override `WorkflowLoader.SUPPORTED_VERSIONS`, `WorkflowLoader.VERSION_ORDER`,
the output-type sets, `WorkflowLoader.STRING_CONTRACT_VERSION`,
`WorkflowLoader.ENV_VAR_PATTERN`, or `WorkflowLoader.INPUT_REF_PATTERN` without
creating a second implicit authority. The legacy facade re-exports and binds
all seven compatibility policies; monkeypatch tests must prove each bound value
reaches the request-scoped validator.

`_WorkflowMappingValidator` is private implementation, not an alternative API.
Its current workflow path, source root, imported bundles, input specs,
workflow-is-imported flag, generated-exhaustion refs, generated/private
allowances, validation policy, version/type policy, and error accumulator are
initialized from one request/options pair. It exposes the elaboration backend
methods only to `elaborate_surface_workflow`; callers use only
`validate_workflow_mapping`.

Generated-step admission is derived centrally and cannot be an arbitrary
request flag:

```python
allow_generated_step_kinds = (
    request.frontend_kind == "workflow_lisp"
    or options.boundary_validation_policy
    is WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF
)
```

Therefore every `.orc` lowered mapping enters elaboration with generated steps
enabled. Legacy YAML enables them only under the dedicated-runtime-proof
policy; ordinary/public-callable YAML rejects them. Both directions require
tests: `.orc` and dedicated-proof YAML accept the same minimal generated kind,
while public-callable YAML rejects it.

`WorkflowImportResolver` is a narrow callback protocol implemented by the
legacy loader. The shared coordinator invokes it after version-envelope checks,
normalization, and expected-version comparison—the same order used today. Its
implementation owns recursive YAML file parsing and returns resolved bundles
plus structured load errors. Workflow Lisp supplies `imported_bundles` and no
resolver. Reject a request that supplies both non-empty `imported_bundles` and
an import resolver. This callback keeps file I/O in the legacy frontend without
moving normalization after import loading or changing diagnostic order.

This boundary deliberately makes future frontend-specific validation shortcuts
harder: every semantic validation change must be expressible against the shared
mapping request and structured diagnostic model. A frontend that needs a new
exception must add an explicit, reviewed option rather than mutating validator
private attributes. That extra ceremony is the intended cost of preventing the
YAML parser and Workflow Lisp compiler from drifting into separate semantic
authorities.

## File responsibility map

**Create:**

- `orchestrator/workflow/validation.py` — shared validation policy, options,
  request/result records, v2.14 normalization, validation backend, and the
  mapping-to-bundle entry point. This module must not import `yaml` or open an
  authored workflow file.
- `tests/test_workflow_shared_validation.py` — parity, isolation, options, and
  both-frontend contract tests.

**Modify:**

- `orchestrator/loader.py` — retain `PreservingLoader`, duplicate import-alias
  scanning, YAML text/file decoding, recursive YAML import resolution, and the
  public `WorkflowLoader` compatibility facade; delegate normalization and
  mapping validation to the shared module.
- `orchestrator/workflow_lisp/lowering/core.py` — replace `WorkflowLoader`
  construction/private-attribute mutation with one explicit shared-validation
  request and preserve diagnostic remapping.
- `tests/test_loader_validation.py` — preserve legacy YAML parser/import/error
  contracts and public compatibility imports.
- `tests/test_workflow_lisp_lowering.py` — prove direct shared validation,
  policy options, remapped errors, and lack of dependency on the YAML loader.
- `tests/test_workflow_lisp_modules.py` — retain in-memory imported-bundle
  validation behavior.
- `tests/test_workflow_ir_lowering.py` — retain exact typed bundle/IR
  characterization across the split.
- `docs/plans/2026-07-07-yaml-retirement-program.md` — only after all tests and
  both independent reviews pass, mark Task 3 complete and advance the selector.
- `docs/index.md` and `docs/capability_status_matrix.md` — only at closeout,
  route the implemented boundary and current Stage 6 selector accurately.

**Regression-only; do not edit for Task 3:**

- `orchestrator/dashboard/models.py`
- `orchestrator/dashboard/projection.py`
- `orchestrator/dashboard/server.py`
- `orchestrator/dashboard/compiled_workflow.py`
- `orchestrator/cli/commands/dashboard.py`
- `tests/test_dashboard_projection.py`
- `tests/test_dashboard_server.py`
- `tests/test_dashboard_compiled_workflow.py`
- `tests/test_cli_dashboard_command.py`

## Commit isolation contract

The seven paths in the Stage 6 protected working-tree guard are user-owned and
must remain untouched. Task 2's persisted-surface implementation is a separate
reviewed ownership set and must also remain untouched during Task 3. Every
commit recipe below therefore contains two distinct literal cached-path guards.
Do not combine them, replace them with a status-wide heuristic, or assume a
clean worktree. Each recipe starts with `set -e`, prints the complete cached
path list, compares it to an exact staged allowlist, runs both guards, and runs
`git diff --cached --check` before committing. Any mismatch aborts.

Task 2-owned paths for this split are:

- `docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md`
- `orchestrator/dashboard/compiled_workflow.py`
- `orchestrator/dashboard/models.py`
- `orchestrator/dashboard/projection.py`
- `orchestrator/dashboard/server.py`
- `orchestrator/runtime_observability.py`
- `orchestrator/workflow/persisted_surface.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/build_artifacts.py`
- `tests/test_cli_dashboard_command.py`
- `tests/test_dashboard_compiled_workflow.py`
- `tests/test_dashboard_projection.py`
- `tests/test_dashboard_server.py`
- `tests/test_runtime_observability.py`
- `tests/test_runtime_observability_cli.py`
- `tests/test_persisted_workflow_surface.py`
- `tests/test_workflow_lisp_procedure_identity_retirement.py`
- `tests/test_workflow_lisp_build_artifacts.py`

## Task 0: Prove Task 2 closeout and commit this reviewed plan

**Files:**

- Create: `docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md`

- [x] Record the reviewed Task 2 closeout SHA in `TASK2_CLOSEOUT_COMMIT`. Verify
  both Task 2 independent reviews apply to that tree, the commit is an ancestor
  of `HEAD`, the Stage 6 selector is Task 3, YAML remains `Legacy`, and every
  Task 2-owned path above is clean. Fail closed if the SHA or either review
  binding is absent.
- [x] Obtain independent specification and execution-quality approval of this
  plan after the final persisted-surface and atomic-composition revisions.
- [x] Commit the reviewed plan before touching implementation files:

```bash
set -e
TASK2_CLOSEOUT_COMMIT=2b6001c7c8e78cc6a0cc1dd4e7d969549347aeab
test -n "${TASK2_CLOSEOUT_COMMIT:?record the reviewed Task 2 closeout commit}"
test "$(git rev-parse "${TASK2_CLOSEOUT_COMMIT}^{commit}")" = \
  "$TASK2_CLOSEOUT_COMMIT"
git merge-base --is-ancestor "$TASK2_CLOSEOUT_COMMIT" HEAD
git show "$TASK2_CLOSEOUT_COMMIT:docs/plans/2026-07-07-yaml-retirement-program.md" \
  | rg -q '^\*\*Current selector:\*\* Task 3,'
git show "$TASK2_CLOSEOUT_COMMIT:docs/capability_status_matrix.md" \
  | rg -q '^\| YAML DSL v2\.x \| Legacy \|'
git show "$TASK2_CLOSEOUT_COMMIT:docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md" \
  | rg -q '^\*\*Status:\*\* Complete\.'
git show "$TASK2_CLOSEOUT_COMMIT:docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md" \
  | rg -q 'Independent specification review returned PASS'
git show "$TASK2_CLOSEOUT_COMMIT:docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md" \
  | rg -q 'code-quality review returned APPROVED'
test -z "$(git status --short -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py \
  orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py \
  orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py \
  orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py \
  orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py \
  tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py \
  tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py \
  tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py \
  tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
git add docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md
echo 'cached paths:'
git diff --cached --name-only
EXPECTED='docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md'
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "docs: plan shared workflow validation split"
```

## Task 1: Freeze the current two-frontend contract

**Files:**

- Create: `tests/test_workflow_shared_validation.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [x] Characterize a successful YAML mapping/bundle and a successful real
  `.orc` compile with `validate_shared=True`. Compare contract-level surface,
  Core AST, Semantic IR, executable IR, runtime plan, projection, provenance,
  normalized fields, and stable IDs; do not assert object reprs or prompt prose.
- [x] Characterize unsupported/mistyped version, unsafe path, marked duplicate
  import alias, same-version imported-workflow mismatch, and structured
  `subject_refs` used by Workflow Lisp source-map remapping. Preserve error
  order and existing messages where callers rely on them.
- [x] Collect and run the characterization before production changes:

```bash
pytest --collect-only -q tests/test_workflow_shared_validation.py \
  tests/test_loader_validation.py tests/test_workflow_lisp_lowering.py
pytest -q tests/test_workflow_shared_validation.py tests/test_loader_validation.py \
  tests/test_workflow_ir_lowering.py tests/test_workflow_lisp_lowering.py \
  -k 'shared_validation or loader_bundle or duplicate_import or version or remap'
```

Expected: collection and characterization are GREEN. This is a freeze, not a
RED implementation step.

- [x] Commit the characterization:

```bash
set -e
git add tests/test_workflow_shared_validation.py tests/test_loader_validation.py \
  tests/test_workflow_lisp_lowering.py
echo 'cached paths:'
git diff --cached --name-only
EXPECTED="$(printf '%s\n' tests/test_loader_validation.py \
  tests/test_workflow_lisp_lowering.py tests/test_workflow_shared_validation.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "test: characterize shared workflow validation boundary"
```

## Task 2: Atomically extract shared validation and compose the YAML frontend

### Atomic sequencing correction

Task 1's required real `.orc` characterization proved that the originally
separate Task 2 and Task 3 production commits cannot both satisfy this plan.
Removing semantic-validator methods from `WorkflowLoader` immediately breaks
the existing `.orc` validation route, while retaining those methods through
inheritance, private delegation, or facade-owned mutable validator state would
violate the accepted architecture. Therefore the extraction, YAML composition,
and direct `.orc` reroute are one atomic TDD implementation commit. No checked-in
revision may contain the extracted YAML facade without the direct `.orc` route.

Commit this reviewed sequencing correction by itself before continuing any
production implementation:

```bash
set -e
git add docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md
echo 'cached paths:'
git diff --cached --name-only
EXPECTED='docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md'
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "docs: make shared validation reroute atomic"
```

The Task 2 and Task 3 RED tests still run in their documented order, but their
production changes and GREEN verification land together. The former separate
commit recipes are superseded by this exact combined recipe:

```bash
set -e
git add orchestrator/workflow/validation.py orchestrator/loader.py \
  orchestrator/workflow_lisp/lowering/core.py \
  tests/test_workflow_shared_validation.py tests/test_loader_validation.py \
  tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_modules.py
echo 'cached paths:'
git diff --cached --name-only
EXPECTED="$(printf '%s\n' \
  orchestrator/loader.py \
  orchestrator/workflow/validation.py \
  orchestrator/workflow_lisp/lowering/core.py \
  tests/test_loader_validation.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_shared_validation.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "refactor: share validation across authored frontends"
```

The combined group must pass the complete Task 2 GREEN command and the complete
Task 3 both-direction command before review. The Task 3 section remains the
required `.orc` RED/GREEN checklist and evidence boundary; only its separate
commit recipe is superseded.

**Files:**

- Create: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_workflow_shared_validation.py`
- Modify: `tests/test_loader_validation.py`

- [x] Write genuine RED tests for the missing shared records/coordinator,
  in-memory bundle construction, structured bundle-construction errors,
  request isolation, parser isolation, private validator, generated-step policy,
  all seven compatibility policy bindings, recursive YAML imports, and exact
  once-per-parsed-file delegation. Require `WorkflowLoader` to use composition;
  neither frontend may import, construct, or reach through
  `_WorkflowMappingValidator`.
- [x] Run the RED selector and inspect failures:

```bash
pytest -q tests/test_workflow_shared_validation.py tests/test_loader_validation.py \
  -k 'in_memory or structured_errors or parser_isolation or private_validator or generated_step_policy or compatibility_policy_binding or bundle_construction_errors or workflow_loader_uses_shared_validator_by_composition or parsed_yaml_delegates_once_to_shared_validation or recursive_import'
```

Expected: failures are caused by the absent shared API and absent composition,
not malformed fixtures. Extraction and composition land together.

- [x] Create `orchestrator/workflow/validation.py` with the explicit immutable
  request/options/result records, import resolver protocol, normalization,
  private request-scoped `_WorkflowMappingValidator`, surface elaboration, and
  `build_loaded_workflow_bundle` coordination described above. Catch bundle
  construction `WorkflowValidationError` and return its exact structured errors.
- [x] In the same implementation step and commit, reduce `WorkflowLoader` to
  YAML/YML parse/file-recursion/import-resolution ownership plus composition
  through `validate_workflow_mapping`. Preserve `PreservingLoader`, marked
  duplicate aliases, path/import/version/error order, public load APIs, and all
  seven compatibility attributes. Bind those values explicitly into options.
  No checked-in revision may give `WorkflowLoader` ownership of the private
  validator or retain validator mutable state.
- [x] Run the extraction-only integration check before the `.orc` reroute and
  confirm the expected intermediate RED:

```bash
pytest -q tests/test_workflow_shared_validation.py tests/test_loader_validation.py \
  tests/test_workflow_ir_lowering.py
```

Expected at this intermediate worktree state: the Task 1 real `.orc`
characterization fails because `_validate_one_lowered_workflow` still reaches
the removed `WorkflowLoader` semantic-validator methods. This is required RED
evidence, not a committable state. After Task 3 reroutes `.orc`, rerun this
complete command GREEN together with Task 3's complete GREEN command.

- [x] Stage the extraction and YAML composition in the combined atomic commit.

Use only the atomic sequencing correction's combined recipe above, after the
Task 3 direct `.orc` RED/GREEN work also passes.

## Task 3: Redirect Workflow Lisp to shared validation directly

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_shared_validation.py`

- [x] **Step 1: Write the RED independence test**

Monkeypatch the legacy `WorkflowLoader` constructor and YAML parser to raise if
called, then compile a real `.orc` fixture with `validate_shared=True`.

```python
def test_orc_shared_validation_does_not_enter_legacy_yaml_loader(...):
    monkeypatch.setattr(
        "orchestrator.loader.WorkflowLoader.__init__",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy loader used")),
    )
    result = compile_stage3_module(ORC_FIXTURE, validate_shared=True, ...)
    assert result.validated_bundles
```

Choose a fixture with no explicitly requested legacy YAML imported-bundle
manifest. This test governs the normal `.orc` path; an explicit compatibility
manifest may still intentionally load a legacy YAML bundle in its own frontend
adapter.

Also adapt the existing executable-IR shared-validation remap test so it forces
`orchestrator.workflow.validation.build_loaded_workflow_bundle` to raise a
structured `WorkflowValidationError`. Record whether that shared patch site was
called. Before the `.orc` reroute, the test must fail because the shared site is
not reached at all. After the reroute, assert the site is reached exactly once,
the Task 2 coordinator returns the exact error, and
`_raise_remapped_validation_error` attributes it to the original `.orc` span.

- [x] **Step 2: Run the independence test and verify RED**

```bash
pytest -q \
  tests/test_workflow_shared_validation.py \
  tests/test_workflow_lisp_lowering.py \
  -k 'orc_shared_validation_does_not_enter_legacy_yaml_loader or remaps_executable_ir_shared_validation_failures'
```

Expected: both selected tests FAIL: the independence test because
`_validate_one_lowered_workflow` still constructs `WorkflowLoader`, and the
executable-IR test because Workflow Lisp has not yet reached the shared
coordinator/patch site. The Task 2 direct coordinator catch test already passes
and must remain green.

- [x] **Step 3: Replace private loader mutation with an explicit request**

In `_validate_one_lowered_workflow`:

- import the policy/options/request/service from
  `orchestrator.workflow.validation`, not `orchestrator.loader`;
- translate lowered-workflow allowances into
  `WorkflowMappingValidationOptions` and `WorkflowMappingBuildRequest`;
- pass in-memory same-file/imported bundles unchanged;
- set `frontend_kind="workflow_lisp"` in the request;
- rely on the coordinator's generated-step rule so `.orc` always passes
  `allow_generated_step_kinds=True` to elaboration, independent of the boundary
  validation profile;
- preserve generated path allocations, lexical checkpoint points, managed
  write-root inputs, runtime context inputs, private exec-context bindings,
  compatibility bridge inputs, private artifact IDs, generated
  repeat-exhaustion refs, and both dedicated-runtime-proof allowance sets; and
- pass `result.errors` unchanged into `_raise_remapped_validation_error`.

The shared coordinator already catches `WorkflowValidationError` from
`build_loaded_workflow_bundle` after Task 2. Task 3 must route `.orc` through
that existing catch and pass its exact structured errors to source remapping;
do not add a second catch in Workflow Lisp.

Delete the current mutations of `_allow_private_collection_output_schemas`,
`_allow_generated_repeat_until_on_exhausted_refs`,
`_generated_repeat_until_on_exhausted_refs`,
`_dedicated_runtime_proof_nested_structured_step_names`, and
`_dedicated_runtime_proof_parent_ref_allowances`. Those become explicit typed
options.

- [x] **Step 4: Run both-direction policy and diagnostic tests**

Run:

```bash
pytest -q \
  tests/test_workflow_shared_validation.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  -k 'shared_validation or runtime_proof or imported_bundles or remap or subject_refs or compatibility_bridge'
```

Expected: PASS, including:

- a generated `.orc` form accepted because Workflow Lisp always enables
  generated step kinds;
- the same generated kind accepted for dedicated-runtime-proof YAML and
  rejected for public-callable YAML;
- source-map error spans and structured subject refs unchanged;
- a forced `build_loaded_workflow_bundle` / executable-IR failure remapped to
  the originating `.orc` span with `validation_pass == "shared_validation"`;
- in-memory imported bundles reused without YAML loading; and
- the Workflow Lisp bundle contract projection unchanged from Task 1's
  Workflow Lisp characterization.

- [x] **Step 5: Stage the direct `.orc` route in the combined atomic commit**

Use only the atomic sequencing correction's combined recipe above, after both
Task 2 and Task 3 GREEN commands pass.

## Task 4: Install the permanent boundary guard and run route smokes

**Files:**

- Modify: `tests/test_workflow_shared_validation.py`
- Regression only: Task 2 dashboard files/tests listed above

- [x] **Step 1: Add the protected architecture guard**

Use AST-based checks, not raw substring counts, to enforce:

- `orchestrator/workflow/validation.py` imports neither `yaml` nor the legacy
  `WorkflowLoader`;
- `orchestrator/workflow_lisp/lowering/core.py` imports neither
  `WorkflowLoader` nor YAML parsing symbols;
- `_WorkflowMappingValidator` remains private and neither final frontend imports
  or directly uses it; `validate_workflow_mapping` is the sole public
  mapping-to-bundle entry point;
- generated-step admission is derived exactly as `.orc = true`, dedicated
  runtime-proof YAML = true, and public-callable YAML = false;
- the seven compatibility policy values are request/options-bound and no
  validator method reads shadow module or facade constants directly;
- direct `.orc` validation continues to succeed when the legacy loader is
  unavailable;
- `test_persisted_dashboard_typed_surface_does_not_use_fresh_frontends_or_source`
  loads the final state/manifest/digest-bound immutable persisted surface graph;
  traps the Workflow Lisp compiler/parser, YAML parser, macro expansion,
  elaboration, bundle construction/lowering, executable validation, runtime-plan
  derivation, and `validate_workflow_mapping`; traps `open`, `Path.read_text`,
  and `Path.read_bytes` only for the exact bound `.orc` source; and proves the
  bound manifest and `persisted_workflow_surface.json` artifact reads still occur;
  and
- YAML parser behavior continues to enter the shared mapping validator after
  parsing.

Do not prohibit unrelated YAML consumers elsewhere in the repository.

- [x] **Step 2: Collect all added or renamed tests**

```bash
pytest --collect-only -q \
  tests/test_workflow_shared_validation.py \
  tests/test_loader_validation.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_ir_lowering.py
```

Expected: exit 0 with every new test collected once.

- [x] **Step 3: Run the focused Task 3 suite**

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_workflow_shared_validation.py \
  tests/test_loader_validation.py \
  tests/test_workflow_ir_lowering.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_build_artifacts.py
```

Expected: PASS. Do not weaken a validation assertion or skip a failing fixture
to make the split land.

- [x] **Step 4: Run an import smoke**

```bash
python - <<'PY'
from orchestrator.loader import WorkflowBoundaryValidationPolicy, WorkflowLoader
from orchestrator.workflow.validation import validate_workflow_mapping
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
print("yaml/shared/orc imports ok")
PY
```

Expected: `yaml/shared/orc imports ok` and exit 0.

- [x] **Step 5: Run a fresh `.orc` end-to-end route smoke**

Run from the repository root:

```bash
python -m orchestrator run \
  tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc \
  --entry-workflow run-counter \
  --dry-run
```

Expected: exit 0 after fresh `.orc` compile, shared validation, bundle
construction, input validation, and dry-run routing. This must not use emitted
debug YAML as authority.

- [x] **Step 6: Run Task 2 regression tests without editing Task 2**

```bash
pytest -q tests/test_dashboard*.py tests/test_cli_dashboard_command.py
pytest -q tests/test_workflow_shared_validation.py \
  -k persisted_dashboard_typed_surface_does_not_use_fresh_frontends_or_source
```

Expected: PASS. Coverage must include
`orchestrator/dashboard/compiled_workflow.py`,
`tests/test_dashboard_compiled_workflow.py`, the projector/server suites, and
the CLI dashboard command. The persisted test must assert the returned value is
the immutable DTO graph bound by final state, manifest, and digest. It must
prove every fresh path is unreachable while artifact JSON reads remain live.

- [x] **Step 7: Commit the guard and smoke test changes**

```bash
set -e
git add tests/test_workflow_shared_validation.py
echo 'cached paths:'
git diff --cached --name-only
EXPECTED="tests/test_workflow_shared_validation.py"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "test: guard shared validation frontend boundary"
```

## Task 5: Broad verification, independent reviews, and roadmap closeout

**Files:**

- Modify after approval only:
  `docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md`
- Modify after approval only: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify after approval only:
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify after approval only:
  `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify after approval only: `docs/index.md`
- Modify after approval only: `docs/capability_status_matrix.md`
- Modify after approval only: `tests/test_workflow_yaml_orc_gap_list.py`
- Modify after approval only: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Run the broad suite in tmux**

Use the `tmux` skill and run from the repository root:

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: all tests pass, or any pre-existing unrelated failures are identified
with fresh reproducible baseline evidence. Do not classify a new loader,
lowering, CLI, dashboard, or validation failure as unrelated.

- [x] **Step 2: Request independent specification review**

The specification reviewer must inspect the complete diff against Stage 6 Task
3, `specs/dsl.md`, typed surface/IR authority, and the Workflow Lisp diagnostic
contract. Require an explicit `PASS` or concrete blocking findings. The review
must specifically answer:

1. Is authored YAML parsing/file recursion isolated to the legacy frontend?
2. Do YAML and `.orc` converge on exactly one mapping validation authority?
3. Are validation order, policies, errors, provenance, and IR semantics
   unchanged?
4. Does the dashboard consume only the immutable final-state/manifest/digest-
   bound Task 2 DTO, with every fresh frontend and exact `.orc` source read
   trapped while bound artifact JSON reads remain allowed?

- [x] **Step 3: Request independent code-quality review**

The code-quality reviewer must inspect module responsibility, public API
compatibility, absence of private-state reach-through, import cycles, test
quality, and failure-path clarity. Require `APPROVED` or concrete findings.

- [x] **Step 4: Fix findings and rerun affected plus focused tests**

For each accepted finding, add or strengthen a failing test first, implement the
minimal correction, rerun the narrow selector, then rerun the complete focused
Task 3 command, Task 2 regression lane, applicable route smoke, and the broad
tmux suite. Restart both independent reviews after any accepted diff change;
the final specification PASS and quality APPROVED must bind the exact post-fix
implementation tree used for closeout.

- [x] **Step 5: Update the roadmap and routing docs only after both reviews pass**

Record:

- this implementation plan's `Complete` status, exact commit and
  verification/review evidence, and closure of every Task 1-5 tracking box;
- the Stage 6 roadmap Task 3 checklist completion and exact evidence;
- the next Stage 6 selector without implying Task 7 parser removal is complete;
- YAML DSL status remains `Legacy` until the final gate; and
- Workflow Lisp remains validated through the shared mapping authority without
  claiming persisted artifacts are fresh source.

Update the two canonical selector tests with the same exclusive-current guard
used by Task 2, so stale Task 3 routing is rejected after Task 4 becomes current.
Then run the routing contract before staging:

```bash
pytest -q tests/test_workflow_yaml_orc_gap_list.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Stage exactly the eight Step-6 paths and run the Step-6 cached allowlist,
protected-path guards, Task-2 ownership guard, and cached diff-check, but do not
commit yet. Record `CLOSEOUT_REVIEW_BASE="$(git rev-parse HEAD)"` and
`CLOSEOUT_REVIEW_TREE="$(git write-tree)"`. Request final independent
specification/consistency and execution-quality reviews of that exact cached
closeout tree. Each verdict must cite both values and explicitly approve the
eight-path roadmap/evidence/selector transition. Any edit invalidates both
verdicts: restage, recompute both values, and restart both closeout reviews.

- [x] **Step 6: Commit the reviewed closeout**

```bash
set -e
: "${CLOSEOUT_REVIEW_BASE:?bind the final closeout review base}"
: "${CLOSEOUT_REVIEW_TREE:?bind the final closeout review tree}"
test "$(git rev-parse HEAD)" = "$CLOSEOUT_REVIEW_BASE"
test "$(git write-tree)" = "$CLOSEOUT_REVIEW_TREE"
git diff --quiet -- \
  docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/index.md docs/capability_status_matrix.md \
  tests/test_workflow_yaml_orc_gap_list.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
echo 'cached paths:'
git diff --cached --name-only
EXPECTED="$(printf '%s\n' \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/plans/2026-07-16-yaml-loader-shared-validation-split-plan.md \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_yaml_orc_gap_list.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL" = "$EXPECTED"
USER_PROTECTED="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
test -z "$USER_PROTECTED"
TASK2_OWNED="$(git diff --cached --name-only -- \
  docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md \
  orchestrator/dashboard/compiled_workflow.py orchestrator/dashboard/models.py \
  orchestrator/dashboard/projection.py orchestrator/dashboard/server.py \
  orchestrator/runtime_observability.py orchestrator/workflow/persisted_surface.py \
  orchestrator/workflow/surface_ast.py orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_artifacts.py tests/test_cli_dashboard_command.py \
  tests/test_dashboard_compiled_workflow.py tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_persisted_workflow_surface.py \
  tests/test_workflow_lisp_procedure_identity_retirement.py \
  tests/test_workflow_lisp_build_artifacts.py)"
test -z "$TASK2_OWNED"
git diff --cached --check
git commit -m "docs: close YAML retirement shared validation task"
```

**Completion evidence:** The reviewed plan landed at `c587995e`, the
characterization at `a375b1bd`, the atomic-sequencing amendment at `15da1291`,
the shared validator plus both frontend routes at `88102b9a`, the permanent
boundary guard at `631434c3`, and the post-split verified-drain typed-load smoke
correction at `7cc6f1d2`. Those six pre-closeout commits plus this reviewed
closeout are seven total; the characterization, implementation, guard,
smoke correction, and closeout are the five execution commits.

The final guard module collected and passed 27 tests. The complete focused
Task-3 lane passed 624 tests, the dashboard/CLI regression passed 126, and the
persisted-surface fresh-frontend/source trap passed directly. The import smoke
printed `yaml/shared/orc imports ok`, and a fresh
`pure_expr_loop_counter.orc` route reached successful dry-run validation. The
final broad rerun recorded 5137 passed and 17 skipped with only the same six
established unrelated failures. Independent specification review returned PASS
and code-quality review returned APPROVED for exact HEAD `7cc6f1d2` after the
broad-regression smoke correction and architecture-guard review fixes.

## Completion criteria

Task 3 is complete only when all of the following are true:

1. `orchestrator/loader.py` is the sole authored YAML/YML parser and recursive
   file-loader frontend.
2. YAML and Workflow Lisp both use the same in-memory normalization,
   validation, elaboration, and bundle-construction service.
3. Workflow Lisp no longer imports, constructs, or mutates `WorkflowLoader`.
4. Existing YAML public APIs and diagnostics remain compatible.
5. `_WorkflowMappingValidator` is private and request-scoped;
   `validate_workflow_mapping` is the sole public coordinator used by both
   fresh frontends.
6. Generated steps are enabled for every `.orc` mapping and only for
   dedicated-runtime-proof YAML, with the public-callable YAML rejection test
   passing.
7. All seven compatibility policies—including `STRING_CONTRACT_VERSION` and
   both regex patterns—are facade-bound, re-exported, and covered by
   monkeypatch authority tests.
8. Workflow Lisp source-map remapping, validation profiles, provenance, and
   typed bundle/IR projections remain unchanged, including errors raised during
   bundle construction.
9. Task 2's final state/manifest/digest-bound immutable persisted surface graph
   remains downstream of fresh validation; its loader performs no compiler,
   parser, elaborator, lowerer, validator, or exact `.orc` source read, and its
   complete dashboard plus CLI regression suite passes without Task 3 edits.
10. New tests collect, focused suites pass, the `.orc` dry-run smoke passes, and
   broad verification is clean or fail-closed on a demonstrably unrelated
   baseline.
11. Independent specification review returns `PASS` and independent
   code-quality review returns `APPROVED`.
12. The original reviewed plan, its reviewed atomic-sequencing amendment, four
    pre-closeout execution commits, and this reviewed closeout commit (seven
    total; five execution/closeout commits) each pass `set -e`, cached-path
    printing, exact staged allowlist equality, the literal seven-user-path
    guard, the separate Task 2-owned-file guard, and
    `git diff --cached --check` before commit creation.
13. Only then are the Stage 6 roadmap, documentation index, and capability
   matrix advanced.
