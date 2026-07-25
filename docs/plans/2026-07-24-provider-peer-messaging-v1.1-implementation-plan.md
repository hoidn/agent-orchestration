# Provider Peer Messaging v1.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Every behavior change uses
> `superpowers:test-driven-development`; every task receives an independent
> specification-compliance review followed by an implementation-quality
> review before its commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stage 7 v1.1 recorded turn-boundary messaging and pure
settlement for a static group of two through eight live provider members,
without changing the shipped target-2.16 provider-supervision surface.

**Architecture:** Add a provider-neutral interactive terminal capability and
adapter, then place all peer protocol, receiving-attempt ledger, lifecycle,
and result mutations behind one `provider_peer_group.v1` coordinator. Expose
that separate executable node through target-2.17 Workflow Lisp, the ordinary
WCC/schema-2 route, and every established executable projection; do not reuse
the observation pane or v1 cancellation/resume/directive path.

**Tech Stack:** Python 3.11+, immutable dataclasses, Unix-domain local
request/response transport, append-only canonical JSONL, subprocess/POSIX
process groups, tmux, Workflow Lisp WCC schema 2, executable IR v1, state
schema 2.1, pytest/pytest-xdist.

**Accepted design:** `docs/design/workflow_lisp_provider_peer_messaging.md`
at commit `8001c01653f46df4b32fc0c8859bf68f2c785c63`, tree
`37cfc863d80bf84fa82211d3794c3aaae23c983d`, content digest
`sha256:4f21cec1c10a9f3040649ae56fd17c7f561216ffed90cc7789c6fd91a6d48d9b`.
That commit includes the independently approved amendment and its routing
updates. Implementation may begin only after this plan itself receives both
ordered reviews and is committed.

**Status:** Independently reviewed and approved for subagent-driven
execution. No v1.1 implementation code began before this plan gate.

**Plan review:** Independent design/sequence review:
`PLAN_SPEC_APPROVED`. Ordered path/selector/execution-quality review:
`PLAN_QUALITY_APPROVED` after correcting the CLI package paths, explicit E2E
enablement on the closing real gate, and the complete owner-directed
security-test exclusion set.

---

## Scope And Deliberate Cost

This plan implements only:

- target DSL `2.17` `with-live-provider-peers`;
- literal, authored-order groups of `2..8` members;
- `provider_peer_group.v1`;
- the declared `interactive_terminal_turn_queue.v1` capability;
- exact-attempt `peer-ready`, `peer-send`, `peer-ack`, and `peer-finish`;
- durable receiver-ledger record-before-offer ordering;
- natural turn-boundary delivery and provider-declared natural close;
- typed frozen member bundles and one pure atomic settlement; and
- whole-visit interruption quarantine and force-restart behavior.

Do not combine this feature with v1 `STEER`, provider-session resume,
observation panes, dynamic membership, per-edge ACLs, effectful settlement,
cross-run messages, transcript parsing, or general background/join
primitives. Do not implement or test any security work.

The direct additive implementation makes a future mixed peer-plus-STEER
surface harder: that future work must explicitly define message ownership
across replacement attempts instead of inheriting an accidental behavior.
Keeping a separate coordinator and node also leaves some v1/v1.1 structural
duplication. That is accepted to preserve byte- and behavior-compatible v1
artifacts.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/workflow_lisp_provider_peer_messaging.md`
- `docs/design/workflow_lisp_provider_live_binding.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_lisp_native_transportable_returns.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- `docs/plans/2026-07-23-provider-live-binding-implementation-plan.md`
- `specs/providers.md`
- `specs/io.md`
- `specs/state.md`
- `specs/versioning.md`
- `specs/observability.md`

If this plan conflicts with the accepted design, correct the plan; do not
reinterpret the design in code.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Stage only task-owned paths and commit after the two
ordered reviews. Never use `git add .`, `git add -A`, destructive
checkout/reset, or broad cleanup. Preserve all pre-existing user changes.

For every implementation task:

1. write the smallest behavioral or contract test that must fail;
2. run it and confirm the failure is caused by missing v1.1 behavior;
3. implement only the behavior selected by that test;
4. rerun the narrow selector;
5. run the task's adjacent regression selector;
6. run `pytest --collect-only -q` for every new or renamed test module;
7. dispatch one fresh specification reviewer against the accepted design and
   task diff;
