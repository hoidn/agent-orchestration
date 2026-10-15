# Native Session CLI Probe — Live Execution

**Status:** The bounded observation-only execution is complete: **17 CLI/model attempts, nine Codex and eight Claude**, with independent evidence review and coordinator verification complete. Codex demonstrated bounded active-writer exclusion; Claude accepted overlapping native appends, so its exclusive-continuation obligation is `NOT_OBSERVED`. Exact interrupted-turn recovery remains inconclusive for both providers, and Codex atomic continuation from an expected position remains unqualified. No native-session adapter or runtime capability is enabled by this result.

The [plan](../plans/2026-10-13-native-session-cli-probe-plan.md) and [preparation report](2026-10-13-native-session-cli-probe.md) own the protocol and local harness evidence. The separate JSON prompt-rendering change does not affect this experiment: its hand-authored prompts use the CLI's native JSON Schema flags.

## Original campaign and evidence

Executed from the repository root through tmux:

```sh
python scripts/experiments/native_session_cli_probe.py --provider codex --execute --model gpt-6-luna --output-dir /tmp/native-session-cli-live-20261013-5vscq03t/codex
```

The campaign recorded Codex CLI `0.162.1`, low effort, a 180-second deadline per model attempt and a hard eight-attempt bound. Its current exclusivity gate permits at most four calls before stopping. It performed **one** model call, with no automatic retry. The wrapper exited 1 after 6.155 seconds; the model invocation exited 0 after 5.769 seconds. No timeout or interruption was requested.

Private evidence is under `/tmp/native-session-cli-live-20261013-5vscq03t/`: `authorization.json` records the selected model, bounds and source hashes; `execution.json` records the command and wrapper exit; `codex/observations.json` records the invocation, gates and skipped stages. `codex/evidence/` contains raw stdout/stderr and the native-store snapshot. These temporary local files are not durable repository attachments. The staged authentication file was removed and its absence checked.

Native session: `01a1376c-a966-7cd2-ac38-28dce83915e1`. Native turn: `01a1376c-ab2c-7f11-bf8a-76dd83455452`. Snapshot `native-01-review.jsonl` has SHA-256 `41c4038b94d0b167760e1f72f9d6fa1ebb65589a4b9710e782bae602d48c4553`.

## Original campaign observations

| Obligation | Observed evidence | Disposition / limit |
| --- | --- | --- |
| Review without changing the workspace | Schema-1 result has the submitted nonce and `reviewed: true`; workspace snapshots match. | Observed for this single fresh turn. |
| Exact completion identifiable without stdout | Native snapshot binds session, nonce-bearing user message, turn ID, final result and `task_complete`; references are session metadata and lines 2, 10, 18 and 22. | Observed for this fresh turn; no same-session continuation yet. |
| All child processes terminated before appending | CLI exit 0, but harness receipt has `quiescent: false`. The original receipt does not record which tracking condition failed. | Inconclusive. Native completion is established independently; process quiescence is not. |
| Turn 2 applies a different schema and reverses the review-only task instruction | Invocation 2 not run. | Inconclusive; stopped at the process gate. |
| Two concurrent resumes enforce exclusive continuation | Invocations 3–4 not run. | Inconclusive. |
| Interruption and recovery | Invocations 5–6 not run. | Inconclusive. |
| Distinguishable native-session loss | Invocation 7 not run. | Inconclusive. |
| Alternate-home isolation | Invocation 8 not run. | Inconclusive; selecting a private home alone is not this proof. |
| Claude equivalents | No Claude model calls. | Pending the Codex gates. |

The report's generic completion-gate reason combines several conditions. In this invocation the native result and unchanged workspace passed; the failed condition was quiescence. It must not be described as failure to identify a native completion.

## Harness diagnosis

Offline controlled subprocess tests reproduced a race: a short-lived descendant can disappear between the `/proc` snapshot and `pidfd_open`. The tracker permanently marks that normal exit as a tracking failure, even when no owned process remains alive. Reproduction evidence is `/tmp/native-process-exit-race-pw76uuze/controlled.json`.

This establishes a harness defect, not its retrospective causality for the live run. The live receipt lacks the diagnostic detail needed to prove that this race caused its stop. The original inconclusive receipt is retained unchanged; a correction cannot retroactively upgrade it.

