# OMP Integration Proposal: Worker Harness, Advised Steps, Session Transport

**Status:** Proposed; owner decision required. Creates no gate, no review
obligation, and no roadmap-level unit. Nothing here touches the frozen ES
apparatus; all accepted work lands as new capability beside it, after the
study unless stated otherwise.
**Date:** 2026-08-14
**Author:** assistant session (orchestration supervision), at owner request
**Repo references:** symbol/path-based as of HEAD `54d3d1bb`; the omp
checkout examined is `~/Documents/oh-my-pi` (fork of pi-mono by can1357).

## 1. Question and scope

Does the orc runtime reinvent wheels that pi/omp already provide, and should
omp serve as (a) the runtime substrate, or (b) the inter-agent communication
layer for synchronously communicating providers? This proposal records the
grounded comparison, the options considered with verdicts, and the accepted
integration designs.

## 2. Grounded findings

### 2.1 orc's extension seams (already present)

- Providers are declarative `ProviderTemplate`s — argv/stdin command
  templates with `${model}` / `${reasoning_effort}` substitution — and
  workflows can register custom providers via
  `ProviderRegistry.register_from_workflow`
  (`orchestrator/providers/registry.py`) with zero runtime code changes.
- Batch session transport is a structural seam:
  `ProviderSessionSupport.metadata_mode` selects an incremental stdout codec
  via `create_session_transport_accumulator`
  (`orchestrator/providers/session_transport.py`). One codec exists today:
  `CodexExecJsonlAccumulator` (fail-closed session identity, terminal and
  resume-boundary markers, normalized assistant text, typed
  `provider_session_transport_error`).
- Interactive session transport (the target-2.16/2.17 live-binding
  substrate) is a keystroke contract: `InteractiveSessionSupport`
  (`orchestrator/providers/types.py`) delivers supervisor messages by typing
  `${PROMPT}` into a terminal with submit keys; turn boundaries are inferred
  from terminal state.
- **Usage fact:** no authored workflow under `workflows/` consumes the 2.16
  live-binding or 2.17 peer-messaging surfaces. They are implemented runtime
  capability with zero production consumers.

### 2.2 omp's relevant surfaces (verified in source/docs)

- `omp -p` one-shot; `omp --mode rpc` NDJSON stdio with protocol-v2 lossless
  chunking, correlation ids, and typed frames — command vocabulary includes
  `prompt` (with `streamingBehavior: "steer" | "followUp"`), `steer`,
  `abort`, `get_state` (returns `sessionId`); an official Python RPC client
  exists (`docs/rpc.md`).
- Model roles and ensembles: `modelRoles` (default/task/plan/slow/advisor),
  a live **advisor** that reads the primary's transcript on its own model and
  context and injects aside/concern/blocker notes mid-stream, throttled by
  `advisor.syncBacklog`. The advisor's tool surface is read-only (read, grep,
  glob — no mutation tools), so role separation is structural. RPC/ACP host
  defaults cover advisor settings, indicating headless support.
- Subagents: declarative agent definitions (frontmatter: models, tools,
  spawn policy, output schema), schema-validated typed yields to the parent,
  isolated worktrees, peer IRC DMs, Agent Hub (`hub list` / `hub send`),
  parked/revive lifecycle, per-agent cost/token metering.
- Collab: E2E-encrypted live session sharing (terminal or browser guests,
  steer/interrupt/hub control); hosted relay `my.omp.sh` plus a
  source-available local relay for LAN-only use.
- Metaharness: experiment → run → trace model with SQLite store, REST/SSE
  API, comparable arms inheriting sibling config, containerized trials, and
  a host-side auth gateway keeping credentials out of containers.
- Project-level config: omp resolves `.omp/` in the project (config,
  `agents/*.md`, `WATCHDOG.md`) in addition to `~/.omp/`.

### 2.3 Verdict on "reinventing the wheel"