8. fix and re-review until specification approval;
9. dispatch a separate quality reviewer against the approved diff;
10. fix and re-review until quality approval; and
11. stage exact paths, run `git diff --cached --check`, and commit.

Use the `tmux` skill for real-provider checks and the closing broad suite.
Keep the installed/default provider and model; wait for it rather than
substituting a faster model. A real gate that needs Escape, Ctrl-C,
cancellation, provider-session resume, authoritative screen parsing, or a
forcing key triggers the accepted design's stop/revise criterion.

Security is excluded by owner direction. The broad command must exclude:

```text
tests/test_at61_at62_wait_for_path_safety.py
tests/test_cli_safety.py
tests/test_provider_isolation_policy.py
tests/test_provider_isolation_schema_resources.py
tests/test_secrets.py
```

and must use `-k 'not security and not secret and not isolation'`.

## Protected Working Tree

The following existing changes are outside this plan. Do not edit, restore,
stage, or commit them:

```text
docs/index.md
docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
docs/plans/2026-07-01-workflow-audit-tier-fixes.md
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
docs/superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md
state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md
```

`docs/index.md` currently contains an unstaged owner-authored parked-roadmap
hunk. A later routing task may update only peer-messaging rows and must stage
those hunks interactively, leaving the owner hunk unstaged.

## File And Responsibility Map

New focused modules:

- `orchestrator/providers/interactive_terminal.py`: capability validation and
  the `interactive_terminal_turn_queue.v1` adapter/handle contract.
- `orchestrator/workflow/provider_peer_group/models.py`: closed group,
  member, lifecycle, request, receipt, and evidence records.
- `orchestrator/workflow/provider_peer_group/paths.py`: safe visit/member
  prompt, ledger, evidence, and provisional-bundle paths.
- `orchestrator/workflow/provider_peer_group/ledger.py`: canonical,
  append-only, fsynced receiver ledger.
- `orchestrator/workflow/provider_peer_group/protocol.py`: bounded local
  endpoint, opaque member binding, and thin client transport.
- `orchestrator/workflow/provider_peer_group/coordinator.py`: the only group
  lifecycle/evidence/result writer and serialized event loop.
- `orchestrator/workflow/provider_peer_group/bindings.py`: pure settlement
  evaluation and typed-bundle validation bridge.

Extend existing files only at their established seams:

- provider template schema/loading: `orchestrator/providers/types.py`,
  `orchestrator/providers/registry.py`, `orchestrator/providers/__init__.py`;
- member CLI: `orchestrator/cli/main.py`,
  `orchestrator/cli/commands/peer.py`,
  `orchestrator/cli/commands/__init__.py`;
- executable/runtime dispatch: `orchestrator/workflow/executable_ir.py`,
  `orchestrator/workflow/runtime_step.py`,
  `orchestrator/workflow/runtime_plan.py`,
  `orchestrator/workflow/executor.py`,
  `orchestrator/workflow/resume_planner.py`,
  `orchestrator/workflow/provider_attempts.py`;
- surface/type/effect/WCC: `orchestrator/workflow_lisp/syntax.py`,
  `form_registry.py`, `expressions.py`, `effects.py`, `macros.py`,
  `functions.py`, `expression_traversal.py`, `typecheck_dispatch.py`,
  `typecheck_effects.py`, and
  `wcc/{model,anf,route,elaborate,analysis,defunctionalize}.py`;
- projections: `orchestrator/workflow/{core_ast,runtime_plan,semantic_ir}.py`,
  `orchestrator/workflow_lisp/{build_artifacts,source_map}.py`;
- docs/specs only after behavior passes.

Do not move v1 implementation into common modules during this tranche.

## Task 1: Freeze v1 And Add The Structural Capability

**Outcome:** Complete. The six-artifact target-2.16 oracle and structural
capability passed fresh focused/adjacent validation and ordered
`TASK1_SPEC_APPROVED` / `TASK1_QUALITY_APPROVED` reviews.

**Files:**

- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/v1_2_16_artifact_digests.json`
- Create: `tests/test_provider_interactive_terminal.py`
- Modify: `tests/test_workflow_lisp_provider_supervision_e2e.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/providers/__init__.py`

- [x] **Step 1: Commit a target-2.16 compatibility oracle**

Compile the existing
`tests/fixtures/workflow_lisp/provider_supervision/provider_supervision_continue.orc`
at the accepted-design commit and record canonical digests for executable IR,
Core AST, runtime plan, Semantic IR, source map, and build manifest. Add one
test that recompiles the fixture and compares exactly to those digests.

- [x] **Step 2: Prove the new capability tests fail**

Add tests for an immutable `InteractiveSessionSupport` with:

```python
schema_version = "interactive_terminal_turn_queue.v1"
turn_boundary_messages = True
command = ("codex", "${PROMPT}")
message_submit_keys = ("ENTER",)
graceful_close_text = "/exit"
graceful_close_submit_keys = ("ENTER",)
```

Test missing/extra fields, empty strings/tokens, zero or duplicate
`${PROMPT}`, `${SESSION_ID}`, unknown schema, non-boolean enablement, and every
forcing key/action. Test that name, input mode, TTY availability,
`session_support`, and observation support never infer the capability.

Run:

```bash
pytest -q tests/test_provider_interactive_terminal.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py \
  -k 'interactive_session or target_2_16_artifact'
```

Expected: FAIL only because the capability and compatibility helper do not
exist.

- [x] **Step 3: Implement closed capability parsing and validation**

Add the optional capability to `ProviderTemplate`, include it in builtin and
workflow-manifest loading, and validate it structurally. Keep providers
without it valid outside a peer group. Adapter selection may inspect only
`schema_version`.

- [x] **Step 4: Run narrow and adjacent tests**

```bash
pytest -q tests/test_provider_interactive_terminal.py
pytest -q tests/test_provider_execution.py tests/test_provider_supervision_ir.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py
pytest --collect-only -q tests/test_provider_interactive_terminal.py
```

Expected: all pass and the v1 digest oracle is unchanged.

- [x] **Step 5: Obtain ordered reviews and commit**

Commit message: `Add structural interactive provider capability`.

## Task 2: Implement The Interactive Terminal Adapter

**Files:**

- Create: `orchestrator/providers/interactive_terminal.py`
- Extend: `tests/test_provider_interactive_terminal.py`

- [ ] **Step 1: Add fake-driver failing tests**

Cover `start`, literal `offer`, `offer_close`, `join`, and `abort` against a
recording tmux/subprocess driver. Assert exact handle binding, literal UTF-8
and multiline preservation, only declared submit keys, natural-exit proof,
pane/process loss, offer/close timeout, cleanup failure, and that no v1
cancellation, resume, observation, or directive API is invoked.

- [ ] **Step 2: Run the failing selector**

```bash
pytest -q tests/test_provider_interactive_terminal.py -k 'adapter or handle'
```

Expected: FAIL because adapter operations are absent.

- [ ] **Step 3: Add the minimal provider-neutral adapter**

Own a private tmux server/session and one provider TUI pane per handle. Build
the launch command only from the validated capability and resolved
invocation. `offer` submits literal framing plus verbatim message at a natural
queued turn; `offer_close` submits only the declared close text; `join`
requires natural client/process/pane completion. `abort` is cleanup evidence
only and can never produce a successful member result.

- [ ] **Step 4: Run narrow and provider regressions**

```bash
pytest -q tests/test_provider_interactive_terminal.py
pytest -q tests/test_provider_observation.py \
  tests/test_provider_observation_execution.py \
  tests/test_provider_execution_control.py
```

Expected: all pass.

- [ ] **Step 5: Obtain ordered reviews and commit**

Commit message: `Add turn-boundary interactive provider adapter`.

## Task 3: Add Closed Peer Contracts, Paths, And Ledgers

**Files:**

- Create: `orchestrator/workflow/provider_peer_group/__init__.py`
- Create: `orchestrator/workflow/provider_peer_group/models.py`
- Create: `orchestrator/workflow/provider_peer_group/paths.py`
- Create: `orchestrator/workflow/provider_peer_group/ledger.py`
- Create: `tests/test_provider_peer_group_contracts.py`

- [ ] **Step 1: Write closed-schema and path tests**

Test exact keys/types for group/member configs, lifecycle states, endpoint
identity, opaque sender binding, request/receipt unions, immutable frozen
member results, and terminal evidence. Test deterministic safe paths for
`2..8` members and rejection of absolute, parent, colliding, duplicate, or
pre-existing nonempty path plans.

- [ ] **Step 2: Write ledger ordering tests**

Test an explicit fsynced header, canonical monotonically sequenced
`recorded`, `offered|offer_failed`, and `receiver_acknowledged` rows,
record-before-offer ordering, exact sender/receiver attempt identities,
verbatim content/digest, final digest/counts, and rejection of mutation,
replacement, malformed tails, duplicate ids, or wrong-attempt ack.

- [ ] **Step 3: Confirm tests fail**

```bash
pytest -q tests/test_provider_peer_group_contracts.py
```

Expected: FAIL because the package is absent.

- [ ] **Step 4: Implement minimal immutable contracts and ledger**

Use canonical JSON with sorted keys and compact separators. Open ledgers in
exclusive-create/append mode, flush and `fsync` every lifecycle row, and
never store messages in prompt dependency snapshots or workflow values.

- [ ] **Step 5: Run narrow and adjacent evidence tests**

```bash
pytest -q tests/test_provider_peer_group_contracts.py
pytest -q tests/test_provider_supervision_ir.py \
  tests/test_prompt_dependency_evidence.py
