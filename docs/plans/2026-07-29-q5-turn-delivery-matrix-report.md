# Q5 Turn-Delivery Matrix Report — Concurrent Debugging Agent

- **Date:** 2026-07-29 (concurrent agent, isolated clone; brief:
  `docs/plans/2026-07-29-q5-closeout-debug-brief.md`)
- **Substrate:** fresh clone of `mr4-local` @ `9fc11ae0` at
  `/home/ollie/.tmp/q5-debug2/repo`, branch `q5-turn-delivery-matrix`.
  No live attempt session, socket, or shared state was written; live-pane
  access was read-only `capture-pane`.
- **Stop record:** governs throughout. Nothing here marks Q5 complete or
  closes Task 14. The synced live probe below is diagnosis-grade
  instrumentation, explicitly not the Task-13 acceptance gate.

## Executive Summary

1. **V2 verdict: CONFIRMED.** Bracketed paste (`paste-buffer -p`) is the
   load-bearing element of `Stabilize bracketed interactive paste
   submission` (`9fc11ae0`). In 33 isolated real-codex sessions
   (v0.145.0, tmux 3.4), every bracketed cell submitted (14/14 across
   512 B–8 KiB payloads, 0–1 s settles, 80x24 and 200x50 panes), and every
   raw-paste-plus-immediate-Enter cell failed (0/5). Enter and C-m submit;
   KPEnter does not. **V3 (delivery-mode change) is not needed.**
2. **New blocker found and fixed: the graceful-close/receipt-flush race.**
   Attempt #7 (`q5-task13-submitv2b-20260729`, 01:31) got *both*
   interactive turns delivered and submitted — the first real-provider run
   ever to do so — and then crashed in `_close_and_join`:
   `PhasedSubmitProtocolClosedError` from a `BrokenPipeError` while
   flushing the final `accepted_closing` receipt. Root cause: the
   coordinator offered `/exit` to the codex pane *before* flushing the
   receipt to the submit client, and the submit client is a child of the
   provider's still-blocked tool call. The KILL cells prove codex
   v0.145.0 exits immediately on `/exit` mid-tool-call and kills the tool
   subprocess (4/4). Fix committed here: flush the receipt before any
   close byte, and terminalize (rather than crash) on flush failure.
3. **Fixed stack proven live.** With the fix and a startup-synchronized
   probe, the full invalid→valid spine completed against real codex in
   **37.67 s**: both submissions, `accepted_closing` flushed, `/exit`
   landed on an idle composer, natural join proven, terminal event
   `publication_succeeded`, ledger validates offline (`complete`, 21
   rows). First fully green real-provider combined cycle on this seam.
4. **Initial-offer startup race identified (affects fixtures without a
   blocking task action).** The adapter pastes the initial materialization
   turn ~50 ms after `task_started`; tmux applies bracket codes only if
   the pane application has *already* enabled bracketed paste, so a paste
   that races codex TUI startup degrades to raw and is never committed
   (this run's un-synced probe: stalled exactly like field attempt #4).
   The combined acceptance test is immune — its recording adapter gates
   the first offer on the task-action marker. Recorded as a design
   consideration for consumers whose task phase has no blocking action.
5. **F1/F2 field-validated.** Attempts #3 and #4 left truthful
   deadline-terminalized ledgers observable in their (still-live, dead-pane)
   tmux scrollbacks; see the audit appendix.

## Consolidation Disposition

The debug branch is diagnosis provenance, not a competing implementation
lineage. Its remaining deliverables were reconciled into the consolidated
`mr4-local` line as follows:

- matrix harness `52a52b2a` was integrated as `bcca80be`;
- startup-synchronized probe `ce39161c` was integrated as `e5048646`;
- this report `faf3e88f` was integrated as `26afe4a9`;
- the exact `d405e5ee` patch was **not** cherry-picked. Its diagnosis and
  required receipt-before-close ordering are accepted, but its code is
  superseded by the already-landed `4f350407`, `18cc7578`, and `668c9c53`
  stack. That stack flushes the final receipt before any adapter close
  bytes, routes accepted-closing, retry, final-rejection, exhausted, and
  active flush failures through the shared terminalizing resolver, preserves
  the primary protocol-closed/timeout diagnostic, and records close intent
  before the flush. It therefore covers the `d405e5ee` contract without
  reintroducing a parallel implementation.

Accordingly, later references in this historical report to “land
`d405e5ee`” describe the debug branch at the time of investigation and are
not current routing instructions. Production V2 bracketed-paste delivery
remains unchanged; `KPEnter` remains a negative harness control and is not a
production submit key.

## Workstream 1 — Isolated Turn-Delivery Matrix

### Harness

`scripts/q5_turn_delivery_matrix.py` (committed). Per cell: fresh private
tmux server → real `codex --model gpt-5.5 --config
model_reasoning_effort=low --dangerously-bypass-approvals-and-sandbox` in a
pre-trusted scratch dir (`~/.codex/config.toml` `projects` entry) → wait
for composer-ready → deliver a frame-shaped payload (JSON first line,
blank line, instruction, filler; embedded newlines; production-matched
sizes) with the production adapter's exact mechanics (`load-buffer`,
`paste-buffer [-p] -d`, per-key settle, `send-keys`) → success = the model
acts (filesystem sentinel), pane snapshots archived. Pane interpretation
is harness-only; the production adapter's declared-inputs boundary is
untouched. Field calibration: attempt #4's ledger shows the real initial
materialization turn is 2446 bytes (frame 234 + slice 2212), so the 2048 B
cells sit at production scale.

