# Workflow Lisp E1 `run-ref` Component Implementation Plan

## Metadata

- **Status:** accepted for execution; E1 is owner-selected, Task 0 is closed,
  and Task 1 is the active implementation step
- **Owner:** agent-orchestration maintainers
- **Selected tranche:** E1 only — pinned-workspace child execution through
  `run-ref`
- **Target DSL:** 2.24
- **Baseline:** commit `11ba569b93ba4fb734c437e85bfa16b58368669a`,
  tree `2745c6b9015074e2d971c84344888210ed321c0e`
- **Selection authority:**
  `docs/plans/2026-07-31-workflow-lisp-e1-e3-owner-selection.md`
- **Required ordered plan verdicts:** `E1_PLAN_SPEC_APPROVED`, then
  `E1_PLAN_QUALITY_APPROVED`
- **Required ordered final verdicts:** `E1_FINAL_SPEC_APPROVED`, then
  `E1_FINAL_QUALITY_APPROVED`
- **Reviewed plan candidate:** commit
  `0c392ac93e2e7a0304dbda48549d8113904ab90c`, tree
  `3a55ac5f3e7dfcd9d9000d4ac3ca22474df31cb2`, plan SHA-256
  `524e7a76afd23f8dbcbd7e5b9a33514efbaf347a7a2041bc2d1a8847be899389`
- **Plan review:** `artifacts/review/e1-run-ref-plan-review.md`;
  `E1_PLAN_SPEC_APPROVED`, then `E1_PLAN_QUALITY_APPROVED`
- **Governing inputs:**
  - `docs/design/workflow_lisp_trial_runs.md`
    (`sha256:ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`)
  - `docs/design/workflow_lisp_program_search_boundaries.md`
    (`sha256:a42a1db72b887eb94cfa7c3fe93fe6e7269e99daa2867ccd484d16bbe0f0d41b`)
  - `docs/design/workflow_language_design_principles.md`
    (`sha256:36a4b4d5626e0d6f7c3444c49f74856a7d4d11cb3bad745e2c475b8b80fe0951`)
  - the accepted M2 pure-result-replay contract and landed ML
    at-least-once/single-writer contract

## Objective

Land the smallest target-2.24 `run-ref` surface that executes an exact pinned
repository revision in a fresh child workspace and returns the child value,
deterministic workspace-delta evidence, and run accounting. Both accepted
program loci must work:

1. a named workflow transported from the caller's already-compiled bundle,
   without recompilation; and
2. a clone-relative committed `.orc` entry compiled by the ordinary full
   child compiler, with rejection exposed through a stable JSON diagnostic
   API.

E1 is a durable child-run effect boundary. It is not `call`, a command
adapter, a closure, an expression evaluator, a trial scheduler, or a sandbox.
E2 and E3 remain gated until the canonical E1 exit record says `PASS_E1`.

## Direct architecture and deliberate cost

The compiler will lower a distinct `RUN_REF` leaf into shared surface, core,
semantic, executable, runtime-plan, source-map, checkpoint, and persisted
views. A new `orchestrator/workflow/run_ref/` package owns source identity,
materialization, compiled-bundle capsules, child launch, attempt ledgers,
workspace deltas, and result validation. `WorkflowExecutor` delegates to that
package; it does not assemble Git or child-process commands inline.

Mode 1 uses a private, version-local pickle-protocol-5 capsule because no
loaded-bundle decoder exists and recompilation would violate the accepted
design. The capsule is compiler-produced runtime input, never authored data or
a public interchange format. It packages the exact reachable `.orc` and
asset closure because current asset resolution and call-frame checksums read
`WorkflowProvenance.workflow_path`. The child stages those exact bytes below
its clone-local `.orchestrate/`, validates the capsule and closure, relocates
provenance to the staged copies, and runs the ordinary loaded-bundle path.

