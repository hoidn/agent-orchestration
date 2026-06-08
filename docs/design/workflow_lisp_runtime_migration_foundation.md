# Workflow Lisp Runtime Migration Foundation

Status: draft design
Kind: architecture decision / migration foundation
Created: 2026-06-08
Scope: command/provider structured-output conformance, migration promotion gate
hardening, and generated state/path allocation ownership.

Authority:

- Normative command IO behavior lives in `specs/io.md`.
- Normative runtime state behavior lives in `specs/state.md`.
- This document is a migration foundation and implementation-sequencing design.
- This document does not by itself promote any `.orc` workflow to primary
  surface.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `specs/io.md`
- `specs/dsl.md`
- `specs/state.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/lisp_workflow_drafting_guide.md`

## 1. Purpose

This document records the runtime/migration foundation required before
additional Workflow Lisp promotion work depends on command-result bundles,
machine-readable parity gates, or compiler-owned generated path layout.

It is a consuming architecture. It does not replace `specs/io.md`,
`specs/dsl.md`, `specs/state.md`, or
`docs/design/workflow_lisp_state_layout.md`; it identifies the runtime, spec,
CLI, and frontend deltas needed to make those surfaces promotion-grade
together.

This document does not by itself promote any `.orc` workflow to primary. YAML
remains authoritative for a workflow family until the migration parity process
computes non-regressive parity for that family.

## 2. Executive Decision

Implement one migration foundation in three ordered tranches:

1. command/provider structured-output conformance;
2. machine-readable migration promotion gates; and
3. centralized generated state/path allocation.

The common theme is authority. Declared bundle files must be the semantic
authority for structured command and provider results rather than stdout,
prompt-obedience, or caller-selected environment values. Migration promotion
must be computed from validated evidence rather than asserted in manifests or
hand-authored reports. Compiler-generated paths must be allocated through one
layout/provenance contract rather than scattered lowering-helper conventions.

This document is not a runtime spec. Normative command IO behavior remains in
`specs/io.md`; normative run-state behavior remains in `specs/state.md`; and
executable/runtime authority remains with the validated executable workflow
path. This document defines the implementation and evidence boundary required
before further `.orc` promotion work should proceed.

## 3. Authority And Dependency Direction

### 3.1 This Document Consumes

- `specs/io.md` owns normative command IO behavior. It already states that
  command steps with `output_bundle.path` receive
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, that the runtime-owned value wins over any
  caller-provided value, that the runtime creates or validates the parent
  directory before command launch, and that the bundle file is semantic
  authority. It also owns provider structured-bundle path binding for provider
  steps with `output_bundle.path` or `variant_output.path`.
- `specs/dsl.md` owns `output_bundle`, `variant_output`, `publishes`,
  `consumes`, and version gating.
- `specs/state.md` owns runtime state authority and resume identity.
- `docs/design/workflow_lisp_state_layout.md` owns target state/path derivation
  principles.
- `docs/design/workflow_lisp_key_migration_parity_architecture.md` owns the
  existing parity evidence shape and non-regression computation.
- `docs/lisp_workflow_drafting_guide.md` owns author-facing migration
  discipline and semantic-authority rules.

### 3.2 This Document Owns

- the required runtime hardening for command structured-output authority;
- the strict-gate behavior needed before `migration-parity` is used as a
  release gate;
- the first implementation boundary for `StateLayout` / `PathAllocator`; and
- the minimum acceptance evidence before additional `.orc` primary-promotion
  work depends on these surfaces.

### 3.3 This Document Does Not Own

- full command adapter lint policy;
- full state layout path-shape migration;
- review/revise-loop semantics;
- runtime closures or dynamic procedure values; or
- semantic diffing beyond explicit parity evidence.

### 3.4 Target Dependency Directions

Command structured-output authority:

```text
command-result / command/provider step
  -> declared output_bundle contract
  -> runtime path-safety resolution
  -> runtime-owned ORCHESTRATOR_OUTPUT_BUNDLE_PATH
  -> parent directory readiness, for command steps
  -> command/provider execution
  -> declared bundle validation
  -> typed artifacts / state
```

Migration promotion gate:

