# Workflow Lisp Provider Live Binding

- **Status:** proposed
- **Kind:** feature / provider transport and frontend concurrency architecture
  decision
- **Owner:** Workflow Lisp frontend + provider runtime
- **Reviewers:** pending independent design review; direction resolved with
  the user on 2026-07-13 through two clarification rounds (worker is an
  in-workflow provider invocation hosted in tmux; control path is tmux
  send-keys; no runtime polling — agents interact whenever they choose;
  free-form steering; always-on tmux hosting with a 1:1
  invocation-to-pane invariant; post-hoc call-site composition over
  already-defined procedures; last-expression settlement semantics)
- **Created:** 2026-07-13
- **Last material update:** 2026-07-13
- **Related docs / plans:**
  - `docs/design/workflow_lisp_frontend_specification.md` (parent language
    contract)
  - `docs/design/workflow_language_design_principles.md` (explicit-effect
    direction this design deliberately and visibly relaxes at one point)
  - `docs/design/workflow_lisp_provider_prompt_queue.md` (sibling proposal:
    static multi-turn on one session; adjacent but orthogonal — see Context)
  - `docs/design/workflow_lisp_proc_refs_partial_application.md` (precedent
    for call-site composition over already-defined procedures)
  - `docs/design/workflow_lisp_unified_frontend_design.md` (deferred
    runtime-surfaces gate: no runtime procedure values — this form is
    compile-time static composition)
  - `docs/design/workflow_lisp_lexical_execution_checkpoints.md` (checkpoint
    identity and resume policy authority)
  - `specs/providers.md`, `specs/io.md`, `specs/index.md` (the
    concurrency-out-of-scope statements this design narrowly amends),
    `specs/examples/multi-agent-inbox.md` (existing sanctioned coordination
    pattern, which remains valid and complementary)
- **Implementation target:** not scheduled; requires an explicit amendment to
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
  (see Dependencies And Sequencing)

## Summary

There is no way for one provider agent to observe and steer another provider
agent's live work. Coordination today is file-based and turn-based: filesystem
queues between agents, and cross-run watchdogs that read persisted run state
and act only through resume/relaunch. A supervisor cannot course-correct a
long agentic invocation mid-flight, answer its interactive prompts, or pair
two agents on one task.

This design adds two capabilities:

1. **tmux-hosted provider invocations** — the provider executor launches
   every invocation inside its own tmux pane on a run-scoped private socket,
   with a strict 1:1 invocation-to-pane invariant. The pane is the live,
   addressable identity of a running invocation, whether or not anything
   binds to it.
2. **`with-live-providers`** — a call-site structured-concurrency form that
   composes N already-defined provider calls into **one atomic runtime
   step** whose member invocations run concurrently. A member may declare
   `:tmux-binding-of` a sibling, which injects the sibling's live tmux
   target (plus a standard interaction preamble) into its prompt the way
   input contracts are injected today. All interaction is then performed by
   the member agents themselves through their ordinary tool use
   (`capture-pane`, `send-keys`) — free-form, at moments they choose. The
   runtime mediates none of it. The form's value follows last-expression
   semantics: the body consumes whichever member results it needs, and
   settlement policy becomes ordinary dataflow.

## Context And Authority

Verified implementation behavior this design builds on (2026-07-13 checkout):

- **The step loop is strictly serial.** The executor advances one node at a
  time in a single-threaded cursor loop
  (`orchestrator/workflow/executor.py:2680`). No DSL surface offers parallel
  steps; `specs/index.md` explicitly lists concurrency, parallel blocks, and
  event-driven triggers as out of scope. This design confines all
  concurrency **inside one executable node** and leaves the cursor serial.
- **Side-band threads during a blocking step are established practice.** The
  executor already runs a heartbeat thread while a step executes
  (`executor.py:3237-3251`), the live-notes observer polls in a background
  thread (`orchestrator/observability/live_notes.py:82-91`), and streaming
  mode tees provider output through reader threads
  (`orchestrator/providers/executor.py:423`, `_capture_pipe`). Concurrent
  member invocations inside one node are an extension of this precedent, not
  a new runtime paradigm.
