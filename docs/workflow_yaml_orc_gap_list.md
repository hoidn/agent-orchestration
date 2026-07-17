# YAML-to-Workflow-Lisp Gap List

Status: Stage 6 Task 1 gate contract

This audit closes the language-gap list for exactly the two YAML workflows that
must receive dedicated `.orc` ports and the one protected holdout in the
content-addressed YAML-retirement handoff. It does not inventory the deletion or
Design Delta archive queues, and it does not authorize a workflow edit, port,
promotion, or deletion.

The machine authority for queue membership is
`docs/plans/2026-07-13-procedure-first-reuse-inventory.json`. The behavioral
inputs are the three YAML files named below, the current Workflow Lisp
capability contracts, and Task 15 of
`docs/plans/2026-07-05-post-foundation-target-completion-plan.md`.

## Approach and cost

Map each observed YAML mechanic to an existing typed `.orc` route first. Keep a
named fail-closed gate where current `.orc` cannot yet express or prove the same
public or operational contract. Delete YAML-only indirection when the typed
port has a direct value carrier. This makes a quick static-provider port harder:
both ports must preserve or explicitly waive provider-call policy and prompt
input semantics before parity can pass.

The four classifications are closed:

- `implemented`: the current checkout has a design, compiler/runtime route, and
  focused test authority. The later port must still prove family parity.
- `blocking_gate`: the port may not claim parity until the named gate closes.
- `owner_waiver`: the owner has explicitly accepted a named contract delta.
- `drop`: the mechanic is YAML-only indirection and must not be copied into the
  port.

No owner waiver is recorded by this audit.

## Queue reconciliation

| Queue ID | Disposition | YAML path | Decision gate |
|---|---|---|---|
| `port_verified_iteration` | `port` | `workflows/examples/verified_iteration_drain.yaml` | Apply the implemented generic provider-policy/profile capabilities; close `prompt-dependency-parity` and `verified-iteration-artifact-lineage`; then execute the Stage 6 per-family promotion gate. |
| `port_generic_run_watchdog` | `port` | `workflows/examples/generic_run_watchdog.yaml` | Apply the implemented generic provider-policy/profile capabilities; close `prompt-dependency-parity` and `generic-run-watchdog-port-plan-and-parity`; then execute the Stage 6 per-family promotion gate. |
| `hold_non_progress_step_back` | `hold` | `workflows/examples/non_progress_step_back_demo.yaml` | `step-back-owner-disposition`; no port or deletion is inferred while the protected queue remains held. |

## Gap decisions

