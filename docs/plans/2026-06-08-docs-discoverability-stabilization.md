# Docs Discoverability Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative documentation-discoverability layer so readers can identify current authority, feature status, copy-safe examples, and design-doc status without rewriting the existing documentation hub.

**Architecture:** Keep `docs/index.md` as the primary documentation hub and edit it only with a small additive triage block. Add three focused routing/status docs (`docs/capability_status_matrix.md`, `docs/design/README.md`, `docs/documentation_conventions.md`), one short conceptual front door (`docs/architecture_overview.md`), demote stale competing entrypoints, and fix copy-unsafe commands in `workflows/README.md` and `tests/README.md`. Do not move large sections out of existing guides in this pass.

**Tech Stack:** Markdown documentation, repository-local `rg` checks, `git diff --check`, and targeted markdown/link sanity by inspection.

---

## Scope

This is a docs-only stabilization pass. It should not change runtime behavior, Workflow Lisp implementation, workflow YAML semantics, prompts, tests, or specs.

This pass is recommended before broad feature-surface expansion and large Workflow Lisp authoring-surface changes because it reduces routing/status ambiguity. It is not itself an executable workflow gate unless a separate roadmap, backlog, manifest, or selector update makes it one. It should not block critical bugfixes, workflow recovery fixes, verification fixes, or narrow operational repairs.

## Source Authorities

Read these before implementation:

- `docs/index.md`: primary documentation hub and routing layer.
- `AGENTS.md`: root operational instructions for agents.
- `MIND_MAP.md`: existing secondary map that currently claims primary agent authority.
- `README.md`: top-level onboarding and command examples.
- `docs/orchestration_start_here.md`: existing conceptual entry point.
- `docs/workflow_drafting_guide.md`: YAML workflow authoring guidance.
- `docs/lisp_workflow_drafting_guide.md`: Workflow Lisp authoring guidance and availability labels.
- `docs/design/workflow_language_design_principles.md`: semantic authority principles.
- `docs/design/workflow_lisp_frontend_specification.md`: current Workflow Lisp base contract.
- `docs/design/workflow_lisp_unified_frontend_design.md`: future/deferred Workflow Lisp surfaces.
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`: implemented companion/history for review/revise stdlib migration.
- `docs/design/workflow_lisp_runtime_closures_boundary.md`: deferred runtime closure boundary.
- `workflows/README.md`: workflow catalog and copyable run commands.
- `tests/README.md`: test and smoke-check guidance.
- `specs/index.md`, `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, `specs/state.md`: normative contract references.

## File Map

- Create: `docs/capability_status_matrix.md`
  - Central status matrix for public authoring/runtime surfaces that readers might copy or rely on.
- Create: `docs/design/README.md`
  - Curated index of design docs grouped by current contract, migration guidance, frontend direction, runtime authority, future/deferred work, and historical notes.
- Create: `docs/architecture_overview.md`
  - One-page conceptual front door that links to `docs/orchestration_start_here.md` for the fuller explanation.
- Create: `docs/documentation_conventions.md`
  - Checklist for future docs so new pages state status, authority, evidence, copyability, and trust boundaries.
- Modify: `workflows/README.md`
  - Replace maintainer-local absolute `PYTHONPATH` commands with copy-safe repo-root commands and add a compact "which example should I copy?" section.
- Modify: `tests/README.md`
  - Replace maintainer-local absolute `PYTHONPATH` smoke-check commands with copy-safe repo-root commands.
- Modify: `MIND_MAP.md`
  - Demote from primary knowledge index to secondary, non-normative orientation map with stale-area warning.
- Modify: `AGENTS.md`
  - Add a small entrypoint clarification without rewriting the operational rules.
- Modify: `docs/index.md`
  - Add a small additive `Fast Triage` block only. Do not restructure the hub.
- Optionally modify: `README.md`
  - Add at most one short "New to the repo?" pointer block if the index and architecture overview need a top-level link.

## Non-Goals