- **The runtime already has tmux affinity — for reading.** Live-agent-notes
  resolves a tmux pane by pid descent and reads it via
  `tmux capture-pane -p -J` (`live_notes.py:184-218`, `:271`), and
  `monitor_process.json` records the orchestrator's own tmux identity
  (`orchestrator/monitor/process.py`). The observe half of live interaction
  exists; no send path exists anywhere.
- **Provider invocations are exec-per-turn subprocesses** run with pipes and
  blocking waits, timeout-killed via a process-tree kill
  (`providers/executor.py:399`, `_terminate_process_tree`). Session
  transports append masked output chunks to a spool file with per-chunk
  flush (`providers/executor.py:692`, `_append_masked_transport`), and codex
  JSONL metadata is parsed in-flight from the stdout callback
  (`providers/executor.py:748`, `_stream_codex_jsonl_chunk`). Pane hosting
  must preserve these contracts (feasibility item T1).
- **Multi-invocation atomic nodes are an established family:**
  `adjudicated_provider` (v2.11), the `managed_jobs` guard (v2.13), and the
  proposed prompt-queue turn loop. This form is the first member whose
  internal invocations run concurrently rather than sequentially.
- **Call-site composition over existing procedures has a precedent:**
  compile-time ProcRefs and `bind-proc` compose already-defined procedures
  without runtime procedure values. `with-live-providers` follows the same
  post-hoc composition philosophy.
- **External live state has a ruling.** The prompt-queue design fixed that
  provider-side session persistence is external, non-content-addressed
  state: nothing in a run may treat it as durable workflow state, and
  interrupted work replays fresh. A live tmux pane is the same class of
  state; this design inherits that ruling (atomic form, fresh replay).
- **Effect atoms and their threading path are enumerated** in
  `orchestrator/workflow_lisp/effects.py` (`UsesProviderEffect`,
  `MovesResourceEffect`, union at `:109`); a new atom threads through
  typecheck effects, lowering, the executable IR, executor dispatch,
  checkpoint policy, and the source map.
- **Relationship to prompt-queue:** orthogonal. The queue drives N
  sequential *turns* (separate processes) against one persisted session,
  with the runtime owning the turn loop. Live binding operates *within*
  invocations: each member is still one exec-per-turn process; steering
  happens at the TTY of a live process, not by injecting protocol turns. The
  queue's persistent-process-transport non-goal (turn protocols over a
  long-lived transport) remains untouched.

Ambiguity resolved by this design: whether live agent-to-agent interaction is
runtime-mediated (observe/send effect forms, runtime polling) or
agent-mediated (the runtime provides hosting, wiring, and lifecycle; agents
interact through their own tools). This design fixes it as **agent-mediated**.

## Problem

- A long agentic provider invocation is a black box until it exits. The only
  intervention today is timeout-kill; the only supervision is post-hoc (next
  step reads its output) or cross-run (watchdog reads `state.json` and can
  merely resume/relaunch). Mid-flight course correction, answering a
  worker's interactive prompt, and live pair-work between two agents are all
  inexpressible.
- The ingredients exist but are disconnected: panes can be read
  (live-notes), spools can be tailed, agents have shell tools that can run
  `tmux send-keys` — but there is no hosting invariant that gives every
  invocation an addressable pane, no declaration that tells one provider
  where its peer lives, and no execution shape that lets two provider steps
  be in flight at once.
- This needs a design-level decision because it changes the provider
  transport globally (always-on pane hosting), introduces bounded
  concurrency into a deliberately serial runtime, and deliberately relaxes
  strict input-explicitness for steered invocations — each of which must be
  bounded by contract rather than emerging ad hoc.

## Goals And Non-Goals

Goals:

1. Every provider invocation runs in its own addressable tmux pane (1:1,
   never shared, never reused), uniformly, bound or not.