| Gap ID | Applies to | Observed YAML mechanics | Classification | Gate or authority |
|---|---|---|---|---|
| `common.public-boundary-defaults` | `port_verified_iteration`, `port_generic_run_watchdog` | `default` on scalar, enum, integer, and relpath inputs | `implemented` | Bounded `defworkflow` scalar, enum, integer, and path defaults are implemented in the Workflow Lisp frontend specification and boundary-default tests. |
| `common.runtime-provider-selection` | `port_verified_iteration`, `port_generic_run_watchdog` | runtime `provider` input choosing one of a closed provider set | `implemented` | Keep each provider as a compiler-known extern and route the typed provider enum through effectful `if`; provider refs do not become runtime values. |
| `common.provider-call-policy` | `port_verified_iteration`, `port_generic_run_watchdog` | `provider_params` model/effort counterpart and `timeout_sec`: typed model and effort plus positive literal timeout with public compile-run-resume | `implemented` | Generic implementation closure: typed model and effort plus positive literal timeout are implemented through lowering, executable identity, runtime, and public compile-run-resume evidence. Family parity and promotion remain pending; YAML deletion remains pending. |
| `common.provider-invocation-profile` | `port_verified_iteration`, `port_generic_run_watchdog` | shared no-default unrestricted Codex Claude profiles | `implemented` | Exact argv profile evidence: `codex_unrestricted_workspace` uses `defaults={}`, `input_mode=stdin`, and `["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", "${model}", "--config", "reasoning_effort=${reasoning_effort}"]`; `claude_unrestricted_workspace` uses `defaults={}`, `input_mode=stdin`, and `["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]`. Both are shared provider data, not family-specific compiler routes. |
| `common.structured-results` | `port_verified_iteration`, `port_generic_run_watchdog` | provider `expected_outputs` sidecars and command `output_bundle` records | `implemented` | `provider-result`, `command-result`, native transportable returns, records, unions, enums, optionals, and runtime-owned bundle paths replace scalar sidecar parsing. Port scripts must honor the runtime bundle target and keep semantic files separate. |
| `common.prompt-dependency-parity` | `port_verified_iteration`, `port_generic_run_watchdog` | `depends_on` required files with `inject` content, ordering, and an optional instruction | `blocking_gate` | `prompt-dependency-parity`: typed prompt-input rendering is implemented, but each port must prove that the typed request and prompt assets preserve the required dependency content and ordering. Otherwise add the missing generic surface or obtain an explicit owner waiver. |
| `common.command-boundary` | `port_verified_iteration`, `port_generic_run_watchdog` | stable Python command steps that read workspace or run state and write structured artifacts | `implemented` | `command-result` plus external-tool or fully certified adapter bindings is the current route. Hidden stdout parsing and inline shell remain forbidden. |
| `verified.bounded-loop` | `port_verified_iteration` | `repeat_until`, maximum 40, typed terminal condition, and `on_exhausted` to `STALLED` | `implemented` | `loop/recur` supports runtime maximums, typed carried state, effectful bodies, typed `continue` and `done`, and scalar exhaustion projection through shared `repeat_until`. |
| `verified.iteration-artifact-lineage` | `port_verified_iteration` | `loop.index`-scoped work orders, verdicts, checks, reviews, ledger, status tokens, and resume-visible outputs | `blocking_gate` | `verified-iteration-artifact-lineage`: the compiled port and one-continue plus one-terminal smoke must prove per-iteration uniqueness, exact command and provider dependencies, Record idempotence, and resume-safe lineage. Generated paths may differ only where the parity contract classifies them private. |
| `verified.summary-pointer-helper` | `port_verified_iteration` | `PublishSummaryPath` calling `write_lisp_frontend_relpath_value.py` only to echo the summary path | `drop` | Return the typed summary relpath produced by the Record result directly. Do not port `write_lisp_frontend_relpath_value.py` as workflow behavior. |
| `verified.task-15-input-drift` | `port_verified_iteration` | Task 15 describes two prompt files and three commands, while the YAML has three provider prompt assets and a fourth pointer-only command | `implemented` | The port binds `work.md`, `review_iteration.md`, and `review_done.md`; it retains the prepare, check, and record command semantics and applies the preceding `drop` decision to the pointer helper. This gap list is the corrected Task 15 translation input. |
| `watchdog.probe-and-publication` | `port_generic_run_watchdog` | probe `output_bundle`, optional repair bundle consumption, and final watchdog `output_bundle` | `implemented` | Keep the run probe and final durable publication as explicit external command boundaries with typed record contracts and path-safe results. The probe's clock and run-store reads remain visible effects. |
| `watchdog.conditional-repair` | `port_generic_run_watchdog` | `when` over repair-required, provider repair, and deterministic no-action defaults | `implemented` | Use a typed repair/no-action union, effectful `if`, and a final typed projection. The provider result owns the repair decision; no report parsing controls routing. |
| `watchdog.port-plan-and-parity` | `port_generic_run_watchdog` | no existing `.orc` source or dedicated translation plan | `blocking_gate` | `generic-run-watchdog-port-plan-and-parity`: write the bounded port plan, name `workflows/library/generic_run_watchdog/watchdog.orc`, register parity/readiness, and prove clean plus repair-required paths before promotion. |
| `step-back.typed-routing` | `hold_non_progress_step_back` | command `output_bundle`, enum `match`, branch-local commands, and `set_scalar` | `implemented` | If the owner later selects port, `command-result`, typed enum routing, pure values, and typed workflow returns cover the observed language mechanics. This is capability evidence, not a port decision. |
| `step-back.owner-disposition` | `hold_non_progress_step_back` | protected recovery workflow has no authorized replacement disposition | `blocking_gate` | `step-back-owner-disposition`: the recovery owner must record an explicit delete-or-port decision and a reviewed handoff update before Stage 6 mutates or requeues the protected path. |

