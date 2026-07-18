# Workflow Lisp Provider Prompt Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by task.
> Use `superpowers:test-driven-development` for every production change. Every
> task requires a specification-compliance review followed by an
> implementation-quality review before the next task starts. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Add the approved generic, typed
`provider-result :prompt-dependencies` surface, one bounded per-attempt dependency
snapshot/render boundary shared by ordinary and adjudicated provider execution,
and crash-durable content-free evidence without changing keyword-free `.orc`
artifacts or making evidence resume authority.

**Architecture:** Keep authored exact-path operands in the Workflow Lisp AST and
WCC, then pass the compiler-produced `CompilerPromptDependencyContract` through a
typed side table keyed by stable provider step ID rather than smuggling an origin
marker through the YAML-shaped mapping. Core, executable, semantic, source-map,
and persisted surfaces retain their owned views while `runtime_plan` remains
topology-only. At runtime, one shared snapshot owner resolves, reads, normalizes,
de-duplicates, orders, and renders an immutable
snapshot once per provider attempt; a root-owned durable allocator and immutable
publication protocol give Workflow Lisp attempts evidence identities but never
participate in provider selection, checkpoint reuse, or resume decisions.

**Tech Stack:** Python 3.11+, frozen dataclasses and enums, Workflow Lisp
WCC/schema 2, shared typed workflow IR, ordinary POSIX filesystem operations,
`fcntl.flock`, canonical JSON/SHA-256, pytest/xdist, multiprocessing,
and tmux.

**Approved design:**
`docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md`
at commit `267925f4`, exact SHA-256
`293f366020b57d87dfb7eab988247826179f15826c9f61b94cf4f8faf07a7921`.

**Execution status:** Tasks 1-3 are committed through reconstructed `044b3278`:
the immutable
preimplementation baseline, typed frontend, classic/WCC owner-side-table
projection, canonical compiler contract, and source-map lineage all passed their
ordered gates. Task 4 functional typed-IR transport passed both ordered reviews
and committed at reconstructed `6fa32d0d`. Task 5 immutable snapshot rendering, exact byte
budgeting, stable successful-YAML compatibility, and typed exact resolution passed
its replacement specification-compliance and implementation-quality reviews and
committed at reconstructed `a1fe6cde`.
Task 6 is wholly skipped under the 2026-07-18 user scope override and makes no
platform-preflight or descriptor-read claim. Task 7's functional durability,
aggregate-owner, closed-scope, allocator, event, and concurrency implementation
passed both ordered reviews and committed at reconstructed `8e4645e5`. Task 8's functional
evidence implementation is reconstructed at `fff1b1fc`; retrospective review of
its pre-rewrite object `42e0ebc3` exposed
an ancestor-directory durability defect, which the generic repair committed at
reconstructed `1f424cc9` closed under fresh ordered reviews. Task 9's per-attempt composition
is reconstructed at `d9fc6b9f`; retrospective review of pre-rewrite `42839223`
exposed a completion-failure-domain
defect, which the generic repair reconstructed at `a1385290` closed under fresh
ordered reviews. Task 10's functional crash/resume and real `.orc` coverage
is reconstructed at `6fa662fd` and its pre-rewrite object `be8247ea` passed
retrospective exact-object reviews. The Task 11 CLI regression repair is
reconstructed at `95dd3f75`; the Task 8 and Task 9 retrospective
repairs followed, and the strict long-duration broad-summary parser repair passed
both ordered reviews and is reconstructed at `cb8e2d89`. The allocator-repair and
Git-native trailer-validator corrections are reconstructed at `bb9f34ad` and
`70e2ea3c`. Fresh Task 11 focused,
genericity, broad, isolated-row, and exact-baseline comparison evidence was
recaptured from the landed reconstruction-reference correction `5f480019`; the
exact-baseline comparator passed and the final Task 11 plan-only closure is frozen
and committed at `b59e283c` after ordered holistic specification PASS
`TASK11-HOLISTIC-SPEC-PASS-20260718-B69F5B77-01` and functional-quality APPROVED
`TASK11-HOLISTIC-QUALITY-APPROVED-20260718-B69F5B77-01`. Documentation closure
is Task 12: its functional documentation subject is frozen for ordered review
and becomes authoritative only with the unchanged reviewed commit. Task 13 and
both workflow-family parity/promotion claims remain open and unauthorized.

---

## Scope, Sequencing, And Deliberate Cost

This execution implements the functional subset retained by the 2026-07-18 user
scope override, not the complete approved prerequisite and not a path-only
compiler shortcut.

Retained functional scope:

- closed `:prompt-dependencies` syntax with required/optional typed `relpath`
  operands, literal position, and optional literal instruction;
- classic/direct and WCC/schema-2 preservation through one owner emitter;
- a separate, typed compiler contract that cannot be authored or reconstructed
  from YAML mappings;
- exact injection-byte accounting and stable successful-YAML compatibility below
  the new boundary;
- one snapshot/render call per ordinary or adjudicated provider attempt;
- root-owned, crash-durable attempt allocation and cross-process state/evidence
  locking;
- immutable success/failure evidence plus an offline, terminal-only validated
  index; and
- pending/completed resume behavior that never reads evidence as authority.

Excluded security hardening remains unimplemented and unclaimed: descriptor-
relative stable reads, platform probes, symlink/traversal/hostile-directory
defenses, authentication/provenance mechanisms, and adversarial-security tests.

Implementation starts only after the provider-call-policy prerequisite plan has
completed its final reviewed commit. Both features touch `ProviderResultExpr`,
WCC, lowering, shared provider step IR, validation, and executor code. Do not
interleave their source edits or capture a compatibility golden from a dirty
provider-policy tree. Record the provider-policy completion commit as the base in
this plan's execution-status line before Task 1 begins.

The direct design deliberately makes binary injection, globs in typed `.orc`,
dynamic instructions, arbitrary renderers, native-Windows fallback, and evidence-
driven resume harder to add. Those require separate designs rather than widening
this functional tranche.

Do not create a worktree. The repository's `AGENTS.md` explicitly forbids it.

## Governing Authorities

Read these before implementation and use the first applicable durable contract as
authority:

- `AGENTS.md` and `docs/index.md`;
- the approved design named above;
- `docs/workflow_yaml_orc_gap_list.md`;
- `docs/design/workflow_language_design_principles.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_semantic_workflow_ir.md`;
- `docs/design/workflow_lisp_executable_ir.md`;
- `specs/dependencies.md`;
- `specs/providers.md`;
- `specs/state.md`; and
- `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
  for the immediately preceding, separately reviewed provider-result edits.

The approved design controls only the retained functional clauses for this
execution. Its excluded security clauses are not execution authority under the
2026-07-18 user override. Task 12 updates durable functional specs only after
implementation and evidence are real.

## Protected And Concurrent Working-Tree Contract

The following pre-existing paths belong to the user and are outside this plan.
Do not edit, restore, stage, or commit them:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

The YAML-deletion plan is separate concurrent work. Do not edit or stage it from
this plan:

- `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`

Before every commit, stage only the exact current-task paths and run:

```bash
git diff --cached --name-only -- \
  docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  tests/test_workflow_non_progress_step_back_demo.py \
  workflows/examples/non_progress_step_back_demo.yaml \
  workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
git diff --cached --name-only -- \
  docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md
git diff --cached --check
```

Expected: no output. Never use `git add -A`, `git add .`, or a broad directory
add. The known whole-worktree `git diff --check` failure in
`state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt` is protected and
must not be “fixed” by this work.

These cached-diff commands are necessary but not sufficient because tests execute
the combined index and working tree. Task 1 therefore bootstraps canonical
verification-subject support in
`scripts/provider_prompt_dependency_broad_gate.py`; every task uses it before its
first verification command.

Task 10 owner repairs additionally use a separate closed
`workflow_verification_frozen_overlay.v1` record. The helper's
`capture-frozen-overlay` operation receives the complete exact eligible
test/fixture path set from Task 10, derives the non-empty set of dirty or untracked
eligible paths itself, and rejects an omitted dirty eligible path, a selected
clean path, any staged selected path, a rename/copy status, invalid UTF-8, a
non-file path, or a duplicate. The record contains its schema, exact capture
`HEAD` and index tree, sorted eligible and selected path sets, one ordinary
type/mode/byte-count/SHA/status inventory row for every selected path, and a
`record_sha256` over compact canonical ASCII JSON with only that member omitted.
Its output must be a new regular non-symlink file beneath an absent, repo-relative,
`git check-ignore`-proven `.orchestrate/tmp/` root. The helper publishes it
no-clobber and validates it immediately. It is captured before any owner
production edit and is not itself a verification subject or an allowed
post-launch update.

The closed `workflow_verification_subject.v1` manifest contains:

- exact `HEAD` and index tree;
- sorted declared `protected_paths`, `allowed_untracked_paths`,
  `task_subject_paths`, `allowed_post_launch_updates`,
  `generated_evidence_paths`, and
  `ignored_evidence_roots`;
- `frozen_overlay`, either `null` for ordinary tasks or one closed binding with
  the overlay-record repo-relative path, byte count, file SHA-256, self-digest,
  exact selected-path set, and copied inventory rows;
- one sorted inventory row for every declared protected, allowed-untracked, and
  task-subject path, with exact porcelain `XY` status or `CLEAN`/`ABSENT`, UTF-8
  path, `regular`/`symlink`/`missing` type, four-digit octal mode or `null`, byte
  count, and SHA-256 over regular-file bytes or symlink-target bytes;
- the complete sorted non-ignored Git status path/status set; and
- `record_sha256` over compact canonical ASCII JSON with only that member
  omitted.

Capture rejects a rename/copy status, invalid UTF-8 path, non-file declared path,
a duplicate within one declaration, any protected/allowed-untracked/task-subject
authority overlap, an allowed post-launch path that is not an exact task-subject
subset, any staged path outside the task subject, and every dirty or
untracked path outside the exact declared union. Ignored evidence roots must be
repo-relative, beneath `.orchestrate/tmp/`, proven ignored by `git check-ignore`,
and absent before the helper creates them. They are not an undisclosed overlay:
each generated artifact consumed by a baseline, outcome, or review is separately
byte-count/SHA-bound by that closed record.

`capture-subject --frozen-overlay <record>` is the only non-null overlay route.
It first validates the frozen record, requires every selected overlay path to be
repeated explicitly as a `task_subject_path`, rejects every selected path from
`allowed_post_launch_updates`, requires every declared task subject to be
non-staged at this post-edit capture, requires the current overlay status/type/
mode/bytes/SHA to equal the pre-repair record exactly, and copies those rows plus
the record binding into the new subject. The owner-repair subject is captured only
after the owner's production candidate exists and before its first final GREEN
acceptance run. Thus production candidate bytes are immutable launch bytes, not
post-launch exceptions. Every launch/review verification revalidates the external
frozen record and current overlay rows against the copied binding. Review
verification also requires every frozen-overlay path to remain non-staged.
Changing, deleting, staging, replacing, or rewriting and restoring an overlay is
prohibited; any observable endpoint mismatch invalidates the repair and returns
control to Task 10. The helper makes no claim about filesystem activity that
leaves no observable byte/status change.

`allowed_post_launch_updates` is closed and normally contains only this plan plus
any generated tracked baseline. `generated_evidence_paths` contains exact files
under the ignored evidence root, such as a temporary outcome and review envelope.
The helper's closed `broad-v1` generated-evidence layout expands to
`collection.log`, `collection.status.json`, `junit.xml`, `broad.log`,
`broad.status.json`, `pane.log`, `outcome.json`, `review-subject.json`, and
`isolated/row-00` through `row-05` with each `.log`, `.xml`, and `.status.json`
suffix; missing declared outputs remain explicit until created. The two command
status files use the closed `workflow_broad_command_status.v1` schema and bind
the phase, exact argv, integer exit, and self-digest. The helper publishes them
atomically and no-clobber. Collection acceptance requires exit `0`; the Task 1
preimplementation broad acceptance requires exit `1`. Tmux `pane_dead` is only
a liveness/completion observation because supported tmux versions may expose an
empty `pane_dead_status`; it is never command-exit authority. The closed
`review-v1` layout contains only `review-subject.json` for non-broad tasks.
The manifest output itself is the one implicit file in either ignored root; no
layout lists or hashes itself.
All other inventory rows and Git status entries must remain byte-identical to
the launch manifest until review staging. Review staging may change only
task-subject `XY` status while preserving their launch bytes, except for exact
byte changes named by
`allowed_post_launch_updates`. The helper's
`verify-subject` command has two phases:

1. `--phase launch` requires exact current equality to the immutable launch
   manifest, including `HEAD`, index tree, full status, and every inventoried
   byte. It also rejects any ignored-root entry outside the declared generated-
   evidence layout; declared outputs may transition only from missing to regular,
   non-symlink files and are not trusted until a closed record binds their exact
   mode/byte-count/SHA. After a
   declared baseline/outcome has been produced, the optional
   `--generated-evidence <path>` form permits only that record's declared
   missing-to-file transition and validates that it binds the launch manifest.
   The path must be either an exact generated-evidence-layout member or an exact
   `allowed_post_launch_updates` member whose schema is a generated tracked
   baseline. In the latter case, verification additionally permits only that
   baseline's launch-to-current inventory/status transition. No plan update or
   unrelated allowed-post-launch update is permitted in this phase.
2. `--phase review` additionally consumes a closed
   `workflow_verification_review_subject.v1` envelope. That envelope binds the
   launch-manifest digest, every allowed post-launch path's launch and reviewed
   type/mode/byte-count/SHA, exact staged path/status set, review patch SHA-256,
   review tree, generated evidence path/digest, and its own self-digest. For a
   non-null frozen overlay it also repeats the frozen record path/file digest/
   self-digest and copied inventory digest, and requires those values to equal
   the launch manifest before checking that no overlay row is staged. It rejects
   any other difference. The envelope lives under the declared ignored evidence
   root and is supplied directly to reviewers; it is never semantic runtime
   evidence.

Every task re-runs launch-phase verification after each test tranche. At review
freeze, it stages the exact task files, builds the review envelope, and runs
review-phase verification. It repeats review-phase verification after both
reviews and immediately before commit. Task 1 binds the launch-manifest digest
into the immutable baseline. Tasks 11 and 13 bind it into their outcomes. A test,
tmux pane, baseline, or outcome without this subject binding is not acceptable.

## File Responsibility Map

### Focused test and fixture surface

- Create `tests/test_workflow_lisp_provider_prompt_dependencies.py`: parser,
  typed AST, diagnostics, traversal, specialization, WCC, owner lowering,
  source-map, Core/executable/Semantic/persisted round trips, YAML reservation,
  checkpoint identity, and keyword-free golden tests.
- Create `tests/test_prompt_dependency_content_snapshot.py`: classified rows,
  safe reads, alias grouping, exact rendering/cap boundaries, real platform probe,
  and stable-YAML differential tests.
- Create `tests/test_provider_attempt_allocation.py`: aggregate-owner resolution,
  closed scope validation, durable state transitions, lock order, crash points,
  nested calls/loops, and concurrency tests.
- Create `tests/test_prompt_dependency_evidence.py`: closed record/index schemas,
  digest domains, no-clobber publication, crash remnants, completeness, tamper,
  and quiescence tests.
- Create `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`: real
  `.orc` compile/load/run/retry/interruption/resume/completed-reuse proof with a
  capturing provider.
- Create `tests/test_provider_prompt_dependency_broad_gate.py`: closed baseline,
  outcome, and remediation-schema tests plus exact-match, added/changed-failure,
  reviewed-subset comparisons, canonical verification-subject capture/verify,
  frozen-overlay capture/validation/cross-manifest equality, undisclosed-overlay
  rejection, and review-envelope drift tests.
- Create
  `tests/fixtures/workflow_lisp/provider_prompt_dependencies/keyword_free.orc`:
  provider result with no new keyword.
- Create
  `tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc`:
  required/optional typed parameters, aliases, append/prepend variants, and a
  structured provider result.
- Create
  `tests/fixtures/workflow_lisp/provider_prompt_dependencies/procedure_loop.orc`:
  inline procedure plus supported loop-carried relpath proof.
- Create
  `tests/fixtures/workflow_lisp/provider_prompt_dependencies/prompts.json`,
  `providers.json`, and `prompt.md`: public extern inputs with arbitrary sentinel
  prompt content.
- Create
  `tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json`:
  exact pre-feature bytes/digests for every absence-sensitive build artifact.
- Create
  `tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json`:
  the reviewed, content-addressed preimplementation broad-suite record binding
  the governing six established-unrelated rows, stable signatures, command
  exits, collection/run totals, and raw/JUnit/log digests.
- Create `scripts/provider_prompt_dependency_broad_gate.py`: a thin generic
  frozen-overlay/subject capture/verify and baseline/outcome/remediation compare
  CLI over the closed evidence contracts. It executes no workflow or pytest and
  may not classify a failure by family, provider, or feature name.

Tests must assert structure, bytes, digests, behavior, and dataflow. They must not
assert literal production prompt phrases.

### Frontend and compiler owners

- Modify `orchestrator/workflow_lisp/expressions.py`: immutable
  `PromptDependencySpec`, nested closed keyword parser, provenance, and optional
  `ProviderResultExpr` member.
- Modify `orchestrator/workflow_lisp/expression_traversal.py`: visit all required
  and optional operands.
- Modify `orchestrator/workflow_lisp/typecheck_effects.py`: `PathTypeRef`/relpath,
  inline-lowerability, literal instruction byte bound, and effect aggregation.
- Modify `orchestrator/workflow_lisp/functions.py`: function normalization and
  cloning preservation.
- Modify `orchestrator/workflow_lisp/procedure_specialization.py`: preserve and
  substitute the configuration children anywhere its explicit node rebuilds do
  not already delegate through traversal.
- Modify `orchestrator/workflow_lisp/workflow_refs.py`: retain dependency discovery
  through generic traversal and add no extern/family special case.
- Modify `orchestrator/workflow_lisp/wcc/route.py`: validate the operands on every
  supported WCC route.
- Modify `orchestrator/workflow_lisp/wcc/elaborate.py`: typed WCC values, role
  partition, policy, and per-row provenance.
- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`: reconstruct the exact
  frontend spec on every provider-result path.
- Modify `orchestrator/workflow_lisp/lowering/context.py`: typed compiler-contract
  side table owned by the lowering context.
- Modify `orchestrator/workflow_lisp/lowering/effects.py`: extend
  `LowerableProviderResult`, emit ordinary `depends_on`, and create the typed
  compiler contract once.
- Modify `orchestrator/workflow_lisp/lowering/core.py`: retain the typed side table
  on `LoweredWorkflow` and pass it separately to shared validation.
- Modify `orchestrator/workflow_lisp/lowering/origins.py` and
  `orchestrator/workflow_lisp/source_map.py`: clause/operand/policy lineage and
  stable origin keys.

No family/module/provider name is permitted in these mechanisms. Add a permanent
source guard over these files.

### Shared typed contract and IR owners

- Create `orchestrator/workflow/prompt_dependency_contract.py`: enums, frozen
  `CompilerPromptDependencyContract`, canonical normalized digest, closed wire
  decoder, and authenticated-side-table validation.
- Modify `orchestrator/workflow/validation.py`: typed side table on
  `WorkflowMappingBuildRequest`; exact step-ID reconciliation; Workflow Lisp-only
  acceptance; YAML rejection of all lookalikes at step/`depends_on`/`inject`
  levels.
- Modify `orchestrator/workflow/elaboration.py`: attach a typed contract by stable
  step ID without reading it from the authored mapping.
- Modify `orchestrator/workflow/surface_ast.py`,
  `orchestrator/workflow/core_ast.py`, `orchestrator/workflow/lowering.py`, and
  `orchestrator/workflow/executable_ir.py`: optional typed field and closed
  validation.
- Modify `orchestrator/workflow/runtime_step.py`: expose the dataclass only to
  runtime code through a typed accessor; do not thaw it into a public mapping key.
- Modify `orchestrator/workflow/semantic_ir.py`: optional normalized prompt surface
  with typed refs, policy, instruction digest, exact mode, and origin key.
- Modify `orchestrator/workflow/persisted_surface.py`: dedicated optional closed
  member; require authenticated Workflow Lisp manifest/source/source-map context
  whenever present.
- Modify `orchestrator/dashboard/compiled_workflow.py`: pass the already validated
  build/source/source-map bindings into the persisted decoder and verify source
  bytes against `manifest.source_sha256`.
- Modify `orchestrator/workflow_lisp/build.py` and
  `orchestrator/workflow_lisp/build_artifacts.py`: production-time authenticated
  decode and a typed-contract-present-only manifest anchor for the exact
  `source_map.json` path and SHA-256. Omit the anchor when the contract is absent
  so keyword-free manifest bytes do not change.
- Modify `orchestrator/workflow_lisp/lexical_checkpoints.py`: include the typed
  exact-path contract in the existing provider prompt-input contract digest.
- Modify `tests/workflow_bundle_helpers.py` only where typed executable round-trip
  test helpers require the new optional field.

`orchestrator/workflow/runtime_plan.py` must not change. Its byte identity is an
explicit negative test.

### Safe snapshot, rendering, and platform owners

- Create `orchestrator/deps/safe_io.py`: operational capability probe, trusted
  workspace directory descriptor, component/symlink resolution, no-follow final
  open, streaming UTF-8/newline normalization, identity rechecks, and cleanup.
- Create `orchestrator/deps/content_snapshot.py`: classified authored rows,
  required-wins alias grouping, lexicographic canonical target order, immutable
  snapshot records, one attempt-wide retained-content budget, exact cap renderer,
  and stable failure taxonomy. Row/group metadata may scale with authored input,
  but retained dependency-content bytes across all groups may not scale as
  `group_count * MAX_INJECTION_BYTES`.
- Modify `orchestrator/deps/resolver.py`: preserve the legacy glob API while
  exposing classified YAML rows to the shared snapshot owner; exact mode never
  calls `glob`.
- Modify `orchestrator/deps/injector.py`: retain list-mode compatibility and make
  content mode render only from an immutable snapshot; remove `Path.read_text`
  and catch-and-skip behavior.
- Modify `orchestrator/deps/__init__.py`: export only the stable shared APIs.

The safe reader may not use `Path.resolve` or string-prefix containment as its
security decision, and may not fall back to pathname reads on unsupported
platforms.

### Durable state, attempt identity, and evidence owners

- Create `orchestrator/state_locking.py`: descriptor-relative regular lock files,
  state-mutation/evidence lock order, file+directory-fsynced atomic state writes,
  and testable fault points.
- Modify `orchestrator/state.py`: optional omitted-when-empty
  `provider_attempt_allocations`, closed load validation, durable writer, and sole
  allocation/publication-event methods.
- Modify `orchestrator/workflow/call_frame_state.py` and
  `orchestrator/workflow/executor_runtime.py`: nested managers delegate through
  the aggregate root; no mirrored allocator state.
- Create `orchestrator/workflow/provider_attempts.py`: `ProviderAttemptScope`,
  recursive `ResumeScopePath` validation, aggregate-owner resolution, visit key,
  and allocator projection.
- Create `orchestrator/workflow/prompt_dependency_evidence.py`: canonical success
  and failure records, immutable record publication, manifest binding, terminal
  validator, crash-temp cleanup, and immutable index publication.
- Create `scripts/validate_prompt_dependency_evidence.py`: thin
  provider/family-neutral offline CLI over the production validator; no workflow
  execution and no concrete workflow, family, module, or provider identity
  branch.

