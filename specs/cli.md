# CLI Contract (Normative)

## Workspace execution ownership

Only one run may execute in a workspace at a time. `run` and `resume`
(including `--force-restart`) acquire a workspace lock before compilation or
execution-state mutation. A competing invocation is refused with
`workspace_run_already_active`, naming the active run, and `run`, `resume` and
`trial` exit 2. Exit 2 means the request was refused before execution; exit 1
stays the status of a workflow that ran and failed. Exit 2 is also the status
of a compile or validation error, so a caller that must tell those apart reads
the code. Changing `--state-dir` does not bypass this rule. The trial SDK/CLI
uses the same workspace lock; nested workflow calls belong to their root run
and do not acquire it again.
Run-ref children own their separate clone workspace. `prompt run` can prepare
or reserve its scaffold before entering the ordinary `run` owner, but cannot
execute a provider while another run owns the workspace. The lock is not a
transaction over scaffold authoring or reservation. Commands that are not
runs take no workspace lock: `prompt resume` (with `--in-place` it runs a
provider in the workspace), `input answer|cancel`, `report` and `dashboard`.

The workspace is the physical current directory: a path that reaches it through
a symbolic link names the same workspace. The lock is an exclusive `flock` on
`.orchestrate/workspace.lock`, which records the owner's run ID as metadata. A
starter holds `.orchestrate/workspace.guard` while it takes the lock and
records its ID, so a refusal names the current owner. A starter waits at most
5 seconds for the guard; if another starter still holds it, the request is
refused with `workspace_run_already_active` and a message that the guard is
held. Exclusion assumes a local filesystem. On NFS, `flock` is emulated with
byte-range locks on the server, and with `local_lock=flock` or
`local_lock=all` it excludes only processes on one host.

The operating system releases ownership when execution returns (including
failure or suspension) or the process dies. Retained lock metadata is not
authority: a dead process's lock file does not prevent a later run. Lock files
are not removed on release. `--dry-run` neither acquires nor requires this
lock. Existing per-run writer locks still coordinate mutation of a run;
read-only reporting remains available. When another process holds a run's
writer lock, `run` and `resume` refuse with `run_already_active` and exit 2, as
for `workspace_run_already_active`. Concurrent execution requires separate
workspaces. Result bundle paths and persisted result identities are unchanged.

A `run`, `resume`, or `trial` started from inside an active run (by one of its
command steps or providers) in that run's workspace is a competing invocation
and is refused the same way; only nested workflow calls belong to the root run.
A run that supervises another run therefore uses its own workspace: it reads
the other run's workspace by path and starts `resume` or `run` for it with that
workspace as the working directory.

## Workflow Lisp REPL

