# Q3 Persisted Prompt-Schema Authority Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by
> task and `superpowers:test-driven-development` for every production change.
> Execute Tasks 1–4 serially with their named RED/GREEN gates, then Task 5
> builds one combined exact-path candidate and obtains one independent
> specification-compliance review followed by one distinct
> implementation-quality review before one commit. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Persist the compiler-owned compiled-prompt-fragment identity schema
for each exact `ProviderAttemptScope` so terminal and state-only readers can
strictly validate Q3 v2 prompt snapshots without reopening source or trusting
record-authored schema claims.

**Architecture:** Add one optional closed
`prompt_fragment_identity_schema_version` member directly to the existing
allocator entry keyed by canonical `ProviderAttemptScope.key`. Q3 allocation
supplies the compiler-derived `compiled_prompt_fragment_identity.v1` or
`compiled_prompt_fragment_identity.v2` token and persists it in the same
durable state write as the allocation; pre-Q3 entries retain their exact
three-member bytes. Terminal evidence validation derives its validation
authority from that scope-keyed persisted member and removes the weaker
caller-supplied runtime-step map.

**Tech Stack:** Python 3.11+, dataclasses, closed JSON state, canonical
`ProviderAttemptScope` SHA-256 identities, durable state locking, Workflow
Lisp typed runtime carriers, functional prompt evidence, and pytest.

---

## Authority And Status

This is the minimal prerequisite correction discovered while starting Task 6
of:

- `docs/plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md`

The accepted Q3 behavior remains governed by:

- `docs/design/workflow_lisp_prompt_identity_diagnostics.md`;
- `docs/design/workflow_lisp_prompt_calculus.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_executable_ir.md`;
- `specs/state.md`; and
- `specs/versioning.md`.

The correction does not implement the Task 6 report projection. Task 6 may
resume only after this exact plan passes ordered plan review, the correction
passes ordered implementation review, and the reviewed correction is
committed.

## Deliberate Cost

This makes persisted-state evolution and scope-key canonicalization harder.
Future fragment identity schema versions must update the closed state
validator, and any future change to `ProviderAttemptScope` canonicalization
must preserve the authority binding or migrate it explicitly. That cost is
intentional: state-only readers gain durable compiler authority without
depending on current compiler behavior, authored source availability, or a
record's self-claim.

## Closed Storage Contract

The existing allocator entry is currently:

```json
{
  "scope": {},
  "last_allocated_ordinal": 1,
  "events": []
}
```

A Q3 fragment-backed scope adds exactly one member:

```json
{
  "scope": {},
  "last_allocated_ordinal": 1,
  "events": [],
  "prompt_fragment_identity_schema_version":
    "compiled_prompt_fragment_identity.v2"
}
```

The only accepted values are:

- `compiled_prompt_fragment_identity.v1`; and
- `compiled_prompt_fragment_identity.v2`.

The allocator mapping key remains `ProviderAttemptScope.key`. Existing
validation continues to require that the key equals the canonical digest of
the entry's exact `scope`. Embedding the authority in that entry intentionally
eliminates a separately addressable orphan-authority collection: an authority
member cannot exist without its scope and allocation entry.

The following rules are exact:

1. Pre-Q3 entries use the existing three-member shape and preserve their
   serialized bytes.
2. Q3 fragment-backed allocation requires one of the two exact authority
   tokens.
3. The authority is persisted in the same locked durable state mutation as
   the first allocation for the scope.
4. Every later allocation for a bound scope must repeat the same token.
   Missing or conflicting input fails before the ordinal or state bytes
   change.
5. A pre-Q3 scope without the optional member remains valid but can never be
   rebound as Q3. A later allocation for that existing scope with a schema
   token fails before the ordinal or state bytes change. Q3 authority must be
   present on the scope's first allocation.
6. Absence becomes a validation error only when a reader encounters a v2
   prompt snapshot that requires the authority.
7. An entry with an unknown member, malformed token, non-string value,
   mismatched mapping key, or noncanonical scope fails closed.
8. The authority is keyed by the complete scope digest, not
   `runtime_step_id`; equal runtime-step strings in different loop/call-frame
   scopes remain distinct.
9. The authority is not copied into prompt evidence, inferred from a v2
   record, reconstructed from source, or derived by the current compiler.
