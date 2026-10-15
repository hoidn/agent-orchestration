# Workflow Lisp Private Runtime State And Consumer Value Flow: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_private_runtime_state_and_consumer_value_flow.md](../../design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md).

## 9. Track R: Private Lexical Execution Checkpoints

### R0: Resume semantics census and characterization

Record current resume behavior, generated path identity, loop-frame state,
`resume-or-start` usage, run-state path flow, and fail-closed schema checks.

Acceptance:

- current resume fixtures are characterized;
- every resume-only authored field is classified;
- no domain resource is mislabeled as checkpoint-only.

### R1: Checkpoint schema and shadow emission

Emit checkpoint records beside current runtime state without using them for
restore.

Acceptance:

- checkpoints include schema version, WCC identity, binding schema, effect
  policy, and source-map provenance;
- checkpoint emission is deterministic for the same executable/run/frame;
- mismatch diagnostics exist and fail closed in shadow validation.

### R2: Restore for pure and structured regions

Restore pure bindings, `let*`, `match`, loop counters, branch proofs, and
structured control positions from checkpoints where no unsafe pending effect is
involved.

Acceptance:

- branch-local and loop-local resume fixtures restore without authored
  run-state paths;
- variant proof state is restored only when proof identity matches;
- stale checkpoint and executable drift fixtures fail closed.

### R3: Effect-boundary resume policies

Attach resume policy to every generated effect boundary.

Acceptance:

- pure, provider, command, workflow call, materialized view, and transition
  boundaries all emit policy metadata;
- unsafe non-idempotent command replay is rejected;
- provider reuse requires validated structured-output evidence.

### R4: Transition-aware resume

Integrate checkpoints with transition audit and idempotency keys.

Acceptance:

- committed transitions are not blindly replayed;
- idempotent transition replay returns the committed result with audit evidence;
- resource version conflicts invalidate dependent checkpoints.

### R5: Resume-only authored plumbing retirement

Remove or hide path fields whose only purpose is checkpoint/resume recovery.

Acceptance:

- promoted boundaries do not expose resume-only state paths;
- loop state carries typed values and resources, not checkpoint paths;
- `resume-or-start` remains for domain reusable state, not program-position
  recovery.

### R6: Default flip and legacy cleanup

Make lexical checkpoints the default resume substrate for eligible WCC regions,
with compatibility behavior retained only for historical runs.

Acceptance:

- default restore uses checkpoints in eligible regions;
- positive next-record absence may restore exactly one uniquely ordered,
  globally checkpoint-ID-unique, fully validated nearest prior effect boundary
  while preserving the original restart node;
- absent, ambiguous, unordered, unsafe, invalid, or present-but-unusable
  candidate state fails closed without scanning older boundaries;
- legacy step-granular resume remains available for historical compatible runs;
- cleanup removes dead resume-only public plumbing after evidence proves no
  current consumer.


### 7.3 Lexical checkpoint content

A checkpoint records enough private runtime data to resume a WCC execution
region:

```text
checkpoint {
  program_identity
  lowering_schema_version
  source_module_digest
  wcc_node_id
  lexical_environment_digest
  typed_bindings
  active_variant_proofs
  loop_frame_state
  pending_effect_policy
  completed_effect_refs
  resource_version_observations
}
```

Typed bindings may contain validated typed values or references to validated
runtime-owned bundles. They must not contain arbitrary Python objects, open
file handles, unvalidated stdout, or paths treated as semantic authority.

### 7.4 Checkpoint validity

A checkpoint is valid only when all of the following match:

- workflow/module identity;
- WCC lowering schema version;
- executable program digest;
- checkpoint schema version;
- typed binding schemas;
- effect-boundary policy;
- resource version observations for resource-sensitive regions; and
- structured-output bundle hashes for completed provider/command effects that
  are being reused.

Mismatch fails closed. The runtime may recompute from a prior safe boundary, but
it must not silently reuse a stale checkpoint.