The reinvention is concentrated in orc's **operational** layers — process
supervision, keystroke session driving, JSONL scraping, metering-by-parsing —
where omp's equivalents are more mature. orc's **core** is not duplicated
anywhere in omp: a deterministic workflow language, typed step contracts,
fail-closed bound-path result bundles, replay-deterministic resume, and
content-addressed provenance. omp's orchestration is model-driven task
dispatch; orc's founding principle is that workflows own deterministic
control. The correct move is a layer swap, not a substrate swap.

## 3. Invariants any integration must preserve

1. Workflows own deterministic control; prompts own local judgment.
2. The declared return type is the contract; the bound-path
   `output_bundle` / `variant_output` is the only result channel. Provider
   stdout, RPC frames, and advisor transcripts are observability evidence,
   never a result channel.
3. Provider identity fully determines the treatment: no ambient
   machine-global state may change what a named provider does.
4. Coordination outcomes that gate or route workflow behavior must be typed,
   ledgered, and replayable (the 2.16/2.17 property set).
5. The frozen ES apparatus (arms, metering, locks, projections) is untouched.

## 4. Options considered

| # | Option | Verdict |
| --- | --- | --- |
| A | Full substrate swap: rebuild orc's runtime on omp | Reject |
| B | omp as worker provider via `omp -p` (config-level template) | Accept — phase 0 |
| C | omp RPC-backed provider session transport | Accept — phase 1 |
| D1 | omp as replacement implementation of 2.16/2.17 (map declared synchronous provider coordination onto advisor/worker) | Reject as a lowering; accept the decomposition in §5 |
| D2 | omp advisor/worker as the default pattern for *advisory* supervision (advised step) | Accept |
| E | omp as supervision cockpit for long-lived primaries (Agent Hub, Collab, advisor) | Accept — trial, local relay only |
| F | Metaharness as trial-execution plumbing for ES-style studies | Accept — post-freeze evaluation spike only |
| G | Reverse embed: orc as an omp extension (`/orc`) | Reject (YAGNI) |
| H | Expose omp's typed subagent yields as a second orc result channel | Reject (contract drift; the bundle is the typed channel) |

### 4.1 Why A is rejected

omp has no deterministic workflow control, no typed step contracts, no
fail-closed bundles, no content-addressed freeze, no replay-deterministic
resume. Rebuilding those inside omp extensions means rewriting orc in
TypeScript against a fast-moving single-lead fork (~80k-line Rust core,
continuously tuned, PRs temporarily open to all). For a preregistered-study
substrate the drift profile alone is disqualifying.

### 4.2 The D1 mapping, examined precisely

Mapping orc's declared worker+supervisor (2.16) or peer set (2.17) onto
omp's advisor/worker machinery preserves — and in one respect improves —
the *channel*:

- Synchrony is tighter: orc offers messages at turn/attempt boundaries; the
  omp advisor observes the live transcript and injects mid-stream.
- No forcing edge holds on both sides (the advisor can only inject text).
- Role separation is structural (read-only advisor toolset).
- Cross-model pairs are native via `modelRoles`. Cross-*harness* pairs are
  lost: every party runs the omp harness.

It cannot preserve the *contract*:

- **Typed settlement is structurally impossible.** The advisor is read-only
  and cannot write a bound-path bundle; its only output channel is prose
  injected into another context. Recovering a verdict by parsing advisor
  transcripts is the report-parsing-as-authority pattern this repo bans.
- No append-before-offer ledger, no cooperative receipts, no attempt-bound
  ingress: injections are recorded post-hoc in session JSONL — evidence
  without contract.
- No replay determinism under orc resume: omp sessions have their own
  resume machinery; stitching the two would be new glue, not piggybacking.
- 2.17 analogues (receipts, settlement) do not exist for subagent IRC DMs.

Conclusion: as a lowering of 2.16/2.17 the mapping is lossy in exactly the
dimensions those surfaces were specified for. Do **not** build a
"2.16-compiled-to-omp" translation layer; it would assert an equivalence the
substrate cannot honor.

## 5. Accepted design: the advised-step pattern (D2)