### Execution integration owners

- Modify `orchestrator/workflow/prompting.py`: compose a supplied immutable
  dependency block at the existing contract position; no workspace reopen.
- Modify `orchestrator/workflow/executor.py`: one shared per-attempt composition
  call inside the ordinary retry loop, allocation/evidence order, final-prompt
  digest, preservation of truncation metadata through the existing
  provider-result `debug.injection` surface, and completed-boundary no-reopen
  behavior.
- Modify `orchestrator/workflow/adjudication_bindings.py` and
  `orchestrator/workflow/adjudication_candidates.py`: pass candidate ID/scope and
  use the same snapshot API once per retry.
- Modify `orchestrator/cli/commands/run.py`: for a typed contract, run safe-I/O
  preflight and enable root state locking before `StateManager.initialize`.
- Modify `orchestrator/cli/commands/resume.py`: preflight before force-restart
  initialization and before any mutation of a loaded affected run.

Legacy YAML uses the same stable content snapshot and retry freshness but acquires
no allocator entry or Workflow Lisp evidence record.

### Documentation owners, only after implementation closes

- Modify `specs/dependencies.md`, `specs/providers.md`, `specs/security.md`, and
  `specs/state.md`.
- Modify `docs/design/workflow_lisp_frontend_specification.md`,
  `docs/design/workflow_lisp_semantic_workflow_ir.md`, and
  `docs/design/workflow_lisp_executable_ir.md`.
- Modify `docs/lisp_workflow_drafting_guide.md`,
  `docs/capability_status_matrix.md`, `docs/design/README.md`, and `docs/index.md`.
- Modify `docs/workflow_yaml_orc_gap_list.md` only to close the generic
  provider-input proof prerequisite; do not claim either survivor family has
  promoted.
- Modify the approved design's status/evidence section only in the final reviewed
  closure commit; do not rewrite its decisions.
- Modify this plan's checkboxes/status in every task commit.

## Non-Negotiable Runtime And Evidence Invariants

Every task reviewer checks these invariants even when the task touches only one
layer:

1. Absence adds no serialized `null`, empty map, allocator member, evidence path,
   or runtime-plan change.
2. YAML never authors or reconstructs exact-mode/compiler-origin metadata.
3. Exact mode reads only typed runtime binding refs already proven relpath.
4. Required and present optional content failures occur before provider
   preparation; absent optional remains valid.
5. One attempt performs one snapshot/read/render; rendering and evidence never
   reopen a dependency.
6. Canonical target order is lexicographic; authored order survives only as row
   provenance.
7. The rendered injection block is at most 262144 UTF-8 bytes under the exact
   accounting contract.
8. Provider attempt ordinals derive only from durable root state and may contain
   disclosed gaps.
9. Runtime never enumerates, opens, hashes, or validates earlier evidence to
   prepare, retry, resume, or reuse a provider boundary.
10. A completed provider result is reused without reopening mutable dependencies;
    authoritative contract drift still invalidates checkpoint reuse.
11. Runtime-plan topology remains byte-identical.
12. No concrete family, workflow, module, or provider identity branch enters
    generic code. Frontend-origin checks use the closed typed capability/enum,
    never a compiler-name string branch.
13. Truncation remains visible through the existing provider-result
    `debug.injection` surface as well as prompt text and structured evidence; it
    does not create a second state member, expose bodies, or change the debug
    shape for non-truncated attempts.
14. Retained snapshot dependency content is bounded once per attempt by the global
    injection budget, independent of canonical-group count. Transient decoder/read
    buffers are fixed and also independent of group count. Row/group metadata may
    scale with input count, and every selected file is still streamed completely
    for UTF-8 validation, counts, and digests after the retained-content budget is
    exhausted.
15. Broad verification is accepted only by the reviewed exact-six baseline
    comparator or by that baseline minus separately committed and independently
    reviewed remediation rows; a new or changed failure always fails closed.

## Reviewed Broad-Failure Baseline Contract

The repository does not currently have a zero-failure broad-suite baseline. The
governing Stage-6 roadmap repeatedly records exactly six established unrelated
failures, and the reviewed migration-wave replay owns their accepted identities
and stable signatures. This plan must not relabel those rows, silently tolerate
them, or require an impossible zero exit.

Before any feature production edit, Task 1 captures and commits the closed
`workflow_broad_known_failure_baseline.v1` record at
`tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json`.
It must bind all of the following:

- the exact validated `workflow_verification_subject.v1` launch-manifest path,
  byte count, SHA-256, self-digest, `HEAD`, index tree, complete sorted Git status,
  and full protected/allowed-untracked/task-subject inventory, plus
  Python/pytest/platform identifiers, exact collect and broad commands, and
  capture timestamp;
- collection exit, collected count, raw collection-log byte count/SHA-256;
- broad pytest exit, internally consistent passed/failed/skipped/error/xfailed/
  xpassed/total counts, JUnit and complete-log byte counts/SHA-256;
- exactly six ordered failure rows, each with node ID, the accepted stable
  signature, isolated command and exit `1`, raw isolated-log and isolated-JUnit
  byte counts/SHA-256 values, canonical per-failure JUnit payload,
  canonical-payload SHA-256, stable-signature SHA-256, and the authority row
  digest;
- exact content bindings to
  `docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json`
  at SHA-256 `d7bcad2eabf075bcb1f5a5e62bee600add68f075f0b51f15dc53644a4105f9f2`,
  `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`
  at SHA-256 `4c1b7e3ce36872df9e9f522c5709801290d10541676d5e58cbd31facecac6cbd`,
  and `tests/workflow_lisp_procedure_identity.py` at SHA-256
  `f1157d11c8b8f8c1a2aacb72d4424ef3ddfc5c2cbe8ace076f6411ac6fc28dec`;
  the six rows are exactly the replay's `established_unrelated` rows, never its
  historical pilot rows; and
- `record_sha256`, computed over canonical compact ASCII JSON with only that
  member omitted. Unknown/missing keys, digest drift, a nonzero collection exit,
  any count mismatch, a row count other than six, or an authority mismatch fails
  baseline construction.

The gate's closed `workflow_broad_failure_normalization.v1` is implemented and
tested in the Task 1 helper. For every isolated run it parses exactly one JUnit
`testcase`, requires the testcase node ID to equal the invoked node, and reduces
the failure to this canonical compact-JSON payload:

```text
{
  schema: "workflow_broad_canonical_failure.v1",
  nodeid: exact pytest node ID,
  outcome: "failure",
  exception_type: normalized non-empty exception class,
  normalized_failure_signature: normalized non-empty stable signature
}
```

Signature extraction applies the existing bounded repository-root, pytest-temp,
elapsed-summary, and Python-repr normalization and normalizes only the source-line
integer in Python logging-record prefixes of the form
`<LEVEL> <logger>:<python-file>:<decimal-line>`. It does not include JUnit timing,
captured stdout/stderr, traceback frames, or pytest summary text in the canonical
payload, and it does not normalize assertion values, exception types/messages,
paths after the bounded root substitutions, arbitrary numbers, hashes, or other
semantic content. The raw isolated log and JUnit file remain digest-bound evidence
but are not compared byte-for-byte across runs. Canonical-payload SHA-256 covers
the complete payload above; stable-signature SHA-256 covers canonical
`{nodeid, normalized_failure_signature}`. Both must equal values derived from the
authority row during baseline construction.

The baseline binds the normalizer schema and helper-file digest; Task 11 rejects
unreviewed helper drift. Task 1's ordered specification and quality reviewers
approve the exact baseline, helper, tests, and capture bindings in their own
immutable tree, and Task 1 commits that byte-identical tree before Task 2 may edit
any frontend, compiler, IR, runtime, or other feature production path. One exact
metadata-only migration is enumerated after Task 11 exposed that the helper did
not accept pytest's valid optional long-duration `H:MM:SS` suffix. The same
ordered repair reviews must approve the strict parser, its both-direction tests,
this plan, and a baseline update that changes only
`normalization.helper_sha256` plus the canonically derived `record_sha256`. The
pre-migration baseline file SHA-256 is
`3d71df6eb7777db7af96ec9271a259078aa307cfbd5da71d7c4a6bc96f6426d0`,
record SHA-256 is
`d6677f99da9ba471696cd2b47d38397881ec9a50eea69a56807d38a592df3b90`,
and helper SHA-256 is
`1473354e2c40829061fb281350d97e779117691d106c2a86cedbb485d9163ca7`.
The reviewed migration target has baseline file SHA-256
`c382f8f70264f1cdc9a31d2100009463b8e8b56a51fb41cd67a4cb5c6e1b82c6`,
record SHA-256
`ead6d7f11ad9b2222a376135ac5c03336b1685c107a39d4c117e89892a063058`,
and helper SHA-256
`b60c395e78dd757bd7bf1cb1eeac70428ba84195f3991443b91ec16e537a538c`.
A canonical projection that omits `record_sha256` and replaces only the helper
digest with the fixed `__HELPER_SHA256__` sentinel has SHA-256
`eba9b11a15ef5c42a10b05055a3835c342d9d71d6b7ab6662b6dcb75f3a71be4`
on both sides, proving that authorities, subject, capture, environment, totals,
and all failure rows are byte-semantically unchanged. No raw evidence or outcome
is regenerated or used to rewrite the baseline. After this one reviewed
migration lands, the baseline is immutable again; later work never rewrites it
to match an outcome, except for one second correctness-driven metadata-only
migration after holistic quality review proved that the helper accepted
blank-separated pseudo-trailers. That correction changes only
`normalization.helper_sha256` from
`b60c395e78dd757bd7bf1cb1eeac70428ba84195f3991443b91ec16e537a538c` to
`e0567213a561699ad9ea94500ac327001061b37acd56d795a118ea6d4e2cc8fc`
and the canonically derived `record_sha256` from
`ead6d7f11ad9b2222a376135ac5c03336b1685c107a39d4c117e89892a063058`
to `513802fc9ba0ab9ac93c0278c0f1283c55b94d428309ea83e133c14dcfc666fa`.
The target baseline file SHA-256 is
`b32732ba7cf1d70b70694d7edabc4a28100d6d80313711b6402f4fa6af0825fe`;
the canonical helper-sentinel invariant remains
`eba9b11a15ef5c42a10b05055a3835c342d9d71d6b7ab6662b6dcb75f3a71be4`,
so no authority, subject, captured evidence, environment, totals, or failure row
changes. After this second reviewed migration, the baseline is immutable again.
The capture may record the protected dirty paths and the
separately owned YAML-deletion plan listed above, but every other dirty path must
be absent or explicitly part of Task 1's reviewed subject.

Every Task 11 or Task 13 broad run writes a temporary closed
`workflow_broad_outcome.v1` containing the same subject-manifest,
command/environment, collection, totals, raw-file, JUnit/log, failure-row, and
self-digest domains. Outcome construction requires a fresh launch-phase
verification of that same manifest and embeds its exact path/byte count/file
SHA-256/self-digest/HEAD/index tree. The gate CLI validates both records before
comparison. Each outcome also reruns all six
baseline node IDs in isolation, in baseline order, with the same argv and the
same per-row log/JUnit/status filenames used by Task 1. The comparator derives
the canonical payload from those fresh isolated JUnit files; it never copies a
payload or digest from the baseline. Acceptance is closed:

1. **Exact baseline match:** the observed failure node/signature/canonical-
   payload-digest set is exactly the six-row baseline; every isolated exit is
   `1`, collection exit is `0`, broad exit is `1`, and all outcome totals and raw
   digests validate. Passing/collected
   totals may increase because this plan adds tests, but they are evidence fields,
   not a license to change a failure; failed/error counts must equal the exact
   observed rows and no collection/runtime crash is allowed.
2. **Strict subset after remediation:** no subset, including the empty set, is
   accepted directly. First return the fixed failure to its actual owner, land
   the fix with the ordinary ordered exact-tree reviews, then commit a separate
   canonical `workflow_broad_failure_remediation.v1` record under
   `docs/plans/evidence/provider-prompt-dependencies/broad-remediations/`. That
   record binds the immutable baseline digest, exactly the sorted unique removed
   rows, fixing commit/tree and focused proof digests, and two independent closed
   specification/quality approval pairs: one for the fixing commit and one for
   the remediation-record commit. Its `record_path` must be the canonical
   directory plus the SHA-256 of the canonical removed-row array. The validator
   receives the actual record path, requires byte-for-byte canonical equality,
   and finds exactly one reachable addition commit containing those exact bytes
   at that exact path. It requires `fixing_commit < record addition commit <=
   current HEAD`, exact commit trees, and exact ordered `Review-Tree`,
   `Spec-Review`, then `Quality-Review` trailers on both commits. This establishes
   one immutable record per removed-row set: correction cannot overwrite that
   deterministic path and would require an explicitly revised record contract,
   which is outside this plan. Temporary or untracked remediation JSON is never
   accepted. The compare CLI rejects every non-regular, symlink, non-JSON, or
   non-record entry in a supplied remediation directory, and the comparator
   validates every supplied record before selecting even the exact branch. Only
   then may the comparator accept exactly
   `baseline rows - union(reviewed remediation rows)`, with broad exit `1` when
   rows remain or `0` when the reviewed remainder is empty. Every remaining row
   must have isolated exit `1` and the exact baseline canonical payload digest;
   every remediated row must have isolated exit `0`, a one-test passing JUnit
   result, and no failure payload. Overlapping,
   duplicate, unreviewed, wrong-commit, or non-baseline remediation rows fail.
3. **Anything else:** any added node, changed signature or canonical payload,
   missing row without a valid remediation, unexpected error, collection failure,
   count disagreement, invalid exit, malformed raw artifact, or baseline/
   remediation tamper fails closed. If attributable to this feature, return to
   the owning task and restart its tests and both reviews. Otherwise stop and
   revise the plan; never call it an established failure from the Task 11 loop.

Both baseline and outcome validators parse the complete node-ID inventory from
the authoritative `pytest --collect-only -q` log and reconcile it one-to-one with
the complete JUnit testcase inventory. Unknown, missing, ambiguous, or duplicate
passing, failing, errored, skipped, or xfailed cases fail closed. Totals contain
explicit `xfailed` and `xpassed` fields, including zero, and reconcile the pytest
terminal summary with JUnit aggregation and testcase outcomes; ordinary
`passed`/`skipped` totals exclude xpass/xfail respectively.

`scripts/provider_prompt_dependency_broad_gate.py` is only a deterministic
evidence builder/validator/comparator. Tests cover exact acceptance; added and
signature/canonical-payload-changed failures; missing rows; malformed
exit/totals/JUnit/log/hash;
unreviewed, overlapping, uncommitted, and tampered remediations on both exact and
subset branches; unexpected remediation-directory entries; a valid strict
subset; a valid fully remediated zero-exit outcome; explicit zero/nonzero
xfail/xpass reconciliation; and complete collection/JUnit inventory tamper. It must not execute pytest, edit the
baseline, infer causality, or authorize a waiver.

## Review And Commit Discipline

Use one fresh implementation subagent per task. Never run two implementation
subagents concurrently because most tasks share typed IR or executor owners.
Except for Task 1's explicitly tested bootstrap, capture the task's immutable
verification subject after implementation/self-review edits but before its first
final GREEN/acceptance verification command; ordinary RED runs precede this
freeze and are recorded in task evidence but are not acceptance evidence. Pass
every path created or modified in the task's `Files`
list through repeated `--task-subject` arguments, the eight paths
from the protected/concurrent contract through their corresponding repeated
arguments, this plan through `--allowed-post-launch-update`, and one task-specific
ignored root through `--ignored-evidence-root`. Do not abbreviate directories or
use a glob. Use `--generated-evidence-layout review-v1` unless a task below requires
`broad-v1`. The execution log records the complete argv.

Task 10 owner repairs do not move this freeze earlier. They first capture the
separate pre-edit frozen-overlay record, then capture the ordinary immutable
owner-repair subject only after the production candidate exists. The latter is
the launch manifest used by GREEN runs and reviews; its non-null frozen-overlay
binding proves exact equality to the earlier record.

Immediately run:

```bash
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
```

After its RED/GREEN work and self-review, use this digest-stable protocol for
**every** task, including the implementation gate in Task 11, documentation
closure in Task 12, and final gate in Task 13:

1. Finish the task's tests and self-review, re-run launch-phase subject
   verification, and update this plan's current-task
   checkboxes and any intended post-commit status/evidence text **before** review.
   The last checkbox in each task means “freeze this review subject and dispatch
   the ordered reviews”; review outcomes are recorded in commit trailers, not by
   a later plan edit.
2. Stage only the task's exact paths plus this plan. Run the protected-path and
   cached-diff guards. Record the staged patch digest and exact Git tree object:

   ```bash
   REVIEW_PATCH_SHA256="$(git diff --cached --binary | sha256sum | awk '{print $1}')"
   REVIEW_TREE="$(git write-tree)"
   test -n "$REVIEW_PATCH_SHA256" && test -n "$REVIEW_TREE"
   git diff --cached --name-status
   python scripts/provider_prompt_dependency_broad_gate.py build-review-subject \
     --subject-manifest "$CAPTURE_ROOT/subject.json" \
     --generated-evidence "$TASK_EVIDENCE" \
     --review-patch-sha256 "$REVIEW_PATCH_SHA256" \
     --review-tree "$REVIEW_TREE" \
     --output "$CAPTURE_ROOT/review-subject.json"
   python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
     --manifest "$CAPTURE_ROOT/subject.json" \
     --phase review \
     --review-subject "$CAPTURE_ROOT/review-subject.json"
   ```

   `TASK_EVIDENCE` is the immutable generated baseline/outcome for Tasks 1, 11,
   and 13. Other tasks set it to the immutable launch subject itself; their
   runnable command outputs are supplied directly to reviewers, while the review
   envelope proves the source/tree/overlay identity under which they ran.

3. Dispatch a fresh specification-compliance reviewer with the approved design,
   this plan, task number, exact staged diff, `REVIEW_PATCH_SHA256`,
   `REVIEW_TREE`, immutable launch manifest, task evidence, and review-subject
   envelope. Repeat specification review until PASS.
4. Only after specification PASS, dispatch a different implementation-quality
   reviewer against the **same** patch digest and tree. Return every finding to
   the same implementer. Any source, test, fixture, plan, checkbox, status, or
   whitespace change invalidates both reviews: fix, rerun selectors, restage,
   compute a new patch/tree pair, and restart specification review.
5. After both PASS results, do not edit any tracked byte. Re-run the guards and
   prove the index is still the reviewed subject:

   ```bash
   test "$(git diff --cached --binary | sha256sum | awk '{print $1}')" = \
     "$REVIEW_PATCH_SHA256"
   test "$(git write-tree)" = "$REVIEW_TREE"
   git diff --cached --check
   python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
     --manifest "$CAPTURE_ROOT/subject.json" \
     --phase review \
     --review-subject "$CAPTURE_ROOT/review-subject.json"
   ```

6. Commit that unchanged tree with trailers carrying the review subject and the
   two externally returned review identifiers/verdicts. Commit metadata does not
   change the reviewed tree:

   ```text
   Review-Tree: <REVIEW_TREE>
   Review-Patch-SHA256: <REVIEW_PATCH_SHA256>
   Spec-Review: PASS <review-identifier>
   Quality-Review: APPROVED <review-identifier>
   ```

The execution log must never mark a review outcome by editing the already
reviewed tree. A later task may report the prior commit and its trailers, but it
must not retroactively change the prior task's review subject. Task 13 verifies
the trailers and tree identity for every task commit.

Suggested task commit subjects appear below. A reviewer may not waive a failing
test, weaken a failure category, relax an exact schema, or substitute inspection
for a runnable check. Acceptance by the closed known-failure comparator is not a
waiver: it proves exact equality to the already reviewed six-row authority minus
only separately committed and independently reviewed remediation rows.

## Task 1: Freeze And Independently Review Preimplementation Baselines

**Owner:** fresh baseline/evidence implementer. This task may create only tests,
fixtures, the generic gate helper, immutable baselines, ignored capture artifacts,
and this plan. It may not edit a frontend, compiler, IR, runtime, workflow, prompt,
or specification production path.

**Files:**

- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/keyword_free.orc`
- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/providers.json`
- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/prompts.json`
- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/prompt.md`
- Create `tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json`
- Create `tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json`
- Create `tests/test_provider_prompt_dependency_broad_gate.py`
- Create `scripts/provider_prompt_dependency_broad_gate.py`
- Create `tests/test_workflow_lisp_provider_prompt_dependencies.py` with only the
  keyword-free baseline test in this task
- Create ignored capture artifacts under
  `.orchestrate/tmp/provider-prompt-dependencies-preimplementation/`
- Modify this plan

- [x] **Step 1: Bootstrap subject-manifest verification and record the clean
  implementation base.**

Require a clean index and a completed provider-policy commit. The protected paths
listed above may remain dirty, but refuse unstaged or staged changes in every
compiler/build/IR/runtime path that can influence these artifacts. Record the
exact clean base commit and tree. Compile the keyword-free fixture through both
default WCC/schema 2 and classic/direct compatibility routes. Store canonical
bytes and `sha256:` values for frontend AST, lowered mapping, Core AST, executable
IR, Semantic IR, persisted surface, runtime plan, and source map. The closed
baseline object includes `implementation_base_commit` equal to the exact
provider-policy completion commit; Task 11 reads it as the only feature diff
base. Generate it once; later tests only read it.

Before the broad run, write RED tests for both closed subject schemas, sorted
full-status and file/symlink inventories, invalid UTF-8/rename/non-file input,
undisclosed dirty/untracked paths, unexpected staging, protected-overlay byte
drift, allowed post-launch plan/baseline updates, ignored-root constraints,
self-digests, both closed generated-evidence layouts, and launch/review
verification. Also write RED tests for the closed frozen-overlay schema and
commands: exact eligible-to-dirty selection, omitted/extra/clean/staged/renamed
row rejection, no-clobber ignored-root publication, record tamper, a post-edit
subject whose repeated overlay rows equal the pre-edit record, production bytes
already frozen at post-edit subject capture, pre-staged candidate/plan rejection,
frozen-row staging/drift rejection in both verification phases, and an allowed
plan-only post-launch update. In the same test module, cover the
baseline/outcome/remediation schemas, canonical JUnit payload extraction,
exact/subset/tamper directions, raw artifact digest validation, subject-manifest
binding, pairwise-disjoint subject authorities, frozen-overlay/task-subject/
post-launch relationships, complete collection/JUnit testcase reconciliation,
explicit zero/nonzero xfail/xpass totals, validate-before-branch comparison,
closed remediation-directory inputs, immutable tracked remediation path/bytes/
commit ancestry, independent fixing/record review trailers, and authority
mismatch in
`tests/test_provider_prompt_dependency_broad_gate.py`. Implement the complete
thin helper surface in `scripts/provider_prompt_dependency_broad_gate.py`, with
only the frozen-overlay/subject capture/verify and baseline build/validate/compare
operations required by these tests; it executes neither pytest nor a workflow.
Run the complete helper test module before continuing. No helper or helper-test
byte may change after the launch manifest is captured; an exposed defect restarts
Task 1 from a new manifest and fresh broad run.

- [x] **Step 2: Capture the full preimplementation broad run in tmux.**

Use the repository broad command and these exact self-contained blocks. No block
depends on a variable from a prior shell:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps-preimplementation.sock"
SESSION="prompt-deps-preimplementation"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-preimplementation/current"
mkdir -p "$SOCKET_DIR"
if tmux -S "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
  echo "refusing to replace existing tmux session: $SESSION" >&2
  exit 1
