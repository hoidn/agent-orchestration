# Workflow Lisp Phased Contract Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every production change. Every
> production task receives an independent specification-compliance review
> followed by a distinct implementation-quality review before its exact
> candidate is committed. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement target-2.23 explicit phased contract delivery for a
fragment-backed `provider-result`: one canonical prompt is cut into a task
turn and a contract/materialization turn inside one interactive provider
attempt, with bounded materialization-only correction and no early result or
artifact authority.

**Architecture:** First land and prove the design's generic deadline-aware
interactive-adapter prerequisite without implementing any Q5 coordinator.
Then build Q5's pure contracts and complete runtime machinery behind directly
constructed immutable policy/configuration values: diagnostics and policy
partitioning, canonical cuts and frames, identity/evidence, the current Q3
report owner, ledger, endpoint, and the complete
`PhasedProviderAttemptCoordinator`. Only after that machinery is reviewed and
committed does one atomic public-activation task add target-2.23 syntax,
compiler/IR/persistence carriage, `RuntimeStep`, provider-executor
partitioning, capability admission, and the sole explicit-phased runtime
route. This ordering prevents any public `.orc` phased surface from existing
while its runtime is incomplete. Existing Q3 identity/evidence is extended to
identity v2/functional v3; report v2 remains read-only and non-authoritative.

**Tech Stack:** Python 3.11+, immutable dataclasses, canonical JSON/JSONL and
SHA-256, Workflow Lisp targets 2.20–2.23, classic and WCC lowering,
Surface/Core/Semantic/Executable IR, state schema 2.1, the target-2.17
`InteractiveTerminalTurnQueueAdapter`, local attempt-bound IPC, pytest with
pytest-xdist, tmux, and the existing real-provider E2E harness.

---

## Accepted Authority And Plan Status

The fixed implementation authority is:

- baseline commit
  `872a29af13f140d53b3637b475859496a50d5724`, tree
  `332b5e339cbc90d0028625f1d88442f498288682`;
- `docs/design/workflow_lisp_phased_contract_delivery.md` at that commit,
  SHA-256
  `7a571e2d02aae321271857c134ac1ca0ffe681e8122b195cc622ee7590cc9459`;
- the target-2.17 substrate boundary in
  `docs/design/workflow_lisp_provider_prompt_queue.md` at that commit,
  SHA-256
  `f934aa6d4524f5546c3abe1b9c2899b58bd25d3c730f7e76c7ef526b2a061b34`;
- principles 28, 29, and 30 in
  `docs/design/workflow_language_design_principles.md`; and
- Stage Q5 in
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`.

This is a proposed implementation plan. It does not authorize production,
test, fixture, workflow, specification, or routing changes. Before any
pre-Q5 prerequisite or Q5 task executes, this exact plan must receive:

1. independent `Q5_PLAN_SPEC_APPROVED`;
2. then a distinct `Q5_PLAN_QUALITY_APPROVED`; and
3. a commit of the exact reviewed bytes with no post-review edits.

Any plan-byte change after either approval restarts ordered plan specification
then quality review. If this plan conflicts with the accepted design, revise
the plan and repeat those reviews; do not reinterpret the design in code.

## Actual Prerequisite Audit At The Bound Baseline

The baseline contains the Q3 implementation substrate Q5 needs:

- target-2.22 `CompilerPromptAttemptBindingPlan`;
- `PromptFragmentRenderResult` and the one-render trace;
- separator-inclusive runtime-contribution composition;
- prepared provider-policy projection;
- five-role attempt identity v1 and functional evidence v2;
- content-addressed attempt evidence publication; and
- strict pure comparison helpers.

Q5 does **not** depend on the separately planned Q3 Task 6 report module. That
module is absent at this baseline, but it may land independently before Q5
Task 4. Task 4 must audit its current parent: if Q3 report v1 is present, Q5
extends that single pure projection owner to v2 while preserving every v1
qualification/state-only invariant; if it is absent, Q5 creates the same owner
directly. Q5 neither waits for Q3 Task 6 nor creates a parallel report module.

One required prerequisite is genuinely absent:

- `InteractiveTerminalTurnQueueAdapter.start`, `offer`, and `offer_close`
  still allocate independent operation deadlines;
- `start` still returns a handle or throws;
- `InteractiveTerminalStartOutcome`, `NoBackendAllocationProof`, and
  handle-free `PhasedFailedCleanupEvidence` do not exist; and
- the target-2.17 peer coordinator does not pass its already-owned absolute
  deadline to those three operations.

Therefore this plan may be reviewed, but Q5 Task 1 is blocked until
Prerequisite Gates P0–P2 below land and pass their own ordered reviews. The
gap must not be hidden with a Q5-local wrapper, a fake adapter, inferred
no-allocation from a missing handle, or per-operation relative timeouts.

The accepted design originally required this proof before implementation
planning. This plan is drafted now only under the explicit owner direction to
make the prerequisite the first executable gate. Plan approval does not waive
the prerequisite.

The durable owner override is the 2026-07-26 session direction, quoted
verbatim: “Route it through independent design review (spec then quality, per
the roadmap's required order) … Do not begin Q5 planning before the design
review verdict.” The accepted design commit
`872a29af13f140d53b3637b475859496a50d5724` is that verdict. The direction
therefore authorizes this implementation plan, including P0–P2 as its first
executable gates, despite the design's earlier preplanning-feasibility
wording; it does not waive any feasibility, review, or implementation gate.

## Deliberate Cost

The implementation adds a distinct single-attempt coordinator, exact policy
carriage, two evidence schema versions, a closed JSONL ledger, and an
attempt-bound submit endpoint instead of teaching the ordinary composed
executor to guess when phasing is possible. This makes a third semantic phase,
another transport schema, broader candidate set, dynamic attempt cap, or
ledger recovery require a reviewed contract change. The cost is intentional:
the composed path remains simple and byte-compatible, while the phased path's
transport, authority, and failure boundaries stay inspectable.

## Scope And Load-Bearing Constraints

This plan implements only:

- target-2.23 explicit `:delivery :phased|:composed`;
- literal phased `:materialization-attempts` in `1..3`, defaulting to `2`;
- fragment-backed `provider-result` with a non-empty generated result-contract
  suffix;
- exact `interactive_terminal_turn_queue.v1` capability admission;
- the derived `T1 || T2 == C` cut at the existing output-contract suffix
  owner;
- versioned runtime protocol frames outside `C`;
- one interactive provider process and one whole-attempt deadline;
- complete Q2 validation on every submitted candidate;
- materialization-only retry in the same client, never a second task turn;
- frozen candidate restoration/verification and one authoritative state
  commit after natural join;
- identity v2, functional evidence v3, report v2, a content-free phase ledger,
  and offline ledger validation;
- sticky quarantine of interrupted nonterminal phased visits; and
- the motivating `review_revise_design_docs.orc` consumer.

The following constraints are load-bearing:

1. Omitted delivery preserves pre-Q5 compiler, IR, persisted, prompt,
   invocation, Q3 identity-v1/functional-v2, result, checkpoint, and
   completed-boundary behavior byte-for-byte.
2. Explicit composed delivery uses the ordinary composed transport. It does
   not construct the Q5 coordinator.
3. Explicit phased delivery never falls back to composed delivery after a
   target, policy, capability, carriage, deadline, or preparation refusal.
4. `T1` and `T2` are slices from one canonical composition operation:
   `T1=P`, `T2=S`, and `T1 || T2 == C` byte-for-byte.
5. Protocol frames are outside `C`; tests compare byte algorithms and digests,
   never literal production prompt prose.
6. One provider-attempt ordinal, one provider process, and one task delivery
   serve the entire initial/retry materialization sequence.
7. Every submit runs both Q2 validators in output-position then structured-
   result order. Neither local mapping becomes authoritative early.
8. Retry clears only preflight-absent exact bound regular candidate files and
   proves them absent before offering unchanged `T2` again.
9. A successful natural-shutdown proof moves in-memory lifecycle to
   `JOINED_PENDING_COMMIT` before the `join_succeeded` ledger write.
10. No post-proof path calls `abort`, emits cleanup again, or treats a ledger
    row as result authority.
11. T0–T4 are a closed terminalization grammar. T2a records pending cleanup
    once; T2b never records it again. An allocated ingress has at most one
    start and one finished-or-failed outcome.
12. `provider_cleanup_proof` is exactly
    `null|NoBackendAllocationProof|PhasedFailedCleanupEvidence`; the existing
    handle-bound `FailedCleanupProof` is validated against the active handle
    and projected, never persisted raw.
13. Before successful provider start, binding and endpoint-locator values are
    inert and reserve no endpoint resource. Actual address binding begins
    strictly after start.
14. The ledger is provenance only. Runtime publication, resume, retry, and
    settlement never parse it.
15. Identity v2 distinguishes canonical `C` from successful ordered
    deliveries. No field calls `C` a delivered `final_prompt`.
16. Report v2 strictly validates source evidence, compares only same-version
    identities, and remains read-only.
17. Interrupted nonterminal phased visits are sticky-failed and cannot be
    ordinarily resumed. Completed compatible results reuse without reading
    the phase ledger.
18. Q5 has no Q4 dependency and no dependency on a Q3 Task 6 report
    implementation.
19. No workflow, provider, family, module, or prompt name selects Q5 behavior.
20. Tests assert behavioral, contract, artifact-lineage, lifecycle, and
    dataflow properties, not literal prompt wording.
21. Tasks 1–10 expose no authored syntax, compiler carrier, persisted field,
    `RuntimeStep` field, provider-executor route, workflow-executor route, or
    runtime capability admission. They accept only directly constructed
    immutable internal policy/configuration values in tests.
22. Task 11 is one atomic activation boundary: no reviewed commit may contain
    only part of the public compiler-to-runtime route.

## Explicitly Excluded Scope

Do not add a YAML surface, authored prompt queue, peer-group reuse, same-turn
steering, a third phase, dynamic attempt caps, provider-native duplex
transport, new result channel, tolerant boundary normalization, mid-attempt
resume, or ledger-driven recovery.

Security, safety, secrets, and provider-isolation production modules, test
modules, specifications, documentation, configuration admission, and
diagnostics are outside this owner-directed execution. Do not inspect, edit,
stage, run, or implement them as Q5 authority. This tranche makes no support
claim for isolated-provider configurations and does not implement or test the
accepted design's `provider_phased_isolation_unsupported` row; that row remains
explicitly deferred rather than being inferred from existing configuration.

`specs/io.md` remains unchanged. No isolation brokerage or candidate
visibility claim is added.

## Governing Authorities

Read before execution:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_language_design_principles.md`, principles 27–30;
- `docs/design/workflow_lisp_prompt_calculus.md`;
- `docs/design/workflow_lisp_prompt_identity_diagnostics.md`;
- `docs/design/workflow_lisp_phased_contract_delivery.md`;
- `docs/design/workflow_lisp_provider_peer_messaging.md`;
- `docs/design/workflow_lisp_provider_prompt_queue.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_semantic_workflow_ir.md`;
- `docs/design/workflow_lisp_executable_ir.md`;
- the active Q/L roadmap;
- the accepted Q1, Q2, Q3, and target-2.17 peer implementation plans;
- `specs/dsl.md`;
- `specs/providers.md`;
- `specs/state.md`; and
- `specs/versioning.md`.

