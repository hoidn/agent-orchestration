# Q5 Phased Turn-Queue Coordinator Diagnosis Report (2026-07-28)

- **Task brief:** `docs/plans/2026-07-28-q5-phased-turn-queue-coordinator-diagnosis-task.md`
- **Substrate:** fresh clone of the canonical repository at `bceb03e4`
  (`Activate phased contract delivery`, tip of `main`), per the brief's
  execution addendum. All file:line references below are against that commit.
- **Method:** provider-free. The real `PhasedProviderAttemptCoordinator`, the
  real `InteractiveTerminalTurnQueueAdapter` (real tmux backend), the real
  `PhasedSubmitEndpoint` (real unix socket), the real
  `ProviderPromptPhaseLedgerWriter`, and the production `AWAITING_SUBMIT`
  polling loop are driven end to end by a deterministic scripted provider
  running inside the tmux pane and submitting through the production
  `submit_materialization` helper. No coordinator internals are mocked; the
  turn-queue capability boundary is not bypassed.
- **Fixture modules (this clone):**
  - `tests/test_q5_phased_synthetic_provider_diagnosis.py` (real stack,
    6 behavior fixtures + 1 strict-xfail contract fixture)
  - `tests/test_q5_phased_deadline_expiry_ledger_surfacing.py`
    (deterministic frozen-clock mechanics, 2 behavior fixtures + 1
    strict-xfail contract fixture)
- **Result:** `8 passed, 2 xfailed` (strict xfails are the confirmed-defect
  contract fixtures); adjacent suites
  (`test_provider_phased_delivery_coordinator.py`,
  `test_provider_prompt_phase_ledger.py`,
  `test_workflow_lisp_phased_delivery_runtime.py`,
  `test_provider_interactive_terminal.py`) `633 passed`.

## Executive verdict

- **H1 (an unbounded wait): refuted.** Every blocking wait reachable between
  attempt admission and terminal outcome is bounded by the single
  whole-attempt monotonic deadline; the stalls forced at every
  provider-reachable wait state terminate at that deadline, executably.
- **H2 (a swallowed expiry): confirmed, twice** (findings F1 and F2 below),
  each with a strict-xfail fixture that is the ready-made regression test.
  Both defects make deadline/terminalization outcomes invisible or invalid in
  the *evidence surface* (phase ledger / offline validation) while the
  returned failure object stays correct. F1 reproduces, byte-shape for
  byte-shape, the silent five-row ledger observed on 2026-07-27 and recorded
  by the 2026-07-28 stop record.
- **The observed stall itself was not a coordinator hang.** The 2026-07-27
  "55 minutes of silence" is a *healthy bounded wait still inside its 3600 s
  budget* with a provider that never submitted, over a ledger that by
  construction shows nothing between `turn_offered` and the (never-reached)
  submit — and, per F1, would have shown nothing even at expiry. The
  2026-07-28 runs terminating at 3601.5 s are the deadline working as
  implemented. A provider that actually *dies* mid-wait is detected in well
  under a second and produces a full terminalization ledger (fixture T4), so
  during the observed windows the real provider was alive-and-idle, exactly
  as the stop record's `provider_behavior_nonterminating` classification
  says.

**Outcome routing selected (exactly one): H1/H2 — coordinator/adapter defect
found.** F1 and F2 are fixed under the stopped Q5 implementation plan's
discipline (TDD — the two strict-xfail fixtures become the regression tests;
ordered spec-then-quality review; reviewed-bytes commits). Only after those
fixes land may the combined invalid→valid real-provider proof be
re-attempted, and the re-attempt inherits this instrumentation. To be
explicit about scope: F1/F2 explain why the two failures were
*uninterpretable and unevidenceable*, not why the provider declined to
submit; if a post-fix re-attempt stalls again, its ledger will now carry the
deadline terminalization rows and validate offline, proving the
provider-behavioral residue directly and giving the owner the H3 decision
basis (different acceptance model/effort, or a prompt-queue change) with
evidence instead of silence.

## Findings

### F1 — confirmed H2 defect: no ledger row can ever record a whole-attempt deadline expiry