10. `workflow_provider_attempt_allocation_projection.v1` and
   `workflow_prompt_dependency_validated_index.functional.v1` are not widened
   by this correction. Terminal validation reads the authority from the
   already validated terminal `RunState` while retaining its existing exact
   projection/index formats and state-byte stability checks.
11. Workflow Lisp target 2.22 does not imply or introduce a durable state
    schema 2.2 or an allocator projection v2. The optional member is admitted
    by the existing state-schema-2.1 allocator validator and the projection
    remains v1.

## File Map

- Modify `orchestrator/workflow/provider_attempts.py`
  - Accept and normalize the optional scope-entry authority in the existing
    state-schema-2.1 allocator validator.
  - Preserve exact legacy entry output when the authority is absent.
- Modify `orchestrator/state.py`
  - Extend `StateManager.allocate_provider_attempt` and
    `StateManager._allocate_provider_attempt_from` with one keyword-only
    authority argument.
  - Bind or compare the token under the existing allocation lock and persist
    it atomically with the ordinal.
- Modify `orchestrator/workflow/call_frame_state.py`
  - Extend `NestedStateManager.allocate_provider_attempt` with the same
    keyword-only authority argument and forward it unchanged to the aggregate
    root owner.
- Modify `orchestrator/workflow/executor_runtime.py`
  - Extend the `ParentCallStateManager` protocol declaration with the same
    keyword-only authority argument so concrete managers satisfy the runtime
    interface.
- Modify `orchestrator/workflow/executor.py`
  - Derive the token once from the typed compiler fragment contract.
  - Pass it to allocation and reuse the same value for Q3 failure/snapshot
    construction.
- Modify `orchestrator/workflow/prompt_dependency_evidence.py`
  - Remove the caller-supplied runtime-step schema map.
  - Resolve each record's authority from its exact validated allocation entry.
- Modify `tests/test_provider_attempt_allocation.py`
  - Cover closed state shape, atomic binding, collision behavior, direct,
    dynamic-loop, and call-frame scope separation.
- Modify `tests/test_workflow_lisp_prompt_identity_runtime.py`
  - Prove the runtime passes compiler-derived authority and retains it through
    success and prelaunch failure.
- Modify `tests/test_prompt_dependency_evidence.py`
  - Prove terminal validation derives exact scope authority and fails closed
    on missing, malformed, conflicting, and misbound state.

No Task 6 report file is created or modified by this correction.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve all user and concurrent-session changes.
Before each task, audit the task's exact paths against `HEAD`, the working
tree, and the index. Use an isolated alternate index for review/commit
packaging; do not reset or replace the shared index.

For every production change:

1. add the smallest named behavioral test first;
2. run it and prove RED for the missing authority behavior;
3. implement only enough production code for GREEN;
4. rerun the focused selector and named adjacent tests;
5. record fresh command output; and
6. do not weaken a validator or change a test merely to erase a failure.

Security, secrets, safety, and provider-isolation suites are outside this
correction's scope and are not added to its selectors.

## Task 1: Close The Scope-Entry State Shape

**Files:**

- Modify: `orchestrator/workflow/provider_attempts.py`
- Modify: `tests/test_provider_attempt_allocation.py`

- [ ] **Step 1: Add legacy-byte and accepted-token RED tests.**
  Add tests named:

  - `test_pre_q3_allocator_entry_round_trips_without_prompt_schema_authority`
  - `test_allocator_entry_accepts_exact_scope_bound_prompt_schema_authority`

  Build one existing three-member allocation entry and prove its normalized
  dict and serialized `RunState.to_dict()` bytes do not gain a new member.
  Build otherwise identical entries containing each exact v1/v2 token and
  require the normalized entry to retain the token under the same canonical
  scope key.

- [ ] **Step 2: Add closed-negative RED tests.**
  Add:

  - `test_allocator_entry_rejects_malformed_prompt_schema_authority`
  - `test_allocator_entry_rejects_unknown_member_with_prompt_schema_authority`
  - `test_prompt_schema_authority_cannot_be_misbound_to_another_scope_key`

  Cover `None`, booleans, empty strings, unknown versions, an extra member,
  a mapping key that disagrees with `scope.key`, and a scope body changed
  without recomputing the key. Require the existing allocator validation
  boundary to reject every case.