The provider-prompt-queue proposal is context for the already-landed
target-2.17 turn-queue substrate only. It is not selected by Q5 and does not
authorize `prompt-queue`.

## File And Responsibility Map

Generic adapter prerequisite:

- Modify `orchestrator/providers/interactive_terminal.py`
- Modify `orchestrator/workflow/provider_peer_group/bindings.py`
- Modify `orchestrator/workflow/provider_peer_group/coordinator.py`
- Modify `tests/test_provider_interactive_terminal.py`
- Modify `tests/test_provider_peer_group_contracts.py`
- Modify `tests/test_provider_peer_group_runtime.py`
- Modify `tests/test_workflow_lisp_provider_peer_group_e2e.py`
- Modify `tests/e2e/test_e2e_provider_peer_delivery.py`

Internal models, diagnostics, and policy partition:

- Create `orchestrator/workflow/provider_phased_delivery/__init__.py`
- Create `orchestrator/workflow/provider_phased_delivery/models.py`
- Create `orchestrator/workflow/provider_phased_delivery/diagnostics.py`
- Create `tests/test_provider_phased_delivery_contracts.py`
- Create `tests/test_provider_phased_delivery_diagnostics.py`
- Create `tests/test_provider_phased_delivery_policy.py`

Canonical cut and frames:

- Modify `orchestrator/workflow/prompting.py`
- Create `orchestrator/workflow/provider_phased_delivery/frames.py`
- Modify `tests/test_prompt_contract_injection.py`

Identity, evidence, and current-Q3-aware internal report support:

- Modify `orchestrator/workflow/prompt_identity.py`
- Modify `orchestrator/workflow/prompt_dependency_evidence.py`
- Create or modify `orchestrator/workflow/prompt_context_report.py`
- Create `tests/test_provider_phased_delivery_identity.py`
- Create or modify `tests/test_prompt_context_report.py`

Ledger encoding, writer, manifests, and offline validator:

- Create `orchestrator/workflow/provider_phased_delivery/ledger.py`
- Create `tests/test_provider_prompt_phase_ledger.py`

Submit protocol and endpoint:

- Create `orchestrator/workflow/provider_phased_delivery/protocol.py`
- Create `orchestrator/workflow/provider_phased_delivery/endpoint.py`
- Create `orchestrator/cli/commands/provider_materialization.py`
- Modify `orchestrator/cli/commands/__init__.py`
- Modify `orchestrator/cli/main.py`
- Create `tests/test_provider_materialization_protocol.py`
- Create `tests/test_cli_provider_materialization.py`

Internal coordinator core, terminalization, races, and deadlines:

- Create `orchestrator/workflow/provider_phased_delivery/bindings.py`
- Create `orchestrator/workflow/provider_phased_delivery/coordinator.py`
- Create `tests/test_provider_phased_delivery_coordinator.py`

Atomic target-2.23 public activation:

- Modify `orchestrator/workflow_lisp/syntax.py`
- Modify `orchestrator/workflow_lisp/prompts.py`
- Modify `orchestrator/workflow_lisp/expressions.py`
- Modify `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify `orchestrator/workflow_lisp/lowering/effects.py`
- Modify `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify `orchestrator/workflow/prompt_fragment_contract.py`
- Modify `orchestrator/workflow/surface_ast.py`
- Modify `orchestrator/workflow/core_ast.py`
- Modify `orchestrator/workflow/semantic_ir.py`
- Modify `orchestrator/workflow/executable_ir.py`
- Modify `orchestrator/workflow/elaboration.py`
- Modify `orchestrator/workflow/lowering.py`
- Modify `orchestrator/workflow/validation.py`
- Modify `orchestrator/workflow/persisted_surface.py`
- Modify `orchestrator/workflow/runtime_step.py`
- Modify `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify `orchestrator/providers/types.py`
- Modify `orchestrator/providers/executor.py`
- Modify `orchestrator/workflow/executor.py`
- Modify `orchestrator/observability/report.py`
- Modify `orchestrator/cli/commands/report.py`
- Create `tests/test_workflow_lisp_phased_delivery_carriage.py`
- Create `tests/test_workflow_lisp_phased_delivery_persistence.py`
- Create `tests/test_workflow_lisp_phased_delivery_runtime.py`
- Modify `tests/test_workflow_lisp_provider_call_policy.py`
- Modify `tests/test_observability_report.py`
- Modify `tests/test_cli_report_command.py`

Integration, compatibility, and real consumer:

- Create `tests/fixtures/workflow_lisp/phased_contract_delivery/`
- Create `tests/test_workflow_lisp_phased_delivery_e2e.py`
- Modify `tests/test_workflow_lisp_provider_call_policy_e2e.py`
- Create `tests/e2e/test_e2e_provider_phased_contract_delivery.py`
- Modify `workflows/examples/review_revise_design_docs.orc`
- Modify only its existing provider/prompt fixture inputs when the E2E requires
  that exact change.

Normative, authoring, capability, and routing closure:

- Modify `specs/dsl.md`
- Modify `specs/providers.md`
- Modify `specs/state.md`
- Modify `specs/versioning.md`
- Modify `specs/index.md`
- Modify `docs/design/workflow_lisp_frontend_specification.md`
- Modify `docs/design/workflow_lisp_prompt_identity_diagnostics.md`
- Modify `docs/design/workflow_lisp_phased_contract_delivery.md`
- Modify `docs/design/README.md`
- Modify `docs/lisp_workflow_drafting_guide.md`
- Modify `docs/capability_status_matrix.md`
- Modify `docs/index.md`
- Modify the active Q/L roadmap
- Modify `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify this implementation plan with factual closure evidence only.

