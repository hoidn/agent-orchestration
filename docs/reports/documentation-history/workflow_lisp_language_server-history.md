# Workflow Lisp Language Server: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_language_server.md](../../design/workflow_lisp_language_server.md).

## Original delivery metadata

- **Reviewers:** independent specification rereview
  `STAGE8_DESIGN_SPEC_APPROVED`, then independent quality rereview
  `STAGE8_DESIGN_QUALITY_APPROVED` (2026-07-25); L1 independent specification
  review `L1_DESIGN_SPEC_APPROVED`, then independent quality review
  `L1_DESIGN_QUALITY_APPROVED` (2026-07-26); L2 final specification review
  `L2_FINAL_SPEC_APPROVED`, then independent final quality review
  `L2_FINAL_QUALITY_APPROVED` (2026-07-27); L3 independent specification review
  `L3_DESIGN_SPEC_APPROVED`, then independent quality review
  `L3_DESIGN_QUALITY_APPROVED` (2026-07-28); L3 canonical-path refusal
  correction `L3_CANONICAL_PATH_DESIGN_SPEC_APPROVED`, then independent
  `L3_CANONICAL_PATH_DESIGN_QUALITY_APPROVED` (2026-07-28); L3 Task 1
  `L3_TASK1_SPEC_APPROVED`, then `L3_TASK1_QUALITY_APPROVED`; L3 Task 2 and
  its xdist-evidence correction each received restarted
  `L3_TASK2_SPEC_APPROVED`, then `L3_TASK2_QUALITY_APPROVED`; final closure
  `L3_FINAL_SPEC_APPROVED`, then `L3_FINAL_QUALITY_APPROVED` (2026-07-28);
  L4 independent specification review `L4_DESIGN_SPEC_APPROVED`, then
  independent quality review `L4_DESIGN_QUALITY_APPROVED`; L4 Task 1
  `L4_TASK1_SPEC_APPROVED`, then `L4_TASK1_QUALITY_APPROVED`; L4 Task 2
  `L4_TASK2_SPEC_APPROVED`, then `L4_TASK2_QUALITY_APPROVED`; L4 Task 3
  `L4_TASK3_SPEC_APPROVED`, then `L4_TASK3_QUALITY_APPROVED`. Task 4 closure
  diff `c41e2e756f1d0c6bc27bbd9a8b8bbbfc57c59fc121b0bd46dc548709c286b990`
  received `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED` before
  commit `1f64f153`, tree `7790ee0e`. That exact tree received
  `L4_FINAL_SPEC_APPROVED`; final quality returned `CHANGES_REQUIRED` solely
  for stale review-status metadata. The corrected routing/status diff
  `29e0bc01037058f0c29dac15c0d461798a5e47a836fe8b3e8336beb937410951`
  landed at `251d9d53674e863fddae4535ea4f7022914287cd`, tree
  `e2417d395cbcabe9adaffb136759ebff3d42b677`, then passed a 357-test focused
  control. External closure-record SHA-256
  `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804`
  records ordered `L4_FINAL_SPEC_APPROVED` then
  `L4_FINAL_QUALITY_APPROVED`; the prior rejection is superseded history
- **Created:** 2026-07-13
- **Last material update:** 2026-07-28
- **Review history:** earlier design and quality changes-required rounds,
  including the F2 source-root, payload-based read-only build, and optional
  authored-call-provenance corrections, are incorporated. The latest quality
  review additionally required a single-workspace-root v1 and exact-byte
  compiler read tracing, then identified the production-injected builtin
  stdlib root as the one required containment exception. The final correction
  preserves current `Path.read_text(encoding="utf-8")` parser semantics,
  including text I/O's implicit `newline=None` universal-newline translation,
  while retaining raw-byte digest/editor identity. Ordered final rereviews
  approved the exact amended design:
  `STAGE8_DESIGN_SPEC_APPROVED`, then
  `STAGE8_DESIGN_QUALITY_APPROVED`. The L3 immutable per-source-selection
  amendment then passed ordered `L3_DESIGN_SPEC_APPROVED` and
  `L3_DESIGN_QUALITY_APPROVED`. The implementation-discovered
  uncanonicalizable-JSON-key correction then passed ordered
  `L3_CANONICAL_PATH_DESIGN_SPEC_APPROVED` and
  `L3_CANONICAL_PATH_DESIGN_QUALITY_APPROVED`.

## Original delivery metadata

- **Implementation record:** Stage 8 (the final stage) is complete under
  `docs/plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md`.
  The 2026-07-13 roadmap amendments initially named it Stage 7 and renumbered
  it when provider live binding was inserted ahead of it. Generic client setup
  lives in `docs/workflow_lisp_language_server_setup.md`. The bounded L0
  reliability/actionability successor is also implemented under
  `docs/plans/2026-07-26-workflow-lisp-language-server-l0-implementation-plan.md`;
  L1 authored symbols and callable signatures are implemented under
  `docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md`
  through `f1eecf65`, `ec2328dd`, `d174faf2`, and `66163dc0` plus its reviewed
  repository-real stdio/status closure. L2 recovery-safe static completion is
  implemented through `70b83f32`, `b399c041`, `ee213a43`, and `10e3ccc3`
  under its reviewed five-task implementation plan, then closed by ordered
  `L2_FINAL_SPEC_APPROVED` and `L2_FINAL_QUALITY_APPROVED`. L5 authored
  reference navigation is implemented through `95e05c01`, `042c0bc3`,
  `870f7db2`, `7233138a`, and `041754e6` under
  `docs/plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md`.
  L3 per-source entry selection is implemented after compiler-session
  reentrancy closed under
  `docs/plans/2026-07-27-workflow-lisp-compiler-session-state-implementation-plan.md`;
  its reviewed three-task component plan is
  `docs/plans/2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md`.
  The implementation landed through Task 1 `fc1b01ee`, Task 2 `9e59929d`,
  and Task 2's xdist-evidence correction `8c704f3f`.
  L4 current-only diagnostic publication is implemented at `11629551` and
  transport-local serialized compile progress is implemented at `0d5f7009`
  under
  `docs/plans/2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md`.

