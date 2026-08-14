# OMP Integration: Design And Roadmap Extension

## Metadata

- **Title:** OMP integration — generic worker template, JSON session codec, prompt scaffolder, multiagent conf presets, bidirectional session bridge
- **Status:** proposed
- **Kind:** architecture decision + roadmap extension
- **Owner:** repository owner (decision holder)
- **Created:** 2026-08-14 (**Last material update:** 2026-08-14, lightened and generalized to multiagent conf presets per owner direction)
- **Related:** extends [`2026-08-14-omp-integration-proposal.md`](2026-08-14-omp-integration-proposal.md); spec home on landing [`specs/providers.md`](../../specs/providers.md); authoring home [`docs/lisp_workflow_drafting_guide.md`](../lisp_workflow_drafting_guide.md); omp checkout `~/Documents/oh-my-pi`
- **Implementation target:** one thin tranche + one gated follow-on; nothing touches the frozen ES apparatus

## Summary

Four small pieces, each general rather than omp-shaped, replace the
proposal's phase machinery:

1. **One omp template family** (registry built-ins, pure data) with two
   lanes: `omp` / `omp_unrestricted_workspace` as **general providers
   exactly like the codex family** (bare workers, no conf), and `omp_conf`
   as the **introspective lane** where multiagent topologies (advisors,
   subagent fan-out, peer teams) are configuration files, never orc
   concepts.
2. **One session codec** (`OMP_JSON_STDOUT`) behind the existing
   `create_session_transport_accumulator` seam — which automatically feeds
   the existing run-scoped tmux observation panes, giving live
   `tmux attach` observability with zero new machinery.
3. **One scaffolder** — write a prompt and a conf, get the corresponding
   `.orc` written and executed. Provider-agnostic: omp is just the case
   where the conf is an ensemble directory. The generated workflow calls
   the same shared library procedure hand-authored workflows use.
4. **One bidirectional session bridge** — an orc step's session evidence is
   a real omp session (reopen it interactively with `omp --resume`); an
   ad-hoc interactive omp session imports back into orc as evidence plus a
   regenerated, reproducible `.orc`.

No new `.orc` forms, no RPC client, no driver abstraction, no per-ensemble
code; one small certified staging adapter shared by every consumer.
Grounding corrections from the 2026-08-14
adversarial review (G1–G10) are incorporated by reference; the ones that
shape this design are restated inline where they bind.

## Problem