pytest --collect-only -q tests/test_provider_peer_group_contracts.py
```

Expected: all pass.

- [ ] **Step 6: Obtain ordered reviews and commit**

Commit message: `Add provider peer group contracts and ledgers`.

## Task 4: Add The Bound Endpoint And Thin Peer Clients

**Files:**

- Create: `orchestrator/workflow/provider_peer_group/protocol.py`
- Create: `tests/test_provider_peer_group_protocol.py`
- Create: `orchestrator/cli/commands/peer.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Add failing endpoint/client tests**

Test one local endpoint bound to
`run_id/step_name/node_id/visit_count/endpoint_instance_id`, opaque
environment-only member credentials, one bounded canonical request and
receipt, `65_536`-byte UTF-8 message ceiling, required client request id,
unknown/extra fields, incomplete frames, endpoint closure, and waiter
resolution. Test the CLI exposes only:

```text
peer-ready
peer-send <target-binding> <message>
peer-ack <message-id>
peer-finish
```

and offers no sender, root, endpoint, pane, state, ledger, or run selector.

- [ ] **Step 2: Confirm the selectors fail**

```bash
pytest -q tests/test_provider_peer_group_protocol.py \
  tests/test_workflow_lisp_cli.py -k 'peer_'
```

Expected: FAIL because the transport and commands are absent.

- [ ] **Step 3: Implement listener/event handoff and thin clients**

The listener decodes and bounds requests, enqueues immutable events, and
waits for coordinator receipts. It never touches state, ledgers, bundles, or
the adapter. Client helpers read only the opaque active-group environment,
perform one request, print/return the receipt, and map closed errors to
nonzero exit.

- [ ] **Step 4: Run narrow and CLI regressions**

```bash
pytest -q tests/test_provider_peer_group_protocol.py
pytest -q tests/test_workflow_lisp_cli.py tests/test_cli_report_command.py
pytest --collect-only -q tests/test_provider_peer_group_protocol.py
```

Expected: all pass.

- [ ] **Step 5: Obtain ordered reviews and commit**

Commit message: `Add attempt-bound provider peer protocol`.

## Task 5: Implement The Single-Writer Group Coordinator

**Files:**

- Create: `orchestrator/workflow/provider_peer_group/coordinator.py`
- Create: `orchestrator/workflow/provider_peer_group/bindings.py`
- Create: `tests/test_provider_peer_group_runtime.py`
- Extend: `orchestrator/workflow/provider_peer_group/models.py`
- Extend: `orchestrator/workflow/provider_peer_group/protocol.py`

- [ ] **Step 1: Test allocation and readiness fail-first**

With a fake adapter and listener, prove every attempt, prompt snapshot, empty
ledger, and provisional path is allocated before launch; `peer-ready` blocks
until every member reaches `READY_WAITING`; one coordinator transition makes
all members `ACTIVE`; barrier failure resolves every waiter and joins all
resources.

- [ ] **Step 2: Test send/ack ordering fail-first**

Cover exact attribution/targeting, self/unknown/ambiguous/stale/not-ready/
closing/terminal rejection without a ledger row, record+fsync before adapter
offer, durable offered before client success, offer failure, exact ack,
same-request replay, conflicting replay, two concurrent senders, and endpoint
shutdown with waiting clients.

- [ ] **Step 3: Test finish and race semantics fail-first**

Cover `pending_messages`, both send-vs-finish orderings, freeze only after
valid typed bundle and all incoming acks, close offered while the finish
request remains active, successful receipt before the caller's turn ends,
natural join before `TERMINAL`, early provider exit, close/join timeout,
failure cleanup, and no settlement publication on any failure.