The correction accepts disappearance only after rechecking the original
PID/start-time identity. Permission errors, failed reads, an original process
still alive, ambiguous adoption and live descendants continue to reject
quiescence. Receipts now retain tracking flags and captured identities.
Independent code review passed; the three harness modules collected and
passed **98 tests in 13.64s**, and `py_compile` passed. Logs and exit codes are
in `/tmp/native-process-race-checks-gyher3c7/`. The reviewer independently ran
the 14 process tests. No provider calls were made by these checks.

## Corrected campaign — historical first-phase result

The coordinator explicitly launched a fresh campaign after reviewing the
correction. This was not an automatic retry, and the original attempt counts
toward the same eight-attempt bound. No receipt was rewritten or accepted
retrospectively.

```sh
python scripts/experiments/native_session_cli_probe.py --provider codex --execute --model gpt-6-luna --output-dir /tmp/native-session-cli-corrected-20261013-puhfqktj/codex
```

Codex CLI `0.162.1`, `gpt-6-luna`, low effort. The wrapper started at
`2026-10-13T22:52:18.849632Z` and exited 0 after 15.623 seconds, having made
four attempts. Its semantic disposition is `STOPPED_AT_EXCLUSIVITY_GATE`;
exit 0 does not mean qualification. Every invocation reports quiescence with
no tracking failures. The copied auth file was removed and absence verified.
The private evidence root contains `authorization.json`, `execution.json`,
`codex/observations.json`, raw per-invocation logs and native snapshots.

Session: `01a13777-79ec-7511-8b2b-42a6111e33cf`.

| Obligation | Observation and evidence | Disposition / limit |
| --- | --- | --- |
| Turn 1 has its own schema and makes no workspace edits | Schema 1, matching nonce, unchanged workspace; native `01-review` snapshot SHA-256 `4ba9c63f1676d17c9616289eb6c28c6c5843af210acfd0233e2ccf15844f3001`. | `OBSERVED` for result and no edits; the receipt does not prove substantive review of the file. |
| Turn 2 applies schema 2 and writes despite turn 1's no-change instruction | Same-session resume returned schema 2 without schema-1 fields and wrote exactly its fresh nonce to `execution.txt`; no other workspace changes. Native `02-write` snapshot SHA-256 `f525fda0ffaff5124631c9f5e0f5209da709c195172aba823af18273f4748d03`. | `OBSERVED`. |
| Completion can be identified without stdout or a harness completion receipt | Native session, prompt nonce, turn, predecessor, final value and completion bind for both turns. The coordinator also reconciled completed turn 3 from the final store alone. | `OBSERVED` for these completed turns, not a general crash-recovery proof. |
| Two simultaneous resumes encounter native exclusion | While turn 3's tool was held, call 4 failed with `thread-store conflict`, the exact session UUID, `already has an active writer` and code `-32600`. Its nonce never appears in the native store; stdout is empty. | Active-writer exclusion `OBSERVED`, bounded to this attempt and CLI version. |
| Continuation atomically checks the expected predecessor | The expected predecessor was prompt text, not a native compare-and-append condition. No test establishes protection against another writer completing between a precheck and lock acquisition. | Full design obligation remains `INCONCLUSIVE`. |
| Interrupt a running turn and recover | Stages 5–6 not launched. | Stopped at the exclusivity gate. |
| Distinguishable session loss and alternate-home isolation | Stages 7–8 not launched. | Stopped at the exclusivity gate. Private-home selection alone does not establish isolation under resume. |
| Claude equivalents | No Claude invocation. | Codex gate remains unsatisfied. |

The rejected resume occurred at `22:52:32.290Z`, between turn 3's native
start at `22:52:28.682Z` and completion at `22:52:33.932Z`. The final native
snapshot is `codex/evidence/coordinator-native-after-overlap.jsonl`, SHA-256
`b6efbb74f74bec6a90f11acd80a8f84e034b5b22827f16599fca0e0f5c571c6f`;
lines 36, 39, 47 and 51 bind that third turn. The rejection log's SHA-256 is
`7428a1f68ff81627d6a59540e663d21ebf284ac9a1498ad6d5192547a55fc14f`.
`coordinator-observation.json` records the local reconciliation and count.

