# Provider Live Binding T3 Behavior Simulation

- **Date:** 2026-07-23
- **Decision:** `ADOPT_NARROWLY`
- **Scope:** Stage 7 control-path choice after the adverse T3 probe
- **Compared authority:** V0 Git blob
  `641ceb35a5e421d28a9d6013ee82527b762ce13b`
  (`sha256:9143daacd4fa1eecc48a68b9306f16bed58b18f801dab5a2b1e71c922d192ff9`)
  versus V1
  `docs/design/workflow_lisp_provider_live_binding.md`
  (`sha256:9c2a2f333eb277154c8a98a0897cf9b390339a42fcf8a7702ce5582824ada113`)

## Inputs And Exclusions

Inputs:

- the Stage 7 entry and stop/revise gates in
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`;
- the proposed same-invocation `send-keys` design preserved at Git blob
  `641ceb35a5e421d28a9d6013ee82527b762ce13b`;
- the current provider template, registry, executor, provider-session, and
  workflow-executor implementations;
- installed `codex-cli 0.145.0`, Claude Code `2.1.211`, and tmux `3.4`;
- fresh controlled T3 probes against the installed Codex and Claude
  interactive clients; and
- the existing provider-session fresh/resume contract.

Excluded:

- provider-native duplex protocol integration (`codex app-server`, Claude
  stream-json, and remote-control transports);
- repeated or unbounded steering;
- cross-run supervision;
- general background/join workflow primitives; and
- all security analysis and security-specific implementation work, by the
  user's standing scope direction.

## Compared Versions

### V0 — proposed direct TTY steering

Two provider invocations run concurrently. The supervisor receives the
worker's tmux target and uses ordinary `capture-pane` and `send-keys` at any
time. The runtime does not mediate interaction. Each member remains one
exec-per-turn process.

### V1a — TUI interrupt and immediate new turn

The supervisor sends the provider client's interrupt key, then submits a new
message in the same interactive client. The client owns interruption and
turn replacement.

### V1b — runtime-controlled turn-boundary resume

The worker and supervisor run concurrently through ordinary provider
invocations. The supervisor observes a live, non-authoritative tmux mirror
and returns a validated directive:

```json
{"variant": "CONTINUE"}
```

or:

```json
{"variant": "STEER", "guidance": "Free-form corrective guidance"}
```

For `STEER`, the runtime requires a unique stable worker session id, reaps the
worker leader, verifies that the runtime-owned PGID is empty, joins executor
and capture work, and performs exactly one provider-session resume turn with
the guidance. Only the winning completed worker turn's validated result bundle
is authoritative.

## Scenario Setup

1. **Target case — wrong long-running approach.** A worker starts a
   long-running tool after choosing the wrong approach. A supervisor detects
   the problem while the worker is active and asks it to change course.
2. **Hard case — ambiguous cancellation.** The worker has started a child
   process and the runtime cannot prove that its owned process group stopped
   and all local executor/capture work joined.
3. **Small case — no correction needed.** The supervisor observes acceptable
   work and returns `CONTINUE`.
4. **Unsupported-provider case.** The selected worker template has no
   validated session-resume capability or cannot expose a stable session id
   before the active turn settles.
5. **Controller-crash case.** The workflow controller disappears after
   member launch but before the group terminal commit.
6. **Workspace-effect case.** A cancelled worker or concurrent supervisor
   changes files before the selected result is published.

## Probe Reproduction

### Codex interactive queue/interruption probe

Launch:

```bash
tmux new-session -d -s stage7-codex-t3-repro -- \
  codex --no-alt-screen \
  --dangerously-bypass-approvals-and-sandbox \
  --model gpt-5.6-terra
```

Driver sequence:

```bash
tmux send-keys -t stage7-codex-t3-repro -l \
  'Use the shell tool to run: sleep 60. After it finishes, reply with exactly ORIGINAL and nothing else.'
tmux send-keys -t stage7-codex-t3-repro Enter

# After the UI reported active work and one background terminal:
tmux send-keys -t stage7-codex-t3-repro -l \
  'Instead reply with exactly STEERED and nothing else.'
tmux send-keys -t stage7-codex-t3-repro Enter
tmux send-keys -t stage7-codex-t3-repro Tab
tmux send-keys -t stage7-codex-t3-repro Escape
```

Decisive normalized capture while active:

```text
Working (... esc to interrupt) · 1 background terminal running
Queued follow-up inputs
  ↳ Instead reply with exactly STEERED and nothing else.
```

Decisive normalized capture after the interruption/queued-turn transition:

```text
ORIGINAL
› Instead reply with exactly STEERED and nothing else.
STEERED
1 background terminal running
```

The exact timing and prose are not the contract. The structural facts are:
ordinary input became a queued follow-up, the later turn ran, and local tool
work was still reported alive. This disproves V0's direct active-turn input
and process-ownership assumptions.

An earlier exploratory Claude TUI probe also processed submitted guidance only
after the original response. Its raw capture was not retained, so it is
corroborating context rather than the reproducible decision evidence.

### Codex real JSONL identity probe

Command:

```bash
cd /tmp
codex exec --json \
  --dangerously-bypass-approvals-and-sandbox \
  --skip-git-repo-check \
  'Reply with exactly OK and do not use tools.'
