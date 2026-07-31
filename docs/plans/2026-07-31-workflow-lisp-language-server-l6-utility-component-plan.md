# Workflow Lisp Language Server L6 Utility Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Each
> selected unit receives independent specification review followed by a
> distinct quality review before commit. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Implement only an explicitly owner-activated subset of the three
accepted L6 utilities: authored signature/declared-header hover, reverse-L5
references, and a standalone `.orc` TextMate grammar.

**Architecture:** L6a and L6b extend only the immutable current-success views
in `orchestrator/lsp/navigation.py` and their protocol translation in
`orchestrator/lsp/server.py`; the existing state/driver preflight remains the
sole freshness authority. L6c is an independently selectable repository asset
verified by a locked real TextMate/Oniguruma oracle and by production-parser,
packaging, and server-isolation controls.

**Tech Stack:** Python 3.11+, frozen dataclasses/tuples, pygls/lsprotocol,
pytest/pytest-xdist, framed JSON-RPC over stdio, TextMate JSON,
`vscode-textmate@9.2.0`, `vscode-oniguruma@2.0.1`, and Node only for the
development-time L6c oracle.

**Accepted design:** commit
`e7de48e2710dddefbf14717575973b4ce41b5a06`, tree
`0a2bb399c10b4242c314f9fcc924cf89f6a6b9b6`, exact
`docs/design/workflow_lisp_language_server.md` SHA-256
`3c52e3d0fb9c5683eae80ae3d81aae7d6e75bef71ef72c7daf19e6da1ecee338`,
after ordered `L6_DESIGN_SPEC_APPROVED` then
`L6_DESIGN_QUALITY_APPROVED`.

**Design review record:**
`artifacts/review/workflow-lisp-language-server-l6-design-review.md`, exact
SHA-256
`b5ea1849ae67d4b806a6512cc4c0cdb5fad1b0c7a37f4914d661402c6fcd8028`.

**Plan status:** accepted and reviewed; no implementation selected. The exact
reviewed plan landed at `df2b468c284585d7de3740e791df0eb427283148`, tree
`f86be7c721a4fcd992c1572b88fdd2ebc94961b8`, with plan SHA-256
`9b8281c2622476a1028eb48d12464ed2bdcdaceb6a4a7eba6a4ba2580da69227`
after ordered `L6_PLAN_SPEC_APPROVED` then `L6_PLAN_QUALITY_APPROVED`. The
exact review record is
`artifacts/review/workflow-lisp-language-server-l6-plan-review.md`, SHA-256
`0052bbea068fdff7bd5ac01786f10d92bc5e073195fb6cab7388c596599a1cb2`.
This plan selects no implementation and no L6 unit; the current activation is
**none**.

---

## Selection, Scope, And Deliberate Costs

A valid activation is an explicit owner decision made after both plan reviews.
The activation-only update to this plan must name `owner`, `activated_at`, a
stable decision-source reference, and a non-empty sorted `activated_units`
subset of `L6a`, `L6b`, and `L6c`. That mechanical field population does not
reopen plan review; any change to tasks, scope, or gates does. The resulting
activation commit/tree is recorded in the postcommit operator handoff, not
self-referentially inside its own commit. Plan approval, task listing,
eligibility, or activation of one unit does not activate another. The current
activation is **none**.

Each activated unit keeps its own RED/GREEN cycle, ordered implementation
reviews, behavior commit, broad non-security gate, routing/status closure,
ordered final reviews, and postcommit control. Even when the owner activates
multiple units together, do not combine their behavior or closure commits.
This independent selection makes batching shared navigation edits harder; the
cost is accepted to prevent one utility from selecting another implicitly.

L6c deliberately recognizes generic-type nesting only through depth 20.
Production-valid depths 21, 50, and 100 receive lower-fidelity ordinary-symbol
presentation with no invalid scope. Do not turn a TextMate recognizer miss
into a compiler-validity claim.

## Governing Authorities And Protected Surfaces

Read before execution:

- `AGENTS.md` and `docs/index.md`;
- the exact accepted design binding above;
- `docs/plans/2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md`;
- `docs/design/workflow_lisp_frontend_specification.md` §76.1;
- `docs/design/workflow_language_design_principles.md`, especially Principles
  28-30;
