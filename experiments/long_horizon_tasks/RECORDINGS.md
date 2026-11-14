# Recordings of the pinned CLI (Task 1 of the long-horizon plan)

Evidence for the [long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md)'s
frozen rules, recorded 2026-11-13 on this machine. No model or provider call was made: the real CLI ran
inside a rootless Podman task container against `stub_api.py` on the host, with a dummy key and the agent
phase on an allowlist that does not list the vendor's API. `recordings.json` names every recording with
the SHA-256 of its files; the files stay under `/home/ollie/lh-cache/recordings/`. `fixtures/` holds one
cut per harness exception class and stream ending (no model text, tool input or output, no home path).

## What was recorded

- **CLI 2.1.311**, the version of the public row; it still installs (manifest built 2026-10-26, binary
  SHA-256 `86dc1fcc…ada`), and every session's init event reports `2.1.311`. Installed by the harness's
  own path (apt `curl nodejs npm procps`, then the vendor's bootstrap script) in one task image
  (`sound-change-cascade`'s Dockerfile, unchanged), about four minutes per attempt under load.
- **Scenarios** (`stub_api.py --scenario`): a normal end; a budget stop by `--max-budget-usd`; a refusal;
  an output limit; a context limit at the first request and after a compaction attempt; a harness
  timeout; a background subagent; a foreground subagent that asks for model `fable` and effort `max`;
  web tools enabled; `CLAUDE_CODE_SIMPLE=1` (the public row's setting). Effort `low`, `medium`, `high`.
- **Three public trials** of Terminal-Bench 4.0 row `f12d32df` (Claude Code 2.1.311, Haiku 5.5, `max`):
  a refusal, a pass and a fail, fetched anonymously from the hub's public storage.
- **Allowlist probes** with the `oracle` agent (`allowlist_probe.py` as the scratch task's solution).

## Reproduce

```
export LH=/home/ollie/lh-cache        # hvenv with Harbor 0.25.0 + podman-compose 1.6.0
printf '[engine]\ncompose_warning_logs = false\n' > $LH/logs/containers-override.conf
podman pull docker.io/gogost/gost@sha256:afc0137758ab4ce399d47a299f9abbacbf522b52a17e59cbb4b4e7a1a66e9196
podman tag  docker.io/gogost/gost@sha256:afc0…9196 docker.io/gogost/gost:3.2.7-nightly.20260602
experiments/long_horizon_tasks/record.sh make_task           # scratch task: neutral instruction, probe, allowlist
experiments/long_horizon_tasks/record.sh probe-oracle normal oracle --disable-verification
experiments/long_horizon_tasks/record.sh budget-medium budget claude-code --ak version=2.1.311 \
  --disable-verification --effort medium --ak max_budget_usd=0.05     # the other runs: recordings.json
python -I experiments/long_horizon_tasks/cut_fixture.py <trial dir> "<source>" fixtures/<name>.json
```

Two host-side fixes were needed, neither touching a task file: `harbor_patient.py` passes `-T` where the
harness passes `--no-TTY` to `compose exec` (podman-compose 1.6.0 rejects it, so every switch of a
phase's network policy failed before this); and `compose_warning_logs = false`, because podman 4.9
ignores `PODMAN_COMPOSE_WARNING_LOGS` and its banner broke the harness's package-manager probe.

## Plan assumption / what the recording shows

| Plan (section) | Assumption | Recording | Verdict |
| --- | --- | --- | --- |
| D2 | The harness's agent is what the public per-task figures measured | All 330 public trials ran with `CLAUDE_CODE_SIMPLE=1` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`: tools `Bash, Edit, Read` only. Without it the CLI declares 20 tools (`Task`, `Workflow`, `Skill`, `Cron*`, `Monitor`, `SendMessage`, …) | Contradicted unless the ladder sets the same two variables |
| D2 | Effort is bound by `--effort` and equal at every level | `--effort` reaches the request as `output_config.effort` (`low`, `medium`, `high`) with beta `effort-2025-11-24`; but the `Agent` tool takes `effort` and `model` fields, and a subagent asked for `max` ran at `max` in a `low` session | Contradicted (off with `CLAUDE_CODE_SIMPLE=1`, which removes `Agent`) |
| D2 | With a base URL the harness pins every alias and the subagent model | Every request named `claude-haiku-5-5`, including a subagent asked for `fable`; no title, summary or fallback request for another model | Confirmed |
| D2 | Switches for the advisor tool and the refusal fallback exist | In the binary: `CLAUDE_CODE_DISABLE_ADVISOR_TOOL`, `advisorModel`, `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL`; `fallbackModel`, `CLAUDE_CODE_NO_MODEL_FALLBACK`, `CLAUDE_CODE_REFUSAL_FALLBACK_CATCH_ALL`. No request declared an advisor; a refusal ended in `model_refusal_no_fallback` with no other model asked | Names confirmed; effect of each switch not exercised |
| D2 | The agent-setup log is kept per attempt and names the packages | `agent/setup/` stays empty; only `trial.log` shows the apt command | Contradicted |
| D2 | The CLI's version is checked from the session | `claude_code_version` in the init event; the setup's `claude --version` output is not kept | Confirmed (init event) |
| D3 | Built-in web agent and web tools are off | Under an allowlist the harness adds `--disallowedTools WebSearch,WebFetch`. 2.1.311's init lists agents `claude, Explore, general-purpose, Plan, statusline-setup` (no `web-fetch`; the binary filters that built-in out). Enabled, `WebFetch` first checks the domain with the vendor directly, bypassing the base URL (denied here: tool error), and `WebSearch` sends a request with server tool `web_search_20250305` through the base URL | Confirmed off by default; a passthrough must refuse server tools |
| D3 | The allowlist works under rootless Podman | Allowed index served, code host and vendor API refused, host listener reached, egress log copied by `podman logs -f` before teardown; setup ran on the open network (the CLI installed from hosts not on the list) | Confirmed, after the `-T` fix |
| D3 | A request naming an allowed host but routed elsewhere cannot be stopped | The proxy dials the named host itself: both misrouted requests reached pypi.org, never the denied address | Better than assumed |
| D3 / D4 | The passthrough's address is listed explicitly | Allowed by IP (`192.168.4.59`), entries carry no port: the container also reached the host's ssh on port 22 | Confirmed; every port of that address is open |
| D3 | The egress log serves the scan | A denial is logged as the IP and port with a `bypass` error line; the requested name is not logged | Partly: denied hosts appear as addresses only |
| D4 | Price table: input 0.10, output 0.50 per million, five times above 100,000 prompt tokens | The CLI's own cost equals the table for small requests (USD 0.0003, 0.052) and for a 990,000-token request (USD 0.49525 = 5 ×). On the three public archives the table, applied to deduplicated session rows, gives 1.05 to 1.11 times the CLI's figure | Base and the 5× point confirmed; threshold not pinned (Task 2) |
| D4 | The CLI's budget limit is a second guard | Stops after the response that crosses the cap (one response of overshoot), `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, exit 1. Subagent usage counts: a foreground subagent was stopped mid-run; background agents are killed with a plain-text line `Budget limit reached (…); stopping background agents.` | Confirmed, with one response of overshoot |
| D4 | Four settlement figures: meter, session records, CLI cost, per-model usage | Session rows repeat one message's usage per content block (dedupe by `message.id`); subagent rows live in `<session>/subagents/agent-*.jsonl`; a `cost-state` row holds the CLI's total; stream assistant events carry the start-of-message usage (1 to 3 output tokens); the result's `usage` is all zero at a budget stop while `modelUsage` and `total_cost_usd` are right | Readable, with these rules |
| D5 | A session has started when the stream holds an init event | Every session emitted `init` before its first request | Confirmed |
| D5 | A budget stop matches no harness pattern | `NonZeroAgentExitCodeError` (the harness's budget pattern expects "Budget has been exceeded", which 2.1.311 does not print) | Confirmed |
| D5 | Refusal, context and output endings are sibling classes of provider faults | Refusal: `AgentSafetyRefusalError` (the CLI retries once with the same model, then exit 1). Output limit: `OutputTokenExceededError` (three retries). Context limit: `NonZeroAgentExitCodeError`, not `ContextWindowExceededError`, at the first request and after a failed compaction, because the CLI rewrites the API's message ("Prompt is too long · …") | Partly contradicted: the context ending lands in the base class, together with the budget stop |
| D5 | The ending can be read from the stream | The result's `subtype` is `success` for refusal, output and context endings; the ending is in `is_error`, `terminal_reason` (`completed`, `budget_exhausted`, `api_error`, `prompt_too_long`, `blocking_limit`) and `api_error` / `stop_reason`. A harness timeout leaves no result event (`AgentTimeoutError`); the verifier still ran | Contradicted for `subtype`; use `terminal_reason` |
| D5 | Pre-session failures are separable | Both pre-session failures seen (network switch, agent install) are `RuntimeError` with no stream | Confirmed |

The key's value appeared in no kept file. The harness's exception text quotes the container command,
which carries the environment (`-e NAME=value`); here truncation happened to cut the key out, which a
launcher must not rely on.