This makes a language-neutral or cross-version compiled-bundle transport,
additional source-locator schemes, setup policy changes, and loop-contained
child effects harder to add later. Those costs are preferable to a parallel
runtime, a disguised command, mutable controller-source reads, or an
unreviewed general serialization framework.

## Exact authored surface

The copy-safe target-2.24 form is:

```lisp
(run-ref
  :source (:repo "<canonical-locator>" :commit "<40-lowercase-hex-sha>")
  :program (:bundle <static-workflow-name>)
  :inputs (:input-name value-expr ...)
  :policy (:setup ((:argv ("/absolute/program" "literal-arg" ...)
                    :env (:NAME "literal-value" ...)) ...)))
```

or:

```lisp
(run-ref
  :source (:repo "<canonical-locator>" :commit "<40-lowercase-hex-sha>")
  :program (:path "relative/program.orc" :entry <static-workflow-name>)
  :inputs (:input-name value-expr ...)
  :returns Value
  :policy (:environment :deterministic-effect-free
           :setup ()))
```

The exact rules are:

- keys are closed and appear once; source and program discriminators are
  mutually exclusive;
- `:repo`, `:commit`, mode, path, entry, policy, setup argv, and setup env are
  compile-time literals; inputs are ordinary expressions;
- `:commit` is one exact lowercase 40-hex commit ID, never a branch, tag,
  abbreviated SHA, or symbolic ref;
- v1 locators are canonical absolute filesystem paths normalized to `file://`
  URIs, canonical `file://` URIs, and canonical `https://` or `ssh://` URIs.
  URI userinfo, query, fragment, scp shorthand, and implicit relative paths
  reject. A later amendment owns further schemes;
- program paths are normalized relative POSIX `.orc` paths with no empty,
  dot, parent, absolute, or backslash segment;
- mode-1 workflow names resolve statically through the compiler's reachable
  workflow catalog. The named target and its reachable bundle graph enter the
  compiled capsule even when no ordinary `call` references it;
- mode-1 inputs are checked against the exact child signature at caller
  compile time. Mode-2 input names/values are retained as typed transportable
  values, then checked against the freshly compiled child signature before
  launch;
- every existing transportable target-2.19 value is allowed. Relpath values
  are copied into deterministic clone-local input locations and rebound only
  after the child contract accepts the destination; source paths are never
  passed through as host paths;
- mode 1 has no `:returns`; its value type is the statically selected child
  return type. Mode 2 defaults to exact `Value`; optional `:returns T` accepts
  any transportable type and is checked against the child's normalized return
  contract at runtime;
- mode 1 forbids `:environment`: its statically selected bundle is authored
  and certified with the controller and may use its ordinary declared
  effects. Mode 2 requires `:environment` and v1 admits only
  `:deterministic-effect-free`. This closes the required positive and negative
  E1 generated-candidate proof without selecting provider isolation,
  sandboxing, or security work. Mode-2 programs with provider, command,
  unknown, or otherwise non-pure effects reject as
  `trial_candidate_environment_not_admissible`;
- setup uses argv directly, never a shell. `argv[0]` is absolute or a
  canonical `./` workspace-relative executable. Setup receives only declared
  env plus runtime-owned `PWD` and evidence variables; it does not inherit an
  unrecorded environment. Each command's stdout/stderr/exit/duration is
  evidence;
- `run-ref` is admitted in ordinary workflow bodies, `let*`, `if`, `match`,
  reusable calls, and effectful procedures. It is rejected in pure functions,
  pure settlement/evaluation bodies, `loop/recur`, `list/map-effect`, and
  generated repeat/for-each frames at 2.24. Existing lexical identities are
  sufficient, but equivalent nested atomic settlement is not yet proven;
  loop support requires a later reviewed amendment; and
- mode-1 children may execute reachable compiled calls and may themselves
  contain an otherwise-valid `run-ref`; each child owns a separate root.

## Compiler-owned result and evidence types

Each site receives a deterministic compiler-generated monomorphic record:

```text
RunRefResult$<site-digest> = {
  value: T,
  workspace_delta: WorkspaceDelta,
  accounting: RunRefAccounting
}
```

`T` follows the mode rules above. Do not add general generic records or model
the boundary as `WorkflowRef[T]`. Loop-state carriers establish the precedent
for compiler-generated record types. A narrow run-ref contract encoder embeds
the exact generated child-result contract under `value`, including direct
root, record, union, optional, list, map, path, and exact `Value` shapes;
ordinary record flattening is not silently stretched to support this envelope.

The fixed compiler-owned schemas are:

```text
WorkspaceDelta = {
  base: RepositoryRevisionId,
  changed_files: List[WorkspaceEntryDelta],
  deleted_files: List[WorkspaceEntryDelta],
  untracked_files: List[WorkspaceEntryDelta],
  normalized_diff: NormalizedWorkspaceDiff,
  declared_artifacts: List[DeclaredWorkspaceArtifact]
}

RunRefAccounting = {
  child_run_id: RunId,
  attempt_ordinal: Int,
  terminal_status: String,
  elapsed_ms: Int,
  setup_ms: Int,
  compile_ms: Int,
  provider_attempts: Value,
  token_usage: Value,
  cost: Value
}
```

`RepositoryRevisionId` is the accepted load-bearing nominal digest of exactly
the normalized locator, resolved commit SHA, materializer version,
submodule policy, LFS policy, and authored setup-command identity. The
verified Git tree ID, compiler/runtime identity, and post-setup baseline tree
digest are separate, digest-bound materialization/program/baseline facts in
`RunRefStepConfig`, the attempt ledger, and evidence manifest; setup output is
evidence and never changes `RepositoryRevisionId`. `WorkspaceEntryDelta`,
`NormalizedWorkspaceDiff`, and `DeclaredWorkspaceArtifact` use structural
fields for canonical relative path, kind, mode, size, old/new SHA-256, link
target, and bounded text-diff data where applicable. Unknown usage/cost stays
the exact transportable string `"UNKNOWN"`; it is never invented as zero.

Only normalized diff content is capped: 8 MiB total and 256 KiB per text
entry. All changed/deleted/untracked metadata rows remain complete and sorted
by UTF-8 path bytes. Content beyond the cap is represented by old/new digests,
sizes, the complete entry-catalog digest, omitted byte/entry counts, and an
explicit `truncated` flag. Binary files and symlinks use digest/size/target
metadata and are never decoded or followed. `.git/`, clone-local
`.orchestrate/`, and setup evidence are excluded. Special filesystem entries
fail the attempt without weakening the delta.

## Source, materialization, and program identity

`orchestrator/workflow/run_ref/source.py` owns a canonical
`run_ref_source.v1` request and `run_ref_repository_revision.v1` result.
Materialization uses ordinary bare mirrors and detached clones, never Git
worktrees:

1. normalize the locator and acquire a content-addressed mirror lock;
2. initialize/fetch an exact commit into
   `<run-ref-root>/mirrors/<source-digest>/`;
3. verify `commit^{commit}` equals the authored SHA, record `commit^{tree}`,
   reject `.gitmodules`, and reject any committed `.gitattributes` LFS filter;
4. seal the mirror manifest and perform no later network access for that
   source identity;
5. create an ordinary fresh detached clone at
   `<run-ref-root>/runs/<parent-run-id>/<step-identity>/<ordinal>/workspace`;
6. verify the checked-out product manifest against the sealed tree; and
7. run setup and freeze the post-setup baseline before child execution.

The runtime root defaults outside the parent workspace at
`~/.local/state/orchestrator/run-ref`; tests and operators may use the existing
runtime configuration/CLI plumbing to provide a different absolute root. Its
canonical path is persisted in the parent ledger and must match on resume.