Live supervision decomposes into (a) a synchronous advisory channel and
(b) a settlement. omp does (a) better than orc's keystroke transport; (b)
is orc's bread and butter as an ordinary sequential step.

- **Advised step:** a provider step whose omp invocation carries a
  workflow-materialized ensemble config — the advisor (and optionally plan
  role) is part of the provider. The workflow sees one step, one bundle.
- **Settlement step (only when a verdict is needed):** a normal next step
  whose provider reads the exported evidence — including the advisor
  transcript (`__advisor*.jsonl` from the omp session artifacts, copied into
  the run evidence root) — and emits the typed verdict bundle.

What this composition gives up relative to true 2.16: mid-step
workflow-visible intervention (the workflow cannot route or abort on a
supervisor decision while the step runs) and per-message contract
provenance. Given zero current 2.16/2.17 consumers, no existing behavior is
lost.

**Division-of-labor rule (normative once adopted):** use the omp ensemble
when coordination is intra-step quality pressure whose trace is
observability evidence; use 2.16/2.17 when the coordination outcome must be
a workflow-routable fact (gate, approval, settlement) or when mid-step
workflow-visible settlement is genuinely required.

Inside orc workflows the ensemble's plan role is mostly redundant —
plan/implement/review are already separate steps with per-step provider
routing and a reviewable plan artifact. The live advisor is the part orc
cannot cheaply replicate.

### 5.1 Config authority contract (hard requirement)

`~/.omp/agent/config.yml` is hidden operator-global state and must never
define an orc provider's behavior. The ensemble definition
(`.omp/config.yml` with `modelRoles` + `advisor`, `.omp/WATCHDOG.md`) is
materialized by the workflow into the step workspace as versioned assets, so
ensemble identity is part of the workflow's declared inputs, pinned,
diffable, and present in run evidence. The phase-0 trial must confirm
project-level `.omp/` fully overrides user-global config for every field
set. The WATCHDOG.md for orc contexts should point at the step's
materialized acceptance-criteria file rather than "the approved plan"
abstractly.

## 6. Accepted design: RPC session transport (C)

Three pieces behind existing seams; no new `.orc` semantics.

1. **Wire client** (`orchestrator/providers/omp_rpc.py`): ready handshake,
   protocol-v2 negotiation, `rpc_chunk` reassembly, id-correlated commands
   (`prompt`, `steer`, `abort`, `get_state`). Prefer the published Python
   RPC client, version-pinned, wrapped behind a minimal in-repo interface.
2. **Transport driver** (the one genuinely new seam): today input delivery
   is "write prompt bytes to stdin, close stdin", unabstracted. Introduce
   `SessionTransportDriver` selected structurally from `metadata_mode`, with
   `PipeTextDriver` (current behavior, extracted) and `OmpRpcDriver`
   (spawn → ready → negotiate → one `prompt` command carrying the fully
   composed prompt → consume frames to the turn-terminal event → close).
   Rejected alternative: an external shim binary imitating
   `codex exec --json` — it hides handshake failures in another process and
   adds a separately versioned artifact.
3. **Codec + templates:** new `ProviderSessionMetadataMode.OMP_RPC_NDJSON`
   with an `OmpRpcAccumulator` implementing the same structural interface as
   the codex codec (`feed` / `snapshot` / `finalize` / `event_count`):
   `get_state.sessionId` → identity; turn-end/error frames → terminal;
   post-resume start → resume boundary; `message_update` deltas →
   normalized assistant text and the streaming callback. Additive gains:
   usage frames land as structured `{tokens, cost}` in finalize metadata
   (metering by protocol fact), and the ready frame's advertised version is
   recorded as `provider_runtime_version` (harness version becomes run
   evidence). Provider templates stay pure data:
   `fresh_command=["omp","--mode","rpc","--no-session",...]`,
   `resume_command=[...,"--resume","${SESSION_ID}"]`,
   `turn_boundary_resume=True`.