Do not create a generic “provider lifecycle framework.” The new package is
specific to the accepted phased-delivery contract while remaining free of
workflow/provider/family names.

## Execution And Review Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every user and external change. Execute
tasks in order and do not dispatch two Q5 implementers against shared files.
For every production task:

1. dispatch a fresh implementer with the complete task and accepted design;
2. write the smallest behavioral/contract test first;
3. run it and prove RED for the intended missing behavior, not collection,
   syntax, fixture, or unrelated dirty-tree failure;
4. implement only the selected task;
5. run its exact narrow selector GREEN, then its named adjacent regressions;
6. run `pytest --collect-only -q` for every new or renamed test module;
7. capture current `HEAD`, tree, and exact task-owned path hashes;
8. construct an isolated exact-path/hunk candidate;
9. run `git diff --check`, inspect every candidate path, and read the complete
   diff;
10. obtain an independent task specification review;
11. fix every finding and repeat specification review until approved;
12. obtain a distinct task quality review only after specification approval;
13. if any byte changes, restart ordered task specification then quality
    review;
14. commit exactly the reviewed bytes with no post-review edits; and
15. rerun the task selector from the committed tree.

Pure characterization/integration gates that begin GREEN do not patch
production. A RED in such a gate routes back to the owning production task
for a fresh RED/GREEN cycle and both ordered reviews.

Use the `tmux` skill for commands expected to exceed one minute, the real
provider gates, and broad pytest. Wait for the configured review
provider/model; do not substitute a faster model.

## Concurrent-Edit And Collision Contract

At plan drafting, the shared tree already contains concurrent changes in Q5
adjacent paths, including:

```text
orchestrator/providers/executor.py
orchestrator/providers/types.py
orchestrator/workflow/executor.py
orchestrator/workflow_lisp/expressions.py
orchestrator/workflow_lisp/typecheck_effects.py
orchestrator/workflow_lisp/wcc/elaborate.py
orchestrator/workflow_lisp/wcc/defunctionalize.py
orchestrator/workflow/prompt_dependency_evidence.py
orchestrator/workflow/prompt_identity.py
tests/test_prompt_dependency_evidence.py
tests/test_prompt_identity.py
tests/test_provider_attempt_allocation.py
tests/test_workflow_lisp_prompt_identity_carriage.py
tests/test_workflow_lisp_prompt_identity_persistence.py
tests/test_workflow_lisp_prompt_identity_render_trace.py
tests/test_workflow_lisp_prompt_identity_runtime.py
tests/test_workflow_lisp_provider_call_policy.py
tests/test_workflow_lisp_provider_call_policy_e2e.py
docs/capability_status_matrix.md
docs/design/README.md
docs/design/workflow_lisp_phased_contract_delivery.md
docs/design/workflow_lisp_provider_prompt_queue.md
docs/index.md
the active Q/L roadmap
tests/test_workflow_lisp_drain_roadmap_routing.py
```

Before first touching any path, capture:

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse HEAD:<path>
git hash-object <path>
git diff --binary HEAD -- <path>
git diff --stat HEAD -- <path>
```

Store one path-specific baseline patch outside the repository. Reconcile
function/section ownership against the current working blob. If Q5 and ambient
work touch the same function or documentation paragraph, merge the complete
current function/paragraph deliberately; never replay a stale whole-file
patch. Stage with an alternate index or edited patches and prove all ambient
hunks remain unstaged.

Repeat the audit when `HEAD` changes, a path hash changes unexpectedly, or an
external commit lands before commit. Rerun the task tests and both ordered
reviews after reconciliation. Never use `git add .`, `git add -A`, destructive
checkout/reset, or whole-file staging of a shared dirty path.

The commit candidate must name its expected parent and exact tree. If the
parent moves, reconstruct the candidate on the new parent, rerun tests, and
repeat both reviews. Do not silently absorb unrelated commits.

## Preimplementation Plan-Acceptance Gate

- [ ] Review this exact plan for specification compliance against the accepted
  Q5 design and record `Q5_PLAN_SPEC_APPROVED`.
- [ ] Review the same bytes for implementation quality, task sizing,
  ownership, collision safety, and executable selectors; record
  `Q5_PLAN_QUALITY_APPROVED`.
- [ ] Commit the exact approved plan bytes.
- [ ] Update only the Q5 plan-routing rows to say “reviewed plan; prerequisite
  gates next; implementation not started.” Review and commit those routing
  bytes in the same specification-then-quality order.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'language_quality or phased_contract or prompt_calculus'
  ```

- [ ] Bind the post-routing `HEAD` and tree for Prerequisite Gate P0.

No following command is authorized until this gate closes.

## Prerequisite Gate P0: Adapter-Only Characterization And Gap Proof

**Files:** Inspect only; do not modify or commit.

- `orchestrator/providers/interactive_terminal.py`
- `orchestrator/workflow/provider_peer_group/bindings.py`
- `orchestrator/workflow/provider_peer_group/coordinator.py`
- their existing test modules listed in the responsibility map.

- [ ] **Step 1: Freeze current target-2.17 behavior.**
  Record current public signatures, `InteractiveMemberHandle`,
  `OfferReceipt`, `CloseOfferReceipt`, `NaturalShutdownProof`,
  handle-bound `FailedCleanupProof`, the peer adapter protocol, and every
  peer coordinator call site.
- [ ] **Step 2: Run the current adapter and peer controls.**

  ```bash
  pytest -q \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_contracts.py \
    tests/test_provider_peer_group_runtime.py \
    tests/test_workflow_lisp_provider_peer_group_e2e.py
  ```

- [ ] **Step 3: Prove the exact gap without patching.**
  Verify that `start`, `offer`, and `offer_close` lack caller deadlines;
  `start` returns a handle or raises; and the three closed failed-start
  outcomes/proofs are absent. Verify Q5 coordinator, submit endpoint,
  candidate reset, and identity-v2 are also absent from this characterization.
- [ ] **Step 4: Obtain one independent specification review of the
  characterization record.**
  The reviewer must confirm it proves a prerequisite gap rather than claiming
  Q5 behavior. Write the minimal record to
  `/home/ollie/.tmp/q5-p0-adapter-prerequisite-characterization.md`, bind its
  SHA-256 in this plan's later factual closure section, and keep it outside the
  repository. No quality review is needed because P0 changes no repository
  bytes.

**P0 completion gate:** Current target-2.17 behavior is freshly green, the
missing deadline/closed-start surface is precisely demonstrated, and no Q5
implementation exists or is claimed.

## Prerequisite Gate P1: Deadline-Aware Adapter And Closed Start Outcome

**Files:**

- Modify `orchestrator/providers/interactive_terminal.py`
- Modify `orchestrator/workflow/provider_peer_group/bindings.py`
- Modify `orchestrator/workflow/provider_peer_group/coordinator.py`
- Modify `tests/test_provider_interactive_terminal.py`
- Modify `tests/test_provider_peer_group_contracts.py`
- Modify `tests/test_provider_peer_group_runtime.py`
- Modify `tests/test_workflow_lisp_provider_peer_group_e2e.py`

- [ ] **Step 1: Write adapter contract RED tests.**
  Require:

  ```text
  start(invocation, *, deadline) -> InteractiveTerminalStartOutcome
  offer(handle, literal_message, *, deadline) -> OfferReceipt
  offer_close(handle, *, deadline) -> CloseOfferReceipt
  join(handle, deadline) -> NaturalShutdownProof
  abort(handle, deadline) -> FailedCleanupProof
  ```

  Require one finite absolute monotonic deadline and
  `min(operation_timeout, deadline-now)` at every backend action.