fi
rm -rf -- "$CAPTURE_ROOT"
python scripts/provider_prompt_dependency_broad_gate.py capture-subject \
  --output "$CAPTURE_ROOT/subject.json" \
  --ignored-evidence-root "$CAPTURE_ROOT" \
  --generated-evidence-layout broad-v1 \
  --protected docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  --protected docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  --protected docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  --protected state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  --protected tests/test_workflow_non_progress_step_back_demo.py \
  --protected workflows/examples/non_progress_step_back_demo.yaml \
  --protected workflows/library/prompts/workflow_step_back/diagnose_non_progress.md \
  --allowed-untracked docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md \
  --task-subject docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md \
  --task-subject tests/fixtures/workflow_lisp/provider_prompt_dependencies/keyword_free.orc \
  --task-subject tests/fixtures/workflow_lisp/provider_prompt_dependencies/providers.json \
  --task-subject tests/fixtures/workflow_lisp/provider_prompt_dependencies/prompts.json \
  --task-subject tests/fixtures/workflow_lisp/provider_prompt_dependencies/prompt.md \
  --task-subject tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json \
  --task-subject tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json \
  --task-subject tests/test_provider_prompt_dependency_broad_gate.py \
  --task-subject scripts/provider_prompt_dependency_broad_gate.py \
  --task-subject tests/test_workflow_lisp_provider_prompt_dependencies.py \
  --allowed-post-launch-update docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md \
  --allowed-post-launch-update tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
tmux -S "$SOCKET" new-session -d -s "$SESSION" -n pytest -c "$PWD"
tmux -S "$SOCKET" set-option -t "$SESSION" remain-on-exit on
BROAD_COMMAND='set -o pipefail
pytest --collect-only -q > .orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/collection.log 2>&1
collect_rc=$?
python scripts/provider_prompt_dependency_broad_gate.py write-command-status --output .orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/collection.status.json --phase collection --exit-code "$collect_rc" --arg pytest --arg=--collect-only --arg=-q
pytest -q -n 16 --dist=worksteal --junitxml=.orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/junit.xml 2>&1 | tee .orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/broad.log
pytest_rc=${PIPESTATUS[0]}
python scripts/provider_prompt_dependency_broad_gate.py write-command-status --output .orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/broad.status.json --phase broad --exit-code "$pytest_rc" --arg pytest --arg=-q --arg=-n --arg=16 --arg=--dist=worksteal --arg=--junitxml=.orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/junit.xml
printf "__COLLECT_EXIT__=%s\n__PYTEST_EXIT__=%s\n" "$collect_rc" "$pytest_rc"
test "$collect_rc" -eq 0 || exit "$collect_rc"
test "$pytest_rc" -eq 1
wrapper_rc=$?
exit "$wrapper_rc"'
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -l -- "$BROAD_COMMAND"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 Enter
```

Poll below 60-second intervals with:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps-preimplementation.sock"
SESSION="prompt-deps-preimplementation"
tmux -S "$SOCKET" display-message -p -t "$SESSION":0.0 '#{pane_dead} #{pane_dead_status}'
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

Then verify/capture before killing:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps-preimplementation.sock"
SESSION="prompt-deps-preimplementation"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-preimplementation/current"
test "$(tmux -S "$SOCKET" display-message -p -t "$SESSION":0.0 '#{pane_dead}')" = '1'
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S - > "$CAPTURE_ROOT/pane.log"
rg -n '^__COLLECT_EXIT__=0$' "$CAPTURE_ROOT/pane.log"
rg -n '^__PYTEST_EXIT__=1$' "$CAPTURE_ROOT/pane.log"
test -s "$CAPTURE_ROOT/collection.log"
test -s "$CAPTURE_ROOT/collection.status.json"
test -s "$CAPTURE_ROOT/junit.xml"
test -s "$CAPTURE_ROOT/broad.log"
test -s "$CAPTURE_ROOT/broad.status.json"
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
tmux -S "$SOCKET" kill-session -t "$SESSION"
```

- [x] **Step 3: Capture all six authority rows in isolation.**

Run this exact driver. It takes node IDs only from the content-addressed replay
authority, uses argv rather than shell evaluation, writes deterministic row
filenames, and fails on every pytest status other than ordinary pass/fail:

```bash
AUTHORITY="docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-preimplementation/current"
python - "$AUTHORITY" "$CAPTURE_ROOT" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

authority = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = [row for row in authority["failures"] if row["category"] == "established_unrelated"]
if len(rows) != 6:
    raise SystemExit("authority must select exactly six established_unrelated rows")
root = Path(sys.argv[2]) / "isolated"
root.mkdir(parents=True, exist_ok=False)
for index, row in enumerate(rows):
    nodeid = row["nodeid"]
    stem = f"row-{index:02d}"
    log_path = root / f"{stem}.log"
    junit_path = root / f"{stem}.xml"
    argv = [sys.executable, "-m", "pytest", "-q", nodeid, f"--junitxml={junit_path}"]
    with log_path.open("wb") as stream:
        completed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if completed.returncode not in (0, 1):
        raise SystemExit(f"isolated row {index} ended with non-test status {completed.returncode}")
    status = {
        "schema": "workflow_broad_isolated_status.v1",
        "row_index": index,
        "nodeid": nodeid,
        "argv": argv,
        "exit_code": completed.returncode,
    }
    (root / f"{stem}.status.json").write_bytes(
        json.dumps(status, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )
PY
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
```

Expected: six `.log`, six `.xml`, and six canonical `.status.json` files; every
status records exit `1` at the preimplementation base.

- [x] **Step 4: Build and validate the immutable broad baseline.**

Using the already-tested helper without changing it or its tests, build and
validate the immutable baseline only from the captured artifacts:

```bash
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-preimplementation/current"
BASELINE="tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json"
python scripts/provider_prompt_dependency_broad_gate.py build-baseline \
  --authority docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json \
  --correction docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json \
  --normalizer tests/workflow_lisp_procedure_identity.py \
  --subject-manifest "$CAPTURE_ROOT/subject.json" \
  --capture-root "$CAPTURE_ROOT" \
  --output "$BASELINE"
python scripts/provider_prompt_dependency_broad_gate.py validate-baseline \
  --baseline "$BASELINE"
```

The builder requires broad collection exit `0`, broad exit `1`, exactly the six
authority rows, each isolated exit `1`, a one-failure JUnit testcase per row,
canonical payload/signature equality to authority, all totals/digests, and exact
authority content hashes. It also requires a unique complete collection-node
inventory, a unique complete JUnit testcase inventory with the same nodes, and
strict agreement among testcase outcomes, JUnit aggregation, and the pytest
summary, including explicit `xfailed: 0` / `xpassed: 0` when absent. The upstream adjudication authority retains its
existing `failures` array; the baseline and outcome evidence schemas use the
distinct closed `failure_rows` field throughout.

- [x] **Step 5: Run baseline verification.**

```bash
pytest -q tests/test_workflow_lisp_provider_call_policy.py
pytest --collect-only -q tests/test_provider_prompt_dependency_broad_gate.py
pytest -q tests/test_provider_prompt_dependency_broad_gate.py
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k keyword_free
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest .orchestrate/tmp/provider-prompt-dependencies-preimplementation/current/subject.json \
  --phase launch \
  --generated-evidence tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json
```

Expected: all pass, and the reviewed subject contains no feature production edit.

- [x] **Step 6: Freeze the conditional review candidate and prepare the ordered
  independent-review handoff.**

Apply the digest-stable protocol. The specification reviewer checks authority and
schema equality; a different quality reviewer checks capture/parser/comparator
robustness. Commit the byte-identical reviewed tree before Task 2 starts. No Task
2 production edit may coexist in the index or worktree during these reviews. Set
`CAPTURE_ROOT` to the preimplementation capture root and `TASK_EVIDENCE` to the
generated baseline when building the review-subject envelope. Supply the launch
manifest, baseline, and review envelope to both reviewers, and re-run review-phase
verification immediately before commit.

Suggested commit: `test: freeze prompt dependency preimplementation baselines`

The prior capture-4 candidate and its baseline were rejected by specification
review after the review exposed incomplete literal outcome/remediation CLI and
closed-validator behavior. Those artifacts were deleted and are not acceptance
evidence. A disposable, separately pathed and byte-different raw-evidence probe
subsequently exercised literal `build-outcome`, `validate-outcome`,
`compare --remediation-dir`, and generated-evidence verification through the
`exact` branch; that probe was also deleted and is not acceptance evidence. The
capture-5 subject and baseline were subsequently invalidated before handoff when
the final generated-evidence check exposed that the verifier allowed only the
evidence path, rather than every explicitly declared post-launch transition.
Those artifacts were deleted. The replacement helper has permanent coverage for
simultaneous plan plus generated-evidence transitions and rejects undeclared,
deleted, symlink/type-changing, mode-changing, or prematurely staged launch
transitions. A disposable literal launch/review probe confirmed the same behavior
for an ignored outcome plus plan update and was deleted. The fresh capture-6
subject file SHA-256 is
`d991efa8a2a01c4cda295c23923f5e985b4b6338d16df95d6fea6f94fbca50f2`
and its self-digest is
`8f722d80ce98f76fb6c976de414e6e8127f5a8c520ff66705fd37e9f39a4bcf0`.
The capture-6 baseline file SHA-256 is
`b62223a14d503ca0ec2c2fcc441bda355280e3abe4219bda0debeb85f64c565d`
and its self-digest is
`6fe470aaa0984c63f08d93bdaf0f444354744f2f2f71b3312dd0d3b7309474d0`.
Collection recorded `5408` tests with exit `0`; the broad run recorded `5385`
passed, `6` failed, `17` skipped, `0` errors, and exit `1`. Every authority row
exited `1` in isolation. Post-build verification recorded `56` provider-policy
passes, `23` helper-gate passes, and `1` keyword-free baseline pass. The
standalone capture-6 validator rejected all `55` independently resealed baseline
tamper directions. Specification review nevertheless rejected review tree
`2ae5482a` / patch `48026be3` under
`TASK1-SPEC-REJECT-20260717-2AE5482A-02`: exact nested status/inventory/review and
remediation Git/trailer validation was incomplete, literal outcome/comparator
behavior lacked permanent self-contained coverage, and the frozen-overlay matrix
was incomplete. Capture 6 and its baseline are therefore invalid and must be
deleted. The replacement helper tests now cover these contracts in self-contained
repositories, including literal exact/subset/zero-exit outcome comparison and the
exact eight-path Task 10 overlay CLI. The fresh capture-7 subject file SHA-256 is
`310e9458470528f7c224dbd207d319c8ae7a63ba940ded02de0d34774a54c280`
and its self-digest is
`59cdaf549fd47242b984e2442a48b8ee391add5be13bc3bcc0f3b737c3a32c47`.
The capture-7 baseline file SHA-256 is
`4d4d08226bbfa356de8826b565dedacc1c0573085d77d0e2bad37da29caa2458`
and its self-digest is
`0a9d47242acee1f05da5b60dfc65bb779c48e76b8dfe17bb03f9dd2e93d23ae9`.
Collection recorded `5434` tests with exit `0`; the broad run recorded `5411`
passed, `6` failed, `17` skipped, `0` errors, and exit `1`. Every authority row
exited `1` in isolation. Post-build verification recorded `56` provider-policy
passes, `49` helper-gate passes, and `1` keyword-free baseline pass. The
standalone capture-7 validator rejected all `55` independently resealed baseline
tamper directions. Specification review rejected review tree `61d9d05a` / patch
`5f0e2fe7` under `TASK1-SPEC-REJECT-20260717-61D9D05A-03`: serialized subject
validation did not close all authority/overlay relationships; exact comparison
could bypass malformed remediation inputs; remediation JSON was not bound to an
immutable tracked path and reviewed containing commit; xfail/xpass totals were
implicit; and collection/JUnit reconciliation covered failures rather than the
complete testcase inventory. Capture 7 and its baseline were deleted. The
replacement helper now validates every remediation before either comparison
branch, binds each immutable record to a deterministic tracked path and unique
reachable addition commit after its independently reviewed fix, records explicit
zero/nonzero xfail/xpass totals, and reconciles every collected node with exactly
one JUnit testcase. Permanent tests cover exact and subset invalid/uncommitted
records, unexpected directory entries, both total fixtures, unknown/missing/
duplicate pass/skip cases, and parameter IDs containing embedded `::`. The
post-regression helper module records `60` passes; a disposable literal probe of
the deleted capture-7 raw logs reconciled all `5434` collection nodes with all
`5434` JUnit cases and derived `5411` passed, `6` failed, `17` skipped, `0`
errors, `0` xfailed, and `0` xpassed. That disposable probe is not acceptance
evidence. Capture 8 was generated only after the helper, helper tests, and
keyword-free baseline bytes froze.

The frozen capture-8 helper file SHA-256 is
`965a0a9398424c6d518bb27a4ea40e0e7cebf79741d4e58143ef8240faff321f`
and its permanent test-module SHA-256 is
`cd16e70b707f48123c9b295d740c7b1817073194082d10374fcfec6ad268d5d0`.
The capture-8 subject file SHA-256 is
`da39fbda33ccb92c5cdb169a44ba9a56e9c412779c3cb9a54757a9766d8cd79e`
and its self-digest is
`75628d0159ba123f31410d9dd1c21f6e0859392c5435b031d789e339a6db66a0`.
The capture-8 baseline file SHA-256 is
`48695402d8e8b9569db3619bc488e9190cc221c73f763d6163e97cb367f542ce`
and its self-digest is
`58e07aef6aa22c36b6241fd6325ca952ca31951d8eab4c0d39aab9981006b8f1`.
Collection recorded `5445` unique nodes with exit `0`; the broad JUnit contains
exactly the same `5445` unique testcases and records `5422` passed, `6` failed,
`17` skipped, `0` errors, `0` xfailed, `0` xpassed, and exit `1`. Every authority
row exited `1` in isolation and all `18` row artifacts are present. Post-build
verification records `56` provider-policy passes, `60` helper-gate passes, `1`
keyword-free baseline pass, standalone baseline validation, and launch-phase
generated-evidence verification. A final pre-handoff audit then found that the
permanent authority-overlap probes enumerated only the three unordered pairs,
rather than both ordered tamper directions requested by review 3, and that
focused-proof bindings were checked against worktree files rather than blobs in
the fixing commit tree. Capture 8 and its baseline were therefore invalidated and
deleted before review. The replacement table-driven tests cover all six ordered
authority overlaps plus the resealed post-launch-subset direction. Remediation
validation now reads every sorted unique focused-proof path and digest directly
from `fixing_commit`, rejects invalid paths/digests/missing blobs, and remains
valid when the proof is absent from the current worktree. Capture 9 must be
generated after these helper and test bytes freeze; no review verdict is claimed
here, and the implementing agent does not stage or commit them.

The frozen capture-9 helper file SHA-256 is
`fb67e7df2e0b063e22f626f1332c3a8385b3c5720b31c4c815dd974768c671f6`
and its permanent test-module SHA-256 is
`4dbeb76a1babd6cd38d05e77f35cd9899f6b67f028cb7c3419d1fb12a2b4eaec`.
The capture-9 subject file SHA-256 is
`9d73dc263a9d0fee17838ee2b9b6b1a0028b8445b11ae6e6f511999e94041c57`
and its self-digest is
`73b150f049aaa3e16aecc657b4a29667159526db3d4569da276eeb514ca87eb9`.
The capture-9 baseline file SHA-256 is
`3afbf723df331123d02c506a64e5fcff539a4a21236e23663c0356e7d6e5ba97`
and its self-digest is
`1767fe05e26bd6885f17787d363e23f4b0ac69a4969576b9d74154cda6c1647a`.
Collection recorded `5453` unique nodes with exit `0`; JUnit contains exactly the
same `5453` unique cases and records `5430` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `68` helper-gate passes, `1` keyword-free
baseline pass, standalone validation, launch-transition verification, and a
fresh direct `5453`/`5453` collection/JUnit reconciliation. These exact bytes
were rejected by specification review for tree `7263adc2` / patch `6bc9d7d7`
under `TASK1-SPEC-REJECT-20260717-7263ADC2-04`. The single confirmed blocker was
that a resealed subject could retain an extra dirty `full_status` path after
removing that path from every authority list and the inventory. Capture 9 and
its baseline were invalidated and deleted. The replacement validator now derives
the exact dirty/untracked path set from serialized inventory rows and requires
set equality with `full_status`; `CLEAN` and `ABSENT` authority rows intentionally
remain inventory-only. Permanent tests reproduce the rejected extra-status row
and preserve a clean tracked protected authority with an empty `full_status`.
Capture 10 must be generated only after these helper/test bytes freeze. No new
review verdict is claimed here, and the implementing agent does not stage or
commit them.

The frozen capture-10 helper file SHA-256 is
`6174178e439d91063280db5cb41f2a0eadae51a3b4823f9310422c575e5a57f1`
and its permanent test-module SHA-256 is
`11ac3658a92ebe9f12da06774b4f0caa5d5abba4c506781459ed8b5b114e60cd`.
The capture-10 subject file SHA-256 is
`94c10159e4e6e01c06659179854d53a28b83bf3dec1d30372a5e01a266f7bbf9`
and its self-digest is
`b23f42c92487d35a38f17b7574a39f13863b6b2b47a8016704f1f28cd6e66a01`.
The capture-10 baseline file SHA-256 is
`e768c39b2f4a70aeb80b992f7363317d71e43a1758242049d30ba485b79f1f84`
and its self-digest is
`8ae6e8ee91ae76af8713e0a93f4c8c54b3f2fbdd33b30787616f9a73a9d17da8`.
Collection recorded `5455` unique nodes with exit `0`; JUnit contains exactly the
same `5455` unique cases and records `5432` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `70` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes are the replacement candidate
were rejected by specification review for tree `8c50190d` / patch `484a779a`
under `TASK1-SPEC-REJECT-20260717-8C50190D-05`. The single confirmed blocker was
that review-phase verification accepted a new undeclared untracked path created
after a valid review envelope: declared inventories and staged rows were checked,
but the complete live Git-status set was not. Capture 10 and its baseline were
invalidated and deleted. The replacement review verifier parses complete
porcelain-v2 status, retaining both origin and destination for rename/copy rows,
and requires exact equality with the status map derived from launch dirty
authorities, explicitly reviewed post-launch transitions, and staged task rows
before checking patch/tree identity. Permanent tests prove that a valid mixed
review with a staged task plus allowed unstaged plan transition passes, while a
post-envelope untracked file and a staged rename both reject. Reviewed allowed
transitions accept exact staged, unstaged, or untracked status rather than being
misclassified as staged-only. Capture 11 must be generated after these helper and
test bytes freeze. No new review verdict is claimed here, and the implementing
agent does not stage or commit them.

The frozen capture-11 helper file SHA-256 is
`f5ec777151b38a456b26115c6aee34f0767c3ec1ffa324e79b2a75dd05278ce8`
and its permanent test-module SHA-256 is
`9abcc543bcb5fd587a8eed14b84440fdfba393f8e3d0743b90bccb7814215bbd`.
The capture-11 subject file SHA-256 is
`98e14c464a06ddad168919a633f329355f44cb989f58ac1708eab7074edbe30f`
and its self-digest is
`8551d8ec5f0647a2f44e966a94839b521d8cb40f1c7d0e4c96e30bac20865c30`.
The capture-11 baseline file SHA-256 is
`e1c3971484580444085ee62930cde561f5b0ed98cff4e25328f77c14b1f2f0b6`
and its self-digest is
`35d8b5000785fdfe22fa07b6489fefc9660ea8cf0f1479a10696f221daf8258d`.
Collection recorded `5457` unique nodes with exit `0`; JUnit contains exactly the
same `5457` unique cases and records `5434` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `72` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes are the replacement candidate
received ordered specification PASS
`TASK1-SPEC-PASS-20260717-F36CFCC9-06`, then quality REJECT
`TASK1-QUALITY-REJECT-20260717-F36CFCC9-01` on the unchanged tree/patch. The
single confirmed blocker was filesystem type closure: ignored-evidence inventory
accepted symlinks, and a supplied generated-evidence path could be loaded through
a symlink without an independent `lstat` regular-file gate. Capture 11 and its
baseline were invalidated and deleted. The replacement inventory uses `lstat`
and requires `S_ISREG` for every present declared ignored-evidence member; the
supplied generated-evidence path independently receives the same non-symlink
regular-file check before JSON loading or binding. Permanent RED/GREEN cases
cover symlinks to valid in-repository and external targets plus declared directory
and FIFO leaves. Existing absent-to-regular transition and no-clobber coverage
remains green. Capture 12 must be generated only after these helper/test bytes
freeze, then both ordered reviews restart. No new review verdict is claimed here,
and the implementing agent does not stage or commit them.

The frozen capture-12 helper file SHA-256 is
`ffc25fa423b460075bb0b1e90be04df0d0c9675fdde35324f981b937808a974f`
and its permanent test-module SHA-256 is
`bc4fc423409b8d26b7e0c08a48c6950dd0efea626a2643cb69fd7e83dbc0096f`.
The capture-12 subject file SHA-256 is
`0fc5ab77672f69585da3a12f086252eef4713ea03e4b79258ef2daa1b2685c6f`
and its self-digest is
`2496c9eeeaef07afcc7c9fc7c054f933218b111856d1e8973be206caa9a521eb`.
The capture-12 baseline file SHA-256 is
`ad1d8141e95feea294b4fb3c1be716a606fca5b941cde5296a0a6bff9f0ccd85`
and its self-digest is
`277baf51c7df8b41886ec7277dace509b7d47c74a48bc1b5efe4480460e0bbce`.
Collection recorded `5461` unique nodes with exit `0`; JUnit contains exactly the
same `5461` unique cases and records `5438` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `76` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes are the replacement candidate
were rejected by specification review for tree `ce87fd07` / patch `a7345ef2`
under `TASK1-SPEC-REJECT-20260717-CE87FD07-07`. The single confirmed blocker was
that complete inventory and totals reconciliation did not bind the broad failing
node IDs to the exact six authority/isolated `failure_rows`: a same-count swap
could make one authority case pass and one unrelated collected case fail. Capture
12 and its baseline were invalidated and deleted. Permanent RED/GREEN tests cover
that swap independently through `build_baseline` and a resealed standalone
baseline while keeping totals and all isolated rows unchanged. Both builder and
validator now require the broad JUnit failing-node set, evaluated against the six
authority node IDs, to equal the exact failure-row node set. Capture 13 must be
generated after these helper/test bytes freeze, then ordered reviews restart. No
new review verdict is claimed here, and the implementing agent does not stage or
commit them.