```text
target manifest
  -> evidence commands / accepted waivers
  -> schema-validated generated report
  -> computed non_regressive
  -> gate evaluation / derived views
  -> promotion eligibility decision
```

Generated path allocation:

```text
semantic allocation request
  -> StateLayout
  -> PathAllocator
  -> neutral allocation metadata
  -> runtime binding + workflow_boundary_projection + source_map projection + Semantic IR projection
```

### 3.5 Prohibited Dependency Directions

Command structured-output anti-pattern:

```text
authored env var
  -> command/provider-chosen bundle path
  -> stdout JSON or arbitrary file
  -> semantic state
```

Migration promotion anti-pattern:

```text
hand-authored report
  -> asserted non_regressive=true
  -> primary surface
```

Generated path allocation anti-pattern:

```text
lowering helper A synthesizes path string
lowering helper B synthesizes hidden input
executor helper C synthesizes resume identity
source map reconstructs after the fact
```

Current checkout already contains partial implementation evidence for several
surfaces, but this document treats them as foundation-ready only after the
verification criteria below pass.

## 4. Current Status Snapshot

| Surface | Current normative status | Current implementation status | Evidence required before foundation-ready |
| --- | --- | --- | --- |
| command `output_bundle.path` env injection | Normative in `specs/io.md` | Must be verified in runtime executor | env override, parent creation/validation, missing-bundle failure tests |
| provider `output_bundle.path` / `variant_output.path` env injection | Normative in `specs/io.md` | Implemented for provider invocation env binding | env override tests, wrong-path validation failure tests |
| command `variant_output.path` | Conditional unless accepted in normative specs | Do not assume as foundation behavior | normative spec update, or `output_bundle.path` plus compiler-owned validator/projection |
| `migration-parity` report generation | Tool/evidence surface; promotion policy in migration docs | Existing tool computes `non_regressive` | schema validation, strict gate mode, stable nonzero exit tests |
| `non_regressive` | Must be tooling-computed | Existing reports compute it from evidence | target-manifest and hand-authored-report negative tests |
| StateLayout / PathAllocator | Draft design direction | Partial/scattered generated path evidence | one allocation/provenance boundary plus source-map and Semantic IR tests |
| hidden `__write_root__...` inputs | Compatibility mechanism, not public API | Existing generated/private binding mechanics | public-boundary inspection tests and runtime-contract visibility tests |

The remaining gap is coherence: these surfaces are implemented in several
places, but not yet hardened as one promotion-grade foundation.

## 5. Problem

Workflow Lisp migration confidence is limited by three related failure modes.

First, structured-output authority can drift. If authored environment variables
can override the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, a command or
provider can write semantic state somewhere other than the contract path. If a
provider sees the right path only in prompt text, useful provider output can
still land at a plausible wrong path and fail validation. If the command runtime
does not create or validate the bundle parent before launch, adapters must carry
path setup logic that should belong to the runtime contract.

Second, the migration promotion gate is currently stronger than a report but
not yet always a hard release valve. It computes `non_regressive`, but a caller
can still treat a generated report as advisory unless there is an explicit
gate mode, strict report validation, and clear distinction between
`non_regressive` and `eligible_for_primary_surface`.

Third, generated path allocation is scattered across lowering helpers, managed
write-root inputs, source-map generation, semantic IR projection, call binding,
and executor entry binding. This makes it easy to fix one path family while
leaving another family with stale resume identity, public hidden inputs, or
parallel-run collisions.

## 6. Goals

- Make declared command `output_bundle.path` files the semantic authority for
  command structured outputs.
- Make declared provider `output_bundle.path` and `variant_output.path` files
  runtime-owned structured-output targets, exposed out of band to the provider.
- Treat command `variant_output.path` as conditional until accepted by
  normative DSL/IO specs, or lower command-produced unions through
  `output_bundle.path` plus compiler-owned validator/projection.
- Ensure the runtime, not command adapters, owns structured bundle target
  injection and parent-directory readiness.
- Make migration promotion fail closed when required evidence is missing,
  stale, malformed, regressive, or ineligible.
- Keep `non_regressive` computed only by tooling.
- Keep parity reports as evidence objects; derive `primary_surface` only in the
  gate layer or derived views from computed non-regression and promotion
  eligibility.