**Mechanism.** Every coordinator operation shares one deadline
(`_CoordinatorSession.attempt_deadline`, = `composition.deadline`).
`PhasedProviderAttemptCoordinator._append`
(`orchestrator/workflow/provider_phased_delivery/coordinator.py:331-354`)
admits a `ledger_append` deadline operation against that same deadline before
every write; `_safe_append` (`coordinator.py:356-370`) converts the refusal
into a silent `False`. Once the whole-attempt deadline expires — which is the
*only* way any `deadline_exhausted_*` terminalization begins — every
subsequent append is refused, so the entire fail-safe terminalization
production (`cleanup_finished`, `ingress_shutdown_started`,
`ingress_shutdown_finished|failed`, `terminal_failed`, and `join_failed`
after a join expiry) is dropped. The ledger keeps the healthy-looking prefix;
offline validation reports `valid_prefix / nonterminal_prefix`; the run is
indistinguishable, from evidence alone, from an attempt still waiting.

**Design contradiction.** The accepted design requires the opposite:
`docs/design/workflow_lisp_phased_contract_delivery.md` makes fail-safe
terminalization "the only exception" to the zero-call rule — reached "with no
remaining budget", it still *emits* `ingress_shutdown_finished` /
`ingress_shutdown_failed` and follows the T2a/T2b edges (design "Deadline
observation discipline", incl. the fail-safe paragraph, and the T0–T3
terminalization productions, which route *every* pre-proof failure —
explicitly including deadline failures — through `cleanup_finished` →
ingress rows → `terminal_failed`). The design's tolerance for a missing
terminal row is tied to filesystem/state failure and post-join best-effort
rows, not to deadline gating of the terminalizer's own appends.

**Executable evidence.**

- `tests/test_q5_phased_deadline_expiry_ledger_surfacing.py::test_post_expiry_terminalization_leaves_healthy_looking_ledger_prefix`
  — deterministic frozen clock, real ledger writer: exactly 5 rows (header +
  `task_start_requested`, `task_started`, `turn_offer_requested`,
  `turn_offered`), `valid_prefix`, `terminal_event: None`.
- `…::test_post_expiry_terminalization_returns_structured_failure_but_skips_cleanup`
  — the failure object alone carries `deadline_exhausted_during_submit`,
  `cleanup_diagnostic deadline_exhausted_before_adapter_cleanup`,
  `abort_calls 0`.
- `…::test_post_expiry_terminalization_emits_failsafe_ledger_rows` —
  **strict xfail**: asserts the design-mandated emissions; remove the xfail
  with the fix.
- Real-stack replays (below) show the same 5-row byte shape under the real
  adapter/endpoint/ledger: fixtures T2, T3, T6.

**Correspondence to observations.** The stop record
(`Record phased consumer gate stop`, 3fc3a09e in the active lineage) reports
both real runs failing at `3601.5x s` with "each observed phase ledger
remained at the five-event pre-submit prefix" — exactly this shape. The
2026-07-27 silence-then-abandonment is the same ledger contract observed
mid-wait.

### F2 — confirmed H2 defect: a truthful exhausted-attempts terminalization ledger fails offline validation

**Mechanism.** `PhasedSubmitEndpoint.resolve`
(`orchestrator/workflow/provider_phased_delivery/endpoint.py:349-355`)
increments `active_requests_drained` only for `accepted_closing` receipts. A
submission resolved with a terminal `failed` receipt — the
`materialization_attempts_exhausted` path
(`coordinator.py:1136-1153`) — counts nothing, and by shutdown time there is
nothing left to drain. The offline validator's grammar
(`orchestrator/workflow/provider_phased_delivery/ledger.py:2093-2099`)
requires `active_requests_drained >= 1` at `ingress_shutdown_finished|failed`
whenever a `submit_received` has been seen (`current_submit` is set at
`submit_received`, `ledger.py:1896`, and never cleared). Result: the
*complete, truthful* terminalization ledger — through `terminal_failed` — is
classified `malformed / payload_invalid`, `terminal_event: None`.