2. A call-site form composes already-defined provider calls so their
   invocations run concurrently inside one atomic step, with declared
   peer-binding injections — no special authoring inside the composed
   procedures.
3. Interaction is free-form and agent-driven; the runtime performs no
   per-interaction mediation and imposes no polling cadence.
4. Settlement is last-expression dataflow: the body decides which member
   results matter; the scope terminates stragglers on exit with recorded
   evidence.
5. The steering relationship is visible in the composition's type/effect
   surface, and every member's pane transcript is persisted evidence.
6. Mechanics are structural: no branching on workflow, provider, family, or
   domain names.
7. A single-member, binding-free form is behaviorally equivalent to the
   plain invocation.

Non-Goals (intentionally excluded):

- **Runtime-mediated interaction.** No observe/send effect forms, no
  runtime polling loops, no runtime interpretation of steering content.
- **DAG-level parallelism.** No concurrent steps, branches, or background
  step primitives; concurrency exists only inside `with-live-providers`.
- **Event-driven runtime.** The executor never waits on output events; the
  member agents own their reaction timing.
- **Live handles as values.** Tmux targets never escape the scope — not
  into results, artifacts, state, or later steps.
- **Mid-scope checkpointing or partial resume.** The form is atomic; an
  interrupted form re-executes fresh with new panes (inherited external-
  state ruling).
- **Cross-run binding.** Binding to another run's panes stays deferred; the
  watchdog pattern remains the cross-run layer.
- **Turn-protocol transport changes.** Members remain single exec-per-turn
  invocations; this design does not create persistent turn transports and
  does not overlap the prompt-queue surface.
- **Typed steering vocabularies.** Free-form is the point (user decision);
  a constrained command union can be layered later as prompt guidance
  without changing this contract.
- **Multi-step members in v1.** A member is one provider invocation (see
  Design Details); composing whole multi-step procedures concurrently is a
  recorded future extension.

## Decision

Add pane hosting as the provider executor's default transport, and add a
`with-live-providers` structured-concurrency binding form.

- **Chosen approach:** always-on tmux hosting with a 1:1 invocation↔pane
  invariant; post-hoc call-site composition over existing provider
  procedures; prompt-injected peer bindings (a fourth member of the existing
  injection family); agent-mediated free-form interaction; last-expression
  settlement with scope-exit termination of unreferenced members; one atomic
  node with fresh-replay resume.
- **Alternatives rejected:**
  - *Runtime observe/send effect vocabulary* (spawn/observe/send/await as
    typed effect forms the runtime executes). Rejected per the resolved
    direction: it puts the runtime in the interaction loop, adds latency
    and duplication (agents already have the tools), and hard-codes an
    interaction grammar where free-form judgment is wanted.
  - *Poll-based supervisor loop* (typed loop: capture → provider decision →
    gated send-keys per iteration). Remains expressible today with zero new
    capability and is the recommended baseline while this design is
    pending — but rejected as the target: per-iteration invocation latency,
    loop-bound cadence, and no live low-latency steering.
  - *Supervisor attachment* (monitor declared as a companion of one worker
    step). Rejected: asymmetric — cannot express bidirectional peers — and
    couples the monitor to the worker's step authoring, against the post-hoc
    composition requirement.
  - *Background launch + join* (general async step primitive with an await).
    Rejected for v1: leaks async in-flight state into checkpoint/resume
    across arbitrary step distances; the structured scope achieves the
    target use cases with a bounded blast radius.
  - *Fixed settlement policies* (worker-primary / all-members /
    monitor-authoritative as modes). Rejected: last-expression semantics
    express all three as ordinary dataflow (see Design Details), with no
    policy enum to maintain.
  - *Opt-in pane hosting.* Rejected by user decision: always-on keeps the
    1:1 invariant uniform, makes every invocation observable by default,
    and avoids two transport paths diverging. (A degraded-environment
    escape hatch is an open question, not a mode.)