- Introduce a single path/layout allocation boundary for compiler-generated
  write roots, bundle paths, state paths, and generated path provenance.
- Preserve existing public API behavior while hiding compiler-owned
  `__write_root__...` inputs from public entrypoints.
- Preserve source-map and Semantic IR evidence for generated paths.

## 7. Non-Goals

- Do not redesign review/revise-loop, `resume-or-start`, generic effectful
  composition, or adapter lint policy in this document.
- Do not ban command steps.
- Do not replace YAML primaries based on this design alone.
- Do not introduce a generic semantic diff engine for migration parity.
- Do not rewrite all existing generated paths in one change.
- Do not make reports, stdout, pointer files, or debug YAML semantic authority.

## 8. Architecture Invariants

- Declared command bundle files are semantic authority for structured command
  results; stdout is not.
- Runtime-owned environment values cannot be overridden by authored
  environment values.
- `non_regressive` is computed, never authored.
- Reports are evidence objects, not workflow semantic authority; only
  schema-valid, gate-accepted reports may contribute to promotion decisions.
- Hidden `__write_root__...` inputs are not public entrypoint inputs.
- Generated private paths are source-mapped and represented in Semantic IR.
- Path allocation failures are diagnostics, not silent fallback to
  helper-generated strings.
- Existing resume identity is preserved unless an explicit compatibility
  boundary says otherwise.

## 9. Tranche 1: Structured-Output Path Authority

### 9.1 Contract

This tranche does not introduce a new semantic rule for `output_bundle.path`.
It makes the runtime, tests, and migration evidence conform to the
already-normative `specs/io.md` structured-bundle contract.

For command steps with `output_bundle.path`, implementation evidence must prove
that the runtime:

1. resolves the path through the existing output-contract path-safety logic;
2. sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` unconditionally to that resolved
   workspace-relative target;
3. overrides any authored `env.ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
4. creates or validates the bundle parent directory before command launch;
5. validates the bundle file after successful command exit; and
6. fails the step as an output-contract failure if exit is `0` but the bundle is
   missing or invalid.

Stdout JSON remains debug/captured output unless the step explicitly uses
`output_capture: json`. It must not become structured command state when an
`output_bundle` contract is present.

For provider steps with `output_bundle.path` or `variant_output.path`,
implementation evidence must prove that the runtime:

1. resolves the path before provider invocation;
2. exposes the resolved workspace-relative target as
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
3. overrides any authored or provider-template value for that environment name;
4. renders prompt contract text that treats the runtime-owned binding as the
   authoritative write target; and
5. fails the step as an output-contract failure if the provider writes the
   bundle anywhere else.

For command-produced union results, this tranche is conditional:

- use `variant_output.path` only after that surface is accepted by the
  normative DSL/IO specs; or
- lower through an authoritative `output_bundle.path` containing the raw
  discriminant and payload, followed by a compiler-owned validator/projection
  step that establishes variant-proof-compatible typed refs.

### 9.2 Tasks

- Resolve the declared bundle path through existing output-contract path-safety
  logic.
- Set `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` after authored env merge, so the
  runtime value wins.
- Create or validate the parent directory before command launch.
- Validate the declared bundle after successful command exit.
- Preserve nonzero command exit as primary failure.
- Treat stdout JSON as debug/capture unless the step explicitly uses
  `output_capture: json`.
- Add or update normative spec text for every structured command-bundle surface
  covered by this rule.
- Pass runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to provider steps with
  `output_bundle.path` or `variant_output.path`.
- Keep prompt text as schema/path guidance, not the only path authority.

### 9.3 Acceptance

- Authored env override cannot redirect structured output.
- Provider authored env override cannot redirect structured output.
- Runtime creates the command bundle parent before launch.
- Exit `0` plus missing bundle fails as output-contract failure.
- Exit `0` plus invalid bundle fails as output-contract failure.
- Nonzero command exit remains primary.
- Stdout JSON does not satisfy a missing bundle.
- Provider wrong-path writes fail as missing bundle output-contract failures.
- Covered command `variant_output` behavior is either normatively specified or
  explicitly deferred.

