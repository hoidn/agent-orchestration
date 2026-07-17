# YAML Deprecation Surface Design

**Status:** Accepted for Stage 6 Task 4 execution under the YAML retirement
roadmap and the owner's standing instruction to continue without an additional
approval stop.

**Owner:** `docs/plans/2026-07-07-yaml-retirement-program.md`, Task 4.

## Goal

Make YAML/YML visibly legacy without rejecting it: every explicit fresh
authored-YAML root load emits one structured advisory warning, persisted-run
compatibility reads remain quiet, and new-author documentation and template
routing lead to Workflow Lisp `.orc`.

Task 7 still owns fresh-YAML rejection, parser removal, and the final removal of
the PyYAML dependency.

## Governing contracts

- `docs/plans/2026-07-07-yaml-retirement-program.md` defines Task 4 and keeps
  YAML `Legacy` until the final gate.
- `specs/dsl.md` owns the normative advisory-warning behavior.
- `docs/capability_status_matrix.md` owns copy-safety status.
- `docs/lisp_workflow_drafting_guide.md` is the preferred new-author route.
- `docs/workflow_drafting_guide.md` remains a compatibility-maintenance guide
  for existing YAML.
- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json` and
  `docs/workflow_yaml_estate_triage.md` freeze the YAML estate. Task 4 must not
  edit a queued YAML/YML source merely to make it look deprecated.

## Decision

### Warning boundary

`WorkflowLoader.load_bundle()` is the one deprecation-event boundary. Its
constructor gains a keyword-only `emit_yaml_deprecation_warning: bool = True`
policy. On every public root-load call whose requested path has a case-insensitive
`.yaml` or `.yml` suffix, the loader emits one WARNING record before parsing.

The record contract is exact:

- logger: `orchestrator.loader.yaml_deprecation`;
- level: `WARNING`;
- `workflow_deprecation_code`: `workflow_yaml_authoring_deprecated`;
- `workflow_deprecation_path`: the string form of
  `Path(requested_path).resolve(strict=False)`; and
- `workflow_deprecation_format`: `yaml`.

Tests assert the logger, count, level, and structured fields. They do not assert
literal warning phrasing.

`load()` continues to delegate to `load_bundle()`, so it emits no second event.
Private `_load_workflow()` recursion never emits, so a root and all its recursive
imports produce exactly one event. Reusing a loader for two explicit public
root loads emits two events. Malformed YAML still emits because deprecation is a
property of the attempted authored surface, not successful validation.

### Fresh and persisted consumers

Fresh paths keep the default enabled:

- `orchestrator run` for YAML/YML;
- direct public `WorkflowLoader` use; and
- explicit YAML bundle loads requested by a fresh Workflow Lisp build.

Persisted compatibility consumers opt out explicitly:

- `orchestrator resume` when reopening a persisted YAML/YML workflow;
- `orchestrator report`; and
- dashboard legacy projection.

Persisted `.orc` resume is also covered. `FrontendBuildRequest` gains the same
keyword policy with a default of `True`. `build_frontend_bundle()` forwards it
only to the `WorkflowLoader` used for explicit legacy YAML bundle dependencies.
Resume passes `False` when it rebuilds a persisted `.orc` source. This policy is
observability-only: it is excluded from source/build fingerprints, manifests,
bundle identity, semantic/executable IR, and persisted state. A fresh build with
N explicit YAML manifest roots emits N events (one per public dependency-root
load); recursive imports below each root remain silent. A persisted `.orc`
resume over the same manifest emits none.

The opt-out changes only event emission. It does not change parsing, validation,
diagnostics, execution, resume state, exit codes, or bundle identity.

### Author and template routing

The default authoring route changes to `.orc` in:

- `README.md`;
- `docs/index.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `docs/workflow_drafting_guide.md`;
- `workflows/README.md`; and
- `workflows/templates/README.md`.

The normative warning contract is added to `specs/dsl.md`. The accepted design
is linked from the Task-4 roadmap owner and `docs/index.md`, and the YAML row in
`docs/capability_status_matrix.md` records the design and implemented evidence.

The YAML guide remains available for existing compatibility files. The frozen
`workflows/templates/autonomous_drain_with_work_instructions.v214.yaml` file is
not edited, renamed, or copied: its documentation marks it compatibility-only
and routes new templates to registry-approved `.orc` examples. Task 4 creates no
third migration port.

## Alternatives considered

### CLI-only warning

Rejected because it misses direct library callers and YAML bundle loads that are
explicit dependencies of fresh `.orc` compilation. It also duplicates frontend
classification across commands.

### Mandatory per-call policy enum

Rejected as unnecessary machinery for a frontend scheduled for deletion. An
enum would better support several long-lived load purposes, but Task 4 needs
only fresh-default versus persisted-compatibility suppression. The loader
constructor keeps the boolean keyword-only; the build-request field propagates
that warning-only policy only to explicit legacy YAML dependency loads and is
excluded from semantic identity and fingerprints.

### `warnings.warn`

Rejected because ordinary `DeprecationWarning` filtering hides events and
call-site deduplication does not express once per explicit fresh root load. A
structured log record is visible and deterministic.

## Error handling and invariants

- Warning emission occurs before parsing and cannot make a valid load invalid.
- Non-YAML suffixes emit no YAML deprecation event.
- Recursive imports do not multiply events.
- Suppression is explicit at persisted consumers; it is not inferred from
  filesystem layout or run state.
- Message wording is non-contractual. Event identity and routing are the
  behavioral contract.
- No queued workflow source, prompt, or protected user-owned path is modified.
- YAML stays executable and `Legacy`; Task 7 remains incomplete.

## Verification

Behavioral tests must cover both directions:

1. `.yaml` and `.yml` fresh roots emit exactly one structured event;
2. `load()` does not double-emit;
3. recursive imports remain one event tied to the root;
4. malformed YAML still emits;
5. explicit suppression and non-YAML suffixes emit none;
6. two explicit fresh root loads emit two;
7. persisted resume, report, and dashboard reads emit none;
8. persisted `.orc` resume with YAML bundle dependencies also emits none;
9. fresh CLI YAML run and fresh `.orc` YAML-bundle dependency paths emit one
   event per explicit YAML dependency root;
10. `.orc` without a YAML bundle dependency emits none; and
11. author/template routing selects `.orc` while retaining the YAML guide only
    as compatibility documentation.

After narrow tests, run the affected CLI, resume, report, dashboard, loader,
Workflow Lisp build, routing, and broad suites. Obtain independent specification
and code-quality review before advancing the Stage 6 selector to Task 5.

## Future cost

The boolean policy is intentionally less expressive than a general load-purpose
enum. If another authored frontend needs more than fresh-versus-persisted
warning policy before Task 7, the facade/build request will require an explicit
policy type. Keeping the switch keyword-only, observability-only, and out of
fingerprints confines that future change.