- Do not create `docs/authority_glossary.md` in this pass.
- Do not create `docs/debugging_cookbook.md` in this pass.
- Do not create `docs/migration_playbook_yaml_to_orc.md` in this pass.
- Do not create `docs/command_adapter_inventory.md` in this pass.
- Do not create `docs/examples_index.md` in this pass.
- Do not create `docs/agent_entrypoint.md` in this pass.
- Do not create `docs/change_type_router.md` in this pass.
- Do not create `docs/agent_checklists.md` in this pass.
- Do not create nested `AGENTS.md` files in this pass.
- Do not split `docs/index.md` into router/catalog files in this pass.
- Do not rewrite root `AGENTS.md` as a full docs router.
- Do not add banners to every file under `docs/design/`.
- Do not rewrite `docs/index.md` into a new structure.
- Do not change normative specs except to fix an obviously broken link discovered during verification.

## Implementation Tasks

### Task 1: Create the Capability Status Matrix

**Files:**
- Create: `docs/capability_status_matrix.md`

- [ ] **Step 1: Re-read current authoring/status sections**

  Run:

  ```bash
  sed -n '1,180p' docs/lisp_workflow_drafting_guide.md
  sed -n '1,140p' docs/workflow_drafting_guide.md
  sed -n '1,120p' workflows/README.md
  ```

  Expected: current availability labels, YAML/.orc parity guidance, and workflow catalog status are visible.

- [ ] **Step 2: Create the matrix file**

  Add `docs/capability_status_matrix.md` with this structure:

  ```markdown
  # Capability Status Matrix

  Status: informative routing/status index
  Normative authority: `specs/` for runtime/DSL behavior; linked design docs for Workflow Lisp/frontend contracts
  Scope: public authoring/runtime surfaces that maintainers may copy, invoke, or depend on

  This matrix is a discoverability layer. If it conflicts with a normative spec, the spec wins and this matrix should be fixed.

  Status labels:

  - `Implemented`: available in current checkout with runtime/test/spec evidence.
  - `Partial`: available for some routes, but incomplete or bounded.
  - `Library`: available as a library/frontend abstraction rather than a raw DSL primitive.
  - `Designed`: design exists, implementation is not complete enough for normal use.
  - `Future`: intentionally deferred.
  - `Legacy`: retained for compatibility or historical examples, not preferred for new authoring.

  | Surface / feature | Status | Normal for new authoring? | Authority lane | Evidence | Copyable example | Notes |
  | --- | --- | --- | --- | --- | --- | --- |
  | YAML DSL v2.x | Implemented | Yes, when exact runtime behavior or unsupported `.orc` forms are needed | `specs/dsl.md` | workflow dry-runs and runtime tests | `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | YAML remains the exact runtime source where no promoted `.orc` parity exists. |
  ```

- [ ] **Step 3: Add required rows**

  Include rows for at least:

  - YAML DSL v2.x
  - Workflow Lisp `.orc`
  - `provider-result`
  - `command-result`
  - `match`
  - `loop/recur`
  - `review-revise-loop`
  - `resource-transition`
  - `ProcRef`
  - `bind-proc`
  - `let-proc`
  - runtime closures
  - Semantic IR
  - Executable IR
  - debug YAML renderer
  - source maps
  - command adapters
  - managed provider jobs
  - provider sessions
  - `output_bundle`
  - `variant_output`
  - `select_variant_output`
  - `publishes`
  - `consumes`
  - `depends_on`
  - `materialize_artifacts`
  - `pre_snapshot`
  - `requires_variant`

  Keep notes short. Use the status labels defined in the matrix file consistently.

- [ ] **Step 4: Keep evidence concrete**

  For implemented rows, evidence should be a spec, design doc, fixture, example workflow, test module, or dry-run/parity record. Do not write vague evidence such as "supported by docs".

- [ ] **Step 5: Verify status wording**

  Run:

  ```bash
  rg "Future|Designed|Partial|Implemented|Legacy|Library" docs/capability_status_matrix.md
  rg "runtime closures|let-proc|review-revise-loop|Workflow Lisp|YAML DSL" docs/capability_status_matrix.md
  ```

  Expected: each major public surface appears once with a status label.

### Task 2: Create the Design Docs Curator Index

**Files:**
- Create: `docs/design/README.md`

- [ ] **Step 1: Inventory current design docs**

  Run:

  ```bash
  find docs/design -maxdepth 1 -type f -name '*.md' | sort
  ```

  Expected: all design docs are listed.

- [ ] **Step 2: Create `docs/design/README.md`**

  Add this structure:

  ```markdown
  # Design Documentation Index

  Status: informative design-doc curator
  Normative authority: `specs/` for runtime behavior; current component docs for accepted frontend contracts

  This page helps readers distinguish current contracts, migration guidance, frontend direction, future/deferred work, and historical notes. It is a routing page, not a replacement for the linked docs.

  ## Current Component Contracts

  | Doc | Applies to | Current checkout? | Normal authoring guidance? | Notes |
  | --- | --- | ---: | ---: | --- |
  ```

- [ ] **Step 3: Group high-traffic docs first**

  Add rows for these docs at minimum:

  - `workflow_language_design_principles.md`
  - `workflow_command_adapter_contract.md`
  - `workflow_lisp_frontend_specification.md`
  - `workflow_lisp_semantic_workflow_ir.md`
  - `workflow_lisp_executable_ir.md`
  - `workflow_lisp_macro_surface_contract.md`
  - `workflow_lisp_stdlib_lowering.md`
  - `workflow_lisp_state_layout.md`
  - `workflow_lisp_key_migration_parity_architecture.md`
  - `workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `workflow_lisp_unified_frontend_design.md`
  - `workflow_lisp_runtime_closures_boundary.md`
  - `workflow_lisp_refactor_architecture.md`