- [ ] **Step 4: Confirm the lifecycle suite fails**

```bash
pytest -q tests/test_provider_peer_group_runtime.py
```

Expected: FAIL because the coordinator is absent.

- [ ] **Step 5: Implement one serialized coordinator event loop**

Only the coordinator may mutate lifecycle, ledgers, frozen bundles, evidence,
state, or settlement. Listener/member threads emit immutable events. Preserve
authored order, one atomic terminal commit, exact current-step clearance, and
proved cleanup. A finish with outstanding incoming messages returns
`pending_messages` and leaves the member `ACTIVE`.

- [ ] **Step 6: Run narrow and adjacent coordinator tests**

```bash
pytest -q tests/test_provider_peer_group_runtime.py
pytest -q tests/test_provider_supervision_runtime.py \
  tests/test_provider_supervision_resume.py \
  tests/test_state_manager.py
pytest --collect-only -q tests/test_provider_peer_group_runtime.py
```

Expected: all pass.

- [ ] **Step 7: Obtain ordered reviews and commit**

Commit message: `Implement provider peer group coordinator`.

## Task 6: Add The Executable Node, Runtime Dispatch, And Quarantine

**Files:**

- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Create: `tests/test_provider_peer_group_ir.py`
- Create: `tests/test_provider_peer_group_resume.py`
- Extend: `tests/test_provider_peer_group_runtime.py`
- Modify: `tests/test_resume_command.py`

- [ ] **Step 1: Add failing closed-IR tests**

Define `ExecutableNodeKind.PROVIDER_PEER_GROUP` and
`provider_peer_group.v1`. Test exact `2..8` authored-order members, closed
all-other-member policy, settlement/result contract, positive member and
whole-step timeouts, distinct visit/member paths, capability requirement,
source ownership, `max_steers: 0`, and tamper/extra/missing/reordered member
and path failures.

- [ ] **Step 2: Add failing hand-built runtime tests**

Drive the coordinator from a hand-built typed executable node. Prove
capability preflight repeats before launch, overlapping member attempts,
frozen-bundle authority, pure authored-order settlement, one atomic state and
result write, terminal evidence, reportable failure, and cleanup.

- [ ] **Step 3: Add interruption/quarantine tests**

An interrupted running peer visit without its exact terminal result must
retain partial ledgers/evidence, clear the exact current step, record a sticky
peer-group quarantine failure, and make ordinary resume fail. Explicit force
restart creates new visit/attempt/endpoint/ledger identities. It never
retargets a message or resumes a member.

- [ ] **Step 4: Confirm all new tests fail**

```bash
pytest -q tests/test_provider_peer_group_ir.py \
  tests/test_provider_peer_group_runtime.py \
  tests/test_provider_peer_group_resume.py \
  tests/test_resume_command.py -k 'peer_group'
```

Expected: FAIL because executable/runtime cases are absent.

- [ ] **Step 5: Implement the new node and dispatch**

Add the node beside, not inside, `ProviderSupervisionStepConfig`. Reuse only
generic atomic finalization and attempt allocation APIs. Keep the v1
serializer, runtime step, resume guard, and coordinator behavior unchanged.
Because members run concurrently and every close/join must fit inside the
member deadline, derive the ordinary whole-step timeout as
`max(member.timeout_sec)`; do not invent new surface syntax or add sequential
member budgets.

- [ ] **Step 6: Run narrow, v1 regression, and collection checks**

```bash
pytest -q tests/test_provider_peer_group_ir.py \
  tests/test_provider_peer_group_runtime.py \
  tests/test_provider_peer_group_resume.py
pytest -q tests/test_provider_supervision_ir.py \
  tests/test_provider_supervision_runtime.py \
  tests/test_provider_supervision_resume.py \
  tests/test_resume_command.py
pytest --collect-only -q tests/test_provider_peer_group_ir.py \
  tests/test_provider_peer_group_resume.py
```

Expected: all pass.

- [ ] **Step 7: Obtain ordered reviews and commit**

Commit message: `Add provider peer group executable runtime`.

## Task 7: Pass The Real One-Member Adapter Feasibility Gate

**Files:**