### 9.4 Normative Spec Deltas

`output_bundle.path` behavior is already normative in `specs/io.md`.
Provider `output_bundle.path` and `variant_output.path` runtime-owned path
binding is also normative in `specs/io.md`.

`variant_output.path` remains conditional in this document. If command-produced
`variant_output` with an explicit bundle path is intended to be a promotion
foundation surface, update `specs/io.md` and `specs/dsl.md` so that it uses the
same runtime-owned environment, parent-readiness, path-safety, and post-exit
validation contract as `output_bundle.path`.

## 10. Tranche 2: Migration Promotion Gate Hardening

### 10.1 Contract

Keep the existing manifest-driven `migration-parity` model, but harden it into
a release gate.

The promotion command must define strict gate modes with stable exit semantics.
At minimum, `--require-non-regressive` exits nonzero when any selected target
lacks valid, complete, current, computed non-regression evidence.

Gate modes:

`--require-non-regressive`

- selected targets must have `report_valid=true`;
- selected targets must have `evidence_complete=true`;
- selected targets must have computed `non_regressive=true`;
- ineligible targets may pass this gate but must not become primary.

`--require-promotable`

- selected targets must satisfy all `--require-non-regressive` requirements;
- selected targets must also have `eligible_for_primary_surface=true`;
- aggregate promotion decisions may derive `primary_surface` only under this
  mode.

Decision table:

| `report_valid` | `evidence_complete` | `non_regressive` | `eligible_for_primary_surface` | `--require-non-regressive` | `--require-promotable` | gate-layer `primary_surface` |
| --- | --- | --- | --- | --- | --- | --- |
| false | any | any | any | fail | fail | not derived |
| true | false | any | any | fail | fail | not derived |
| true | true | false | any | fail | fail | not derived |
| true | true | true | false | pass | fail | `yaml` |
| true | true | true | true | pass | pass | `orc` |

The command must validate both freshly generated reports and reused existing
reports against the same schema/version contract before including them in an
aggregate index. Existing reports are not authority merely because they are
JSON objects.

`non_regressive` remains computed from evidence. Target manifests and hand
authored reports must not provide it. Per-target parity reports stay
evidence-only artifacts. If the CLI needs a machine-readable strict-gate
result beyond markdown/index rendering, it should emit a separate versioned
gate-evaluation object rather than turning the report itself into promotion
policy authority. Gate-layer or derived-view `primary_surface` is derived from:

```text
computed non_regressive
AND promotion_eligibility.eligible_for_primary_surface
```

When `non_regressive=true` but `eligible_for_primary_surface=false`, reports
and derived gate views must make the distinction explicit: the candidate may be
non-regressive against recorded evidence but still not promotable.

### 10.2 Required Report Fields

The strict gate report schema must include at least:

- `schema_version`;
- `workflow_family`;
- `candidate`;
- `yaml_primary`;
- `target_identity`;
- `evidence`;
- `evidence_freshness`;
- `promotion_eligibility`;
- tooling-computed `non_regressive`;
- `generated_at`;
- `generated_by`;
- `tool_version`; and
- optional accepted waivers with owner and expiry.

`target_identity` must contain the exact identity material strict reuse checks
will validate:

- `targets_schema_version`;
- `target_manifest_path`;
- `target_manifest_sha256`;
- `target_index` or another stable selected-target key within that manifest;
- `workflow_family`;
- `candidate_path`;
- `candidate_sha256`;
- `yaml_primary_path`; and
- `entry_workflow`.

`evidence_freshness` must carry the freshness inputs strict gating uses:

- `generated_at`;
- `compile_manifest_path`, when compile evidence produced one;
- `compile_manifest_sha256`, when compile evidence produced one;
- `compiled_workflow_checksum`, when compile/run evidence exposes it;
- `required_artifact_paths` for emitted required compile artifacts; and
- per-role evidence references needed to prove the report still corresponds to
  the selected target and current evidence set.

`report_valid` and `evidence_complete` are gate-derived checks, not authored
fields:

- `report_valid=true` only when the report schema version matches, all required
  fields above are present, authored computed fields are absent, and
  `target_identity` matches the selected manifest row exactly.