The proposal (and this document's earlier draft) budgeted integration
machinery per capability: per-ensemble templates, a staging adapter, a
library procedure, an RPC client and driver, phased codecs. The dominant
use case is simpler — *run a prompt under a configured omp, watch it live,
get a typed result* — and the heavy shape makes the simple case cost a
hand-authored workflow plus asset plumbing. Meanwhile two assets that make
the light shape possible already exist and were underused: orc's run-scoped
tmux observation panes (`orchestrator/providers/observation.py`, wired to
codec assistant text at `orchestrator/providers/executor.py:1187`), and
omp's persistent, resumable session JSONL.

## Decision

- **X1 — One template family, two lanes.** Registry built-ins
  (`registry.py:_load_builtin_providers`, pure data), all sharing the
  codec, session persistence, panes, and bridge:
  - *General-provider lane* (`omp`, `omp_unrestricted_workspace`): omp as
    a codex-class worker — externs-manifest name, `${model}` param,
    `${PROMPT}` in, bundle out, resume via `${SESSION_ID}`. No conf mount:
    a hermetic empty agent dir (missing config is defined as empty →
    schema defaults), `--no-extensions --no-title`, pinned approval mode.
    Usable anywhere `codex` is usable, including as a drop-in externs
    swap.
  - *Introspective lane* (`omp_conf`): the strict conf mount
    (`.omp-conf/`) carrying a preset topology. Topology identity is data
    (conf digest + `omp --version`), not a template per topology.
  Calibrated workflows that need identity-by-name may still pin dedicated
  named templates; that is a naming convention, not machinery.
- **X2 — One codec, panes for free.** `OMP_JSON_STDOUT` parses
  `omp --mode json` stdout (session header id → fail-closed identity;
  `message_update`/`message_end` → assistant text; `turn_end`/`agent_end` →
  terminal + embedded usage → `{tokens, cost}`; error surfaces → typed
  transport error). The assistant-text callback is what observation panes
  display, so every omp step is live-watchable at
  `tmux -S <run observation socket> attach` the day the codec lands.
  The RPC stack (client, driver, `steer`) stays out entirely, gated on a
  named consumer needing mid-turn control; recorded fallback if
  `--mode json` proves insufficient (F2/F5) is the proposal's original C.
- **X3 — Scaffolder: prompt + conf → generated `.orc` → run.** A CLI
  entry that deterministically generates a minimal one-step workflow, its
  externs manifests, and a pinned conf copy, then compiles and runs it —
  writing the generated `.orc` to disk as an ordinary, editable,
  versionable artifact. The generated workflow *contains* its staging (it
  calls the shared library procedure), so a bare `orchestrator run` on
  `run.orc` behaves identically to the scaffolder — the CLI performs no
  staging of its own. General: `--provider codex_gpt55` works identically;
  the conf argument is simply absent.
- **X3a — Shared library procedure, not per-workflow glue.** One
  `defproc` family under `workflows/library/omp/` owns conf staging +
  provider call + advisor-evidence wiring for every consumer (generated
  and hand-authored). Reason it stays despite the lighter shape: the
  scaffolder covers whole-workflow entry only; hand-authored multi-step
  workflows embedding an omp step would otherwise each re-invent staging
  and evidence wiring — exactly the copy-paste the procedure-first reuse
  contract bans — and the generated artifact would stop being
  self-contained if the CLI staged instead.
- **X4 — Bidirectional session bridge.** Forward: the step's persisted
  session (under the staged agent dir, inside the step workspace) is
  evidence *and* a live omp artifact — `omp --resume <id>` with the same
  `PI_CODING_AGENT_DIR` reopens it interactively for post-hoc inspection.
  Reverse: `import` of any omp session JSONL produces (a) typed evidence
  (messages, usage, models) and (b) a regenerated scaffold (prompt from the
  first user message, conf snapshot) so an interactive exploration becomes
  a reproducible orc run. Neither direction makes prose an authority:
  bundles remain the only result channel.
- **X5 — Hermeticity + admission rule retained from the review, compressed.**
  Every omp invocation: relocated agent dir (`PI_CODING_AGENT_DIR` → staged
  conf), strict `--config` overlay, advisor tools pinned in `WATCHDOG.yml`
  (read-only is an omp *default*, not a guarantee), `memory` explicitly
  disabled, sessions persisted (no `--no-session`; `--resume` gets full
  ids). Admission tiers stand: intra-step omp capabilities (advisor,
  subagents, roles, skills) are conf; boundary-crossing capabilities wait
  for consumers; hub/IRC state must not outlive its step; memory and
  cross-step revival are banned. Acceptance is adversarial (planted
  canaries in `~/.omp`, ancestor `.claude`), not "override confirmed".
- **X6 — Supported multiagent conf patterns.** The design supports omp's
  useful multiagent patterns as named conf presets under
  `workflows/assets/omp_confs/`, all intra-step and all riding the same
  template/procedure/codec unchanged: `advised/` (advisor + worker),
  `fanout/` (primary + declarative `agents/*.md` task subagents with
  schema-validated yields in isolated worktrees), `peer-team/` (fan-out
  plus the `hub` tool granted to subagents for intra-step DMs and roster
  coordination), and `advised-fanout/` (advisor watching a fanning-out
  primary). A preset pins everything behavior-relevant: models per role,
  advisor roster + tools, agent definitions + `spawns` depth, tool grants.
  Subagent yields terminate at the omp primary (never a second orc result
  channel); the primary's bound-path bundle stays the only result. What
  remains out: cross-step hub/parked state, memory, and mid-turn workflow
  control (RPC gate) — the boundary is the step, not the pattern.

## Design Details

### The template family (all omp-specific runtime knowledge, in one place)

```python
# General-provider lane — omp as a codex-class worker; no conf.
# Missing agent-dir config is defined as empty (schema defaults);
# --no-extensions/--no-title cut ambient surface and a wasted title call.
"omp": ProviderTemplate(
    name="omp",
    command=["env", "PI_CODING_AGENT_DIR=.omp-agent",
             "omp", "--mode", "json",
             "--no-extensions", "--no-title",
             "--approval-mode", "write",
             "--model", "${model}", "${PROMPT}"],
    defaults={"model": "deepseek/deepseek-v4"},
    input_mode=InputMode.ARGV,
    session_support=ProviderSessionSupport(
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        fresh_command=[...same...],
        resume_command=[..., "--resume", "${SESSION_ID}", "${PROMPT}"],
        turn_boundary_resume=True,
    ),
)

# Trusted-workspace variant, parallel to codex/claude *_unrestricted_workspace:
# same argv with --yolo instead of --approval-mode write; no defaults,
# stdin input mode (piped stdin auto-enables print mode), per the existing
# unrestricted-profile conventions in specs/providers.md.
"omp_unrestricted_workspace": ProviderTemplate(...)

# Introspective lane — strict conf mount; used by every preset.
# Topology (advisor on/off, agents, roles, tool grants) lives entirely in
# the conf; the argv is preset-independent.
"omp_conf": ProviderTemplate(
    name="omp_conf",
    command=["env", "PI_CODING_AGENT_DIR=.omp-conf/agent",
             "omp", "--mode", "json",
             "--no-extensions", "--no-title",
             "--approval-mode", "write",
             "--config", ".omp-conf/config.yml",
             "--model", "${model}", "${PROMPT}"],
    defaults={"model": "deepseek/deepseek-v4"},
    input_mode=InputMode.ARGV,
    session_support=ProviderSessionSupport(... as above ...),
)
```

Approval mode is pinned in argv (a runtime override) on both lanes so it
is evidence-visible and cannot drift via config; `write` is the
conservative default and F7 verifies it suffices for ordinary worker
tasks, else the template adjusts before landing. The advised presets do
not need an `--advisor` flag: `advisor.enabled: true` in the mounted
`config.yml` owns topology, keeping one conf template for all four
presets.

`.omp-conf/` is `omp_conf`'s fixed mount point in the step workspace.
Whatever the
conf contains — advisor roster, subagent definitions, peer-team tool
grants, model roles, skills — is invisible to orc and fully recorded: conf
digest, `omp --version`, per-agent metering, and the session JSONL land in
run evidence.

### Conf pattern presets (`workflows/assets/omp_confs/`)

| Preset | conf contents | Evidence facts recorded |
| --- | --- | --- |
| `advised/` | `config.yml` (advisor role, `syncBacklog`), `agent/WATCHDOG.yml` (pinned read-only tools), `WATCHDOG.md` | advisor transcript non-empty, advisor usage |
| `fanout/` | `agent/agents/*.md` (models, tools, `spawns: none`, output schemas) | subagent count, per-agent tokens/cost, worktree cleanup check |
| `peer-team/` | `fanout/` plus `hub` in agent tool grants | as `fanout/` plus hub-message activity in session artifacts |
| `advised-fanout/` | union of `advised/` + `fanout/` | union of both fact sets |

Presets compose by file union; a workflow-specific conf starts as a copy of
a preset and is pinned by digest like any other. The liveness principle
generalizes: each preset names the evidence fact that proves its topology
actually ran (a dead advisor, a fan-out that never spawned, a peer team
that never messaged — all visible, never silent).

Canonical `advised/` content (normative for the preset; asset files land
with tranche 1):

```yaml
# config.yml — passed via strict --config overlay
modelRoles:
  # NO `default:` here — the template's `--model ${model}` is a runtime
  # override and beats every config layer (verified precedence:
  # defaults <- global <- project <- --config overlays <- runtime
  # overrides). The primary model is the step's `:model` param, where orc
  # records it as treatment identity; a preset `default:` would be
  # silently shadowed dead config.
  task: deepseek/deepseek-v4-pro:high          # consumed by fanout presets
  plan: openai-codex/gpt-5.6-sol:xhigh
  slow: openai-codex/gpt-5.6-sol:xhigh
  advisor: openai-codex/gpt-5.6-sol:xhigh
advisor:
  enabled: true
  syncBacklog: "1"     # string enum "off"|"1"|"3"|"5" (settings-schema.ts:471)
memory:
  enabled: false       # explicit pin — unset fields deep-merge from operator globals
```

```yaml
# agent/WATCHDOG.yml — required companion; the read-only grant is an omp
# DEFAULT, so the preset pins it explicitly
advisors:
  - name: Supervisor
    enabled: true
    tools: [read, grep, glob]
```

Preset rules distilled: every ambient-sensitive field set explicitly
(`memory`, `advisor.*`, every consumed role); `modelRoles.default` omitted;
advisor tool grants always pinned; an unresolvable advisor model surfaces
as `no_model` + a failing liveness fact, never a silent bare run.

### The shared library procedure (`workflows/library/omp/`)

```lisp
(defrecord ConfMount
  (conf-digest String)          ; sha256 of the staged conf tree (evidence authority)
  (advisor-transcript Path))    ; expected __advisor.<slug>.jsonl location

(defproc omp-attempt
  ((conf Path.conf) (prompt-inputs ...) ...) -> OmpAttempt
  :effects ((uses-command commands.stage-omp-conf)
            (uses-provider providers.worker))
  :lowering inline
  (let* ((mount (command-result commands.stage-omp-conf
                  :inputs (conf)
                  :returns ConfMount))       ; copies conf → .omp-conf/, computes digest
         (attempt (provider-result providers.worker
                    :prompt prompts.task
                    :inputs (...)
                    :returns ...)))
    (make-omp-attempt :attempt attempt
                      :conf-digest mount.conf-digest
                      :advisor-transcript mount.advisor-transcript)))
```

`stage-omp-conf` is one certified command adapter (copy tree, compute
digest, emit `ConfMount`); any logic beyond copy + digest + path injection
is out of contract. The settlement tier contracts (`AdvisorSettlement`:
`verdict`, `advisor-note-count`, `unresolved-blockers`) live in the same
library module for workflows that route on an advised verdict. Ordinary
forms only; nothing here is compiler-visible.

### The scaffolder (the simple case costs one command)

```bash
orchestrator prompt run \
  --prompt task.md \
  --conf workflows/assets/omp_confs/ds_fable_advised/ \
  --provider omp \
  --returns '{"summary": "String", "files_changed": "List[String]"}'
```

Deterministic generation (same inputs → byte-identical outputs) under
`workflows/generated/<slug>/`:

```
workflows/generated/<slug>/
├── run.orc            # defworkflow calling omp-attempt; :returns from --returns
├── providers.json     # {"providers.worker": "omp_conf"} (bare runs: "omp")
├── prompts.json       # {"prompts.task": "task.md"}
└── conf/              # pinned copy of --conf (self-contained, versionable)
```

then compiles, runs, streams the pane, and prints the bundle path and
`tmux attach` command. The CLI itself stages nothing: `run.orc` calls
`omp-attempt`, whose `stage-omp-conf` step mounts `conf/` → `.omp-conf/`
at run time, so a later bare `orchestrator run run.orc` is byte-for-byte
the same execution. The scaffolder selects the lane from its inputs:
`--conf` present → `omp_conf` + the staging call; absent → a direct
`provider-result` on the named provider (`omp`, `codex_gpt55`, any
registry name) with no staging step. Generated files are ordinary
artifacts: edit `run.orc` and it is simply a hand-authored workflow from
then on — the scaffolder is an on-ramp, not a dialect. Omitting
`--returns` defaults to a single `String` result field. Regeneration is
edit-safe by determinism: when the output directory exists, `prompt run`
regenerates in memory and compares — identical bytes proceed as a no-op,
differing bytes prove hand-editing and the command refuses without
`--force`; it never silently overwrites authored content.

### Observability (existing machinery, documented not built)

`ProviderObservationManager` already owns a private run-scoped tmux server;
ordinary invocations already attempt a pane; the codec's normalized
assistant text is already the pane's display stream
(`executor.py:1187-1191`). Deliverables here are only: the codec (X2), the
scaffolder printing the attach command, and a short runbook note in
`docs/workflow_monitoring.md`. Panes stay observation-only — no captured
pane data enters evidence (existing invariant). Interactive *control*
(typing into the live session) is explicitly not this surface; it waits
behind the same consumer gate as RPC `steer`.

### The bridge, both directions

- **orc → omp:** after (or during) a run,
  `PI_CODING_AGENT_DIR=<evidence>/omp-agent omp --resume <session-id>`
  opens the recorded session in the full TUI — inspection, `/advisor dump`,
  forking — without any orc involvement. Feasibility F1 (session files land
  under the relocated agent dir) is the one open prerequisite.
- **omp → orc:** `orchestrator prompt import <session.jsonl>` emits typed
  evidence (message/usage/model facts) and regenerates the scaffold inputs
  (prompt, model, conf snapshot) so the run can be repeated as an orc step.
  Import is evidence-only: it never fabricates a bundle for the original
  interactive session.

## Contracts And Interfaces

- New enum member + codec: spec home `specs/providers.md` on landing;
  fixtures from the pinned build are the wire pin.
- New CLI: `orchestrator prompt run|import` — spec home `specs/cli.md` on
  landing; generation is deterministic and side-effect-free apart from the
  named output directory.
- Generic `omp` built-in: provider template table in `specs/providers.md`.
- Library contracts (`ConfMount`, `OmpAttempt`, `AdvisorSettlement`,
  `omp-attempt`, `stage-omp-conf`): owned by `workflows/library/omp/`,
  not spec surfaces; the adapter is certified under the command-adapter
  contract.
- Unchanged: `.orc` grammar, bundle authority, resume/steering CLI forms,
  codex estate, 2.16/2.17 surfaces (their deprecate-or-commit decision
  point stands, scheduled at this tranche's close).
- Failure behavior: header/id/terminal anomalies and malformed frames fail
  the step closed on the existing typed transport-error surface; missing
  conf overlay is a hard process error; no fallback between json and text
  modes.
- omp surfaces consumed — the complete contract-point inventory; everything
  else in omp is opaque, version-pinned harness internals free to churn
  under the pin:

| Contract point | omp component | Our consumer | Pin |
| --- | --- | --- | --- |
| CLI argv: `-p`/`--mode json`, `--config`, `--model`, `--resume <full-id>`, `--approval-mode`, `--no-extensions`, `--no-title` | `cli/args.ts`, `cli/flag-tables.ts`, `modes/print-mode.ts` | provider templates (both lanes) | template + upgrade review |
| Config semantics: precedence, `PI_CODING_AGENT_DIR` relocation, `modelRoles`/`advisor.*`/`memory` fields | `config/settings-schema.ts`, config resolution | conf presets, hermeticity (X4) | canary tests (F3) |
| stdout NDJSON events: session header, `message_update`/`message_end`, `turn_end`/`agent_end`, embedded `Usage`, `notice` | `packages/agent/src/types.ts`, `session/agent-session-events.ts`, `packages/catalog` `Usage` | `OMP_JSON_STDOUT` codec, panes | checked-in frame fixtures |
| Session persistence: `SessionHeader.id`, append-only session JSONL, `__advisor.<slug>.jsonl`, resume | `session/session-manager.ts`, `session/session-entries.ts`, `advisor/transcript-recorder.ts` | identity check, evidence, bridge (`omp --resume`, import) | F1 + fixtures |
| Advisor subsystem: headless `--advisor`, WATCHDOG discovery, emission guard, `syncBacklog` | `src/advisor/*` | `advised*` presets | preset pins + liveness fact |
| Subagent system: `agents/*.md` frontmatter, schema-validated yields, worktree isolation, per-agent metering, `hub` tool | `src/task/*`, `discovery/helpers.ts`, `registry/agent-registry.ts`, `tools/hub` | `fanout/`/`peer-team/` presets | F6 + preset pins |
| Version identity | `omp --version` | `provider_runtime_version` evidence | recorded per invocation |

  Deliberately NOT consumed: RPC/ACP modes and the `omp-rpc` client
  (phase-2 gate), collab/relay (ops trial only), metaharness (post-ES
  spike), memory backends (banned), Agent Hub TUI/cross-step revival
  (banned beyond step scope), extensions/hooks/skills/MCP (admissible
  later as conf, not in the four presets).

## Feasibility Prerequisites (exit criteria for the tranche's first run)

- **F1** [open]: session JSONL (incl. `__advisor.<slug>.jsonl` and subagent
  artifacts) lands under the relocated agent dir. [INFERENCE from
  `config-usage.md`; one run.]
- **F2** [open]: `--advisor` composes with `--mode json` (advisor events +
  drain under JSON print mode).
- **F3** [open]: hermeticity canaries (user-global config, user WATCHDOG,
  ancestor `.claude`) provably absent from behavior and evidence.
- **F5** [open]: resume-boundary observability under
  `--mode json --resume` sufficient for `turn_boundary_resume`.
- **F6** [open]: task-subagent activity under `--mode json` is observable
  in evidence (per-agent metering, yields in the primary session, worktree
  cleanup on step end).
- **F7** [open]: bare-lane neutrality and headless completion — a fresh
  empty agent dir yields schema defaults with memory/advisor off; an
  ordinary bash+edit worker task completes under `--approval-mode write`
  (else the lane's pinned mode is adjusted); stdin input composes with
  `--mode json` for the unrestricted variant.

## Roadmap

- **Tranche 1 (one reviewed change):** the omp template family (`omp`,
  `omp_unrestricted_workspace`, `omp_conf`) + codec +
  fixtures + `workflows/library/omp/` (`omp-attempt`, `stage-omp-conf`
  adapter, settlement contracts) + conf presets
  (`workflows/assets/omp_confs/`) + scaffolder (`run`/`import`) +
  monitoring-doc note + the two-arm bare-vs-advised trial: one `run.orc`
  on `omp_conf`, arms differing only in the digest-pinned conf input
  (neutral `advisor.enabled: false` conf vs `advised/`), plus one
  `fanout/` preset smoke (F6) and one bare-lane `omp` smoke (F7).
  Exit: F1–F7
  resolved; canary scenario passes; codec unit + fake-child tests green;
  one real orchestrator smoke; cost and wall-time (advisor drain ≤10 min,
  `syncBacklog` stalls) measured and reported.
- **DP-A (at tranche close):** 2.16/2.17 deprecate-or-commit;
  drafting-guide guidance (advised-conf conventions, admission tiers)
  enters only with the trial evidence — normativity stays evidence-gated.
- **Gated follow-on:** RPC interactive lane (client, driver, `steer`,
  live-attach *control*) only when a named workflow needs mid-turn
  intervention. Relay policy (hosted vs single-machine; loopback-only
  local relay) remains an independent owner decision.
- **Post-ES-hand-back:** metaharness spike and supervision-as-variable
  study candidacy, unchanged from the proposal, with the tranche-1 trial
  as pilot data.

## Invariants And Failure Modes

Proposal invariants 1–5 bind unchanged. Added: conf digest + harness
version are mandatory evidence for every omp step; advisor liveness
(non-empty advisor transcript, usage > 0) is recorded per attempt so a
silently dead advisor never silently narrows a treatment; hub/IRC state
never outlives its step; memory stays explicitly disabled; generated
workflows are ordinary workflows (no generated-only runtime path).

## Verification Strategy

Codec fixture tests (identity, terminal, resume boundary, usage, error
mapping, malformed input — negative tests fail closed); fake-child process
tests; scaffolder determinism test (same inputs → identical bytes),
self-containment test (scaffolder run ≡ bare `orchestrator run` on the
generated `run.orc`), and round-trip test (`run` → `import` → regenerated
scaffold equals original modulo session facts); library-procedure staging
and evidence-wiring coverage; the canary acceptance scenario as explicit negative
tests; one real smoke run; behavioral assertions only, no prompt-text
assertions; `pytest --collect-only` on new test modules.

## Declarative Acceptance Scenario

Clean checkout; canaries planted in `~/.omp/agent/` and an ancestor
`.claude/`; run `orchestrator prompt run --prompt task.md --conf
workflows/assets/omp_confs/advised/ --provider omp --returns
'{"summary":"String"}'`. Expected: generated
`.orc` + manifests written; run completes with a schema-valid bundle;
evidence contains session JSONL, non-empty advisor transcript, conf digest,
`omp --version`, tokens/cost; the printed `tmux attach` target shows live
assistant text during the run; `omp --resume` against the evidence agent
dir reopens the session. Forbidden: any canary influence; any result read
from stdout; any difference between the generated workflow's execution and
the same workflow run by hand with `orchestrator run`.

## Stop / Revise Criteria

F3 leak with no hermetic fix → revise isolation before adoption. F2/F5/F6
failure for a preset → that preset is withheld (transport fallback for
F2/F5 remains proposal option C). Trial shows no
advised-arm signal at material cost → conf pattern stays available,
guidance does not become a default. Upstream `--mode json`/session-layout
change under the pin → wire-contract break: re-record fixtures, re-review.

## Documentation Impact

On landing: `specs/providers.md` (mode, template), `specs/cli.md`
(`prompt run|import`), capability-matrix rows (omp provider, codec,
scaffolder; 2.16/2.17 annotation), `docs/workflow_monitoring.md` (attach
runbook), index entry. Drafting-guide text waits for DP-A.

## Open Questions (owner)

1. Approve tranche 1 as scoped (single reviewed change, trial included)?
2. Scaffolder namespace: `orchestrator prompt run|import` vs a flag on
   `orchestrator run` — default is the former; not blocking.
3. DP-A timing confirmation; relay policy independent as before.
