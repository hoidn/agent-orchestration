# Live Provider Supervision And Peer Groups: Salvage Record

Status: **Historical.** This page keeps the design knowledge worth reusing from two **Retired**
features: live provider supervision (`with-live-providers`) and provider peer groups
(`with-live-provider-peers`). Nothing here is implemented, selected or admitted. The page selects no
work, changes no spec, and is not copy-safe: the build refuses both forms.

- **Future direction.** The owner keeps live supervision and peers as an unscheduled future
  direction ([roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md), owner
  decision 9). No phase owns it. The two source forms keep their parser, checker and elaboration on
  `main`; the old executor packages and the `peer-*` commands are deleted. A port needs its own
  design on evaluated execution; this page is its starting material.
- **Use today.** [Agent Sessions](workflow_lisp_agent_sessions.md) for several typed turns on one
  conversation; bounded parallel map ([evaluated execution](workflow_lisp_evaluated_execution.md),
  §11) for independent calls at once. Those two and [Providers](../../specs/providers.md) own
  current behavior. Section numbers (§) and rules (K, M, R) below are evaluated execution's.
- **Original designs.** The history records for
  [supervision](../reports/documentation-history/workflow_lisp_provider_live_binding-history.md) and
  [peers](../reports/documentation-history/workflow_lisp_provider_peer_messaging-history.md);
  quoted section names refer to them. Other evidence: the
  [execution facts report](../reports/2026-09-29-workflow-lisp-execution-facts.md), the
  [Q4 decision brief](../reports/2026-07-27-q4-binding-decision-brief.md) and the
  [Lane D plan](../plans/2026-11-11-lane-d-dead-executors-and-state-manager-plan.md).
- **Code.** `main` keeps the frontend handling and the spec sections of the two forms. Local tag
  `archive/dead-executors-2026-11-11` also holds `provider_supervision/` and
  `provider_peer_group/` under `orchestrator/workflow/`, `orchestrator/cli/commands/peer.py`, the
  frontend handling and the spec sections; names below are as they exist there. It does **not** hold
  the step-executor half that hosted the coordinators (`WorkflowProviderSupervisionBindings`,
  `WorkflowProviderPeerGroupBindings`) or the runtime tests. The last tree with all of it is commit
  `08cdd59b`.

## What Each Feature Did