- `evidence_complete=true` only when required evidence roles are present,
  required compile artifacts are present, waivers are still valid, and
  `evidence_freshness` proves the report still matches the selected manifest,
  compile manifest, and candidate workflow checksum.

`primary_surface` is a gate-layer or derived-view delta in this document. It
must be derived by tooling from computed non-regression and eligibility; it is
not authored in the target manifest and it is not a required parity-report
field.

### 10.3 Acceptance

- Target manifests cannot provide `non_regressive`.
- Hand-authored reports cannot provide authoritative `non_regressive`.
- Reused reports validate schema/version, selected target identity,
  manifest/checksum freshness, and required evidence references before
  contributing to an aggregate gate.
- `--require-non-regressive` exits nonzero when any selected target lacks
  valid, complete, current, computed non-regression evidence.
- `--require-promotable` exits nonzero unless selected targets are both
  non-regressive and eligible for primary surface.
- Non-regressive but ineligible candidates do not become primary, and
  `primary_surface` remains a gate/view derivation rather than a report-owned
  authority field.

## 11. Tranche 3: StateLayout / PathAllocator Foundation

### 11.1 Contract

Introduce a concrete `StateLayout` / `PathAllocator` boundary without forcing a
large path migration in the first patch.

The first implementation should centralize allocation and provenance for:

- generated command/provider result bundle write roots;
- generated internal inputs such as `__write_root__...`;
- reusable call write-root bindings;
- entrypoint runtime-owned managed write roots;
- the allocation metadata consumed by source-map projection; and
- the allocation metadata consumed by Semantic IR state-layout projection.

The initial allocator should preserve current concrete path shapes where
practical; the first migration is ownership/provenance centralization, not a
path-shape migration. The important first step is that every generated path
family goes through one allocation interface and one provenance interface.

After that interface is stable, path families can move toward the
`workflow_lisp_state_layout.md` target: private generated write paths are
run-isolated by default, resume reconstructs the same private path for the
same run/call-frame/loop identity, and authored stable workspace artifacts
remain explicit.

### 11.2 Tasks

- Add a concrete allocation request shape with stable semantic identity,
  provenance, privacy, resume scope, and path-safety policy.
- Route command-result bundle allocation through the new boundary.
- Route reusable-call write-root allocation through the new boundary.
- Keep downstream projection owners explicit: runtime/executable binding owns
  generated hidden-input projection, `workflow_boundary_projection` owns public
  boundary explanation, SourceMap owns traceability entries, and Semantic IR
  owns typed state-layout entries derived from allocation metadata.
- Keep compiler-owned generated write roots hidden from public workflow
  signatures.
- Preserve current concrete path shapes where practical.

### 11.3 Acceptance

- Generated result bundle paths route through the allocator.
- Generated internal inputs remain hidden from public inputs and present in
  executable/runtime contracts where required.
- Source maps and Semantic IR contain matching generated path/layout entries.
- Repeated calls, loop iterations, and match arms produce collision-proof
  allocations.
- Resume reconstructs the same allocation identity for the same run and
  call-frame/loop identity.
- Formatting-only source-span changes do not change stable allocation identity.

### 11.4 StateLayout Non-Goals

`StateLayout` does not own arbitrary child-process filesystem effects, provider
report content, semantic artifact values, or queue movement semantics.

## 12. Design Details

### Command Bundle Contract

The command execution path has three phases:

```text
resolve contract path
  -> prepare runtime-owned environment and parent directory
  -> run command
  -> validate declared bundle
  -> publish typed artifacts
```

The path passed through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the same path used
for post-exit validation. A command cannot select a different semantic target
by writing a different env value or by printing JSON to stdout.

Required failure behavior:

| Case | Result |
| --- | --- |
| Authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` | Runtime value wins |
| Bundle path unsafe | Step fails before command launch |
| Parent cannot be created/validated | Step fails before command launch |
| Command exits nonzero | Command failure remains primary |
| Command exits `0`, bundle missing | Output-contract failure |
| Command exits `0`, bundle invalid | Output-contract failure |
| Stdout contains valid JSON, bundle missing | Output-contract failure |

### Promotion Gate Contract

The parity report is a machine-readable evidence object, not a checklist
summary and not workflow semantic authority. A report may contribute to
promotion only when:

- its schema/version validates;
- it was generated from the selected target manifest;
- required evidence references are present and current;
- computed fields such as `non_regressive` are produced by tooling; and
- the aggregate gate derives promotion decisions from those computed fields.

A report has these evidence layers:

```text
target manifest
  -> evidence commands and accepted waivers
  -> generated report
  -> computed non_regressive
  -> derived aggregate index / gate evaluation
  -> optional primary-surface view or decision
```

Required evidence roles remain those already represented by the migration
parity implementation and architecture:

- compile;
- shared validation;
- dry-run or smoke/integration;
- baseline characterization;
- output contract parity;
- terminal state parity;
- artifact parity;
- resume/reuse parity;
- generated-source provenance; and
- deprecated-mechanic replacement or accepted waiver.

The gate must distinguish:

- `report_valid`: the report schema and identity contract are valid for the
  selected target;
- `evidence_complete`: required evidence exists and is current enough for that
  selected target and candidate checksum;
- `non_regressive`: evidence proves no required parity regression;
- `eligible_for_primary_surface`: policy allows promotion; and
- `primary_surface`: a gate/view projection selected from those computed
  inputs, not a report-owned semantic field.

### StateLayout / PathAllocator Contract

`StateLayout` owns semantic allocation requests. `PathAllocator` owns concrete
path names for those requests. Together they return neutral allocation
metadata. Adjacent layers own their own projections over that metadata.

`source_span` is provenance, not identity. Stable allocation identity must be
derived from semantic ownership:

- workflow/module identity;
- generated role;
- authored semantic target;
- call-frame identity when applicable;
- loop identity and iteration/visit scope when applicable; and
- lowering schema version when path reconstruction semantics change.

Formatting-only source edits must not change resume identity unless the
semantic owner changes.

Illustrative request shape:

```text
layout.allocate(
  owner="workflow_lisp",
  workflow_id="design-plan-stack::review-plan",
  source_span=...,  # provenance only
  semantic_role="command_result_bundle",
  stable_identity="review-plan/run-review/result",
  privacy="private_generated",
  resume_scope="call_frame",
)
```

Initial semantic roles should use an explicit closed vocabulary rather than
free-form strings:

- `command_result_bundle`;
- `provider_result_bundle`;
- `variant_projection_bundle`;
- `reusable_call_write_root`;
- `entrypoint_managed_write_root`;
- `generated_internal_input_binding`; and
- `compatibility_pointer_view`.

Initial privacy classes:

- `public_authored`;
- `public_artifact`;
- `private_generated`;
- `compatibility_view`; and
- `runtime_sidecar`.

Initial resume scopes:

- `none`;
- `run`;
- `call_frame`;
- `loop_frame`;
- `loop_iteration`; and
- `step_visit`.

The returned allocation contains:

```text
generated_input_name, when needed
concrete_path_template
semantic_identity
privacy
path_safety_policy
resume_identity
projection_hints
```

`StateLayout` does not decide semantic workflow outcomes. It decides where
compiler/runtime-owned state and generated bundle files live, how they are
hidden from public inputs, and how they are explained.

Projection ownership stays separate:

- runtime/executable lowering consumes allocation metadata to bind hidden
  runtime inputs and concrete bundle/write-root paths;
- `workflow_boundary_projection` consumes allocation metadata to explain hidden
  generated inputs without turning them into public authored inputs;
- `source_map.json` consumes allocation metadata plus source provenance to
  emit traceability entries; and
- Semantic IR consumes allocation metadata to emit `SemanticStateLayoutEntry`
  records and related bridges.

## 13. Contracts And Interfaces

### Runtime

- `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is runtime-owned for structured command
  bundle steps.
- Runtime creates or validates the bundle parent before command launch.
- Runtime validates output bundles after successful command exit.
- Runtime entry binding for compiler-managed write roots remains hidden from
  public workflow inputs.

### CLI

- `migration-parity` remains the machine-readable promotion evidence command.
- Strict gate modes exit nonzero according to the explicit
  `--require-non-regressive` and `--require-promotable` semantics above.