## Gate contracts and closure boundaries

### `provider-call-policy-parity` generic implementation closure

The generic language-surface portion of this gate is implemented. Ordinary
`provider-result` carries typed model and effort plus a positive literal timeout
through lowering, executable identity, runtime preparation, and public
compile/run/resume. Declarative provider data maps the canonical options, and
the two no-default unrestricted profiles preserve the retained operational argv.
The characterized YAML inputs remain the family proof targets:

- verified iteration: runtime worker and reviewer model and effort inputs, plus
  7200, 1800, and 3600 second call timeouts;
- generic watchdog: the workflow-level model and effort defaults plus the 7200
  second repair timeout.

This generic implementation closure does not prove either survivor family.
Each port must still bind its exact inputs and deadlines, prove actual provider
selection/argv plus prompt and artifact behavior, and pass its own run/resume and
promotion gates. Family parity and promotion remain pending. YAML deletion
remains pending the reference, supported-root-consumer, and Task-7 parser gates.
Dynamic provider selection remains separate and is already expressible by
branching over a closed typed enum while each branch names a compiler-known
extern.

### `prompt-dependency-parity`

The current typed prompt-input route is the preferred implementation, but
compile success alone is insufficient. Each port's provider-input evidence
must show that the request preserves all required semantic inputs from the YAML
dependency injection. The watchdog proof also binds the prepend instruction's
meaning, not its literal wording. Missing content, wrong ordering, or reliance
on an undeclared ambient file keeps the gate closed.

### `verified-iteration-artifact-lineage`

The Task 15 smoke must exercise one `CONTINUE` iteration and one terminal
route. It must bind loop-carried status, all three reviews/verdict channels,
the check result, ledger/status writes, summary publication, and Record's
resume idempotence. This is a family proof gate over implemented generic loop,
result, state-layout, and command machinery; it is not permission to add a
family-name compiler branch.

### `generic-run-watchdog-port-plan-and-parity`

The plan must cover both `repair_required=NO` and `repair_required=YES`, retain
the probe's run-store and clock effects, preserve repair result validation, and
prove the final published result. It must not infer successful repair from
provider prose or process exit alone.

### `step-back-owner-disposition`

The hold is a scheduling and authority gate, not a missing language feature.
Until the owner record exists, the protected YAML, its tests, prompt, recovery
plan, and related working-tree files remain byte-for-byte outside Stage 6.

## Current capability evidence

- `docs/design/workflow_lisp_frontend_specification.md`: workflow defaults,
  typed `if`, `match`, `loop/recur`, provider/command results, prompt externs,
  and generated path authority.
- `docs/design/workflow_lisp_native_transportable_returns.md`: direct typed
  record, union, scalar, optional, and path result transport.
- `docs/design/workflow_command_adapter_contract.md`: external-tool and
  certified-adapter command boundaries.
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`: promotion
  evidence and non-regression remain mandatory after compile and smoke.
- `tests/test_workflow_lisp_loop_recur.py`,
  `tests/test_workflow_lisp_structured_results.py`,
  `tests/test_workflow_lisp_native_returns_e2e.py`, and
  `tests/test_workflow_lisp_typed_prompt_inputs.py`: focused executable
  capability evidence.
- `tests/test_workflow_lisp_provider_call_policy.py`,
  `tests/test_provider_call_policy.py`, and
  `tests/test_workflow_lisp_provider_call_policy_e2e.py`: typed policy,
  declarative mapping/profile argv, and public compile/run/resume evidence.

## Port-entry decision

The generic provider-policy and invocation-profile prerequisites are available,
but neither port may claim parity or enter promotion until its remaining family
proof gates close. Family parity and promotion remain pending; YAML deletion
remains pending. The protected holdout remains excluded until
`step-back-owner-disposition` closes. No other unclassified gap remains in this
three-queue scope.