- [ ] **Step 4: Group remaining docs without over-claiming**

  Add remaining docs under broad categories:

  - Current component contracts
  - Migration guidance
  - Frontend design direction
  - Runtime/executable authority
  - Future/deferred work
  - Historical notes

  If implementation status is unclear, write `Partial/unknown from this index; read the doc and linked evidence`.

- [ ] **Step 5: Verify no design doc is missing from the index**

  Run:

  ```bash
  python - <<'PY'
  from pathlib import Path
  index = Path("docs/design/README.md").read_text()
  missing = []
  for path in sorted(Path("docs/design").glob("*.md")):
      if path.name == "README.md":
          continue
      if path.name not in index:
          missing.append(str(path))
  if missing:
      raise SystemExit("Missing design docs:\n" + "\n".join(missing))
  print("All design docs are referenced.")
  PY
  ```

  Expected: `All design docs are referenced.`

### Task 3: Demote Stale Competing Entrypoints

**Files:**
- Modify: `MIND_MAP.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Inspect current entrypoint claims**

  Run:

  ```bash
  sed -n '1,80p' AGENTS.md
  sed -n '1,60p' MIND_MAP.md
  ```

  Expected before edit: `AGENTS.md` tells agents to read `docs/index.md`; `MIND_MAP.md` claims it is the primary knowledge index.

- [ ] **Step 2: Demote `MIND_MAP.md` with a top banner**

  Replace the current opening agent claim with a banner like:

  ```markdown
  > **Status:** secondary orientation map
  > **Authority:** non-normative
  > **Last audited:** 2026-06-08
  > **Known stale areas:** version numbers, LOC counts, implementation topology, and current feature status
  >
  > This file is not the agent entry point. Start with root `AGENTS.md`, then `docs/index.md`.
  > Use this map only as a secondary concept locator. If it conflicts with `specs/`,
  > current docs, tests, or implementation evidence, it loses.
  ```

  Preserve the existing node content below the banner in this pass. Do not try to refresh the whole map.

- [ ] **Step 3: Add a narrow documentation-routing clarification to `AGENTS.md`**

  Add a short section near the top, after `Read docs/index.md before making changes.`:

  ```markdown
  ## Documentation Routing

  - Start with this file for repo operating rules.
  - Use `docs/index.md` to choose governing docs/specs before making changes.
  - If a nested `AGENTS.md` exists for the path you are editing, follow it too.
  - For feature-status questions, use `docs/index.md` to find the current status/discoverability docs.
  ```

  Keep the `AGENTS.md` edit to one short additive `Documentation Routing` section near the top. Preserve the existing rule list and verification expectations byte-for-byte except where the new section is inserted.

- [ ] **Step 4: Verify no primary mind-map claim remains**

  Run:

  ```bash
  rg "primary knowledge index|mind map wraps every task|Always reference node IDs" AGENTS.md MIND_MAP.md
  ```

  Expected: no matches, unless the match is in a clearly demoted/historical sentence that cannot be mistaken for current instruction.

- [ ] **Step 5: Verify AGENTS diff is small**

  Run:

  ```bash
  git diff -- AGENTS.md MIND_MAP.md
  ```

  Expected: `AGENTS.md` has only the new entrypoint section; `MIND_MAP.md` has only the demotion/freshness banner change near the top.

### Task 4: Fix Copy-Unsafe Workflow And Test Commands

**Files:**
- Modify: `workflows/README.md`
- Modify: `tests/README.md`

- [ ] **Step 1: Locate maintainer-local paths**

  Run:

  ```bash
  rg "PYTHONPATH=/home/ollie/Documents/agent-orchestration|/home/ollie/Documents/agent-orchestration" workflows/README.md tests/README.md
  ```

  Expected before edit: maintainer-local `PYTHONPATH` examples in `workflows/README.md`; `tests/README.md` may also contain a stale smoke-check example.

- [ ] **Step 2: Replace the top command block**

  Replace the initial run guidance with:

  ````markdown
  Run workflows from the repo root after `pip install -e ".[dev]"`:

  ```bash
  python -m orchestrator run workflows/examples/<workflow>.yaml --dry-run
  ```

  If you are running from a checkout without an editable install, use:

  ```bash
  PYTHONPATH="$(pwd)" python -m orchestrator run workflows/examples/<workflow>.yaml --dry-run
  ```
  ````

- [ ] **Step 3: Replace input-required examples**

  Use `python -m orchestrator ...` without absolute `PYTHONPATH` for the input examples. Keep the commands otherwise unchanged.

- [ ] **Step 4: Add a compact copy-first section**

  Add this near the workflow catalog status or before the main catalog:

  ```markdown
  ## Which Example Should I Copy?

  | Goal | Copy first | Avoid |
  | --- | --- | --- |
  | Current call-based dry run | `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | Legacy monoliths and migration-only wrappers |
  | Small `.orc` authoring example | `workflows/examples/kiss_backlog_item.orc` | Production queue drains |
  | Managed provider jobs | `workflows/examples/managed_provider_jobs_demo.yaml` | Hand-authored guard/recovery scripts |
  | Adjudicated provider | `workflows/examples/adjudicated_provider_demo.yaml` | Older provider examples |
  ```