- CLI docs/specs must describe the command once it is relied on as a release
  gate.

### Generated Artifacts

- `source_map.json` records generated paths and generated internal inputs from
  allocation metadata plus source provenance.
- Semantic IR records corresponding state-layout entries derived from the same
  allocation metadata.
- Validated parity JSON reports are machine-readable gate evidence.
- Parity JSON reports are not workflow semantic authority and do not redefine
  runtime behavior.
- Markdown parity reports, indexes, and any gate-evaluation summaries are
  views unless a separate explicit contract promotes one of them.

## 14. Dependencies And Sequencing

Tranche 1 should land first because it proves runtime conformance to the
normative command structured-bundle contract and strengthens every
command-result migration.

Tranche 2 can land next because the command exists; hardening it does not
require StateLayout to be complete. It should include any spec/CLI doc updates
needed to treat the command as a gate.

Tranche 3 should follow as a staged refactor. It has broader blast radius and
should start by routing existing allocation families through a shared boundary
without changing all concrete paths at once.

Work that can proceed in parallel:

- report-schema validation for existing parity reports;
- CLI spec/doc alignment for `migration-parity`;
- focused tests for command bundle env precedence; and
- inventory of generated path families that currently bypass a shared layout
  interface.

Work that should wait for this foundation:

- treating additional `.orc` candidates as primary YAML replacements;
- broad strict adapter-lint enforcement; and
- large-scale generated path shape changes.

## 15. Work Blocked Until This Foundation Lands

- Additional `.orc` candidates treated as primary YAML replacements.
- Broad strict adapter-lint enforcement.
- Generated path-shape migration.
- Any feature that relies on compiler-owned write roots being hidden from
  public entrypoints.
- Any promotion report being used as a release gate without schema validation
  and strict gate semantics.

## 16. Evidence And Implementation Boundaries

### 16.1 Required Evidence

Implementation follows this design only if the default runtime command path
sets structured bundle env values, creates/validates parents, and validates the
declared bundle. Adapter-side `mkdir` calls and tests that manually write bundle
files are not sufficient evidence.

Migration promotion follows this design only if the CLI can fail as a gate.
Generated reports that compute `non_regressive` but never affect exit behavior
are useful evidence, but not a release valve.

State layout follows this design only if generated path families route through
one allocation/provenance boundary. Existing helpers that merely keep producing
`__write_root__...` names are compatibility mechanics, not the target
architecture.

### 16.2 Prohibited Evidence

The following do not prove this foundation:

- a command adapter that creates its own bundle parent;
- a test that writes the bundle manually instead of using the runtime command
  path;
- a parity JSON file with hand-authored `non_regressive`;
- a report accepted without schema/version validation;
- a reused report accepted without matching manifest hash or candidate/workflow
  checksum evidence;
- a generated path visible only in debug YAML but absent from source maps or
  Semantic IR; or
- an implementation that preserves `__write_root__...` public inputs and calls
  that "compatibility."

## 17. Compatibility And Migration

Existing YAML and `.orc` workflows remain valid.