- Create: `tests/e2e/test_e2e_provider_peer_delivery.py`
- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/real_adapter_prompt.md`
- Extend: `orchestrator/providers/interactive_terminal.py` only if required
  by behavior already specified in the accepted design.

- [ ] **Step 1: Add a bounded real-adapter test**

The test owns a temporary endpoint, bundle path, ledger, and adapter handle.
The initial real provider turn must call `peer-ready`; the harness then
records and offers one literal message; the queued next turn calls
`peer-ack`, writes one valid typed bundle, calls `peer-finish`, and ends
naturally after the declared close is offered.
Use `sys.executable -m orchestrator peer-*` in injected runtime guidance;
there is no repository console-script entry point to assume.

Assert:

```text
recorded -> offered -> receiver_acknowledged
valid frozen bundle
finish receipt
natural client exit
joined process/pane/helper boundary
no cancellation/resume/directive call
```

- [ ] **Step 2: Run it in tmux**

```bash
ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
  tests/e2e/test_e2e_provider_peer_delivery.py \
  -k real_one_member_adapter
```

Expected: PASS with the installed supported provider. If delivery needs a
forcing action, stop and revise the design; do not move the interruption
point or substitute a fixture.

- [ ] **Step 3: Run deterministic adapter regressions**

```bash
pytest -q tests/test_provider_interactive_terminal.py \
  tests/test_provider_peer_group_protocol.py \
  tests/test_provider_peer_group_runtime.py
```

Expected: all pass.

- [ ] **Step 4: Obtain ordered reviews and commit**

Commit message: `Prove real provider turn-boundary delivery`.

## Task 8: Add Target-2.17 Surface, Types, Effects, And WCC Closure

**Files:**

- Modify: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/effects.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/wcc/model.py`
- Modify: `orchestrator/workflow_lisp/wcc/anf.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/analysis.py`
- Create: `tests/test_workflow_lisp_provider_peer_group.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`

- [ ] **Step 1: Add surface and type failures**

Test target `<2.17` rejection, target `2.17` acceptance, literal `2`, `3`, and
`8` members, rejection of `1` and `9`, duplicate bindings, malformed binding
shape, sibling result capture, ineligible member shape, non-transportable
member/settlement type, effectful settlement, and pure settlement typing.
Assert `LivePeerMessagingEffect(members=<authored order>)` plus member effects
and no `LiveSupervisionEffect`.

- [ ] **Step 2: Add WCC closure failures**

Test recursive inline-specialized direct procedures, exactly one
unconditional provider perform plus pure projection, and rejection of
residual call/branch/loop/second perform/non-provider effect/later-sibling
reference. Assert one authored-order `WccProviderPeerGroup`, never a
`WccProviderSupervision`.

- [ ] **Step 3: Confirm the frontend tests fail**

```bash
pytest -q tests/test_workflow_lisp_provider_peer_group.py \
  tests/test_workflow_lisp_wcc_m4.py -k 'peer_group or live_provider_peer'
```

Expected: FAIL because target/form/effect/WCC cases are absent.

- [ ] **Step 4: Implement the smallest separate frontend route**

Add `MAX_STATIC_LIVE_PROVIDER_PEERS = 8`, the target gate, surface AST/type
case, effect, and WCC term. Generalize an existing pure helper only where its
contract is genuinely identical; do not rewrite v1 through the new form.

- [ ] **Step 5: Run narrow and full v1 frontend regressions**

```bash
pytest -q tests/test_workflow_lisp_provider_peer_group.py \
  tests/test_workflow_lisp_wcc_m4.py
pytest -q tests/test_workflow_lisp_provider_supervision.py \
  tests/test_workflow_lisp_wcc_characterization.py \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m2.py \
  tests/test_workflow_lisp_wcc_m3.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py
pytest --collect-only -q tests/test_workflow_lisp_provider_peer_group.py
```

Expected: all pass.

- [ ] **Step 6: Obtain ordered reviews and commit**

Commit message: `Add static provider peer group frontend`.

## Task 9: Lower Through Every Executable Projection

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/prompt_dependency_contract.py`
- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/pure_expr.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Create: `tests/test_workflow_lisp_provider_peer_group_e2e.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- [ ] **Step 1: Add failing lowering/projection tests**

Compile target-2.17 two-, three-, and eight-member fixtures and assert authored
order, independent member configs/result contracts, closed messaging policy,
`max_steers: 0`, pure settlement payload/contract, capability requirement,
paths, prompt ownership, and exact checkpoint inputs in Core, executable IR,
runtime plan, Semantic IR, source map, and public build exports.

- [ ] **Step 2: Add tamper and v1-separation tests**

Reject extra/missing/reordered members and paths at every parser/validator.
Assert the target-2.16 compatibility oracle from Task 1 remains identical and
target 2.17 still emits the old node for `with-live-providers`.

