# Native Session CLI Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task. The user subsequently authorized execution with “finish executing the plan”; that authorization persists. No commit is requested.

**Goal:** Prepare an independent, bounded CLI experiment that can establish or falsify native-session prerequisites before any Orchestrator integration.

**Evidence:** [Preparation report](../reports/2026-10-13-native-session-cli-probe.md) and [live execution report](../reports/2026-10-13-native-session-cli-live.md). Local fake-process checks do not qualify either provider.

**Execution status:** Bounded observation execution is complete after independent evidence review and coordinator verification: **17 cumulative CLI/model attempts, nine Codex and eight Claude**. No further calls are authorized under the exhausted ceiling. Codex active-writer exclusion is observed; its atomic expected-position condition remains unqualified. Claude accepted overlapping native appends (`NOT_OBSERVED` for exclusive continuation). Exact interrupted-turn recovery remains inconclusive for both providers. Loss and alternate-home attempts rejected the exact locators, originals were restored byte-for-byte, all continuation attempts reached quiescence and copied auth was removed. The original and intermediate adverse receipts remain historical evidence. Preparation passed 92 tests, the process-race correction passed 98, and the final continuation checks collected/passed 125 tests with compile exit 0. The live report owns full evidence and limits; execution completion does not qualify native sessions.

**Architecture:** One stdlib entry point invokes disposable native sessions directly, retains raw native evidence, and reports observations against explicit obligations. Codex and Claude are separate campaigns, with Codex first. Default preparation performs no subprocess calls or credential access; paid execution requires a separate explicit provider opt-in after authorization. No Orchestrator imports, adapters, registration, runtime edits, session manager, or qualification framework.

**Tech Stack:** Python stdlib, pytest, locally installed provider CLIs, synthetic native fixtures and fake child processes.

**Tradeoff:** Explicit provider-specific parsing makes new CLI formats/providers require deliberate parser work. This probe cannot prove runtime memo recovery, compiler composition, or exclusion of external writers through a run lock alone.

The fixed campaign remains in one script even where it exceeds the approximate
500-line split threshold. Native parsing and Linux process cleanup have their
own concrete modules; adding a separate campaign abstraction would not help
this single experiment.

## Authority and scope

- Start from [documentation routing](../index.md), [design routing](../design/README.md), and [capability status](../capability_status_matrix.md): agent sessions are proposed, not implemented.
- [Agent Sessions](../design/workflow_lisp_agent_sessions.md), especially current turn contracts, native completion/position, exclusive continuation and quiescence, supplies the obligations.
- [PQ-1a](2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) remains the sole mechanism-qualification owner. This experiment contributes evidence; it selects neither implementation nor a DSL target and cannot qualify the entire mechanism.
- Preserve all unrelated dirty work. Touch only the probe, its tests/fixtures, this plan and its report, plus a discovery link from PQ-1a. No production call sites, configuration, exports or `.orc` consumers change.
- Preparation, local fake-process verification and the requested Codex execution are authorized. Codex uses explicit `gpt-6-luna` and effort `low`; Claude `haiku` was a later candidate behind the original Codex gates. The continuation amendment authorizes its independent observations, never an automatic fallback. Do not infer prices from names or caches.

## 2026-10-13 continuation amendment — observations only

After the first phase was reported as partial, the user renewed execution with
“finish executing”. This amendment changes the experiment's stopping sequence,
not the [Agent Sessions](../design/workflow_lisp_agent_sessions.md) contract or
PQ-1a qualification. Preserve the original paused campaign, all five counted
attempts, raw evidence and saved gate results. In particular,
`exclusive_continuation` remains `INCONCLUSIVE`: the observed active-writer
lock does not establish an atomic expected-position check.

The renewed ceiling is **12 additional CLI/model attempts: four Codex and
eight Claude**, for at most **17 attempts cumulatively**. Failed launch,
rejection, interruption and alternate-home attempts all count. This explicitly
extends the earlier cumulative eight-attempt Codex ceiling; it does not reset
the five-attempt history. Retain the 180-second per-attempt deadline, pinned
models/policies, no automatic retry or fallback, private disposable storage,
bounded cleanup and authentication removal. Local provider version/help/schema
commands are limited to six per provider and 30 seconds each, with no model
request; record them separately. Local process/file checks also send no model
request; never use either category to hide a model attempt.