```

Exact output shape:

```json
{"type":"thread.started","thread_id":"019f929b-bea9-76a2-955d-5991618b6f34"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}
{"type":"turn.completed","usage":{"input_tokens":16911,"cached_input_tokens":13056,"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}
```

The identity and text values themselves are incidental. The load-bearing
facts are that `thread_id` is available before completion, assistant output
is nested at `item.completed.item.text`, and only exact `turn.completed`
marks the successful turn boundary; `item.completed` is earlier.

## Evidence Ledger

| Fact | Classification | Evidence |
|---|---|---|
| Current provider `STDIN` mode delivers the initial prompt and then closes stdin. | observed | `orchestrator/providers/executor.py` |
| Current builtin Codex commands declare fresh and resume exec turns, but the current parser is incompatible with installed real-shape `thread_id` and suffix-misclassifies `item.completed` as terminal. | observed | `orchestrator/providers/registry.py`, `orchestrator/providers/executor.py`, fresh real JSONL probe |
| Claude accepted a message during a running tool but processed it only after emitting the original answer. | observed | fresh T3 tmux probe |
| Codex displayed that ordinary input would be submitted after the next tool call. | observed | fresh T3 tmux probe |
| Codex Escape interrupted the model turn, accepted the new message, and left the prior shell tool running in the background. | observed | fresh T3 tmux probe |
| The proposed V0 design requires ordinary TTY input to affect the active turn. | specified | Git blob `641ceb35a5e421d28a9d6013ee82527b762ce13b` |
| Stage 7 routes an adverse T3 outcome to turn-boundary redesign before planning. | specified | procedure-first roadmap |
| A runtime-owned process group can provide a stronger cancellation boundary than a client-owned TUI interrupt, if the leader/PGID/future/capture boundary is verified before resume. | inferred | current process-tree support plus proposed strengthening |
| Installed Codex emits a preterminal `thread.started.thread_id` and uses exact `turn.completed` for the turn boundary. | observed | fresh real Codex JSONL probe |
| Installed Codex carries the assistant message in nested `item.completed.item` data rather than a top-level assistant-text field. | observed | fresh real Codex JSONL probe |

## Deterministic Workflow Delta

V1b changes the design in five deterministic ways:

1. A pane is an observation mirror, not the authoritative provider transport.
   Existing raw stdout, stderr, JSONL parsing, result bundles, and timeout
   channels remain authoritative.
2. The supervisor's validated directive bundle is the only steering input.
   Pane text and stdout never become control or result data.
3. The runtime mediates one control decision and one optional resume turn.
4. A single coordinator owns workflow state and publication; concurrent
   workers receive immutable requests and return member-local outcomes.
5. The form has one atomic workflow-state/result commit. A live coordinator
   may retry fresh only after complete cleanup; controller-crash resume
   quarantines before any provider launch. No live pane or provider-native
   session is durable workflow state.

## Simulated Event Log

### Scenario 1 — wrong long-running approach

| Version | Event trace | Outcome |
|---|---|---|
| V0 | Worker starts tool → supervisor captures pane → supervisor sends ordinary text + Enter → installed client queues text → worker completes original turn → queued text becomes a later turn, if processed at all. | Fails the claimed same-turn correction contract. |
| V1a | Worker starts tool → supervisor sends client interrupt → client starts replacement turn → old tool remains backgrounded → replacement result may settle while old tool still mutates the workspace. | Correction occurs, but result and process ownership are ambiguous. |
| V1b | Worker fresh session and supervisor start → metadata codec canonicalizes one preterminal `thread_id` → supervisor returns `STEER` → coordinator reaps the leader and empties the owned PGID → executor/capture work joins and the partial-stream identity remains unique → one resume invocation receives guidance plus a fresh typed output contract/path → resumed bundle validates → coordinator publishes it as the worker result. | Conditional corrected result with one explicit authority boundary; phase-1 runtime proof remains required. |

### Scenario 2 — ambiguous cancellation

| Version | Event trace | Outcome |
|---|---|---|
| V0 | Runtime has no control event or cancellation acknowledgement. | Cannot distinguish effective steering from queued input. |
| V1a | Client reports interruption, but a child tool remains live. | May settle incorrectly. |
| V1b | Every `STEER` enters the same idempotent boundary verifier. Cancellation does not complete the owned boundary, or a naturally exited leader's frozen terminal snapshot reports a lingering same-PGID child. | Group cleans up and fails closed; no resume turn and no result publication. A clean natural exit with the complete frozen boundary may resume. |

### Scenario 3 — no correction needed

| Version | Event trace | Outcome |
|---|---|---|
| V0 | Supervisor observes and sends nothing; group relies on last-expression settlement and may terminate the supervisor based on reference analysis. | Works only if the original concurrency and settlement machinery is correct. |
| V1a | No interruption; worker and supervisor finish. | Works, but still requires a persistent TUI transport for no benefit. |
| V1b | Supervisor returns `CONTINUE` → coordinator awaits the current worker → worker bundle validates → pure settlement expression runs → one atomic workflow-state/result commit lands. | Deterministic no-steer control path. |

### Scenario 4 — unsupported provider

| Version | Event trace | Outcome |
|---|---|---|
| V0 | A boolean-like `interactive_input` claim could be inferred from a TTY even though ordinary input queues. | False capability claim is possible. |
| V1a | Provider-specific keys and client UI semantics are required. | Not structurally generic. |
| V1b | Compile/load validation requires explicit turn-boundary resume support backed by session commands and preterminal session-id extraction. | Rejected before provider launch. |

### Scenario 5 — controller crash

| Version | Event trace | Outcome |
|---|---|---|
| V0 | Controller exits with only client/pane state describing the active members → ordinary resume cannot prove prior processes dead. | A fresh replay could overlap unproved provider work. |
| V1a | Controller exits after a client-owned interrupt → the client and background child state are not durable workflow authority. | Ordinary resume cannot safely infer a turn boundary. |
| V1b | Coordinator publishes one visit-qualified running record before member launch → controller exits before the group terminal commit → ordinary resume detects the incomplete live visit and writes the sticky interrupted-visit quarantine before any provider launch. | Fails closed; only explicit force-restart or a new run may cross the boundary. |

### Scenario 6 — workspace effects

| Version | Event trace | Outcome |
|---|---|---|
| V0 | Concurrent members mutate one workspace while control remains implicit. | Neither result authority nor rollback is defined. |
| V1a | The replacement turn begins while an old child can remain active. | Concurrent workspace mutation remains ambiguous. |
| V1b | Providers retain their ordinary workspace authority → a fresh worker may mutate before cancellation and the supervisor may mutate concurrently → one coordinator still selects and atomically publishes exactly one workflow result, but does not roll back or claim deterministic workspace bytes. | Workflow-state/result authority is deterministic; provider workspace effects are explicitly outside that atomicity boundary. |

## Decision Rationale

V0 is rejected because fresh behavior contradicts its essential premise.
V1a is rejected because the installed client's interruption acknowledgement
does not establish process quiescence or result authority.

V1b is adopted narrowly. It preserves the useful intent—one provider can
observe another live and issue free-form corrective guidance—while moving the
correction to an explicit provider turn boundary owned by the runtime. It
does not pretend queued TTY input is active-turn steering.

One resumed turn is the v1 bound. More turns would require a durable loop
contract, repeated supervisor decisions, budget accounting, and a new
checkpoint/failure analysis.

## Comparison

| Property | V0 | V1a | V1b |
|---|---:|---:|---:|
| Proven with installed clients | no | partially | existing session primitives observed; required new runtime proof pending |
| Meaningful live correction | no | yes | yes |
| Generic provider contract | no | no | yes |
| Explicit result authority | no | no | yes |
| Fail-closed cancellation | no | no | required |
| Preserves raw provider transport | uncertain | no | yes |
| Crash handling | fresh replay | unclear | fail-closed quarantine |

## Assumptions And Falsifiers

- **Assumption:** a supported provider can expose one stable canonical session
  id before its active turn exits. The installed Codex transport satisfies
  this with `thread.started.thread_id`.
  **Falsifier:** the real integration probe exposes the id only after process
  completion. The supported mode then degrades to safe post-turn resume and
  cannot satisfy Stage 7's live-correction gate.
- **Assumption:** the runtime can reap the process leader, empty its owned
  PGID, and join executor/capture work before launching the resume turn.
  **Falsifier:** a fixture or real provider leaves the owned PGID live or
  local executor/capture work unjoined after the complete grace/kill sequence.
  Stage 7 must stop rather than weaken this boundary.
- **Assumption:** a supervisor can make a useful decision from the live mirror
  without pane text becoming authoritative data.
  **Falsifier:** the real supervisor cannot distinguish the target state
  reliably enough to produce a valid directive.

## Regression Risks

- display-mirror work accidentally changes raw provider transport;
- an interrupted attempt writes to the same bundle path as the resumed turn;
- worker threads mutate shared workflow state;
- event races allow both the fresh and resumed result to publish;
- a directive is accepted from stdout or pane text instead of the validated
  bundle;
- unsupported templates pass validation through provider-name special cases;
- crash recovery attempts to reuse an external live session;
- ordinary resume launches a fresh group after a controller crash and overlaps
  an unproved prior provider process;
- "atomic" is misread as rollback of provider workspace effects.

## Recommendation

Revise the live-binding design and Stage 7 roadmap around V1b, then resimulate
the concrete executable design through fixture scenarios before frontend
exposure. Keep provider-native active-turn protocols, repeated steering, and
general background/join semantics as separate future proposals.

Verification for this report:

```bash
git diff --check -- \
  docs/plans/2026-07-23-provider-live-binding-t3-behavior-simulation.md
```
