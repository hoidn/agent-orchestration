# Workflow Lisp Language Server L0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for each behavior change. Each task
> receives an ordered specification-compliance review and then an
> implementation-quality review before commit.

**Goal:** Close the bounded L0 reliability/actionability defects: one-probe
save-driven reverse invalidation, intentional structured initialization
failures, visible compiler-owned notes/expansion roles, and a content-keyed
pure-projection export cache.

**Architecture:** Keep the LSP a read-only consumer of production compilation.
One new pure state transition chooses exactly one existing save/observe path
from one disk snapshot. Initialization translates only structured compiler
errors at the JSON-RPC boundary. Diagnostic presentation remains a view over
unchanged contributions. The untraced pure-projection helper caches exact
content, while traced compilation continues through its existing single-read
owner.

**Accepted design:** `docs/design/workflow_lisp_language_server.md` and
`docs/design/workflow_lisp_frontend_specification.md` at commit `cd7f55f5`;
SHA-256 values
`75eaf1a2d4c70b586b9cfaeb8b5b68f6931fc82feaa4aa7e25b8bcc3457cfb18`
and
`16215c456b71371dd9d948e5350c95173855b12605213f11b69a878c945279a4`.

**Characterization:** the cache at
`orchestrator/workflow_lisp/lowering/pure_projection.py:485` is path-keyed. A
same-process probe returned the old export after same-path content replacement
and returned the new export only after clearing the `lru_cache`. The minimal
content-key correction is therefore required by L0.

**Execution status:** accepted for execution after ordered independent plan
review: `L0_IMPLEMENTATION_PLAN_SPEC_APPROVED`,
`L0_IMPLEMENTATION_PLAN_QUALITY_APPROVED`, and post-quality
`L0_IMPLEMENTATION_PLAN_SPEC_REAFFIRMED`.

**Deliberate cost:** exact-content cache keys require reading content before
lookup, so they cannot avoid the filesystem read. L0 prevents stale reuse; it
does not attempt general compile caching, overlays, or incrementality.

## Disjoint Concurrent Ownership

L0 production ownership is limited to:

- `orchestrator/lsp/state.py`
- `orchestrator/lsp/server.py`
- `orchestrator/lsp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering/pure_projection.py`

and the named LSP/cache tests below. Active Q1 prompt-core Tasks 1–5 own none of
those paths. Shared specification/routing documents are updated only after each
implementation stage closes and must be serialized with Q1's documentation
task. Do not edit Q1 prompt files, provider runtime files, security/provider
isolation work, or ambient dirty paths.

No worktree is allowed. Stage exact task paths only; never use `git add .` or
`git add -A`.

## Task 1: Content-Keyed Pure-Projection Export Cache

**Files:**

- Modify:
  `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Create:
  `tests/test_workflow_lisp_pure_projection_cache.py`

- [ ] Write RED tests for same canonical path with changed bytes, unchanged
  bytes reuse, structured parse failure, and traced-read bypass.
- [ ] Replace the path-only cache owner with a cached function keyed by
  canonical path plus SHA-256 of exact bytes and taking those exact bytes as
  its parse input. Do not reopen the path inside the cached function.
- [ ] Preserve the existing `SourceReadTrace` route byte-for-byte and bypass
  the untraced cache whenever a trace is supplied.
- [ ] Run:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_pure_projection_cache.py
  pytest -q tests/test_workflow_lisp_pure_projection_cache.py \
    tests/test_workflow_lisp_pure_projection_runtime.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 2: One-Probe Save And Reverse Invalidation

**Files:**

- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_state.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`

- [ ] Write RED state tests for:
  changed save, unchanged save, equal missing/unreadable sentinels, transitions
  to/from/between sentinels, trustworthy importers, dirty/unavailable
  dependencies, unknown closures, diagnostic targets, pending cancellation,
  and exact generation/scheduling effects.
- [ ] Add one pure `save_observed_entry` transition. Compare the supplied
  snapshot revision with the retained entry revision:
  equal (including equal sentinels) delegates only to `save_entry`; unequal
  delegates only to `observe_file_revision`.