Failure semantics are inherited, not invented: missing ready frame,
negotiation rejection, malformed or over-ceiling frames, turn-failed events,
missing terminal marker, and resume session-id mismatch all map onto the
existing typed transport-error surface and fail the step closed. No silent
fallback between RPC and `-p` modes — one template, one transport.

A phase-2 RPC variant of `InteractiveSessionSupport` (message delivery as
one `steer` frame; turn boundaries as event-frame facts instead of terminal
heuristics; graceful close as protocol close) is specified only in outline
and deliberately deferred until a workflow needs an omp worker under live
binding. The ledger machinery above the transport would not change.

### 6.1 `.orc` exposure: deliberately none

Provider selection stays a provider name; results stay bound-path bundles;
resume, steering, metering, `--stream-output` / `--step-summaries` /
`--live-agent-notes` keep their forms with better data underneath. Spec
footprint when C lands: `specs/providers.md` gains the metadata mode and
driver contract; `docs/capability_status_matrix.md` gains a row; the
provider-template quick reference gains the omp entries. No changes to
`specs/dsl.md` or any Workflow Lisp surface.

## 7. Sequencing

- **Phase 0 (now, zero orc code):** one low-stakes workflow declares a
  pinned `omp` provider via workflow-level provider config — both a bare
  worker and an advised step (e.g., DeepSeek doer + Fable/Sol advisor via
  materialized `.omp/`). Acceptance: bundles validate identically to a
  codex worker; advisor demonstrably runs headless; project config fully
  overrides user-global; per-step cost measured.
- **Phase 1 (if phase 0 is clean):** implement §6 as a normal spec'd change
  in `orchestrator/providers/` — codec/driver unit tests against checked-in
  frame fixtures recorded from the pinned omp version (fixtures double as
  the wire-contract pin), a fake-child driver test for handshake/failure
  paths, one real orchestrator smoke run, no assertions on prompt text.
- **Phase 2 (YAGNI-gated):** RPC interactive variant for live binding, only
  when a workflow needs it.
- **Trial (parallel, outside orc):** supervision cockpit (E) on the next
  fresh non-ES primary; local relay only until the owner makes the
  hosted-relay policy call. The current codex primary stays untouched
  mid-freeze.
- **Post-ES-Task-7:** one-day spike evaluating metaharness as trial
  plumbing under orc's frozen referee layer (orc as referee, metaharness as
  track) for any F2/rerun.
- **Docs:** flag 2.16/2.17 in the capability matrix as "implemented, no
  production consumers; advised-step pattern preferred for new advisory
  work" so authors don't reach for the heavier surface by default.

## 8. Risks and standing constraints

- **Harness drift / treatment identity:** omp is continuously tuned and its
  own benchmarks show harness choice moves agent pass rates severalfold.
  Pin versions (nix flake / mise); record `provider_runtime_version`; treat
  harness identity (codex vs omp, version) as part of the treatment in any
  calibrated workflow, never neutral infrastructure. Never silently swap a
  calibrated workflow's provider harness.
- **Supply chain:** single-lead fork with temporarily open PRs; pin exact
  versions and review upgrades deliberately.
- **Relay policy:** Collab's hosted relay is E2E-encrypted with
  link-possession trust; default to the local relay until the owner
  approves routing repo content through the hosted service.
- **Ensemble cost:** a frontier advisor reads every doer turn;
  `advisor.syncBacklog` bounds latency skew, not spend. Meter in phase 0.
- **Freeze:** nothing in this proposal executes against the ES apparatus
  before hand-back; ensemble providers are out of scope for the frozen
  study's arms.

## 9. Open decisions for the owner

1. Approve phase 0 (pinned omp provider + advised-step trial in one
   low-stakes workflow)?
2. Python RPC client dependency vs minimal in-repo implementation for
   phase 1?
3. Hosted-relay policy for Collab, or local-only standing rule?
4. Adopt the division-of-labor rule (§5) into the drafting guide when the
   omp provider lands?
5. Post-study: schedule the metaharness spike, and does "supervision as
   experimental variable" (bare doer vs advised doer under the ES
   apparatus) belong on the follow-on study list?