Command steps that already honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` continue to
work. Command steps that intentionally override that variable become invalid
for structured bundle contracts because the runtime-owned value wins.

Command adapters remain legitimate when they invoke external tools or certified
adapters with declared inputs, outputs, effects, fixtures, and source maps.
Hidden semantic glue in inline Python/shell, report parsing, pointer-as-state,
or ad hoc JSON rewrites remains migration debt under
`docs/design/workflow_command_adapter_contract.md`.

Existing parity reports remain readable, but strict gate mode may reject old
reports that lack schema/version fields, target-identity fingerprints, or
required freshness evidence. That is expected: old evidence can remain
historical, but it should not be promotion gate evidence.

StateLayout migration is incremental. The first implementation should preserve
current concrete paths where practical and move ownership behind an allocator
facade before changing path shapes.

## 18. Verification Strategy

Command structured-output tests:

- authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to an absolute path:
  runtime value wins, no escape occurs;
- authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to a different
  workspace-relative path: runtime value wins;
- runtime creates the bundle parent before command launch;
- bundle parent path containing `..` fails path-safety validation before launch;
- symlink-escape bundle parent fails path-safety validation according to
  security/path rules;
- `output_capture: json` plus `output_bundle.path`: stdout JSON is
  captured/debug only and the bundle remains semantic authority;
- stdout JSON without bundle fails as missing bundle;
- nonzero command exit remains primary over bundle validation;
- command exits zero and writes valid stdout JSON but no bundle:
  output-contract failure;
- command under reusable `call` preserves workspace-relative authored contract
  paths while runtime-owned identities remain namespaced;
- `variant_output.path` is tested only after normative spec support exists, or
  the `output_bundle.path` plus validator/projection route is tested instead.

Migration gate tests:

- target manifest rejects authored `non_regressive`;
- hand-authored parity report `non_regressive` is rejected or ignored in favor
  of a computed value;
- strict reuse checks require target manifest hash and candidate/workflow
  checksum identity material in the report;
- reused report generated from a different target manifest hash is rejected;
- reused report generated from a different workflow checksum is rejected;
- strict gate exits nonzero for regressive eligible targets;
- strict gate exits zero for non-regressive eligible targets;
- non-regressive but ineligible target does not become primary;
- strict promotable mode exits nonzero for an ineligible target;
- markdown-only report never contributes to promotion;
- reused existing reports are schema/version validated;
- report validity and evidence completeness are derived from the report's
  identity/freshness fields rather than authored booleans;
- expired waivers, missing required evidence, missing required artifacts, and
  hidden managed write-root inputs force non-regression false;
- aggregate index or gate-evaluation view derives `primary_surface` from
  computed non-regression and promotion eligibility.

StateLayout tests:

- generated result bundle paths route through the allocator;
- generated internal inputs remain hidden from public inputs and present in
  runtime contracts;
- source maps and Semantic IR contain matching generated path/layout entries;
- repeated calls, loop iterations, and match arms produce collision-proof
  allocations;
- resume reconstructs the same allocation identity for the same run and
  call-frame/loop identity;
- formatting-only source-span changes do not change stable allocation identity;
- semantic target changes do change allocation identity;
- private generated path differs across independent runs when run-isolation is
  required;
- same procedure called from two call sites does not collide;
- absolute paths and `..` escapes are rejected.

## 19. Declarative Acceptance Scenarios

### Command Bundle Authority

Initial state: a workflow has a command step with an `output_bundle.path` and an
authored env value for `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

Entrypoint: `python -m orchestrator run ...`

Expected result: runtime overrides the authored env value, the command sees the
contract path, the bundle validates, and the step artifacts come from the
bundle file.

Forbidden result: stdout JSON or the authored env path becomes semantic state.

### Promotion Gate

Initial state: a parity target has compile and dry-run evidence but missing
resume parity.

Entrypoint:

```bash
python -m orchestrator migration-parity \
  workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --require-non-regressive
```

Expected result: the report is generated, `non_regressive=false`, and the CLI
exits nonzero for an eligible promotion target.

Forbidden result: the target appears as primary `.orc` because it compiled.

### Generated Path Allocation

Initial state: a `.orc` workflow calls the same reusable procedure twice inside
a loop, and each call lowers to a command-result bundle.

Entrypoint: compile, shared validation, and dry-run/run.

Expected result: each generated bundle path has one allocator identity, one
hidden runtime input when needed, matching source-map and Semantic IR entries,
and no collision across calls or loop iterations.

Forbidden result: generated path strings are synthesized independently by
lowering helpers with no common provenance.

## 20. Success Criteria

- Command structured-output tests pass for env precedence, parent creation, and
  missing-bundle fail-closed behavior.
- `migration-parity` has a strict gate mode with focused CLI tests.
- Existing parity reports and indexes are still generated, but reused reports
  are schema/version checked and strict reuse validates manifest/checksum
  identity material.
- A `StateLayout` / `PathAllocator` implementation boundary exists and at
  least command-result and reusable-call write-root allocation route through it.
- Source-map and Semantic IR tests prove generated path provenance survives.
- No public workflow entrypoint exposes compiler-owned `__write_root__...`
  inputs.
- `git diff --check` passes.
