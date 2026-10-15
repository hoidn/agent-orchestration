# Native Session CLI Probe Preparation

**Status at preparation:** Implemented, independently reviewed and locally verified; no live provider was run during preparation. The user subsequently authorized execution. Current observations and stop reasons live in the [live execution report](2026-10-13-native-session-cli-live.md); the table below preserves the earlier preparation state.

This standalone probe prepares a bounded comparison of native-session continuation in Codex and Claude before any Orchestrator integration. It uses only Python's standard library at runtime. Preparation creates a private disposable workspace, turn schemas, evidence directories, and a manifest. It does not spawn a subprocess, resolve a provider executable, inspect credentials, or copy authentication. Real execution requires `--execute` and an explicit `--model`; authorization was pending when this preparation report was written. Preparation and local fake-process testing are not provider evidence.

The [probe plan](../plans/2026-10-13-native-session-cli-probe-plan.md) implements an experiment against the proposed [Agent Sessions obligations](../design/workflow_lisp_agent_sessions.md). [PQ-1a](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns) remains the sole mechanism-qualification owner. The entry point is [native_session_cli_probe.py](../../scripts/experiments/native_session_cli_probe.py).

The probe limits model attempts to eight per provider, counts failed launch attempts, enforces a finite timeout no greater than 180 seconds for each call, and does not retry. These are invocation bounds, not a guaranteed monetary cap. A bounded `--version` command runs only after explicit execution is selected; its output is reported separately and does not count as a model call. It records the actual installed CLI version in a future authorized run rather than treating prior help/version reconnaissance as that campaign's version.

Execution requires Linux `/proc`, subreaper support and pidfd signaling. The execution deadline and bounded process cleanup are recorded separately; cleanup can extend elapsed time beyond the call's deadline. `provider_stopped_monotonic` is the time a poll observed the CLI's exit, not its exact kernel exit time or proof that its tools stopped. Only the separate descendant checks establish quiescence; failure to establish it blocks subsequent turns.

## Command and isolation contract

The following are argument templates; `PROMPT`, `SCHEMA`, `MODEL`, and `SESSION` are per-call values. Codex resumes use the same `exec` entry point because its inspected `resume` command did not expose a sandbox flag. The probe pins the sandbox and approval policy on every Codex call:

```text
codex exec [resume SESSION] --json --output-schema SCHEMA --ignore-user-config --ignore-rules --skip-git-repo-check -m MODEL -c 'sandbox_mode="workspace-write"' -c 'approval_policy="never"' -c 'model_reasoning_effort="low"' PROMPT
```

Claude uses the private `CLAUDE_CONFIG_DIR`, an empty setting-source list, disabled hooks and slash commands, strict empty MCP configuration, and a fixed Bash tool policy for both review and write turns:

```text
claude -p PROMPT --output-format stream-json --verbose [--resume SESSION] --json-schema SCHEMA --model MODEL --effort low --setting-sources '' --settings '{"disableAllHooks":true}' --strict-mcp-config --mcp-config '{"mcpServers":{}}' --disable-slash-commands --tools Bash --allowedTools Bash --permission-mode acceptEdits
```

The disposable workspace and provider homes are outside the repository and use private directory permissions. The child environment is an allowlist, with a sanitized `PATH` that retains the resolved CLI's executable directory. During an authorized run, the probe stages only Codex `~/.codex/auth.json` or Claude `~/.claude/.credentials.json` into that private home and removes the copy in cleanup. It never copies provider configuration, plugins, hooks, or session history. Failure to find the expected credential stops execution. The actual credential files and provider accounts have not been inspected or used in this preparation.

Current reconnaissance identified Codex 0.162.1 and Claude 2.1.296 in an earlier read-only CLI inspection. Those are not campaign versions: the campaign records fresh `--version` output if and when it is authorized. The prepared candidates are Codex `gpt-6-luna` at low effort and Claude `haiku` at low effort; the CLI does not select either automatically. No price or billing estimate is inferred.

## Native evidence and stop rules

