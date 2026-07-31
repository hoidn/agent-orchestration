# Workflow Lisp Pure-Result Replay

## Metadata

- **Status:** accepted M2 design; M2 feasibility complete
- **Kind:** architecture decision
- **Owner:** Ollie
- **Reviewers:** independent specification review, then independent quality review
- **Review status:** initial direction approved by
  `M2_FEASIBILITY_SPEC_APPROVED`, then `M2_FEASIBILITY_QUALITY_APPROVED`;
  executable implementation landed through `cf0490d1` with completed-resume
  compatibility correction `ce02cd17`; final acceptance passed
  `M2_FEASIBILITY_FINAL_SPEC_APPROVED` then
  `M2_FEASIBILITY_FINAL_QUALITY_APPROVED`
- **Created:** 2026-07-29
- **Last material update:** 2026-07-30
- **Related docs / plans:**
  - `docs/plans/2026-07-26-substrate-maintenance-track.md`
  - `docs/reports/2026-07-26-m0-decision-brief.md`
  - `docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md`
  - `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
  - `docs/design/workflow_lisp_lexical_checkpoint_resumability.md`
  - `specs/state.md`
- **Implementation status:** the explicit-profile feasibility mechanism is
  implemented in M2; ordinary root and fresh-frame activation remains the
  separate Phase M3a target

## Summary

Successful compiler-generated pure projections are derived values, not durable
run facts. For runs explicitly created under the new replay profile, the
runtime keeps them in the active executor's transient step-result overlay,
replaces their value-bearing rows with exact value-free completion shells,
omits their private-lineage values and bundle sidecars from durable state, and
deterministically reconstructs them on resume from validated bound inputs and
validated durable effect results.

This design selects only component (a) of substrate Phase M2. Effect-identity
memo keys and memo-first execution do not enter: the owner-recorded re-entry
evidence for component (b) is absent. The design therefore creates no second
effect identity and does not change provider, command, resource-transition,
materialized-view, call-boundary, loop-progress, or public settlement
durability.

The first implementation is deliberately narrower than arbitrary history
replay. It covers successful, acyclic `pure_projection` nodes in a root or
non-iterative call frame. Loop/recur and other multiply visited regions retain
their existing durable results. That boundary keeps M3a independent from the
unselected memo-key component and from the separately described M3c loop-state
elision.

## Context And Authority

The governing substrate track says that durable effects should become the
runtime interface and records pure-result replay as M2 component (a). The M0
decision brief closes the M2 depth decision at component (a) unless
post-ML evidence shows positional invalidation causing provider re-spend in
three distinct runs or one full-workflow re-execution. No such evidence is
recorded.

The landed runtime already supplies the essential seams:

- `pure_projection` is compiler-generated, deterministic, and evaluated by the
  closed pure-expression evaluator;
- direct result validation happens in memory before the current optional
  bundle write;
- the executor's mutable execution dictionary is distinct from
  `StateManager`'s serialized `RunState`;
- `step_visits` and `current_step` carry the progress vocabulary needed for
  replay, and the explicit-profile feasibility mechanism now closes their
  former crash gap with atomic begin and settlement transactions;
- an additive root persistence profile can distinguish new value-free-shell
  state from historical bundle-backed state without reinterpreting old rows;
- the executable IR uses typed result addresses on several runtime surfaces,
  but `pure_projection.binding_refs` still carry validated compatibility ref
  documents and there is no existing typed replay dependency graph;
- lexical checkpoint records already treat a pure projection as having no
  completed-effect reference; and
- restore payload validation permits an effect barrier without serializing
  every derivable binding.

The historical checkpoint policy permits deterministic pure recomputation or
validated bundle reuse. The accepted explicit profile narrows that choice for
the eligible class: replay is the only resume path, and no new pure-result
bundle or pure-boundary checkpoint is written.
Existing root/callee checksums, executable and source identity, projection
integrity, bound-input validation, checkpoint validation, completed-effect
validation, and output-contract validation remain prerequisites.

## Problem

The current runtime persists one pure value several times:

1. a `steps.<PresentationKey>` result row in `state.json`;
2. a private `pure_projection` result bundle on disk;
3. a private artifact-version value in state; and
4. potentially a pure value in a lexical restore payload.

Those copies do not represent external work. They are deterministic functions
of executable code, bound inputs, and already-committed effect results. Their
presence enlarges state, broadens resume compatibility checks, and lets stale
derived bytes look like authority.

Simply deleting the rows is unsafe. The current positional resume planner
interprets a missing step result as unfinished work, and downstream reference
resolution expects earlier pure artifacts in the execution dictionary. A
correct change must reconstruct the values before the true unfinished
boundary without re-running a provider, command, transition, call, or
materialized view.

## Goals

- Replace value-bearing durable results for eligible successful pure
  projections with exact value-free completion shells.
- Reconstruct the same typed artifacts in memory before resumed execution
  reaches the true unfinished durable boundary.
- Keep all effect and public-boundary validation exactly as strict as today.
- Preserve diagnostics, declared artifacts, and workflow settlement values
  byte-for-byte for the same inputs and effect results.
- Treat interruption during pure evaluation as safely replayable without
  treating an unstarted node as completed.
- Reduce durable value count and bytes without adding a replacement
  pure-value ledger.
- Remain compatible with valid historical state and pure bundle records.

## Non-Goals

- Effect-identity memo keys, memo-first execution, or positional-resume
  replacement.
- Replaying, suppressing, or changing the reuse policy of any effect.
- Loop/recur checkpoint elision or replay of multiply visited pure nodes.
- Changing provider at-least-once behavior or completed-result reuse.
- Removing effect checkpoint records, call frames, loop progress, visit
  counters, finalization state, workflow outputs, artifact lineage, or
  evidence ledgers.
- Removing generated pure-bundle allocation fields from the compiled program
  while supported historical runs still depend on the old executable shape.
- Introducing an authored annotation, feature flag, new public type, or new
  effect identity.

## Decision

### Chosen approach: value-free completion shells plus a transient replay overlay

An eligible successful pure result is normalized exactly as today and placed
in the executor's in-memory `state["steps"]` overlay. The durable
`RunState.steps` entry is instead an exact value-free shell:

```json
{
  "name": "<presentation-key>",
  "step_id": "<qualified-node-id>",
  "visit_count": 1,
  "status": "completed",
  "exit_code": 0,
  "outcome": {
    "status": "completed",
    "phase": "execution",
    "class": "completed",
    "retryable": false
  },
  "result_storage": "derived_pure_replay.v1"
}
```

No output, text, JSON, artifact, debug, duration, bundle reference, or value is
permitted in that shell. The same exact shape is used in root and nested
call-frame state. Existing status/report consumers may show it as a completed
internal step without gaining result authority.

The runtime does not write or reuse a private pure-result bundle and does not
emit a pure-boundary checkpoint record. Before dispatching the true unfinished
durable boundary, it replaces only the required valid shells in the active
execution dictionary with recomputed full results. `RunState` retains the
shells.

Progress and completion have one closed interpretation:

- eligible-pure visit increment and `current_step` publication occur in one
  atomic state transaction;
- no visit, no matching `current_step`, and no shell means unstarted;
- a matching eligible-pure `current_step` means interrupted and safe to
  recompute;
- a valid matching completion shell means the visit settled successfully and
  its value is derived;
- a positive visit with neither matching `current_step` nor matching shell is
  invalid and fails closed rather than being inferred complete; and
- a durable failed or skipped full row keeps its existing meaning and is not
  elided.

Successful settlement atomically writes the shell and clears `current_step`
only after pure evaluation and the typed output contract succeed. Failure
atomically writes its ordinary full result and clears `current_step`.

### Alternatives considered

1. **Rowless completion inferred from `step_visits` and `current_step`.** The
   current executor persists the visit before publishing `current_step`, so a
   crash can expose a positive visit without proof that evaluation began.
   Closing that gap still leaves status/report consumers unable to distinguish
   an intentionally derived result from a missing row without recompiling the
   workflow. Rejected.
2. **Compact pure-value cache or digest rows.** This reduces bytes but leaves a
   second authority-like value channel and adds a schema that later work must
   migrate. Rejected.
3. **Unbounded replay from workflow entry.** This is superficially simple but
   would cross effects, loops, and live regions and could duplicate external
   work. Rejected.
4. **Delete all pure rows and let the positional planner restart at the first
   missing row.** The subsequent normal execution path would reach and
   re-execute already-completed effects. Rejected.

The chosen approach keeps existing effect rows as the durable barrier and
uses an existing `steps` entry as value-free completion evidence. It reuses
the existing pure evaluator, reference parser/resolver, state projection,
contracts, and runtime plan rather than creating a second interpreter. The M2
feasibility mechanism derives an identity-neutral typed dependency index in
memory; neither positional runtime dependencies nor raw pure binding refs are
treated as that graph.

## Eligibility Contract

A result is replay-eligible only when every condition holds:

| Condition | Requirement |
| --- | --- |
| Origin | The executable node is compiler-generated, not authored through a compatibility frontend. |
| Kind | The executable kind is exactly `pure_projection`. |
| Outcome | The visit completed successfully. Failed and skipped rows remain durable. |
| Region | The node is acyclic and executes at most once in its root or call frame. |
| Inputs | Every binding resolves from validated bound inputs, validated durable effect results, or an earlier replay-eligible projection in the same required dependency closure. |
| Outputs | The node has no public publication or external write. Its generated output contract is validated in memory. |
| Identity | The ordinary workflow, executable, source, projection, call-frame, and bound-input guards have passed. |
| Profile | The run or nested frame was created under `derived_pure_replay.v1`; an absent profile means historical behavior. |

Any routed cycle, loop/recur body, per-iteration node, ambiguous reachability,
or node whose input provenance cannot be proven falls outside the class and
keeps current persistence. Classification is derived from executable/runtime
plan facts; presentation names and family/module names are never classifiers.

The same rule applies recursively to an acyclic callee execution frame because
that frame has its own validated executable and state manager. The outer call
boundary remains a durable effect result. Iteration-local call frames and pure
nodes stay durable until a later loop design explicitly admits them.

## Runtime Model

### Persistence profile

A Workflow Lisp root or nested call-frame state explicitly initialized under
the replay profile carries:

```json
{
  "result_persistence_profile": "derived_pure_replay.v1"
}
```

This additive schema-2.1 field selects value-free pure-result semantics. It
contains no value, digest, completion list, or execution authority beyond
choosing the closed persistence interpretation. It must be written atomically
when the root/frame is initialized, before any visit can begin.

An absent field means the historical bundle-backed profile. An unknown value
fails closed. Resume never infers the profile from missing files or rows and
never adds the field to an old run. This prevents deletion or corruption of a
historical pure row from being mistaken for intentional elision.

### Transient replay dependency index

The current runtime plan's `dependencies` are positional/control topology, not
result dataflow, and `pure_projection.binding_refs` are closed compatibility
ref documents rather than `NodeResultAddress` objects. Neither is sufficient
replay authority.

After ordinary source, executable, and projection validation, the explicit
profile derives one process-local dependency index without changing serialized
IR or runtime-plan bytes:

1. Walk only the validator-owned ref-bearing fields consumed by the runtime,
   including pure binding refs and the selected consumer's typed/ref inputs.
   Do not infer dependencies from arbitrary prompt or command text.
2. Parse each already-validated ref through the existing closed surface-ref
   grammar and the exact root/call-frame projection catalog.
3. Bind workflow inputs to `WorkflowInputAddress` and step results to exact
   `NodeResultAddress`/block/loop/call addresses with field/member contracts.
4. Require presentation key, qualified node identity, scope, output member,
   payload binding name, and declared contract to agree. Unknown, duplicate,
   cross-frame, or unindexed refs fail closed.
5. Derive edges only from those addresses and prove the selected pure
   subgraph acyclic, single-visit, and outside iterative ownership.

The selected unfinished consumer's addresses seed the closure. When workflow
settlement is the next consumer, its already-typed output contract addresses
seed it. An interrupted eligible pure node seeds its own input closure but is
executed as the interrupted visit, not as read-only overlay preparation.

This index is identity-neutral: it is never serialized, never added to
checkpoint or executable digests, and never used to modify historical state.
If exact typing cannot be derived from the validated current executable, the
node is ineligible on fresh execution and resume fails before any effect when
a shell claims otherwise.

### Fresh execution

1. The runtime performs the ordinary guard checks, then atomically increments
   `step_visits` and records the matching `current_step`. No persisted state
   may expose the increment without that cursor.
2. The existing pure evaluator resolves bindings and evaluates the expression.
3. The existing output-contract validator creates the same typed artifact map.
4. On failure, the ordinary failed result is persisted and `current_step` is
   cleared in the same state transaction.
5. On success, the normalized result is inserted only into the active
   execution dictionary; the exact value-free completion shell is written to
   `RunState.steps` and `current_step` is cleared in the same state
   transaction.
6. Step summaries and status/report projections receive the value-free shell,
   not the transient value-bearing result.
7. No pure bundle, pure private artifact-version value, or pure checkpoint
   record is written.
8. A later effect or workflow settlement persists only its own authority.

If the process dies before the atomic settlement, the matching
`current_step` remains and resume recomputes the pure node. If it dies after
settlement, the valid shell proves that the eligible visit settled and resume
reconstructs its value. A positive visit without either witness is invalid,
not successful. Both valid outcomes are safe because evaluation has no
external effect.

### Resume

Resume preserves this order:

1. Load the durable state without mutating it.
2. Run the existing root/callee checksum and projection-integrity audits.
3. Validate the persistence profile, compiled eligibility classification, and
   every eligible pure persistence surface. Under the replay profile, a
   successful eligible entry must be the exact value-free shell. A
   value-bearing successful row, pure bundle, pure private artifact-version
   value, pure checkpoint record, or pure restore-binding value is a profile
   conflict and fails before planning. Failed/skipped full rows remain valid.
   This preflight occurs before executor prologue recovery, bound-input
   validation writes, or existing call-frame constructor persistence. An
   existing nested frame is loaded read-only and audited before any update.
4. Build the transient typed dependency index above.
5. Determine the true unfinished durable boundary exactly once and carry that
   decision through checkpoint selection and dispatch. A valid shell is terminal;
   a matching `current_step` is interrupted; an absent shell with no visit is
   unstarted; and every contradictory progress combination fails closed.
6. Build the default-resume checkpoint candidate set. Under the replay
   profile, replay-eligible pure points are excluded because they have no
   durable checkpoint record. Historical-profile and noneligible pure points
   keep current candidacy. The existing unique-nearest rule then selects among
   actual durable candidates, and a missing, ambiguous, or invalid nearest
   durable record still fails closed.
7. If filtering leaves no prior durable candidate, admit
   `VALIDATED_FRAME_ENTRY_REPLAY` only when the validated active prefix from
   root/call-frame entry contains bound inputs and successful replay-eligible
   shells but no node that owns a durable checkpoint. It restores no record
   and uses the already-validated frame inputs as leaves. If any prior durable
   boundary should exist, record absence remains a terminal checkpoint error.
8. Activate any validated lexical restore overlay selected at the nearest
   actual durable boundary.
9. Starting from the unfinished boundary's typed inputs, build only the
   required `NodeResultAddress` dependency closure. Leaves may be validated
   bound inputs or validated completed effect artifacts. A pure dependency may
   recursively depend on earlier admitted pure nodes. The closure must not
   linearly dispatch or traverse effect nodes.
10. Re-evaluate that closure in topological order into a transient overlay.
   Overlay identity includes root/call-frame scope, executable node identity,
   result address, and visit identity; a presentation name alone is never a
   replay key.
11. Apply the same typed output contracts used during fresh execution.
12. Continue at the already-selected unfinished durable node through the
   ordinary executor. If it is an interrupted eligible pure node, validate and
   reuse its existing cursor and visit count without another increment,
   execute that node once through the ordinary pure evaluator, then atomically
   settle the same visit to its shell or full failure and route its successor.
   Read-only overlay preparation never clears or settles the cursor.

If final workflow output or finalization resolution, rather than another
effect, is the next consumer, that consumer's result addresses seed the same
dependency-closure algorithm.

Replay never increments visits, starts a step, emits a checkpoint, writes an
output path, publishes an artifact, runs a command/provider/call/transition/
view, or changes durable state. It is preparation for reference resolution,
not a second execution visit.

### Durable/transient split

| Surface | Durable under `derived_pure_replay.v1`? | Reason |
| --- | ---: | --- |
| Successful eligible pure value | No | Deterministically derived. |
| Successful eligible pure completion shell | Yes | Value-free visit settlement and status/report topology. |
| Pure private result bundle | No new writes | Deterministically derived; old records remain readable. |
| Pure private artifact-version value | No | Same derived value under another key. |
| Pure checkpoint record | No new writes | Not an effect boundary. |
| Failed pure result | Yes | Diagnostic and retry boundary. |
| Skipped/control result | Yes | Reached-route proof, not a pure value cache. |
| `step_visits` and `current_step` | Yes | Atomic execution progress and interruption witness. |
| Provider/command/resource/call results | Yes | Effect authority. |
| Materialized-view state/evidence | Yes | Existing deterministic-view contract is unchanged. |
| Loop/recur and per-iteration results | Yes | M3c is not selected. |
| Public and non-pure artifact lineage/consumes | Yes | Publication/freshness authority. |
| Workflow inputs, outputs, finalization | Yes | Public run boundary. |
| Result persistence profile | Yes | Fail-closed old/new interpretation; carries no result value. |
| Replay overlay | No | Process-local derived values only. |

## Checkpoint And Bundle Contract

The runtime plan may continue to describe a pure projection and its existing
generated output path so that the executable identity of supported historical
runs does not change solely for M3a. The new runtime does not read or write
that path for an eligible projection. Removing the dead compiled allocation is
a later compatibility cleanup, not part of this behavior change.

New replay-profile checkpoint records are emitted only after durable
boundaries. Replay-eligible pure points are removed from the default-resume
candidate set before the existing unique-nearest durable selection; they are
not treated as missing durable records. Noneligible and historical pure points
keep current checkpoint behavior. Once the candidate set is filtered, no
search may skip past a missing, malformed, ambiguous, or invalid nearest
durable record.

`VALIDATED_FRAME_ENTRY_REPLAY` is the only zero-record case. It is available
only when the restart point has no prior actual durable checkpoint owner and
the entire reached prefix consists of validated frame inputs plus successful
eligible shells. It is not a fallback after an unusable durable record. Root
and call-frame cases require their ordinary input/projection guards and have
both-direction tests.

A restore payload does not serialize a value or
`private_artifact_ref` for a `pure_binding` whose descriptor has a deterministic
value document/result address. The executable runtime plan carries the recipe;
the checkpoint binding-schema digest binds that plan, while the binding entry
is absent from the record. Resume supplies the value through the dependency
closure before continuation. Completed-effect references and their validation
remain unchanged.

Historical-profile checkpoint records and pure bundle references remain on
their existing reader, validation, and reuse path. A malformed historical
bundle therefore retains its current failure behavior. Historical rows and
sidecars are not backfilled, rewritten, deleted, or silently reinterpreted
merely because a run is inspected or resumed.

Under the replay profile, coexistence is fail-closed rather than a migration
path. A successful eligible pure entry must be the exact shell above. Any
value-bearing successful row, bundle at its compiled private path, matching
private artifact-version value, checkpoint record, or restore-binding value
for that node is rejected as `profile_conflict`. This audit applies separately
to every nested call frame before its overlay is constructed.

## Failure Contract

Replay fails before any later effect dispatch when:

- the replay profile, progress witness, completion shell, or forbidden
  coexistence audit is invalid;
- an expected durable effect result is absent, nonterminal, malformed, or
  contract-invalid;
- an eligible node has ambiguous reachability or multiple-visit ancestry;
- a required binding cannot be resolved from the admitted sources;
- the pure evaluator fails; or
- the recomputed value violates its output contract.

The stable top-level diagnostic is `pure_result_replay_unavailable`. Its
context contains only the executable step identity, source origin when
available, and one reason:

- `durable_input_missing`
- `durable_input_invalid`
- `progress_witness_invalid`
- `profile_conflict`
- `dependency_index_invalid`
- `reachability_ambiguous`
- `multiple_visit_region`
- `binding_unresolved`
- `evaluation_failed`
- `output_contract_invalid`

The underlying typed pure-expression or output-contract diagnostic is retained
as a nested cause when one exists. No failure falls back to a historical pure
value, restarts the whole workflow, or silently re-pays an effect.

Default-resume checkpoint selection failures retain their existing
checkpoint diagnostic family. Filtering an admitted replay-eligible pure
point is not a relaxation of the nearest-durable rule: after filtering, a
missing or invalid nearest actual durable record remains terminal and the
runtime never scans past it.

## Compatibility And Migration

- State schema remains `2.1`; `result_persistence_profile` is additive. Absence
  of an eligible successful pure shell after a recorded visit is invalid under
  the replay profile. The exact shell, executable kind, profile, visit, and
  cursor must agree.
- Old pure rows, bundles, and checkpoint bindings remain immutable and keep
  their historical validation/reuse behavior. They are never silently
  interpreted as replay-profile state.
- Unsupported or mismatched workflow/executable/checkpoint state still fails
  under the existing diagnostic before replay.
- No state upgrader, backfill, runtime flag, or dual-write phase is needed.
- Existing compiled pure-bundle path carriage remains temporarily to preserve
  program identity. Its later deletion requires its own supported-run
  compatibility check.
- Status and persisted step-summary/report surfaces show the exact value-free
  completion shell for each successful eligible visit. They must not expose a
  reconstructed or formerly persisted pure value. Run state, logs, and reports
  therefore retain inspectable step-level completion evidence while treating
  the derived value as non-authoritative. Declared workflow outputs,
  artifacts, diagnostics, and settlement values remain unchanged.

## Completed M2 Feasibility Fixture

The M2 feasibility proof uses one generic acyclic program with this shape:

```text
bound input
    -> pure projection A
    -> deterministic counted effect E1
    -> pure projection B (uses A and E1)
    -> interrupted effect E2
    -> workflow settlement