- [ ] **Step 5: Replace stale command in `tests/README.md`**

  If `tests/README.md` contains maintainer-local `PYTHONPATH`, replace it with a repo-root command. For example:

  ```bash
  python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
  ```

  If the command needs source-tree imports without editable install, use:

  ```bash
  PYTHONPATH="$(pwd)" python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
  ```

- [ ] **Step 6: Verify copy-safety**

  Run:

  ```bash
  rg "PYTHONPATH=/home/ollie/Documents/agent-orchestration" workflows/README.md tests/README.md
  ```

  Expected: no matches.

### Task 5: Add a Short Architecture Overview

**Files:**
- Create: `docs/architecture_overview.md`

- [ ] **Step 1: Create a one-page front door**

  Add `docs/architecture_overview.md` with this structure:

  ````markdown
  # Architecture Overview

  Status: informative front door
  Normative authority: `specs/`
  Fuller model: `docs/orchestration_start_here.md`

  `agent-orchestration` is a compiler/runtime system for making unreliable agent work cross deterministic, typed, durable artifact boundaries.

  ## One-Screen Model

  ```text
  authored surface
    YAML or .orc
          ↓
  typed contracts
          ↓
  Core / Semantic IR / Executable IR
          ↓
  runtime state + artifacts
          ↓
  reports, logs, dashboards, debug YAML as views
  ```
  ````