Complete Codex scenarios 5–8 using the existing disposable session after
rechecking ownership, quiescence and its exact native file/current head against
the retained coordinator evidence. Do not spend calls repeating scenarios 1–4.
Then execute the eight Claude scenarios as a separate low-cost `haiku`
campaign. A capability failure or inconclusive observation stops qualification,
but need not stop another safe, independent observation. Missing native
locator/file prerequisites leave dependent scenarios unrun with reasons;
they never authorize inventing a locator, guessing a session or resetting
history to obtain a pass.

Reuse the existing process, containment, snapshot and recovery-tail operations
in a bounded experiment driver. Separate permission to perform these diagnostic
observations from their evidence classifications; never supply a fabricated
`OBSERVED` gate to `_run_recovery_tail`, overwrite an adverse result or add a
runtime bypass/feature flag. Invocation 6 is one deliberately new diagnostic
resume after interruption, not reconciliation or permission to replay an
unresolved Agent turn. If its native outcome remains uncertain, retain that
finding; scenarios 7–8 may still inspect session loss and home isolation once
all writers are quiescent and the disposable locator/file is unambiguous. Do
not report an uncertain predecessor as established, and do not issue further
ordinary continuation calls to repair it.

Unknown process ownership, unproved quiescence, unsafe paths, compromised
isolation or unsupported authentication still stop affected provider work.
Preserve native evidence before exact-file deletion, restore only after
quiescence, and verify the restoration before alternate-home testing. If the
installed CLI offers no provider-enforced expected-position condition, record
that feasibility gap; prompt text and a precheck cannot fill it. Completion
means all feasible authorized scenarios have observations or explicit safety/
prerequisite dispositions, not that all capabilities are observed.

**Tradeoff:** This obtains independent failure/recovery/isolation evidence
without repeating paid setup. It cannot be reported as one gate-passing
qualification campaign or establish the architectural guarantee from private
storage alone. The original gate and eight-call protocol below remain the
historical baseline; this amendment supersedes only their spending stop and
cross-provider ordering for this bounded continuation.

## Files and responsibilities

| Path | Responsibility |
| --- | --- |
| `scripts/experiments/native_session_cli_probe.py` | Prepare scenarios, opt-in execution, bounded process lifecycle, disposable storage, native evidence inspection and observation table |
| `scripts/experiments/native_session_cli_evidence.py` | Concrete native parsing and native overlap evidence, no plugin abstraction |
| `scripts/experiments/native_session_cli_process.py` | Concrete Linux child tracking and termination, including adopted descendants; separate only to keep modules bounded |
| `tests/experiments/test_native_session_cli_probe.py`, `test_native_session_cli_evidence.py`, `test_native_session_cli_process.py` | Behavioral tests, small generated native fixtures and stdlib fake child CLI; separate lifecycle and native parser regressions; no literal prompt-text assertions |
| `docs/reports/2026-10-13-native-session-cli-probe.md` | Historical preparation protocol, exact command templates, local verification evidence and then-unresolved provider fields |
| `docs/reports/2026-10-13-native-session-cli-live.md` | Historical campaign receipts, continuation observations, cumulative attempt counts and final qualification limits |

## Evidence and stop rules

The original campaign's gating and spending sequence below is the historical
baseline. The continuation amendment above supersedes its stop/order rules
only for the authorized diagnostic observations; evidence standards and
qualification gates remain in force.

For every obligation retain `OBSERVED`, `NOT_OBSERVED` or `INCONCLUSIVE`, the exact native locator/record references, raw-file hashes, invocation identity, expected/observed relationship and limitation. Unrun rows are `INCONCLUSIVE` with `not run`; `NOT_OBSERVED` requires an executed test with enough evidence to establish the property was absent. Partial, malformed, ambiguous or unsupported native records fail closed. Preserve raw evidence privately and never upgrade it from assistant text, stdout events, exit zero or harness-written receipts.