The frozen capture-13 helper file SHA-256 is
`74cac3c8a37e5efbaa1b4aa08c07132f80886b4f9933ca05922373e05f30d1e6`
and its permanent test-module SHA-256 is
`b651b58a999c724f3fdb766b6c0e3535efa682afdf87e51f1ce74b71250b1487`.
The capture-13 subject file SHA-256 is
`643c07aedfe2e3baf864ed9a5d9c8d50bd9a79bdd6f0b9e319cce557feac8181`
and its self-digest is
`4a264b383bdec897e6bf8e964374f144cf3069e366a2d98e0beec53030e45b5d`.
The capture-13 baseline file SHA-256 is
`41493dde39227b0b28ee77bcab8823a6c37afc82d00a9f8ec003613bed433861`
and its self-digest is
`a6b6a3b208b3a11a1ab57d51e08752e37ffe889abbbf60bb88f0d7b61acf4edf`.
Collection recorded `5463` unique nodes with exit `0`; JUnit contains exactly the
same `5463` unique cases and records `5440` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `78` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes received ordered specification
PASS `TASK1-SPEC-PASS-20260717-A453FBC2-08`, then quality REJECT
`TASK1-QUALITY-REJECT-20260717-A453FBC2-09` on the unchanged tree/patch. The
single confirmed blocker was ignored-evidence root namespace closure: the
declared root itself could be replaced by a symlink to an in-repository or
external directory, after which leaf `lstat` gates enumerated and loaded the
redirected namespace. Capture 13 and its baseline were invalidated and deleted.
The replacement root resolver walks each repo-relative component from the
repository root through the declared ignored-evidence root with `lstat` and
requires every present component to be a real non-symlink directory. Absence is
permitted only for capture prepublication, while verification requires the
complete real-directory chain; ancestors outside the repository boundary are
not inspected. Permanent RED/GREEN cases cover an ordinary root, an
in-repository root symlink, an external root symlink, and an intermediate
symlink component. The focused matrix records `4` passes and the complete helper
module records `82` passes. Capture 14 must be generated only after these
helper/test/plan bytes freeze, then ordered reviews restart. No new review
verdict is claimed here, and the implementing agent does not stage or commit
them.

The frozen capture-14 helper file SHA-256 is
`eace5282fbb8207471fd02dc47d99a3bed4ee71c34ba33349c5f7eb844736fc9`
and its permanent test-module SHA-256 is
`27218fe57351d0152af47a502f7bc48ce70bc27cbad0a71b82a77c727ea518f1`.
The capture-14 subject file SHA-256 is
`3fe71d50235f90b4484a10e1f652ce9bf9465f8a911291b7db41b032fbaf0926`
and its self-digest is
`e51dc38333a1750c3c9101ae20253523d37e8944d64bacae64cb42068a90be18`.
The capture-14 baseline file SHA-256 is
`b53cea6c53ec6051fa8d1b920922462d7ca71ec521d601f18b1df424a02f2e6d`
and its self-digest is
`0d02b62f7007f4e72c663305356a1b0006b4ce6a14732e391fc2b1586bae152d`.
Collection recorded `5467` unique nodes with exit `0`; JUnit contains exactly the
same `5467` unique cases and records `5444` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `82` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes are the replacement candidate
were rejected by specification review for tree `54b55b4a` / patch `c97a4725`
under `TASK1-SPEC-REJECT-20260717-54B55B4A-09`. The two coupled blockers were
that Task 10 prescribed a literal `validate-frozen-overlay` operation absent
from the helper CLI and the direct frozen-overlay validator accepted staged
index drift because it syntax-checked, but did not compare, the captured index
tree. Capture 14 and its baseline were invalidated and deleted. The replacement
CLI accepts required `--overlay`, loads the closed record, and validates its
HEAD, exact current index tree, selected live rows, and record bytes. Subject
verification deliberately checks the overlay index against the subject launch
index because its separately closed review envelope may later stage non-overlay
task paths; the existing launch and review tree gates continue to bind the
current index. Permanent RED/GREEN tests cover the literal CLI positive case,
direct mismatched-current-index rejection, and the legitimate staged-plan review
boundary. A plan-prescribed command table also literal-parses all `11` helper
operations named by this plan so another absent operation rejects permanently;
no unused command was added. The complete helper module records `95` passes.
Capture 15 must be generated only after these helper/test/plan bytes freeze,
then ordered reviews restart. No new review verdict is claimed here, and the
implementing agent does not stage or commit them.

The frozen capture-15 helper file SHA-256 is
`1473354e2c40829061fb281350d97e779117691d106c2a86cedbb485d9163ca7`
and its permanent test-module SHA-256 is
`e9de84fbafe7b81d098b1942c9ff70778d1f119ea3c0f0137081fe93b83560d9`.
The capture-15 subject file SHA-256 is
`e53647cfaada8830a6600d4fbbbdd50af642a3a4542ea18460a7e6b01392edb3`
and its self-digest is
`c307b9f9fa000bcbf18cfb99b506690f64631cf8a4466d20c6a273ecb9891a66`.
The capture-15 baseline file SHA-256 is
`3d71df6eb7777db7af96ec9271a259078aa307cfbd5da71d7c4a6bc96f6426d0`
and its self-digest is
`d6677f99da9ba471696cd2b47d38397881ec9a50eea69a56807d38a592df3b90`.
Collection recorded `5480` unique nodes with exit `0`; JUnit contains exactly the
same `5480` unique cases and records `5457` passed, `6` failed, `17` skipped,
`0` errors, `0` xfailed, `0` xpassed, and exit `1`. All six authority rows exit
`1` alone and all `18` isolated artifacts are present. Post-build verification
records `56` provider-policy passes, `95` helper-gate passes, `1` keyword-free
baseline pass, standalone baseline validation, and final launch-transition plus
generated-evidence verification. These exact bytes are the replacement candidate
for restarted ordered specification then quality review; no new review verdict
is claimed here, and the implementing agent does not stage or commit them.

## Task 2: Add Typed Frontend Syntax

**Owner:** fresh frontend implementer after the reviewed Task 1 commit.

**Files:**

- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc`
- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/procedure_loop.orc`
- Modify `tests/test_workflow_lisp_provider_prompt_dependencies.py`
- Modify `orchestrator/workflow_lisp/expressions.py`
- Modify `orchestrator/workflow_lisp/expression_traversal.py`
- Modify `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify `orchestrator/workflow_lisp/functions.py`
- Modify `orchestrator/workflow_lisp/procedure_specialization.py` only if its
  explicit rebuild otherwise drops the new spec
- Modify `orchestrator/workflow_lisp/workflow_refs.py`
- Modify `orchestrator/workflow_lisp/wcc/route.py`
- Modify this plan

- [x] **Step 1: Write parser and closed-shape RED tests.**

Cover required-only, optional-only, mixed, default prepend, authored instruction,
duplicate/unknown nested keys, empty lists/clause, invalid position, dynamic
instruction, and 261629/261630/261631 UTF-8-byte instruction boundaries. Assert
stable diagnostic codes and source spans, not message prose.

Run:

```bash
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k 'parser or instruction'
```

Expected: FAIL because `:prompt-dependencies` is rejected.

- [x] **Step 2: Implement immutable syntax and parsing.**

Add `PromptDependencySpec(required, optional, position, instruction, span,
form_path, expansion_stack)` and an omit-if-none field on `ProviderResultExpr`.
Parse the nested list as a closed keyword form, preserve authored indices and
operand spans, reject the private generated-relpath literal as an authoring route,
and enforce instruction bytes with strict UTF-8.

- [x] **Step 3: Write type/effect/inline-lowerability RED tests.**

Accept only `PathTypeRef` whose definition has `kind == "relpath"`. Reject String,
path-looking String, primitive, Optional, List, Map, Record, union field not
resolved to relpath, provider/prompt extern, literal, effectful operand, and a
synthetic nested-loop form. Prove eligible workflow/procedure params, aliases,
loop-carried relpath fields, and relpath result fields. Inline-lowerability is
`NameExpr`/`FieldAccessExpr` plus zero direct and transitive effects; procedure-edge
metadata alone is not an effect.

Run the focused selector and expect failures for missing type rules.

- [x] **Step 4: Implement typechecking and effect aggregation.**

Recurse over every row, use a distinct `prompt_dependency_operand_type_invalid`
diagnostic before the inline-lowerability diagnostic, preserve each typed summary,
and merge them into the provider effect summary without creating a new effect.

- [x] **Step 5: Write and satisfy traversal/normalization/specialization/WCC-route
  RED tests.**

Prove `iter_child_exprs`, pure-function normalization, imported inline-procedure
specialization, binding substitution, dependency discovery, and every supported
WCC route retain both partitions and policy. Test behavior rather than dataclass
field enumeration. Add
`test_prompt_dependency_generic_mechanism_has_no_concrete_identity_branch`, a
permanent added-line guard over the exact production path set and forbidden
identities enumerated in Task 11. Add
`test_prompt_dependency_genericity_added_line_extractor_rejects_leading_plus_identity`
with a synthetic patch containing both an exact `+++ b/path` header and an added
source line whose content begins `+codex`; require only the header to be excluded
and the source line to fail the identity scan.

- [x] **Step 6: Run collection and focused regression.**

```bash
pytest --collect-only -q tests/test_workflow_lisp_provider_prompt_dependencies.py
pytest --collect-only -q tests/test_provider_prompt_dependency_broad_gate.py
pytest -q tests/test_provider_prompt_dependency_broad_gate.py
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py
pytest -q tests/test_workflow_lisp_provider_call_policy.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_wcc_m4.py
```

Expected: collection succeeds; all selected tests pass.

- [x] **Step 7: Freeze the review subject and dispatch the ordered reviews.**

Apply the digest-stable protocol above. Commit only after both reviewers PASS the
unchanged `REVIEW_TREE`.

Suggested commit: `feat: add typed prompt dependency syntax`

The first Task 2 candidate at review tree `97bf1df6` / patch `fb92e6fa` was
rejected under `TASK2-SPEC-REJECT-20260717-97BF1DF6-01`. Its fixture only
inspected an original same-file procedure body and therefore did not prove that
an imported call's relpath binding, specialization metadata, typed effect
summary, both dependency partitions, policy, and generic child traversal survive
on the specialized owner. It also lacked an explicit resolved union-field
non-relpath precedence case. That launch subject is invalid. The replacement
uses the supported imported-call route plus the public specialization and generic
expression-traversal owners; no prompt-dependency production drop was exposed,
so `procedure_specialization.py` and `workflow_refs.py` remain unchanged.

The replacement Task 2 candidate at review tree `cc40751d` / patch `3a75e971`
was rejected under `TASK2-SPEC-REJECT-20260717-CC40751D-02`. It proved the
negative synthetic nested-loop rejection but did not prove the required positive
supported loop-carried relpath case. That launch subject is invalid. The next
replacement adds an ordinary `loop/recur` whose carried record exposes required
and optional relpath fields directly to a provider prompt dependency. Behavioral
coverage proves both fields resolve to `PathTypeRef(kind=relpath)`, the two
partitions and authored policy survive, the typed provider summary remains, and
the complete loop passes the Task 2-owned WCC M4 support validator. No production
drop was exposed, so the repair changes only the fixture and test in addition to
this rejection record; it does not enter Task 3 lowering.

## Task 3: Preserve WCC And Lower Through One Typed Owner Side Table

**Owner:** fresh compiler/lowering implementer.

**Files:**

- Modify `tests/test_workflow_lisp_provider_prompt_dependencies.py`
- Modify `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify `orchestrator/workflow_lisp/lowering/context.py`
- Modify `orchestrator/workflow_lisp/lowering/effects.py`
- Modify `orchestrator/workflow_lisp/lowering/core.py`
- Modify `orchestrator/workflow_lisp/lowering/origins.py`
- Modify `orchestrator/workflow_lisp/lowering/procedures.py` so manually-created
  inline-procedure child contexts share the Task-3-owned contract and lineage
  collectors rather than dropping their results
- Modify `orchestrator/workflow_lisp/source_map.py`
- Create `orchestrator/workflow/prompt_dependency_contract.py`
- Modify this plan

- [x] **Step 1: Write WCC round-trip RED tests.**

Assert WCC preserves each typed value, row role/index, authored ordering, position,
instruction, clause/row spans, form paths, and expansion stacks. Exercise root,
inline procedure, loop body, and the frontend-expression reconstruction used by
loop lowering. Compare WCC and classic output at the normalized owner boundary.

Expected: FAIL because WCC does not carry the spec.

- [x] **Step 2: Implement WCC payload and reconstruction.**

Keep `WccPerform.operation_payload` as the operation-specific owner. Store closed
typed row records rather than YAML strings, and reconstruct `PromptDependencySpec`
before `LowerableProviderResult` reaches the shared emitter. Do not add a new WCC
node or schema.

- [x] **Step 3: Write typed contract and digest RED tests.**

Specify enums with no public string coercion and a frozen
`CompilerPromptDependencyContract`. Assert canonical digest over exactly
`{schema, required_binding_refs, optional_binding_refs, position,
instruction_utf8_sha256_or_null}` with authored array order. Reject empty refs,
unknown enum strings, mappings passed where a dataclass is required, source digest
syntax errors, empty origin, extra keys, and digest mismatch.

- [x] **Step 4: Implement the typed contract module.**

Provide canonical JSON with `sort_keys=True`, compact separators,
`ensure_ascii=True`, no newline, and `sha256:<lowercase-hex>`. Keep construction
private to the lowering/shared-validation route; expose validation/serialization,
not a permissive `from_mapping` public API.

- [x] **Step 5: Write owner-emitter and side-table RED tests.**

The emitted provider mapping contains only ordinary `depends_on` with runtime
binding templates and `inject: {mode: content, position, instruction?}`. The typed
contract is stored separately on `LoweredWorkflow.compiler_prompt_dependency_contracts`
under the stable provider step ID. Assert source SHA-256 equals the exact accepted
`.orc` bytes and `source_origin_key` resolves to the provider step/operand source
map. Assert classic and WCC produce identical mappings/contracts/digests.

- [x] **Step 6: Implement one owner projection.**

Extend `LowerableProviderResult`. Resolve each operand through existing inline
value/reference rendering; fail if it cannot become one existing binding ref.
Build exact `depends_on` and the typed side-table entry in
`_lower_provider_result_operation`. Have both lowering routes call only this owner.

- [x] **Step 7: Add source-map clause/row/policy lineage.**

Add a closed prompt-dependency lineage section under each workflow source map.
Bind the clause, each authored row/ref/role/index, position, and instruction to
source origins. Validate duplicate/missing origin keys and ensure the typed
contract's origin exists.

- [x] **Step 8: Run focused verification, freeze the review subject, and dispatch
  the ordered reviews.**

```bash
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k 'wcc or lowering or contract or source_map'
pytest -q tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_provider_call_policy.py
```

Suggested commit: `feat: lower typed prompt dependency contracts`

## Task 4: Carry And Authenticate Shared Typed IR Without Widening YAML

**Owner:** fresh shared-IR implementer.

**Files:**