The verified Git tree ID is retained in materialization evidence but does not
widen `RepositoryRevisionId`. Compiler/runtime identity v1 is the canonical
digest of Python implementation and major/minor, orchestrator version,
lowering schema, and sorted content
digests of the installed `orchestrator` package's Python/data files. Mode-2
program identity additionally hashes module names with source-read revisions,
entry name/signature, lowering route, and exact provider/prompt/command
configuration payloads. Absolute clone/build paths and timestamps are not
identity. The hermeticity fixture compiles changed bytes at the same path and
equal bytes at distinct clone roots to prove stale path-keyed reuse is absent
and normalized identity is path-independent.

## Mode-1 compiled capsule

The frontend build emits one `run_ref_bundle_capsule.v1` directory only when a
reachable 2.24 form uses mode 1. It contains:

- a protocol-5 pickle of the closed target bundle graph, using an internal
  mapping-proxy reducer and a fixed maximum byte size;
- exact reachable `.orc`, prompt-asset, and workflow-asset bytes addressed by
  canonical closure paths and SHA-256;
- selected canonical workflow/signature and import-graph identities;
- Python, orchestrator, compiler/runtime, target, lowering, capsule, and
  encoding versions;
- canonical persisted-surface, executable-IR, semantic-IR, full runtime-plan,
  core-AST, projection, and result-contract digests; and
- a canonical manifest digest plus the pickle/closure byte digests.

The trusted expected capsule digest is carried by the parent's compiled
`RunRefStepConfig`; a digest stored only beside the capsule is insufficient.
Before unpickling, the child verifies size and the parent-bound SHA. After
decoding, it requires exact `LoadedWorkflowBundle` objects, the selected
canonical workflow, a closed import graph, compatible runtime/compiler
versions, and every canonical digest. It refreezes mappings, stages and
verifies closure bytes below clone `.orchestrate/run-ref-capsule/`, relocates
bundle provenance to those staged files, then runs existing core/semantic/
executable/runtime-plan/projection validators. A behavioral test patches the
frontend reader/compiler to hard-fail and proves mode 1 never recompiles or
reads mutable controller source.

## Mode-2 diagnostics API

E1 adds an opt-in machine surface to the existing `orchestrator compile`
command, not the distinct in-language C1 `check-workflow` step:

```text
orchestrator compile candidate.orc ... --diagnostics-json
```

With the flag, stdout is exactly one
`workflow_lisp_compile_diagnostics.v1` JSON document and human diagnostic
rendering is suppressed. The document has `status: accepted|rejected`, the
selected entry/signature and normalized program identity when accepted, and
the existing ordered `serialize_diagnostic` envelopes in `diagnostics` in
both cases. Exit is 0 for accepted and 2 for rejected. Without the flag,
current CLI bytes and behavior remain unchanged. E1 child code consumes the
same library serializer; it does not parse stderr or implement a parallel
validator.

## Parent ledger, child topology, and recovery

One canonical `run_ref_attempt_ledger.v1` lives under the parent run root and
is keyed by the full runtime step identity and visit. Each append-only ordinal
row binds source, program, input, policy, config, capsule/compiler, baseline,
child-run, result-contract, result-payload, delta, accounting, and evidence
digests plus stage/status/timestamps. Writes use existing atomic/fsync helpers
under the parent run's single writer. Child state remains only in the clone's
`.orchestrate/runs/<child-run-id>` and its ordinary run-lifetime lock.

The commit sequence is:

1. allocate and persist a fresh ordinal;
2. materialize, setup, compile/decode, bind inputs, and launch the ordinary
   child through a private argument-bounded child entrypoint;
3. validate terminal child state and declared outputs;
4. freeze final workspace, delta, accounting, and evidence manifests;
5. atomically mark the ledger row `completed_pending_parent_commit`;
6. atomically persist the parent state transition that stores
   `StepResult.run_ref` plus typed artifacts and clears `current_step`; this
   existing state-file transition is the sole settlement point, and the
   result binds the exact pending ledger-row and evidence digests; and