**Impact.** Deadline-independent. Any real acceptance attempt that submits
invalid materializations until exhaustion produces evidence that cannot
validate offline; had the 2026-07-28 runs submitted-but-failed instead of
never submitting, the evidence chain would have been poisoned by F2 instead
of silenced by F1.

**Executable evidence.**

- `tests/test_q5_phased_synthetic_provider_diagnosis.py::test_exhausted_attempts_aborts_live_provider_and_surfaces_terminal_rows`
  — real stack: all 11 rows land (`…`, `cleanup_finished`,
  `ingress_shutdown_started`, `ingress_shutdown_finished`,
  `terminal_failed`), live abort ran (`abort_calls 1`, cleanup `COMPLETE`,
  tmux server gone), yet `validate_ledger_bytes` → `malformed /
  payload_invalid`. Bisection localizes the rejected row to the
  terminalizing `ingress_shutdown_finished` with `workers_joined: 1,
  active_requests_drained: 0`; the identical payload shape in the *normal*
  close path (fixture T1) validates `complete`, because there
  `accepted_closing` incremented the drain counter.
- `…::test_exhausted_attempts_ledger_should_validate_offline` — **strict
  xfail**: asserts `complete` / `terminal_failed`; remove with the fix.

Whether the fix belongs in the producer (count terminally-failed resolutions
as drainage), the validator (drop or refine the `current_submit` drain rule),
or the design's payload table is a spec decision for the Q5 plan's ordered
review — the fixture pins the contract either way.

### O1 — designed, consequential: post-expiry terminalization never aborts the provider

Not a defect — the design's zero-call rule explicitly covers it ("post-start
abort is not called because its before-check observes expiry", cleanup table;
"expiry before abort starts zero adapter backend actions…") — but it is why
both real runs left live provider processes/sockets for manual cleanup, and
fixtures T2/T3/T6 assert the surviving tmux server as evidence
(`provider_cleanup INCOMPLETE`, `abort_calls 0`,
`cleanup_diagnostic deadline_exhausted_before_adapter_cleanup`). Operators
must expect survivor reaping after every whole-attempt deadline expiry; only
the returned failure object says so (and, until F1 is fixed, nothing in the
ledger does).

## Wait-state enumeration (task item 1)

Scope: every blocking wait reachable between attempt admission
(`run()`/`derive_attempt_deadline`) and terminal outcome, from code. The
single budget is `composition.deadline` (absolute monotonic; production:
step `timeout_sec`, default 3600 —
`runtime_bindings.py:228-237`). Coordinator-side `_admit_deadline` /
`_finish_deadline` brackets are *checks*, not enforcement; boundedness is a
property of each callee, verified below. "Surfaces" columns describe (a) the
returned outcome and (b) the phase ledger.

Legend — fixtures `T1…T6` are in
`tests/test_q5_phased_synthetic_provider_diagnosis.py`:
T1 `test_synthetic_provider_completes_invalid_then_valid_spine`,
T2 `test_never_engaging_provider_bounds_wait_at_whole_attempt_deadline`,
T3 `test_mid_phase_silent_provider_bounds_wait_and_freezes_ledger_prefix`,
T4 `test_provider_exit_before_submit_surfaces_and_terminalizes_fast`,
T5 `test_exhausted_attempts_aborts_live_provider_and_surfaces_terminal_rows`,
T6 `test_close_refusing_provider_bounds_join_and_freezes_ledger_at_join_started`;
`B*` are in `tests/test_q5_phased_deadline_expiry_ledger_surfacing.py`.