- Modify `tests/test_workflow_lisp_provider_prompt_dependencies.py`
- Modify `tests/test_loader_validation.py`
- Modify `tests/test_workflow_lisp_build_artifacts.py`
- Modify `tests/test_persisted_workflow_surface.py`
- Modify `tests/test_dashboard_compiled_workflow.py`
- Modify `tests/workflow_bundle_helpers.py`
- Modify `orchestrator/workflow/validation.py`
- Modify `orchestrator/workflow/elaboration.py`
- Modify `orchestrator/workflow/surface_ast.py`
- Modify `orchestrator/workflow/core_ast.py`
- Modify `orchestrator/workflow/lowering.py`
- Modify `orchestrator/workflow/executable_ir.py`
- Modify `orchestrator/workflow/runtime_step.py`
- Modify `orchestrator/workflow/semantic_ir.py`
- Modify `orchestrator/workflow/persisted_surface.py`
- Modify `orchestrator/dashboard/compiled_workflow.py`
- Modify `orchestrator/workflow_lisp/build.py`
- Modify `orchestrator/workflow_lisp/build_artifacts.py`
- Modify `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify `orchestrator/workflow_lisp/lowering/core.py` (adjacent request-plumbing
  owner required to pass the compiler-owned side table into shared validation)
- Modify this plan

**2026-07-17 user scope override:** the user explicitly directed execution to
"skip security." For Task 4, this removes all adversarial authentication,
provenance, private-lookalike rejection, build-anchor, and tamper-enforcement
work. Steps 5-6 are therefore recorded as skipped, and the authentication-only
portions of Steps 7-8 are skipped. Functional typed side-table reconciliation,
transport through the shared IRs, closed persisted member encoding/decoding,
omission compatibility, runtime-plan byte identity, and checkpoint identity
remain required. YAML receives no compiler side-table capability, but this task
does not reject private-looking YAML keys. These reduced claims do not satisfy
the approved design's security boundary and any later restoration is a separate
hardening migration.

- [x] **Step 1: Write typed side-table reconciliation RED tests (functional
  scope).**

Extend `WorkflowMappingBuildRequest` with a typed mapping keyed by stable step ID.
Test exactly one matching Workflow Lisp provider step; reject missing/extra keys,
wrong step kind, duplicate association, non-dataclass values, and frontend kind
absent or YAML. The authored mapping never contains a contract marker. Source-file
digest, source-map-origin, and normalized-digest authentication cases are skipped
by the user scope override.

- [x] **Step 2: Implement validation/elaboration attachment.**

Pass the side table explicitly from `LoweredWorkflow`; attach only after stable
step IDs exist. Surface AST carries the typed optional field. YAML loader requests
have no capability/table and cannot create it.

- [x] **Step 3: Write Core/executable/RuntimeStep/Semantic RED tests.**

Assert typed dataclass identity survives Core and executable lowering; invalid
typed values fail `validate_executable_workflow`; RuntimeStep exposes a typed
accessor but no thawed public key; Semantic prompt surface includes normalized
typed refs/policy/origin. Assert `runtime_plan` contains none of these fields and
its golden bytes remain identical.

- [x] **Step 4: Implement each owned IR view.**

Add optional fields with omission semantics. Do not globally bump Semantic IR;
validate/document the additive optional member. Do not add dependency config to
runtime plan or state projection. Name the byte-identity regression
`test_prompt_dependency_absence_keeps_runtime_plan_bytes_exact` so the final
source-guard tranche can invoke it directly.

- [x] **Step 5: Skipped by user scope override — YAML reserved-lookalike
  rejection RED tests.**

For YAML/YML, reject `compiler_prompt_dependency_contract`,
`path_interpretation`, `evidence_required`, and origin/digest lookalikes at the
step, `depends_on`, and `depends_on.inject` levels. Characterize every currently
valid legacy `depends_on`/`inject` form before changing validation; this task
reserves the private compiler namespace but does not broadly tighten unrelated
legacy extension-key behavior.

- [x] **Step 6: Skipped by user scope override — explicit private-namespace
  rejection.**

Keep `required`, `optional`, and `inject` compatibility, including the existing
boolean and public mapping forms. Reject the reserved private keys at each
accepted nesting level before elaboration. Do not add a public `exact` or
`origin_kind` string, and do not use this security boundary to reject unrelated
legacy keys that the pre-feature schema accepted.

- [x] **Step 7: Write functional persisted transport RED tests; skip
  authentication tests by user scope override.**

Presence round-trips the closed typed member and unknown/partial wire fields
remain rejected. Absence continues to decode with the old call shape and exact
bytes. Workflow-Lisp provenance, build fingerprint/anchor, source and source-map
authentication, tamper, and hand-built-mapping adversarial cases are skipped.

- [x] **Step 8: Implement functional persisted decode; skip authenticated
  decode by user scope override.**

Add a dedicated closed member to `PersistedSurfaceStep` and reconstruct the typed
contract during decode. Omit the member entirely when no contract exists so the
keyword-free persisted surface stays byte-identical. Authentication context,
manifest anchor, dashboard provenance validation, and authenticated build-time
reopen are skipped.

- [x] **Step 9: Bind checkpoint identity (functional scope).**

Add serialized typed contract to `_provider_prompt_input_contract_digest`. Prove
required/optional membership, position, instruction, origin, or normalized digest
drift rejects completed-effect reuse, while post-completion content drift does not.

- [x] **Step 10: Run selectors, freeze the review subject, and dispatch the
  ordered reviews.**

Execution checkpoint: all three adjusted functional selectors passed, as did the
complete provider-prompt-dependency module. The candidate capture then passed both
ordered reviews and committed at reconstructed
`6fa32d0deaa65d583f758a08f51958c5d04e6189`.

```bash
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k 'shared_ir or persisted or checkpoint or keyword_free or absence_keeps_runtime_plan or side_table'
pytest -q tests/test_loader_validation.py tests/test_persisted_workflow_surface.py tests/test_dashboard_compiled_workflow.py
pytest -q tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lexical_checkpoints.py tests/test_workflow_lisp_lexical_checkpoint_restore.py
```

Suggested commit: `feat: carry prompt dependency IR`

## Task 5: Implement Exact Content Rendering And Stable YAML Compatibility

**Owner:** fresh renderer implementer.

**Files:**

- Create `tests/test_prompt_dependency_content_snapshot.py`
- Modify `tests/test_dependency_injection.py`
- Modify `tests/test_dependency_resolution.py`
- Create `orchestrator/deps/content_snapshot.py`
- Modify `orchestrator/deps/resolver.py`
- Modify `orchestrator/deps/injector.py`
- Modify `orchestrator/deps/__init__.py`
- Modify this plan

- [x] **Step 1: Write immutable classified-row and alias-group RED tests.**

Define authored rows with role/index/binding/evaluated relpath and snapshots with
absent rows plus canonical groups. Prove required-before-optional evidence order,
canonical target sorting, lexical/symlink alias de-duplication, required-wins, and
optional-only no-match default selection. At this task boundary, feed verified
in-memory file payloads; safe filesystem acquisition belongs to Task 6. Include an
adversarial many-group case whose aggregate input is many times the injection cap
and prove retained dependency-content bytes across the complete immutable snapshot
never exceed the single attempt-wide budget. Metadata may remain one bounded row/
group record per authored input; independent cap-sized content buffers per group
are forbidden.

- [x] **Step 2: Implement pure snapshot grouping models.**

Use frozen dataclasses/tuples. Validate roles, contiguous indices, safe canonical
POSIX targets, group membership, and uniqueness. Never collapse authored aliases
before evidence metadata exists.

- [x] **Step 3: Write exact cap RED tests.**

Cover instruction byte lengths 261629/261630/261631; multibyte boundaries;
pre-truncation sizes 262143/262144/262145; first partial group; no-positive-prefix
omission; no later group after truncation; an adversarial number of distinct
canonical groups before and after budget exhaustion; exact 512-byte summary;
rejected 513-byte summary; exact headers, markers, separators, and final block
assertion.

- [x] **Step 4: Implement the pure renderer.**

Define `MAX_INJECTION_BYTES=262144`,
`TRUNCATION_SUMMARY_RESERVE_BYTES=512`, and
`MAX_INSTRUCTION_BYTES=261630`. Budget encoded bytes exactly, choose only strict
UTF-8 prefixes, and return immutable block bytes plus full per-group truncation
metadata. `DependencyInjector` content mode consumes this result; list mode stays
unchanged.

- [x] **Step 5: Write stable-YAML differential RED tests.**

Against a local characterization copy of the prior successful renderer, compare
exact prompt bytes below the new cap for required-only, optional-only, mixed
required/optional, lexicographic order, custom instruction, prepend/append,
optional no-match, CRLF, and lone CR. Spy on default-instruction selection rather
than asserting production text. Boundary tightenings are asserted separately.

- [x] **Step 6: Implement classified legacy resolution without exact-mode glob
  reuse.**

Legacy YAML still expands globs and produces classified resolved rows. Typed exact
rows reject glob magic and never call `glob.glob`. Both feed the same renderer.

- [x] **Step 7: Run focused verification, freeze the review subject, and dispatch
  the ordered reviews.**

```bash
pytest --collect-only -q tests/test_prompt_dependency_content_snapshot.py
pytest -q tests/test_prompt_dependency_content_snapshot.py -k 'render or cap or compatibility'
pytest -q tests/test_dependency_injection.py tests/test_dependency_resolution.py tests/test_injection_integration.py
```

Suggested commit: `refactor: render immutable dependency snapshots`

## Task 6: Implement Descriptor-Relative Stable Reads And Platform Preflight

**Owner:** fresh filesystem-security implementer.

**Files:**

- Modify `tests/test_prompt_dependency_content_snapshot.py`
- Create `orchestrator/deps/safe_io.py`
- Modify `orchestrator/deps/content_snapshot.py`
- Modify `orchestrator/deps/injector.py`
- Modify `orchestrator/deps/__init__.py`
- Modify this plan

- [x] **Step 1: Skipped by user scope override — exact-path validation and
  real-platform probe tests.**

Reject undefined/residual `${...}`, NUL, backslash, empty/dot, absolute, `..`, and
each of `*`, `?`, `[`. On the actual POSIX test filesystem prove descriptor-
relative open/stat/readlink/link/unlink, flags, FIFO nonblocking behavior,
file/directory fsync, hard-link no-clobber, flock, identity fields, cache key, and
probe cleanup. Force each negative capability independently. On non-POSIX, assert
stable `unsupported_safe_read_platform` before any dependency open.

- [x] **Step 2: Skipped by user scope override — operational preflight.**

Cache only complete success or stable negative result per `(workspace st_dev,
aggregate run-root st_dev)` and process. Record booleans/platform/devices/failure
code only, never host paths. Probe creates private entries under both roots and
cleans every probe entry before returning. It must not touch allocator state.

For a fresh typed run, the command boundary may create the already selected
aggregate run-root directory and any required parent directories before
`StateManager.initialize` solely so the operational probe can obtain the run-root
device and create its private probe directory. That directory creation is not
`RunState` initialization. Before successful preflight there may be no
`state.json`, `logs/`, `.state-mutation.lock`, prompt-dependency evidence tree,
allocator member, retry/session mutation, or provider side effect. On every probe
exit, success or failure, remove and directory-`fsync` all private probe entries.
To avoid a racy ownership/delete protocol, an aggregate run root created for the
probe may remain only as an empty directory after probe failure; required parent
directories may likewise remain empty. No other entry or semantic run record may
remain. Tests must cover both a pre-existing root and this exact empty-root
residue. `StateManager.initialize` may reuse the empty root only after a complete
successful probe.

- [x] **Step 3: Skipped by user scope override — component-walk and symlink
  tests.**

Cover safe relative and safe absolute in-workspace symlinks, escape, broken link,
hop bound, parent swap before final open, parent swap after open, alias retarget,
delete between phases, direct optional ENOENT versus post-symlink ENOENT, and
component identity changes. Assert safe relative diagnostics only.

- [x] **Step 4: Skipped by user scope override — trusted descriptor walk.**

Open the workspace with required flags, resolve components using dir-fd
operations, retain directory identity tuples, open the final component with
`O_NONBLOCK|O_NOFOLLOW`, require regular file, re-resolve aliases, and compare
component/final identity before read and after read. Close every descriptor on
every exit.

- [x] **Step 5: Skipped by user scope override — streaming-read security tests.**

Cover FIFO without hang, directory, socket, controlled device-mode `fstat`,
unreadable open, invalid UTF-8 including chunk boundary, CRLF/lone-CR across chunk
boundaries, raw/normalized digests and totals, mutation of every stat field,
post-read alias swap, very large file memory bound, and injected read failure. Add
an instrumented adversarial case with many distinct near-cap canonical targets:
the retained snapshot-content high-water mark across the whole attempt must remain
within one global injection budget, not one budget per target; the separate
decoder/read-buffer high-water mark must remain fixed as target count grows. Assert
every target is nevertheless read to EOF and its full raw and normalized counts/
digests validate after the global retention budget reaches zero.

- [x] **Step 6: Skipped by user scope override — stable descriptor-relative
  streaming acquisition.**

Hash raw descriptor bytes, strictly incrementally decode, normalize newlines,
hash normalized full content, and consume one shared attempt-wide retained-content
budget across canonical groups, then repeat all file/directory/alias identity
checks. Once that global budget is exhausted, retain no more content bytes but
continue streaming every selected file to EOF for strict UTF-8 validation, full
raw/normalized counts, and digests. Fixed decoder/read buffers do not count as
retained snapshot content and may not grow with group count. Optional weakens
absence only. Return stable failure categories/operations; never raw errno prose
or absolute paths.

- [x] **Step 7: Skipped by user scope override — descriptor-owner/source-guard
  proof.**

Instrument open/read calls: one final descriptor stream per canonical target;
renderer and evidence-data construction use only the immutable snapshot. Add the
AST/source guard
`test_content_snapshot_owner_has_no_pathname_content_reader`, covering
`safe_io.py`, `content_snapshot.py`, and content-mode code in `injector.py`; it
must reject `Path.read_text`, built-in pathname `open`, or any reopen outside the
descriptor-relative owner while permitting list-mode logic that does not read
content.

- [x] **Step 8: Skipped by user scope override — Task 6 security verification
  and reviews.**

```bash
pytest -q tests/test_prompt_dependency_content_snapshot.py -k 'safe or platform or symlink or fifo or utf8 or changed or newline'
pytest -q tests/test_dependency_injection.py tests/test_dependency_resolution.py
```

Positive platform tests must exercise the actual filesystem, not mocked flag
presence. Suggested commit: `feat: harden prompt dependency reads`

## Task 7: Add Durable Root Allocation And Cross-Process Locking

**Owner:** fresh state/concurrency implementer.

**Files:**

- Create `tests/test_provider_attempt_allocation.py`
- Create `orchestrator/state_locking.py`
- Create `orchestrator/workflow/provider_attempts.py`
- Modify `orchestrator/state.py`
- Modify `orchestrator/workflow/call_frame_state.py`
- Modify `orchestrator/workflow/executor_runtime.py`
- Modify `orchestrator/workflow/executor.py`
- Modify `orchestrator/cli/commands/run.py`
- Modify `orchestrator/cli/commands/resume.py`
- Modify `tests/test_cli_safety.py` (Task 11 broad-regression repair)
- Modify `tests/test_cli_observability_config.py` (Task 11 broad-regression
  repair)
- Modify this plan

- [x] **Step 1: Write omitted-state and durable-write RED tests.**

Assert old states load and serialize byte-compatible with no allocator member.
Once affected, every root write uses `.state-mutation.lock`, short-write handling,
file fsync, atomic replace, and parent-directory fsync. Inject open/write/fsync/
replace/dir-fsync failures and prove no false durability claim.

- [x] **Step 2: Implement generic state locking/durable writer (functional
  scope).**

Enable it explicitly for typed-contract runs and automatically when a loaded state
has non-empty allocator data. Ordinary unaffected runs retain existing bytes and
avoid creating a lock. Descriptor-specific path/open validation, no-follow
hardening, and symlink defenses are omitted by the user scope override; this step
implements ordinary cross-process locking and file- plus directory-synced durable
writes only. One generic detector walks the executable bundle/import graph and
enables this coordination at the command boundary before an affected manager's
first state mutation; it is allocator enablement, not platform preflight.

- [x] **Step 3: Write aggregate-owner resolution RED tests.**

Cover root; one- and two-level calls; loop in call; mismatched run ID/workspace
device/root; wrong deterministic call-frame root; cycle; non-StateManager
terminal; missing/swapped/truncated/extended `ResumeScopePath`; malformed nested
RunState; and a nested manager attempting independent allocation.

- [x] **Step 4: Implement `resolve_aggregate_run_owner`.**

Walk `parent_manager` identity-safely, validate every hop, return terminal root,
ordered scope path, leaf state, and aggregate root. Recursively verify call-frame
snapshots and delegate all writes exactly once through the root.

- [x] **Step 5: Write closed `ProviderAttemptScope` RED tests.**

Cover direct provider, for-each, repeat-until, loop in call, two-level call, and
adjudicated candidate. Bind exact runtime step/enclosing step/visit/iteration
fields. Reject missing/extra/nullable/wrong types, current-step contradictions,
zero visit, nested-loop shape, bad candidate ID, and local retry index leakage.

- [x] **Step 6: Implement canonical scope and allocator projection.**

Key scopes by full SHA-256 canonical JSON. Store complete scope,
`last_allocated_ordinal`, and ordered closed events. Validate all persisted input
before increment. Allocation ordinals are exactly contiguous through
`last_allocated_ordinal`; allocation-only publication gaps are valid. Persisted
events are canonical by ordinal, with each allocation immediately followed by its
optional publication; duplicate, noncanonical, or conflicting events are not.

- [x] **Step 7: Write allocation/publication-event crash RED tests.**

Fault before durable allocation, after allocation, and during the later
publication-event transition. Prove same next integer only before durability,
strictly larger afterward, and no evidence-directory enumeration.

- [x] **Step 8: Implement sole root allocator/event writers.**

Lock order is state-mutation flock, aggregate-evidence flock, then root in-process
`RLock`; release reverse. Allocation and the later publication-manifest event
both take all three locks. Ordinary unrelated root-state writes take the first
and third locks, skipping the middle; record-only publication takes the first two
and may not acquire the third while retaining them. Persist before returning an
ordinal/event success. Publication calls may arrive in any allocated-ordinal
order; under the locks, insert each event beside its allocation so the durable
projection remains canonical rather than chronological.

- [x] **Step 9: Skipped by user scope override — depends entirely on excluded
  Task 6 platform preflight.**

For fresh typed `.orc`, preflight occurs after bundle/run-root resolution but
before `StateManager.initialize`, `state.json`/`logs`/lock/evidence creation,
retry advancement, or session mutation. The only permitted earlier filesystem
mutation is creation of the selected aggregate root/parents and private probe
entries under the Task 6 lifecycle above. Probe failure removes every private
entry and leaves at most the specified empty aggregate root/parents; allocator,
state, logs, evidence, session, and provider remain absent. For resume and
force-restart, preflight occurs before any affected root-state write. Legacy YAML
preflights before its first content snapshot but need not precede initialization.

- [x] **Step 10: Skipped by user scope override — depends entirely on excluded
  Task 6 platform preflight.**

Use one helper that detects typed contracts recursively in the loaded bundle. Do
not duplicate scan logic in run and resume. Preserve dry-run as no run-state
mutation while still validating the compiled contract. The helper owns the
fresh-root preparation boundary: it may create/reuse the empty aggregate root,
runs the probe, enforces cleanup/residue, and returns capability success before
the caller can initialize state. Dry-run may perform the probe and therefore may
leave only the same empty-directory residue; it creates no semantic run state.

- [x] **Step 11: Run functional concurrency selectors; parent-owned candidate
  capture and ordered reviews remain next.**

```bash
pytest --collect-only -q tests/test_provider_attempt_allocation.py
pytest -q tests/test_provider_attempt_allocation.py
pytest -q tests/test_state_manager.py tests/test_workflow_state_compatibility.py tests/test_resume_command.py
```

Functional implementer replacement evidence after the `81896bcb`, `bfb4c9dd`,
and `507946d6` specification rejections and the `088f926d`, `d4c16b32`, and
`6358f9ec` implementation-quality rejections: the earlier focused quality
correction tranche passed 11/11; the new module now collected 82 tests and passed
82/82; the required state/compatibility/resume group passed 115/115; and the
relevant call-frame/runtime selector `tests/test_subworkflow_calls.py` passed
71/71. The
new RED reproduced an affected manager loaded before ordinal 1 erasing the
allocator through an ordinary mutation; the GREEN proof hook-enables two separate
processes from the same recursive typed contract while the allocator is empty,
then uses a barrier to prove both the first allocation and ordinary status
mutation survive whether allocation or status wins the lock first. Separate
coverage proves imported-only detection, complete shared/cyclic graph traversal,
malformed affected siblings in both mapping orders, malformed imports beneath a
local affected node, and that a genuinely unaffected bundle retains legacy
serialization with no allocator or lock residue. Repair coverage proves a durable
manager restores a valid backup without reading corrupt primary JSON, falls back
from a semantically invalid newest backup to an older valid backup, and
auto-enables subsequent durable writes after allocator-bearing recovery.
Allocator-bearing restoration itself is now spy-proven to use the durable writer
with the exact accepted backup bytes, while unaffected recovery is spy-proven to
avoid both that writer and lock residue. All changed Python modules passed
`py_compile`, and a static search
found no production caller of `StateManager._write_state()` outside its defining
module. The implementer performed no staging or commit. The parent must capture
the immutable candidate only after verifying the allowed path set, then restart
the specification-compliance review before the implementation-quality review;
neither replacement review is claimed by this functional checkpoint.

Task 11 broad-regression repair evidence: the broad capture against
`be8247ea` collected 5,774 nodes and finished with 5,743 passed, 17 skipped, and
14 failed. Six failures are the frozen known-failure baseline; the other eight
were six `tests/test_cli_safety.py` run-command tests plus
`test_run_workflow_persists_observability_runtime_config` and
`test_resume_force_restart_uses_typed_bundle_context_when_legacy_adapter_drifts`
in `tests/test_cli_observability_config.py`. All eight failed at the new
`enable_provider_attempt_coordination_for_bundle` boundary because their plain
instance mocks were not real-`StateManager`-spec-compatible; production's strict
`isinstance` guard remains unchanged. The exact eight-selector RED was 0 passed /
8 failed. The minimal test-only repair derives each affected mock's spec from an
initialized real `StateManager`, explicitly proves `isinstance` compatibility,
and preserves the tests' mocked execution and existing assertions; the exact
selectors then passed 8/8 and both complete modified modules passed 40/40.
The two modified modules still collect exactly 40 nodes, and the adjacent
provider-attempt-allocation plus resume-command selector passed 167/167. This
candidate was captured before staging or commit, with ordered reviews pending.
The current Task 11 subject and broad artifacts predate these test bytes and are
invalid for completion evidence: after the repair receives ordered review and
lands in its own Task 7 repair commit, Task 11 must discard the old capture,
recapture a fresh subject against the new HEAD, and restart its focused and
broad verification sequence.

Suggested commit: `feat: allocate durable provider attempt identities`

## Task 8: Publish And Validate Immutable Content-Free Evidence

**Owner:** fresh evidence implementer.

**Execution scope:** functional evidence correctness, immutable ordinary-file
publication, terminal reconciliation, and concurrency only. Per the execution
override, this task does **not** implement or claim descriptor-relative access,
`openat`/`O_NOFOLLOW`, symlink or traversal resistance, hostile-directory or
platform preflight guarantees, provenance/authentication, or adversarial-security
coverage. Those security-only clauses are intentionally skipped rather than
silently treated as satisfied.

**Files:**

- Create `tests/test_prompt_dependency_evidence.py`
- Create `orchestrator/workflow/prompt_dependency_evidence.py`
- Create `scripts/validate_prompt_dependency_evidence.py`
- Modify `orchestrator/state_locking.py`
- Modify `orchestrator/state.py`
- Modify `orchestrator/workflow/provider_attempts.py`
- Modify this plan

- [x] **Step 1: Write canonical functional success/failure schema RED tests.**

Use the distinct closed schemas
`workflow_prompt_dependency_evidence.functional.v1` and
`workflow_prompt_dependency_failure_evidence.functional.v1`. Instantiate the
functional fields derivable from the Task-5 immutable snapshot/render and Task-7
scope/ordinal: run, compiler contract, attempt identity, authored-row disposition,
canonical groups, instruction metadata, injection metadata, final-prompt metadata,
failure category/operation, provider-call false, and self-digest. Enforce exact
keys, JSON types, digest syntax, ordering, cross-fields, and no serialized body.
Embed the complete closed output of
`serialize_compiler_prompt_dependency_contract` in both record kinds so offline
validation can cross-check row cardinality/order/binding refs, position, and the
authored-versus-default instruction source without executable IR.
Both schemas carry an explicit closed `record_kind`. Builders take authoritative
in-memory `RunState` identity fields directly and never reread `state.json` to
populate a record. Failure records carry nullable authored-row ID/evaluated-path
context and closed `provider_calls={preparation:false,execution:false}`.
The closed run object is exactly `run_id`, `workflow_file`, and
`workflow_checksum`; it does not serialize an absolute root or duplicate resume
scope. Row IDs are `sha256:` digests over canonical
`{source_origin_key,role,authored_index,binding_ref}`. Instruction source is one
of `authored`, `default_required`, or `default_optional`, derived from the closed
compiler contract.
Reject one-field tampering in both directions. Alias/stability/stat/raw-path,
safe-path, per-section, provenance, authentication, and adversarial-security
clauses are skipped.

- [x] **Step 2: Implement canonical record builders/validators.**

Use compact `ensure_ascii=True` canonical JSON with no trailing newline. Success
records derive only from one builder-owned authoritative render and final prompt
bytes returned by a composition callback that consumes that same render; the
operation returns the render, final prompt, and record without rerendering. Failure
records expose stable safe categories/operations only. Keep record-file SHA
separate from embedded record SHA.

- [x] **Step 3: Write ordinary immutable publication RED tests.**

Use the exact aggregate-relative destination
`workflow_lisp/prompt_dependencies/<step_key>/<visit_key>/attempt-<ordinal-as-%06d>.json`,
where each key is the first 24 lowercase hex characters of the specified full
identity digest. Repeat every unhashed identity in the record. Cover deterministic
destination derivation, short writes, file fsync, atomic hard-link no-clobber,
all-destination-`EEXIST` rejection, parent fsync, temp cleanup plus fsync, failure
propagation, and publication-event ordering. No arbitrary destination input.
Descriptor-relative, symlink, traversal, hostile-directory, and other
security-only publication cases are skipped.

- [x] **Step 4: Implement functional no-clobber publication.**

Use a deterministic generated path, canonical ASCII JSON without a newline,
complete short-write handling to a temporary file, file fsync, atomic hard-link
no-clobber, parent fsync, and temporary cleanup plus parent fsync. Any destination
`EEXIST`, including same bytes, rejects current-record publication so a crash orphan
cannot later be promoted into a manifest event. Never replace a
destination. Persist `evidence_published` in canonical ordinal order only after
the complete file is immutable, binding relative path, final file digest, and
record kind. Preserve state-then-aggregate lock order and propagate failures.

- [x] **Step 5: Write functional offline allocator-projection/index RED tests.**

Cover terminal completed/failed status; nonterminal rejection; frozen full state
digest; exact allocator projection; all publications and allocation-only gaps;
missing/corrupt/duplicate/wrong-kind records; orphan; allocation-only gaps;
unsorted/duplicate rows; wrong counts; index self-digest; immutable same-bytes
`EEXIST`; conflicting `EEXIST`; and stale index after later resume. Manifest-path
and adversarial filesystem security cases are skipped. The only index destination is
`workflow_lisp/prompt_dependencies/validated-indexes/<allocator-projection-sha256-hex>.json`
under the aggregate root.

- [x] **Step 6: Implement the functional terminal validator and CLI.**

Hold state-mutation then aggregate-evidence flocks continuously through both state
reads, scan, candidate build, immutable index link/fsync, final state recheck, and
release. On final mismatch remove only an index newly linked by this pass and
directory-fsync. Runtime never calls this validator. Add
`test_runtime_modules_do_not_import_or_call_offline_prompt_dependency_validator`,
an AST import/call guard over executor, prompting, adjudication, run, and resume
modules. It rejects the offline terminal-validator and validated-index builder/CLI
symbols while allowing runtime record builders and immutable current-record
publication APIs.

- [x] **Step 7: Write functional multiprocess quiescence/lock-order RED tests.**

One process holds validation while conforming resume/status/nested-frame writers
block then proceed. An injected bypass writer changes state and is detected. Run a
stress loop across allocation, record publication, manifest event, ordinary state
write, and validation; require bounded completion with no deadlock.

- [x] **Step 8: Run evidence selectors, freeze the review subject, and dispatch
  the ordered reviews.**

```bash
pytest --collect-only -q tests/test_prompt_dependency_evidence.py
pytest -q tests/test_prompt_dependency_evidence.py
pytest -q tests/test_provider_attempt_allocation.py tests/test_state_manager.py
```

Final reviewed subject: tree
`14296ca07657624a19e463d9a8bf08bd8caa6b1d`, binary patch SHA-256
`1065e07edda7c73f82eec3dd3b1b506668d18f3fc26d2421160f8a1755ea5fb4`,
specification token `TASK8-SPEC-PASS-20260718-14296CA0-03`, and quality token
`TASK8-QUALITY-APPROVED-20260718-14296CA0-01`. Fresh parent verification recorded
56 Task-8 passes and 108 Task-7/state regression passes; the independent reviews
recorded 268 broader regression passes. Security-only criteria were excluded by
the binding execution override.

Retrospective provenance review later bound the committed Task 8 subject as
commit `42e0ebc3445f63e05c094b71f069369d763b1985`, tree
`12cd555c497cca195b18c09c8c8269f2df05d7f1`, and patch SHA-256
`526ca8a5038eb73d8bf027f21ec78f3958ba26ba13b918edaf47b0e83572a574`.
Specification verdict `TASK8-RETRO-SPEC-PASS-20260718-12CD555C-01` found no
functional specification issue. Functional-quality verdict
`TASK8-RETRO-QUALITY-REJECT-20260718-12CD555C-01` found that first publication
created nested directories but synced only the leaf directory, leaving ancestor
directory entries outside the crash-durability claim. The repair is test-first,
shared by current-record and index publication, and must receive fresh ordered
reviews. Its first frozen candidate, prospective tree
`c77d4f339675133c90091ad90cb39e5aeccd15b8` and patch SHA-256
`d38e5a6bc25df1cbbc8d21c30afee43bda9c620e40c988006ad3446689460c14`,
passed specification review as
`TASK8-DURABILITY-REPAIR-SPEC-PASS-20260718-C77D4F33-01` but was rejected by
functional-quality review as
`TASK8-DURABILITY-REPAIR-QUALITY-REJECT-20260718-C77D4F33-01`: a failed parent
directory sync could leave created residue, after which a successful retry
skipped the potentially incomplete ancestor sync. That candidate is superseded
by a bounded durable-anchor repair that resyncs every chain component and its
parent on every successful invocation, including failed-then-retried current and
index publication. That superseded candidate claimed no replacement approval.

The replacement repair's pre-rewrite commit was
`128990096b87d3cb70218278aea3e982586faebc`; its reconstructed commit is
`1f424cc9ae2f18a4a33c4c4732692ef642430c76`, exact tree
`06cf3f8f1df39e593ba9bfe7b704e0415063b6c3`, and binary patch SHA-256
`d52e45a17371bd4f96eb2cbc25d286c7ee78f299d667ac454587ad95098ab388`.
It passed specification review
`TASK8-DURABILITY-REPAIR-SPEC-PASS-20260718-06CF3F8F-02` and functional-quality
review `TASK8-DURABILITY-REPAIR-QUALITY-APPROVED-20260718-06CF3F8F-01`, both
recorded as Git-native trailers on the reconstructed commit. The repair resyncs every bounded directory
component and its parent on every invocation, including retry residue, closing
the retrospective blocker without changing the content-free evidence contract.

Suggested commit: `feat: publish prompt dependency evidence`

## Task 9: Consolidate Ordinary And Adjudicated Per-Attempt Composition

**Owner:** fresh executor-integration implementer.

**Execution scope:** functional per-attempt composition, retry freshness, typed
ordinary-provider evidence ordering, and existing debug/state compatibility only.
Per the 2026-07-18 execution override, this task does **not** implement or claim a
platform preflight/probe, path/symlink/traversal/non-regular/change-during-read
protection, security diagnostics, or adversarial-security coverage. Typed
adjudicated evidence is not expressible in the current IR because
`AdjudicatedProviderStepConfig` has no compiler-contract carrier; this task keeps
adjudicated execution on the shared YAML composition/debug path and records that
typed adjudicated limitation for Task 10 instead of expanding the frontend/IR.

**Files:**

- Create `tests/fixtures/workflow_lisp/provider_prompt_dependencies/without_instruction.orc`
- Modify `tests/test_prompt_contract_injection.py`
- Modify `tests/test_adjudicated_provider_runtime.py`
- Modify `tests/test_v214_runtime_semantics.py` for the adjudicated attempt-callback
  behavioral interception
- Verify without modification `tests/test_injection_integration.py`
- Verify without modification `tests/test_adjudicated_provider_resume.py`
- Verify without modification `tests/test_at72_provider_state_persistence.py`
- Modify `orchestrator/workflow/prompting.py`
- Modify `orchestrator/workflow/executor.py`
- Modify `orchestrator/workflow/adjudication_bindings.py`
- Modify `orchestrator/workflow/adjudication_candidates.py`
- Modify `orchestrator/workflow/adjudication_runtime.py` for the coherent typed
  attempt-composition callback protocol
- Modify `orchestrator/workflow/adjudication_helpers.py` to retain only nonempty
  candidate `debug.injection` in the existing candidate-state projection
- Modify `orchestrator/deps/content_snapshot.py`
- Modify `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify this plan

- [x] **Step 1: Write ordinary retry RED tests.**

With a capturing provider, fail one retryable attempt, mutate a YAML dependency,
then succeed. Assert two fresh snapshots, one snapshot/render per attempt, first
prompt only old bytes, second only new bytes, distinct digests, stable composition
order, and no Workflow Lisp allocator/evidence for YAML. For a truncated attempt,
assert the existing provider-result `debug.injection` member receives the same
counts/status as the immutable renderer result and persists with the step result;
for a non-truncated attempt, assert no new debug member appears. A stable workspace
must remain byte-identical to prior successful YAML behavior.

- [x] **Step 2: Move ordinary composition inside the retry boundary.**

Keep base prompt/asset stages contractually ordered, but call one shared
per-attempt composition owner inside the retry boundary. Content mode takes one
fresh snapshot and exactly one render per attempt; pass that immutable block
through `PromptComposer` and never sequence resolver+injector independently.
List/none dependencies retain their existing non-content behavior.

- [x] **Step 3: Write adjudicated candidate RED tests.**

Each candidate retry gets one candidate-workspace snapshot with
`adjudication_subject.candidate_id`, same ordering/API, and no reopen. Cover
different candidates, retry mutation, baseline refresh, required failure, and
optional absence. Prove truncated candidate results preserve the existing
`debug.injection` surface through candidate/result state without exposing prompt
or dependency bodies. YAML adjudicated steps still produce no Workflow Lisp
evidence.

- [x] **Step 4: Switch adjudicated composition to the shared API.**

Extend the typed callback rather than importing executor internals into the
candidate module. Preserve candidate prompt override, output-contract suffix,
consumes, and evaluator behavior.

- [x] **Step 5: Write typed Workflow Lisp allocation/publication-order and debug
  RED tests.**

Assert this exact success sequence: ordinal allocation; exactly one snapshot/render;
insertion of the immutable dependency
block into the already composed base-prompt
and `asset_depends_on` prefix at the declared position; typed-input,
consumed-artifact, and output-contract composition; strict UTF-8 encoding of the
exact final prompt and its digest; success-record construction from that snapshot
and those exact bytes; immutable record publication; manifest event; then
provider preparation/execution. Assert the success record's
`final_prompt` digest recomputes from the bytes passed unchanged to
`prepare_invocation`.

Test dependency failures as a separate branch: after allocation, a snapshot or
render failure may construct and best-effort publish only the closed failure
record and matching manifest event; it never constructs a success record or final
prompt and never reaches provider preparation. Allocation, snapshot, success-record
construction/publication, or event failure must stop before preparation. Failure
evidence never completes a checkpoint.

For truncated success snapshots, assert prompt markers, evidence truncation rows,
and the existing provider-result `debug.injection` member agree exactly. Persist
that member through the ordinary and adjudicated result/state paths. Do not add a
second state field; non-truncated results retain their pre-feature debug shape.

- [x] **Step 6: Integrate typed evidence.**

Construct `ProviderAttemptScope` from authoritative state/runtime step identity,
not evidence or local retry index. Finalize evidence from the same snapshot and
exact bytes passed to `prepare_invocation`. Never reopen snapshot/evidence and
never call offline validation. The implementation order is therefore
`allocate -> snapshot/render -> finish composition/final-prompt
digest -> publish success record -> persist evidence_published canonically ->
prepare/execute`.
Keep failure-record construction on the separate branch above.

- [x] **Step 7: Write retained functional failure-category integration tests.**

Exercise missing required, unreadable, invalid UTF-8, and invalid injection.
Assert provider preparation/execution counts remain zero and only the closed
functional failure category plus relative authored-row context reaches evidence.
Unsafe-path, symlink, traversal, non-regular, changed-during-read, unsupported-
platform, and other security/preflight cases are explicitly skipped.

- [x] **Step 8: Run focused integration, freeze the review subject, and dispatch
  the ordered reviews.**

Implementation and focused integration are complete, and the parent owns the
exact-tree freeze plus both ordered reviews. The first
specification review rejected a stale adjacent behavioral interception of the old
two-value adjudication callback; that test now intercepts the three-value attempt
callback and remains part of the closed Task 9 subject. Fresh Task 9 verification
on 2026-07-18 recorded 173 collected integration tests, 86 ordinary
prompt/injection passes, 81 adjudicated runtime/resume passes, 22 provider-state
and legacy-injection passes, 177 adjacent snapshot/allocation/evidence passes,
120 Workflow Lisp prompt-dependency/call-policy passes, and 18 v2.14 runtime
semantic passes. The scoped diff check passed, and the separately protected
YAML-retirement execution plan retained SHA-256
`2de3c7aafd13e7518f9030621fcc1a13a70daa8ae1418c6bf81be1d3f8918d2d`.

The subsequent quality review found that typed execution checked only
compatibility-row cardinality, so a replaced or swapped mapping template could
change the resolved dependency while evidence continued to name the compiler
binding; the mapping's injection position also controlled execution without
being reconciled to the compiler contract. The finding was accepted. Focused
TDD reproduced all three contradictions before provider preparation, retained a
canonical positive control, and then made the compiler contract authoritative:
every typed compatibility row must be exactly `${<binding_ref>}`, the explicit
mapping position must equal `contract.position.value`, and typed composition uses
that contract value. YAML semantics remain unchanged. The earlier quality verdict
is superseded; this corrected delta is eligible to commit only after a fresh exact-
tree specification review followed by a fresh implementation-quality review.

Final-quality review `TASK9-QUALITY-REJECT-20260718-DD3C6114-02` then found that
the compiler contract still did not own the complete compatibility projection:
mapping mode could select the legacy branch before allocation, extra mapping
members were accepted, and instruction presence/content was not validated as a
closed projection before acquisition. The finding was accepted. A second focused
TDD correction now makes contract presence select the typed attempt branch even
when `depends_on` is absent or non-mapping; allocation precedes the closed
projection check; the top mapping must contain exactly `required`, `optional`,
and `inject`; `inject` must contain exactly `mode`/`position` plus `instruction`
iff its compiler digest is non-null; mode must be `content`; position, canonical
row templates, and strict UTF-8 instruction SHA-256 must match the contract.
Failures publish failure evidence only and never prepare or execute a provider.
A real compiler-lowered no-instruction fixture covers the null-digest direction,
while explicit YAML list/content controls prove YAML retains its mapping-driven
behavior with no typed allocation or evidence. This final-quality verdict is
superseded; the corrected exact tree requires fresh ordered reviews.

The final pre-freeze edge check parameterized the non-mapping projection control
with both a list and explicit `None`. Both enter the allocated failure branch:
the typed `RuntimeStep` mapping omits a `None` compatibility value, and the
executor's existing `step.get('depends_on', {})` therefore normalizes both missing
and explicit `None` to the same invalid empty projection before closed validation.
No additional production change was necessary; both directions passed freshly.

Final-quality review `TASK9-QUALITY-REJECT-20260718-AD57309E-03` then found that
an adjudicated candidate without an authored `prompt_variant_id` derived that ID
only after its first successful composition. When a retry refreshed changed
dependency content, `composed_prompt_hash` advanced to the final attempt while the
derived variant ID continued to identify the first prompt. The finding was
accepted. Focused TDD now proves both directions: a runtime-derived variant ID is
recomputed after every successful composition from the current prompt-source
kind/path and current `composed_prompt_hash`, while an explicitly authored variant
ID remains unchanged across retries. The earlier quality verdict is superseded;
the corrected integrated Task 9 tree still requires fresh ordered reviews.

A retrospective review subsequently bound the committed Task 9 subject as commit
`42839223d126b0070f2978c0f6da5696c6bda65e`, tree
`61c39268e7855823cd927e33eb496172ebe97ea5`, and patch SHA-256
`70e8427b7d90879f5d366a317d1bc9c305758ad176786464a926ab88c4ba25d5`.
Specification verdict `TASK9-RETRO-SPEC-PASS-20260718-61C39268-01` found no
functional specification issue. Functional-quality verdict
`TASK9-RETRO-QUALITY-REJECT-20260718-61C39268-01` found that
`compose_content_dependency_attempt` invoked its downstream final-prompt callback
inside the executor's broad dependency-render exception domain. An `OSError`
while writing typed prompt-input evidence, a later prompt-completion `ValueError`,
or a strict UTF-8 encoding failure could therefore be falsely published as
`invalid_injection_contract` / `render` dependency evidence. Focused TDD now
places only the callback, its string-result check, and final UTF-8 encode behind
a generic typed completion exception preserving the prior
`TypeError`/`ValueError`/`OSError` catch domain. The executor handles that exception
before dependency failures as `prompt_completion_failed`, without publishing a
prompt-dependency record or event and without provider preparation or execution.
A genuine dependency-injection `ValueError` remains in the dependency domain and
still publishes the closed failure record.

The historical verification sentence above also understated its already-committed
subject: the five-module collection was `174`, not `173`, and the adjudicated
runtime/resume tranche was `82`, not `81`. This repair adds one collected ordinary
regression covering four completion-failure directions, so the first repair candidate
collects `175` across those five modules and the ordinary prompt/injection tranche
passes `87`, not the prior `86`; the modified module passes `76` and the adjacent
prompting/adjudication/resume/evidence regression tranche passes `377`. Task 8's
durability repair is present at `12899009`. Task 10 remains approved at commit
`be8247ea` under `TASK10-SPEC-PASS-20260718-AC9F4728-02` and
`TASK10-QUALITY-APPROVED-20260718-AC9F4728-02`; this Task 9 repair does not alter
that contract. Task 11's previously captured subject and evidence are invalidated
and remain reopened; they must be regenerated only after this correction receives
fresh ordered reviews and lands.

The first frozen repair candidate then failed specification review as
`TASK9-FAILURE-REPAIR-SPEC-FAIL-20260718-CE0443FB-01`. The new typed completion
exception was handled by the primary typed-evidence consumer, but the shared
`_compose_provider_attempt_for_step` consumer used by adjudicated and other
non-primary composition still caught only raw `TypeError` / `ValueError` dependency
failures. A downstream strict-encoding completion error therefore escaped into
adjudication as generic `candidate_failed`. Focused TDD reproduced that escape and
retained the opposite-direction control: the shared consumer now catches
`PromptCompletionError` before its existing dependency-error branch and returns
`prompt_completion_failed`, while a genuine
`apply_rendered_content_dependency` `ValueError` remains
`invalid_injection_contract`. Both stop before provider execution and surface as
the ordinary `contract_violation` candidate failure rather than `candidate_failed`.
The failed frozen candidate is superseded and claims no approval. Fresh verification
of the replacement records `177` collected five-module integration tests, `148`
passes across both modified modules, and `307` adjacent
prompting/resume/evidence/provider regressions; the adjudicated runtime/resume
tranche is now `84`. Both ordered reviews must restart on the new exact subject.

The replacement repair's pre-rewrite commit was
`21de86ceffd9a31262e86741871d75d279215e21`; its reconstructed commit is
`a13852900c6ce212776a061c2ccdbb1e1e75e002`, exact tree
`03e58c65352e4d3ed621e43fc96113f3078e5d5e`, and binary patch SHA-256
`919364f2a43cb5cc76fecdacfae0cbf9dbfdcf63dbb1b4b557e85c337b9969b3`.
It passed specification review
`TASK9-FAILURE-REPAIR-SPEC-PASS-20260718-03E58C65-02` and functional-quality
review `TASK9-FAILURE-REPAIR-QUALITY-APPROVED-20260718-03E58C65-01`, both
recorded as Git-native trailers on the reconstructed commit. Primary and shared/adjudicated consumers now
separate typed prompt completion failures from genuine dependency-render failures,
closing the retrospective blocker without family-specific behavior.

```bash
pytest --collect-only -q tests/test_prompt_contract_injection.py tests/test_injection_integration.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_resume.py tests/test_at72_provider_state_persistence.py
pytest -q tests/test_prompt_contract_injection.py tests/test_injection_integration.py
pytest -q tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_resume.py
pytest -q tests/test_at72_provider_state_persistence.py tests/test_dependency_injection.py
pytest -q tests/test_prompt_dependency_content_snapshot.py tests/test_provider_attempt_allocation.py tests/test_prompt_dependency_evidence.py
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py tests/test_workflow_lisp_provider_call_policy.py
pytest -q tests/test_v214_runtime_semantics.py
```

Suggested commit: `refactor: snapshot dependencies per provider attempt`

## Task 10: Prove Crash, Resume, And Real `.orc` End-To-End Semantics

**Owner:** fresh runtime/E2E implementer.

**Execution override (2026-07-18):** Task 10 is functional-only. Skip all
security-related work, including escaping-symlink/path cases and adversarial,
schema-tamper, index-tamper, or evidence-tamper cases. Retain the positive real
`.orc` E2E, functional crash/resume durability, accidental evidence deletion or
corruption independence, allocator corruption fail-closed behavior,
completed-boundary reuse/checkpoint-contract rejection, and root/call/loop scope
coverage. Typed adjudicated allocator/evidence coverage is N/A because
`AdjudicatedProviderStepConfig` has no compiler-contract carrier; Task 9 already
covers YAML adjudicated per-attempt composition and debug behavior. This override
does not remove or weaken existing security behavior; it excludes security work
from this execution tranche.

**Files:**

- Create `tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py`
- Modify `tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc`
- Inspect without modification
  `tests/fixtures/workflow_lisp/provider_prompt_dependencies/procedure_loop.orc`
- Verify without modification `tests/test_workflow_lisp_provider_prompt_dependencies.py`
- Verify without modification `tests/test_provider_attempt_allocation.py`
- Verify without modification `tests/test_prompt_dependency_evidence.py`
- Verify without modification `tests/test_workflow_lisp_lexical_checkpoint_restore.py`
- Verify without modification
  `tests/test_workflow_lisp_lexical_checkpoint_default_resume.py`
- Modify this plan

- [x] **Step 1: Write the real positive `.orc` E2E RED test.**

Compile the real mixed fixture through public WCC/schema 2 and shared validation,
load the bundle, bind typed relpath inputs, execute with a capturing provider that
writes the real structured output bundle, and terminally validate evidence.
Assert four present sentinel bodies in canonical order, one absent optional row,
declared placement, exact final-prompt digest, source/contract digests, one
attempt-specific success record, one valid index, and a completed typed result.

Execution evidence: the new `mixed-e2e` entrypoint compiles through the public
entrypoint with shared validation, executes a real structured provider result,
and validates the terminal evidence index. The RED first failed on the absent
entrypoint; the fixture-only GREEN preserves the pre-existing `mixed` contract.

- [x] **Step 2: Skip the security-only swapped-path `.orc` E2E test.**

Skipped by the functional-only execution override. Existing path/symlink behavior
is unchanged and no claim about it is made by Task 10.

- [x] **Step 3: Write crash-matrix E2E RED tests.**

Inject crashes: before allocation persistence; after allocation/before record;
after record/before manifest event; after event/before preparation; during
preparation/execution. Resume each run from authoritative executable/checkpoint/
allocator state while spying on evidence filesystem access. Runtime resume must
not enumerate, open, hash, or reject an orphan record: it ignores prior evidence
content, allocates the exact same/new ordinal required by durable allocator state,
takes a fresh snapshot, never overwrites an earlier path, and preserves normal
provider interruption semantics.

After each resumed runtime case reaches a terminal state, invoke the offline
validator separately. Assert an allocation-only gap is disclosed and accepted,
while a record published before its missing `evidence_published` event is an
orphan that rejects only that offline evidence set and emits no validated index.
The offline verdict must not retroactively change the resumed semantic result or
provider checkpoint.

Execution evidence: a temporary E2E workflow adds a real committed seed boundary
and downstream command around the fixture-owned provider dependency contract. It
covers failed allocation persistence, allocation-before-snapshot, immutable
record-before-publication-event, publication-before-preparation, and provider
execution interruption. Resume uses a fresh `StateManager` and snapshot. The
orphan case guards the exact old record against runtime open, then proves offline
validation alone rejects it and emits no validated index. The initial no-seed RED
was `lexical_default_resume_prior_boundary_missing`; the fixture gained a seed
boundary instead of weakening fail-closed resume.

Review correction: all resumed runs with prior published/orphan evidence now use
one scoped guard that rejects exact prior-record reads through `Path`, built-in,
and `os` entrypoints and rejects enumeration of only the corresponding ancestors
through `workflow_lisp/prompt_dependencies`. New attempt publication remains
writable, and unrelated state/checkpoint traversal remains available. A dedicated
RED/GREEN guard test proves both rejection and fresh-record write permission.

- [x] **Step 4: Write pending-resume evidence-independence RED tests.**

For separate runs accidentally delete or corrupt prior evidence. Pending resume
must not enumerate/open it, must allocate from authoritative state, and must
snapshot fresh. Corrupt allocator scope/counter/event order separately and assert
resume fails closed without consulting evidence. Schema/index/evidence tamper
security cases are skipped by the functional-only execution override.

Execution evidence: separate deleted and corrupt prior-record runs guard the
exact historical path against runtime open, mutate a dependency, resume from a
fresh snapshot/publication, and complete. Offline validation rejects only the
historical evidence. Allocator closed-shape, counter, event-order, and corruption
fail-closed coverage remains in `tests/test_provider_attempt_allocation.py`; its
fresh adjacent suite passed as part of the 138-test allocator/evidence tranche.

- [x] **Step 5: Write completed-boundary reuse RED tests.**

Complete provider, interrupt downstream, then mutate/delete dependency and resume.
Assert provider result reuse with zero dependency open/allocation/provider calls.
Change required/optional role, position, instruction, or authoritative persisted
contract and assert checkpoint rejection. Security-oriented evidence tamper is
skipped; accidental evidence deletion/corruption must leave an otherwise-valid
completed semantic result unchanged while offline validation reports the evidence
problem.

Execution evidence: deleted and corrupt evidence cases interrupt after the
committed provider checkpoint, delete a required dependency, and resume the
downstream continuation with snapshot, allocation, provider preparation, and
provider execution guarded to zero calls. The same scoped prior-evidence guard is
active during completed reuse and provider-execution interruption. Contract
identity coverage remains split across the typed dependency digest-change test
and executable lexical checkpoint rejection tests; no synthetic security-tamper
E2E is claimed.

- [x] **Step 6: Prove real `.orc` call-frame scope and record distinct loop N/A boundaries.**

Use real two-level calls, a loop in a call frame, root for-each, and root
repeat-until. Assert exact recursive frame IDs, enclosing step visit, iteration,
runtime step IDs, aggregate-root paths, monotonic ordinals, and one root
transition. Preserve nested-loop rejection. Typed adjudicated allocator/evidence
is N/A because the adjudicated runtime has no compiler-contract carrier; its YAML
composition/debug behavior remains covered by Task 9.

Execution evidence: `mixed.orc` now contains a supported real two-level
same-module call route whose leaf owns the typed prompt-dependency contract. The
E2E derives both call-frame IDs and the provider runtime identity from compiled
call/provider nodes, then asserts the exact recursive `call_frame_ids`, leaf
provider step/visit, ordinal 1 allocation/publication, null loop/adjudication
fields, absence of nested allocator state, and record/index ownership under the
aggregate root only. The RED failed solely because the call entrypoint was absent;
the fixture-only route made it GREEN.

Distinct limitations remain intentionally unclaimed: the imported `defproc`
route lowers inline and is not a call frame; `loop-carried` does not pass public
shared validation; and no typed root for-each carrier exists for this contract.
Loop-in-call and root-loop runtime shapes remain adjacent allocator coverage, not
evidence supplied by the new call test. Typed adjudicated allocator/evidence is
N/A; Task 9 owns YAML composition/debug coverage.

- [x] **Step 7: Route any exposed production defect back to its owner task.**

Task 10 owns tests, fixtures, and verification only. If a RED E2E test exposes a
production defect, stop this task and return the defect to its actual owner under
the File Responsibility Map and the exact Task 2-9 `Files` lists:

- Task 2 owns frontend syntax, traversal, type/effect rules, specialization, and
  WCC route validation;
- Task 3 owns WCC payload/reconstruction, the typed compiler contract and side
  table, owner lowering, origins, and source-map lineage;
- Task 4 owns shared validation/IR attachment, authenticated persistence/build
  views, and checkpoint-contract identity;
- Task 5 owns pure grouping/rendering and stable YAML resolution/injection
  compatibility;
- Task 6 owns descriptor-relative acquisition and platform preflight;
- Task 7 owns durable root-state locking, aggregate ownership, attempt identity,
  and command-boundary preflight integration;
- Task 8 owns immutable evidence publication, allocator publication events, and
  offline validation; and
- Task 9 owns ordinary/adjudicated per-attempt composition, debug propagation,
  and provider-boundary integration.

The failing Task 10 RED tests and fixtures are a frozen repair overlay, not part of
the owner-fix commit. Use two distinct closed bindings; never try to use one launch
manifest across the production edit.

1. **Before any owner production edit, capture the frozen RED overlay.** Pass the
   following complete eligible set to `capture-frozen-overlay` as eight repeated
   `--eligible-path` arguments; never abbreviate a directory or use a glob:

   ```text
   tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
   tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc
   tests/fixtures/workflow_lisp/provider_prompt_dependencies/procedure_loop.orc
   tests/test_workflow_lisp_provider_prompt_dependencies.py
   tests/test_provider_attempt_allocation.py
   tests/test_prompt_dependency_evidence.py
   tests/test_workflow_lisp_lexical_checkpoint_restore.py
   tests/test_workflow_lisp_lexical_checkpoint_default_resume.py
   ```

   Write the record to a fresh owner-specific ignored path such as
   `.orchestrate/tmp/provider-prompt-dependencies-task10-repair-<owner>-<sequence>/frozen-overlay.json`;
   refuse an existing root rather than deleting or replacing it. The helper must
   derive and capture every currently dirty/untracked eligible path, require the
   selected set to be non-empty and entirely non-staged, validate the record, and
   print/record its exact path, byte count, file SHA-256, self-digest, and selected
   path list in the repair execution log. This is the immutable pre-repair binding.
   If a production edit already exists, stop and return that unreviewed candidate
   to its owning implementer for explicit disposition; do not discard shared-tree
   bytes, capture late, or backfill the record.
2. **Implement the owner candidate without touching the overlay.** Return the
   defect to the actual Task 2-9 owner. The owner may modify only the smallest
   exposed production path set from that task's `Files` list. During this edit the
   frozen overlay record and all selected overlay paths are read-only and
   non-staged. If another Task 10 eligible path becomes dirty, or a selected path
   changes status/type/mode/bytes/SHA, abandon the owner candidate and return to
   Task 10 for a new RED-overlay capture.
3. **After the production candidate exists and before its first final GREEN run,
   capture the separate owner-repair subject.** First run
   `validate-frozen-overlay` and compare every live selected path to the pre-repair
   record. Then run `capture-subject` into a different fresh ignored root. Pass the
   exact modified production paths and this plan as ordinary repeated
   `--task-subject` arguments, repeat every selected overlay path explicitly as a
   `--task-subject`, pass the pre-repair record through `--frozen-overlay`, and
   retain the ordinary protected/concurrent declarations. The only
   `--allowed-post-launch-update` is this plan for the later owner-repair
   bookkeeping. Every task subject must still be non-staged. The capture must
   reject unless its copied overlay rows exactly equal the pre-repair record and
   its production rows already contain the owner candidate bytes. Record both
   binding digests in the execution log. No production path is an allowed
   post-launch update.
4. Add only those exposed production paths to the actual owning task's repair
   `Files` list in this plan. Run the owning task's focused selectors, including
   the frozen Task 10 RED test that exposed the defect, and re-run launch-phase
   subject verification after every tranche. The frozen record and the post-edit
   subject together must prove the overlay remained non-staged and byte/status
   identical while the production candidate remained byte-identical to its
   post-edit launch inventory. Any further production-candidate edit invalidates
   only the post-edit owner-repair subject: revalidate the unchanged pre-repair
   frozen record, capture a new post-edit subject in another fresh ignored root,
   and restart the final GREEN/review sequence.
5. Stage only the exact owner production paths plus this plan. The closed review
   envelope must prove that exact staged set, bind both frozen-overlay and
   post-edit-subject digests, and reject every staged overlay path. Apply the
   ordinary specification-then-quality exact-tree review protocol. Supply both
   records to both reviewers. Immediately before committing, re-run review-phase
   verification and prove the frozen overlay, candidate bytes, patch digest, tree,
   and staged set remain unchanged. Commit only the reviewed production fix and
   plan update.
6. After that commit changes `HEAD`, discard both completed repair bindings,
   recapture a fresh Task 10 launch subject against the new commit with the same
   Task 10 tests/fixtures as ordinary Task 10 task subjects, rerun the complete
   Task 10 RED/GREEN and focused tranche, and restart both Task 10 reviews. Never
   reuse either repair binding as Task 10 evidence.

This is the sole prescribed closed route for carrying an in-progress Task 10
overlay into an owner repair. If one defect crosses owners, split it into the
smallest owner-specific fixes and repeat the two-binding protocol for each owner
in dependency order. Never edit production from Task 10, assign a file to an
unrelated task merely to continue, move interruption points, invent evidence
recovery, or weaken existing checksum/call-frame/checkpoint guards.

Execution evidence: no production defect was exposed and no production file was
edited. RED results were fixture-contract gaps (missing entrypoint, terminal
provider with no continuation, and no prior boundary), corrected only in Task 10
test/fixture surfaces. The frozen owner-repair overlay route was not entered.

- [x] **Step 8: Run focused E2E and resume suites.**

```bash
pytest --collect-only -q tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
pytest -q tests/test_workflow_lisp_lexical_checkpoint_restore.py tests/test_workflow_lisp_lexical_checkpoint_default_resume.py
pytest -q tests/test_resume_command.py tests/test_adjudicated_provider_resume.py
```

Fresh post-correction evidence: collect-only found 11 tests; the new E2E module
passed 11; the existing prompt-dependency frontend suite passed 64; allocator plus
evidence suites passed 138; lexical restore plus default-resume suites passed
122; resume-command plus adjudicated-resume suites passed 97.

- [x] **Step 9: Freeze the review subject and dispatch the ordered reviews.**

Apply the digest-stable protocol and commit only after both reviewers PASS the
unchanged tree.

Review history: functional quality verdict
`TASK10-QUALITY-REJECT-20260718-2AE61543-01` rejected the earlier candidate for
two test-contract gaps: it substituted adjacent unit coverage for a supported
real `.orc` call-frame route, and its prior-evidence probes did not cover all
resumed historical evidence sets or directory enumeration. The accepted
corrections above supersede the rejected candidate only after a fresh immutable
subject and restarted ordered specification-then-quality reviews; no earlier
approval token applies to the corrected tree.

Retrospective exact-object review bound the committed Task 10 subject as commit
`be8247ead9f1b3fc73997f50b9bdbd40a4a37784`, tree
`ac9f4728eb3e40579553d3531e57eded5d6c5c23`, and binary patch SHA-256
`d62628d10f85a11bb25e103630b55c1fe0ac41872893960441e6bd5f743f9678`.
Specification verdict `TASK10-RETRO-SPEC-PASS-20260718-AC9F4728-01` and
functional-quality verdict
`TASK10-RETRO-QUALITY-APPROVED-20260718-AC9F4728-01` both passed with no
findings.

Suggested commit: `test: prove prompt dependency runtime semantics`

## Task 11: Close Implementation Verification Before Documentation

**Owner:** verification coordinator; production edits only if a failing test exposes
a real defect, in which case return to the owning task/review loop.

**Files:**

- Modify this plan
- Read but never modify
  `tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json`
- Create temporary ignored broad collection/log/JUnit/outcome artifacts under
  `.orchestrate/tmp/provider-prompt-dependencies-task11/`
- Conditionally consume only already committed, independently reviewed
  `docs/plans/evidence/provider-prompt-dependencies/broad-remediations/*.json`;
  if a new remediation is needed, stop Task 11 and land it through the separate
  owner/review sequence before restarting this task. Never create a temporary
  remediation file: each consumed record has the deterministic removed-row-set
  filename and remains byte-identical to its unique tracked addition commit
- Create no documentation status claims yet

**Invalidated evidence:** the completed Steps 1-4 capture and review subject
recorded below predate retrospective production blockers. They are not completion
evidence. After every repair lands with its ordered reviews, delete the current
temporary capture, create a fresh subject from the new HEAD, and rerun Task 11
from Step 1. The checkboxes were therefore reopened until the fresh execution
recorded below.

The subsequent Task 11 capture at HEAD
`21de86ceffd9a31262e86741871d75d279215e21` is also diagnostic evidence only.
Its subject file SHA-256 was
`569eb15d996456302a106c2ba59b90537470bb34feab6ef63c8b97e09e958be5`
and its record SHA-256 was
`691ba1dee449f5f03e3b59a8d3797b0046e03fb561afaf2121565dd33064e3b7`.
Collection exited `0` with `5785` tests. The broad run exited `1` with `6`
failed, `5762` passed, `17` skipped, `33` warnings, and the valid pytest summary
duration `64.79s (0:01:04)`. `build-outcome` stopped fail-closed with `cannot
derive pytest broad summary totals` because the helper accepted only a seconds
duration at end of line. The generic parser repair accepts pytest's optional
tightly formed parenthesized `H:MM:SS` suffix, normalizes the complete variable
duration, and continues to reject malformed suffixes and trailing junk. Because
the helper, its tests, and this plan changed after subject capture, the entire
capture was invalidated. The repair therefore required deletion of the temporary
capture and a fresh Task 11 subject and Steps 1-4 execution from its landed HEAD.
Specification
review `TASK11-DURATION-SPEC-FAIL-20260718-D73C9C0A-01` rejected the first repair
candidate because it recorded the wrong full capture HEAD, allowed out-of-range
minute/second fields and trailing whitespace, consumed LF/CRLF during
normalization, and did not migrate the baseline's bound helper digest. The
replacement candidate uses unbounded hour digits with `[0-5]\d` minute/second
fields, a strict captured `\r?$` terminator that preserves line endings, and the
one reviewed metadata-only baseline migration enumerated above.
Specification review `TASK11-DURATION-SPEC-PASS-20260718-A61B42A7-01` accepted
that corrected candidate. Functional-quality review
`TASK11-DURATION-QUALITY-REJECT-20260718-A61B42A7-01` rejected the same tree
because its new baseline-validation test launched the helper with a historical,
machine-specific interpreter path from captured evidence. The replacement test
calls the loaded validator directly and supplies the captured interpreter string
only as contract data, so no executable at that historical path is required;
the captured baseline remains byte-unchanged.

The final parser candidate passed restarted specification review
`TASK11-DURATION-SPEC-PASS-20260718-B29957B9-01` and functional-quality review
`TASK11-DURATION-QUALITY-APPROVED-20260718-B29957B9-01`, then committed as
pre-rewrite object `fa54148be469f4d58755079bf8b02766738328d5`, exact tree
`b29957b9cab299462ddde2b0e6f4d2dc51dac603`; its canonical-trailer
reconstruction is `cb8e2d892b82fc825bcbc0759c3f447104c50a0d` with the same
subject, tree, parent-relative patch, identities, and timestamps.

**Enumerated trailer-provenance closure:** the original Task 8, Task 9,
and Task 10 commits predate the required review trailers. The final reviewed
Task 11 plan-only commit containing this record—not the earlier mixed-file
corrective commits—is the
sole permitted closure record for those three exact mappings; it is not a generic
missing-trailer waiver. It binds reviewed Task 8 pre-rewrite commit
`42e0ebc3445f63e05c094b71f069369d763b1985` to reconstructed commit
`fff1b1fcb1d6af9f9582a55ed9120f28915a6c90`, tree
`12cd555c497cca195b18c09c8c8269f2df05d7f1`, patch
`526ca8a5038eb73d8bf027f21ec78f3958ba26ba13b918edaf47b0e83572a574`,
retrospective specification PASS `TASK8-RETRO-SPEC-PASS-20260718-12CD555C-01`,
retrospective quality REJECT `TASK8-RETRO-QUALITY-REJECT-20260718-12CD555C-01`,
and its closing reviewed repair mapping
`128990096b87d3cb70218278aea3e982586faebc` to
`1f424cc9ae2f18a4a33c4c4732692ef642430c76` with the exact review tokens
recorded above. It binds reviewed Task 9 pre-rewrite commit
`42839223d126b0070f2978c0f6da5696c6bda65e` to reconstructed commit
`d9fc6b9f43621f7995ffc416d9896bc1e691b46f`, tree
`61c39268e7855823cd927e33eb496172ebe97ea5`, patch
`70e8427b7d90879f5d366a317d1bc9c305758ad176786464a926ab88c4ba25d5`,
retrospective specification PASS `TASK9-RETRO-SPEC-PASS-20260718-61C39268-01`,
retrospective quality REJECT `TASK9-RETRO-QUALITY-REJECT-20260718-61C39268-01`,
and its closing reviewed repair mapping
`21de86ceffd9a31262e86741871d75d279215e21` to
`a13852900c6ce212776a061c2ccdbb1e1e75e002` with the exact review tokens
recorded above. It binds reviewed Task 10 pre-rewrite commit
`be8247ead9f1b3fc73997f50b9bdbd40a4a37784` to reconstructed commit
`6fa662fd032ac9ae4b58e0503665afd07343af26`, tree
`ac9f4728eb3e40579553d3531e57eded5d6c5c23`, patch
`d62628d10f85a11bb25e103630b55c1fe0ac41872893960441e6bd5f743f9678`,
retrospective specification PASS `TASK10-RETRO-SPEC-PASS-20260718-AC9F4728-01`,
and retrospective quality APPROVED
`TASK10-RETRO-QUALITY-APPROVED-20260718-AC9F4728-01`. Each mapping has identical
subject, tree, and parent-relative patch; the pre-rewrite history remains reachable
at `refs/archive/provider-prompt-pre-trailer-rewrite`. Task 13 may accept missing
trailers only for these three exact reconstructed objects and only after the final
Task 11 closure commit itself has a matching immutable review tree, patch digest,
and ordered PASS/APPROVED trailers. Every other reconstructed task commit must
satisfy Git-native direct trailer parsing.

Holistic specification review
`TASK11-HOLISTIC-SPEC-FAIL-20260718-13196795-01` rejected the first Task 11
freeze because the parser-repair commit used noncanonical review-trailer names
and omitted its review tree and patch binding. The commit was amended
metadata-only to the exact direct trailer form above, preserving tree
`b29957b9cab299462ddde2b0e6f4d2dc51dac603`; because its commit identity changed,
all Task 11 capture and review evidence was invalidated and Steps 1-4 reopened.

The replacement freeze passed holistic specification review as
`TASK11-HOLISTIC-SPEC-PASS-20260718-FE11C070-02` but functional-quality review
`TASK11-HOLISTIC-QUALITY-REJECT-20260718-FE11C070-01` found three blockers. First,
a pre-step backup could restore state from before a durably committed provider
attempt allocation and reuse its ordinal. The generic correction must durably
establish a run-root allocation-started repair barrier before committing an
ordinal and make backup repair fail closed, without replacing the primary, when
that barrier, the legacy aggregate-lock migration signal, or an allocator-bearing
backup exists. Second, the broad-gate helper must obtain review metadata from
Git's parsed terminal trailer block and reject blank-separated pseudo-trailers.
Third, the linear Task 1-11 commit chain must be reconstructed metadata-only with
identical trees, parent-relative patches, subjects, identities, and timestamps so
all ten directly reviewed commits have contiguous canonical trailers. The three
original Task 8/9/10 commits remain the only exact-object exceptions; the final
closure records their old reviewed full IDs and reconstructed full IDs and proves
subject/tree/patch equality. The helper and allocator corrections each require
TDD plus restarted ordered reviews before reconstruction, and the complete Task 11
capture is invalidated again after every resulting commit-identity change.

The allocator repair passed `ALLOCATOR-REPAIR-SPEC-PASS-20260718-5DA58189-01`
and `ALLOCATOR-REPAIR-QUALITY-APPROVED-20260718-5DA58189-01`; its reconstructed
commit is `bb9f34adf666dab6acbd83bdd13f93379f178e4b`, exact tree
`5da58189921a09b6c8d6089761d2617563d855dd`, patch
`b4d97238c6b58ace40a5dd5d25f6ae812e52d52d4d12edac821eed5ce7920a12`.
Trailer-validator specification review
`TRAILER-VALIDATOR-SPEC-FAIL-20260718-E7832E2E-01` rejected a case-insensitive
relevant-key hole; the corrected tree then passed
`TRAILER-VALIDATOR-SPEC-PASS-20260718-156045E6-02` and
`TRAILER-VALIDATOR-QUALITY-APPROVED-20260718-156045E6-01`. Its reconstructed
commit is `70e2ea3c3df9e6b820166b0b182fd1b34c6516cb`, exact tree
`156045e6ac6f9ceb6a79bdc6f70ce3d32a1782c7`, patch
`c47aa98f198e317562dab05dcfb2ad85a44b3b373c78704a0914d4596ca4f8db`.
The linear metadata reconstruction then completed atomically with zero content diff.
The exact old-to-new mapping is:

- `a2a755ba3c3de53a64f14cc2bfad8fcb85d27e99` ->
  `8cafe882a9fcce28fb9d533f32ffd26a6456fe95`
- `dec0357e85aba4977c24caabe10b103be7d737ce` ->
  `43345c37e17a23130d1c35af6e46c792fb3a5d4e`
- `185268b2c222a9ffb42d0774e5d400c71b8241af` ->
  `044b32781d7468a8ea78d64c19f13d426eef9d14`
- `b43a20252633250bc9ac152edfffb26b35966930` ->
  `6fa32d0deaa65d583f758a08f51958c5d04e6189`
- `cd2f4c1f9aebb0a735bbdba3566726fa14e12dda` ->
  `a1fe6cdec6d10afa3513cabab39e932e33a630cf`
- `dd23f224684fdd104e3c8181a21f90ae997702a1` ->
  `8e4645e56e8ce29ab23c7fb6d23f87beee9b74f2`
- `42e0ebc3445f63e05c094b71f069369d763b1985` ->
  `fff1b1fcb1d6af9f9582a55ed9120f28915a6c90`
- `42839223d126b0070f2978c0f6da5696c6bda65e` ->
  `d9fc6b9f43621f7995ffc416d9896bc1e691b46f`
- `be8247ead9f1b3fc73997f50b9bdbd40a4a37784` ->
  `6fa662fd032ac9ae4b58e0503665afd07343af26`
- `4d0067bb426e4b4473ca7947540b93edf317f887` ->
  `95dd3f75097a63a62489252058d9c6d1fdc1e729`
- `128990096b87d3cb70218278aea3e982586faebc` ->
  `1f424cc9ae2f18a4a33c4c4732692ef642430c76`
- `21de86ceffd9a31262e86741871d75d279215e21` ->
  `a13852900c6ce212776a061c2ccdbb1e1e75e002`
- `fa54148be469f4d58755079bf8b02766738328d5` ->
  `cb8e2d892b82fc825bcbc0759c3f447104c50a0d`
- `540fa4807818399c915f9600090803237231539c` ->
  `bb9f34adf666dab6acbd83bdd13f93379f178e4b`
- `fec82759b8db94f125e9e9f27ea9d0b0fb795b0f` ->
  `70e2ea3c3df9e6b820166b0b182fd1b34c6516cb`

All 15 pairs have identical subjects, trees, author/committer identities and
timestamps, and corresponding-parent binary patch digests. The 12 directly
reviewed reconstructed commits expose all four canonical fields through
`git interpret-trailers --parse`; the three exact exemptions expose none.
The Task 3 genericity test's abandoned Task 2 history literal is updated to the
reconstructed full ID before Task 11 recapture.

- [x] **Step 1: Run the complete focused tranche.**

```bash
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task11/current"
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
if tmux -S "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
  echo "refusing to replace existing tmux session: $SESSION" >&2
  exit 1
fi
rm -rf -- "$CAPTURE_ROOT"
python scripts/provider_prompt_dependency_broad_gate.py capture-subject \
  --output "$CAPTURE_ROOT/subject.json" \
  --ignored-evidence-root "$CAPTURE_ROOT" \
  --generated-evidence-layout broad-v1 \
  --protected docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  --protected docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  --protected docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  --protected state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  --protected tests/test_workflow_non_progress_step_back_demo.py \
  --protected workflows/examples/non_progress_step_back_demo.yaml \
  --protected workflows/library/prompts/workflow_step_back/diagnose_non_progress.md \
  --allowed-untracked docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md \
  --task-subject docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md \
  --allowed-post-launch-update docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
pytest -q \
  tests/test_workflow_lisp_provider_prompt_dependencies.py \
  tests/test_prompt_dependency_content_snapshot.py \
  tests/test_provider_attempt_allocation.py \
  tests/test_prompt_dependency_evidence.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_provider_prompt_dependency_broad_gate.py \
  tests/test_dependency_injection.py \
  tests/test_dependency_resolution.py \
  tests/test_prompt_contract_injection.py \
  tests/test_injection_integration.py \
  tests/test_adjudicated_provider_runtime.py \
  tests/test_adjudicated_provider_resume.py \
  tests/test_state_manager.py \
  tests/test_workflow_state_compatibility.py \
  tests/test_workflow_lisp_lexical_checkpoint_restore.py \
  tests/test_workflow_lisp_lexical_checkpoint_default_resume.py
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
```

Expected: all pass with only already-reviewed platform skips.

Fresh evidence at implementation HEAD
`5f4800191cc88652f0d26bc7c1f9e9f49c358cf7`: the launch-phase subject
verification passed before and after the focused tranche, and the focused
tranche passed `736` tests in `25.44s`. The fresh subject manifest has file
SHA-256 `29092aa55f420508a9b1c8fc9f8e5cddbdaebfb7cc0ea6e8a51d487e7dab5234`,
record SHA-256 `877f01e4794499975e57e06244cfce0197af635aeb4b44d9258f4653e4aa82d8`,
and index tree `85c7478f29bf75dc36e42c88178b117d5c28e72e`.

- [x] **Step 2: Run genericity, absence, and source guards.**

Read the exact implementation base from the Task 1 golden and require it to be an
ancestor of the current implementation HEAD. The genericity scan covers only the
following exact feature-owned production and generic CLI paths and only added
lines in that exact base range; it does not reject generic words such as
`provider`, `module`, `workflow`, or `compiler`. Both CLIs are in this guard:
the broad-gate helper must not classify by family, provider, or feature identity,
and the offline evidence CLI must remain free of concrete workflow, family,
module, or provider identity branches.

```bash
PROMPT_DEPS_BASE="$(python -c \
  'import json; print(json.load(open("tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json", encoding="utf-8"))["implementation_base_commit"])')"
PROMPT_DEPS_HEAD="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$PROMPT_DEPS_BASE" "$PROMPT_DEPS_HEAD"

PROMPT_DEPS_PRODUCTION_PATHS=(
  orchestrator/workflow_lisp/expressions.py
  orchestrator/workflow_lisp/expression_traversal.py
  orchestrator/workflow_lisp/typecheck_effects.py
  orchestrator/workflow_lisp/functions.py
  orchestrator/workflow_lisp/procedure_specialization.py
  orchestrator/workflow_lisp/workflow_refs.py
  orchestrator/workflow_lisp/wcc/route.py
  orchestrator/workflow_lisp/wcc/elaborate.py
  orchestrator/workflow_lisp/wcc/defunctionalize.py
  orchestrator/workflow_lisp/lowering/context.py
  orchestrator/workflow_lisp/lowering/effects.py
  orchestrator/workflow_lisp/lowering/core.py
  orchestrator/workflow_lisp/lowering/origins.py
  orchestrator/workflow_lisp/source_map.py
  orchestrator/workflow_lisp/build.py
  orchestrator/workflow_lisp/build_artifacts.py
  orchestrator/workflow_lisp/lexical_checkpoints.py
  orchestrator/workflow/prompt_dependency_contract.py
  orchestrator/workflow/validation.py
  orchestrator/workflow/elaboration.py
  orchestrator/workflow/surface_ast.py
  orchestrator/workflow/core_ast.py
  orchestrator/workflow/lowering.py
  orchestrator/workflow/executable_ir.py
  orchestrator/workflow/runtime_step.py
  orchestrator/workflow/semantic_ir.py
  orchestrator/workflow/persisted_surface.py
  orchestrator/dashboard/compiled_workflow.py
  orchestrator/deps/safe_io.py
  orchestrator/deps/content_snapshot.py
  orchestrator/deps/resolver.py
  orchestrator/deps/injector.py
  orchestrator/deps/__init__.py
  orchestrator/state_locking.py
  orchestrator/state.py
  orchestrator/workflow/call_frame_state.py
  orchestrator/workflow/executor_runtime.py
  orchestrator/workflow/provider_attempts.py
  orchestrator/workflow/prompt_dependency_evidence.py
  orchestrator/workflow/prompting.py
  orchestrator/workflow/executor.py
  orchestrator/workflow/adjudication_bindings.py
  orchestrator/workflow/adjudication_candidates.py
  orchestrator/cli/commands/run.py
  orchestrator/cli/commands/resume.py
  scripts/provider_prompt_dependency_broad_gate.py
  scripts/validate_prompt_dependency_evidence.py
)

FORBIDDEN_CONCRETE_IDENTITIES='verified[_-]iteration[_-]drain|generic[_-]run[_-]watchdog|tracked[_-]plan[_-]phase|remaining[_-]neurips[_-]migration[_-]experiment|codex|claude|anthropic|openai'
GENERICITY_DIFF="$(mktemp "${TMPDIR:-/tmp}/prompt-deps-genericity-diff.XXXXXX")" || exit 1
GENERICITY_ADDED="$(mktemp "${TMPDIR:-/tmp}/prompt-deps-genericity-added.XXXXXX")" || {
  rm -f -- "$GENERICITY_DIFF"
  exit 1
}
cleanup_prompt_deps_genericity() {
  rm -f -- "$GENERICITY_DIFF" "$GENERICITY_ADDED"
}
trap cleanup_prompt_deps_genericity EXIT HUP INT TERM

if ! git diff --unified=0 \
    "$PROMPT_DEPS_BASE".."$PROMPT_DEPS_HEAD" -- \
    "${PROMPT_DEPS_PRODUCTION_PATHS[@]}" > "$GENERICITY_DIFF"; then
  echo 'git diff failed while constructing the genericity subject' >&2
  exit 1
fi

if ! awk '
  /^diff --git / { in_file_header = 1; saw_old_header = 0; next }
  in_file_header && /^--- / { saw_old_header = 1; next }
  in_file_header && saw_old_header && /^\+\+\+ / {
    in_file_header = 0
    saw_old_header = 0
    next
  }
  in_file_header { next }
  /^\+/ { print substr($0, 2) }
  END { if (in_file_header) exit 2 }
' "$GENERICITY_DIFF" > "$GENERICITY_ADDED"; then
  echo 'awk failed while extracting added production lines' >&2
  exit 1
fi

if rg -ni "$FORBIDDEN_CONCRETE_IDENTITIES" "$GENERICITY_ADDED"; then
  FORBIDDEN_RC=0
else
  FORBIDDEN_RC=$?
fi
case "$FORBIDDEN_RC" in
  0)
    echo 'concrete workflow/family/provider identity entered generic mechanism' >&2
    exit 1
    ;;
  1) ;;
  *)
    echo "rg failed while scanning added production lines: $FORBIDDEN_RC" >&2
    exit 1
    ;;
esac

cleanup_prompt_deps_genericity
trap - EXIT HUP INT TERM

pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py::test_prompt_dependency_generic_mechanism_has_no_concrete_identity_branch
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py::test_prompt_dependency_genericity_added_line_extractor_rejects_leading_plus_identity
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py::test_prompt_dependency_absence_keeps_runtime_plan_bytes_exact
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k keyword_free
pytest -q tests/test_prompt_dependency_evidence.py::test_runtime_modules_do_not_import_or_call_offline_prompt_dependency_validator
```

Expected: the base is an ancestor, the added-line identity scan prints nothing,
the leading-plus bypass regression passes, and all five functional
behavioral/source guards pass. The pathname-content-reader selector is
deliberately excluded because the user excluded all security-related work; this
is a scope exclusion, not a failing or missing functional result. The
offline-validator guard rejects only terminal validator/index APIs in runtime
modules, not the current-attempt record publisher. This avoids false positives
from ordinary generic provider or module terminology.

Fresh evidence: the implementation base
`451765a2ebd374111d2cbeab0969cec4830717fb` is an ancestor of the implementation
HEAD `5f4800191cc88652f0d26bc7c1f9e9f49c358cf7`; the genericity subject contains
`7195` added lines and zero forbidden
identity matches. The genericity diff SHA-256 is
`46f3e288598cd0e14f2d58866455738fc2dfe52158cd423bcc607ee1ec817a9d`,
the extracted-added-lines SHA-256 is
`727cf80c4d93b8cb29fee67ae2ef6dad6450ac8783784d2d9d8ce4baba1978f0`,
and all five functional guards passed.

- [x] **Step 3: Run the broad suite in persistent tmux.**

Use a private socket and a remain-on-exit pane so process completion is
observable. Closed command-status records, rather than tmux pane metadata, are
exit authority. The pane exits zero only when collection completed, pytest
produced a normal test outcome (`0` or `1` rather than a collection/runtime
crash), and both raw artifacts and status records exist. The comparator, not the
pane wrapper, decides whether pytest's recorded exit and failures satisfy the
reviewed baseline.

Every block below is deliberately self-contained because tool calls start fresh
shells. Do not omit or rely on a prior value of `SOCKET`, `SESSION`, or
`CAPTURE_ROOT`.

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task11/current"
mkdir -p "$SOCKET_DIR"
if tmux -S "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
  echo "refusing to replace existing tmux session: $SESSION" >&2
  exit 1
fi
test -f "$CAPTURE_ROOT/subject.json"
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
tmux -S "$SOCKET" new-session -d -s "$SESSION" -n pytest -c "$PWD"
tmux -S "$SOCKET" set-option -t "$SESSION" remain-on-exit on
BROAD_COMMAND='set -o pipefail
pytest --collect-only -q > .orchestrate/tmp/provider-prompt-dependencies-task11/current/collection.log 2>&1
collect_rc=$?
python scripts/provider_prompt_dependency_broad_gate.py write-command-status --output .orchestrate/tmp/provider-prompt-dependencies-task11/current/collection.status.json --phase collection --exit-code "$collect_rc" --arg pytest --arg=--collect-only --arg=-q
pytest -q -n 16 --dist=worksteal --junitxml=.orchestrate/tmp/provider-prompt-dependencies-task11/current/junit.xml 2>&1 | tee .orchestrate/tmp/provider-prompt-dependencies-task11/current/broad.log
pytest_rc=${PIPESTATUS[0]}
python scripts/provider_prompt_dependency_broad_gate.py write-command-status --output .orchestrate/tmp/provider-prompt-dependencies-task11/current/broad.status.json --phase broad --exit-code "$pytest_rc" --arg pytest --arg=-q --arg=-n --arg=16 --arg=--dist=worksteal --arg=--junitxml=.orchestrate/tmp/provider-prompt-dependencies-task11/current/junit.xml
printf "__COLLECT_EXIT__=%s\n__PYTEST_EXIT__=%s\n" "$collect_rc" "$pytest_rc"
test "$collect_rc" -eq 0 || exit "$collect_rc"
test "$pytest_rc" -eq 0 -o "$pytest_rc" -eq 1
wrapper_rc=$?
exit "$wrapper_rc"'
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -l -- "$BROAD_COMMAND"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 Enter
```

Immediately print copy/paste monitor commands with their concrete expanded
socket/session values. This print block is also self-contained:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
printf 'To monitor: tmux -S %q attach -t %q\n' "$SOCKET" "$SESSION"
printf 'To capture: tmux -S %q capture-pane -p -J -t %q:0.0 -S -200\n' "$SOCKET" "$SESSION"
```

Poll at intervals below 60 seconds with this self-contained status block;
`pane_dead` is the only normative tmux field and reports liveness only:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
tmux -S "$SOCKET" display-message -p -t "$SESSION":0.0 '#{pane_dead}'
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

Completion requires exactly `1` from `pane_dead`, plus closed status records and
captured `__COLLECT_EXIT__=0` and `__PYTEST_EXIT__=0|1`. Preserve and verify the
complete pane before killing the session; this final block also recomputes every
value:

```bash
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task11/current"
test "$(tmux -S "$SOCKET" display-message -p -t "$SESSION":0.0 '#{pane_dead}')" = '1'
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S - > "$CAPTURE_ROOT/pane.log"
rg -n '^__COLLECT_EXIT__=0$' "$CAPTURE_ROOT/pane.log"
rg -n '^__PYTEST_EXIT__=(0|1)$' "$CAPTURE_ROOT/pane.log"
test -s "$CAPTURE_ROOT/collection.log"
test -s "$CAPTURE_ROOT/collection.status.json"
test -s "$CAPTURE_ROOT/junit.xml"
test -s "$CAPTURE_ROOT/broad.log"
test -s "$CAPTURE_ROOT/broad.status.json"
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
tmux -S "$SOCKET" kill-session -t "$SESSION"
```

Rerun every baseline row in isolation with the identical capture driver and
artifact grammar used by Task 1. This block is self-contained and does not trust
shell command text from JSON:

```bash
BASELINE="tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json"
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task11/current"
python - "$BASELINE" "$CAPTURE_ROOT" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

baseline = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rows = baseline["failure_rows"]
if len(rows) != 6:
    raise SystemExit("baseline must contain exactly six failure rows")
root = Path(sys.argv[2]) / "isolated"
root.mkdir(parents=True, exist_ok=False)
for index, row in enumerate(rows):
    nodeid = row["nodeid"]
    stem = f"row-{index:02d}"
    log_path = root / f"{stem}.log"
    junit_path = root / f"{stem}.xml"
    argv = [sys.executable, "-m", "pytest", "-q", nodeid, f"--junitxml={junit_path}"]
    with log_path.open("wb") as stream:
        completed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if completed.returncode not in (0, 1):
        raise SystemExit(f"isolated row {index} ended with non-test status {completed.returncode}")
    status = {
        "schema": "workflow_broad_isolated_status.v1",
        "row_index": index,
        "nodeid": nodeid,
        "argv": argv,
        "exit_code": completed.returncode,
    }
    (root / f"{stem}.status.json").write_bytes(
        json.dumps(status, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )
PY
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
```

Build and compare the closed outcome. `build-outcome` must parse and digest all
six fresh isolated logs/JUnit/status files, derive each canonical failure payload
itself, and cross-check isolated and broad-JUnit outcomes. The remediation
directory may be absent or empty; every present record must already be committed
and independently reviewed. `compare` enumerates every directory entry, rejects
non-regular/symlink/non-JSON/non-record entries, validates each record's canonical
path, exact committed bytes, ancestry, trees, and independent ordered review
trailers before selecting either exact or subset mode, and rejects overlapping
records:

```bash
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task11/current"
BASELINE="tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json"
REMEDIATIONS="docs/plans/evidence/provider-prompt-dependencies/broad-remediations"
python scripts/provider_prompt_dependency_broad_gate.py build-outcome \
  --baseline "$BASELINE" \
  --subject-manifest "$CAPTURE_ROOT/subject.json" \
  --capture-root "$CAPTURE_ROOT" \
  --output "$CAPTURE_ROOT/outcome.json"
python scripts/provider_prompt_dependency_broad_gate.py compare \
  --baseline "$BASELINE" \
  --outcome "$CAPTURE_ROOT/outcome.json" \
  --remediation-dir "$REMEDIATIONS"
```

After recording the permitted Task 11 Steps 1-3 evidence update in this plan,
and before computing or staging the review freeze, verify the generated evidence
against that allowed post-launch transition:

```bash
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch \
  --generated-evidence "$CAPTURE_ROOT/outcome.json"
```

Expected: comparator exit `0` under exactly one closed acceptance branch above.
A raw pytest exit `1` is acceptable only when its complete observed set equals
the reviewed baseline minus reviewed remediations. Do not infer acceptance from
pane death, pytest's exit alone, or a human reading of the failure summary.

Fresh evidence: collection exited `0` with `5810` collected tests. The broad
suite exited `1` with exactly `6` failed, `5787` passed, `17` skipped, `33`
warnings, and `5810` total in `53.45s`; every one of the six baseline rows also
exited `1` in isolation.
The comparator accepted the exact-baseline branch. The baseline file SHA-256 is
`b32732ba7cf1d70b70694d7edabc4a28100d6d80313711b6402f4fa6af0825fe`
and its record SHA-256 is
`513802fc9ba0ab9ac93c0278c0f1283c55b94d428309ea83e133c14dcfc666fa`.
The remediation directory was absent, so no remediation record was selected.
The outcome file SHA-256 is
`7a2974c75d9090e0714a4ad3700b9408eb0aff2eceb82fb0ebfcd20a965b82b9`
and its record SHA-256 is
`b4a5aea8a2e3ed9c6f7e23ff851e0f251dfb1ab433c24b7551c03b58101413d4`.
The allowed untracked YAML plan remained byte-identical at SHA-256
`2de3c7aafd13e7518f9030621fcc1a13a70daa8ae1418c6bf81be1d3f8918d2d`.

- [x] **Step 4: Freeze the implementation-gate subject and dispatch holistic
  reviews.**

Dispatch one independent specification reviewer and one independent functional-
quality reviewer against the exact implementation tree and all fresh command
evidence. Security review is explicitly excluded by the user's scope. Both
functional reviews must approve before any durable document says “Implemented.”
Apply the digest-stable protocol, including setting this checkbox and the intended
Task 11 execution status plus the validated outcome's `record_sha256`, collection
exit/count, pytest exit/totals, comparison branch, baseline digest, and remediation
digests before `REVIEW_TREE` is computed. Dispatch specification review first and
functional-quality review only after specification PASS. Set `CAPTURE_ROOT` to the
Task 11 root and `TASK_EVIDENCE` to its `outcome.json`; build and verify the closed
review-subject envelope after staging the plan update. The envelope must prove
that this plan is the only post-launch tracked-byte change and bind its exact
launch/review hashes. Re-run review-phase verification after each verdict and
immediately before commit.

**Post-review commit:** After both reviewers approve the unchanged tree, prove the
patch/tree digests still match and commit without editing this plan or any other
tracked byte.

Suggested commit: `test: gate prompt dependency implementation`

## Task 12: Update Durable Functional Contracts And Close The Generic Roadmap Gap

**Owner:** fresh documentation/contracts implementer after Task 11 is committed.

**Files:**

- Modify `specs/dependencies.md`
- Modify `specs/providers.md`
- Modify `specs/state.md`
- Modify `docs/design/workflow_lisp_frontend_specification.md`
- Modify `docs/design/workflow_lisp_semantic_workflow_ir.md`
- Modify `docs/design/workflow_lisp_executable_ir.md`
- Modify `docs/lisp_workflow_drafting_guide.md`
- Modify `docs/capability_status_matrix.md`
- Modify `docs/design/README.md`
- Modify `docs/index.md`
- Modify `docs/workflow_yaml_orc_gap_list.md`
- Modify `docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md`
- Modify `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify `tests/test_workflow_yaml_orc_gap_list.py`
- Modify this plan

- [x] **Step 1: Write routing/status RED tests.**

Require exact discoverability and truthful labels: typed prompt dependencies are
Implemented for the retained functional contract; YAML content mode remains
legacy with stable-success compatibility and fresh-per-retry behavior; runtime
plan remains topology-only; evidence is non-authoritative; the generic
provider-input gap closes without promoting
`verified_iteration_drain` or `generic_run_watchdog`.

- [x] **Step 2: Update normative specs from the landed behavior.**

Document exact authoring, order, cap, selected-file failure categories, retry
snapshot, allocator/state, evidence/index, checkpoint, and resume contracts.
Remove or qualify stale catch-and-skip and approximate-cap text. Keep excluded
clauses outside this functional documentation tranche. Do not include roadmap
progress in durable specs.

- [x] **Step 3: Update design and drafting docs.**

Add the public syntax/type examples and explain required versus optional exact
paths, deterministic order, truncation, and completed-result
reuse. Keep examples free of family names and do not present globs/dynamic paths as
supported `.orc` forms.

- [x] **Step 4: Update status/routing docs and close design status.**

Bind the implementation commits, focused/broad results, and both reviews. Mark the
retained functional subset implemented without widening its claim. Route the next
survivor-port work to this mechanism; do not claim port parity evidence exists.

- [x] **Step 5: Run documentation/routing selectors.**

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py tests/test_workflow_yaml_orc_gap_list.py
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies.py -k 'keyword_free or docs or genericity'
```

- [x] **Step 6: Re-run the real `.orc` smoke.**

```bash
pytest -q tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
```

Fresh Task 12 evidence: both changed routing modules collected 54 tests. The
RED selectors failed on the missing matrix/index/gap closure and the still-open
Task 12 status as intended. After the functional contract updates, the
documentation/genericity selector passed 2 tests with 62 deselected and the
real `.orc` end-to-end module passed 11 tests. The final complete routing result
after the checklist transition was 54 passed in 0.58 seconds; the routing guard
itself requires Steps 1-7 checked in the immutable review subject.

- [x] **Step 7: Freeze the documentation subject and dispatch the ordered
  reviews.**

Apply the digest-stable protocol. Reviewers must check consistency among specs,
design, matrix, gap list, drafting guide, indexes, and actual test evidence.
Review only the retained functional contract. Dispatch quality review only after
specification PASS.

**Post-review commit:** After both reviewers approve the unchanged tree, verify
the patch/tree pair again and commit without editing tracked bytes.

Suggested commit: `docs: close prompt dependency prerequisite`

## Task 13: Final Exact-Tree Gate And Handoff To Survivor Ports

**Owner:** final verification coordinator.

**Files:**

- Modify this plan only for final status/evidence

- [ ] **Step 1: Re-run new/renamed test collection.**

```bash
CAPTURE_ROOT=".orchestrate/tmp/provider-prompt-dependencies-task13/current"
SOCKET_DIR="${CLAUDE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/claude-tmux-sockets}"
SOCKET="$SOCKET_DIR/prompt-deps.sock"
SESSION="prompt-deps-broad"
if tmux -S "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
  echo "refusing to replace existing tmux session: $SESSION" >&2
  exit 1
fi
rm -rf -- "$CAPTURE_ROOT"
python scripts/provider_prompt_dependency_broad_gate.py capture-subject \
  --output "$CAPTURE_ROOT/subject.json" \
  --ignored-evidence-root "$CAPTURE_ROOT" \
  --generated-evidence-layout broad-v1 \
  --protected docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  --protected docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  --protected docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  --protected state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  --protected tests/test_workflow_non_progress_step_back_demo.py \
  --protected workflows/examples/non_progress_step_back_demo.yaml \
  --protected workflows/library/prompts/workflow_step_back/diagnose_non_progress.md \
  --allowed-untracked docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md \
  --task-subject docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md \
  --allowed-post-launch-update docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
pytest --collect-only -q \
  tests/test_workflow_lisp_provider_prompt_dependencies.py \
  tests/test_prompt_dependency_content_snapshot.py \
  tests/test_provider_attempt_allocation.py \
  tests/test_prompt_dependency_evidence.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_provider_prompt_dependency_broad_gate.py
python scripts/provider_prompt_dependency_broad_gate.py verify-subject \
  --manifest "$CAPTURE_ROOT/subject.json" \
  --phase launch
```

- [ ] **Step 2: Re-run focused tests and the broad tmux gate from Task 11.**

Fresh output is mandatory after the documentation commit. Use the same closed
command-status, pane-liveness, and baseline-comparator protocol; do not reuse old logs. Repeat
the complete Task 11 launch, printed-monitor, poll, final-capture/kill, isolated-
row capture, outcome-build, and compare blocks with each block independently
assigning/recomputing
`SOCKET` and `SESSION`, and use the literal capture root
`.orchestrate/tmp/provider-prompt-dependencies-task13/current`. Record the fresh
outcome digest/totals/comparison branch before freezing the Task 13 review tree.
Use the same literal canonical remediation directory from Task 11; do not copy a
record into Task 13's ignored capture root or construct any untracked remediation
input. The comparator must validate every directory entry before accepting even
an exact baseline outcome.
Do not repeat Task 11's `rm -rf`/capture-subject prelude: reuse and verify the
Task 13 manifest created in Step 1 before the focused tranche, before tmux launch,
after pane death, after isolated rows, and after outcome comparison. Pass
`--subject-manifest "$CAPTURE_ROOT/subject.json"` to `build-outcome`, then require
launch-phase verification with
`--generated-evidence "$CAPTURE_ROOT/outcome.json"`.

- [ ] **Step 3: Run cached-diff/protected-path guards and inspect exact commits.**

Confirm every task commit includes its plan checkbox update, no protected path,
no YAML-deletion plan, no family-name mechanism, and no uncommitted task file.

- [ ] **Step 4: Freeze the final exact-tree subject and dispatch holistic
  specification and quality/security reviews.**

The specification reviewer checks every design success criterion and stop/revise
criterion. The quality reviewer checks descriptor/lock cleanup, bounded memory,
deadlock safety, schema closure, stable diagnostics, absence compatibility, and
test quality. Before computing `REVIEW_TREE`, set the final plan status, all Task
13 checkboxes through this step, and every satisfied Final Acceptance Checklist
item to their intended committed values. Any fix or bookkeeping-byte change
restarts focused, broad, and both reviews with a new subject.

Set `CAPTURE_ROOT` to the Task 13 root and `TASK_EVIDENCE` to its `outcome.json`.
After staging the plan-only final status, build the review-subject envelope and
require it to prove that the plan is the sole tracked post-launch update. Supply
the launch manifest, outcome, and envelope to both reviewers; re-run review-phase
verification after each verdict and immediately before commit.

**Post-review commit:** Once both reviewers approve, prove the patch/tree pair is
unchanged and commit the reviewed final status without editing any tracked byte.

Suggested commit: `docs: complete prompt dependency implementation`

**Post-commit handoff without family claims:**

Report exact commit SHAs, focused/broad counts, platform coverage/skips, record and
index schema versions, and both review artifacts. State only that the generic
provider-input prerequisite is available. The next roadmap task may use it for
survivor `.orc` ports, but each port still requires its own artifact, prompt,
retry/resume, provider-policy, and parity evidence.

## Final Acceptance Checklist

- [ ] Public `.orc` syntax accepts only typed inline-lowerable exact relpaths.
- [ ] WCC/schema 2 and classic lowering share one owner projection.
- [ ] Typed origin metadata never travels through or reconstructs from a YAML map.
- [ ] Core/executable/persisted/Semantic/source-map views retain only their owned
  contract; runtime plan remains unchanged.
- [ ] Required/present-optional unsafe content fails before provider preparation.
- [x] Operational safe-I/O probe and unsupported-platform failure are skipped
  under the 2026-07-18 security-scope override.
- [ ] Ordinary and adjudicated retries snapshot/render exactly once per attempt.
- [ ] Truncation agrees across prompt markers, structured evidence, and the
  existing persisted provider-result `debug.injection` surface; non-truncated
  debug shape remains compatible.
- [ ] Stable YAML successful bytes remain compatible below deliberate boundaries.
- [ ] Durable root allocation is monotonic, recursive-scope-safe, and crash
  consistent.
- [ ] Retained dependency content is globally attempt-bounded independent of
  canonical-group count, while every selected file is still streamed fully for
  validation, counts, and digests.
- [ ] Records/indexes are closed, immutable, digest-verifiable, content-free, and
  quiescence-validated.
- [ ] Evidence is never runtime/resume authority.
- [ ] Pending resume snapshots fresh; completed reuse never reopens dependencies.
- [ ] Keyword-free build artifacts remain exact.
- [ ] Real `.orc` positive, negative, retry, crash, and resume E2E tests pass.
- [ ] Broad xdist suite completes normally in tmux and its closed outcome passes
  the reviewed exact-six-minus-reviewed-remediations comparator with explicit
  collection, pytest, and pane exit status, all bound to the launch subject
  manifest and unchanged review envelope.
- [ ] Independent specification and functional implementation-quality reviews approve the exact
  final tree.
- [ ] Durable docs close only the generic prerequisite and do not claim survivor
  promotion or YAML retirement.
