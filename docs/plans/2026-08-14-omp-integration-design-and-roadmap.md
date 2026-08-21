# OMP Integration: Design And Roadmap Extension

## Metadata

- **Title:** OMP integration — generic worker template, JSON session codec, prompt scaffolder, multiagent conf presets, bidirectional session bridge
- **Status:** accepted; owner selected `OMP-I1` tranche 1 on 2026-08-21, with activation blocked only until frozen-ES hand-back; the owner-approved declarative capability extension remains lower-priority, pending, unselected `OMP-I2`
- **Kind:** architecture decision + roadmap extension
- **Owner:** repository owner (decision holder)
- **Created:** 2026-08-14 (**Last material update:** 2026-08-21, tranche-1 selection recorded and design inconsistencies resolved; declarative skill/extension selection remains a lower-priority follow-on behind `OMP-I1`)
- **Related:** extends [`2026-08-14-omp-integration-proposal.md`](2026-08-14-omp-integration-proposal.md); spec home on landing [`specs/providers.md`](../../specs/providers.md); authoring home [`docs/lisp_workflow_drafting_guide.md`](../lisp_workflow_drafting_guide.md); omp checkout `~/Documents/oh-my-pi`
- **Implementation target:** one thin `OMP-I1` tranche plus independently gated follow-ons; `OMP-I2` is lower priority and nothing touches the frozen ES apparatus
- **Upstream pin:** `oh-my-pi` tag `v17.3.4`, commit `ffd53ff92a6f575d499730475a73460dd7cc2eea`; capture binary `/home/ollie/.local/bin/omp` reports `omp/17.3.4` and has SHA-256 `3fce4b25628064b0cd7bfbc6245ecdada331750ed4b341aca6bd29ba4478aab5`

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
3. **One scaffolder** — supply the task prompt inline or from a file; the
   system materializes it as an ordinary workflow-owned prompt asset and
   canonical prompt extern. Describe the desired output in prose (or supply an
   exact return schema), optionally add a conf, and get the corresponding
   `.orc` written and executed. Provider-agnostic: omp is just the case where
   the conf is an ensemble directory. The generated workflow calls the same
   shared library procedure hand-authored workflows use.
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
  `message_update`/`message_end` → assistant text; terminal message `Usage`
  (not optional `agent_end.telemetry`) → `{tokens, cost}`; error surfaces →
  typed transport error). Unknown event types are tolerated; a missing or
  non-first session header fails identity closed. The assistant-text callback
  is what observation panes
  display, so every omp step is live-watchable at
  `tmux -S <run observation socket> attach` the day the codec lands.
  The RPC stack (client, driver, `steer`) stays out entirely and is not a
  fallback. A named consumer needing mid-turn control must separately activate
  the gated RPC follow-on.
- **X3 — Scaffolder: prompt artifact + output contract + optional conf →
  generated `.orc` → run.** A CLI entry requires exactly one of
  `--prompt TEXT` and `--prompt-file PATH`. One materializer validates
  non-empty UTF-8, writes the exact bytes as workflow-owned `prompt.md`, and
  emits the canonical `{"prompts.task":{"asset_file":"prompt.md"}}` binding
  in `prompts.json`; it performs no model rewrite or path auto-detection. The
  existing prompt-extern normalizer produces the ordinary `PromptExtern`.
  The CLI then generates a minimal one-step workflow, its remaining externs
  manifest, a canonical output-contract artifact, and an optional pinned conf
  copy, compiles, and runs it — writing every generated input as an ordinary,
  editable, versionable source artifact. The generated workflow *contains*
  its staging, so a bare `orchestrator run` on `run.orc` behaves identically
  without the original CLI working directory or prompt-file path. General:
  `--provider codex_gpt55` works identically; the conf argument is simply
  absent.
  `--provider` always names the exact generated provider extern; the CLI does
  not rewrite `omp` to `omp_conf`. A conf-backed run therefore uses
  `--provider omp_conf --conf PATH`; `--provider omp` has no conf input and
  rejects `--conf`.