- [ ] **Step 3: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q tests/test_provider_attempt_allocation.py
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'prompt_schema_authority or pre_q3_allocator_entry'
  ```

  Expected: collection succeeds; the accepted Q3 shape fails because allocator
  entries still require exactly the legacy three members.

- [ ] **Step 4: Implement the dual closed shape.**
  In the existing state-schema-2.1 allocation validator:

  - accept exactly the legacy key set or that set plus
    `prompt_fragment_identity_schema_version`;
  - validate the optional value against the two exact tokens;
  - emit the optional member only when it was present; and
  - leave event ordering, lifecycle validation, scope validation, and legacy
    normalization unchanged.

  Keep the authority on the allocation entry. Do not add a top-level map,
  wrapper schema, new projection schema, or runtime-step-keyed fallback.

- [ ] **Step 5: Run GREEN and allocator regressions.**

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'prompt_schema_authority or pre_q3_allocator_entry'
  pytest -q tests/test_provider_attempt_allocation.py
  ```

**Task 1 completion gate:** The existing state-schema-2.1 allocator validator
retains the exact optional token, legacy entries remain byte-identical, and
malformed or misbound entries fail closed.

## Task 2: Bind Authority Atomically At Allocation

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/executor_runtime.py`
- Modify: `tests/test_provider_attempt_allocation.py`

- [ ] **Step 1: Add first-allocation RED tests.**
  Add:

  - `test_q3_allocation_persists_scope_authority_in_the_same_state_write`
  - `test_pre_q3_allocation_preserves_legacy_entry_bytes`

  Call the allocator with a keyword-only
  `prompt_fragment_identity_schema_version` for Q3 and require the first
  durable state document to contain both ordinal 1 and the token in the same
  scope entry. Call the existing API without the keyword and require the exact
  legacy entry shape.

- [ ] **Step 2: Add collision and mutation-order RED tests.**
  Add:

  - `test_bound_q3_scope_requires_the_same_authority_on_retry`
  - `test_bound_q3_scope_rejects_conflicting_authority_before_allocating`
  - `test_legacy_scope_cannot_be_rebound_as_q3`
  - `test_failed_q3_authority_bind_leaves_durable_state_unchanged`

  After binding a scope, require a later allocation to repeat the same token.
  Omission, v1/v2 conflict, malformed input, or an attempt to add a Q3 token
  to an existing legacy entry must raise before incrementing
  `last_allocated_ordinal`, appending an event, or changing durable state
  bytes. A simulated durable-write failure must never produce a disk state
  containing only one half of the allocation/authority pair.

- [ ] **Step 3: Add exact-scope separation RED tests.**
  Add:

  - `test_prompt_schema_authority_distinguishes_dynamic_loop_scopes`
  - `test_prompt_schema_authority_distinguishes_equal_runtime_ids_in_call_frames`

  Use existing provider-attempt scope fixtures to create:

  - two canonical loop iteration scopes; and
  - two scopes with equal `runtime_step_id` but different call-frame paths.

  Require distinct canonical keys and independently retained authority.
  Exercise concrete `StateManager.allocate_provider_attempt` and
  `NestedStateManager.allocate_provider_attempt` through their public methods.
  Require the nested path to forward through
  `StateManager._allocate_provider_attempt_from` so the authority resides only
  in aggregate-root state. Treat `ParentCallStateManager` only as the protocol
  signature checked by those concrete implementations. Do not introduce a
  runtime-step lookup table.

- [ ] **Step 4: Prove RED is intentional.**

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'q3_allocation or bound_q3_scope or legacy_scope_cannot_be_rebound_as_q3 or prompt_schema_authority_distinguishes'
  ```

  Expected: failures show that allocation does not accept or persist the new
  keyword and cannot detect authority conflicts.

- [ ] **Step 5: Implement the allocation contract.**
  Change `StateManager.allocate_provider_attempt`,
  `StateManager._allocate_provider_attempt_from`,
  `NestedStateManager.allocate_provider_attempt`, and the
  `ParentCallStateManager` protocol declaration to the equivalent of:

  ```python
  def allocate_provider_attempt(
      self,
      scope: Any,
      *,
      prompt_fragment_identity_schema_version: str | None = None,
  ) -> int:
  ```

  Forward the keyword unchanged from both concrete public methods through
  `StateManager._allocate_provider_attempt_from`; the protocol declares the
  same public shape but performs no forwarding. Validate the token before
  state mutation. Under the existing process lock and state lock:

  - for a new Q3 scope, construct the entry with ordinal/event and authority;
  - for an existing bound scope, require the supplied token to equal the
    retained token;
  - reject a missing token for an already bound scope;
  - permit `None` when creating or extending an unbound legacy scope;
  - reject a non-null token for an existing unbound legacy scope; and
  - persist the validated allocation dict once through the existing durable
    state writer.

  Reuse existing locking, repair-barrier, replay, and state-write owners. Do
  not add a second journal or post-allocation bind API.