### Pass 1 (one run per cell)

| Cell | Paste | Settle s | Keys | Bytes | Trail NL | Pane | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A (attempt-4 replica) | raw | 0 | ENTER | 2048 | no | 80x24 | **not submitted** |
| B (V1 replica) | raw | 0.25 | ENTER,ENTER | 2048 | no | 80x24 | submitted |
| C (V2 production) | bracketed | 1.0 | ENTER,ENTER | 2048 | no | 80x24 | submitted |
| D | bracketed | 0.25 | ENTER | 2048 | no | 80x24 | submitted |
| E | bracketed | 0 | ENTER | 2048 | no | 80x24 | submitted |
| F | bracketed | 1.0 | ENTER | 2048 | no | 80x24 | submitted |
| G | raw | 1.0 | ENTER,ENTER | 2048 | no | 80x24 | submitted |
| H | raw | 2.0 | ENTER,ENTER | 2048 | no | 80x24 | submitted |
| I | bracketed | 1.0 | C-m | 2048 | no | 80x24 | submitted |
| J | bracketed | 1.0 | KPEnter | 2048 | no | 80x24 | **not submitted** |
| K | literal `send-keys -l` 256 B chunks | 0.5 | ENTER | 2048 | no | 80x24 | submitted |
| L | bracketed | 1.0 | ENTER,ENTER | 8192 | no | 80x24 | submitted |
| M | bracketed | 1.0 | ENTER,ENTER | 512 | no | 80x24 | submitted |
| N | bracketed | 1.0 | ENTER | 2048 | yes | 80x24 | submitted |
| O | raw | 0 | ENTER | 2048 | yes | 80x24 | **not submitted** |
| S | raw | 0 | ENTER | 512 | no | 80x24 | **not submitted** |
| X | bracketed | 1.0 | ENTER,ENTER | 2048 | no | 200x50 | submitted |

### Pass 2 (repeats, deterministic)

| Cell | Runs | Submitted |
| --- | --- | --- |
| A (raw, 0 s, ENTER) | 3 | 0/3 (0/5 incl. pass 1 + smoke) |
| B (V1: raw, 0.25 s, ENTER,ENTER) | 3 | 3/3 (4/4 incl. pass 1) |
| C (V2: bracketed, 1.0 s, ENTER,ENTER) | 3 | 3/3 (4/4) |
| E (bracketed, 0 s, ENTER) | 3 | 3/3 (4/4) |
| KILL (`/exit` mid-tool-call) | 3 | tool killed 3/3 (4/4) |

Raw data: `~/.tmp/q5-debug2/exp/{pass1,pass2}/matrix.jsonl` plus per-run
pane snapshots (`pane-<run>-postkeys.txt`, `pane-<run>-final.txt`).

### Findings