- **Tradeoffs accepted:** steered outputs are not reproducible from declared
  inputs (hence atomic fresh replay); steering content is auditable only
  through transcripts; tmux becomes a runtime dependency for all runs; N
  live agent CLIs run concurrently (cost and workspace-contention
  responsibility rest with the author, bounded by validation).
- **Left open:** see Open Questions (degraded environments, interactive
  provider templates, straggler grace default, explicit await annotations,
  multi-step members, cross-run binding).

Naming note: the form is spelled `with-live-providers`; "bind" spellings were
avoided because `bind-proc` owns partial-application vocabulary in this
frontend.

## Design Details

### Part A: tmux-hosted invocation transport

- Each run owns a private tmux server socket under the run's state root
  (recorded in run state); panes are named deterministically from run id,
  step id, visit, and invocation index. The invocation's pane identity is
  recorded in its invocation metadata, extending the existing
  `monitor_process.json` family from "the orchestrator's own pane" to every
  provider invocation.
- The executor launches the composed provider command inside the pane; a
  thin wrapper captures the exit status to a file and signals completion
  (`tmux wait-for`-class mechanism). For unbound invocations the executor
  still blocks synchronously — the transport changes, the execution model
  does not.
- Output capture: pane output is piped (pipe-pane or FIFO) into the existing
  per-chunk callback machinery so that **masking, the transport spool, and
  in-flight JSONL metadata parsing** (`_append_masked_transport`,
  `_stream_codex_jsonl_chunk`) keep working unchanged. Preserving these
  contracts under a TTY is feasibility item T1.
- Timeout and kill: the existing invocation timeout budget applies; kill is
  `tmux kill-pane` plus the existing process-tree kill as fallback.
- Contract: an unbound invocation under pane hosting is **behaviorally
  identical** to today's pipe transport — same result contracts, bundles,
  metadata, and evidence; the pane is purely additional observability. This
  equivalence gets a dedicated compatibility suite.

### Part B: the `with-live-providers` form

Authoring surface (illustrative):

```lisp
(with-live-providers
    ((w (call procs.run-migration :input plan))
     (m (call procs.supervise
          :input policy
          :tmux-binding-of w)))
  (settle-migration m))          ;; form value = body's last expression
```

- **Members.** Each binding pairs a name with a provider call: a provider
  invocation form, or a call to an already-defined procedure that lowers to
  exactly one provider invocation (verified at compile time with a dedicated
  diagnostic). This keeps the concurrency unit equal to the invocation and
  preserves the 1:1 pane invariant, while covering the normal
  procedure-first case of thin typed wrappers around one invocation.
  Members keep their declared return types, contracts, and effect
  classifications unchanged.
- **Bindings.** `:tmux-binding-of <member>` (one name or a list) must
  resolve to sibling members; unknown names are compile diagnostics. Mutual
  declarations express bidirectional pairs. At runtime, panes are allocated
  before launch so every member's composed prompt can carry its peers' tmux
  socket + target plus a standard interaction preamble, rendered by the
  prompt composer exactly like the existing typed-input/consumes/asset
  injections. Prompt-audit metadata records which binding injections were
  applied — the structural (non-phrasing) assertion surface for tests.
- **Typing.** The form's type is the body's last-expression type; member
  names are lexical bindings of the members' declared return types within
  the body. Bindings affect effects and injections, never types.
- **Effects.** The form's effect summary is the union of member effects plus
  a new `LiveBindingEffect` atom per declared binding (from-member,
  to-member) — the visible marker that one invocation may steer another.
- **Runtime execution (one atomic node):**
  1. allocate panes for all members; compose prompts with binding
     injections;
  2. launch all member invocations concurrently (worker threads driving the
     existing prepare/execute path per member);
  3. await the members the body references (the compile-time free-variable
     set of the body — conservative and deterministic); when they settle,
     evaluate the body;
  4. scope exit: members still running whose results are unreferenced get a
     grace period, then termination — recorded as evidence with reason
     `scope_exit`, never as a step failure.