- [ ] **Step 2: Write closed-start RED matrices.**
  Cover exact success plus:

  1. `none/not_required/true/NoBackendAllocationProof`;
  2. `possible_or_allocated/completed/true/PhasedFailedCleanupEvidence`; and
  3. `possible_or_allocated/incomplete/false/PhasedFailedCleanupEvidence`.

  Missing handle alone must prove nothing. No failure may escape as an
  exception. The production
  `interactive_terminal_start_cleanup_incomplete` path must select case 3.
  Failed start never returns handle-bound `FailedCleanupProof`.
- [ ] **Step 3: Write the pure active-handle projection RED matrix.**
  Add one side-effect-free
  `project_phased_failed_cleanup_evidence(proof, *, active_handle_id)` boundary
  beside the adapter proof types. An exact existing `FailedCleanupProof` whose
  `handle_id` equals the supplied active handle projects only its five
  handle-free fields. Wrong type, extra/missing/malformed field, unknown error
  token, or missing/mismatched handle identity fails closed and returns no
  projection. The function writes no ledger and knows no coordinator state.
- [ ] **Step 4: Write deadline RED matrices.**
  Before-expiry cases start zero backend actions and return/raise the exact
  `start_timeout`, `offer_timeout`, or `close_offer_timeout` surface. During-
  operation expiry starts no later backend action, uses no fresh cleanup
  budget, and leaves no helper/waiter alive past the supplied deadline.
- [ ] **Step 5: Write target-2.17 compatibility RED tests.**
  Migrate the peer protocol/coordinator to pass its already-owned deadline.
  Prove unchanged launch, offer, close, join, abort, settlement, cleanup,
  ledger, and evidence semantics. `abort` still returns the exact existing
  handle-bound `FailedCleanupProof`.
- [ ] **Step 6: Prove RED.**

  ```bash
  pytest -q \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_contracts.py \
    tests/test_provider_peer_group_runtime.py \
    -k 'deadline or start_outcome or cleanup_proof or offer or close'
  ```

- [ ] **Step 7: Implement the minimum generic adapter extension.**
  Add immutable exact proof/outcome types, validate their closed field
  combinations, use the caller deadline in every selected backend operation,
  and convert every start failure to one closed outcome. Do not add a Q5
  coordinator, endpoint, ledger, candidate path, or workflow-specific branch.
- [ ] **Step 8: Run GREEN and complete target-2.17 regressions.**

  ```bash
  pytest -q \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_contracts.py \
    tests/test_provider_peer_group_runtime.py \
    tests/test_workflow_lisp_provider_peer_group.py \
    tests/test_workflow_lisp_provider_peer_group_e2e.py
  ```

- [ ] **Step 9: Review and commit.**
  Obtain `Q5_P1_SPEC_APPROVED`, then distinct
  `Q5_P1_QUALITY_APPROVED`; commit only the exact prerequisite paths and rerun
  the selector.

**P1 completion gate:** The generic adapter exposes the exact deadline-aware
surface and closed start union; every before/during timeout and failed-start
combination is executable; target-2.17 behavior and handle-bound abort proof
are unchanged; and no Q5 coordinator exists.

## Prerequisite Gate P2: Production-Adapter Feasibility Proof

**Files:**

- Modify `tests/e2e/test_e2e_provider_peer_delivery.py`

- [ ] **Step 1: Add an adapter-only real-provider gate.**
  Through the production adapter and exact structural capability, prove one
  successful start with exactly one counted task action, two distinct literal
  offers at successive natural turn boundaries in the same client, normal
  close/join, a remainder smaller than configured operation timeout, and zero
  live backend/helper operations at the deadline. Assert the proof uses no
  peer coordinator or peer command, cancellation or session resume, pane-text
  interpretation, or second provider process.
- [ ] **Step 2: Exercise all three failed-start fixtures through the production
  adapter.**
  Assert the exact proof combinations, zero exception escape, and zero
  handle-bound proof on failure. Separately show a valid post-start
  `FailedCleanupProof` remains handle-bound and that a missing/mismatched
  handle identity cannot later be projected as evidence.
- [ ] **Step 3: Run deterministic and real gates in tmux.**

  ```bash
  pytest -q \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_runtime.py \
    -k 'deadline or start_outcome or two_successive_offers'
  ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
    tests/e2e/test_e2e_provider_peer_delivery.py \
    -k 'phased_adapter_feasibility or real_adapter'
  ```

- [ ] **Step 4: Review the evidence and commit the E2E-only delta.**
  Obtain `Q5_P2_SPEC_APPROVED`, then distinct
  `Q5_P2_QUALITY_APPROVED`; commit the exact test delta.

**P2 completion gate:** The production adapter, not a fake, proves the exact
same-client/deadline/closed-start prerequisite and no test implements or claims
the Q5 coordinator. Any failure stops Q5 Task 1 and returns the accepted design
for revision.

## Post-Prerequisite Q5 Control Baseline

After P2 commits and before Task 1:

- [ ] Bind the exact P2 `HEAD`, tree, full dirty inventory, and all prospective
  Q5 path hashes.
- [ ] Run the exact broad non-security collection and suite commands named in
  Task 14 in tmux.
- [ ] Preserve collected node IDs, totals, failing node IDs, skipped node IDs,
  and logs outside the repository as the pre-Q5 comparison baseline.
- [ ] Classify existing non-passes without fixing unrelated or excluded work.
- [ ] Obtain one independent specification review that the baseline is
  reproducible and post-prerequisite. This is an evidence gate with no
  production or test edits and therefore needs no quality review.

Task 1 may start only from this bound post-prerequisite baseline. A later
external commit requires a fresh collision audit, not automatic recapture of a
new broad baseline; explain the lineage delta at final comparison.

## Task 1: Pure Models, Closed Diagnostics, And Policy Partition

**Files:** Create package `provider_phased_delivery` files `__init__.py`,
`models.py`, and `diagnostics.py`; create
`tests/test_provider_phased_delivery_contracts.py`,
`tests/test_provider_phased_delivery_diagnostics.py`, and
`tests/test_provider_phased_delivery_policy.py`.

- [ ] Write RED immutable-model tests for directly constructed internal phased
  policy/configuration, composition projections, turn rows, receipts,
  manifests, lifecycle state, and the exact P1 cleanup/start proof union.
  Reject missing/extra fields, Boolean integers, malformed digests, illegal
  ordinals, and impossible union combinations.
- [ ] Before any Q5 refusal producer exists, generate RED totality/bijection
  cases for the accepted static/reason/deadline registry minus exactly
  `provider_phased_isolation_unsupported` /
  `isolation_required_unsupported`, which the owner deferred. Require one
  code, reason, value/source profile, precedence position, and non-null
  `summary == reason`. Add no isolation producer, test, or normative claim.
- [ ] Write RED tests for
  `partition_provider_call_policy(policy)`, returning the pair
  `(provider_bound_policy, phased_runtime_policy)`. Only `model` and `effort`
  are provider-bound strings; only `delivery` and integer
  `materialization_attempts` are runtime-consumed. Reject unknown keys, wrong
  scalar types, Boolean integers, illegal pairing, and range violations. Use
  only generic closed-key negatives.
- [ ] Prove RED, implement only pure immutable foundations, then run:

  ```bash
  pytest --collect-only -q \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_diagnostics.py \
    tests/test_provider_phased_delivery_policy.py
  pytest -q \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_diagnostics.py \
    tests/test_provider_phased_delivery_policy.py
  ```

- [ ] Obtain ordered `Q5_TASK1_SPEC_APPROVED` then
  `Q5_TASK1_QUALITY_APPROVED`; commit only these files.

**Gate:** Every later refusal producer imports a pre-existing total registry;
policy ownership is exact; no compiler, persistence, provider executor,
workflow executor, endpoint, ledger I/O, or public `.orc` phased surface
exists.

## Task 2: Derived Canonical Cut And Protocol Frames

**Files:** Modify `orchestrator/workflow/prompting.py`; create
`provider_phased_delivery/frames.py`; modify Task-1 contract tests and
`tests/test_prompt_contract_injection.py`.

- [ ] Write RED vectors for empty/non-empty `P`, LF boundaries, Q1/Q2,
  guidance variants, and consumed-artifact variants. Require strict UTF-8
  `task_slice`, `materialization_slice`, and `canonical_composed`, with
  `T1=P`, `T2=S`, and `T1 || T2 == C`.