- [ ] **Step 6: Run GREEN and state regressions.**

  ```bash
  pytest -q tests/test_provider_attempt_allocation.py \
    -k 'q3_allocation or bound_q3_scope or legacy_scope_cannot_be_rebound_as_q3 or prompt_schema_authority'
  pytest -q tests/test_provider_attempt_allocation.py
  ```

**Task 2 completion gate:** The compiler-authority token and ordinal become
durable together, retries cannot omit or change it, and complete scope
identity—not a runtime-step string—owns the binding. A legacy allocation entry
cannot be retrospectively upgraded to Q3.

## Task 3: Feed The Binding From Typed Runtime Authority

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_workflow_lisp_prompt_identity_runtime.py`

- [ ] **Step 1: Add compiler-derived allocation RED tests.**
  Add:

  - `test_target_222_allocation_persists_compiler_fragment_schema_authority`
  - `test_target_222_preparation_failure_retains_allocation_schema_authority`
  - `test_legacy_fragment_execution_does_not_add_schema_authority`

  For target 2.22, capture the exact allocation call and persisted entry.
  Require contract-v1 and contract-v2 fragment fixtures to select their
  corresponding exact tokens. Prove the token is already durable when
  invocation preparation fails. Run one below-target fixture and require its
  allocator entry and execution result bytes to retain legacy behavior.

- [ ] **Step 2: Add one-source-of-truth RED assertion.**
  In the success fixture, require the persisted allocation token, the fragment
  preparation-failure fragment token when applicable, and the validated v2
  fragment-program role token to agree. Test values and digests, not prompt
  prose.

- [ ] **Step 3: Prove RED is intentional.**

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_identity_runtime.py \
    -k 'allocation_persists_compiler_fragment_schema_authority or preparation_failure_retains_allocation_schema_authority or legacy_fragment_execution_does_not_add_schema_authority'
  ```

  Expected: Q3 entries lack the persisted member because the executor still
  calls the legacy allocation API.

- [ ] **Step 4: Derive and reuse one typed token.**
  In the existing Q3 fragment branch, derive one local authority value from
  the already validated typed fragment contract:

  - `CompilerPromptFragmentContract` maps to v1;
  - `CompilerPromptFragmentContractV2` maps to v2.

  Pass that exact value into `allocate_provider_attempt`. Reuse the same local
  value in preparation-failure construction, fragment-program role
  construction, v2 snapshot construction, and publication validation.
  Preserve allocation position, retry order, provider preparation/launch
  order, and all non-Q3 behavior.

- [ ] **Step 5: Run GREEN and adjacent runtime regressions.**

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_identity_runtime.py \
    -k 'schema_authority or preparation_failure or publish_before_launch or retry'
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py
  ```

**Task 3 completion gate:** Runtime obtains the persisted token only from the
typed compiler fragment carrier, binds it at allocation before all later
failure/success paths, and uses one value consistently through publication.

## Task 4: Make Terminal Validation Consume Persisted Scope Authority

**Files:**

- Modify: `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `tests/test_prompt_dependency_evidence.py`
- Modify: `tests/test_workflow_lisp_prompt_identity_runtime.py`

- [ ] **Step 1: Replace the external-map RED contract.**
  Replace
  `test_v2_terminal_validation_accepts_only_explicit_trusted_schema_context`
  with:

  - `test_v2_terminal_validation_derives_persisted_scope_schema_authority`
  - `test_v2_terminal_validation_rejects_missing_scope_schema_authority`
  - `test_v2_terminal_validation_rejects_conflicting_scope_schema_authority`

  The positive case calls `validate_terminal_evidence(root, state_file)`
  without a schema-map argument. The negative cases mutate only the persisted
  allocation entry and require fail-closed validation without echoing or
  trusting the record's schema claim.

- [ ] **Step 2: Add exact-scope terminal RED tests.**
  Add:

  - `test_terminal_validation_does_not_alias_equal_runtime_step_ids_across_scopes`
  - `test_terminal_validation_rejects_misbound_scope_authority`

  Bind two records under scopes that share a runtime-step string but differ by
  canonical resume/call-frame scope. Require each record to receive only its
  own entry's authority. A swapped/misbound key or scope body must fail at
  allocator validation before evidence validation.