- [ ] **Step 3: Confirm the projection tests fail**

```bash
pytest -q tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_source_map.py \
  -k 'peer_group or live_provider_peer'
```

Expected: FAIL because defunctionalization/projections are absent.

- [ ] **Step 4: Implement WCC-to-Core-to-executable lowering**

Carry the peer group only through the ordinary post-WCC route and add explicit
cases to established projections. Do not change envelope schema versions and
do not add a surface-to-runtime escape.

- [ ] **Step 5: Run narrow and adjacent projection regressions**

```bash
pytest -q tests/test_workflow_lisp_provider_peer_group.py \
  tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_source_map.py
pytest -q tests/test_workflow_lisp_provider_supervision.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py
pytest --collect-only -q tests/test_workflow_lisp_provider_peer_group_e2e.py
```

Expected: all pass.

- [ ] **Step 6: Obtain ordered reviews and commit**

Commit message: `Lower provider peer groups through executable artifacts`.

## Task 10: Close Deterministic Runtime Integration

**Files:**

- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/provider_peer_group_three.orc`
- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/providers.json`
- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/prompts.json`
- Extend: `tests/test_workflow_lisp_provider_peer_group_e2e.py`
- Extend: `tests/test_provider_peer_group_resume.py`
- Modify runtime/report modules only where a failing test proves a missing
  established projection.

- [ ] **Step 1: Add deterministic two- and three-member execution tests**

Use controlled interactive provider fixtures to exercise
ready/send/ack/finish, literal Unicode/newlines, one pure aggregate result,
member ledger/evidence reports, exact provisional-bundle authority, one
atomic published settlement, and full endpoint/process cleanup.

- [ ] **Step 2: Add both-direction failure and restart tests**

Cover launch/barrier/send/offer/ack/bundle/finish/close/join/settlement
failures, controller interruption, sticky ordinary-resume rejection, and one
force restart with wholly new visit identities. Assert no failed path
publishes a settlement or retargets a message.

- [ ] **Step 3: Run deterministic integration**

```bash
pytest -q tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_provider_peer_group_resume.py \
  tests/test_cli_report_command.py
```

Expected: all pass.

- [ ] **Step 4: Run the complete Stage-7 focused set**

```bash
pytest -q \
  tests/test_provider_interactive_terminal.py \
  tests/test_provider_peer_group_contracts.py \
  tests/test_provider_peer_group_protocol.py \
  tests/test_provider_peer_group_ir.py \
  tests/test_provider_peer_group_runtime.py \
  tests/test_provider_peer_group_resume.py \
  tests/test_workflow_lisp_provider_peer_group.py \
  tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_provider_supervision_ir.py \
  tests/test_provider_supervision_runtime.py \
  tests/test_provider_supervision_resume.py \
  tests/test_workflow_lisp_provider_supervision.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py
```

Expected: all pass.

- [ ] **Step 5: Obtain ordered reviews and commit**

Commit message: `Integrate provider peer group execution`.

## Task 11: Pass The Real Two- And Three-Member Gates

**Files:**

- Extend: `tests/e2e/test_e2e_provider_peer_delivery.py`
- Create:
  `tests/fixtures/workflow_lisp/provider_peer_group/real_peer_group_three.orc`
- Create only the minimal real-provider prompt/extern fixtures required by
  the test.

- [ ] **Step 1: Run a real two-member protocol group in tmux**

One member must invoke `peer-send` through its ordinary shell tool. The
receiver must durably ack it, include the content in its valid typed result,
cooperatively finish, and close naturally. Assert exact ledgers, bundles,
cleanup, and one aggregate result.

- [ ] **Step 2: Run a real three-member `.orc` workflow in tmux**

Compile and execute the target-2.17 fixture through the public run surface.
Assert static composition, at least one recorded peer message, pure
settlement, reports, and one atomic result.

- [ ] **Step 3: Re-run the shipped v1 real smoke**

```bash
ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
  tests/e2e/test_e2e_provider_supervision.py
```

Expected: both v1 `CONTINUE|STEER` cases remain green and use
`provider_supervision.v1`.

- [ ] **Step 4: Run the real v1.1 gates**

```bash
ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
  tests/e2e/test_e2e_provider_peer_delivery.py