| ID | Wait state (code) | Blocking primitive | Deadline | Expiry surfacing | Verdict / evidence |
| --- | --- | --- | --- | --- | --- |
| W-R1 | `AWAITING_SUBMIT` loop, `runtime_bindings.py:744-765` | 50 ms sliced `endpoint.receive_event` + sliced liveness probe | whole-attempt, checked every slice | outcome: `SerializedAttemptEvent(deadline)` → `deadline_exhausted_during_submit`; provider death → `provider_exit` → `provider_exited_before_submit`; ledger: **nothing at expiry (F1)**; heartbeatless by design mid-wait | **bounded, surfaced-in-outcome, silent-in-ledger.** Forced stalls: T2 (never engages; terminates in `[T, T+4)`), T3 (silent mid-phase); death path: T4 (detected < 10 s, full terminal rows); slicing unit tests `test_workflow_lisp_phased_delivery_runtime.py::test_phased_liveness_probe_timeout_is_sliced_and_rechecks_submit`, `::test_phased_submit_wait_reports_whole_attempt_deadline` |
| W-A1 | adapter `start`, `interactive_terminal.py:973-1083` | tmux `subprocess.run` per op, each `timeout = min(remaining, 5 s)` (`_remaining` `:1641-1650`; backend `_run` `:602-630` always passes `timeout=`) | whole-attempt, per-op | outcome: `start_timeout` failed outcome with `NoBackendAllocationProof` (pre-allocation) or cleanup evidence (post-allocation); coordinator `task_start_failed` ledger row (pre-expiry) | **bounded, surfaced.** Live: T1–T6; not provider-forceable mid-op (tmux-side); expiry covered by `test_provider_interactive_terminal.py::test_interactive_adapter_start_outcome_before_deadline_proves_no_allocation`, `::test_interactive_adapter_deadline_limits_every_selected_backend_action`, `::test_interactive_adapter_during_operation_deadline_starts_no_later_action`; coordinator admission: `test_whole_attempt_deadline_matrix` |
| W-A2 | adapter `offer` (initial/retry), `:1115-1174` | `_require_live_process` + `load-buffer`/`paste-buffer`/`send-keys`, each bounded as W-A1 | whole-attempt, per-op | `offer_timeout` exception → coordinator `initial_offer_failed`/`retry_offer_failed` + `turn_offer_failed` row (pre-expiry) | **bounded, surfaced.** Live: T1/T3/T6; independent of provider cooperation (send-keys cannot be stalled by an unreading provider — pty buffering, small turns); expiry: `::test_interactive_adapter_offer_deadline_expiry_starts_zero_backend_actions`, `::test_interactive_adapter_offer_operations_share_one_deadline`, `::test_interactive_adapter_types_backend_offer_timeouts` |
| W-A3 | adapter `offer_close`, `:1176-1228` | same as W-A2 | whole-attempt, per-op | `close_offer_timeout` → `close_offer_failed` (+row pre-expiry) | **bounded, surfaced.** Live: T1/T6; expiry: same adapter parametrized tests (`close` arm) |
| W-A4 | adapter `probe_process_status`, `:1085-1113` | one bounded tmux `display-message` + exit-file `read_text` | ≤ min(whole-attempt, 50 ms slice from W-R1, 5 s cap) | `backend_operation_timeout` → treated as still-running by W-R1 (continue + re-check); `pane_lost`/non-running → `provider_exit` | **bounded, surfaced.** Live every 50 ms in T2/T3 (~120+ probes per run); death detection T4 |
| W-A5 | adapter `join` poll loop, `:1243-1276` + teardown `:1278-1328` | `pane_process_status` per iteration + `wait(min(poll, deadline-now))`; loop pre-checks `now >= deadline` each pass | whole-attempt | `natural_shutdown_timeout` → coordinator `deadline_exhausted_during_join` (the `_finish_deadline` after-check fires before `join_failed` can be appended); ledger: **ends at `join_started` (F1 flavor)** | **bounded, surfaced-in-outcome, silent-in-ledger.** Forced: T6 (provider refuses close; terminates in `[T, T+4)`) |
| W-A6 | adapter `abort`, `:1342-1470` | straight-line bounded tmux ops; per-op `remaining()` closure skips ops at expiry, never raises | whole-attempt, per-op | returned `FailedCleanupProof` with `error_code` (`cleanup_timeout` on expiry), `cleanup_complete` bool; coordinator `cleanup_finished` row (pre-expiry only) | **bounded (total by construction), surfaced-in-proof.** Live abort: T4 (dead pane), T5 (live pane); post-expiry zero-call skip: B1 + O1; `test_provider_interactive_terminal.py::test_interactive_adapter_abort_at_expired_deadline_is_total` |
| W-A7 | adapter method-entry `RLock` (`:982,:1094,:1125,:1183,:1236,:1348`) | untimed `RLock.__enter__`; `join` holds it across its poll loop | none (primitive); transitively whole-attempt | blocked caller re-checks deadline after acquire (late but typed) | **unreachable cross-thread in production**: the coordinator is single-threaded and endpoint worker threads never call the adapter. Shown unreachable, not skipped. |
| W-A8 | adapter/backend FS syscalls (exit-file `exists`/`read_text` `:761-765`, socket unlink `:1625-1639`, `__init__` mkdir/mkdtemp/resolve) | untimed syscalls | none | n/a (typed errors on failure; exit file is tmp+`mv` regular file — cannot block on a writer) | **bounded in practice; hazard only on a pathological (hung NFS/FUSE) filesystem.** Out of provider reach; noted for completeness |
| W-E1 | endpoint `receive_event`, `endpoint.py:278-294` | `Condition.wait(timeout=_remaining(min(binding, caller)))` re-checked per wakeup | min(whole-attempt, caller slice) | `TimeoutError` per slice → W-R1; closed endpoint → `RuntimeError` | **bounded, surfaced.** Live: T1–T6 (50 ms slices); expiry semantics exercised continuously in T2/T3 |
| W-E2 | endpoint `resolve` receipt flush, `:333-346` | `Future.result(timeout=_remaining(binding))` | whole-attempt | `TimeoutError`; worker death from an exception class outside `(FutureTimeout, OSError, TimeoutError, TypeError, ValueError)` (`:736-744`) leaves the future unset and `resolve` waiting to full deadline — bounded but undiagnosed until expiry | **bounded, surfaced; residual silent-stall-to-deadline hazard on anomalous worker death** (no in-repo exception source; not provider-forceable through the wire protocol — code-cited, kept on the enumeration) |
| W-E3 | endpoint `shutdown` thread joins, `:397-447` | `Thread.join(timeout=_remaining(min(binding, caller)))` per thread; `except TimeoutError: break` | min(whole-attempt, caller) | **no exception ever escapes**; expiry surfaces only as `SubmitEndpointShutdownOutcome` statuses (`workers_joined`, `endpoint_zero_survivor_proven=False`) | **bounded, status-surfaced.** Exercised in every fixture incl. post-expiry (T2/T3/T6 report `endpoint_shutdown_status complete`); B1 asserts the fail-safe still runs post-expiry |
| W-E4 | endpoint accept loop, `:644-653` | `listener.accept()` with `settimeout(min(0.05, _remaining(binding)))` | whole-attempt, 50 ms poll | at binding-deadline expiry the accept thread exits **silently**, listener left open; post-expiry clients block until their own deadline | **bounded; silent by itself** — subsumed by the post-expiry dark period (F1): once the attempt deadline has passed, nothing on this surface is expected to serve. Reachable only at/after expiry; code-cited |
| W-E5 | endpoint worker request read / waiter / receipt sendall, `:682-733`; client `send_submit_request`, `protocol.py:546-591` | per-op `settimeout(_remaining(binding))`; receipt `sendall` at `:733` runs **inside `self._condition`** | whole-attempt | socket timeouts → worker death → client `PhasedSubmitProtocolClosedError`; the sendall-under-lock can pin `receive_event`/`resolve`/`stop_admission`/`shutdown` until the binding deadline (a tighter shutdown cutoff cannot preempt it) | **bounded by the whole-attempt deadline, surfaced client-side.** Live: every submitting fixture; the lock-pinning stall needs a malicious/wedged client with a full socket buffer — not forceable with protocol-sized receipts; code-cited |
| W-L1 | ledger appends (`coordinator._append` → writer) | plain file I/O, no waiting primitive | gated by `ledger_append` admission against the whole-attempt deadline | pre-expiry failures poison the channel and raise `evidence_append_failed`; **post-expiry: the F1 gate — all terminalization appends silently dropped** | **the confirmed H2 seam; see F1** (fixtures B1/B2/B-xfail, T2/T3/T6) |
| W-B1 | consumer-side bindings (`snapshot_candidates`, `validate_*`, `freeze/reset`, evidence/restore/verify, `prepare/atomic_success_commit`) | binding-defined (workspace I/O, state commit) | admission before + after-check (`coordinator.py` per-op brackets; design: "admission never shields long validation … from this after-check") | during-expiry surfaces as `deadline_exhausted_during_*` after the call returns | **out of diagnosis scope** (consumer side, scripted in fixtures per the brief); after-check semantics are the design's chosen containment; coordinator-side surfacing covered by `test_whole_attempt_deadline_matrix` and `test_crossed_deadline_precedes_malformed_operation_return` |