- **X3a — Shared library procedure, not per-workflow glue.** One
  `defproc` family under `workflows/library/omp/` owns conf staging +
  provider call + advisor-evidence wiring for every consumer (generated
  and hand-authored). Reason it stays despite the lighter shape: the
  scaffolder covers whole-workflow entry only; hand-authored multi-step
  workflows embedding an omp step would otherwise each re-invent staging
  and evidence wiring — exactly the copy-paste the procedure-first reuse
  contract bans — and the generated artifact would stop being
  self-contained if the CLI staged instead.
- **X3b — Natural-language output intent becomes one canonical authored
  contract, never model-written source.** `--output TEXT` and exact
  `--returns JSON` are mutually exclusive; neither means the existing direct
  `String` default. `--output` runs checked-in
  `infer-output-contract.orc` as one ordinary typed provider call using the
  named provider/model without task conf. Its fixed `OutputContractDraft`
  contains only ordered field names and type-expression strings; no source
  and no prompt-visible prose. The scaffold derives the record name and
  preserves the user's `--output` text verbatim as the sole result
  description.

  Inferred draft, exact JSON, default `String`, pinned reuse, and import all
  normalize into one versioned `ScaffoldOutputContract` IR before codegen.
  Type strings pass through the Workflow Lisp frontend's existing recursive
  parser/canonical renderer, identifier rules, and string-atom encoder; the
  scaffolder adds only the narrower scalar/collection admission policy
  (`String`, `Bool`, `Int`, `Float`, `Optional`, `List`,
  `Map[String,T]`). One deterministic renderer constructs only the known
  `defrecord` and `:returns` syntax. The ordinary compiler must accept the
  complete source and derive a return contract/guidance structurally equal to
  the IR before the task provider starts. Invalid synthesis fails closed; no
  second type grammar, source template parser, widening, or `String`
  fallback is permitted.
- **X3c — The small native phase-zero bridge is the self-hosting boundary.**
  The inference workflow must compile before its provider can produce the
  field set, so its active type environment cannot also contain the inferred
  result. Native code may sequence inference → canonical IR → deterministic
  rendering → fresh ordinary compilation; it may not interpret output intent,
  invent language semantics, or dynamically install a type into the running
  workflow. This is the bootstrap kernel, not a second runtime lane.