The native proof must bind session, exact submitted prompt nonce, native turn identity, final response nonce, native completion marker and predecessor/current position. Matching text alone is insufficient. Codex schema reconnaissance found `session_meta.id`, `event_msg.task_started.turn_id`, `turn_context.turn_id`, `event_msg.task_complete.{turn_id,last_agent_message}` and `response_item` messages. Disk `task_complete` is not stdout `turn.completed`; establish relationships from the store, not similar event names. Claude schema reconnaissance found user `uuid,parentUuid,sessionId,promptId,message.content` and assistant `uuid,parentUuid,sessionId,message.stop_reason,content`; `end_turn` was observed in an existing record. These are schema hints, not experiment evidence. Claude binding must prove ancestry through `parentUuid` to the unique nonce user and a corresponding native end marker; structured output may be a tool block, so do not equate it to final text. Claude need not expose Codex field names. If the prompt-to-turn or result-to-completion relationship cannot be established, record `INCONCLUSIVE` and stop.

Gate exact native completion after invocations 1–2, then exclusive continuation after 3–4. Missing proof or adverse evidence produces `INCONCLUSIVE` or `REQUIRES_DESIGN` disposition and halts further provider work. There is no automatic PASS, qualification narrative or adapter enablement. A coordinator reviews the table explicitly. Codex must satisfy these gates before separately authorized Claude work uses the same script and sequence. Failed/inconclusive gates block runtime integration and require design review.

Additional Codex schema reconnaissance found native `event_msg.item_completed` records carrying `thread_id`, `turn_id` and an `item` of type `UserMessage` or `AgentMessage`. When present, these can bind message content directly to a turn; their existence in another session is not evidence that this experiment's CLI path emits them. Missing bindings remain inconclusive.

A run writer lock plus a position precheck protects cooperating harness writers only. The concurrent test must bypass that harness serialization. Two ordered successes do not by themselves prove exclusive expected-position continuation. Absent native exclusion/fencing, do not claim the present design satisfied: any alternative limited to private storage and excluding all direct CLI writers requires an explicit design scope decision. Do not silently weaken the guarantee.

## Disposable execution protocol

Use a temporary trivial workspace outside the repository, with no project instructions or hooks. Make provider homes and raw evidence directories private (`0700`) outside the repository. Snapshot workspace contents around each turn; exclude only explicitly named harness files. Copy only the provider's authentication file during authorized execution, with restrictive permissions; never copy config, hooks, plugins, real sessions or historical logs. Remove copied auth in `finally`, including failure paths. Do not print secrets or persist raw environment/auth contents. Resolve credential filename/auth mechanism and provider-home behavior before copying; unsupported authentication/isolation is a stop, not permission to copy an entire home.

Use explicit model, fixed effective tool/security policy and turn-local schemas. Review's instruction to change nothing is task text; execution uses the same write-capable policy. Ignore inherited provider configuration, hooks, MCP/plugin settings and ambient credential fallbacks. Confirm that chosen CLI flags actually enforce that isolation. Preserve only this experiment's native records; never delete/copy real logs. Record versions and sanitized command arguments, invocation count, durations and any usage reported without inventing price estimates.

Maximum **8 model invocations per provider**, with an execution deadline of at most **180 seconds per invocation**, including failed/resume/alternate-home attempts. Bounded process cleanup is measured separately and can extend elapsed time past that deadline. These limits are not a guaranteed monetary cap; API list prices do not establish account-credit billing. No automatic retry, fallback model, repair prompt or ninth invocation. Process-group cleanup must quiesce child tools and wait for termination; inability to prove quiescence stops subsequent appends. Run any long authorized campaign under tmux with the tmux skill.