- [ ] **Step 2: State the authority split**

  Include this exact conceptual content, adjusted for markdown style:

  ```text
  Structured state, artifact values, contracts, snapshots, Semantic IR, and Executable IR are authority.
  Reports, stdout, stderr, pointer files, rendered plans, summaries, dashboards, debug YAML, and source maps are views unless a specific contract promotes them.
  Prompt text is not the workflow.
  Reports are not the workflow.
  Pointer files are not the workflow unless a specific contract makes the pointer path the artifact value.
  The typed contract/state/artifact graph is the workflow.
  ```

- [ ] **Step 3: Answer the five reader questions**

  Add short sections answering:

  - What is authoritative?
  - What is a view?
  - Why files?
  - Why types?
  - Why Workflow Lisp?

  Keep the whole file concise. If it grows beyond about 120 lines, move detail back to links.

- [ ] **Step 4: Link, do not duplicate**

  Link to:

  - `docs/orchestration_start_here.md`
  - `docs/workflow_drafting_guide.md`
  - `docs/lisp_workflow_drafting_guide.md`
  - `docs/capability_status_matrix.md`
  - `specs/index.md`

### Task 6: Add Documentation Conventions

**Files:**
- Create: `docs/documentation_conventions.md`

- [ ] **Step 1: Create the conventions file**

  Add:

  ```markdown
  # Documentation Conventions

  Status: informative repository documentation policy
  Applies to: new and substantially revised docs

  Every new or substantially revised documentation page should answer these questions:

  - Is this normative or informative?
  - Is this current behavior, future design, migration guidance, legacy, or historical?
  - Which spec, design doc, workflow, fixture, or run artifact is authoritative?
  - What runnable example, fixture, test, or command demonstrates the claim?
  - What should readers not copy from this page?
  - Which terms should link to `docs/index.md`, `docs/capability_status_matrix.md`, or a governing spec?
  ```

- [ ] **Step 2: Add status label guidance**

  Define:

  - `Current contract`
  - `Implemented`
  - `Partial`
  - `Library`
  - `Designed`
  - `Future`
  - `Legacy`
  - `Historical`

  Make clear that `specs/` own normative runtime/DSL behavior, while indexes and matrices are discoverability authorities. Reuse the status labels from `docs/capability_status_matrix.md`; do not introduce a second incompatible label set.

- [ ] **Step 3: Add copy-safety guidance**

  State that runnable commands must say whether they assume:

  - repo root after editable install,
  - `PYTHONPATH="$(pwd)"`,
  - installed CLI,
  - external provider credentials,
  - downstream workspace.

### Task 7: Add Conservative Triage Links to `docs/index.md`

**Files:**
- Modify: `docs/index.md`

- [ ] **Step 1: Inspect current top of index**

  Run:

  ```bash
  sed -n '1,80p' docs/index.md
  ```

  Expected: title, short normative/informative statement, then Clarifications.

- [ ] **Step 2: Add only a small `Fast Triage` section**

  Add this section after the opening normative/informative note and before `## Clarifications`:

  ```markdown
  ## Fast Triage

  - New to the repo: [Architecture Overview](architecture_overview.md)
  - Checking whether a feature is implemented: [Capability Status Matrix](capability_status_matrix.md)
  - Reading design docs: [Design Documentation Index](design/README.md)
  - Writing or revising docs: [Documentation Conventions](documentation_conventions.md)
  - Authoring Workflow Lisp: [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md)
  - Authoring YAML: [Workflow Drafting Guide](workflow_drafting_guide.md)
  - Debugging runtime behavior: [Runtime Execution Lifecycle](runtime_execution_lifecycle.md)
  - Checking normative behavior: [Master Spec](../specs/index.md)
  ```

  Do not move, shorten, or reorganize the existing clarification table or reading paths in this task.

- [ ] **Step 3: Verify index remains conservative**

  Run:

  ```bash
  git diff -- docs/index.md
  ```

  Expected: only the new `Fast Triage` section and no large structural rewrite.

### Task 8: Optionally Add Top-Level README Pointers

**Files:**
- Optionally modify: `README.md`