- **Failure boundary.** Into a *ready* composer, raw paste with an
  immediate single Enter never commits (composer visibly holds the full
  multi-line payload; the trailing Enter is absorbed by codex's
  burst-paste handling). Raw paste with ≥0.25 s settle and repeated Enter
  commits in isolation, but this is the marginal zone: production V1
  (attempt #5, same mechanics) still stalled in the field, where the offer
  additionally races provider startup (finding 4). Bracketed paste
  commits in every tested combination, including 0 s settle and a single
  Enter, at 512 B–8 KiB.
- **Minimal reliable sequence:** `load-buffer` + `paste-buffer -p` +
  `send-keys Enter` into a ready composer. V2's 1.0 s per-key settle and
  double ENTER are defense-in-depth on top of the load-bearing `-p`, and
  the settle additionally shrinks the startup-race window; keep V2 as is.
- **Key choice:** `Enter` and `C-m` both submit; `KPEnter` does not
  (0/1) — never use KPEnter in declared submit keys.
- **Startup race (finding 4).** tmux applies paste brackets only when the
  application has already requested bracketed-paste mode. The un-synced
  probe run (see Workstream 3) shows an offer racing codex startup
  degrades to raw paste and stalls exactly like field attempt #4
  (`deadline_exhausted_during_submit` after `turn_offered`). Any
  consumer whose task phase completes without a blocking action can hit
  this; the Task-13 combined test cannot (its first offer is gated on the
  task-action marker).

### V2 verdict

**Confirmed sufficient for turn commitment** (with the composer live),
and field-proven by attempt #7, where both interactive turns were
delivered and submitted. V2 was necessary but not sufficient for a green
attempt — the close race (below) then crashed the attempt after the
final submission.

## Workstream 3 → Coordinator Close Race (fix, not a delivery-mode change)

**V3 as scoped in the brief (chunked typing / file-handoff / non-tmux
injection) is not recommended** — the matrix shows tmux delivery is
reliable. The remaining engineering change is a coordinator sequencing
bug fix:

### Evidence chain

1. **Attempt #7 log** (`/tmp/q5-task13-submitv2b-20260729.log`, 45.81 s):
   `SubmitRequest(..., submission_ordinal=2)` arrived and was resolved
   `accepted_closing` inside `_close_and_join`; flushing that receipt hit
   `BrokenPipeError` → `PhasedSubmitProtocolClosedError` → the exception
   escaped `run()` uncaught (no terminalization, no terminal ledger row).
   (`payload_sha256` being the empty-string digest is by design —
   `submit_materialization` always sends `_EMPTY_PAYLOAD_SHA256`.)
2. **Code path** (pre-fix `coordinator.py::_close_and_join`): offer
   `/exit` + ENTER,ENTER to the pane *first*, resolve/flush the pending
   submit receipt *second*. The submit client
   (`orchestrator provider-materialization-submit`) blocks until the
   receipt and runs as a child of the provider's in-flight tool call.
3. **KILL cells (4/4):** pasting `/exit` + Enter while a codex tool call
   is running makes codex print its resume hint and exit immediately;
   the tool call's process tree dies (sentinel never appears). Hence:
   close-offer-first ⇒ submit client dies ⇒ receipt flush breaks — with
   a real interactive provider the old order can essentially never
   complete cleanly.
4. Prior attempts never reached this path (turn delivery failed first),
   and the synthetic/real-endpoint suites model the submit client as an
   independent thread that survives `offer_close`, which is why the race
   was invisible offline.

### Fix (committed here)

`d405e5ee Flush submit receipt before graceful close offer`

- `_close_and_join`: resolve/flush the `accepted_closing` receipt
  **before** `close_offer_requested`/`offer_close`. The client's
  request→receipt contract completes while the client is alive; the
  provider's tool call returns; the model ends its turn naturally; the
  close offer then lands on an idle composer. Endpoint admission stays
  safe: after the final ordinal, `_classify_request_locked` rejects any
  further submission, and `stop_admission` only touches unresolved
  records (no double-resolve).
- Both `endpoint.resolve` callsites (`accepted_closing` and
  `retry_queued`) now map `PhasedSubmitProtocolClosedError`/`TimeoutError`
  to `_NeedsTerminalization` with new registry reason
  `submit_receipt_flush_failed` (code
  `provider_phased_submit_protocol_invalid`, `S_ENDPOINT`), closing the
  no-terminal-row evidence gap attempt #7 exposed.
- Regression tests:
  `test_accepted_closing_flush_failure_terminalizes_before_close_offer`
  (flush failure ⇒ truthful `PhasedProviderAttemptFailure`, and no close
  byte was ever offered) and
  `test_retry_receipt_flush_failure_terminalizes_instead_of_escaping`;
  happy-path action-order assertion updated to the new order.
- Verification: 187 passed (coordinator + diagnostics suites), 546 passed
  (contracts, identity, policy, q5 expiry/diagnosis, prompt-phase ledger,
  interactive terminal), pyright clean on touched files.

### Live proof on the fixed stack

`ce39161c Synchronize live probe initial offer with provider startup`
upgrades the committed diagnosis probe with the same synchronization the
combined test already has (blocking task action via marker/release; first
offer gated on the marker) and production-matched ENTER,ENTER keys. Run
(`ORCHESTRATE_E2E=1 pytest -q -s
tests/e2e/test_e2e_q5_phased_live_codex_probe.py`, log
`~/.tmp/q5-debug2/exp/probe-fixed2.log`):

```
elapsed 37.67 s, PhasedProviderAttemptSuccess,
events: task_start_requested … submit_received, validation_rejected,
candidate_reset, retry_queued, turn_offered, submit_received,
candidate_frozen, close_offer_requested, close_offered,
ingress_shutdown_started/finished, join_started, join_succeeded,
publication_started, publication_succeeded
ledger_validation: status=complete, rows=21,
terminal_event=publication_succeeded
```

The same probe *without* the sync (first run this morning, log
`~/.tmp/q5-debug2/exp/probe-fixed.log`) expired at 900 s with
`deadline_exhausted_during_submit` after `turn_offered` and a truthful
8-event terminalized ledger (`status=complete`,
`terminal_event=terminal_failed`) — simultaneously demonstrating the
startup race (finding 4) and F1 working under the fixed stack.

## Workstream 2 — Evidence Audit Appendix

Ledger row sequences are from read-only captures of the still-live dead
panes (archived at `~/.tmp/q5-debug2/evidence-attempt3-real-pane.txt` and
`evidence-attempt4-trusted-pane.txt`); E2E workspaces (and ledger JSONL
files) are deleted at test end, so offline re-validation of field bytes is
only possible where files survive.

| # | Attempt | State reachable | Row sequence (events) | Terminal event | First diagnostic | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-07-27 task-13 run | none found (no socket, no workspace, no log) | — | — | (inferred) trust dialog | not re-runnable |
| 2 | 2026-07-28 combined proof | none found | — | — | (inferred) trust dialog | not re-runnable |
| 3 | `q5-task13-real-20260728` | dead-pane scrollback (1336 lines) | task_start_requested, task_started, turn_offer_requested, cleanup_finished, ingress_shutdown_started, ingress_shutdown_finished, terminal_failed (no `turn_offered`) | terminal_failed | `deadline_exhausted_during_initial_offer`; cleanup `deadline_exhausted_before_adapter_cleanup` | rows visibly contiguous + terminalized in dump; F1 rows present; bytes deleted, offline validator not re-runnable |
| 4 | `q5-task13-trusted-20260729` | dead-pane scrollback (1156 lines) | + `turn_offered` (initial materialization, 2446 B, submit_keys count 2) at 05:46:18Z; expiry rows at 06:45:57Z | terminal_failed | `deadline_exhausted_during_submit` | same as #3: F1 terminalization rows present in the field |
| 5 | `q5-task13-submitfixed-20260729` | server gone, no log found | (per stop-record note: five rows) | — | — | unreachable |
| 6 | `q5-task13-submitv2-20260729` (01:19) | server gone, no log found | — | — | — | unreachable |
| 7 | `q5-task13-submitv2b-20260729` (01:31) | full pytest log `/tmp/q5-task13-submitv2b-20260729.log` + dead runner pane | delivered through second `submit_received`; crash in `_close_and_join` before any terminal row could be written | **none** (crash bypassed terminalization — gap now closed by `d405e5ee`) | `PhasedSubmitProtocolClosedError` ← `BrokenPipeError` at receipt flush | ledger bytes deleted with workspace |
| — | surviving synthetic ledger (task-5 era, `/tmp/q5t5-6boe7g4g/...jsonl`) | file on disk | 11 events incl. submit_received, validation_rejected, candidate_reset + F1 terminalization rows | terminal_failed | — | **offline validator run: `status=complete`, `terminal_event=terminal_failed`** |
| — | synced probe run (fixed stack, this clone) | full ledger + log | 19 events, full invalid→valid spine | publication_succeeded | none | **offline: `complete`, 21 rows** |

F1's first real-provider field validation: attempts #3 and #4 both carry
the post-expiry terminalization rows (`cleanup_finished`,
`ingress_shutdown_started/finished`, `terminal_failed`) with truthful
deadline diagnostics — the fix behaves in the field exactly as designed.
Attempt #7 shows the one path F1 did not cover (raw escape from the
receipt flush), which `d405e5ee` closes.

## Recommendations for the primary agent (attempt #8)

1. Fetch and land, in order:
   `52a52b2a` (harness), `d405e5ee` (**the fix — required for any green
   combined run**; without it the final submission deterministically
   broken-pipes), `ce39161c` (probe sync).
   `git fetch /home/ollie/.tmp/q5-debug2/repo q5-turn-delivery-matrix`.
2. Keep V2 exactly as landed; no further keystroke changes needed. Never
   introduce KPEnter.
3. The combined test's driver/marker synchronization is load-bearing for
   the initial offer; do not remove it. For future consumers without a
   blocking task action, the startup race needs a design decision
   (declared-input-compatible options: settle-before-first-offer, or a
   readiness contract) — owner-scope, not patched here.
4. Trust entries added to `~/.codex/config.toml` (additive only):
   `/home/ollie/.tmp/q5-debug2/exp`, `/home/ollie/.tmp/q5-debug2/repo`.
   Remove them when this clone is discarded.