- [ ] Count every contract render once and freeze
  `apply_output_contract_prompt_suffix`; ordinary composition gets no Q5
  frame.
- [ ] Write RED frame vectors for exact frame bytes, slice bytes, delivered
  bytes, counts, and SHA-256 for task, initial materialization, and retry.
  Retry contains bounded named diagnostics and unchanged `T2`; frames never
  enter `C`.
- [ ] Implement pure cut/frame functions accepting directly constructed
  Task-1 models; run:

  ```bash
  pytest -q \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_diagnostics.py \
    tests/test_prompt_contract_injection.py
  ```

- [ ] Obtain ordered `Q5_TASK2_SPEC_APPROVED` then
  `Q5_TASK2_QUALITY_APPROVED`; commit.

**Gate:** The cut has one existing owner, deliveries are byte-accounted,
composed bytes are frozen, and no public phased surface exists.

## Task 3: Attempt Identity V2 And Functional Evidence V3

**Files:** Modify `prompt_identity.py` and
`prompt_dependency_evidence.py`; create
`tests/test_provider_phased_delivery_identity.py`; modify their existing test
modules.

- [ ] Write RED provider-policy-v2 tests for exact Q3 fields plus structural
  transport/phased policy and generic rejection of every undeclared key.
- [ ] Write RED identity-v2 vectors for five roles, canonical composition,
  ordered contiguous actual deliveries, canonical task-row empty-key digest,
  initial/retry ordinals, byte equations, and seal. Failed requested turns are
  not actual deliveries.
- [ ] Write RED functional-v3 cross-field tests: exact keys, no
  `final_prompt`, canonical/identity equality, Q1/Q2 identity, Q3 binding
  correspondence, actual deliveries, and seal. Reseal mutations.
- [ ] Prove compatibility: composed 2.22/2.23 remains identity-v1/
  functional-v2; 2.20/2.21 remains functional-v1; mixed versions fail; v3
  reuses the allocator/immutable-write owner and never reads the ledger.
  Preserve Q3 comparisons, adding only `actual_delivery_drift`; cross-version
  comparison is unavailable as `identity_version_mismatch`.
- [ ] Prove RED, implement version-dispatched pure owners, and run:

  ```bash
  pytest --collect-only -q tests/test_provider_phased_delivery_identity.py
  pytest -q \
    tests/test_provider_phased_delivery_identity.py \
    tests/test_prompt_identity.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py
  ```

- [ ] Obtain ordered `Q5_TASK3_SPEC_APPROVED` then
  `Q5_TASK3_QUALITY_APPROVED`; commit.

**Gate:** Identity/evidence distinguish canonical composition from actual
delivery, version pairing fails closed, and no public runtime route exists.

## Task 4: Internal Prompt-Context Report V2 Support On The Current Q3 Owner

**Files:** Create or modify the single `prompt_context_report.py` and its
direct pure-projection tests only. Do not modify observability or CLI report
selection in this task.

- [ ] Audit the current parent. If Q3 report v1 landed, extend that exact owner
  with all v1 qualification/state-only invariants; otherwise create the same
  pure owner against Q3 validators/allocator. Never create a parallel module.
- [ ] Through directly constructed immutable evidence and direct calls to the
  pure projector, write RED report-v2 exact-key, v1/v2 mutually exclusive
  projection, functional-v1/v2/v3 qualification, snapshot/failure/
  allocation-only/invalid, predecessor, version/drift/composition, and
  unchanged cases. Through Task 10, preserve the current external report
  baseline byte-for-byte: if Q3 public report-v1 exists, it remains v1; if it
  is absent, prompt-context reporting remains absent.
- [ ] Prove execution/resume imports neither report nor report validation;
  missing evidence changes report status only.
- [ ] Implement one content-free pure projection without activating it in any
  public report path and run:

  ```bash
  pytest --collect-only -q tests/test_prompt_context_report.py
  pytest -q \
    tests/test_prompt_context_report.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_dependency_evidence.py
  ```

- [ ] Obtain ordered `Q5_TASK4_SPEC_APPROVED` then
  `Q5_TASK4_QUALITY_APPROVED`; commit.

**Gate:** One current-Q3-aware owner internally supports version-strict,
content-free, runtime-independent report v2, while Task 11 remains the only
public selector: an existing external v1 stays byte-identical, and an absent
external prompt-context report stays absent.

## Task 5: Ledger Encoding, Writer, And Embedded Manifests

**Files:** Create `orchestrator/workflow/provider_phased_delivery/ledger.py`
and `tests/test_provider_prompt_phase_ledger.py`.

- [ ] Write RED physical-format tests for canonical UTF-8 JSONL, sorted keys,
  compact separators, ASCII escaping, one LF, header sequence zero,
  contiguous u63 event sequence, exact `ProviderAttemptScope` path derivation,
  and fsync-before-dependent-action.
- [ ] Write RED exact header/event/payload encoders for every accepted event.
  Reject missing/extra keys, wrong scalars, Boolean integers, malformed
  timestamps/digests, scope mismatch, ordinal/count error, and attempts to
  append after a locally recorded terminal event.
- [ ] Write RED embedded
  `provider_phased_candidate_digest_manifest.v1` tests: deterministic
  expected-output then structured-bundle order, complete
  presence/size/digest nullability, contract ordinals, frozen all-regular
  postcondition, and recomputed manifest seal. Reject digest-only or external
  manifests.
- [ ] Implement only immutable row/manifest encoders plus the append/fsync
  writer. It must not parse ledger history or expose result, retry, resume, or
  settlement reconstruction.
- [ ] Run:

  ```bash
  pytest --collect-only -q tests/test_provider_prompt_phase_ledger.py
  pytest -q \
    tests/test_provider_prompt_phase_ledger.py \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_diagnostics.py \
    -k 'encoding or writer or append or manifest or physical'
  ```

- [ ] Obtain ordered `Q5_TASK5_SPEC_APPROVED` then
  `Q5_TASK5_QUALITY_APPROVED`; commit exact writer/encoder bytes.

**Gate:** The writer produces only exact, durable, content-free rows and
embedded manifests; no offline grammar result or runtime authority exists.

## Task 6: Offline Ledger Grammar And Digest Validation

**Files:** Modify `provider_phased_delivery/ledger.py` and
`tests/test_provider_prompt_phase_ledger.py`.

- [ ] Write RED T0–T4 grammar vectors, including T2a cleanup pending, T2b
  cleanup already finished, normal versus terminalizing ingress, one cleanup
  overall, at most one ingress pair, `ingress_shutdown_failed`, direct
  post-proof terminal failure, and no event after either terminal row.
- [ ] Write RED proof-union matrices for every cleanup status/member/null
  combination, active-handle projection, failed-start proof copies,
  invalid/mismatched handle rejection, natural-proof nullability, and
  rejection of raw `FailedCleanupProof`.
- [ ] Write RED offline result/precedence cases for
  `complete|valid_prefix|malformed|truncated`. The validator reads only ledger
  bytes. Classify every digest as a recomputable seal or opaque reference and
  distinguish order mismatch, equality mismatch, and recomputation mismatch.