## First-phase decision — historical stop point

Independent design/evidence review agreed: Codex has demonstrated a native
active-writer lock. It would be incorrect to describe this as absence of
locking, or to upgrade it to the complete expected-position guarantee in
[Agent Sessions](../design/workflow_lisp_agent_sessions.md). The automatic
gate remains `INCONCLUSIVE` because its parser has no qualified positive
contention diagnostic; the manual observation above records what the actual
diagnostic establishes without changing the saved gate result.

The next design decision is how to bind the expected position to acquisition
of exclusive continuation. Any narrower guarantee based on private storage
and cooperating writers must be explicit in the design, not inferred from
this test. No runtime implementation, adapter registration or Claude
campaign was started. Three attempts remain within the bound; the original
four-call recovery tail would not fit even if the gate were resolved.

The experiment is complete at its prescribed stop point; native-session
qualification remains partial. The JSON renderer was developed independently
and did not block this campaign.

## Observation-only continuation — Codex scenarios 5–8

The user's renewed “finish executing” instruction authorized the plan's
[continuation amendment](../plans/2026-10-13-native-session-cli-probe-plan.md#2026-10-13-continuation-amendment--observations-only).
It preserves the preceding stop disposition and permits four additional Codex
attempts plus an independent eight-attempt Claude campaign, for a cumulative
ceiling of 17. The four Codex attempts used the existing disposable session,
after checking ownership, quiescence, native file hash and its completed head.
No setup or overlap attempt was repeated. Codex has therefore consumed nine
attempts cumulatively: one original, four corrected and four diagnostic.

`/tmp/native-session-completion-20261013-vmronszg/codex-supplement.json`
records `DIAGNOSTICS_COMPLETE`, all four attempts quiescent, both staged auth
files removed and every prior evidence artifact unchanged. The coordinator's
independent reconciliation is `codex-coordinator-observation.json` in that
directory. New raw logs and native snapshots remain under
`/tmp/native-session-cli-corrected-20261013-puhfqktj/codex/evidence/`.
Saved receipts and adverse gate results were retained unchanged.

| Obligation / scenario | Observed evidence | Disposition / limit |
| --- | --- | --- |
| Cancel only after the tool starts; prove quiescence (5) | The entered marker matched the nonce; cancellation was requested, the CLI exited gracefully with 0 and all tracked descendants stopped. `native-after-interruption.jsonl`, SHA-256 `ec881b74ff9b18a2d81e5d9daf99e1b0ae7eeae9dfddeae7785a4a06a270aef3`, records turn `01a13790-3108-73c1-ab40-50eb751a1d0b` starting at line 54 without `task_complete`. | Cancellation and quiescence `OBSERVED`. The saved `interruption_marker_observed: false` is a harness false negative from requiring a negative exit code; the original receipt remains unchanged. Native interrupted-turn disposition remains `INCONCLUSIVE`. |
| Resume once after interruption (6) | `native-06-recovery.jsonl`, SHA-256 `cab572ab5429a20b9ff4b37a678f92cf88b3e196ec49ed19a9b56cd5d1aea981`, records a distinct turn `01a13790-4733-7e73-864c-d180863b0df8`: start at line 68, nonce user at 73, schema-2 final at 74 and completion at 78. Stderr reports a missing custom tool-call output. | New diagnostic turn completion `OBSERVED`; exact recovery `INCONCLUSIVE`. The earlier incomplete lifecycle is unresolved, so the parser rejects the full chain. This is neither reconciliation nor an exactly-once recovery proof. |
| Remove the exact backed-up native file and resume its locator (7) | Exit 1 with `no rollout found for thread id 01a13777-79ec-7511-8b2b-42a6111e33cf`, code `-32600`; no replacement/fallback native file. The sole deleted disposable file was restored with the same `cab572...981` hash before scenario 8. | Exact-locator loss rejection and byte-identical restoration `OBSERVED` for this attempt. The saved generic parser gate remains `INCONCLUSIVE`; no runtime recovery claim follows. |
| Resume the original locator from a fresh `CODEX_HOME` (8) | The alternate home contained no original session. Exit 1 with the same exact-locator error, no new native file, and matching `cab572...981` hashes for the first home before/after. Both staged auth files were removed. | Alternate-home rejection and unchanged original store `OBSERVED` for this attempt. This is bounded home-isolation evidence, not proof against every ambient fallback; the saved generic gate remains `INCONCLUSIVE`. |
| Atomic expected-position continuation | The previously observed active-writer lock is retained. Codex CLI `0.162.1` app-server schema reconnaissance found no expected completed-head parameter on `TurnStartParams` or `ThreadResumeParams`; `TurnSteerParams.expectedTurnId` targets an active turn. Schemas are under `/tmp/native-cli-schema-review-20261013-yn8anj1p/schema/`. | `INCONCLUSIVE`. These inspected surfaces provide no demonstrated atomic completed-head check; this does not establish impossibility across every provider surface. |

The coordinator record retains complete SHA-256 hashes and native line
references, including both exact-locator rejection logs. Prompt predecessor
text and a file precheck supply no provider-enforced compare-and-append
condition. Further ordinary continuation was not used to repair the unresolved
interrupted lifecycle.

## Claude continuation — all eight scenarios attempted

Claude CLI `2.1.296`, model selection `haiku`, used a separate disposable
workspace and private `CLAUDE_CONFIG_DIR`. The first call's saved
`claude/observations.json` stopped at an unsupported native format. Offline
correction recognized the native `StructuredOutput` attachment and matching
`toolEndsTurn` result; the call was not repeated. The second call wrote its
nonce exactly and reached schema-2 completion, but paused the driver on a
synthetic assistant record inserted during resume. Bounded offline recognition
of that native padding allowed scenarios 3–8 without repeating call 2.

The original receipt and intermediate `claude-supplement.json` remain
unchanged. `claude-final-supplement.json` under
`/tmp/native-session-completion-20261013-vmronszg/` records
`DIAGNOSTICS_COMPLETE`, eight cumulative attempts and no remaining scenarios.
All eight attempts reached quiescence; staged auth in both homes was removed,
and prior evidence artifacts remained unchanged. Raw evidence is in that
directory's `claude/evidence/` subdirectory. The session locator is
`1930ae6b-5267-4eec-b1e1-b430dad86844`.

| Obligation / scenario | Observed evidence | Disposition / limit |
| --- | --- | --- |
| Fresh review, schema 1 and native completion without stdout (1) | Workspace unchanged. `native-01-review.jsonl`, SHA-256 `1358a3d6dbc222a4cbe2eb47e5f8746f81cd7f4aaf04ad912d277f333a8a900e`, binds nonce user at line 3 to the structured result at 20, matching attachment at 21 and native terminal tool result at 22; prompt ID `2ea27655-1d07-4f9a-a13d-58e52beb685e`. | Result binding and no edits `OBSERVED` by offline reinspection. The original `INCONCLUSIVE` receipt remains unchanged; substantive review is not independently proved. |
| Same-session schema change and exact workspace write (2) | `native-supplement-02-write.jsonl`, SHA-256 `b0864fb875cdec5b545c5ae1355dc721cdac0df8ec868664f9201313fab05732`, binds user at line 28 to schema-2 result/attachment/end at 43–45; prompt ID `c90b3f66-e42d-4487-9e84-f0a45a3f6784`. The requested nonce was written exactly. A stale schema-1 attempt at 39–40 was rejected natively before the CLI produced the valid result. | `OBSERVED` by offline reinspection. Native resume padding at line 27 is recognized only under bounded model/type/ancestry conditions; the intermediate adverse receipt remains unchanged. |
| Exclusive simultaneous continuation (3–4) | The held tool barrier and live process overlap were observed. `native-supplement-03-04-overlap.jsonl`, SHA-256 `d464b894c4d5b69cf18a1816d2e7231abd4348c608934a8411ceb3958e81d61d`, contains call-3 nonce user at line 52, prompt ID `743e6c2a-f3c2-4dac-b89a-88fa41300988`, and competing call-4 user at 61, prompt ID `7d695b30-89f2-4036-9328-9507c2712d97`, before either completion. The later native store places the actual held-tool result at 63 and terminal results at 67/72. Both CLI attempts exited 0. | `NOT_OBSERVED`: these direct resumes accepted overlapping native appends. This is adverse evidence for this CLI path/version, not merely absence of a recognized contention error. |
| Cancel after marker and establish quiescence (5) | The nonce marker was observed, cancellation requested, CLI exit `-9`, and all tracked descendants stopped. `native-after-interruption.jsonl` SHA-256 `2979f08befbf0ebf713b57d8ef8ae6f5101c5110e83bce7f1d798e88b0915fec` retains the partial native state. | Cancellation and quiescence `OBSERVED`; exact interrupted-turn disposition remains `INCONCLUSIVE`. |
| One diagnostic resume after interruption (6) | CLI exit 0 and quiescence. `native-06-recovery.jsonl`, SHA-256 `702f34c9385b2024f222986d9517c4f803c8ec5b00d778f94f181f7cfdd5d0b5`, inserts an unknown-outcome tool result at line 87, a new nonce user at 89 and result/attachment/end at 92–94. The full lineage parser still rejects unsupported/unordered ancestry after overlapping branches and interruption. | New local result/completion `OBSERVED`; exact recovery `INCONCLUSIVE`. A later structured result does not establish reconciliation or a qualified current head. No extra continuation attempted to repair it. |
| Delete the exact disposable file and resume the original locator (7) | Exit 1 with `No conversation found with session ID: 1930ae6b-5267-4eec-b1e1-b430dad86844`; no replacement/fallback native file. Restoration matches the backed-up `702f34...0b5` hash before scenario 8. | Exact-locator loss rejection and byte-identical restoration `OBSERVED` for this attempt; the saved generic gate remains `INCONCLUSIVE`. |
| Resume from a fresh `CLAUDE_CONFIG_DIR` (8) | Exit 1 with the same exact-locator diagnostic; alternate home started without the session and produced no fallback native session. First-home before/after hashes both equal `702f34...0b5`. Both staged auth files removed. | Alternate-home rejection and unchanged original store `OBSERVED` for this attempt; no universal ambient-fallback guarantee follows. The saved generic gate remains `INCONCLUSIVE`. |

## Final accounting, verification and qualification limits

| Campaign | Counted CLI/model attempts |
| --- | --- |
| Original Codex inconclusive campaign | 1 |
| Corrected Codex campaign, including rejected concurrent resume | 4 |
| Codex diagnostic continuation, scenarios 5–8 | 4 |
| Claude campaign across three retained receipts | 8 |
| **Cumulative total / authorized ceiling** | **17 / 17** |

Failed/rejected/interrupted/alternate-home attempts are included. Offline
parser reinspections, local schema/help reconnaissance and process/file checks
made no model requests. No further calls are authorized under the exhausted
17-attempt ceiling. No scenario was repeated during the observation-only
continuation; the earlier fresh Codex campaign remains counted.

Continuation helper corrections cover Codex graceful cancellation after a
matched marker, Claude native structured-output closure, corresponding overlap
closure handling and bounded synthetic resume padding. Unknown or inconsistent
native ancestry still fails closed; saved receipts are not rewritten.
Fresh coordinator verification collected **125 tests** and ran the three
experiment modules with `pytest -q -n 16 --dist=worksteal`: **125 passed in
4.40s**. Collection and `py_compile` both exited 0. The receipt
`/tmp/native-session-completion-20261013-vmronszg/verification-closeout.json`
retains exact commands, source hashes and logs. The passing suite includes the
standalone fake-CLI end-to-end path; it verifies the probe, not live-provider
capabilities. No broad runtime suite or Orchestrator workflow smoke was run:
this experiment changes no runtime, DSL, workflow or prompt assets.

Independent final evidence review found no critical evidence error and
confirmed the adverse Claude overlap. The coordinator independently verified
attempt counts, current tested source hashes, dead process identities, auth
absence and unchanged receipts; complete raw hashes and native references are
retained in
`/tmp/native-session-completion-20261013-vmronszg/completion-coordinator-observation.json`.
The bounded observation execution is complete. Qualification
remains unavailable: Codex has no demonstrated atomic expected-position
condition on the inspected surfaces, Claude's tested continuation accepts
overlapping appends, and neither provider has exact interrupted-turn recovery
evidence. PQ-1a still owns mechanism qualification; these observations neither
select implementation nor weaken the Agent Sessions guarantee.