7. append the ledger's `committed` transition. A crash between 6 and 7 is
   reconciled from the fully validated settled parent result without launching
   another child. A crash before 6 leaves an incomplete attempt that must be
   dispositioned, discarded, and rerun fresh.

On re-entry, a fully settled parent result is reused only after its bound
ledger row, all referenced digests, and the current `RunRefStepConfig` digest
validate; a missing adjacent `committed` transition is then appended as
reconciliation. A ledger row without the settled parent result, including
`completed_pending_parent_commit`, remains non-authoritative incident
evidence: the runtime records its disposition, removes exactly that attempt
workspace, allocates a new ordinal, rematerializes, and reruns. Multiple
candidate rows for one settled result, a result/row disagreement, or any
missing, malformed, changed, ambiguous, or undiscardable state fails closed.
Add lexical policy
`reuse_validated_run_ref_result`; it never becomes an effect memo key and does
not weaken root/callee checksum or checkpoint guards.

Structural refusal envelopes use the accepted `trial_*` codes and carry
`code`, `rejected_value`, and stable secondary causes. Runtime failures use a
separate closed `run_ref_*` diagnostic set for ledger invalidity, capsule
invalidity, child launch/result invalidity, delta capture failure, and
workspace-discard failure. Human prose is never routing authority.

## Scope exclusions

E1 does not implement or modify:

- `trial`, arms/repetitions, concurrency, adjudication, blinding,
  preregistration, evaluation, promotion, or the E3 controller;
- C1/C2/C3 or an in-language compile/check step;
- runtime `eval`, code values, closures, dynamic workflow refs, hot swap,
  checkpoint import, or a reduced candidate compiler;
- Git worktrees, submodules, LFS, cross-DSL/compiler-version children, setup
  caching, incremental compilation, or candidate-commit identity;
- provider isolation, sandboxing, permission policy, secrets, CLI safety, or
  any other security-related implementation or test. Existing security,
  safety, secrets, and provider-isolation modules/tests remain untouched;
- effect-loop placement at target 2.24; or
- prompt instructions for deterministic obligations. Identity, admission,
  binding, output validation, and evidence are compiler/runtime duties.

## Execution discipline

Use Subagent-Driven Development with no worktrees. Every behavior task starts
with the narrowest missing-behavior RED, implements only enough to turn it
GREEN, obtains an independent specification review followed by a distinct
quality review, commits exact reviewed paths, and runs its named postcommit
control. A material correction restarts the ordered review pair; unchanged
surfaces are not re-reviewed. New/renamed test modules receive
`pytest --collect-only -q`. Long or broad tests run in tmux. The final broad
gate is `pytest -q -n 16 --dist=worksteal` with the standing user-directed
security/safety/secrets/provider-isolation exclusions.

---

## Task 0A: Close the preacceptance hermetic full-compile entry proof

**Files:** create `tests/test_workflow_lisp_e1_compile_hermeticity.py`; this
plan's exact proof record only.

- [x] Run the ordinary full in-memory frontend twice in one process at one
      canonical source path with changed entry and imported-module bytes;
      require fresh source revisions and changed normalized compiler output,
      never a stale cache hit.
- [x] Compile byte-identical source/dependency trees at two distinct clone
      roots; require equal path-normalized semantic/executable/runtime/persisted
      outputs and equal module-name-to-source-digest vectors. Record that the
      existing frontend build fingerprint is allowed to remain path-bound and
      is therefore not an E1 program/repository identity input.
- [x] Require the exact compiler source/configuration read traces to enumerate
      every observed file input. Name any remaining process/compiler input
      that the existing compiler does not capture; Task 2 must bind it through
      the separate compiler/runtime identity before child execution.
- [x] Prove malformed source rejects through the ordinary compiler's stable
      structured diagnostic rather than a parallel validator.
- [x] Run collect-only and the focused fixture, bind fresh results in this
      plan, and do not accept the plan if stale reuse or an unnamed ambient
      input remains.