For Codex, the parser reads only the isolated `sessions/**/rollout-*.jsonl` store and snapshots the exact bytes to private evidence before parsing. Schema reconnaissance parsed local JSONL records for structure and identified `session_meta.id`, `event_msg` task start/completion fields, and `item_completed` records that carry `thread_id`, `turn_id`, and a `UserMessage` or `AgentMessage`. The currently understood message shape uses user text blocks with `text` and `text_elements`, and final assistant text blocks of type `Text` with phase `final_answer`. No transcript message text was reproduced or copied into this report. Missing, malformed, duplicated, or ambiguous native records remain inconclusive.

For Claude, the parser searches only the isolated `projects/**/*.jsonl` store, rejects ambiguity, and follows native user/assistant parent lineage within the expected session. Schema reconnaissance found user `uuid`, `parentUuid`, `sessionId`, `promptId`, and `message.content`, with corresponding assistant lineage, content, and stop fields. This format has not been qualified against a probe execution; unsupported or ambiguous structured-result shapes remain inconclusive.

The exact-completion gate requires the native session, exact submitted nonce, current turn, exact response schema and nonce, final native completion, and expected predecessor relationship. The review and write schemas have distinct required fields and reject extra properties. The harness never uses stdout or exit-zero alone as completion proof. For overlapping resumes, only a recognized native contention/fencing observation could establish exclusive continuation. The current probe has no qualified contention diagnostic, and it does not infer exclusion from a generic nonzero exit or two ordered successful resumes. Two distinct native user appends against the same recorded predecessor establish adverse evidence (`NOT_OBSERVED`) only when native records show the first turn still incomplete at the second append and process/tool observations establish live overlap. Overlapping processes whose native turns are serialized remain `INCONCLUSIVE`. Unknown diagnostics also stop as `INCONCLUSIVE`.

Consequently, authorized campaigns will stop after invocation 4 unless the native exclusion gate can be supported by independently reviewed provider evidence. Invocations 5–8 are implemented and locally exercised through an internal synthetic gate, but there is no public option to bypass the gate. Those synthetic results prove only the harness lifecycle and do not establish real interruption, recovery, session-loss, or alternate-home behavior.

The concrete Codex command awaiting authorization is:

```sh
python scripts/experiments/native_session_cli_probe.py --provider codex --execute --model gpt-6-luna
```

It uses low effort and the default 180-second execution deadline. The current gate limits this first campaign to at most four model attempts, stopping earlier if exact completion cannot be established. Claude is a separate later authorization; neither provider has been launched by this preparation.

## Prepared live-observation table

Each row is a provider obligation. No row below has a live invocation identity, native record reference, or raw hash because no live provider call has occurred.

| Provider scenario | Status | Evidence / limitation |
| --- | --- | --- |
| Codex 1: fresh read-only review, schema 1, nonce, unchanged workspace | `INCONCLUSIVE — not run; authorization pending` | No live invocation; no native evidence. |
| Codex 2: same-session resume, schema 2, exact workspace write and predecessor | `INCONCLUSIVE — not run; authorization pending` | No live invocation; no native evidence. |
| Codex 3–4: overlapping resumes against the same predecessor; native exclusion or adverse append | `INCONCLUSIVE — not run; authorization pending` | No live invocation; no native evidence. Unknown contention formats cannot pass. |
| Codex 5: interrupt after marker and prove process-tree quiescence | `INCONCLUSIVE — not run; authorization pending` | Blocked behind exact-completion and exclusivity gates. |
| Codex 6: one resume after interruption | `INCONCLUSIVE — not run; authorization pending` | Blocked behind earlier gates. |
| Codex 7: delete only the backed-up disposable native file and attempt resume | `INCONCLUSIVE — not run; authorization pending` | Blocked behind earlier gates. |
| Codex 8: after restoring the original file, resume from a second isolated home | `INCONCLUSIVE — not run; authorization pending` | Restoration must be verified before this call; blocked behind earlier gates. |
| Claude 1–2: fresh review and exact same-session schema-changing resume | `INCONCLUSIVE — not run; authorization pending` | No live invocation; exact native result shape still requires observed evidence. |
| Claude 3–4: overlapping resumes against the same predecessor | `INCONCLUSIVE — not run; authorization pending` | No live invocation; contention/fencing format is unqualified. |
| Claude 5: interrupt after marker and prove process-tree quiescence | `INCONCLUSIVE — not run; authorization pending` | Blocked behind earlier gates. |
| Claude 6: one resume after interruption | `INCONCLUSIVE — not run; authorization pending` | Blocked behind earlier gates. |
| Claude 7: delete only the backed-up disposable native file and attempt resume | `INCONCLUSIVE — not run; authorization pending` | Blocked behind earlier gates. |
| Claude 8: after restoring the original file, resume from a second isolated home | `INCONCLUSIVE — not run; authorization pending` | Restoration must be verified before this call; blocked behind earlier gates. |