- [ ] Implement the pure offline parser/validator on Task-5 bytes. It never
  guesses a later row, reads candidate/state/provider data, or authorizes
  runtime publication, retry, resume, or settlement.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_provider_prompt_phase_ledger.py \
    tests/test_provider_phased_delivery_contracts.py \
    tests/test_provider_phased_delivery_diagnostics.py \
    -k 'validator or grammar or digest or terminal or proof'
  ```

- [ ] Obtain ordered `Q5_TASK6_SPEC_APPROVED` then
  `Q5_TASK6_QUALITY_APPROVED`; commit.

**Gate:** Every legal T0–T4 history has one interpretation, malformed evidence
fails at the exact first reason, and the validator remains offline-only.

## Task 7: Attempt-Bound Submit Protocol And Endpoint

**Files:** Create `provider_phased_delivery/protocol.py`,
`provider_phased_delivery/endpoint.py`,
`orchestrator/cli/commands/provider_materialization.py`, protocol/CLI tests,
and modify only CLI registration owners.

- [ ] Write RED binding/request/receipt contracts. The command accepts no
  run, step, ordinal, path, pane, or endpoint argument; reads only
  `ORCHESTRATOR_PHASED_PROVIDER_BINDING`; sends one bounded request id; waits
  for `retry_queued|accepted_closing|failed`; and writes no workflow state or
  ledger.
- [ ] Write RED inert-prestart cases: binding and locator derivation allocate
  no address/file/socket/listener/worker/descriptor/thread/process/namespace.
  Actual bind starts only after successful provider start; loss of that race
  is endpoint-allocation failure.
- [ ] Write RED replay/concurrency/shutdown matrices for exact replay, changed
  payload, foreign/stale binding, duplicate in flight, concurrent submit,
  wrong lifecycle, late/queued requests, receipt flush, stopped admission,
  drained workers, and truthful complete/incomplete endpoint outcome. Every
  wait consumes the shared whole-attempt deadline.
- [ ] Implement the minimum serialized local owner and run:

  ```bash
  pytest --collect-only -q \
    tests/test_provider_materialization_protocol.py \
    tests/test_cli_provider_materialization.py
  pytest -q \
    tests/test_provider_materialization_protocol.py \
    tests/test_cli_provider_materialization.py \
    tests/test_provider_peer_group_protocol.py \
    tests/test_provider_peer_group_runtime.py
  ```

- [ ] Obtain ordered `Q5_TASK7_SPEC_APPROVED` then
  `Q5_TASK7_QUALITY_APPROVED`; commit.

**Gate:** Pre-start values are inert, replay is idempotent, concurrent
requests serialize, and shutdown truthfully proves or withholds zero
survivors.

## Task 8: Coordinator Core, Happy Path, Retry, And Publication

**Files:** Create `provider_phased_delivery/bindings.py`,
`provider_phased_delivery/coordinator.py`, and
`tests/test_provider_phased_delivery_coordinator.py`; modify ledger tests.

- [ ] Write RED `PhasedProviderAttemptCoordinatorBindings` contracts for
  attempt identity, candidate preflight/snapshot/Q2 validation/freeze/reset,
  evidence publication, frozen restoration/verification, atomic success
  commit, and failure finalization. Synthetic bindings supply directly
  constructed immutable policy/configuration; coordinator imports no
  compiler, `RuntimeStep`, provider executor, or workflow executor.
- [ ] Write the one-submit happy RED trace: allocate once, compose once, write
  header, start `F_task || T1`, bind endpoint, offer
  `F_materialization || T2`, run both Q2 validators, freeze, close/flush,
  stop ingress, join naturally, enter `JOINED_PENDING_COMMIT` before
  `join_succeeded`, publish v3, restore/verify, and commit once. Nothing is
  authoritative earlier.
- [ ] Write invalid-then-valid and cap RED cases. Preserve the complete
  rejected manifest; reset only exact preflight-absent regular candidates;
  offer `F_retry(d) || T2`; never repeat task/start/attempt; publish only the
  valid pair. Exercise both opposing invalid fixtures—invalid artifact with
  valid structured result, and valid artifacts with invalid structured
  result—and prove both validators run in fixed output-position-then-
  structured-result order with no short-circuit or early authority. Cover
  caps 1/2/3 and exhaustion.
- [ ] Write RED happy-path candidate containment and record-order cases:
  pre-existing path, pairwise collision, non-regular replacement, complete
  recreation, actual deliveries for successful receipts only, and each
  record-before-dependent-action edge.
- [ ] Implement only the successful/rejected/retry/publication spine. Use
  narrow deterministic failures to hand off to the Task-9 terminalizer; do not
  complete race/deadline matrices here.
- [ ] Run:

  ```bash
  pytest --collect-only -q tests/test_provider_phased_delivery_coordinator.py
  pytest -q \
    tests/test_provider_phased_delivery_coordinator.py \
    tests/test_provider_prompt_phase_ledger.py \
    tests/test_provider_materialization_protocol.py \
    -k 'happy_path or invalid_then_valid or retry or cap or publication'
  ```

- [ ] Obtain ordered `Q5_TASK8_SPEC_APPROVED` then
  `Q5_TASK8_QUALITY_APPROVED`; commit.

**Gate:** Synthetic bindings prove one-client happy and materialization-only
retry through post-join atomic publication; no public authored route exists.

## Task 9: Coordinator Terminalization And Cleanup

**Files:** Modify Task-8 coordinator/bindings/tests and ledger tests.

- [ ] Write executable RED T0–T4 traces for failed start and every
  preparation/evidence/start/offer/endpoint/submit/validation/reset/freeze/
  close/ingress/join/publication failure. Exercise T2a and T2b separately.
- [ ] Write RED cleanup-proof matrices: a live pre-proof handle receives
  exactly one abort; validate active handle before projecting
  `FailedCleanupProof`; malformed/missing/mismatched/raised/timeout cleanup
  produces exact incomplete/null evidence. Failed start never aborts; T4 never
  aborts or cleans up.
- [ ] Write RED endpoint terminality: T0 owns none, T1 shuts partial
  allocation, T2a completes pending cleanup then already-started ingress, T2b
  never duplicates either, T3 uses completed ingress, and incomplete shutdown
  emits `ingress_shutdown_failed`.
- [ ] Write irreversible post-proof RED cases. Natural proof changes lifecycle
  before the ledger write; later ledger/publication/restoration/verification/
  commit failures publish no authority, preserve provisional evidence, and
  make zero abort calls.
- [ ] Implement the closed terminalizer preserving the first diagnostic and
  explicit cleanup/ingress/natural-proof substates; run:

  ```bash
  pytest -q \
    tests/test_provider_phased_delivery_coordinator.py \
    tests/test_provider_prompt_phase_ledger.py \
    tests/test_provider_interactive_terminal.py \
    -k 'terminal or cleanup or ingress or post_join or start_failed'
  ```

- [ ] Obtain ordered `Q5_TASK9_SPEC_APPROVED` then
  `Q5_TASK9_QUALITY_APPROVED`; commit.

**Gate:** All terminal productions and proof combinations are executable
without duplicate cleanup/ingress, invented proof, or post-proof abort.

## Task 10: Coordinator Races And Whole-Attempt Deadlines

**Files:** Modify Task-8/9 coordinator/bindings/tests, endpoint tests, and
ledger tests.

- [ ] Generate RED “exhausted before” and “crossed during” cases for
  preparation, ledger append, start, endpoint allocation, initial/retry offer,
  submit, Q2 validation, reset, freeze, close, ingress, join, v3 publication,
  restoration, verification, state-commit preparation, the final state-lock
  commit-linearization check (`deadline_exhausted_before_state_commit`), and
  cleanup. Before performs zero new action; during prevents all later
  action/commit.
- [ ] Write RED races for provider exit before submit, changed request replay,
  concurrent submits, candidate identity change during validation/freeze,
  reset versus provider rewrite, endpoint address loss, close versus queued
  submit, join/ledger failure, and interruption at
  `JOINED_PENDING_COMMIT`.
- [ ] Write RED evidence-channel failures: record-before-action failure blocks
  normal progress but still performs mandatory fail-safe cleanup; a valid
  prefix never reconstructs a later row or authorizes resume.
- [ ] Complete deadline/race gates without a generic exception fallback or
  fresh cleanup budget; run:

  ```bash
  pytest -q \
    tests/test_provider_phased_delivery_coordinator.py \
    tests/test_provider_prompt_phase_ledger.py \
    tests/test_provider_materialization_protocol.py \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_peer_group_runtime.py \
    -k 'deadline or race or concurrent or evidence_channel or interrupted'
  ```

- [ ] Obtain ordered `Q5_TASK10_SPEC_APPROVED` then
  `Q5_TASK10_QUALITY_APPROVED`; commit.

**Gate:** The complete internal coordinator passes every race/deadline
direction and remains unreachable from authored workflows.

## Task 11: Atomic Target-2.23 Public And Runtime Activation

**Files:** Modify every syntax/compiler/IR, persistence/checkpoint,
`RuntimeStep`, provider executor/types, report selector, and workflow-executor
path in the responsibility map, including:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck_effects.py`
- `orchestrator/workflow_lisp/wcc/elaborate.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- `tests/test_workflow_lisp_provider_call_policy.py`

Create the phased carriage, persistence, runtime, deterministic fixture, and
public-E2E tests. Modify exact adjacent compiler/policy/persistence/checkpoint/
provider/report tests, including
`tests/test_workflow_lisp_provider_call_policy_e2e.py`.

- [ ] **Run a focused carrier-footprint audit before capture or
  resubmission.**
  From current `HEAD` and working blobs, run:

  ```bash
  rg -n \
    'provider_call_policy|CompilerPromptAttemptBindingPlan|RuntimeStep|provider-result|prompt_attempt_identity' \
    orchestrator/workflow_lisp \
    orchestrator/workflow \
    orchestrator/providers \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_lisp_prompt_identity_carriage.py \
    tests/test_workflow_lisp_prompt_identity_persistence.py
  ```

  Record every carrier owner and explicitly classify it as changed or
  unchanged. The audit must cover classic and WCC expression/typecheck/
  elaborate/defunctionalize paths. An unclassified carrier stops capture and
  review.
- [ ] Perform the fresh collision audit on every classified owner, including
  the four newly explicit Workflow Lisp/WCC files and both call-policy test
  modules. Capture path blobs/patches; assign each hunk to Q5 or ambient
  ownership; preserve ambient hunks. Build one exact candidate whose only new
  public route terminates in the complete Task-10 coordinator. Never commit a
  compiler-only, persistence-only, selector-only, or executor-only subset.
- [ ] Write RED target-2.23 syntax/static tests: closed `:delivery`, literal
  integer cap `1..3` default `2`, Boolean rejection, illegal pairing,
  fragment-backed non-empty result contract, exact diagnostics/sources, and
  exact `interactive_terminal_turn_queue.v1` admission. Capability drift
  refuses before allocation with zero composed fallback.
- [ ] Write RED paired carriage through expressions/typecheck, typed
  application, Core, Semantic, Executable, classic/WCC elaborate and
  defunctionalize, persisted state-schema-2.1 identity, checkpoint, and
  `RuntimeStep`. Reject every missing/extra/reordered/default-invented/
  unequal/mixed-version pair. Add no phase cursor.
- [ ] In both primary ordinary and interactive policy suites
  (`tests/test_workflow_lisp_provider_call_policy.py`,
  `tests/test_provider_call_policy.py`,
  `tests/test_provider_execution.py`, and
  `tests/test_provider_interactive_terminal.py`), prove `model`/`effort`
  translation is unchanged; `delivery` and integer
  `materialization_attempts` are runtime-consumed and never provider-bound,
  argv-substituted, or native parameters; unknown keys fail at the shared
  partition. Use only generic closed-key negatives.
- [ ] Write RED dispatch/report-selector tests: explicit phased reaches only
  Task 10 after revalidation; every refusal makes zero coordinator/start/
  composed calls; explicit composed remains ordinary. Activate the Task-4
  report-v2 projector in the existing public report owner in this same atomic
  task: the pre-activation external baseline stays byte-preserved—v1 when Q3
  public report-v1 exists, absent otherwise—and either branch switches to
  `workflow_prompt_context_report.v2` for all runs with functional-v1/v2/v3
  qualification and identity-v1/v2 projection. Nonterminal phased visits
  quarantine; completed reuse reads no ledger.
- [ ] Write RED deterministic public scenarios for both opposing Q2-invalid
  pairs—invalid artifact with valid structured result, and valid artifacts
  with invalid structured result—followed by unchanged-`T2` valid retry.
  Prove fixed validator order, no short-circuit, and no early authority; these
  exact committed tests are the Task-12 GREEN gate.
- [ ] In those public E2E owners, write RED assertions for exact identity-v2/
  functional-v3 delivery rows, ledger and candidate manifests, global
  report-v2 projection, zero endpoint survivors, and no claim that canonical
  `C` was delivered whole. Add separate RED interruption cases before the
  initial offer, during retry, and after valid freeze; all quarantine
  sticky-failed. Add completed-compatible-reuse RED proving no provider,
  endpoint, or ledger access. These tests also land in Task 11 and are replayed
  without edits by Task 12.
- [ ] Freeze 2.20–2.23 omitted/composed compiler, persistence, checkpoint,
  provider policy/invocation, identity/evidence, result, and completed-boundary
  bytes. Report bytes are the intentional exception: every run changes
  globally to the exact report-v2 projection required above.
- [ ] Prove RED, implement the complete route, then rerun the footprint audit
  and require the same classified owner set before candidate capture.
- [ ] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_phased_delivery_carriage.py \
    tests/test_workflow_lisp_phased_delivery_persistence.py \
    tests/test_workflow_lisp_phased_delivery_runtime.py \
    tests/test_workflow_lisp_phased_delivery_e2e.py
  pytest -q \
    tests/test_workflow_lisp_phased_delivery_carriage.py \
    tests/test_workflow_lisp_phased_delivery_persistence.py \
    tests/test_workflow_lisp_phased_delivery_runtime.py \
    tests/test_workflow_lisp_phased_delivery_e2e.py \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py \
    tests/test_provider_call_policy.py \
    tests/test_provider_execution.py \
    tests/test_provider_interactive_terminal.py \
    tests/test_provider_phased_delivery_coordinator.py \
    tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_shared_validation.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_checkpoint_identity_comparison.py \
    tests/test_observability_report.py \
    tests/test_cli_report_command.py
  ```