```

Expected: the one-member adapter, two-member peer-send, and three-member
`.orc` cases all pass without forcing input.

- [ ] **Step 5: Obtain ordered reviews and commit**

Commit message: `Prove real provider peer groups`.

## Task 12: Land Normative Docs And Close Gate S7-v1.1

**Files:**

- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/observability.md`
- Modify: `specs/index.md`
- Modify: `docs/design/workflow_lisp_provider_peer_messaging.md`
- Modify: `docs/design/workflow_lisp_provider_live_binding.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_executable_ir.md`
- Modify: `docs/design/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/workflow_monitoring.md`
- Modify: `docs/capability_status_matrix.md`
- Modify only peer-owned hunks: `docs/index.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-23-provider-live-binding-implementation-plan.md`
- Modify: this plan
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [ ] **Step 1: Update normative and authoring contracts**

Document only implemented behavior: capability/config schema, endpoint/client
surface, ledger claims, lifecycle/cleanup, state/report evidence, target
2.17, node version, authoring rules, and exclusions. Mark the accepted design
implemented and this plan complete only after fresh checks.

- [ ] **Step 2: Update routing and Stage 7 status**

Close Gate S7-v1.1, preserve Gate S7-v1 history, select Stage 8 next, and
leave the parked evolution roadmap/effectiveness experiments non-selectable.
Retain only the two explicitly salvaged post-Stage-8 items.

- [ ] **Step 3: Run docs/routing and focused gates**

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
pytest -q \
  tests/test_provider_interactive_terminal.py \
  tests/test_provider_peer_group_contracts.py \
  tests/test_provider_peer_group_protocol.py \
  tests/test_provider_peer_group_ir.py \
  tests/test_provider_peer_group_runtime.py \
  tests/test_provider_peer_group_resume.py \
  tests/test_workflow_lisp_provider_peer_group.py \
  tests/test_workflow_lisp_provider_peer_group_e2e.py \
  tests/test_provider_supervision_ir.py \
  tests/test_provider_supervision_runtime.py \
  tests/test_provider_supervision_resume.py \
  tests/test_workflow_lisp_provider_supervision.py \
  tests/test_workflow_lisp_provider_supervision_e2e.py
```

Expected: all pass.

- [ ] **Step 4: Run the broad non-security suite in tmux**

Build an explicit collection manifest excluding the three named security
modules, then run:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_secrets.py \
  -k 'not security and not secret and not isolation'
```

Compare against the last Stage-7 v1 baseline: `6,978` passed, `17` skipped,
and only the four exact retained Stage-6 failures. Any new failure must be
fixed or truthfully classified before closure; never weaken a test.

- [ ] **Step 5: Run real smoke and compatibility checks again**

```bash
ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
  tests/e2e/test_e2e_provider_supervision.py \
  tests/e2e/test_e2e_provider_peer_delivery.py
pytest -q tests/test_workflow_lisp_provider_supervision_e2e.py \
  -k target_2_16_artifact
git diff --check
```

Expected: all pass and v1 digests are unchanged.

- [ ] **Step 6: Obtain final ordered independent reviews**

The specification reviewer must compare the complete implementation and
fresh verification against every Gate S7-v1.1 bullet and the accepted
design's success/stop criteria. Only after specification approval may a
separate quality reviewer inspect maintainability, genericity, lifecycle
ordering, failure cleanup, and v1 non-regression. Security review remains
excluded.

- [ ] **Step 7: Stage only owned hunks and commit**

Use `git add -p docs/index.md` so the parked-roadmap owner hunk remains
unstaged.

Commit message: `Complete Stage 7 provider peer messaging`.

- [ ] **Step 8: Continue without confirmation**

Proceed immediately to the Stage 8 `.orc` language-server reviewed-plan gate.
Do not execute or evidence against the parked evolution roadmap or its
effectiveness experiment plans.

## Completion Gate

Gate S7-v1.1 closes only when:

- all twelve tasks are committed after their ordered reviews;
- target-2.16 v1 artifact digests remain unchanged;
- real one-member delivery, two-member messaging, and three-member `.orc`
  gates pass without forcing input;
- sender/receiver attribution, record-before-offer, ack, finish, natural
  close, races, failure cleanup, and quarantine have both-direction coverage;
- target-2.17 `2..8` typing/effects/WCC/projections/runtime behavior matches
  the accepted design;
- no peer path can cancel, resume, steer, settle, or directly publish a
  member;
- focused and broad non-security suites introduce no new failures; and
- the final independent specification and quality reviews approve the exact
  committed implementation.