- the completed L1 and L5 implementation plans; and
- `docs/workflow_lisp_language_server_setup.md`.

If this plan conflicts with the accepted design, correct and rereview the plan
before activation. Do not reinterpret the design in code.

Permitted behavior owners are exact:

- L6a/L6b: `orchestrator/lsp/navigation.py`,
  `orchestrator/lsp/server.py`, existing focused LSP tests, and no compiler
  fixture changes unless an existing L1/L5 fixture cannot express a required
  test;
- L6c: `grammars/workflow-lisp.tmLanguage.json`,
  `tools/textmate-oracle/{package.json,package-lock.json,tokenize.mjs}`,
  `tests/test_workflow_lisp_textmate_grammar.py`, and
  `tests/fixtures/workflow_lisp/grammar/lexical_vectors.orc`; and
- per-unit closure: only the exact routing/setup/capability files named in
  Task 4.

Protected from modification are all compiler/frontend modules under
`orchestrator/workflow_lisp/`, `orchestrator/lsp/state.py`,
`orchestrator/lsp/compile_driver.py`, runtime, workflow, provider, prompt,
security, safety, secrets, and provider-isolation paths. L6c must not modify
`pyproject.toml`, enter Python package data, or add server discovery. If an
activated unit appears to require a protected change, stop that unit and
return to design review.

Execute in `/home/ollie/Documents/agent-orchestration`. Do not create a
worktree or clone. Preserve unrelated changes; never use `git add .`,
`git add -A`, destructive checkout/reset, or broad cleanup. Use tmux for any
command expected to exceed one minute, including broad pytest. Do not run or
modify security-related tests.

## Gate 0: Plan Review And Owner Activation

- [x] Verify the accepted design commit, tree, and file SHA-256 exactly match
      the bindings above.
- [x] Obtain independent `L6_PLAN_SPEC_APPROVED` against this complete plan.
- [x] Obtain distinct `L6_PLAN_QUALITY_APPROVED` only after specification
      approval. If bytes change, restart the ordered pair.
- [x] Commit the exact reviewed plan without marking any unit active. The
      reviewed plan landed at `df2b468c`, tree `f86be7c7`.
- [ ] Receive the explicit owner activation naming the selected subset, fill
      only the fixed activation fields above, and commit that activation-only
      update. Record its resulting commit/tree in the postcommit handoff. Do
      not enter any unlisted task.

## Task 1: L6a Authored Symbol And Callable Hover

**Entry condition:** the activation record names `L6a`.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Test: `tests/test_workflow_lisp_lsp_navigation.py`
- Test: `tests/test_workflow_lisp_lsp_integration.py`
- Test: `tests/test_workflow_lisp_lsp_stdio.py`
- Test: `tests/test_workflow_lisp_lsp_e2e.py`

- [ ] Inventory `NavigationIndex`, L1 symbol/completion producers, all L5
      `DefinitionLink` producers, `_current_navigation`, protocol feature
      registration, and the existing renderer call sites. Record the exact
      task-owned paths and confirm protected files are clean.
- [ ] Add focused tests first for the accepted six-field hover row; all ten L1
      definition selection spans; exact procedure-call, workflow-call, and
      retained proc-ref spans; shared L1 signature rendering; first/last
      in-token bounds; prompt/macro/arbitrary-expression nulls; duplicate,
      overlap, missing, and mismatched facts; and the complete current-snapshot
      null matrix.
- [ ] Add a real stdio test proving exact plain-text definition and callable
      hover/range, then dirty-state `null`, with no workspace writes.
- [ ] Run the new selectors and capture the intended RED caused only by the
      absent hover row/query/handler. Do not weaken an existing assertion.
- [ ] Implement the minimum immutable hover projection and lookup in
      `navigation.py`. Refactor the existing procedure/workflow completion
      detail helpers into one shared L1 renderer; do not duplicate rendering,
      parse source text, or add metadata.
- [ ] Add only the `textDocument/hover` translation/registration in
      `server.py`, reusing `_current_navigation` unchanged. Convert the exact
      anchor span only after the pure lookup succeeds.