Evaluated-entry availability is narrower than the legacy LSP surface. For
the demonstrated W3 sources, CLI and LSP select the same source graph and
builtin helper, but the LSP still terminates with
`evaluated_execution_unavailable` after graph
compilation. Selection/root/hash/read-trace parity does not establish a
successful evaluated snapshot, semantic navigation or terminal diagnostic
parity. Evaluated F2 remains **OPEN_NOT_WAIVED**; the existing F2 acceptance
contract and legacy checks remain unchanged. L2 may supply its existing frozen
static-form recovery response, never stale callables.

## Implementation Record And Handoff

The implementation completed the following independently tested phases:

1. **Diagnostics core** — translation layer (pure, unit-tested), compile
   shared read-only build-core extraction, exact-byte `SourceReadTrace`
   plumbing with one-read raw/decoded/parser views and legacy-newline
   compatibility, separate immutable configuration trace, single-root
   initialization/containment, request normalizer/parity capture, per-entry
   contribution generations, reverse index, serialized full-Stage-3 driver,
   stdio server skeleton, integration/zero-write tests, and exact CLI/import
   parity tests. F1-F3 choices are enforced and recorded. No language/runtime
   semantics change and no Stage-1 import.
2. **Navigation** — optional `authored_callee_span` metadata
   capture/preservation/absence,
   entry/source/config-current snapshot views, closed-matrix
   go-to-definition, document symbols, completion, mandatory pre-response
   digest checks, and dirty/pending/dependency-invalidated/
   configuration-stale/failed/stale null-result tests.
3. **Packaging and docs** — `lsp` extra, editor-setup documentation,
   capability matrix and routing updates, end-to-end check.
4. **L5 authored reference navigation** — collision-safe five-field definition
   rows; exact original-syntax/compiler-catalog joins for authored prompt heads
   and final direct-retained proc-ref names; common-preflight, visibility,
   collision-refusal, and null-matrix coverage; and a repository-real stdio
   check that resolves the review workflow prompt head while keeping its
   macro-consumed proc-refs and macro head null and its direct workflow call
   exact. No compiler/frontend or non-navigation production file changed.

Likely-touched modules: new files under `orchestrator/lsp/`;
`orchestrator/workflow_lisp/build.py`
(`build_frontend_bundle_in_memory`, `FrontendInMemoryBuildResult`,
`_select_and_reattach`, `_reattach_bundle_provenance`,
`_reattach_bundle_semantic_ir`, `_emit`, and recursive
`load_imported_workflow_bundle_manifest`);
`orchestrator/workflow/core_ast.py::build_core_workflow_ast`,
`orchestrator/workflow/lowering.py::build_loaded_workflow_bundle`, and
`orchestrator/workflow/semantic_ir.py::derive_workflow_semantic_ir` for the
authoritative optional `source_map_payload` parameter and legacy persisted-path
fallback; `orchestrator/workflow_lisp/reader.py` (`SourceReadTrace`,
`SourceReadRecord`, and `read_sexpr_file`),
`orchestrator/workflow_lisp/modules.py::resolve_module_graph`, and
`orchestrator/workflow_lisp/compiler.py::compile_stage3_entrypoint` plus its
Stage-3 source-loading helpers for explicit collector threading; any reachable
Stage-3 reread call sites in `orchestrator/workflow_lisp/lowering/core.py` and
`orchestrator/workflow_lisp/lowering/pure_projection.py`;
`orchestrator/workflow_lisp/expressions.py` plus the existing expression
construction, specialization, traversal, and copy paths, and
`orchestrator/workflow_lisp/wcc/defunctionalize.py` for
`authored_callee_span`; `pyproject.toml` (extras); and focused tests under
`tests/`. Compiler/typecheck/lowering/runtime language behavior is unchanged;
the reader/module/compiler delta is trace metadata and exact-byte plumbing
only.

Known tricky areas: UTF-16 coordinate conversion; clearing multi-file
diagnostics when one entry's target set shrinks while another still
contributes; generation-safe atomic replacement; canonical equality of
production-loaded bundles; recursive imported compilation without `_emit`;
zero-write proof; single-root containment without implicit source roots;
reverse-index cleanup; threading one collector through every Stage-3 reread;
rejecting an `A -> B -> A` digest mismatch; external/closed dependency changes
during a serialized compile; immutable configuration latching; mandatory
digest checks without watcher assistance; preserving exact authored
`authored_callee_span` while preserving `None` through WCC/generated/expanded
forms; conservative invalidation when closure ownership is unknown; raw-span
handling when paths are synthetic or unreadable; keeping stdout frame-only;
and keeping compile-worker serialization airtight under request storms.

The implementation followed that dependency order: shared in-memory build
extraction and exact value/zero-write parity; one-read hash/parse identity and
both `A -> B -> A` controls; single-root state; optional
`authored_callee_span`; then transport, navigation, packaging, and docs.

Still out of scope after implementation: all of P1–P5, grammar/extension
packaging, `didChange` compilation, hover, rename, formatting, semantic
tokens, Stage-1 fallback, two-phase publishing, and nominal completion
filtering. Non-default lint/lowering editor configuration, more than one
workspace root, root arbitration, and per-root caches are also out of scope
pending their own designs.