| Invocation | Action and decisive evidence |
| --- | --- |
| 1 | Fresh session: review a trivial file, require no edits and schema 1 with unique prompt/result nonce. Check workspace equality. Discover session and completion from native storage with stdout unavailable to the evidence parser. |
| 2 | Resume the same native session with a different schema 2, fresh nonce and explicit instruction to write that nonce to a designated workspace file. Check exact file content, current schema/result and native prompt → turn → completion/result binding. A schema-1 result cannot satisfy this turn. Apply completion gate now. |
| 3–4 | Launch two direct resumes of that same thread against the same recorded predecessor. Invocation 3 calls a tool that writes an entered marker and sleeps behind a bounded barrier. Only after observing the tool marker while 3 remains alive, launch 4; keep 3 held until 4's attempt is observable or the bound expires. Record process timing and native tool/start/append evidence to establish the overlap window. Missing marker/overlap, no native contention evidence, both competing appends or ambiguous serialized behavior cannot pass. Apply exclusivity gate before continuing. |
| 5 | Resume with tool instructions that write a unique entered marker then sleep. Kill the CLI process group only after that marker; verify all descendants stop. Inspect native store for partial/completed/interrupted state without consulting stdout as completion authority. |
| 6 | After proven quiescence, explicitly resume once and inspect whether the native store reconciles or starts another turn, including possible stale completion/results. Record exact behavior; never call replay an exactly-once recovery proof. Stop if outcome/position remains uncertain. |
| 7 | With no active writer, back up only the exact disposable session file, record its hash, validate containment and reject symlinks, then delete only that file and attempt one resume. Capture error, replacement session or fallback evidence. Never remove a directory tree or a real session; a recreated session does not prove safe continuation. |
| 8 | Use a second fresh private provider home containing only separately authorized auth and no session; attempt resume of the original locator. Record whether the first home's records or any fallback session are used. This exercises `CODEX_HOME` / `CLAUDE_CONFIG_DIR` isolation; an assumed environment variable is not proof. |

Deleting a session in invocation 7 must not contaminate the alternate-home test: preserve the backup, restore the disposable first-home file safely while quiescent before invocation 8, and prove home 2 starts without it. Restoration is a local file operation, never a model call. Remaining tests are skipped with reasons if an earlier gate stops the campaign.

Known CLI reconnaissance: Codex 0.162.1 provides `exec`/`resume`, `--json`, `--output-schema`, `--ignore-user-config`; resume lacks `-s`, so use explicit `-c sandbox_mode=workspace-write -c approval_policy=never`. Pin `gpt-6-luna` and effort `low` explicitly. Claude 2.1.296 provides `--output-format stream-json --verbose --json-schema --resume --model --setting-sources --strict-mcp-config`; official documentation confirms `CLAUDE_CONFIG_DIR` relocates settings/session history/plugins, and `.credentials.json` exists without having been read/copied. Confirm exact empty-config/MCP arguments; invocation 8 must test effective isolation. Existing schema inspection and help/version observations are not provider qualification. No further subprocess is part of default prepare.

## Task 1 — Prepare bounded execution and local tests

**Owner:** Implementation / code, Luna 6 xhigh; escalate bounded implementation failures to Sol 6.1 high. Files: probe and test module above.

- [x] Write focused failing tests for default prepare and explicit execution admission: preparation makes no subprocess call and never opens/copies credentials; provider/model must be explicit for real execution; count includes failed attempts; no retry; timeout quiesces child processes.
- [x] Run the new narrow selectors, then implement only the stdlib argument parsing, scenario preparation and process/file lifecycle required by the protocol. Suggested interface: `--provider codex|claude`, optional `--execute --model MODEL`, with prepare as default; execution remains an operator action after authorization, not a test step.
- [x] Test disposable path containment, symlink rejection, backup/restore and deletion scope with sentinel files outside the experiment home. Test auth cleanup after successful and failed child execution without any real credentials.
- [x] Keep a hard eight-invocation cap and 180-second upper bound; timeouts cannot cause a hidden follow-up. Use the same top-level sequence for both providers and concrete command construction per provider.

## Task 2 — Implement native evidence and decisive scenarios

**Owner:** Implementation / code, same Luna agent. Files: probe, optional parsing companion and test module.