Task 0A result: `tests/test_workflow_lisp_e1_compile_hermeticity.py`
(`sha256:bb7bc47ccdee6e3e3e7e5847e2d4c1b5a3d75194bc6d47014bb6804e0c97382a`)
collects five tests and passed five of five. The same-process entry and
dependency mutations produced fresh source revisions and changed normalized
compiler payloads; byte-identical trees at distinct roots produced equal
root-normalized core, semantic, executable, runtime-plan, boundary, and
persisted views plus the exact module-name-to-source-digest vector; the read
vectors enumerated both source files and all three configuration files; and
malformed input produced the ordinary compiler's structured `type_unknown`
diagnostic. No stale cache reuse was observed.

The probe also confirmed that the existing frontend fingerprint and derived
provenance include absolute build/source-root spellings. They are build-cache
metadata, not E1 identity. Exact compiler/runtime implementation identity is
the one named input absent from the current source/configuration read vectors;
Task 2 must add and test that separate binding before any child is executable.
No other ambient compiler input was observed by this fixture.

## Task 0B: Review and accept this component plan

**Files:** this plan; `artifacts/review/e1-run-ref-plan-review.md`; exact E1
status/routing rows in the E roadmap, execution sequence, design router,
capability matrix, docs index, and routing tests.

- [x] Commit the proposed plan while status remains plan-review-pending and
      bind the completed Task 0A result.
- [x] Obtain `E1_PLAN_SPEC_APPROVED` against the exact commit and governing
      design digests; correct material findings and repeat if needed.
- [x] Obtain distinct `E1_PLAN_QUALITY_APPROVED` once.
- [x] Record verdicts and reviewed plan SHA, change status to
      accepted-for-execution, add behavioral routing assertions, and commit.
- [x] Run the complete routing module postcommit.

Task 0B review closed against commit `0c392ac9`, tree `3a55ac5f`, after
ordered `E1_PLAN_SPEC_APPROVED` then `E1_PLAN_QUALITY_APPROVED`. The exact
bindings, corrected findings, and E1-only execution boundary are recorded in
`artifacts/review/e1-run-ref-plan-review.md`. Task 1 may now begin; this gate
does not claim target 2.24 behavior exists yet or make E2 eligible.
The acceptance/routing candidate landed at
`04c13f992e3cc32d4280ab2e2a07daf3f927b67c`, tree
`0b0b34170d1c865a5664240b7668b3c8ae9c88a6`; its postcommit routing plus
hermeticity control passed 76 tests (71 routing and five hermeticity).

## Task 1: Land target-2.24 normative contracts first

**Files:** `specs/dsl.md`, `specs/state.md`, `specs/versioning.md`,
`specs/index.md`; create focused target-2.24 contract tests.

- [ ] Add RED assertions for unsupported 2.24 and absent normative rows.
- [ ] Specify the exact syntax, generated result/evidence types, refusal and
      runtime diagnostic families, target gate, state/ledger/reuse contract,
      mode split, loop exclusion, and non-security boundary above.
- [ ] Update supported-target routing only; no runtime behavior yet.
- [ ] Run collect-only, spec/version selectors, ordered reviews, commit, and
      postcommit controls.

## Task 2: Prove and implement source identity and materialization

**Files:** create `orchestrator/workflow/run_ref/{contracts,source,workspace}.py`;
create `tests/test_workflow_run_ref_source.py` and fixture repositories.

- [ ] RED: locator/revision separation, changed-same-path compiler input,
      equal-content/different-root normalized identity, exact checkout,
      mirror reuse, no post-seal fetch, preexisting workspace, submodule/LFS,
      setup identity, symlink, and special-entry cases.
- [ ] Implement canonical identities, locked bare mirrors, ordinary detached
      clones, setup evidence, and reusable generic tree-freeze primitives.
- [ ] Prove no Git worktree command is used and no source fetch occurs after
      sealing.