```

The fixture uses the real Workflow Lisp compiler, runtime plan, state manager,
pure evaluator, output-contract validator, resume planner, and executor. Only
the external effect adapter is deterministic and counted. It proves:

1. a clean run and an interrupted/resumed run settle to byte-equal diagnostics,
   declared artifacts, and workflow outputs;
2. successful A and B have exact value-free completion shells and no durable
   values, bundles, pure checkpoint records, private artifact-version values,
   or pure restore-binding values;
3. E1 executes exactly once and its durable result is the replay input;
4. B is recomputed before E2 resumes;
5. crash injection immediately before and after the atomic visit/cursor
   publication can never expose a positive visit without either a matching
   cursor or completion shell;
6. a crash while A or B is `current_step` safely recomputes it;
7. an interrupted A or B resumes and settles the existing visit without
   incrementing it;
8. a crash after A settles but before E1 begins uses
   `VALIDATED_FRAME_ENTRY_REPLAY` from bound inputs;
9. B's omitted checkpoint does not hide E1's valid nearest durable record,
   while an absent or corrupt E1 record still fails closed rather than scanning
   farther back;
10. the transient typed dependency index derives exact addresses from the
    validated compatibility ref documents without changing serialized IR;
11. a replay-profile value-bearing pure row, bundle, lineage value, checkpoint,
   or restore binding fails as a profile conflict in both root and nested
   state;
12. a missing/invalid E1 result or ambiguous/multiple-visit classification
   fails before E2;
13. a loop/recur control fixture retains its current pure result rows and
    checkpoint behavior; and
14. status/report consumers expose the exact value-free completion shells
    without changing public artifacts, diagnostics, or settlement.

This fixture is both the M2 executable feasibility proof and the first RED/GREEN
acceptance spine for M3a. It does not call a replay helper directly. The
dependency-index tranche landed at `159a8f5e`, atomic witness persistence at
`5644bd73`, checkpoint/runtime integration at `cf0490d1`, and completed-resume
compatibility correction at `ce02cd17`. M2 component (a) is historical
complete after the final broad gate and ordered reviews approved its exact
bytes. M3a is eligible but unselected and still requires a separate reviewed
activation plan.

Ordinary CLI-created roots and fresh call frames remain historical-profile.
M2 proves the generic root/frame classification and conflict machinery, while
automatic fresh-frame profile activation and positive nested-frame rollout
remain M3a responsibilities.

Fresh evidence collected 100 tests and passed the post-correction 11-module
feasibility matrix with 694 tests in 8.31 seconds (log SHA-256
`f374f391c96e6b1535bd212ac707cf77feae6f44fa630dfb4664c5b6e54b1336`).
Canonical executable IR SHA-256
`d24c09692754cf5d3846f99a694a6e108013ee0a6764878a7f5a1101c7f224cc`
and runtime-plan SHA-256
`1857767685cf7e67d43acbb819105eb8ce9e5b6b62fc720bffef7ca365762bbb`
are equal across profiles. Outputs, artifacts, diagnostics, and settlement have
exact parity; replay calls are `[E1, E2]`, E1 executes exactly once, historical
pure bundles count 2, replay pure bundles count 0, and A/B replay rows are exact
shells.

Equivalent resumed samples reduce durable leaves from 80 to 72 (8 fewer;
10.0%), `state.json` from 4,975 to 4,636 bytes (339 fewer; 6.814070%), and
run-owned sidecars from 26,452 to 15,561 bytes (10,891 fewer; 41.172690%).
The public historical-profile CLI smoke completed with output `count=3`,
`label=tick`, and omitted `result_persistence_profile`. Source change from
`09c286dc` through `ce02cd17` is orchestrator +3,518/-84 across 12 files and
tests +5,911/-15 across 12 files, total +9,429/-99 across 24 files (numstat
log SHA-256
`e8144fdb40bf2ab36a9abb197fb18bd9e8672004e54ee5e82026ab829aff037c`).
The consolidated 3,157-byte measurement log has SHA-256
`6f735d18c315cd746bd10a3d940ca8ec52c032ec96658fea7a18bd9c5c22483f`.

The first broad candidate exposed one completed-resume compatibility regression:
9,867 tests passed, 19 skipped, and one Q4 judgment-view evidence-loss test
failed because a completed run with no restart node no longer traversed its
terminal rows for evidence revalidation (log SHA-256
`dab15bbc475e88470060dc0234c099361d777b2c9117808633bdd19c9fb990f3`).
The generic lifecycle correction `ce02cd17` preserves the historical
completed-state sweep except for exact phased reuse while keeping a running
post-body interruption epilogue-only. It passed
`M2_FEASIBILITY_TASK3_CORRECTION_SPEC_APPROVED` then
`M2_FEASIBILITY_TASK3_CORRECTION_QUALITY_APPROVED`, 160 affected-module tests,
and the post-correction 694-test matrix.

The routing selector passes 67 tests in 1.48 seconds. The corrected broad
non-security gate passes 9,868 tests with 19 skipped and 5 warnings in 147.90
seconds (log SHA-256
`76308a56635e67d21a84f1254b812e41d4eebde7dc2444fe9cb6dd31a1e7c637`).
Ordered final review passed `M2_FEASIBILITY_FINAL_SPEC_APPROVED` then
`M2_FEASIBILITY_FINAL_QUALITY_APPROVED` against the same closure bytes.

## Verification Strategy

### Unit and contract tests

- Outcome persistence: successful eligible pure values are transient and exact
  value-free shells persist; failed and skipped full rows persist.
- Atomic progress: visit increment plus cursor publication and shell/failure
  plus cursor clearing are indivisible; injected pre/post-write crashes leave
  only valid witness combinations.
- Interrupted visit: resume retains the exact eligible-pure visit ordinal,
  settles that cursor once, and never calls the ordinary visit increment.
- Profile interpretation: absent historical state keeps bundle-backed
  validation; the exact replay profile admits only exact completion shells;
  unknown profiles fail closed; a damaged historical row cannot select replay.
- Completion witness: visit, current-step, and shell combinations map to
  unstarted, interrupted, derived-complete, durable failure/skip, or a named
  fail-closed invalid state.
- Replay ordering: chained pure projections resolve from bound inputs and
  durable effect artifacts.
- Dependency typing: validated compatibility ref documents derive exact
  transient addresses; unknown fields/members/scopes, positional-only edges,
  and serialized-IR changes are rejected.
- Reachability: inactive branch projections do not evaluate; ambiguity and
  cycles fail or remain durable according to eligibility.
- Checkpoints: pure points emit no new record; effect records omit derivable
  pure binding values but retain effect refs and validation; candidate
  filtering skips eligible pure points but never an invalid nearest durable
  record; a pure-only prefix admits validated frame-entry replay, while a
  missing prior durable owner still fails.
- Compatibility: a valid historical pure row/bundle remains readable but
  stays on the historical path; corrupt historical bundles retain their
  existing failure.
- Mixed-profile tampering: replay-profile value rows, bundles, private lineage
  values, checkpoint records, and restore bindings all fail closed in root and
  nested frames.

### Integration and parity

- Run the feasibility fixture through fresh execution and a real
  `WorkflowExecutor(...).execute(resume=True)` path.
- Compare canonical diagnostics, declared artifacts, and settlement outputs
  between persisted-current and replay modes.
- Count effect adapter calls and require no replay duplication.
- Record durable value count and state/sidecar byte count before/after; both
  must decrease for the fixture.
- Run owning pure-projection, resume, lexical-checkpoint, call-frame, state,
  and state-projection suites, then the broad non-security suite.

No test may assert prompt prose. No evidence report, debug projection, or
fixture-only marker may control runtime behavior.

## Declarative Acceptance Scenarios

### Interrupted after a committed effect

Given a validated run in which E1 is committed, B completed as an eligible
pure projection, and E2 is the interrupted current effect, `resume` validates
the run, reconstructs A and B in memory, reuses E1's durable result, and
continues at E2. E1's call count remains one. The final declared outputs equal
the clean-run outputs. Durable state contains A and B's exact completion shells
but neither value.

### Interrupted during pure evaluation

Given a validated run whose `current_step` is B and whose visit count includes
B but has no terminal B shell, `resume` evaluates B again and then continues.
No effect before or after B is invoked by replay preparation. Such a cursor and
visit can only have been published atomically. Resume does not increment the
visit; success or failure settles that same cursor atomically before successor
routing.

### Crash between progress writes

The replay profile has no valid state in which a newly incremented eligible
pure visit exists without either its matching `current_step` or its completion
shell. Crash injection around the atomic begin operation observes the old
unstarted state or the complete interrupted state. A manually constructed gap
fails with `progress_witness_invalid`.

### Omitted pure checkpoint

Given E1's valid durable checkpoint followed by replay-eligible B and
interrupted E2, default resume filters B from the candidate set and selects E1
under the ordinary unique-nearest rule. If E1's selected record is absent or
invalid, resume fails under the existing checkpoint diagnostic and does not
scan to an earlier record.

### Pure prefix before the first durable boundary

Given A's valid shell, no prior effect/checkpoint owner, and E1 not yet
started, resume admits `VALIDATED_FRAME_ENTRY_REPLAY`, reconstructs A from the
validated frame input, and begins E1 normally. If the prefix contains a node
that should own durable checkpoint authority, the same zero-record state fails
closed rather than using frame entry.

### Mixed replay-profile state

Given a replay-profile run containing B's value-bearing success row or any
forbidden B bundle, lineage value, checkpoint record, or restore binding,
resume fails with `profile_conflict` before overlay construction or effect
dispatch. The same rule applies inside a nested call frame.

### Invalid replay source

Given a run whose E1 durable row is missing or fails its existing contract,
replay stops with `pure_result_replay_unavailable` before E2. It does not use a
historical B row or bundle and does not dispatch an effect.

### Excluded recurrent node

Given a pure projection in a loop/recur or other multiply visited region, the
runtime retains its current durable result behavior. M3a makes no replay claim
for that node.

## Success Criteria

The completed implementation supplies the public run/resume fixture and both
directions of every load-bearing rule. It introduces no state schema beyond the
additive profile, no value cache, no effect identity, and no second interpreter.
The profile and exact-shell `result_storage` tag are the only new durable
discriminators, and neither contains a pure value.

M2 is complete because the fresh closure gates prove that durable value count
and state/sidecar bytes both decrease and the exact candidate passed ordered
specification then quality review. The external closure record binds the
committed bytes without becoming runtime or repository authority.

## Stop / Revise Criteria

Revise rather than implement if:

- correct replay requires executing any effect;
- the runtime cannot distinguish a settled eligible visit from an interrupted
  one using the atomic progress fields plus exact completion shell;
- checkpoint validation must accept an unvalidated effect result;
- an acyclic eligibility classifier cannot be derived from executable facts;
- public artifacts or workflow settlement require a durable internal pure
  value;
- valid supported runs would require an untested program-identity migration;
  or
- the implementation cannot reduce durable bytes without hiding behavior in a
  fixture or weakening a gate.

Evidence of positional invalidation re-spend meeting the owner-recorded
threshold reopens component (b) as a separate design decision; it does not
silently expand this design.

## Documentation Impact

The M2 closure updates:

- `specs/state.md` for the additive replay profile and exact value-free shell;
- the lexical checkpoint design's pure policy from reuse-or-recompute to
  replay-only for the eligible class;
- `docs/design/workflow_lisp_state_layout.md` to distinguish retained compiled
  path carriage from new runtime writes;
- `docs/capability_status_matrix.md` after implementation; and
- substrate/index routing and their routing tests at each gate.

The E-series roadmap is not edited here. Its persistence contracts remain
subordinate to the accepted M2 result through its owner-maintained routing.

## Implementation Handoff

The reviewed M2 feasibility plan landed the generic fixture and transient index
at `159a8f5e`, the explicit profile and atomic witness persistence at
`5644bd73`, runtime/checkpoint integration at `cf0490d1`, and the
completed-resume compatibility correction at `ce02cd17`. The fixture
selects the profile only through generic state initialization; it cannot inject
a helper result or control replay through test-only state.

After the final M2 gates and ordered reviews bound this closure, a separate
reviewed M3a plan may activate the profile for ordinary new Workflow
Lisp roots and fresh non-iterative call frames, add positive nested-frame
coverage, and run activation-specific narrow and broad gates. This design and
its completion do not themselves select or implement that activation.

Likely implementation owners are:

- `orchestrator/workflow/outcomes.py`
- a small replay/classification module under `orchestrator/workflow/`
- `orchestrator/state.py`
- `orchestrator/workflow/call_frame_state.py`
- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/resume_planner.py`
- `orchestrator/workflow/steps/pure_projection.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow_lisp/lexical_checkpoints.py`
- `orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py`
- `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- focused pure-projection, resume, checkpoint, call-frame, and state tests

The implementation plan must preserve explicit ownership boundaries and avoid
growing `executor.py` with the replay algorithm.
