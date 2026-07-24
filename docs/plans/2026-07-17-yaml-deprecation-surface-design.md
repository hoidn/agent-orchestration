# YAML Deprecation Surface Design

**Status:** Retired historical Stage 6 Task-4 design. The advisory behavior
landed at `3871099b`, `4e0a700d`, `30b1bd48`, and `ee0e520a`; author routing
landed at `b329c4b3`. Final Task-4 implementation review returned specification
PASS and quality APPROVED for exact HEAD
`b329c4b396e095d195119996838ea8782e6d1401` and tree
`00b1a2d17c6118695c747b7c3001817e4dd4977d`. Task 7 subsequently removed the
advisory boundary with the user-facing YAML loader and project PyYAML
dependency.

**Owner:** `docs/plans/2026-07-07-yaml-retirement-program.md`, Task 4.

## Supersession

Task 7 now rejects fresh non-`.orc` execution before state creation, rejects
nonterminal or restarted legacy YAML/YML resume without mutation, and preserves
completed legacy runs through state-only resume/report/dashboard paths. There
is no current `WorkflowLoader` or YAML deprecation event. The authored workflow
YAML/YML estate is empty, the focused Task-7 gate passed 1,020 tests with 5
skipped, and a production `.orc` dry-run smoke left the run-directory count
unchanged. The final scoped broad comparison introduced zero new failures
against the owner-adopted baseline, and ordered independent review returned
specification PASS and quality APPROVED at `d9baa120`. Stage 6 is complete.

The sections below preserve the implemented Task-4 warning contract at its
reviewed commit. They are provenance, not current runtime or authoring guidance.

## Historical goal

Make YAML/YML visibly legacy without rejecting it at the Task-4 boundary: every
explicit fresh authored-YAML root load emitted one structured advisory warning,
persisted-run compatibility reads remained quiet, and new-author documentation
and template routing led to Workflow Lisp `.orc`.

Task 7 subsequently implemented fresh-YAML rejection, parser removal, and
removal of the project PyYAML dependency.

## Governing contracts

- `docs/plans/2026-07-07-yaml-retirement-program.md` defined Task 4 and kept
  YAML `Legacy` at that historical gate; it records completed Task 7 and
  Stage 6.
- `specs/dsl.md` owned the normative advisory-warning behavior while the
  Task-4 frontend existed.
- `docs/capability_status_matrix.md` owns current copy-safety status and records
  the advisory surface as retired.
- `docs/lisp_workflow_drafting_guide.md` is the preferred new-author route.
- `docs/workflow_drafting_guide.md` remains a compatibility-maintenance guide
  for existing YAML.
- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json` and
  `docs/workflow_yaml_estate_triage.md` freeze the YAML estate. Task 4 must not
  edit a queued YAML/YML source merely to make it look deprecated.

## Historical decision

### Historical warning boundary

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

## Historical error handling and invariants

- Warning emission occurs before parsing and cannot make a valid load invalid.
- Non-YAML suffixes emit no YAML deprecation event.
- Recursive imports do not multiply events.
- Suppression is explicit at persisted consumers; it is not inferred from
  filesystem layout or run state.
- Message wording is non-contractual. Event identity and routing are the
  behavioral contract.
- No queued workflow source, prompt, or protected user-owned path is modified.
- At Task-4 closeout, YAML stayed executable and `Legacy`; that invariant was
  intentionally superseded by Task 7.

## Historical Task-4 verification

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

## Retired future-cost note

The boolean policy was intentionally less expressive than a general
load-purpose enum. Task 7 removed the switch and its loader boundary, so the
previously described pre-Task-7 extension cost no longer applies. Any future
authored frontend requires its own accepted loading and observability contract;
this retired design is not a reusable loader API.