- **Settlement policies are dataflow, not modes.** The three natural
  policies fall out of what the body references:
  - reference only `w` → *worker-primary*: the supervisor is auxiliary and
    is collected at scope exit;
  - reference `w` and `m` → *all-members-typed*: both results are
    first-class for downstream steps;
  - reference only `m` → *monitor-authoritative*: the monitor's typed
    verdict is the result; if it kills the worker, the worker's abnormal
    exit is recorded evidence, not a failure.
- **Failure semantics.** A **referenced** member failing (nonzero exit,
  contract violation, kill) fails the form with a member-indexed diagnostic
  and all transcripts attached. An **unreferenced** member's abnormal exit
  is evidence only. Pane allocation failure fails the step closed. Each
  member keeps its own invocation timeout; the step timeout bounds the
  whole form.
- **Checkpoint/resume.** One checkpoint identity for the whole form, derived
  from static structure and declared inputs as usual. An interrupted form is
  an incomplete step: resume re-executes it fresh — new panes, new
  invocations. No member result is separately checkpointed; live targets are
  never persisted.
- **Observability.** Per-member transport spools and pane transcripts are
  persisted as step-scoped evidence artifacts named by member. Because Part
  A is universal, dashboards and live-notes can target member panes with the
  same mechanics as any invocation.
- **Equivalence contract.** `(with-live-providers ((x <call>)) x)` with no
  bindings is IR- and behavior-equivalent to the plain call (dedicated
  test), the analogue of prompt-queue's arity-1 rule.

### Authority and security model

The binding injection is **information, not privilege**: member agents
already hold shell tools, so the design grants no new capability — it tells
an agent where its peer lives and that steering it is sanctioned. Bounded by:
a run-private tmux socket (filesystem permissions scope which panes are
reachable by path), injected targets naming only sibling panes, and secrets
masking applying to the pane-capture evidence path (part of T1). The
deliberate relaxation of input-explicitness — a steered member's inputs
include untracked live keystrokes — is compensated by making the
relationship explicit in the composition (`LiveBindingEffect`, prompt-audit
flags) and by transcripts as evidence.

## Contracts And Interfaces

- **New:** pane-hosting transport contract (socket location, pane naming,
  exit capture, spool wiring, kill path, per-invocation pane identity in
  metadata); `with-live-providers` form and `:tmux-binding-of` parameter;
  `LiveBindingEffect` atom; a new executable node kind (`provider_group`)
  carrying member invocations and binding edges; member transcript evidence
  naming; compile diagnostics (unknown peer, member-not-single-invocation,
  binding outside the form); the standard interaction preamble as a
  runtime-owned injection block.
- **Changed:** the default provider invocation transport for all runs
  (behavior-compatible by contract, proven by the compatibility suite).
  Nothing else changes for existing workflows; the form is additive.
- **Spec deltas required at implementation time:** `specs/providers.md`
  (pane hosting, group execution, binding injection), `specs/io.md`
  (transcripts are evidence-only), `specs/index.md` (amend the concurrency
  exclusion narrowly: structured provider groups within a single step),
  `specs/versioning.md` (feature gate), and the frontend specification
  (form surface contract).

## Dependencies And Sequencing

- **Feasibility items (recorded, phase-gated, not assumed):**
  - **T1 — transport parity.** A pane-hosted invocation preserves today's
    result and metadata contracts: exit-code capture, masked spool
    equality, and in-flight codex JSONL session-id parsing through a TTY +
    pipe-pane path. This is the trickiest mechanical claim and gates
    flipping the default.
  - **T2 — concurrent-member safety.** N member invocations in flight do
    not corrupt shared run state (state writes, heartbeat, artifact paths);
    audited and locked as needed. The compile-time pipeline's global-state
    constraint is irrelevant here (runtime, not compile), but runtime state
    writes are not currently exercised concurrently.
  - **T3 — steering viability.** A real agent in one pane can effectively
    steer a real agentic CLI in another. **Open prerequisite:** current
    builtin templates run non-interactive `exec`-style commands that may
    ignore stdin entirely; free-form steering requires the steered member's
    CLI to read its TTY (interactive mode) — otherwise a binding is
    observe-only. Provider templates gain a declared `interactive_input`
    capability so authors know which members can be steered; whether any
    builtin CLI supports it today must be probed, and an adverse result
    triggers the stop/revise criteria, not a workaround.