- [ ] Run `pytest --collect-only -q` for every changed test module, then run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_e2e.py
  ```

- [ ] Inspect the complete exact diff and run `git diff --check`. Obtain
      `L6A_IMPLEMENTATION_SPEC_APPROVED`, then distinct
      `L6A_IMPLEMENTATION_QUALITY_APPROVED`; restart both if bytes change.
- [ ] Stage only the reviewed L6a files and commit with subject
      `Add Workflow Lisp signature hover`. Run the focused selector again
      postcommit.

## Task 2: L6b Reverse-L5 References

**Entry condition:** the activation record names `L6b`.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Test: `tests/test_workflow_lisp_lsp_navigation.py`
- Test: `tests/test_workflow_lisp_lsp_integration.py`
- Test: `tests/test_workflow_lisp_lsp_stdio.py`
- Test: `tests/test_workflow_lisp_lsp_e2e.py`

- [ ] Inventory the frozen five-field L5 rows, target/occurrence collision
      keys, deterministic sort keys, definition lookup, current-snapshot
      preflight, and protocol registration. Confirm no L6a behavior is needed
      to implement this unit.
- [ ] Add tests first for exact
      `(target_kind, canonical_target, definition_span)` grouping across all
      four L5 reference kinds; procedure-call plus proc-ref union; same
      spelling across namespaces remaining separate; deterministic
      deduplication/order; both `includeDeclaration` values; whole-definition
      span reuse; exact-token bounds; and definition-token `null`.
- [ ] Add fail-closed tests for unsupported/colliding rows, missing accepted
      text, failed coordinate conversion, out-of-closure locations, every
      current-snapshot null state, and no partial result.
- [ ] Add a real stdio test proving closure-local `Location[]`, declaration
      inclusion both ways, deterministic order, dirty-state `null`, and zero
      workspace/run/build/artifact writes.
- [ ] Run the new selectors and capture the intended RED caused only by the
      absent reverse query/handler.
- [ ] Implement the minimum pure reverse lookup in `navigation.py` over the
      existing `definition_links`; do not discover occurrences, scan files,
      aggregate entry snapshots, or invent a definition-name span.
- [ ] Add only the `textDocument/references` translation/registration in
      `server.py`, reusing `_current_navigation` and converting the complete
      tuple only after every span succeeds.
- [ ] Run `pytest --collect-only -q` and the same four-module focused command
      from Task 1. Inspect the exact diff and run `git diff --check`.
- [ ] Obtain `L6B_IMPLEMENTATION_SPEC_APPROVED`, then distinct
      `L6B_IMPLEMENTATION_QUALITY_APPROVED`; restart both if bytes change.
- [ ] Stage only the reviewed L6b files and commit with subject
      `Add Workflow Lisp authored references`. Run the focused selector again
      postcommit.

## Task 3: L6c Standalone TextMate Grammar

**Entry condition:** the activation record names `L6c`.

**Files:**

- Create: `grammars/workflow-lisp.tmLanguage.json`
- Create: `tools/textmate-oracle/package.json`
- Create: `tools/textmate-oracle/package-lock.json`
- Create: `tools/textmate-oracle/tokenize.mjs`
- Create: `tests/test_workflow_lisp_textmate_grammar.py`
- Create: `tests/fixtures/workflow_lisp/grammar/lexical_vectors.orc`

- [ ] Write the fixture and Python acceptance tests first. Bind the complete
      design scope table and scope stacks, comment/string precedence,
      declaration heads including `defun`, valid and invalid lexical vectors,
      and exact source ranges. Run the new module and capture RED for the
      absent grammar/oracle.
- [ ] Add `package.json` with only exact pins `vscode-textmate@9.2.0` and
      `vscode-oniguruma@2.0.1`; generate and inspect `package-lock.json` so the
      resolved graph/integrities are complete and no dependency range or
      third direct package remains. Never stage `node_modules/`.
- [ ] Implement `tokenize.mjs` to load `onig.wasm`, tokenize the committed
      fixture line by line through `vscode-textmate.Registry`, and emit
      canonical JSON source ranges plus complete scope stacks. Provision the
      locked packages before testing; tokenization itself must require no
      network.
- [ ] Implement the minimum grammar with the accepted exact scopes,
      precedence, recursive Oniguruma generic matcher, depth-20 bound,
      conservative bracket-bearing fallback, and no semantic claims beyond
      the accepted design.
- [ ] In the Python test, cross-check `read_sexpr_text` and
      `parse_type_expression` accept `G(20)`, `G(21)`, `G(50)`, and `G(100)`.
      Require one generic region for `G(20)` and ordinary-symbol/no-invalid
      fallback for depths 21, 50, and 100. Require malformed named vectors to
      fall back without invalid scope and the exact reader-rejected vectors to
      receive their specified `invalid.illegal` scopes.
- [ ] Prove packaging/server isolation: build a wheel from a temporary source
      copy and inspect it for zero grammar/oracle files; assert `pyproject.toml`
      remains unchanged; import/construct and stdio-launch the packaged LSP
      without the repository grammar and prove no grammar discovery/read.
- [ ] Run:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_textmate_grammar.py
  pytest -q tests/test_workflow_lisp_textmate_grammar.py
  ```

  Then inspect the complete asset/oracle/test diff, lockfile, and
  `git diff --check`.