When the runner stops early, `observations.json` lists every remaining ordinal after the actual invocation count through 8 with `not_run: true`; launched attempts have their own invocation rows, including failed attempts. This keeps skipped work distinct from executed but inconclusive evidence.

## Local verification

Local verification uses a generated fake CLI that answers `--version`, appends synthetic native records in the inspected Codex shape, and runs bounded fake tool processes. Sentinel credentials used by tests are fabricated strings in temporary test homes. These checks do not access real credentials, run installed providers, or establish provider behavior.

Coordinator verification collected **92 tests** and ran **92 passed in 12.72s**. All six source/test modules also passed `python -m py_compile`. The commands were:

```sh
python -m pytest --collect-only -q tests/experiments/test_native_session_cli_probe.py tests/experiments/test_native_session_cli_evidence.py tests/experiments/test_native_session_cli_process.py
python -m pytest -q tests/experiments/test_native_session_cli_probe.py tests/experiments/test_native_session_cli_evidence.py tests/experiments/test_native_session_cli_process.py
python -m py_compile scripts/experiments/native_session_cli_probe.py scripts/experiments/native_session_cli_evidence.py scripts/experiments/native_session_cli_process.py tests/experiments/test_native_session_cli_probe.py tests/experiments/test_native_session_cli_evidence.py tests/experiments/test_native_session_cli_process.py
```

The tests include a fake-CLI campaign through the public script entry point, schema changes, native-only evidence, ambiguous records, concurrent deadlines, process cleanup, session backup/restore, and alternate-home fallback. Independent review returned PASS for contract compliance and code quality after corrections, including rejection of duplicate native IDs in partial append observations. This review accepts the experiment harness, not provider viability.

Local command logs and exit codes are under `/tmp/native-session-probe-preparation-20261013-7566dtu5/`: `verification-final.json`, `final-collection.log`, `final-tests.log`, `final-compile.log`, and the earlier `verification.json` with the two preparation runs. These temporary artifacts are local evidence, not durable repository attachments.

| Preparation | Command | Artifact directory |
| --- | --- | --- |
| Codex | `python scripts/experiments/native_session_cli_probe.py --provider codex` — exit 0 | `/tmp/native-session-cli-probe-8ln_6jn_` |
| Claude | `python scripts/experiments/native_session_cli_probe.py --provider claude` — exit 0 | `/tmp/native-session-cli-probe-l1zx0oxh` |

Both roots were mode `0700` and contained the expected manifest, schemas, and workspace files. Their `provider-home` directories contained no files. An in-process audit test also forbids `Popen`, auth-file open/read, and copy operations during `main()` preparation.

This report contributes no qualification and leaves the PQ-1 owner status unchanged. Real execution requires separate provider/model authorization. No provider/model call, real credential read or copy, or commit was performed while preparing this artifact.

No broad runtime suite or Orchestrator smoke was run: the change adds an isolated experiment and documentation, without changing runtime, provider registration or workflow assets. The fake-CLI integration covers the experiment's public entry point. Native format support and native guarantees remain unqualified until the authorized experiment supplies evidence.