- [ ] Run source/materialization/property selectors, ordered reviews, commit,
      and postcommit controls.

## Task 3: Add the structured compile-diagnostics API

**Files:** `orchestrator/workflow_lisp/diagnostics.py`,
`orchestrator/cli/commands/compile.py`, `orchestrator/cli/main.py`;
create/modify non-security CLI compiler tests.

- [ ] RED: success and failure produce the exact versioned JSON document;
      unflagged CLI behavior is unchanged; diagnostics preserve stable codes,
      source locations, phases, and order.
- [ ] Implement one shared serializer consumed by CLI and later child code.
- [ ] Prove this is external batch compilation, not C1 or a parallel checker.
- [ ] Run compile/diagnostic/CLI selectors, ordered reviews, commit, and
      postcommit controls.

## Task 4: Add the typed `run-ref` compiler and shared IR surface

**Files:** form/syntax/expression/effect/typecheck/contract/WCC modules;
shared `surface_ast.py`, `core_ast.py`, `semantic_ir.py`, `executable_ir.py`,
`runtime_plan.py`, `runtime_step.py`, lowering, persisted-surface and
source-map modules; create `tests/test_workflow_lisp_run_ref.py`.

- [ ] RED exact copy-safe syntax for both modes, direct/record/union/list/
      map/optional/path/Value returns, static mode-1 signature/input checking,
      optional mode-2 refinement, and closed malformed-form diagnostics.
- [ ] RED purity/effect tests admit ordinary/branch/procedure placement and
      reject functions, settlement/evaluation bodies, and effect loops.
- [ ] Add generated site/result types, specialized envelope contract encoder,
      `RunsRefEffect`, `SurfaceStepKind.RUN_REF`, `ExecutableNodeKind.RUN_REF`,
      closed config, semantic effect/state rows, source maps, WCC carriage,
      checkpoint policy, and persisted round-trip validation.
- [ ] Run compiler/IR/persisted/checkpoint selectors, ordered reviews, commit,
      and postcommit controls.

## Task 5: Implement the self-contained compiled-bundle capsule

**Files:** create `orchestrator/workflow/run_ref/bundle_transport.py` and
private child command; modify build artifact/provenance plumbing; create
`tests/test_workflow_run_ref_bundle_transport.py`.

- [ ] RED: missing/tampered/oversize/version-skewed pickle, closure, signature,
      and canonical IR digests reject before decode/execution.
- [ ] RED: an asset-using bundle with an imported call executes from staged
      closure bytes after original source/assets are made unreadable; patched
      compiler/reader functions are never called.
- [ ] Using Task 4's reachable mode-1 forms and closed step config, emit the
      closed capsule only for those forms, stage/relocate it, refreeze decoded
      mappings, and run existing cross-validators.
- [ ] Run build/bundle/call/asset selectors, ordered reviews, commit, and
      postcommit controls.

## Task 6: Close mode-2 compilation and admissible-environment proof

**Files:** create the run-ref child compile/admission module and focused mode-2
tests only; do not add parent launch/ledger behavior yet.

- [ ] RED ordinary full child compile from the pinned root, structured compile
      rejection, missing program, signature mismatch, all transportable input
      bindings, and no reduced compiler path.
- [ ] RED admits an effect-free committed candidate and rejects provider,
      command, unknown, submodule, and LFS candidates with the exact accepted
      refusal envelope. Do not invoke or modify isolation/security code.
- [ ] Bind normalized source/config/compiler identity and prove equal pinned
      inputs produce equal program/evidence digests.
- [ ] Run mode-2/compiler/effect selectors, ordered reviews, commit, and
      postcommit controls.

## Task 7: Implement the parent runtime, child launch, ledger, and delta

**Files:** create `orchestrator/workflow/run_ref/{child,ledger,runtime}.py`;
minimal executor/state/checkpoint dispatch changes; create
`tests/test_workflow_run_ref_runtime.py`.