The shared session supports typed evaluated targets 2.35/2.36 and
[native target 3.0](versioning.md#native-target-30). The
[REPL design](../docs/design/workflow_lisp_repl.md) owns capture and expression
semantics.

```text
orchestrator repl [WORKFLOW] [--entry-workflow NAME] [--source-root DIR ...]
  [--provider-externs-file JSON] [--prompt-externs-file JSON]
  [--imported-workflow-bundles-file JSON] [--command-boundaries-file JSON]
  [--run-id RUN_ID] [--state-dir DIR]
:load PATH [the same frontend flags]
:run [--input NAME=VALUE ...] [--input-file JSON] [--state-dir DIR] [--run-ref-root DIR]
:attach RUN_ID
:bindings
:result
:where [NAME]
:browse
:info NAME
:source NAME
:type EXPR
:help
:quit
```

The frontend flags have the same meanings as `compile` and `run`. Startup
loads `WORKFLOW` before attaching `--run-id`. For typed modules, `:load`
publishes the ordinary closed-program build bundle; native loading retains ordinary compiler context
without publishing extra files. Failed compilation reports ordinary rendered
diagnostics and retains the previous module. `:run` requires a loaded module,
uses public run option/input parsing and `run_workflow`, and forwards the
session state directory unless the command overrides it. It attaches the
returned run root after public execution releases its writer locks. This
explicit command has ordinary run effects, lock ownership and evidence writes.

For typed 2.35/2.36, `:attach` resolves `RUN_ID` under `.orchestrate/runs`,
or the session's `--state-dir`, and reads checked `run.json`, `closed_program.json` and one
`memo.jsonl` prefix through `WorkspaceFiles`. It uses stored bound inputs and
ordinary memo reduction, replay commit checks and completed-terminal validation.
It takes no writer lock, launches no effects and neither repairs/appends the
memo nor publishes a derived view. `state.json` is not authority. Attachment
captures a prefix, not a live subscription to a running writer.

A loaded module's program digest must match the run. A mismatch reports
`resume_program_changed` and clears attachment. Without a loaded module,
attachment rebuilds the durable `resume_request` in memory using the ordinary
resume build request and `prepare_closed_program_bundle`; no build artifact
or cache is published. Missing recipe reports `resume_request_missing`, and
changed fresh program reports `resume_program_changed`. Fresh input files are
not rebound for inspection. A matching explicitly loaded module allows reading
a historical run without a recipe. Ordinary checked-authority, memo and compile
errors retain their codes.

### Module and result inspection

`:browse`, `:info NAME`, `:source NAME` and `:type EXPR` require a loaded
module, not attachment. `:browse` takes no arguments; `:info`/`:source` require
exactly one symbol and follow actual import aliases, qualified names and
namespace visibility. They project real declaration metadata, not rendered
output or inaccessible declarations elsewhere in the source graph. Unknown
module declarations report `repl_name_unknown`; ordinary resolver ambiguity
diagnostics retain their codes. Extern display exposes kind/contracts only,
without manifest secrets, prompt contents or command argv.

`:source` returns the checked authored form from the immutable successful-load
snapshot. It verifies retained bytes/hash/span/name, including normalized line
endings. Disk mutation/deletion never causes a filesystem fallback. Missing,
expanded or unavailable authored forms report `repl_source_unavailable`.

Typed `:type` uses ordinary static type/effect analysis and prints `type:` and
`effects:`. It accepts effectful expressions for analysis without evaluating
expressions or operands. Attached lexical names shadow module declarations.
This is distinct from entering a pure expression, which still refuses effects.

`:where [NAME]` requires attachment. At typed targets, it locates a performed
value's retained checked `committed_result_path` beneath the attached authority
root. Omit NAME to inspect the completed entry result. Computed values and
missing/invalid locators report `repl_no_result_file`; unknown captured names
report `name_unknown`; an absent completed entry reports `repl_no_result`.
It locates result files, not source declaration locations. See the
[introspection design](../docs/design/workflow_lisp_repl_introspection.md)
for provenance and per-profile projection boundaries. These commands dispatch
no effects and leave run authority, memo, views and attempt evidence unchanged.

Typed expressions are one datum per input line and require attachment. Lexical
shadowing chooses the innermost binding; compiler names beginning with `%`
are hidden. Ordinary field/list operations and pure module `defun`/`defproc`
calls are admitted. Equality `=` / `!=` retains the
[ordinary frontend §10.2](../docs/design/workflow_lisp_frontend_specification.md#102-closed-pure-expression-surface)
contract for supported scalars and same-type enums; lists do not gain deep
equality semantics. Use the ordinary `list/empty?` operator to test list
emptiness. The frontend rejects transitive effects; a recursive
lowered-body guard and the evaluator with no effect callback also refuse
`perform`. Synthesized runtime variant-case bindings may be displayed but do
not supply frontend proof for expression evaluation. The session accepts no
multiline expressions, definitions, interactive effects, resume command,
module editing, completion/history or flat-profile attachment through 2.34.

`:bindings` shows visible names/types in outer-frame order, capture position
and run identity. `:result` prints the completed entry result with the entry's
return type, including completion through a loop's `done`, or `repl_no_result`
when stopped or failed. Its value is the ordinary evaluator's final return,
not an incidental operand or loop-seed completion. Expression and result
values use two stdout lines: canonical UTF-8 compact sorted-key JSON, then
exactly `: <rendered type>`. REPL and runtime errors print `[code] detail`
on stderr. Frontend errors retain ordinary localized `render_diagnostic`
output, including diagnostic code and `kind`/`form` context. A prompt and
readline are enabled only for a TTY; piped input receives no prompt.

EOF and `:quit` exit `0`. A startup load/attach refusal exits `2`; an unexpected
failure exits `1`. Expected command/expression errors keep the session usable
and eventual normal EOF/quit still exits `0`. Failed ordinary commands retain
compatible session state; digest mismatch leaves it detached. Read-only startup,
attachment, bindings, result and pure/refused expressions leave run authority,
memo, views and attempt evidence byte-identical; `:load` can publish only build
artifacts. `:run` remains the explicit exception using public execution.

| Diagnostic | Condition | Session/startup behavior | Run evidence |
| --- | --- | --- | --- |
| `repl_effect_refused` | Entered expression or called procedure has effects, or a lowered/evaluated `perform` is reached | Session continues | None |
| `repl_run_not_found` | Requested run root does not exist | Session continues; startup exits 2 | None |
| `repl_profile_unsupported` | Requested run uses the flat profile | Session continues; startup exits 2 | None |
| `repl_not_attached` | Expression, `:bindings`, `:result` or `:where` without an attached run | Session continues | None |
| `repl_module_required` | `:run` or module inspection without a loaded module | Session continues | None |
| `repl_expression_arity` | Expression line does not contain exactly one datum | Session continues | None |
| `repl_no_result` | Attached replay has no halted entry result | Session continues | None |
| `repl_name_unknown` | Unknown visible module declaration for `:info`/`:source` | Session continues | None |
| `repl_source_unavailable` | No checked retained authored source for the declaration | Session continues | None |
| `repl_type_unavailable` | Native `:type` receives a compound expression | Session continues | None |
| `repl_no_result_file` | Captured value has no valid retained result-file provenance | Session continues | None |
| `repl_module_context_missing` | Module call needs unavailable transient compiler context | Session continues | None |

Reused `name_unknown`, `resume_program_changed`, `resume_request_missing`,
`memo_inconsistent` and ordinary frontend/value diagnostics retain their
codes and the appropriate rendering above; session errors continue, startup
errors exit `2`, with no inspection evidence writes. A public `:run` failure retains ordinary run
behavior and any evidence that public execution legitimately wrote.

### Native target 3.0 inspection

Native attachment requires a loaded native module and the exact routing pair
`3.1` / `dynamic_execution.v1`. No loaded context reports
`repl_module_required`; there is no durable native rebuild recipe or recoverable
source text in state. Require the loaded semantic program digest to equal the
saved digest; a mismatch reports `resume_program_changed` and detaches.
Unknown/mixed profiles refuse without typed fallback. `:run` still uses the
public run parser/service, including native option restrictions. Each native
`:run` creates a fresh root and may repeat all prior external calls/writes;
there is no effect-result reuse or session resume.

Attachment validates the pinned program/header and one atomic state snapshot,
then reconstructs lexical scope with the ordinary native evaluator. Reached
completed effects consume their prescribed physical, boundary-validated
`result.json` in saved order; no performer is installed. Running/failed/missing
effect rows stop at the actual caller scope. Pure failures, effect-boundary
counts, row reachability and completed terminal values/step counts must agree
with the saved state, or attachment refuses `dynamic_state_invalid`.
A running snapshot may reconstruct an unpublished pure halt, exposed as
`halt-unpublished`; `:result` still reports `repl_no_result`. This explicit REPL
consumer does not alter ordinary source-independent, nonreplaying dynamic
report/status readers. See [state reconstruction](state.md#repl-read-only-reconstruction).

Native loaded-only `:browse`/`:info`/`:source` use real retained lowerer
metadata and the same immutable source checks. `define` exposes parameter
names with unavailable parameter/return/effect inference; workflow, prompt and
type declarations expose their explicit schemas. Native `:type` never evaluates:
literals show literal kinds, visible function names show `Function` with
unavailable return/effect inference, and captured bindings show **observed
runtime kind**, including `Function` for closures. These kinds are distinct
from declared boundary schemas. Compound expressions refuse
`repl_type_unavailable` before evaluating any operand. Unknown value/function
names report `name_unknown`.

Native captured plain values retain no result-file provenance. Native
`:where [NAME]` therefore reports `repl_no_result_file`, even when a value equals
a performed result. Unknown captured names still report `name_unknown`, and
`:where` without a completed entry result reports `repl_no_result`. No lookup
adds lineage wrappers, native recovery or equality-based provenance.

Native expressions use the ordinary reader/lowerer and evaluator with one
finite budget afresh per expression. Direct effects in entered expressions or
new inline functions refuse `repl_effect_refused`. Reaching an effect through
an existing helper/closure refuses before its operands or dispatch, with no
effect callback. An untaken branch may mention an existing effectful function;
this is an execution guard, not global static effect inference. Imported/local
functions, captured closures and ordinary field/list operations retain native
semantics. Evaluation leaves the captured environment unchanged.

`:bindings` shows runtime kinds, including `Function`, rather than inferred
typed signatures. Native data prints canonical JSON then `: <runtime kind>`.
A bare closure prints `<function>` then `: Function`; containers containing
closures refuse `repl_value_not_printable` when printed, but remain usable
internally for selection and calls. Native `:result` requires saved completion
and matching reconstruction, and prints the declared result schema and entry
value, including null. The schema prints its declared name when present;
otherwise it prints the canonical structural JSON descriptor, without source
provenance. Stopped, failed and unpublished halts have no result.
Inspection never changes state, run/program/source files, manifests, views or
attempt evidence; it acquires no writer lock and performs no repair or resume.
Required path assets must still exist. Native state has no historical result
digests/operand fingerprints, so schema-valid historical tampering is not
universally detectable; typed memo integrity guarantees do not transfer.

## Dynamic execution

An explicit `(:target-dsl "3.0")` selects the
[native dynamic profile](versioning.md#native-target-30) through the existing
compile/run entry points and source/entry/binding flags; there is no profile
flag or separate dynamic launcher.

Compile admits the complete source/import graph and every body, writes an
independently checked dynamic program/source map, and validates read-back.
Diagnostics JSON and source-map exports are available; flat Core/executable IR,
runtime-plan, semantic-IR and debug-YAML exports refuse for this representation.
Dry-run prepares source, bindings, permissions, public inputs/defaults and
initial path refinements without evaluating a body, dispatching or allocating
run/effect attempts. A real run allocates a fresh root after preparation.

Run accepts source-root/entry, provider/prompt/command configuration,
`--input`/`--input-file`, `--state-dir`, dry-run and logging/streaming options.
Text `--input` parsing is schema-directed, followed by strict validation; JSON
strings do not coerce to Bool. Missing/extra/invalid inputs and defaults refuse
before root creation. Compiled import bundles remain unsupported even though
the shared parser exposes that option. Retries are fixed at zero, including
when the legacy default would be nonzero; only `--on-error stop` is admitted.
Explicit legacy context, run-ref roots, clean/archive, backup, summary/agent-note
and retry-delay options refuse before run creation with
`dynamic_option_unsupported`.

Report/dashboard and operational readers select the exact persisted profile,
validate immutable pins and authoritative state, and expose native terminal
values plus `resumable: false`. They do not reconstruct missing state, execute,
repair or write. A running record without its writer is interrupted;
watchdogs stop/escalate rather than automatically restarting it. Resume refuses
with `dynamic_resume_unsupported` and invalidation with
`dynamic_invalidation_unsupported`, before source compilation, writes or
performer dispatch. A fresh run can repeat earlier calls, budget and external
writes; it does not adopt orphan outputs. Typed and legacy recovery contracts
below remain scoped to their retained profiles. See
[State](state.md#dynamic-fresh-run-authority).

## Command reference

- Commands
  - `orchestrate run <workflow.orc> [--context k=v ...] [--context-file path] [--input name=value ...] [--input-file path] [--clean-processed] [--archive-processed <dst>]`
    - `--dry-run` validates the workflow and may emit advisory warnings that do not change the exit code. A pure-result replay-index failure is an error only when the compiled structure guarantees that the call is reached; failures along a path under a branch, match arm, or loop body are warnings. Conditions are not evaluated, and a real run is refused if it reaches the call.
  - `orchestrate resume <run_id>`
    - Dynamic schema-3.1 runs refuse with `dynamic_resume_unsupported`; see [dynamic execution](#dynamic-execution).
    - Target-2.35/2.36 evaluated runs select their persisted authority profile before
      legacy state loading. Resume rebuilds the saved request in memory, compares
      the semantic program then bound inputs, and checks the active committed
      prefix before mutable continuation. Committed results are reused without
      redispatch; pending retries follow command closure/provider captured-input
      checks. Missing historical rebuild recipes refuse with
      `resume_request_missing`; malformed present recipes are `memo_inconsistent`.
      `--force-restart` remains unavailable for this profile. See
      [evaluated execution §8.4](../docs/design/workflow_lisp_evaluated_execution.md#84-the-run-header-and-the-representation).
      New evaluated headers persist the resolved canonical `run_ref_root` outside
      recipe/input/program digests without creating it. Explicit mismatching
      resume selection refuses read-only with `resume_run_ref_root_changed`,
      malformed present roots are `memo_inconsistent`, and historical absent
      fields are not backfilled. Path children dispatch through the evaluated
      coordinator; its root and historical-header rules are owned by
      [evaluated execution §8.4](../docs/design/workflow_lisp_evaluated_execution.md#84-the-run-header-and-the-representation).
      The following provider/host-request policies describe the legacy profile.
    - If persisted authoritative state proves an exact interrupted in-flight
      ordinary, session, supervision, peer-group, phased, or adjudicated
      provider visit, resume preserves completed-boundary reuse, discards only
      the partial visit authority, emits
      `provider_attempt_interrupted_rerun` (or the adjudication-specific
      `adjudication_state_mismatch_rerun`), and re-enters normal execution with
      fresh identities. Force restart is not required.
    - Missing, malformed, ambiguous, checksum-incompatible, or otherwise
      unprovable recovery state still fails before provider launch.
    - A durable host request that is `pending` keeps the run suspended without
      entering the execution prologue. An `answered` request is consumed only
      after ordinary source, scope, node, visit, and reply validation; a
      consumed reply uses the existing completed-effect recovery policy or
      fails closed. Resume never creates a replacement question automatically.
  - `orchestrate invalidate <run_id> <identity> [--state-dir <runs-root>]`
    - Dynamic schema-3.1 runs refuse with `dynamic_invalidation_unsupported` without mutation; see [dynamic execution](#dynamic-execution).
    - Target-2.35/2.36 evaluated authority supports one append-only invalidation range
      from the full active committed identity through the active suffix. It uses
      checked stored authority and the run writer lock, without reading current
      sources, rebuilding or dispatching. The next ordinary resume reruns that
      suffix; future retry commits remain active. An inactive identity, historical
      profile, or coordinator anywhere in the suffix refuses with exit 2. No
      per-effect replacement journal or automatic file-dependency selection is
      implied. See [evaluated execution §8.5](../docs/design/workflow_lisp_evaluated_execution.md#85-explicit-continuation-after-a-divergence)
      and `tests/test_workflow_evaluated_invalidate_smoke.py`.
  - `orchestrate input get <run_id> [--state-dir <runs-root>]`
    - Prints the current root host-request record. It does not resume or
      mutate execution.
  - `orchestrate input answer <run_id> <request_id> --text <text> [--state-dir <runs-root>]`
    - Validates and records one `ANSWERED` reply under the existing root writer
      lock. Empty text is valid. It does not execute or resume the workflow.
  - `orchestrate input cancel <run_id> <request_id> [--state-dir <runs-root>]`
    - Validates and records the `CANCELLED` reply under the same lock. It does
      not execute or resume the workflow.
    - Answer/cancel are idempotent only for an identical reply to the latest
      request; conflicting, stale, or overlapping submissions fail without
      replacing persisted data. They preserve the original bound inputs and
      recorded launch arguments.
    - These are thin clients of the durable host-input API. They apply only to
      a target-2.32 run carrying a request record; they do not parse state,
      acquire an alternate lock, or resume execution themselves.
    - Each successful input command prints the complete current request record
      as JSON and exits 0. Missing/invalid requests or submission conflicts
      exit 2; they never launch a provider.
  - `orchestrate report [--run-id <id>] [--runs-root <dir>] [--format md|json] [--output <path>]`
    - Report output may include advisory lint warnings (`lint.warnings[]` in JSON or an appendix in Markdown); warnings remain informational only.
    - Report output may include active runtime fields derived from executor sessions, including `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, and `run.excluded_suspended_ms`. These fields exclude suspended gaps between executor processes and are informational only.
    - Report output may surface provider-session metadata paths and bounded
      interrupted-rerun diagnostic context; partial provider evidence remains
      non-authoritative.
  - `orchestrate prompt run (--prompt TEXT | --prompt-file PATH) --provider (omp|omp_no_tools|omp_conf|omp_unrestricted_workspace) [--conf PATH] [--model MODEL] [--returns JSON | --output TEXT]`
    - Generation requires exactly one prompt source and one public provider.
      `--conf` is required only for `omp_conf`. `--returns` supplies the exact
      semantic contract; `--output` is mutually exclusive and performs one
      internal `omp_conf_inference` call, so ambient providers reject it.
    - The command captures all source inputs before inference or destination
      creation, publishes or reuses one content-addressed target-2.27 scaffold,
      executes its ordinary compiled `run.orc`, and prints one success summary
      naming the run and generated scaffold. Existing mismatched occupants,
      source drift, and malformed or semantically invalid inferred contracts
      fail without replacement.
  - `orchestrate prompt run --scaffold PATH`
    - Rerun accepts only a fully verified scaffold root and is mutually
      exclusive with every generation flag. It executes a run-owned private
      snapshot; mutable generated files are never the execution authority.
  - `orchestrate prompt resume ID [--in-place]`
    - This foreground command requires fd 0, 1, and 2 to be TTYs before lock
      acquisition or child launch. The default is one full-id fork into a new
      session; `--in-place` resumes the linked primary session. It accepts only
      one exact linked primary OMP journal, holds one per-session lock through
      preflight, child, validation, and one no-replace continuation append, and
      exits 0 on success, 1 on any failed post-start outcome, and 2 on
      grammar errors. The continuation record retains the observed child exit
      code; every post-start outcome publishes exactly one closed record.
  - `orchestrate prompt import ID --provider NAME [--conf PATH] [--model MODEL] [--returns JSON | --output TEXT] [--reuse-run-contract]`
    - Import resolves one exact linked active primary journal, verifies the
      full continuation chain and source scaffold/run evidence, extracts only
      authored user-message content, and then uses the ordinary prompt
      generation path. Without `--reuse-run-contract`, the caller supplies the
      new provider/contract flags. With it, provider, model, semantic contract,
      conf, and composed prompt bytes come only from the fully verified source
      scaffold; incompatible flags reject.
  - `orchestrate provider-isolation-environment-manifest --root <absolute-source> --provider-prefix <absolute-prefix> --output <absolute-manifest>`
    - Prospectively validates and canonicalizes one provider rootfs, including
      the runtime-reserved launch shim row, without mutating the source or
      creating a runtime snapshot.
    - Prints the canonical `sha256:<hex>` environment digest and atomically
      publishes the canonical manifest as a new single-link `0600` file.
    - The output parent must already be a real controller-owned, xattr-free
      `0700` directory reached through a trusted ancestor chain. The output
      must not exist, alias the source, overlap the source authority in either
      containment direction, or reuse the basename of any scanned source
      entry.
    - This controller-only authoring command proves the fixed packaged
      shim/interpreter bootstrap closure. It does not launch a provider and
      does not by itself make provider-phase isolation available.
  - `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]`
    - Serves a local, read-only dashboard for explicit workspace roots.
    - The dashboard scans `<workspace>/.orchestrate/runs/*/state.json` at request time and keys runs by `(resolved workspace root, run directory name)`.
    - The default bind host is `127.0.0.1`; binding to another host is an explicit operator choice.
    - Routes include `/runs`, `/runs/<workspace_id>/<run_dir>`, `/runs/<workspace_id>/<run_dir>/summaries`, `/runs/<workspace_id>/<run_dir>/summaries/live.json`, step detail, state preview, and route-scoped workspace/run file previews.
    - Dashboard routes must not execute `resume`, `report`, tmux, provider CLIs, shell commands, or child processes. Copyable commands are rendered as inert text only.
  - `orchestrator monitor --config <path> [--once] [--dry-run] [--dry-run-mark-sent] [--ledger <path>]`
    - Monitors explicit workspace roots from the config file and sends email notifications for completed, failed, crashed, or stalled workflow runs.
    - `--once` performs one scan and exits; without it, the monitor polls until interrupted.
    - `--dry-run` renders notifications without SMTP delivery and does not mark them sent by default.
    - `--dry-run-mark-sent` may be used only with `--dry-run`; it updates the ledger after rendering so duplicate suppression can be rehearsed.
    - `--ledger` overrides the default notification ledger path.
    - Exit code `0` means the scan completed and eligible notifications were handled; `1` means config, scan, or delivery failed; `130` means polling was interrupted.
  - Optional/post-MVP: `orchestrate run-step <step_name> --workflow <workflow.orc>`, `orchestrate watch <workflow.orc>`

- Debugging and recovery flags
  - `--debug`, `--stream-output`, `--progress` (post-MVP), `--trace` (post-MVP), `--dry-run`
  - Runtime observability: `--step-summaries`, `--summary-mode async|sync`, `--summary-provider <name>`, `--summary-timeout-sec <n>`, `--summary-max-input-chars <n>`, `--summary-profile basic|phase-performance`, `--live-agent-notes`, `--live-agent-note-provider <name>`, `--live-agent-note-interval-sec <n>`, `--live-agent-note-timeout-sec <n>`, `--live-agent-note-max-tail-chars <n>`
    - `--summary-profile phase-performance` enables advisory provider-step and phase-boundary summaries with performance judgments. It implies step summaries if `--step-summaries` was not otherwise provided.
    - `--live-agent-notes` enables advisory live notes from bounded tmux pane tails, using `claude_haiku_summary` by default. Provider-session transport may be used as a fallback when tmux pane capture is unavailable. It implies step summaries if `--step-summaries` was not otherwise provided.
  - `--force-restart`, `--repair`, `--backup-state`, `--state-dir <path>`
  - Error handling: `--on-error stop|continue|interactive` (interactive optional/post-MVP)
  - Retries: `--max-retries <n>`, `--retry-delay <ms>`

- Output control
  - `--quiet`, `--verbose`, `--json` (optional/post-MVP), `--log-level debug|info|warn|error`

- Planned environment defaults (not implemented)
  - `ORCHESTRATE_DEBUG=1`, `ORCHESTRATE_STATE_DIR=/tmp/runs`, `ORCHESTRATE_LOG_LEVEL=debug`, `ORCHESTRATE_KEEP_RUNS=30`
  - These reserved names currently have no CLI effect. Use `run --debug`,
    `run --log-level`, and `run`/`resume --state-dir` for supported controls.
    Automatic retention is not implemented; its deletion and precedence
    contract must be specified before `ORCHESTRATE_KEEP_RUNS` is activated.

- Safety
  - `--clean-processed` only operates on the configured `processed_dir` when it resolves within WORKSPACE.
  - `--archive-processed` destination must not be inside the configured `processed_dir`. Default output is `RUN_ROOT/processed.zip`.

## Commands and Examples

```bash
# Run a Workflow Lisp workflow from the beginning
orchestrate run workflows/examples/cycle_guard_demo.orc \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --input terminal_status=READY \
  --input guard_cycles=0

# Resume failed/interrupted run
orchestrate resume <run_id>

# Render status report for latest run
orchestrate report --format md

# Serve local dashboard for one or more explicit workspaces
orchestrate dashboard --workspace "$(pwd)" --host 127.0.0.1 --port 8765

# Monitor configured workspaces once without sending email
orchestrator monitor --config ~/.config/orchestrator/monitor.json --once --dry-run

# Validate the same Workflow Lisp source without executing
orchestrate run workflows/examples/cycle_guard_demo.orc \
  --entry-workflow cycle-guard-demo \
  --source-root workflows/examples \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/cycle_guard_demo.commands.json \
  --input terminal_status=READY \
  --input guard_cycles=0 \
  --dry-run

# Execute single step (optional/post-MVP)
orchestrate run-step <step_name> --workflow workflows/examples/cycle_guard_demo.orc

# Watch for changes and re-run (optional/post-MVP)
orchestrate watch workflows/examples/cycle_guard_demo.orc
```

### Workflow Lisp trials (target 2.25)

```text
orchestrate trial WORKFLOW --entry-workflow NAME
  [--input NAME=VALUE ...] [--input-file JSON]
  [--source-root DIR ...]
  [--provider-externs-file JSON] [--prompt-externs-file JSON]
  [--imported-workflow-bundles-file JSON] [--command-boundaries-file JSON]
  [--state-dir DIR] [--run-ref-root DIR]
```

The public command compiles the selected entry with the ordinary full compiler
and runs it with the ordinary executor. The entry must target DSL `2.25` and
its terminal public result must be the exact compiler-owned trial result.
Inputs bind through `--input` (repeatable) or `--input-file`; provide source
roots and extern manifests required by that workflow. Raw executable configs,
non-trial terminal results, other targets, and privileged bypasses are refused.

The command prints one closed `workflow_trial_run_result.v1` JSON record. It
contains the run ID and terminal status; completed results also contain the
verdict digest and path, while failed results contain a bounded failure
diagnostic. Exit `0` means completed, `1` means the trial ran and failed, and
`2` means validation or admission refused before execution. As elsewhere, exit
`2` alone does not distinguish compile errors from other refusals; read the
diagnostic code.

`--run-ref-root` sets the canonical absolute child-workspace root. When
omitted, it defaults to `~/.local/state/orchestrator/run-ref`. An explicit
value must already be canonical and absolute, and resume must use the root
bound to the persisted run. Trial has no dry-run mode.

### Extended CLI Options

```bash
# Debug and observability
--debug                 # Enable debug logging
--stream-output         # Stream provider stdout/stderr live without full debug side effects
--progress              # Show real-time progress (post-MVP)
--trace                 # Include trace IDs in logs (post-MVP)
--dry-run               # Validate without execution
--step-summaries
--summary-mode async|sync
--summary-provider <name>
--summary-timeout-sec <n>        # Default: 300
--summary-max-input-chars <n>
--summary-profile basic|phase-performance

# State management
--force-restart         # Ignore existing state
--repair                # Attempt state recovery
--backup-state          # Backup state before each step
--state-dir <path>      # Override default .orchestrate/runs

# Workflow signatures (v2.1+)
--input name=value      # Bind one workflow input
--input-file <path>     # Bind workflow inputs from one JSON object file

# Error handling
--on-error stop|continue|interactive
--max-retries <n>
--retry-delay <ms>

# Output control
--quiet
--verbose
--json                  # Optional/post-MVP
--log-level debug|info|warn|error
```

### Planned Environment Defaults

The following legacy proposal is not implemented. Setting these variables
does not change run location, logging, or retention. Use the supported flags
listed above; these names do not imply an automatic cleanup policy.

```bash
ORCHESTRATE_DEBUG=1
ORCHESTRATE_STATE_DIR=/tmp/runs
ORCHESTRATE_LOG_LEVEL=debug
ORCHESTRATE_KEEP_RUNS=30
```

Cross-platform note: Examples use POSIX shell utilities (`bash`, `find`, `mv`, `test`). On Windows, use WSL or adapt to PowerShell equivalents.