- [ ] **Step 3: Add compatibility RED tests.**
  Require:

  - a terminal pre-Q3 run with no authority member to validate exactly as
    before;
  - a valid v1 fragment snapshot to validate without Q3 authority;
  - a Q3 preparation-failure record to retain its existing strict validator;
    and
  - a v2 snapshot with missing authority to fail rather than derive the token
    from `prompt_attempt_identity`.

- [ ] **Step 4: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py
  pytest -q \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    -k 'terminal_validation and schema_authority'
  ```

  Expected: the positive case fails because terminal validation still requires
  a caller-supplied runtime-step map.

- [ ] **Step 5: Remove the external authority API.**
  Remove
  `compiler_fragment_identity_schema_versions` from
  `validate_terminal_evidence` and `_build_terminal_index`.
  After reading and validating terminal `RunState`, validate its allocator and
  select the exact entry by `scope.key`. Pass that entry's optional authority
  into v2 canonical-record validation.

  The record reader must:

  - require authority for a v2 prompt snapshot;
  - reject missing or conflicting authority;
  - continue validating v1 snapshots and existing failure records without
    fabricated authority; and
  - never read authored source, compile a workflow, inspect current compiler
    output, or accept a caller-injected runtime-step map.

  Keep allocator projection and validated-index schemas/bytes unchanged.
  Existing before/after state-byte equality checks remain the mutation-window
  guard.

- [ ] **Step 6: Run GREEN and evidence regressions.**

  ```bash
  pytest -q \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    -k 'terminal_validation or schema_authority or canonical_record'
  pytest -q \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
  ```

**Task 4 completion gate:** Terminal validation uses only the exact
scope-keyed state authority, v2 missing/conflict cases fail closed, old runs
remain compatible, and no current compiler or source is consulted.

## Task 5: Isolation Audit, Ordered Review, And Commit

**Files:**

- Modify only the production/test paths listed in Tasks 1–4.

- [ ] **Step 1: Collect every changed test module.**

  ```bash
  pytest --collect-only -q \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py
  ```

- [ ] **Step 2: Run the focused correction suite.**

  ```bash
  pytest -q \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py
  ```

- [ ] **Step 3: Run adjacent state/runtime/evidence integration.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
  ```

- [ ] **Step 4: Prove exact-path isolation.**
  Build an immutable candidate from the named production/test paths. Prove:

  - no Task 6 report path is present;
  - no security, safety, secrets, or provider-isolation path is present;
  - no ambient shared-tree change is present;
  - the candidate parent is the intended current `HEAD`; and
  - candidate file hashes match the bytes exercised by the final selectors.

- [ ] **Step 5: Obtain ordered independent reviews.**
  Dispatch one fresh specification reviewer against the immutable candidate,
  this plan, the accepted Q3 design, and the prerequisite-gap finding. If it
  rejects, correct the candidate, rerun all selectors, rebuild the immutable
  candidate, and restart specification review.

  Only after specification approval, dispatch a distinct quality reviewer.
  If it rejects, repeat the same correction and ordered-review cycle. Required
  verdict order is:

  1. specification compliance: approved;
  2. implementation quality: approved.

- [ ] **Step 6: Commit exactly the reviewed candidate.**
  Commit only after both approvals. Recheck the parent immediately before the
  atomic ref update; if it moved, rebuild/retest/review rather than projecting
  the old tree onto a new parent.

- [ ] **Step 7: Rerun post-commit verification.**

  ```bash
  pytest -q \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
  ```

## Final Completion Gate

The correction is complete only when:

- every Q3 fragment-backed allocation durably binds one exact v1/v2 compiler
  authority to its canonical scope entry;
- allocation and binding are one durable mutation;
- missing, malformed, conflicting, extra, or misbound authority fails closed;
- equal runtime-step strings across different loop/call-frame scopes cannot
  alias;
- pre-Q3 allocation/state bytes remain unchanged;
- terminal validation derives authority from persisted state and accepts no
  caller/runtime-step authority map;
- no source recompilation or current-compiler dependency exists;
- all named selectors pass from fresh output;
- the immutable exact-path candidate passes specification then quality review;
  and
- Task 6 report code remains untouched and can resume against this committed
  prerequisite.