- [ ] RED distinct parent/child roots and locks, exact input/path copying for
      both compiled program modes, setup-before-baseline, typed output
      validation, complete deterministic delta, accounting `UNKNOWN`
      behavior, and declared artifacts.
- [ ] RED crash injection at allocation, materialize, setup, mode-1 decode or
      Task 6 mode-2 compile, launch, child completion, delta, and parent commit
      boundaries.
- [ ] Require incomplete-attempt disposition + exact workspace deletion +
      fresh ordinal; require completed-result validation/reuse with zero child
      launches. Tamper/ambiguity/discard failure stays fail-closed.
- [ ] Implement only the delegated runtime service and minimum shared state
      field/configuration plumbing over the landed mode-1 and mode-2 services.
- [ ] Run runtime/state/resume/replay selectors, ordered reviews, commit, and
      postcommit controls.

## Task 8: Prove both modes end to end and close E1 feasibility proofs

**Files:** create `tests/e2e/test_e2e_workflow_lisp_run_ref.py`; production
changes only for a newly exposed E1 contract defect through a fresh RED.

- [ ] Execute mode 1 with an imported call and asset, and mode 2 with a direct
      transportable result, in exact pinned fixture repositories.
- [ ] Prove separate roots/writers, typed envelopes, reproducible identities
      and delta bytes, complete metadata, mode-1 zero recompilation, mode-2
      full compilation, committed reuse, and crash → discard → fresh rerun.
- [ ] Prove ordinary branch/procedure placement and target-2.24 loop refusal.
- [ ] Record feasibility proofs 2–4 and their exact test bindings.
- [ ] Run E1 focused integration plus adjacent native-return, calls, assets,
      compiler-session, checkpoints, pure-replay, and at-least-once suites;
      obtain ordered reviews, commit, and postcommit controls.

## Task 9: Route, verify, and close E1

**Files:** exact roadmap/status/router/capability/readiness rows; this plan;
`artifacts/review/e1-run-ref-final-review.md`.

- [ ] Route 2.24 and `run-ref` as implemented-pending-final-gate while E2
      remains selected-pending E1 and E3 remains selected-pending E2/study.
- [ ] Run collect-only for every new module, all focused E1/adjacent selectors,
      deterministic CLI/executor smoke, `git diff --check`, and the broad
      16-worker non-security suite in tmux.
- [ ] Obtain `E1_FINAL_SPEC_APPROVED`, then distinct
      `E1_FINAL_QUALITY_APPROVED`, against exact candidate bytes/evidence.
- [ ] Commit the reviewed candidate, rerun focused/routing/readiness controls,
      and bind commit/tree/test totals in this plan and final review.
- [ ] Record exactly one exit: `PASS_E1`, `REVISE_E1`, or `STOP_E1`. Only
      `PASS_E1` makes selected E2 eligible for its separate reviewed component
      plan; it does not start E2 behavior before that plan gate.

## Final acceptance checklist

- [ ] Target 2.24 is normative, gated, and backward compatible.
- [ ] `run-ref` is a distinct durable effect with exact source/program/policy
      identity and no command/call/eval substitution.
- [ ] Mode 1 runs the exact self-contained compiled capsule without compiler
      or mutable controller-source reads.
- [ ] Mode 2 uses the ordinary full compiler and stable JSON diagnostics.
- [ ] Both modes accept every existing transportable input/result shape and
      enforce exact child contracts.
- [ ] Materialization, setup, delta, accounting, evidence, and declared
      artifacts are deterministic and digest-bound.
- [ ] Separate roots and single writers hold; incomplete attempts discard and
      rerun fresh; committed results validate and reuse.
- [ ] Effect-free generated candidates admit and non-admissible effects reject
      without security/isolation implementation.
- [ ] Feasibility proofs 2–4, focused/E2E/broad gates, ordered final reviews,
      and postcommit controls are fresh and bound.
- [ ] E2/E3/C1-C3 remain truthfully gated and no later surface is inferred.