- **Sequencing:** not roadmap-scheduled; this document does not make the
  work selectable. It touches the provider executor, frontend, IR, and
  checkpoint policy, so implementation must serialize with procedure-first
  Stage 5/6 work at shared surfaces per the roadmap's concurrency rules and
  requires an explicit roadmap amendment (the same path prompt-queue and the
  language server took). Part A (pane transport behind a flag) is
  independently valuable — uniform live observability for every invocation —
  and is deliberately the first phase.
- Work that can proceed independently: independent design review; the T3
  interactive-template probe; the poll-loop supervisor pattern as the
  available-today baseline for urgent supervision needs.

## Invariants And Failure Modes

Invariants that must hold after implementation:

1. 1:1 invocation↔pane; panes are never shared, reused, or outlived by the
   scope that created them.
2. Concurrency exists only inside a `provider_group` node; the step cursor
   remains strictly serial.
3. Live tmux targets never escape the scope: not in results, bundles,
   artifacts, persisted state, or diagnostics payloads (paths to transcript
   evidence are fine; live targets are not).
4. The runtime mediates no interaction: after injection, all
   observation/steering happens through member agents' own tool use.
5. Results travel only as members' validated bundles consumed by the body's
   dataflow; pane transcripts and spools are evidence, never a result
   channel.
6. One checkpoint per form; incomplete forms replay fresh; no live state is
   treated as durable workflow state.
7. No name-keyed branches: hosting, grouping, and binding mechanics never
   consult workflow, provider, family, or domain names.
8. An unbound invocation under pane hosting is behaviorally identical to the
   pipe transport, and a single-member binding-free form is equivalent to
   the plain call.

Failure behavior:

- unknown peer name, member that is not a single provider invocation, or
  `:tmux-binding-of` outside the form → compile diagnostics;
- pane or socket allocation failure → step fails closed before any launch;
- referenced member failure (exit, contract, kill) → form failure with
  member-indexed diagnostic and all member transcripts attached;
- unreferenced member abnormal exit or scope-exit termination → recorded
  evidence, not failure;
- tmux absent at run start → run fails at preflight with a clear diagnostic
  (subject to the degraded-environment open question);
- crash mid-form → incomplete step; resume replays the whole form fresh.

## Security, Operations, And Performance

- No new authority: agents already hold shell tools; the design adds
  addressing information and sanction, scoped by a run-private socket.
  Secrets masking must hold on the pane-capture path (T1).
- Wall-time for a group is the slowest referenced member plus grace, versus
  the sum for sequential alternatives; cost is N concurrent agent CLIs —
  authors size groups deliberately.
- tmux becomes a preflighted runtime dependency for every run (user
  decision); it is headless-compatible, and CI environments must provide it.
- Workspace contention between concurrent members is the author's
  responsibility; existing artifact-path validation continues to apply per
  member.

## Evidence And Implementation Boundaries

- The compatibility suite (pipe vs pane transport on fixture providers) is
  the sanctioned proof for Part A; flipping the default transport without it
  is prohibited.
- Fixture "agents" for group tests are scripted CLIs (one sends keys, the
  other reacts deterministically) — test infrastructure, not the
  implementation; end-to-end evidence must include one real agentic CLI
  steered by a real supervisor provider (gated on T3).
- Binding behavior is asserted through prompt-audit flags, invocation
  metadata, transcripts, and evidence records — never through prompt
  phrasing or transcript wording.

## Compatibility And Migration

- Additive for all existing workflows; no YAML surface. The transport change
  is behavior-compatible by contract and lands behind a flag until the
  compatibility suite proves parity (then flips to default per the user
  decision).
- The filesystem-inbox multi-agent pattern and the cross-run watchdog remain
  valid, sanctioned layers; this design adds the intra-step live layer
  between them.