- **X4 — Bidirectional session bridge.** Forward: the step's persisted
  session (under the staged agent dir, inside the step workspace) is
  evidence *and* a live omp artifact — `omp --resume <id>` with the same
  `PI_CODING_AGENT_DIR` reopens it interactively for post-hoc inspection.
  Orc-born session evidence also carries the compiler-derived
  `ScaffoldOutputContract` (or a digest-bound sidecar reference), bound to
  the generated-source and session identities.

  Reverse: `import` produces typed message/usage/model evidence and
  regenerates the recorded originating task prompt through the same
  `prompt.md` + canonical prompt-extern materializer, alongside model/conf
  inputs. A matching contract sidecar restores the exact return contract;
  transcript prose never reconstructs one. An arbitrary omp session without a
  sidecar requires explicit `--output` or `--returns`, or deliberately uses
  the documented direct-`String` default. Import never fabricates a result
  bundle: bundles remain the only result channel.
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
    command=["env", "-u", "OMP_PROFILE", "-u", "PI_PROFILE",
             "PI_CODING_AGENT_DIR=.omp-agent", "omp", "--mode", "json",
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
    command=["env", "-u", "OMP_PROFILE", "-u", "PI_PROFILE",
             "PI_CODING_AGENT_DIR=.omp-conf/agent", "omp", "--mode", "json",
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
conservative default and F6 verifies it suffices for ordinary worker
tasks, else the template adjusts before landing. The advised presets do
not need an `--advisor` flag: `advisor.enabled: true` in the mounted
`config.yml` owns topology, keeping one conf template for all five
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
| `neutral/` | `config.yml` (`advisor.enabled: false`, `memory.backend: "off"`; no role or WATCHDOG files) | conf digest, zero advisor/subagent activity |
| `advised/` | `config.yml` (advisor role, `syncBacklog`), `agent/WATCHDOG.yml` (pinned read-only tools), `WATCHDOG.md` | advisor transcript non-empty, advisor usage |
| `fanout/` | `agent/agents/*.md` (models, explicit tools excluding `task`, output schemas) | subagent count, per-agent tokens/cost, worktree cleanup check |
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
  backend: "off"       # exact schema key; unset fields deep-merge from operator globals
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
  --prompt "Implement the requested repository change and run its required checks." \
  --conf workflows/assets/omp_confs/advised/ \
  --provider omp_conf \
  --output "A concise summary, repository-relative files changed, whether \
all required checks passed, and any unresolved problems"
```

Task-prompt authoring and result-contract authoring are separate. Exactly one
of `--prompt TEXT` and `--prompt-file PATH` is required. The former encodes
the literal argument as UTF-8; the latter strictly validates UTF-8 and copies
the source bytes. Neither trims, normalizes, summarizes, templates, or sends
the prompt through a model. Both write `prompt.md` beside `run.orc` and emit:

```json
{
  "prompts.task": {
    "asset_file": "prompt.md"
  }
}
```

`asset_file` is the existing source-owned prompt surface: the generated
workflow tree now owns the prompt. Build normalization turns the manifest
entry into the existing `PromptExtern`; there is no new prompt IR or runtime
object model. `--prompt-file` is an ingestion convenience, not a retained
reference to the caller's path.

`--output TEXT` is the human-facing path: one ordinary typed provider
preflight converts the intent into an `OutputContractDraft` containing an
ordered list of `{name, type_expression}` fields. `--returns JSON` is the
exact, no-model-call path and accepts the canonical contract-root schema.
They are mutually exclusive; omitting both constructs the direct-`String`
root through the same normalizer. Synthesis uses the requested provider/model
without task conf in an isolated authoring workspace.

Every path produces the same semantic artifact:

```json
{
  "schema": "scaffold-output-contract.v1",
  "contract": {
    "target_dsl": "2.15",
    "root": {
      "kind": "record",
      "name": "TaskResult",
      "description": "A concise summary, repository-relative files changed, whether all required checks passed, and any unresolved problems",
      "fields": [
        {
          "name": "summary",
          "type": {"kind": "primitive", "name": "String"}
        },
        {
          "name": "files-changed",
          "type": {
            "kind": "list",
            "item": {"kind": "primitive", "name": "String"}
          }
        },
        {
          "name": "checks-passed",
          "type": {"kind": "primitive", "name": "Bool"}
        },
        {
          "name": "unresolved-problems",
          "type": {
            "kind": "list",
            "item": {"kind": "primitive", "name": "String"}
          }
        }
      ]
    }
  },
  "semantic_digest": "<digest of schema + contract only>",
  "provenance": {
    "provider": "omp",
    "model": "<resolved model>",
    "session_id": "<synthesis session>",
    "usage": {}
  },
  "generated_source": {
    "renderer": "workflow-lisp-scaffold.v1",
    "sha256": "<run.orc digest>"
  }
}
```

`contract` is the sole codegen/regeneration authority; ordered fields are
semantic. `provenance` records the nondeterministic authoring call but is
excluded from semantic equality and its digest. `generated_source` detects
manual edits and renderer drift. The scaffolding component owns this stable
external envelope. Workflow Lisp frontend APIs own recursive type parsing and
canonical spelling, symbol admissibility, Lisp string-atom encoding, syntax
construction, and the final compile check. The CLI only sequences those
operations and publishes artifacts.

```
workflows/generated/<slug>/
├── run.orc               # ordinary source rendered from canonical contract
├── prompt.md             # exact literal/file/imported task prompt bytes
├── prompts.json          # {"prompts.task":{"asset_file":"prompt.md"}}
├── output-contract.json  # canonical contract + orthogonal provenance
├── providers.json        # {"providers.worker": "omp_conf"} (bare: requested provider)
└── conf/                 # only with --conf; pinned and versionable
```

For the command above, the deterministic renderer emits:

```lisp
(defrecord TaskResult
  (summary String)
  (files-changed List[String])
  (checks-passed Bool)
  (unresolved-problems List[String]))

;; In the generated provider call:
:returns
  (result TaskResult
    :description "A concise summary, repository-relative files changed, whether all required checks passed, and any unresolved problems")
```

The task prompt is the exact user-authored `prompt.md`; independently, the
only free-form output-contract guidance is the user's verbatim `--output`
text. The model selects result structure but supplies no field guidance.
Source-safe serialization alone would not make model prose safe because
result guidance is appended to the write-enabled task provider prompt.

The scaffolder prints the canonical contract, writes the artifacts, compiles,
structurally compares the compiler-derived return contract/guidance with the
IR, immediately runs, streams the pane, and prints the bundle path and
`tmux attach` command. The CLI itself stages nothing: `run.orc` calls
`omp-attempt`, whose `stage-omp-conf` step mounts `conf/` → `.omp-conf/`.
Absent conf means a direct `provider-result` on the requested registry
provider with no staging step.

Generated files are ordinary source artifacts. While `run.orc` matches
`generated_source.sha256`, regeneration uses `contract`; after a manual
`.orc` edit, its compiled contract becomes execution authority and the
sidecar is stale regeneration metadata. `prompt.md` is independently authored
source: a matching literal or file may reuse it, but differing existing bytes
cannot be overwritten silently. The output-contract sidecar never owns the
task prompt. The command refuses a generated-source, prompt-asset, sidecar,
output-intent, semantic-contract, or renderer mismatch without `--force`;
force is explicit destructive regeneration, never reconciliation.
Exact/default generation is deterministic from raw inputs. The first
`--output` synthesis is nondeterministic, but matching pinned-contract reruns
make no second model call and reproduce identical source bytes.

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
  `env -u OMP_PROFILE -u PI_PROFILE PI_CODING_AGENT_DIR=<evidence>/omp-agent omp --resume <session-id>`
  opens the recorded session in the full TUI — inspection, `/advisor dump`,
  forking — without any orc involvement. Feasibility F1 (session files land
  under the relocated agent dir) is the one open prerequisite.
- **omp → orc:** `orchestrator prompt import <session.jsonl>` emits typed
  message/usage/model evidence and regenerates prompt/model/conf inputs.
  Orc-born sessions carry a digest-bound canonical-contract sidecar/reference,
  so import routes that exact IR through the same renderer. Arbitrary sessions
  without it require explicit output intent/exact contract or use the stated
  direct-`String` default. Transcript prose is evidence, never a contract
  authoring surface, and import never fabricates a bundle for the original
  interactive session.

## Contracts And Interfaces

- New enum member + codec: spec home `specs/providers.md` on landing;
  fixtures from the pinned build are the wire pin.
- New CLI: `orchestrator prompt run|import` — spec home `specs/cli.md` on
  landing. `prompt run` requires exactly one of literal `--prompt TEXT` and
  explicit `--prompt-file PATH`; both publish the same source-owned
  `prompt.md` and canonical `asset_file` prompt-extern binding with no model
  transformation. It independently owns mutually exclusive `--output TEXT`
  (model-assisted draft) and `--returns JSON` (exact canonical root),
  immediate execution, and edit-safe regeneration. `prompt import` uses the
  same prompt materializer, carries a digest-bound canonical contract when
  available, and never infers that contract from transcript prose. No direct
  model client: synthesis is an ordinary provider invocation.
  `--provider` is literal provider identity: `--conf` requires a conf-capable
  template such as `omp_conf`; no implicit `omp` → `omp_conf` remapping exists.
- `ScaffoldOutputContract.v1` is the single public scaffold IR/envelope for
  inferred, exact, default, cached, and imported contracts. The scaffolding
  component owns its codec, policy subset, provenance split, and artifact
  publication. Workflow Lisp frontend code owns or exposes the shared type,
  identifier, string-atom, syntax-rendering, and compile-check primitives; the
  CLI must not duplicate them.
- Generic inference workflow and fixed `OutputContractDraft`: owned by
  `workflows/library/scaffolding/`; the model returns ordered structural data
  only.
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

The source pin and capture binary are distinct evidence. The source tag fixes
the reviewed contract surface; checked-in frame fixtures bind the binary
digest above. Replacing that binary requires fixture recapture. Every provider
argv clears `OMP_PROFILE` and `PI_PROFILE`, because either profile disables
`PI_CODING_AGENT_DIR` relocation.

| Contract point | omp component | Our consumer | Pin |
| --- | --- | --- | --- |
| CLI argv: `--mode json`, `--config`, `--model`, `--resume <full-id>`, `--approval-mode`, `--no-extensions`, `--no-title` | `packages/coding-agent/src/cli/args.ts`, `packages/coding-agent/src/cli/flag-tables.ts`, `packages/coding-agent/src/modes/print-mode.ts` | provider templates (both lanes) | template + upgrade review |
| Config semantics: precedence, `PI_CODING_AGENT_DIR` relocation, `modelRoles`/`advisor.*`/`memory.backend` fields | `packages/coding-agent/src/config/settings-schema.ts`, config resolution | conf presets, hermeticity (X4) | canary tests (F3) |
| stdout NDJSON events: session header, `message_update`/`message_end`, `turn_end`/`agent_end`, embedded `Usage`, `notice` | `packages/agent/src/types.ts`, `packages/coding-agent/src/session/agent-session-events.ts`, `packages/catalog/src/types.ts` | `OMP_JSON_STDOUT` codec, panes | checked-in frame fixtures |
| Session persistence: `SessionHeader.id`, append-only session JSONL, `__advisor.<slug>.jsonl`, resume | `packages/coding-agent/src/session/session-manager.ts`, `packages/coding-agent/src/session/session-entries.ts`, `packages/coding-agent/src/advisor/transcript-recorder.ts` | identity check, evidence, bridge (`omp --resume`, import) | F1 + fixtures |
| Advisor subsystem: headless `advisor.enabled` configuration, WATCHDOG discovery, emission guard, `syncBacklog` | `packages/coding-agent/src/advisor/` | `advised*` presets | preset pins + liveness fact |
| Subagent system: `agents/*.md` frontmatter, schema-validated yields, worktree isolation, per-agent metering, `hub` tool | `packages/coding-agent/src/task/`, `packages/coding-agent/src/discovery/helpers.ts`, `packages/coding-agent/src/registry/agent-registry.ts`, `packages/coding-agent/src/tools/hub/` | `fanout/`/`peer-team/` presets | F5 + preset pins |
| Version identity | `omp --version` | `provider_runtime_version` evidence | source tag + binary digest |

  Deliberately NOT consumed by `OMP-I1`: RPC/ACP modes and the `omp-rpc`
  client (separate gate), collab/relay (ops trial only), metaharness
  (post-ES spike), memory backends (banned), Agent Hub TUI/cross-step
  revival (banned beyond step scope), or non-empty skills/extensions/hooks/
  MCP capability sets. Declarative skills and exact extension bundles belong
  only to lower-priority `OMP-I2`; hooks, MCP, and implicit plugin-package
  capability closure remain unincorporated.

## Deferred Declarative OMP Capability Loading (`OMP-I2`)

Owner decision on 2026-08-14 approves this design for lower-priority roadmap
tracking, not implementation selection. `OMP-I2` cannot enter before
`OMP-I1` closes and a separate owner activation names a consumer. It has no
ordering effect on ES, E3, E-program closure, the P-series, or any earlier
selected or owner-prioritized OMP follow-on.

The authored boundary is an ordinary library value, not new Workflow Lisp
grammar and not new `provider-result` keywords:

```lisp
(record OmpCapabilitySet
  :skills (list "repo-navigation" "systematic-debugging")
  :extensions (list "safe-shell"))
```

`workflows/library/omp/` owns `OmpCapabilitySet` and passes it to
`omp-attempt`. Logical ids resolve only through a checked-in, source-owned,
content-addressed `omp-capabilities-lock.v1`. The certified
`stage-omp-conf` adapter validates kind, containment, exported-name
collisions, and digests; stages only the selected closure; and emits the
requested capability manifest plus its digest. No run may invoke `omp
plugin install`, use network package resolution, or consult ambient installed
plugin state.

Skills and extensions have separate admission rules. A skill is passive
prompt authority: its complete directory and exported name are pinned. An
extension is executable in-process code: it must be an exact reviewed,
self-contained entry bundle. A plugin package is only a distribution
container and is not directly selectable; any later bundle convenience must
expand in the lock to an enumerated skill/extension closure. Undeclared sibling
hooks, tools, rules, commands, agents, prompts, or MCP configuration are not
implicitly authorized.

OMP must load the selected closure exactly and fail before the first provider
request on a missing, mismatching, malformed, duplicate, or unloadable entry.
The requested manifest and observed loaded inventory are separate evidence;
the attempt proceeds only when they match and the observed ambient set is
empty. `omp` version, base-conf digest, and capability-manifest digest jointly
identify the harness treatment. Resume requires the same capability digest,
and OMP-owned advisors/subagents may inherit but never widen the set. The
bound-path provider bundle remains the only orc result channel.

Existing CLI/config controls are evidence candidates, not proof of this exact
closure: `PI_CODING_AGENT_DIR` and `--no-extensions` do not by themselves
disable every discovery subsystem. `OMP-I1` must still prove its empty
capability closure through F3; it does not wait for non-empty author selection.
`OMP-I2` requires either an OMP-owned fail-closed capability-manifest mode or
equivalent executable evidence without an orc-side shadow loader.

`OMP-I2` entry and exit require: closed `OMP-I1`; exact fail-closed OMP
capability-loading evidence; a named consumer and explicit owner activation;
a focused compile/lower/run fixture proving
`OmpCapabilitySet` through the certified adapter boundary; canaries across
user, ancestor, external-tool, installed-plugin, custom-tool, and MCP roots;
selected-skill and selected-extension positive cases; undeclared and
digest/load-failure negatives; same-manifest resume and changed-manifest
refusal; subagent non-widening; no package-state mutation or network install;
and digest-bound requested/loaded inventory evidence.

## Feasibility Prerequisites (exit criteria for the tranche's first run)

- **F1** [open]: session JSONL (incl. `__advisor.<slug>.jsonl` and subagent
  artifacts) lands under the relocated agent dir. [INFERENCE from
  `config-usage.md`; one run.]
- **F2** [open]: staged `advisor.enabled: true` configuration composes with
  `--mode json` (advisor events + drain under JSON print mode).
- **F3** [open]: an empty capability closure is proven with
  `OMP_PROFILE`/`PI_PROFILE` unset: canaries in user-global config, user and
  project/ancestor WATCHDOG files, ancestor external-tool config, skills,
  extensions, hooks, custom tools, installed plugins, and MCP are neither
  loaded/imported nor present in behavior or evidence. Non-empty declarative
  capability selection is `OMP-I2`, not an `OMP-I1` fallback.
- **F4** [open]: resume-boundary observability under
  `--mode json --resume` sufficient for `turn_boundary_resume`.
- **F5** [open]: task-subagent activity under `--mode json` is observable
  in evidence (per-agent metering, yields in the primary session, worktree
  cleanup on step end).
- **F6** [open]: bare-lane neutrality and headless completion — a fresh
  empty agent dir yields schema defaults with memory/advisor off; an
  ordinary bash+edit worker task completes under `--approval-mode write`
  (else the lane's pinned mode is adjusted); stdin input composes with
  `--mode json` for the unrestricted variant.
- **F7** [open]: literal and file prompt inputs pass through one exact,
  source-owned prompt materializer; flag ambiguity, invalid UTF-8, empty
  prompts, external-path retention, and silent overwrite fail closed.
  `--output` returns a schema-valid structural `OutputContractDraft` through
  the ordinary provider path; inferred, exact, default, and imported inputs
  normalize to one `ScaffoldOutputContract.v1`; the shared renderer emits
  compiling canonical type syntax and the compiler derives the same
  contract/guidance; model-authored prose cannot enter task guidance; invalid
  drafts fail before task invocation; matching pinned reruns perform no
  second synthesis call.

## Roadmap

- **Active-roadmap route:** `OMP-I1` is tracked from
  [`2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md).
  Owner selection of tranche 1 is recorded above; activation becomes eligible
  only after hand-back of the frozen ES apparatus.
  Its F1–F7 checks close only OMP-I1 and cannot gate ES, E3, E-program
  completion, or the P-series successor route.
- **Lower-priority route:** `OMP-I2` adds declarative, content-addressed
  skill and exact extension-bundle selection through the ordinary
  `OmpCapabilitySet` library boundary. It is pending and unselected, requires
  closed `OMP-I1`, exact fail-closed OMP loading evidence, a named consumer,
  and separate owner activation, and creates no gate or precedence over any
  selected spine or earlier OMP follow-on.

- **Tranche 1 (one reviewed change):** the omp template family (`omp`,
  `omp_unrestricted_workspace`, `omp_conf`) + codec +
  fixtures + `workflows/library/omp/` (`omp-attempt`, `stage-omp-conf`
  adapter, settlement contracts) + generic
  `workflows/library/scaffolding/infer-output-contract.orc` +
  structural `OutputContractDraft` + versioned `ScaffoldOutputContract`
  codec/checker/renderer + conf presets
  (`workflows/assets/omp_confs/`) + scaffolder (`run`/`import`,
  `--prompt`/`--prompt-file` → owned `prompt.md` + canonical prompt extern,
  `--output`/`--returns`, canonical contract artifact and import sidecar) +
  monitoring-doc note + the two-arm bare-vs-advised trial: one `run.orc` on
  `omp_conf`, arms differing only in the digest-pinned conf input (`neutral/`
  vs `advised/`), plus one `fanout/` preset smoke (F5) and one bare-lane `omp`
  smoke (F6). Exit: F1–F7 resolved;
  canary scenario passes; codec unit + fake-child tests green; one real
  orchestrator smoke; cost and wall-time (contract synthesis, advisor drain
  ≤10 min, `syncBacklog` stalls) measured and reported.
  This tranche proves an empty optional-capability closure under F3; it does
  not implement non-empty skill or extension selection.
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
- **Lower-priority follow-on (`OMP-I2`):** implement the deferred declarative
  capability contract only after its entry conditions above. It remains behind
  `OMP-I1` and does not displace RPC, metaharness, or supervision work if the
  owner selects those first.

## Invariants And Failure Modes

Proposal invariants 1–5 bind unchanged. Added: conf digest + harness
version are mandatory evidence for every omp step; advisor liveness
(non-empty advisor transcript, usage > 0) is recorded per attempt so a
silently dead advisor never silently narrows a treatment; hub/IRC state never
outlives its step; memory stays explicitly disabled; generated workflows are
ordinary workflows (no generated-only runtime path).

Prompt-input invariants: exactly one explicit literal/file mode; one
materializer; non-empty UTF-8 bytes preserved without model transformation;
one source-owned `prompt.md` bound through the existing `asset_file`
`PromptExtern`; no dependency on the ingestion file's original path.
Matching inputs regenerate identically, while edited `prompt.md` is authored
authority and cannot be silently overwritten. Import uses the same route.

Output-contract invariants: one versioned canonical IR feeds every mode; the
model emits structure, never source or prompt-visible guidance; only the
user-authored output intent becomes free-form task guidance; shared frontend
primitives remain the sole type/symbol/string syntax authority; ordinary
compilation and structural equality are required before task invocation; no
invalid contract widens to `String`. Matching generated source is
contract-regenerable; edited `.orc` and its compiled contract are execution
authority. Import restores a digest-bound contract or chooses an explicit
mode—it never parses transcript prose into a contract.

## Verification Strategy

Codec fixture tests (identity, terminal, resume boundary, usage, error
mapping, malformed input — negative tests fail closed); fake-child process
tests; output-contract tests covering valid synthesis, mutually exclusive
flags, exact-mode synthesis bypass, invalid/reserved/duplicate fields,
unsupported recursive types, and failure before task invocation; one
table-driven normalization suite proving inferred, exact, default, cached, and
imported inputs enter the same IR; canonical codec and semantic-digest tests
show provenance changes do not alter contract identity; frontend
type-expression, identifier, and string-atom round trips cover nested
collections, Unicode, quotes, newlines, and control-character rejection.

Prompt-materialization tests cover mutual exclusion and requiredness,
byte-identical literal/file outputs, strict UTF-8 and empty-input rejection,
the canonical `asset_file` manifest object, no model call, no silent overwrite,
and no generated reference to the ingestion path. A compile/run integration
check resolves `prompts.task`, removes or relocates the original
`--prompt-file`, and runs the generated workflow successfully; import enters
the same materializer. Existing final-composed-prompt audit evidence remains
the runtime observation surface.

Renderer checks compile `List[String]`, `Optional[T]`, and
`Map[String,T]` fixtures and structurally compare the compiler-derived return
type/guidance with the IR. Prompt-contribution provenance proves no
model-authored field prose reaches task guidance without asserting literal
prompt wording. Regeneration proves matching pinned contracts make no second
provider call; prompt/output-intent/source/contract/renderer mismatches refuse;
manual source edits make the sidecar stale. Self-containment proves scaffolder
run ≡ bare `orchestrator run` on generated `run.orc`.
Round-trip proves
`run` → digest-bound sidecar → `import` preserves semantic IR/source modulo
enumerated session provenance; arbitrary-session import follows the explicit
or default contract path. Library staging/evidence coverage, canary negatives,
one real smoke, behavioral assertions only, and `pytest --collect-only` on
new modules complete the tranche check.

## Declarative Acceptance Scenario

Clean checkout; canaries planted in `~/.omp/agent/` and an ancestor
`.claude/`; run `orchestrator prompt run --prompt "Implement the requested
repository change and run its required checks." --conf
workflows/assets/omp_confs/advised/ --provider omp_conf --output "A concise
summary, whether all checks passed, and unresolved problems"`. Expected:
`prompt.md` contains the exact literal bytes and `prompts.json` binds
`prompts.task` through canonical `asset_file`; no task-prompt transformation
call or external source path exists. One typed contract-synthesis provider
returns ordered names/types only; canonical `output-contract.json` separates
semantic contract from provider/model/session/usage provenance and
generated-source identity; generated `.orc` uses canonical bracketed
collection types, contains only the verbatim user output intent as result
guidance, and compiles to a structurally equal contract before the task
starts. The task completes with a schema-valid bundle. Evidence contains the
digest-bound canonical contract reference, task session JSONL, non-empty
advisor transcript, conf digest, `omp --version`, tokens/cost; the printed
`tmux attach` target shows live assistant text; `omp --resume` reopens the
task session; `prompt import` reproduces the same owned prompt artifact and
contract/source without deriving a contract from transcript prose.

Forbidden: path-vs-text auto-detection; model rewriting of the task prompt;
retaining the ingestion path instead of owning `prompt.md`; model-authored
source or result guidance; a parallel type/identifier/string grammar in the
CLI; task invocation after prompt/draft/render/compile/equality failure;
synthesis on a matching pinned-contract rerun; silent overwrite of edited
prompt or source artifacts; canary influence; result reads from stdout; any
execution difference between generated source and a bare `orchestrator run`.

## Stop / Revise Criteria

F3 leak with no hermetic fix → revise isolation before adoption. F2 failure
blocks advisor presets; F4 failure blocks the session bridge; F5 failure
blocks fanout/peer presets. None falls back to RPC: the affected tranche scope
must be owner-revised before close. F7 prompt materialization, contract
synthesis, or self-containment failure; model rewriting of task prompts;
model-written source or prompt-visible field prose; a second CLI
type/symbol/string grammar; or task invocation after prompt normalization,
contract normalization, rendering, compilation, or structural equality
failure → tranche does not close. Exact `--returns` alone is not an acceptable
substitute for the approved human-facing output-contract path. Trial shows no
advised-arm signal at material cost → conf pattern stays available, guidance
does not become a default. Upstream `--mode json`/session-layout change under
the pin → wire-contract break: re-record fixtures, re-review.

## Documentation Impact

On landing: `specs/providers.md` (mode, template); `specs/cli.md`
(`prompt run|import`, literal/file prompt materialization and overwrite
authority, exact canonical-root schema, contract sidecar and edit authority);
one public `ScaffoldOutputContract.v1` schema/codec; capability-matrix rows
(omp provider, codec, scaffolder; 2.16/2.17 annotation);
`docs/workflow_monitoring.md` (attach runbook); index entry. Drafting-guide
text waits for DP-A.

## Owner Decisions

1. Resolved 2026-08-21: tranche 1 is selected as scoped, including its trial;
   frozen-ES hand-back remains the only activation blocker.
2. Use `orchestrator prompt run|import`; do not add a parallel flag mode to
   `orchestrator run`.
3. DP-A timing remains at tranche close; relay policy remains an independent
   follow-on decision.