- [ ] Make `save_document` call `probe_disk_source` exactly once and pass that
  snapshot to the new transition. It must not call `observe_disk_path`.
- [ ] Add stdio/integration tests proving one probe and no double generation.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 3: Closed Structured Initialization Failures

**Files:**

- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`

- [ ] Write RED tests for missing and malformed initialization manifests,
  multiple ordered frontend diagnostics, canonical and retained-raw paths, no
  `publishDiagnostics`, and an unstructured exception negative control.
- [ ] Catch only `LispFrontendCompileError` raised while
  `initialize_compile_driver` loads production configuration.
- [ ] Raise `JsonRpcInvalidParams` with exact message
  `Workflow Lisp initialization failed (<N> compiler diagnostics); see data`
  and closed ordered
  `data={"diagnostics":[{"code":...,"path":...},...]}`.
- [ ] Do not reclassify `OSError`, `RuntimeError`, `UnicodeDecodeError`,
  permission failures, or generic exceptions.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_compile_driver.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 4: Diagnostic Notes And Expansion Provenance View

**Files:**

- Modify: `orchestrator/lsp/diagnostics.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`
- Modify: `tests/test_workflow_lisp_lsp_cli_parity.py`

- [ ] Write RED structural tests for macro/helper frame role,
  call/definition role, name, nullable expansion ID, and compiler note order.
- [ ] Store each related-information row with exactly
  `frame_role`, `location_role`, `name`, `expansion_id`, and `location`.
  `frame_role` is `macro|helper`, `location_role` is `call|definition`, and
  `expansion_id` is string-or-null. Render the label as
  `<frame_role> <location_role>: <name>` followed by
  ` [<expansion_id>]` only when the ID is non-null.
- [ ] Preserve raw `DiagnosticContribution.message`, parity identity,
  aggregation key, representative selection, and structured data.
- [ ] Build the transported LSP message from the raw message plus ordered notes
  and the related-information labels from the four structured fields. Assert
  ordering/sentinel containment, never complete production prose.
- [ ] Prove diagnostic aggregation and CLI parity identity remain unchanged.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_diagnostics.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_cli_parity.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 5: Watcher-Disabled Real Stdio Importer Gate And Closure

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-language-server-l0-implementation-plan.md`
- Modify exact L0-owned routing/status hunks only after Q1 releases:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`,
  `docs/design/workflow_lisp_language_server.md`,
  `docs/design/workflow_lisp_frontend_specification.md`,
  `docs/workflow_lisp_language_server_setup.md`,
  `docs/capability_status_matrix.md`,
  `docs/design/README.md`, and `docs/index.md`.

- [ ] Add one real stdio fixture with watcher registration disabled: open a
  clean importer, save changed disk-equal content for its open helper without
  `workspace/didChangeWatchedFiles`, and observe the importer generation's
  compiler-owned result.
- [ ] Run focused L0:

  ```bash
  pytest -q tests/test_workflow_lisp_pure_projection_cache.py \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_diagnostics.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_e2e.py
  ```

- [ ] In tmux, run:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py
  ```

  Classify unrelated failures; do not repair them under L0.
- [ ] Obtain final ordered spec then quality review of the exact committed Task
  1–4 range plus the Task 5 E2E/closure diff.
- [ ] Commit the E2E and serialized routing/docs closure. Record exact commits,
  focused/broad outcomes, and review tokens in a final plan-only factual update.

## Completion Contract

L0 is complete only when:

1. same-path changed content cannot reuse stale export information, unchanged
   content can reuse it, and traced compiler reads bypass the cache;
2. every save performs one disk probe and exactly one save/observe transition;
3. changed imported sources invalidate/schedule trustworthy importers without a
   watcher and unchanged saves retain one local generation;
4. missing/malformed structured initialization failures return closed `-32602`
   data while unstructured failures do not;
5. visible notes and expansion labels retain compiler order/roles without
   changing diagnostic identity or aggregation;
6. the real watcher-disabled stdio importer E2E passes;
7. focused and broad non-security results are freshly classified;
8. each task and final range receive ordered spec then quality approval; and
9. shared docs are serialized after Q1 ownership and route L0 to complete/L1
   without changing Q1 status.