- [ ] Obtain `L6C_IMPLEMENTATION_SPEC_APPROVED`, then distinct
      `L6C_IMPLEMENTATION_QUALITY_APPROVED`; restart both if bytes change.
- [ ] Stage only the six reviewed L6c paths and commit with subject
      `Add Workflow Lisp TextMate grammar`. Run the acceptance module again
      postcommit.

## Task 4: Per-Unit Broad Gate, Routing Closure, And Final Review

Run this task separately for each activated and implemented unit. Completing
it for one unit does not change another unit's status.

**Files (edit only the selected unit's exact rows/paragraphs):**

- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify: `docs/workflow_lisp_language_server_setup.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/design/README.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md`
- Modify: this plan
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Create per unit: `artifacts/review/l6a-hover-final-review.md`,
  `artifacts/review/l6b-references-final-review.md`, or
  `artifacts/review/l6c-textmate-final-review.md`

- [ ] Run the selected unit's complete focused selectors and its repository-
      real stdio/oracle gate from Tasks 1-3. Record collection/pass/fail/error/
      skip totals, elapsed time, exact commit/tree, and raw-output digest.
- [ ] Update only the selected unit to implemented-pending-final-review across
      the design, setup guide, capability matrix, L6 roadmap, routing indexes,
      this plan, and routing tests. Keep every unselected unit explicitly
      unselected and every selected-but-incomplete unit truthful.
- [ ] Run `pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py`, the
      selected focused gate, and `git diff --check` against the complete
      closure candidate.
- [ ] In tmux, run the repository-standard broad non-security suite:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

- [ ] Classify any failure against the focused reproduction before attributing
      it to L6. Do not repair an unrelated or protected failure under this
      plan and do not weaken verification.
- [ ] Write the selected final-review artifact with exact behavior commit,
      closure diff/hash, focused/stdio-or-oracle/broad evidence, exclusions,
      and remaining unselected units. Obtain ordered
      `L6A_FINAL_SPEC_APPROVED` then `L6A_FINAL_QUALITY_APPROVED`, or the
      corresponding `L6B_*`/`L6C_*` pair, against unchanged bytes.
- [ ] Commit only the exact reviewed closure with subject `Close L6a hover`,
      `Close L6b references`, or `Close L6c grammar`. Run the selected focused
      selector and routing test postcommit; record the exact commit/tree and
      outcome in an external closure record without editing reviewed bytes.

## Acceptance And Stop Conditions

Per selected unit, completion requires its behavior commit, exact accepted
contract, focused and real stdio/oracle evidence, broad non-security gate,
routing/setup/capability closure, ordered final reviews, and postcommit
control. No capability is complete from inspection, plan review, or another
unit's evidence.

Stop and return to design review if L6a/L6b requires compiler/frontend,
state/driver, source parsing, snapshot aggregation, or invented spans; if L6c
requires production JavaScript, wheel/editor auto-discovery, tree-sitter, or
claims validity from highlighting; or if any unit cannot preserve the accepted
fail-closed/null and no-write boundaries. Do not activate a successor or mark
the whole L6 stage complete from a partial unit closure without a separate
owner decision.