- [ ] **Step 1: Decide if README needs a small pointer block**

  If `README.md` already routes adequately through `docs/index.md`, skip this task. If adding links improves first-run navigation, add at most this small block under `## Start Here`:

  ```markdown
  AI coding agents should start with `AGENTS.md`; this README is human-facing quickstart material.

  New to the repo?

  1. Read [Architecture Overview](docs/architecture_overview.md).
  2. Use [Capability Status Matrix](docs/capability_status_matrix.md) before relying on a Workflow Lisp feature or design doc.
  3. Use [Workflow Index](workflows/README.md) for runnable examples.
  ```

- [ ] **Step 2: Verify README change is minimal**

  Run:

  ```bash
  git diff -- README.md
  ```

  Expected: either no diff, or one small pointer block only.

### Task 9: Final Verification

**Files:**
- Verify all touched docs.

- [ ] **Step 1: Run stale absolute path check on primary docs**

  Run:

  ```bash
  rg "PYTHONPATH=/home/ollie/Documents/agent-orchestration" AGENTS.md MIND_MAP.md README.md docs/*.md docs/design/README.md workflows/README.md tests/README.md
  ```

  Expected: no matches in primary docs touched by this pass.

- [ ] **Step 2: Run required-link checks**

  Run:

  ```bash
  rg "capability_status_matrix.md|architecture_overview.md|documentation_conventions.md|design/README.md" AGENTS.md docs/index.md README.md docs/*.md
  rg "secondary orientation map|not the agent entry point|docs/index.md" MIND_MAP.md AGENTS.md
  ```

  Also run:

  ```bash
  python - <<'PY'
  from pathlib import Path
  index = Path("docs/index.md").read_text()
  required = [
      "architecture_overview.md",
      "capability_status_matrix.md",
      "design/README.md",
      "documentation_conventions.md",
  ]
  missing = [target for target in required if target not in index]
  if missing:
      raise SystemExit("docs/index.md missing links:\n" + "\n".join(missing))
  print("Required docs/index.md links are present.")
  PY
  ```

  Expected: the new docs are discoverable from `docs/index.md`; `AGENTS.md` points to `docs/index.md`; README links are present only if Task 8 was not skipped; `MIND_MAP.md` is visibly demoted.

- [ ] **Step 3: Run markdown whitespace check**

  Run:

  ```bash
  git diff --check
  ```

  Expected: no whitespace errors.

- [ ] **Step 4: Review changed files**

  Run:

  ```bash
  git diff -- AGENTS.md MIND_MAP.md docs/capability_status_matrix.md docs/design/README.md docs/architecture_overview.md docs/documentation_conventions.md workflows/README.md tests/README.md docs/index.md README.md
  ```

  Expected:

  - New docs are concise routing/status docs.
  - `AGENTS.md` is only clarified, not rewritten.
  - `MIND_MAP.md` no longer claims primary authority.
  - `docs/index.md` has only a small triage addition.
  - `workflows/README.md` and `tests/README.md` commands are copy-safe.
  - No normative spec behavior is changed.

- [ ] **Step 5: Commit**

  Stage only the docs touched by this pass:

  ```bash
  git add \
    AGENTS.md \
    MIND_MAP.md \
    docs/capability_status_matrix.md \
    docs/design/README.md \
    docs/architecture_overview.md \
    docs/documentation_conventions.md \
    workflows/README.md \
    tests/README.md \
    docs/index.md
  ```

  If Task 8 changed README:

  ```bash
  git add README.md
  ```

  Commit:

  ```bash
  git commit -m "docs: stabilize discovery and feature status"
  ```

## Review Notes

The implementation should preserve these intentional boundaries:

- `docs/index.md` remains the primary hub and should not be rewritten.
- `docs/orchestration_start_here.md` remains the fuller conceptual model.
- The new architecture overview is a short front door, not a duplicate guide.
- The capability matrix is an informative status index; specs/design docs remain authority.
- `docs/design/README.md` is a curator page; it does not replace design docs.
- Existing dirty or staged files unrelated to this docs pass must not be reverted or swept into the commit.