Coordinator admission brackets for all 17 registry operations
(`diagnostics.py:517-644`) — before/during expiry reasons and diagnostic
codes — are exhaustively covered by the existing
`test_provider_phased_delivery_coordinator.py::test_whole_attempt_deadline_matrix`
(kept passing at `bceb03e4`; re-run as part of this diagnosis).

## Replay of the observed failure shapes (task item 3)

- **(a) Never engages the handshake** — fixture T2: run terminates at
  `deadline ≤ finish < deadline+4 s` with
  `deadline_exhausted_during_submit`; the ledger is byte-shape identical to
  the observed evidence: exactly 5 rows, events
  `task_start_requested, task_started, turn_offer_requested, turn_offered`,
  offline validation `valid_prefix / nonterminal_prefix / terminal_event
  None`; the provider pane and tmux server demonstrably survive (O1).
  Interpretation of 2026-07-27: silence from 10:33 was the designed
  heartbeatless wait inside budget; even at expiry the ledger would not have
  moved (F1). A dead provider cannot explain the window: T4 proves death
  surfaces in seconds with full terminal rows.
- **(b) Engages then goes silent mid-phase** — fixture T3: identical bounded
  termination; ledger ends `…, retry_queued, turn_offer_requested,
  turn_offered` with no terminal rows — again `valid_prefix`. A mid-phase
  silence is therefore *also* evidence-invisible under F1.