- [ ] Obtain ordered `Q5_TASK11_SPEC_APPROVED` then
  `Q5_TASK11_QUALITY_APPROVED` over the complete candidate. Any byte,
  footprint, ownership, or parent change restarts capture and both reviews.
  Commit the whole activation atomically.

**Gate:** The first public phased surface, every carrier, report selector,
policy split, capability gate, and runtime route land together; phased reaches
only the complete coordinator; omitted/composed bytes are unchanged; all
refusals have zero fallthrough.

## Task 12: GREEN Deterministic Public Integration And Compatibility

**Files:** Inspect only. The gate owns no production, fixture, or test patch.

- [ ] Run the deterministic public phased scenario already landed by Task 11:
  one task action, each opposing invalid first pair in its own trace, both Q2
  validators in fixed order, unchanged-`T2` retry, valid second pair, natural
  join, and one atomic publication. Validate identity v2/functional v3
  deliveries, ledger/manifests, report v2, content-free records, zero endpoint
  survivors, and no claim that `C` was delivered whole.
- [ ] Run interruption before initial offer, during retry, and after freeze;
  require sticky quarantine. Completed compatible reuse touches no provider,
  endpoint, or ledger.
- [ ] Run target-2.17 peer compatibility and 2.20–2.23 omitted/composed
  compatibility, including the primary public policy E2E:
  `tests/test_workflow_lisp_provider_call_policy_e2e.py`. Explicitly prove
  model/effort translation remains unchanged and runtime-only delivery/
  attempts never enter provider arguments on a public compiled workflow.
