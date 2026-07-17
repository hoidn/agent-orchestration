# Design Delta Drain-Builder Checkpoint-Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` while executing this plan. This is the
> bounded Task 6 fail-closed closeout package; do not modify production source,
> runtime mirrors, YAML, compiler/runtime code, checkpoint baselines, or run
> state, and do not commit this package.

**Status:** Complete by fail-closed checkpoint retention. Task 6 Steps 1–5 are
complete without source, mirror, history, or run mutation; Task 7 Step 1 is
current.

**Goal:** Resolve the one internal drain-builder candidate from exact compiler
evidence and retain it when the complete inline hypothetical changes its
caller-owned checkpoint identity.

**Architecture:** First lock the one inventory row, private workflow shape,
single call from the exported public drain, and public workflow binding. Then
compile retained bytes and a minimal compiler-complete hypothetical through a
read/write-safe exact-path override: convert only the private builder to a pure
inline procedure, add the caller's hidden `RunCtx` parameter required for the
ordinary positional procedure call, and compare compiler/runtime-contract
projections without executing either route. Retain the row if the old
caller-owned call checkpoint disappears or any other strict identity surface
changes.

**Tech Stack:** Workflow Lisp compiler and build artifacts, pytest, JSON
inventory, Markdown routing surfaces.

**Approach tradeoff:** The builder remains a private workflow boundary. This
keeps its current checkpoint namespace but leaves function-shaped internal
glue in the workflow layer; future conversion requires an identity-preserving
lowering or a general atomic upgrader.

---

## Exact boundary

`internal-call:workflows/library/lisp_frontend_design_delta/drain.orc:build-drain-runtime-owned:1`

The callee remains private and `lisp_frontend_design_delta/drain::drain`
remains the exported public workflow. No public-entry or history row is added.

The containing workflow is already promoted/live: its inventory public-entry
record is `live`, classified `public-boundary`, and cites the promoted
route-readiness identity. The route-readiness registry marks the same source
`promotion_eligible`, `wcc_default`, `preferred_current_guidance`, and
`parity_constrained`. Those existing public-entry and routing contracts make
strict checkpoint/state compatibility mandatory for this internal change.
Future conversion therefore requires identity-preserving lowering or a general
atomic upgrader that preserves supported checkpoint and state consumers.

## Task 1: Lock retained structure and inventory classification

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add a RED test requiring the exact row to be `effect-adapter` and to
  reference this decision, the route-readiness registry, and structural,
  public-boundary, and hypothetical selectors.
- [x] Require one private `defworkflow` builder, no same-named `defproc`, one
  workflow call from `drain`, and exported `drain` as a public workflow.
- [x] Confirm RED is caused by the former `procedure-candidate` row.

## Task 2: Audit the complete exact-path hypothetical

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add an exact-count transform that converts the builder to pure
  `defproc :lowering inline`, adds hidden `(run RunCtx)` to the public workflow
  runtime signature, and replaces the workflow call with positional
  `(build-drain-runtime-owned run)`.
- [x] Compile retained and hypothetical bytes through the exact production
  path using a read/write-safe same-path override; lock both full source
  digests, compilation results, and advisories.
- [x] Compare checkpoint identity/name/owner/program-point/node/storage,
  bundle/node/call/effect/state projections, public authored
  I/O/artifact/finalization/publication shapes, and hidden runtime
  state/artifact defaults.
- [x] Record only independently reproducible counts. Stop short of runtime or
  resume parity because this audit does not execute either source.

## Task 3: Reconcile inventory and routing

**Files:**

- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Modify: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Reclassify only the exact active row to `effect-adapter`, with the
  checkpoint identity delta and exact selectors in its evidence.
- [x] Reconcile counts to zero procedure candidates, 32 effect adapters, and
  63 legacy-retire rows while preserving 13 public entries, 108 active
  records, one history row, and `source_commit`.
- [x] Add one concise inventory link and preserve historical counts in
  completed decision records.
- [x] Mark Task 6 Steps 1-5 complete on retention evidence without source or
  history commits, and make Task 7 Step 1 current without reordering later
  stages.
- [x] Update canonical index, execution-sequence, capability-matrix, and
  routing tests for the new current selector.

## Task 4: Verify the bounded closeout

**Files:**

- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Parse the JSON inventory and run focused retention, checkpoint,
  public-wrapper, and production compile selectors.
- [x] Run the complete routing module and collect both modified test modules.
- [x] Inspect the scoped diff and verify the production owner plus four
  relevant runtime mirrors are clean against `HEAD`.
- [x] Record that production/mirror/YAML/compiler/run state, inventory history,
  and `source_commit` remain unchanged and no runtime/resume parity is claimed.

## Governing result

Retained source digest is
`sha256:e321e84e80342ff8757ab8f166530af5fdefd23807eab55f16c1a22c095da5fd`;
the complete hypothetical digest is
`sha256:189666db8d4638a116a700079d6f1129b008ef8bdff91060201bc7e10b8ca9be`.
Both compile without diagnostics or retained advisories. The hypothetical
removes caller-owned checkpoint `ckpt:4dc584b1d0c80e14d36a3d5e`
(`pp:970dd723219942ff6192649d`) and adds none, reducing lexical checkpoints
from 11 to 10. All ten common checkpoint IDs, names, owners, program points,
nodes, storage identities, and non-restore details remain stable, while all
ten restore projections change.

The builder bundle disappears (30 to 29 bundles), its exact call node
disappears (111 to 110 executable/runtime nodes), and its call boundary,
workflow-call effect, and six state-layout records disappear. Seventy-one
common compatibility-index/state-projection entries change after the removed
node. Public authored input/output, artifact, finalization, and publication
shapes remain equal, but hidden `run__state-root` and `run__artifact-root`
defaults disappear. These compile projections fail strict identity
compatibility; they are not runtime or resume parity evidence.

## Claim boundary

Production and mirrored `.orc` bytes, YAML, compiler/runtime code, checkpoint
baselines, run state, inventory history, and `source_commit` remain unchanged.
The sole active row remains `effect-adapter`; no source/history commit,
identity remap, upgrader, cross-source resume, promotion, or YAML retirement
is claimed.