## Offline ledger validation over every fixture ledger (task item 4)

| Fixture | Validation status | terminal_event | Reading |
| --- | --- | --- | --- |
| T1 happy invalid→valid | `complete` | `publication_succeeded` | full spine, provider-free, in ~2 s wall |
| T2 never-engage | `valid_prefix` | `None` | **confirmed H2 (F1)**: forced stall ⇒ silent ledger |
| T3 silent mid-phase | `valid_prefix` | `None` | **confirmed H2 (F1)** |
| T4 death pre-submit | `complete`-grade terminal (`terminal_failed`) | `terminal_failed` | pre-expiry surfacing works |
| T5 exhausted attempts | `malformed / payload_invalid` | `None` | **confirmed H2 (F2)**: truthful ledger condemned |
| T6 refuse close | `valid_prefix` | `None` | **confirmed H2 (F1, join flavor)**: ends at `join_started` |
| B1/B2 frozen-clock expiry | `valid_prefix` | `None` | deterministic F1 mechanics |

## What the fix must cover (routed to the stopped Q5 plan's discipline)

1. **F1**: allow the fail-safe terminalizer's ledger emissions to proceed
   after whole-attempt expiry (per design: terminalization is the only
   exception to the zero-call rule), or amend the design if the owner instead
   wants the current gating — either way the strict-xfail fixture
   `test_post_expiry_terminalization_emits_failsafe_ledger_rows` is the
   acceptance test, and T2/T3/T6's ledger assertions flip with it.
2. **F2**: reconcile endpoint drain accounting with the validator's
   `current_submit` rule (producer, validator, or design payload table —
   spec decision), acceptance test
   `test_exhausted_attempts_ledger_should_validate_offline`.
3. Re-attempt the combined invalid→valid real-provider proof only after 1–2
   land; the re-attempt inherits these fixtures/instrumentation so any
   recurrence is interpretable (a stalled provider now yields a terminal
   ledger row and a validating evidence chain, which is the H3 evidence the
   owner would then decide on).

Constraint compliance: no production code was changed in this diagnosis; the
only additions are the two fixture modules and this report, developed and
committed in the prescribed fresh clone. The stop record stays governing: Q5
status does not move; no split-proof substitution; no Task-14 closure.