- [ ] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_phased_delivery_e2e.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py
  pytest -q \
    tests/test_workflow_lisp_phased_delivery_e2e.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_lisp_provider_peer_group_e2e.py
  ```

- [ ] Require GREEN from the exact committed Task-11 tree. Any RED is not
  patched here: classify it, return the failure to Task 11, write the missing
  RED there, implement the correction, repeat Task-11 specification then
  quality review, recommit the complete atomic activation, and restart Task
  12 from its first step.
- [ ] Obtain one independent `Q5_TASK12_INTEGRATION_APPROVED` evidence review.
  No quality review or commit is needed because this task changes no bytes.

**Gate:** The committed public activation passes deterministic integration,
resume/quarantine, peer, compiled-policy, and omitted/composed controls without
post-activation production patches.

## Task 13: Motivating Consumer And Real-Provider Gate

**Files:** Create `tests/e2e/test_e2e_provider_phased_contract_delivery.py`;
modify only the exact fragment-backed call in
`workflows/examples/review_revise_design_docs.orc` and required existing
fixtures.

- [x] Write the real-provider gate before changing the consumer: one
  production coordinator/adapter/client/task action, invalid first
  materialization, one diagnostic materialization-only retry, valid second
  materialization, natural join, exact evidence, and atomic publication.
  Never inspect pane text or cancel/resume a provider session.
- [x] Add explicit phased policy only to the exact review call, preserving
  judgment prose and Q2 output/result authority.
- [x] Run in tmux:

  ```bash
  ORCHESTRATE_E2E=1 PYTHONWARNINGS=error pytest -q -s \
    tests/e2e/test_e2e_provider_phased_contract_delivery.py \
    -k 'review_revise_design_docs and invalid_then_valid'
  ```

- [x] Run the full focused Q5 selector covering Tasks 1–12.
- [x] Obtain ordered `Q5_TASK13_SPEC_APPROVED` then
  `Q5_TASK13_QUALITY_APPROVED`; commit.

**Gate:** The motivating consumer proves a real same-client
task/materialization sequence, bounded correction, exact evidence, and atomic
publication.

## Task 14: Normative, Routing, Broad, And Final Closure

**Files:** Only normative/routing paths in the responsibility map and this
plan.

- [x] Recapture shared docs, preserving newer Q/L/M and owner edits.
- [x] Update `specs/dsl.md`, `specs/providers.md`, `specs/state.md`,
  `specs/versioning.md`, and `specs/index.md` for exact implemented behavior.
  Do not amend `specs/io.md`; add no isolation support/diagnostic claim.
- [x] Update design, authoring, capability, indexes, and roadmap truth. Mark
  Q5 implemented only after P0–P2 and Tasks 1–13 are complete and green.
- [ ] Run routing, authoring, all focused Q5, prompt identity/calculus,
  adapter, peer, compiled-policy, and E2E selectors.
- [ ] In tmux run the same explicit non-security collection ignore list bound
  after P2, then:

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

  Compare node IDs and non-passes with the post-P2 baseline; explain every
  delta without repairing excluded/unrelated failures.
- [ ] Update this plan only with factual commits/selectors/reviews; run
  `git diff --check`; obtain `Q5_FINAL_SPEC_APPROVED`, then
  `Q5_FINAL_QUALITY_APPROVED`. Any byte change restarts both.
- [ ] Commit exact closure and rerun routing plus the focused Q5 selector.

**Gate:** Normative/design/authoring/capability/routing truth agrees; focused,
real-provider, target-2.17, and broad non-security evidence is fresh; ordered
holistic reviews approve the exact tree.

## Final Completion Checklist

Q5 is complete only when:

1. P0–P2 land the deadline-aware closed-start prerequisite without Q5;
2. Tasks 1–10 complete all internal models, cut, identity/evidence/report,
   ledger writer/manifest, offline validator/grammar, endpoint, coordinator
   core, terminalization, races, and deadlines through directly constructed
   immutable configurations before any public phased surface exists;
3. diagnostics are total before producers, excluding only the owner-deferred
   isolation row, with zero isolation producer/test/normative claim;
4. `model`/`effort` stay provider-bound with unchanged ordinary/interactive
   translation, while `delivery`/integer attempts are runtime-only;
5. Task 11 atomically lands every syntax/expression/typecheck/classic/WCC/IR/
   persistence/checkpoint/`RuntimeStep`/report/provider/executor carrier and
   route after a complete carrier-footprint and collision-ownership audit;
6. omitted/composed behavior remains byte-compatible and refusals have zero
   fallthrough;
7. Task 12 is GREEN-only; any failure backroutes to Task 11 TDD and ordered
   reviews rather than creating a post-activation patch;
8. `T1 || T2 == C`, frame separation, ledger non-authority, endpoint
   terminality, and atomic post-join publication hold;
9. retry, cap, opposing Q2-validator, T0–T4, T2a/T2b, deadline, cleanup,
   ingress, post-join, and race cases have both-direction coverage;
10. identity v2/functional v3/current-Q3-aware report v2 are strict and
    non-authoritative;
11. interruption quarantines and completed reuse avoids ledger reads;
12. primary ordinary/interactive/public-E2E policy tests prove unchanged
    provider translation and runtime-only phased keys;
13. deterministic and real-provider consumers prove one-client correction;
14. target-2.17 peer behavior remains unchanged;
15. no Q4, prompt queue, peer-group reuse, name branch, YAML, security,
    safety, secrets, or provider-isolation scope enters the candidate;
16. every production task and the atomic activation receive ordered
    specification then quality review, while the GREEN-only integration gate
    receives its evidence review;
17. focused, E2E, routing, and broad non-security evidence is fresh; and
18. ordered holistic specification then quality review approves the exact
    final committed implementation.

## 2026-07-28 Task 13 Stop Record

**Historical provenance, superseded on 2026-07-29.** The paragraphs below
truthfully record the then-current stop and must remain readable as history.
They no longer select execution; the Task 13 completion record after this
section is current.

Task 13 is not complete, Task 14 has not started, and Q5 must not be described
as fully implemented under this plan.

The exact migrated target-2.23 consumer and its test harness were prepared but
not promoted. Two independent real `gpt-5.5`/`high` combined runs completed the
counted task action and initial-offer release, then reached the one-hour
whole-attempt deadline with no materialization submission. The pytest results
were `1 failed in 3601.52s` and `1 failed in 3601.58s`; each observed phase
ledger remained at the five-event pre-submit prefix. Neither run used pane
inspection, cancellation, resume, or forced settlement.

Comparative controls narrowed the stop:

- the unchanged real-Codex two-turn adapter control passed with
  `gpt-5.4`/`high` in `46.36s`;
- the same control passed with `gpt-5.5`/`high` in `49.05s`;
- moving acceptance guidance to the end of a temporary byte-derived consumer
  and adding a temporary generic materialization action token each still
  produced no submission within the complete four-minute control window; and
- the temporary source and protocol experiments were removed, their exact
  provider/submit sockets and processes were cleaned, and no production
  protocol change was retained.

The deterministic public production-path evidence and the real adapter
controls remain useful component evidence, but they do not prove the combined
consumer gate required by Task 13. Independent specification adjudication
therefore withheld `Q5_TASK13_SPEC_APPROVED` and classified the combined
result as `not_proven / provider_behavior_nonterminating`.

Resume Task 13 only after a reviewed design/plan amendment changes the gate or
after the unchanged combined consumer can produce the required real-provider
invalid-then-valid trace. Do not infer a split-proof substitution, mark Q5
complete, or start Task 14 closure from this stop record.

## 2026-07-29 Task 13 Completion Record

This record supersedes the 2026-07-28 stop for current routing without
rewriting its historical claims.

- The exact target-2.23 motivating-consumer gate completed on real attempt 10:
  `1 passed in 47.29s`. The run used one provider process and the unchanged
  combined invalid-then-valid contract path.
- The classified precommit focused selector passed **2,245** tests, deselected
  exactly the two post-P2 baseline nodes below, and emitted 33 warnings:
  - `tests/test_workflow_lisp_checkpoint_identity_comparison.py::test_design_delta_drain_generic_route_matches_baseline`;
  - `tests/test_workflow_lisp_checkpoint_identity_comparison.py::test_reviewed_inline_call_retirement_rejects_identity_or_lineage_drift`.
- Independent review issued ordered `Q5_TASK13_SPEC_APPROVED` then
  `Q5_TASK13_QUALITY_APPROVED` over the exact consumer and harness delta.
- Commit `bb67f680` (`Prove phased delivery with real review consumer`) landed
  Task 13. The postcommit focused repeat again passed **2,245** tests with the
  same two explicit deselections.

Task 13 is complete. The historical withheld verdict applies only to the
superseded 2026-07-28 candidate; it does not override the later ordered
approvals over the completed bytes.

## 2026-07-29 Task 14 Pre-Correction Candidate Record

The Task 14 normative/design/authoring/capability/routing candidate describes
the implemented Tasks 1–13 surface while preserving newer Q/L/M routing and
the historical stop above.

The broad non-security run at Task-13 commit `bb67f680` completed with
**10,919 passed, 42 failed, 23 skipped, 0 errors, and 33 warnings**. It
predates correction `5d8a3151` and is retained as truthful superseded
candidate evidence, not as the Task-14 closing broad gate. A fresh
post-correction replay and exact delta adjudication of node IDs and non-passes
against the post-P2 baseline remain required. This record does not classify or
repair excluded/unrelated failures.

`Q5_FINAL_SPEC_APPROVED` then `Q5_FINAL_QUALITY_APPROVED` remain unissued and
must be external reviews of the final exact tree. No closure commit is
recorded here, and this candidate does not self-attest either verdict.