**Supervision.** One provider (the worker) did a task. A second provider (the supervisor) ran at the
same time and could read the worker's live output in a tmux pane. The supervisor returned one typed
value: `CONTINUE`, or `STEER` with free-form guidance. On `CONTINUE` the worker's result stood. On
`STEER` the runtime stopped the worker at a proven session boundary, resumed the same provider
session once with the guidance, and used only the resumed turn's result. The user saw one step with
one value (the body, below the worker's `String`), two or three provider attempts as evidence, and
either that value or a failure of the whole group. From
`tests/fixtures/workflow_lisp/provider_supervision/provider_supervision_continue.orc` (condensed):

```lisp
(with-live-providers
  ((worker (provider-result providers.worker :prompt prompts.worker :inputs ()
             :timeout-sec 30 :returns String))
   (supervisor (provider-result providers.supervisor :prompt prompts.supervisor :inputs ()
                 :timeout-sec 30 :returns ProviderSteeringDirective)
     :observes worker))
  worker)
```

**Peer group.** Two to eight providers ran at once as long-lived interactive sessions. A member sent
free-form text to another member by binding name with `orchestrator peer-send`. The runtime recorded
the message, then typed it into the receiver's client, where it ran as the receiver's next turn.
Each member wrote a typed result and called `peer-finish`; a pure body combined the results. The
user saw one step with one typed record, one message ledger per receiver and one pane per member.
From `tests/fixtures/workflow_lisp/provider_peer_group/provider_peer_group_three.orc` (condensed):

```lisp
(with-live-provider-peers
  ((planner  (provider-result providers.planner  :prompt prompts.planner  :inputs ()
               :timeout-sec 10 :returns String))
   (reviewer (provider-result providers.reviewer :prompt prompts.reviewer :inputs ()
               :timeout-sec 10 :returns Bool))
   (builder  (provider-result providers.builder  :prompt prompts.builder  :inputs ()
               :timeout-sec 10 :returns String)))
  (record TeamResult :plan planner :approved reviewer :notes builder))
```

## Reusable Design Decisions

"Survives" says whether the decision holds after a move to evaluated execution.

1. **Correct only at a turn boundary.** *Problem:* a supervisor wants to change what a running
   provider does. *Finding:* text typed into a running client did not reach the turn in progress
   (Claude handled it after the answer; Codex queued it, and an interrupt left the earlier tool
   process running). *Decision:* two moves, never mixed: stop the turn at a proven boundary and
   resume the session once with the guidance (forcing), or queue text for the next natural turn.
   *Survives:* yes, as a fact about clients; probe again. *Source:* "T3a observed outcome".
2. **The runtime reads one discriminant; guidance is opaque.** *Problem:* model prose must not
   become control flow. *Decision:* `ProviderSteeringDirective` is a closed union with wire forms
   `{"variant":"CONTINUE"}` and `{"variant":"STEER","guidance":"<non-empty>"}`, exact key set, read
   only from the supervisor's validated result, never from stdout or a pane; `max_steers` is 1.
   *Survives:* yes, as an ordinary union result. *Source:* `provider_supervision/directive.py`.
3. **The supervisor gets a view, not a handle.** *Problem:* watching must not allow interfering.
   *Decision:* the worker keeps its normal pipes; its normalized output is also appended to a
   display file that a pane tails. The supervisor's prompt receives the pane's socket and target
   (`ProviderSupervisionObservationInjection`); typing there reaches `tail`, not the worker. Only
   the runtime cancels, resumes or publishes. *Survives:* yes, with a change: the address differs
   after every resume, so it must stay outside the effect's resolved input, like the provider
   spelling of the result path (§9.4, R2). *Source:* "Observation Pane Contract".
4. **Prove the boundary before replacing a turn.** *Problem:* the old turn and its replacement must
   not both live, and the session must still resume. *Decision:* the worker's provider declares
   `turn_boundary_resume`. The runtime cancels only on a snapshot with a unique session id,
   `resume_boundary_seen` and no `terminal_seen`; proves the leader reaped, the process group empty
   and capture threads joined; checks the final snapshot again; and requires the resumed turn to
   report the same session id. An id alone is not enough: on Codex 0.145.0 a cancel after
   `thread.started` could not resume, after `turn.started` it could. One zero-wait completion check
   decides a cancel that races a natural exit; a natural failure wins. *Survives:* yes, as is, and
   retained in `orchestrator/providers/` (`ProviderExecutionControl.cancel_and_reap`,
   `SessionIdentitySnapshot`); only `classify_provider_supervision_resume_boundary` is deleted.
   *Source:* "Task 3 stop/revise feasibility result", "Cancellable executor control".
5. **One writer, one settlement, one selected result.** *Problem:* concurrent members, a runtime
   that is not reentrant, and cancelled turns that leave valid-looking results. *Decision:* one
   coordinator allocates attempts and paths before launch; members run immutable requests and send
   events; the coordinator commits once. Each turn has its own result path, absent before launch;
   `STEER` selects only the resume turn and the fresh result is not read. The group's value is a
   pure expression over member results, read by name and free to differ in type. Each member is
   one provider call after inlining. *Survives:* yes, with a change: both coordinators committed
   into parent state and must expose `prepare`, `settle` and `reconcile` (§9.3, K2–K6). *Source:*
   "Runtime Ownership And Concurrency", "Result And Evidence Authority".
6. **Capabilities are declared, never inferred.** *Decision:* forced resume needs
   `session_support.turn_boundary_resume`; queued input needs `interactive_session_support`
   (`interactive_terminal_turn_queue.v1`), with keys from a closed non-forcing set and a declared
   close command. Neither follows from a provider name, stdin or a TTY. *Survives:* yes, retained:
   `InteractiveTerminalTurnQueueAdapter` serves phased delivery at 2.39.
7. **The runtime resolves the sender.** *Problem:* a member must not speak as another or write
   runtime files. *Decision:* one local endpoint per group visit; each member's environment holds
   one opaque binding that the coordinator maps to member and attempt. `peer-send <target> <text>`
   takes no sender, run root or path. Text is non-empty UTF-8 up to 65,536 bytes, verbatim; the
   frame carries message id and sender outside it. A repeated request id returns the earlier
   receipt, or fails if the payload differs. *Survives:* yes, with the changes of items 5 and 6
   below. *Source:* "Runtime-Owned Peer Surface"; `provider_peer_group/protocol.py`.
8. **Delivery states claim only what was proved.** *Decision:* `recorded` (synchronized to the
   receiver's ledger before any offer), then `offered` or `offer_failed` (text submitted to the
   exact client), then `receiver_acknowledged` (the receiver returned the id through its own tool).
   Nothing is named seen or understood. The sender succeeds only after a durable `offered`. One
   coordinator sequence orders all messages. *Survives:* yes, as a vocabulary; the ledger was
   evidence only and nothing read it to deliver again. *Source:* `PeerMessageLedger`.
9. **Start and finish are barriers.** *Decision:* `peer-ready` returns only when every member has
   registered; nobody sends earlier. `peer-finish` answers a retryable `pending_messages` while an
   incoming message is unacknowledged; then the runtime copies the validated result bytes, offers
   the declared close command, and answers. A member is terminal only after its client exits by
   itself with full process proof. *Survives:* yes, as is. *Source:* "Member Lifecycle".
10. **Any failure or crash discards the whole group.** *Decision:* one timeout per member and one
    for the step; the step's wins. Any member, protocol, delivery or cleanup failure cancels and
    joins every member and publishes nothing; forced cleanup is never relabelled a natural close.
    The group is one checkpoint: members, sessions and messages are not resumable one by one. A
    message is bound to the exact receiver attempt, so forcing and queued messages are never
    combined (`max_steers: 0`). Two crash rules were used: quarantine (a sticky run error; only a
    forced restart continues) and guarded rerun (emit `provider_attempt_interrupted_rerun`, start a
    fresh group). *Survives:* yes: the rerun is K4's rule and `must_not_repeat` (§8.1) gives
    quarantine. Parallel map has no cancellation (§11), so cancelling siblings must live inside one
    coordinator. *Source:* "Checkpoint, Retry, And Resume", "Races".
11. **Handles are not values; paths are isolated; the workspace is not.** *Decision:* pane targets,
    socket paths, sender bindings and session ids never enter values, results, state or identity;
    message text stays in the ledger. Evidence and result paths are per member and attempt. All
    members shared one workspace, one OS user and the same provider credentials; containment was
    the runtime-owned process group; nothing was rolled back. *Survives:* handles and paths yes
    (R1; attempt directories). The shared workspace does not: parallel map refuses items that
    share a directory (`parallel_workspace_shared`). *Source:* "Atomicity And Workspace Effects".

## What Was Wrong Or Unfinished (Do Not Copy)

1. **No consumer.** No maintained workflow used either form; every tracked source was a fixture
   (decision brief, option G; Lane D plan, "What Is True Today").
2. **Supervision was one-shot.** `ProviderSupervisionCoordinator._run` waits for the supervisor call
   to end before it acts. The supervisor chose how long to watch, reading the pane through its own
   tools. One directive, one correction; a late `STEER` paid for a second turn after wasted work.
3. **One member's slip failed everyone.** `ProviderPeerGroupCoordinator._handle_send` rejects the
   request and then fails the group for an unknown target, a self target or a target that already
   finished; the design's race table says only that such a send is rejected. A member that exits
   before `peer-finish` does the same. Every member's work is discarded.
4. **The protocol lived in prompts.** Ready, acknowledge and finish were shell commands a model had
   to run in order. The real-provider fixtures (`real_peer_group_sender.md`, `…_receiver.md`) script
   each command and order the two sides with a marker file. Nothing shows unscripted members
   following the protocol.
5. **Retry was not idempotent in practice.** `peer.py::_request_id` makes a new id per invocation
   and the replay table is in memory, so a member that repeats `peer-send` sends a second message.
6. **The endpoint identified; it did not authenticate.** A Unix socket in the system temporary
   directory, no peer-credential check, a binding that is base64 JSON in an inherited environment
   variable. A peer message is model text arriving as a user turn in another unsandboxed session.
7. **Identity was node plus visit count** (`provider-peer-group/<node>/visits/<visit>/…`), which
   evaluated identity excludes (§6). Neither group could run inside a loop body (execution facts
   report, section B: `*_nested_atomicity_unavailable`).
8. **Codex only.** Only the built-in `codex` template declares either capability; the Claude session
   codec has no resume-boundary observation (Providers spec). Declared submit keys were observed per
   client version and have changed. A client can stop at a trust prompt in a new directory; the test
   in `tests/e2e/test_e2e_provider_peer_delivery.py` avoids it by launching from a trusted checkout.
9. **Loose ends.** A pure binding captured by a `with-live-providers` member in the settlement body
   is an open defect (`workflow_lisp_composition_first.md`). Prompt-identity diagnostics excluded
   members (decision brief). Terminal evidence took several hundred lines of proof classes.

## Mapping Onto Evaluated Execution

Every "missing" entry is an open prerequisite, not a known-feasible step.

| Part | Mechanism that exists | Missing |
| --- | --- | --- |
| Correction as a later turn on the same session; the directive | A second `provider-result` on one `agent` (target 2.38); a provider result of union type | Nothing, if the correction follows a finished turn |
| A person decides instead of a provider | Durable host input between turns (§9.5) | It suspends the run; it cannot watch a turn |
| Several calls in flight | Parallel map: independent one-shot items, own directory each | Agent turns, phased providers and host input are refused in a worker (`closed/agent_effects.py::refuse_parallel_effects`); no sibling cancel |
| Stop a running turn, keep the session | `cancel_and_reap`, resume-boundary snapshot | An agent-turn outcome for a deliberately cancelled turn that leaves the session continuable. Today a turn commits only with a valid typed result; an interrupted first turn is abandoned for a new session and a later one refuses (Agent Sessions, "Persistence, Recovery And Invalidation") |
| One provider reads another's output | `ProviderObservationManager`; per-agent views for a person | Giving the address to a provider outside its resolved input |
| Queue text for the next turn | `InteractiveTerminalTurnQueueAdapter.offer`, used by the phased coordinator: one effect, one session | Several interactive sessions at once; an endpoint that carries content (the phased one carries a content-free submit signal) |
| Text into a running turn | None | No probed client applies it. A provider-native duplex protocol was out of scope and never probed |
| The group as one unit | A coordinator-class effect: one identity, own ledger, proof in the memo (§9.3). `EvaluatedPhasedBindings` (`workflow/evaluated/phased_providers.py`) shows an older coordinator hosted this way | The port to `prepare`/`settle`/`reconcile`; kill evidence at both gaps (K9) |
| A workspace per member | Path run references: each child runs in its own clone | Children of one parent run one at a time; an Agent cannot cross a child-run boundary |

**Resume soundness.** Resume is evaluation again: the same program, inputs and committed results
reach the same effects in the same order (§8.3). A message that a model sends when it chooses has no
place in that order; the old message id, `<endpoint instance>:<arrival sequence>`, was local to one
process. Two shapes are sound.

- *The group is one coordinator effect.* Messages have no effect identity; they live in the
  coordinator's ledger. A kill before the memo's `committed` discards the group and runs it again
  (K4): all member work repeats, no message is replayed or sent again, and workspace changes from
  the first try remain. After `committed` the group never reruns and cannot be invalidated (K8).
- *Messages are values.* Each member is an Agent. A member's typed result carries its outgoing
  messages as data, and pure code places them in the recipients' next prompts. Every message then
  sits in a committed turn result: replayed from the memo, never sent twice, identified by the turn
  and its position. Messaging happens only between turns, in rounds.

**Closer to reachable: supervision.** Its smallest useful version needs no new mechanism: a worker
turn on an Agent, a reviewer call that returns `ProviderSteeringDirective`, and on `STEER` a second
turn on the same Agent with the guidance. That program compiled at target 2.38 with four effect
sites (compile-only probe; not run). It corrects in the same session with a commit per turn; it does
not watch a turn or stop it early. Live supervision adds three prerequisites: an agent turn in
flight beside another effect (agents admitted in workers, or one coordinator effect that owns
both); a cancelled turn that is continuable on each adapter (the Codex evidence is from 0.145.0;
Agent Sessions, "Open Questions Before Selection", calls exact interrupted-turn recovery
inconclusive); and the pane address outside input identity.

Peers are further. Rounds run sequentially today (two agents in
`workflows/examples/design_review_execute_agents.orc`); rounds in parallel need turns on distinct
Agents inside workers. Free-running peers need several interactive sessions in flight, content
ingress, the barriers of decision 9 and the coordinator port, in return for all-or-nothing resume.

## What Agent Sessions Already Covers

- **Covers:** several typed turns on one retained conversation, which is what the `STEER` resume
  turn was; two agents that alternate with a typed handoff each time; a commit and a recovery rule
  per turn, with a check of the native head before each append; a read-only view per agent for a
  person; locators that never become values.
- **Does not cover:** any concurrency (one active turn per agent, no agent across a parallel
  boundary); a provider that watches a turn; stopping a turn early and continuing; a message sent
  at a time the model chooses ("no mailbox, fleet"). Its bounded form excludes supervision and peer
  groups by name, and a suffix that contains a committed turn cannot be invalidated.

## Names Worth Keeping

- `ProviderSteeringDirective`, `CONTINUE`, `STEER`, `guidance`, with the exact wire forms.
- `recorded`, `offered`, `offer_failed`, `receiver_acknowledged` (no "seen" or "understood");
  `peer-ready`, `peer-send`, `peer-ack`, `peer-finish`; the retryable `pending_messages`.
- `PeerMemberLifecycle`: `ALLOCATED`, `STARTING`, `READY_WAITING`, `ACTIVE`, `FINISH_REQUESTED`,
  `CLOSING`, `TERMINAL`, `FAILED`. `PeerDeliveryFrame`: header, id, sender, blank line, text.
- Still in `orchestrator/providers/`: `turn_boundary_resume`, `resume_boundary_seen`,
  `terminal_seen`, `cancelled_provisional`, `interactive_terminal_turn_queue.v1`, and the adapter
  verbs `start`, `offer`, `offer_close`, `join`, `abort`.

Safe to lose: both path plans and every visit-count identity; the node schemas
`provider_supervision.v1` and `provider_peer_group.v1` with their IR step configs; the
member-closing pass (`wcc/elaborate.py`) and the 2.16/2.17 target gates;
`provider_supervision/contracts.py`; the quarantine marker reader; the terminal-evidence classes;
the socket framing; the `peer-*` CLI module. The two form names are refused as retired, so a port
with other semantics needs new names.

## Not Verified

- No provider was called. The probe compiled only; the sequential steer was never run.
- The host bindings and runtime tests at `08cdd59b` were not read; statements about prompt
  composition, attempt allocation and state finalization rest on the history records and the
  execution facts report. That members never followed the peer protocol unscripted is inferred
  from the fixtures. The capture defect and the socket's file permissions were not reproduced.
- Whether current clients still queue typed input and resume after a cancel at `turn.started`;
  whether a Claude client can meet `interactive_terminal_turn_queue.v1`; whether agent turns can
  run in parallel workers, a cancelled agent turn can be made continuable, or the phased endpoint
  can carry content.
- `.worktrees/lane-d-a` was not read. Spec sections and frontend symbols named here may be gone
  from `main` once that branch lands; they remain at the tag.