For eligible WCC default resume, node-local restore remains primary. Only when
the restart node owns lexical checkpoint metadata and restore selection
positively reports typed `record_absent` may the runtime consider a prior
effect boundary. Only a missing canonical index or a canonical index whose
program-point and allocation identities match the runtime-plan point and whose
`records` list is valid and empty establishes absence. Foreign or stale index
identity is present-unusable evidence and fails closed. It derives the complete
nearest-prior candidate set solely from `runtime_plan.ordered_node_ids`;
exactly one candidate is required, and
its checkpoint ID must occur exactly once across all
`runtime_plan.lexical_checkpoint_points`, including older, later, and
non-effect points, before it may pass through the ordinary restore validator
unchanged. Resume continues from the original restart node with the validated
prior payload. An index record ID is one safe filename component and cannot
introduce path structure. Index entries may reference only the exact canonical
workspace-relative record path for their record ID, point, and storage scope.
That path must be a lexical direct child of the canonical record family and,
after normalization and symlink resolution, remain a direct child of the
resolved family below the resolved workspace. Absolute, escaping, or symlinked
paths fail closed before record I/O. Entry identities must match the point and
loaded record, which still passes the complete checkpoint-record and restore
validators. Both index and record JSON are opened beneath a trusted workspace
directory descriptor: every parent uses descriptor-relative directory open
with no-follow semantics, and the final file uses descriptor-relative
no-follow and nonblocking open, is verified as regular with `fstat`, and is
decoded from that already-open descriptor. A FIFO or other nonregular target
therefore fails closed without waiting for a peer. There is no pathname reopen
after validation. Only `FileNotFoundError` for the canonical index establishes
absence; unsupported descriptor/no-follow/nonblocking operation, symlinked or
invalid parents, permissions, nonregular targets, and mutation during read fail
closed as present-unusable. Missing or duplicate order, no candidate, global
checkpoint-ID duplication, ambiguity, present-but-unreadable, malformed,
foreign, or incomplete index/record state, unsafe evidence, or validation
failure all fail closed. Default resume never skips an invalid nearest point to
search older checkpoints.

### 7.5 Effect-boundary resume policies

Every effect boundary has an explicit policy:

| Effect kind | Resume behavior |
| --- | --- |
| Pure projection | Recompute or reuse deterministic checkpoint. |
| Materialized view | Regenerate from typed value unless durable publication policy says to preserve existing bytes. |
| Provider call | Reuse only validated structured output with matching prompt/input contract and hash evidence. |
| Command / certified adapter | Reuse only declared output bundle or certified resume protocol. |
| Resource transition | Use idempotency key and transition audit; do not replay as a blind command. |
| External non-idempotent effect | Fail closed unless a certified resume protocol exists. |

The policy is part of Semantic IR and executable IR evidence.

## 11. Dependencies And Sequencing

Prerequisites:

- WCC schema 2 identity is available for target regions.
- `RunCtx`, resources, transitions, materialized views, and boundary authority
  classes are accepted in the frontend baseline.
- StateLayout can allocate checkpoint, publication, and bridge roles.
- Semantic IR and executable IR can carry checkpoint and rendering evidence.

Suggested sequencing:

```text
U0 shared census
  -> R1/R2 checkpoint shadow and pure-region restore
  -> R3/R4 effect and transition-aware resume
  -> R5/R6 resume-only plumbing retirement

U0 shared census
  -> C0 renderer seam verification
  -> C1/C2 prompt and observability rendering
  -> C3/C4 publication and bridge policy
  -> C5 render-only plumbing retirement
  -> C6 author-facing rendering ergonomics
```

Track R and Track C may proceed in either order after U0/C0/R0 if their touched
runtime files are not in conflict. A selector may choose one track, both tracks,
or a narrow shared slice. Neither track may claim the other track's acceptance
evidence.

### 16.1 Resume without authored run-state plumbing

Initial state: a parent `.orc` drain has entered a nested loop and completed a
pure branch selection.

Entrypoint: interrupt after checkpoint shadow emission, then resume the same run
with the same executable identity.

Expected result: the runtime restores the lexical loop position and typed
bindings from a private checkpoint. No public `run_state_path`,
`loop_state_path`, or generated checkpoint path is required.

Forbidden result: the workflow resumes only because the author carried a
runtime bookkeeping path through loop state.

### 16.2 Transition wins over checkpoint

Initial state: a checkpoint observes resource version `v1`, then an external
valid transition advances the resource to `v2`.

Entrypoint: resume from the checkpoint.

Expected result: the checkpoint is invalidated or the region recomputes from a
safe boundary; transition audit remains authority.

Forbidden result: checkpoint restore overwrites or ignores the newer resource
version.

## 18. Summary Recommendation

Use this umbrella as the next cleanup target only if the implementation driver
wants one coherent objective: eliminate authored runtime/file plumbing from
Workflow Lisp without weakening semantic authority. Keep the tracks independent:
Track R makes resume private and lexical; Track C makes rendering
consumer-owned. The shared result is a simpler `.orc` style where authors pass
typed values and resources, while the runtime owns execution memory and
consumers own representations.