- [x] Add synthetic native records with competing turns, stale final messages, nonce mismatch, missing native IDs, partial JSONL and completion for the wrong turn. Assert each refuses exact-completion evidence even with exit zero and plausible stdout.
- [x] Implement exact schema/nonce/session/turn/completion binding for understood native formats. Unknown Claude formats remain explicitly inconclusive; do not manufacture a success fixture from an unverified guess about provider behavior.
- [x] Exercise deterministic overlap and kill-after-marker with a local Python fake CLI process. Test that an absent marker, absent exclusion, ambiguous completion or unquiesced child closes the spending gate and leaves later scenarios unrun.
- [x] Test native-only recovery with captured stdout deleted or inaccessible, schema change across resumes, session-file loss, and second-home isolation using generated stores. Fake evidence proves probe behavior, never real provider capability.
- [x] Run one subprocess end-to-end fake-CLI campaign through the same public probe entrypoint and verify its observation table, budget and evidence paths. No network or provider credentials.

## Task 3 — Prepare report, independent review and coordinator verification

**Owners:** Implementation / report preparation, Luna; independent Review / code and plan, Sol 6.1 high; integration and final verification, coordinator.

- [x] Create the report with protocol/command templates, versions already observed, explicit unresolved auth/model/format details and the obligation table. Every live-provider row starts `INCONCLUSIVE — not run; authorization pending`. Distinguish local fake-test results from live evidence and leave PQ-1 qualification unchanged.
- [x] Run `pytest --collect-only -q tests/experiments/test_native_session_cli_probe.py tests/experiments/test_native_session_cli_evidence.py tests/experiments/test_native_session_cli_process.py`, then `pytest -q tests/experiments/test_native_session_cli_probe.py tests/experiments/test_native_session_cli_evidence.py tests/experiments/test_native_session_cli_process.py`. Ensure the probe module includes the fake-CLI end-to-end scenario; cite actual output in the report.
- [x] Run `python scripts/experiments/native_session_cli_probe.py --provider codex` and the same command with `--provider claude`; both must prepare artifacts without launching any subprocess or reading credentials. Record exact prepared-artifact paths and commands.
- [x] Independent Sol reviewer checks native evidence misbinding, gate ordering, direct external writer limitation, isolation, destructive-path containment, count/time bounds and missing/partial records. Return corrections to the implementer; architectural questions return to Design, Astra 6 xhigh.
- [x] Coordinator inspects the complete scoped diff and fresh verification output. Reuse still-valid test evidence; rerun after relevant corrections. No broad runtime suite or Orchestrator smoke is necessary: no runtime/workflow/prompt assets are changed, and the standalone fake-CLI end-to-end check covers this experiment's public path.
- [x] Finish preparation with the report and concrete sanitized live command ready for review.
- [x] Record subsequent user authorization and launch the bounded Codex campaign; retain its actual evidence and stop disposition in the live report. Starting the campaign does not qualify native sessions or authorize adapter registration.

## Task 4 — Complete the authorized observation-only continuation

**Owners:** bounded code/parser revision, independent review, documentation
revision and final coordinator verification within the continuation amendment.

- [x] Preserve the original five-attempt history and verify the existing Codex session's ownership, quiescence, exact native file and completed head before continuing.
- [x] Execute Codex scenarios 5–8 once each; retain their raw evidence, unresolved interrupted lifecycle, loss/isolation observations, restoration hashes and unchanged saved gates. Nine Codex attempts total.
- [x] Inspect bounded local Codex help/schema surfaces for an expected-position condition; record the scoped feasibility gap without weakening the design guarantee.
- [x] Finish the independent Claude campaign without repeating its first attempt; record every feasible authorized scenario or explicit safety/prerequisite disposition. Eight Claude attempts, including overlapping appends and inconclusive recovery, bring the global total to 17.
- [x] Complete independent review and fresh coordinator verification of relevant parser/process checks and the standalone fake-CLI end-to-end path. Final evidence review found no critical error; 125 tests passed, collection/compile exited 0, and the coordinator checked counts, current source hashes, process termination, auth absence and unchanged receipts.
- [x] Reconcile the live report and PQ-1a pointer with final counts, cleanup evidence and obligation dispositions. Bounded observation execution is complete. Native-session qualification and adapter enablement remain unavailable; no calls remain authorized under the 17-attempt ceiling.