## Verification Strategy

- **Transport (Part A):** golden compatibility suite — identical result
  contracts, bundles, metadata, masked spool content, timeout/kill behavior,
  and codex JSONL session-id parsing across pipe vs pane transports; pane
  identity recorded in invocation metadata; preflight failure without tmux.
- **Typecheck:** unknown-peer and non-single-invocation rejections; binding
  outside the form rejected; form type equals body type; member bindings
  typed as declared returns; effect summary carries `LiveBindingEffect`
  edges.
- **Lowering:** golden IR for a two-member group (one `provider_group` node,
  member order, binding edges, source-map entries per member); single-member
  equivalence against the plain call.
- **Runtime (fixture agents):** concurrent launch with 1:1 panes; binding
  injection applied to the declared member only (prompt-audit); interaction
  proven by transcript (fixture A sends keys, fixture B's behavior changes);
  body referencing only `w` terminates `m` at scope exit with `scope_exit`
  evidence; body referencing only `m` while `m` kills `w` yields `m`'s
  typed result with `w`'s abnormal exit as evidence; referenced-member
  failure fails the form with member-indexed diagnostics; crash mid-form
  resumes as fresh replay with new pane identities.
- **Concurrency safety (T2):** parallel members hammering state
  writes/heartbeat/artifacts with integrity assertions.
- **End-to-end (repo rule):** one orchestrator smoke compiling and running a
  small `.orc` workflow where a real supervisor provider steers a real
  interactive-capable worker CLI on a toy task, settling via the body's
  dataflow (gated on T3's template probe).
- **Negative:** a workflow attempting to place a live tmux target in an
  output bundle or artifact fails validation; binding to a non-member fails
  at compile time, not runtime.

## Declarative Acceptance Scenario

A `.orc` workflow declares `with-live-providers` with members `w` (a
migration-executor procedure) and `m` (a supervisor procedure declaring
`:tmux-binding-of w`), body returning `m`'s `SupervisionVerdict`. Running it:

- launches both invocations concurrently, each in its own pane on the run's
  private socket, with `w`'s tmux target and the interaction preamble
  injected into `m`'s prompt only (prompt-audit asserts this structurally);
- `m` observes `w` mid-flight via capture-pane and sends corrective input
  via send-keys at moments of its own choosing — no runtime mediation
  appears in any log;
- when `m` returns its validated verdict bundle, the form's value is the
  verdict; `w`, still running and unreferenced, receives grace then
  termination recorded as `scope_exit` evidence alongside both transcripts;
- on resume after a mid-form crash, the form re-executes fresh with new pane
  identities and no reuse of prior live state.

This proves the intended integration because every assertion rests on
invocation metadata, prompt-audit flags, evidence records, typed bundles,
and checkpoint behavior — not on transcript phrasing or fixture-only
shortcuts.

## Success Criteria

- Compatibility suite green and the transport default flipped with fresh
  evidence; T1-T3 outcomes recorded.
- All Verification Strategy checks implemented and green, including the
  fixture-agent interaction proofs and the real-CLI end-to-end smoke.
- Single-member equivalence proven at IR and behavior level.
- Spec deltas landed with the implementation; capability matrix row and
  doc-index routing added.
- Independent design review signoff before implementation starts.

## Stop / Revise Criteria

- **T3 fails** — no viable interactive-input provider CLI exists and none
  can be added: revise the control path toward turn-boundary steering
  (resume-turn injection against the worker's provider session) before
  building the form; do not ship send-keys steering that provably cannot
  steer.
- **T1 fails** — pane hosting cannot preserve metadata/masking contracts:
  keep pane hosting opt-in per group instead of the global default, and
  bring the always-on decision back to the user rather than weakening the
  contracts.
- **T2 fails boundedly** — concurrent state safety needs more than
  targeted locking: stop and reconsider a single-flight attachment model
  before introducing broad locking.
- Last-expression settlement proves error-prone in practice (authors
  accidentally terminate members they needed): add explicit `:await` /
  `:auxiliary` member annotations rather than changing the default
  semantics silently.
- The form cannot be implemented without consulting provider or workflow
  names → stop; the abstraction is wrong.

## Documentation Impact

At implementation time: `specs/providers.md`, `specs/io.md`,
`specs/index.md`, `specs/versioning.md`, the frontend specification,
`docs/capability_status_matrix.md`, `docs/index.md` +
`docs/design/README.md` routing updates, the drafting guide (authoring
guidance, the settlement-as-dataflow patterns, and the equivalence note),
and `docs/workflow_monitoring.md` (pane identities as an observability
surface). None are edited by this proposal beyond the routing entries that
announce it.

## Implementation Handoff

Suggested phases (each independently testable):

1. **Pane transport behind a flag** — socket/pane lifecycle, exit capture,
   spool/masking/JSONL wiring, invocation-metadata pane identity, the
   compatibility suite (T1). Independently valuable observability win; zero
   frontend changes.
2. **Group node and runtime** — `provider_group` executable node, concurrent
   member execution with settlement/grace/termination semantics, T2 safety
   work, fixture-agent runtime tests. Producible only by hand-built IR in
   tests; still no frontend exposure.
3. **Frontend surface** — `with-live-providers` parsing, member/binding
   typecheck, `LiveBindingEffect`, lowering with source-map entries,
   equivalence tests, prompt-composer binding injection + prompt-audit.
4. **Steering viability and end-to-end** — `interactive_input` template
   capability, T3 probe, real-CLI smoke, spec deltas, transport default
   flip, capability matrix and docs.

Likely-touched modules: `orchestrator/providers/executor.py` (transport),
`orchestrator/providers/types.py`/`registry.py` (`interactive_input`),
`orchestrator/workflow/executor.py` (node dispatch),
`orchestrator/workflow/executable_ir.py`, `orchestrator/workflow/prompting.py`
(injection), `orchestrator/workflow_lisp/effects.py`, `typecheck_effects.py`,
form registry/expressions, lowering, `lexical_checkpoints.py` (atomic
policy), `orchestrator/state.py` (concurrent-write safety), evidence/state
layout for transcripts.

Known tricky areas: TTY line/chunk integrity for in-flight JSONL parsing
under pipe-pane (T1); masking on the pane path; deterministic
free-variable analysis of the body for the awaited-member set; straggler
termination racing a member's natural exit; keeping pane identities out of
every persisted result surface.

Safe first step: phase 1 behind its flag with the compatibility suite —
fully removable, immediately useful.

Out of scope for the implementation: cross-run binding, multi-step members,
typed steering vocabularies, event-driven wake-ups, background/join
primitives, YAML surface.

## Open Questions

1. **Degraded environments** — is tmux a hard preflight dependency for every
   run (uniformity, the user's default) or is a config fallback to pipe
   transport permitted where tmux is unavailable (breaks the 1:1
   uniformity)? Recommendation: hard dependency with preflight diagnostic;
   revisit on real deployment evidence. Blocking: no.
2. **Interactive provider templates (T3 owner)** — which CLIs support
   effective TTY steering mid-invocation, and what does the builtin
   registry's `interactive_input` story look like? Owner: provider registry.
   Blocking: for the steering end-to-end only; observe-only bindings work
   regardless.
3. **Straggler grace period** — default value and whether it is per-form
   configurable. Recommendation: one default (order of 30s), per-form
   override later if evidence demands. Blocking: no.
4. **Explicit await annotations** — should authors be able to override the
   free-variable analysis with `:await`/`:auxiliary` marks from day one?
   Recommendation: analysis-only in v1; annotations are the recorded
   fallback if the stop/revise trigger fires. Blocking: no.
5. **Multi-step members** — the future shape for composing procedures with
   several internal steps (concurrent sub-graphs). Deferred; requires its
   own design. Blocking: no.
6. **Cross-run binding** — supervising another run's panes (watchdog
   upgrade). Deferred; interacts with run-private socket isolation.
   Blocking: no.
