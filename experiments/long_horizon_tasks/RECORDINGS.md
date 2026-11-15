# Recordings of the pinned CLI (Tasks 1 and 2 of the long-horizon plan)

Evidence for the [long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md)'s
frozen rules, recorded 2026-11-13 on this machine. No model or provider call was made. The real CLI ran
inside a rootless Podman task container against `stub_api.py`, with a dummy key (or, for the token-mode
set, an obviously fake OAuth token), and the agent phase was on an allowlist that does not list the
vendor's API. Task 2's probes are in their own section after the assumption table. The kit's entry point is
[README.md](README.md).

**What is committed and what is not.**
- **Committed:** the cut fixtures, `fixtures/` (the stream side), `fixtures/requests/` (the request
  side), `fixtures/traces/` (file and process calls) and `fixtures/after-limit/` (requests after a time
  limit). The cut rules are in "Fixtures" below.
- **Local cache only:** the raw recordings stay under `$LH/recordings/` in the cache directory
  (`$LH`, by default `~/lh-cache`) (the stub's
  request logs, egress logs, container inspections, harness jobs, session files and debug logs).
  `recordings.json` holds the SHA-256 of each of their files, and each recording's harness arguments.
  For the `t2a-*` recordings those are read back from the trial's `config.json` by
  `cut_fixture.py harbor-args`; a hand-written index had garbled them in the first Task 2a commit (a
  shell variable `$D` was substituted inside `$DENY`, so the eighteen deny-list names were lost).
  **That cache is not backed up**, and a
  local recording cannot be fetched again from anywhere.
- **Fetchable again by digest:** the three public archives and the task packages. Their digests are in
  `recordings.json` and `tasks.json`.

## What was recorded

- **CLI 2.1.311**, the version of the public row.
  - It still installs (manifest built 2026-10-26, binary SHA-256 `86dc1fcc…ada`).
  - Every session's init event reports `2.1.311`.
  - Installed by the harness's own path (apt `curl nodejs npm procps`, then the vendor's bootstrap
    script) in one task image (`sound-change-cascade`'s Dockerfile, unchanged). An install took about
    four minutes per attempt under load.
- **Scenarios** (`stub_api.py --scenario`):
  - endings: a normal end; a budget stop by `--max-budget-usd`; a refusal; an output limit; a context
    limit, at the first request and after a compaction attempt; a harness timeout;
  - subagents: a background subagent; a foreground subagent that asks for model `fable` and effort `max`;
  - settings: web tools enabled; `CLAUDE_CODE_SIMPLE=1` (the public row's setting); effort `low`,
    `medium` and `high`.
  - Task 2 added provider faults, passthrough refusals and the token-mode set.
- **Three public trials** of Terminal-Bench 4.0 row `f12d32df` (Claude Code 2.1.311, Haiku 5.5, `max`):
  a refusal, a pass and a fail, fetched anonymously from the hub's public storage.
- **Allowlist probes** with the `oracle` agent (`allowlist_probe.py` as the scratch task's solution).

## Reproduce

```
export LH=${LH:-$HOME/lh-cache}  # the cache directory; hvenv with Harbor 0.25.0 + podman-compose 1.6.0
printf '[engine]\ncompose_warning_logs = false\n' > $LH/logs/containers-override.conf
podman pull docker.io/gogost/gost@sha256:afc0137758ab4ce399d47a299f9abbacbf522b52a17e59cbb4b4e7a1a66e9196
podman tag  docker.io/gogost/gost@sha256:afc0…9196 docker.io/gogost/gost:3.2.7-nightly.20260602
experiments/long_horizon_tasks/record.sh make_task           # scratch task: neutral instruction, probe, allowlist
experiments/long_horizon_tasks/record.sh probe-relay-oracle normal oracle --disable-verification
experiments/long_horizon_tasks/record.sh s3-budget-medium budget claude-code --ak version=2.1.311 \
  --ae CLAUDE_CODE_SIMPLE=1 --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --disable-verification \
  --effort medium --ak max_budget_usd=0.05                     # the other runs: recordings.json
AUTH=token experiments/long_horizon_tasks/record.sh t2a-normal-low normal claude-code --ak version=2.1.311 \
  --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --ak disallowed_tools=<the eighteen names> \
  --agent-setup-timeout-multiplier 3 --disable-verification --effort low   # Task 2a's form
AUTH=token DECOY=1 experiments/long_horizon_tasks/record.sh t2a-strace-decoy-low normal claude-code …  # the same
python -I experiments/long_horizon_tasks/cut_fixture.py <trial dir> "<source>" fixtures/<name>.json
python -I experiments/long_horizon_tasks/cut_fixture.py requests $LH/recordings/<name>/stub.jsonl \
  "<source>" fixtures/requests/<name>.json
python -I experiments/long_horizon_tasks/cut_fixture.py trace $LH/recordings/<name> "<source>" \
  fixtures/traces/<name>.json
python -I experiments/long_horizon_tasks/cut_fixture.py harbor-args $LH/recordings/<name>/jobs/*/*/config.json
python -I experiments/long_horizon_tasks/price_check.py $LH/recordings/archives/*/x
$LH/hvenv/bin/python -I -c 'import sys; from pathlib import Path; from harbor.publisher.packager import Packager;
  [print(p, "sha256:" + Packager.compute_content_hash(Path(p))[0]) for p in sys.argv[1:]]' <task dir>...
```

The last command recomputes the digests in `tasks.json`. Point it at unpacked 4.1.0 or 4.0.0 packages, or
at the checked copies. The packages come from the hub's public storage at
`packages/terminal-bench/<task>/<hex digest>/dist.tar.gz`, read with the publishable key that ships in the
harbor package (not copied here).

**Routes.** `record.sh` uses the relay route: the stub listens on a unix socket, and `relay` is on the
allowlist. The Task 1 recordings, the names without an `s3-`, `f-`, `pt-`, `key` or `tok` prefix, used the
script's earlier form: the stub was bound to the host's LAN address, and that address was on the
allowlist. The plan rejected that route, and the relay route replaced it. The stub now refuses any address
other than loopback.

**Host-side fixes.** Two were needed, and neither touches a task file:
- `harbor_patient.py` passes `-T` where the harness passes `--no-TTY` to `compose exec`. podman-compose
  1.6.0 rejects `--no-TTY`, so before this fix every switch of a phase's network policy failed.
- `compose_warning_logs = false`, because podman 4.9 ignores `PODMAN_COMPOSE_WARNING_LOGS` and its banner
  broke the harness's package-manager probe.

## Plan assumption / what the recording shows

| Plan (section) | Assumption | Recording | Verdict |
| --- | --- | --- | --- |
| D2 | The harness's agent is what the public per-task figures measured | All 330 public trials ran with `CLAUDE_CODE_SIMPLE=1` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, with tools `Bash, Edit, Read` only. Without that setting the CLI declares 20 tools (`Task`, `Workflow`, `Skill`, `Cron*`, `Monitor`, `SendMessage`, …) | Contradicted unless the ladder sets the same two variables |
| D2 | Effort is bound by `--effort` and equal at every level | `--effort` reaches the request as `output_config.effort` (`low`, `medium`, `high`) with beta `effort-2025-11-24` (request fixtures). But the `Agent` tool takes `effort` and `model` fields, and a subagent asked for `max` ran at `max` in a `low` session | Contradicted (off with `CLAUDE_CODE_SIMPLE=1`, which removes `Agent`) |
| D2 | With a base URL the harness pins every alias and the subagent model | Every request named `claude-haiku-5-5`, including a subagent asked for `fable`. There was no title, summary or fallback request for another model (`fixtures/requests/subagent-override-low.json`) | Confirmed |
| D2 | Switches for the advisor tool and the refusal fallback exist | In the binary: `CLAUDE_CODE_DISABLE_ADVISOR_TOOL`, `advisorModel`, `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL`; `fallbackModel`, `CLAUDE_CODE_NO_MODEL_FALLBACK`, `CLAUDE_CODE_REFUSAL_FALLBACK_CATCH_ALL`. No request declared an advisor. A refusal ended in `model_refusal_no_fallback` with no other model asked | Names confirmed; the effect of each switch not exercised |
| D2 | The agent-setup log is kept per attempt and names the packages | `agent/setup/` stays empty; only `trial.log` shows the apt command | Contradicted |
| D2 | The CLI's version is checked from the session | `claude_code_version` in the init event (every stream fixture). The setup's `claude --version` output is not kept | Confirmed (init event) |
| D3 | Built-in web agent and web tools are off | Under an allowlist the harness adds `--disallowedTools WebSearch,WebFetch`. 2.1.311's init lists agents `claude, Explore, general-purpose, Plan, statusline-setup`; there is no `web-fetch` (the binary filters that built-in out). Enabled, `WebFetch` first checks the domain with the vendor directly, bypassing the base URL (denied here, so a tool error). `WebSearch` sends a request with server tool `web_search_20250305` through the base URL (`fixtures/requests/web2-low.json`) | Confirmed off by default; a passthrough must refuse server tools |
| D3 | The allowlist works under rootless Podman | The allowed index was served; the code host and the vendor API were refused; the host listener was reached. The egress log was copied by `podman logs -f` before teardown. Setup ran on the open network (the CLI installed from hosts not on the list) | Confirmed, after the `-T` fix |
| D3 | A request naming an allowed host but routed elsewhere cannot be stopped | The proxy dials the named host itself: both misrouted requests reached pypi.org, never the denied address | Better than assumed |
| D3 / D4 | The passthrough's address is listed explicitly | Allowed by IP (Task 1: the host's LAN address). Entries carry no port, so the container also reached the host's ssh on port 22 | Confirmed; every port of that address is open. The relay route removes the host address from the list |
| D3 | The egress log serves the scan | A denial is logged as the IP and port with a `bypass` error line; the requested name is not logged | Partly: denied hosts appear as addresses only |
| D4 | Price table: input 0.10, output 0.50 per million, five times above 100,000 prompt tokens | The CLI's own cost equals the table for small requests (USD 0.0003, 0.052) and for a 990,000-token request (USD 0.49525, which is 5 ×). The final rule is under "Prices" | Base and the 5× point confirmed; the cache-write rate differs (Prices) |
| D4 | The CLI's budget limit is a second guard | The CLI stops after the response that crosses the cap (one response of overshoot), with `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, exit 1 (`simple-mode-stub-budget-stop-…`). Subagent usage counts: a foreground subagent was stopped mid-run (`twenty-tools-stub-budget-stop-in-subagent-…`). Background agents are killed, and the CLI prints a plain-text line saying the budget limit was reached and background agents are being stopped | Confirmed, with one response of overshoot |
| D4 | Four settlement figures: meter, session records, CLI cost, per-model usage | Session rows repeat one message's usage per content block (dedupe by `message.id`). Subagent rows live in `<session>/subagents/agent-*.jsonl`, and a `cost-state` row holds the CLI's total. Stream assistant events carry the start-of-message usage (1 to 3 output tokens). At a budget stop the result's `usage` is all zero while `modelUsage` and `total_cost_usd` are right (`simple-mode-stub-budget-stop-…`) | Readable, with these rules |
| D5 | A session has started when the stream holds an init event | Every session emitted `init` before its first request | Confirmed |
| D5 | A budget stop matches no harness pattern | `NonZeroAgentExitCodeError`. The harness's budget pattern expects "Budget has been exceeded", which 2.1.311 does not print | Confirmed |
| D5 | Refusal, context and output endings are sibling classes of provider faults | Refusal: `AgentSafetyRefusalError` (two requests, both refused, then exit 1). Output limit: `OutputTokenExceededError` (four requests). Context limit: `NonZeroAgentExitCodeError`, not `ContextWindowExceededError`, at the first request and after a failed compaction, because the CLI rewrites the API's message into its own prompt-too-long text (in `simple-mode-stub-context-limit-…`) | Partly contradicted: the context ending lands in the base class, together with the budget stop |
| D5 | The ending can be read from the stream | The result's `subtype` is `success` for refusal, output and context endings. The ending is in `is_error`, `terminal_reason` (`completed`, `budget_exhausted`, `api_error`, `prompt_too_long`, `blocking_limit`) and `api_error` / `stop_reason`. `api_error` is **absent** from the result except at an output limit (`max_output_tokens`) and a usage limit in token mode (`usage_limit_reached`); `api_error_status` is present and `null` when there was no HTTP status. A harness timeout leaves no result event (`AgentTimeoutError`), and the verifier still ran (`simple-mode-stub-timeout-…`, `verifier_result` reward 0) | Contradicted for `subtype`; use `terminal_reason` |
| D5 | Pre-session failures are separable | Both pre-session failures seen (network switch, agent install) are `RuntimeError` with no stream | Confirmed |
| D4 (Task 2) | The relay route keeps the agent to the relay and leaves the verifier without it | (a) to (d) below | Confirmed |
| D4 (Task 2) | Cache writes cost 0.20 per million | The CLI prices five-minute writes at 0.125 and one-hour writes at 0.20 (the archives; `*-cache-writes`). Key mode asks for five minutes, token mode for one hour | Contradicted for key mode |
| D5 (Task 2) | Provider faults end in their own harness classes | 429: `ApiRateLimitError`. 500: `ApiInternalServerError`. A 529 and a stalled first byte: `UnknownApiError`. Each ends after about three minutes of the CLI's own retries | Partly: a 529 is not told from other faults by its class |
| D5 (Task 2) | A passthrough refusal ends the attempt at once | 403 `permission_error` with `x-should-retry: false`: no retry, and the message is kept in the result. The 404 and 400 forms are retried, and the 404's message is lost | Confirmed for the proposed 403 form |
| D4 (Task 2, owner ruling) | The CLI can run on a subscription token in the public row's configuration | Simple mode reads no OAuth token: no request is sent, and the session ends `AgentAuthenticationError` | Contradicted (see "Token mode") |
| D2 / D5 (Task 2) | Task content equals the checked copies | 4.1.0 adds prebuilt, digest-pinned agent and verifier images. 7 of the 16 tasks changed from the public row's 4.0.0 | Contradicted (see "Task content") |

The key's value appeared in no kept file. The harness's exception text quotes the container command,
which carries the environment (`-e NAME=value`). Here truncation happened to cut the key out; a launcher
must not rely on that.

## Task 2 probes (no spend)

### The relay route (plan D4, route B)

`relay-compose.yaml` adds a service `relay` (socat, pulled by digest) with its own `networks` entry. It
forwards TCP 8080 to `/run/lh/passthrough.sock`. That socket sits in a directory bind-mounted into the
relay alone, and the stub listens on it. The allowlist is `relay`, `pypi.org`, `files.pythonhosted.org`;
`record.sh` checks it before every run.

| Probe | Recording | Result |
| --- | --- | --- |
| (a) The harness and podman-compose accept the extra service and leave it outside the sidecar's namespace | `probe-relay-oracle` (`containers.txt`) | Held: `relay` runs on the compose bridge network; `main` runs in `container:<sidecar>` |
| (b) The agent reaches `relay` by name through the proxy, and nothing new | `probe-relay-oracle` (`fixtures/requests/probe-relay-oracle.json` holds the relay request) | Held: `relay` resolves (10.89.0.3), and `http://relay:8080/…` reached the stub. Every one of the host's 39 listening TCP ports was refused at the host's address, at the network gateway and at 10.0.2.2: 116 proxy denials in the egress log. The 117th connection, TCP 53 to the gateway's name server, passes by the sidecar's DNS rule and returned nothing. The code host and the vendor's API stay refused; the package index answers |
| (c) The socket is mounted into the relay alone | `probe-relay-oracle`, every later run | Held: `relay` has the one bind mount; `main` and the sidecar have none; `/run/lh` is absent inside the agent's container |
| (d) The verifier's environment has no relay | `probe-relay-nop`, `s3-timeout-low` | Held: the verifier runs in its own compose project (`…__verifier__trial_main_1`, bridge, no mounts) with no `relay` service |

What the agent can still reach:
- `relay:8080`, and so the passthrough;
- the allowed package indexes;
- name lookups at the network's name server;
- ICMP;
- its own network namespace (the sidecar's).

It cannot reach the host or the vendor's API. Not probed: whether the verifier, which has its own network,
could reach the relay's address directly. The raw recordings named in this section (`containers.txt`,
the egress logs) exist only in the local cache.

### The endings again, with three tools, through the relay

Configuration: `CLAUDE_CODE_SIMPLE=1`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, CLI 2.1.311. Every init
event lists exactly `Bash, Edit, Read`. These fixtures now carry a `simple-mode-` prefix; the names the plan's D5
cites hold the Task 2a recordings ("Task 2a" below).

| Ending | Recording / fixture | Recorded fields | Harness class, exit |
| --- | --- | --- | --- |
| Normal | `s3-normal-low` / `simple-mode-stub-normal-end` | `completed`, `is_error false`, `end_turn` | none, 0 |
| CLI budget | `s3-budget-medium` / `simple-mode-stub-budget-stop-NonZeroAgentExitCodeError` | `budget_exhausted`, `error_max_budget_usd`; the result's `usage` is zero, `modelUsage` right | `NonZeroAgentExitCodeError`, 1 |
| Refusal | `s3-refusal-high` / `simple-mode-stub-refusal-AgentSafetyRefusalError` | two requests, both refused (request fixture), then `model_refusal_no_fallback`; `api_error` as `terminal_reason`, `stop_reason refusal` | `AgentSafetyRefusalError`, 1 |
| Output limit | `s3-max-tokens-low` / `simple-mode-stub-output-limit-OutputTokenExceededError` | four requests (request fixture); `terminal_reason api_error`, `api_error max_output_tokens` | `OutputTokenExceededError`, 1 |
| Context limit | `s3-context-low` / `simple-mode-stub-context-limit-NonZeroAgentExitCodeError`; `s3-context-late-low` / `simple-mode-stub-context-limit-after-compaction-NonZeroAgentExitCodeError` | `prompt_too_long` (`api_error_status 400`); after a failed compaction, `blocking_limit` | `NonZeroAgentExitCodeError`, 1 |
| Time limit | `s3-timeout-low` / `simple-mode-stub-timeout-AgentTimeoutError` | no result event; the verifier ran (`verifier_result` reward 0 in the fixture) | `AgentTimeoutError` |

The forms equal the twenty-tool ones, with one difference. With three tools a standalone `sleep 30` runs
(the twenty-tool CLI refused it). So the timeout session made 6 requests, the last 150 s after the first
(`fixtures/requests/s3-timeout-low.json`), where the twenty-tool session made 1,148
(`fixtures/requests/timeout-low.json`).

### Provider faults

Every persistent fault was answered from the second request on; the first turn succeeded. Each row's
request fixture has the recording's name.

| Fault (recording / fixture) | What the CLI did | Final fields | Harness class, exit |
| --- | --- | --- | --- |
| 429 with `retry-after: 5` (`f-rate-limit-retry-after` / `simple-mode-stub-rate-limit-retry-after-ApiRateLimitError`) | 10 retries (`n_api_retry` 10). Waits were 5 s while the header held, then backoff to about 40 s. Gave up after 197 s | `terminal_reason api_error`, `is_error true`, `api_error_status 429`. The result text is a CLI line naming the rejected request and status, then the stub's message (in the fixture) | `ApiRateLimitError`, 1 |
| 429 without it (`f-rate-limit` / `simple-mode-stub-rate-limit-ApiRateLimitError`) | 10 retries, backoff 0.5 s doubling to about 37 s; 184 s | as above | `ApiRateLimitError`, 1 |
| 529 (`f-overloaded` / `simple-mode-stub-overloaded-UnknownApiError`) | 10 retries; 181 s | `api_error_status 529`. The result text names the status and the base URL's host (`relay:8080`), and differs from the harness's overload pattern | `UnknownApiError`, 1 |
| 500 (`f-server-error` / `simple-mode-stub-server-error-ApiInternalServerError`) | 10 retries; 180 s | `api_error_status 500` | `ApiInternalServerError`, 1 |
| Stream cut after the first block (`f-drop` / `simple-mode-stub-dropped-stream-recovered-normal-end`) | One streaming retry (`api_retry`, `error unknown`), then a **non-streaming** request (`stream false`, `max_tokens 64000`; request fixture), which the stub also served | `completed`, `is_error false`: the session went on | none, 0 |
| First byte after 120 s (`f-slow` / `simple-mode-stub-slow-first-byte-UnknownApiError`) | Every attempt ended after about 15 s with a reset connection. 10 retries; the last request started 325 s after the first, and the session ended at 340 s (`duration_ms` 340,168) | `terminal_reason api_error`, `api_error_status null`. The result text names a dropped connection and the base URL (in the fixture) | `UnknownApiError`, 1 |
| 429, 529, 500 once each, then success (`f-transient` / `simple-mode-stub-transient-faults-recovered-normal-end`) | three retries; 6 s | `completed` | none, 0 |

- Each retry emits a stream event `system/api_retry` with `attempt`, `max_retries` (10), `retry_delay_ms`,
  `error_status` and `error` (`rate_limit`, `overloaded`, `server_error`, `unknown`). A normal ending can
  therefore contain recovered faults. Each stream fixture counts them in `n_api_retry`.
- Usage: failed requests add nothing to `modelUsage` or the session file. A cut stream does. The CLI
  counted both cut streams' start-of-message usage (`modelUsage` input 4,000, output 202), while the
  session file holds the two complete messages (2,000 and 200). Settlement's largest-figure rule takes the
  CLI's figure.
- Not separated: whether the 15 s of `f-slow` is the CLI's own first-byte window or a hop of the route
  (socat, the proxy).

### The passthrough's refusals (forms proposed; the stub returned them)

| Refusal (recording / fixture) | Form sent | What the CLI did | Final fields | Harness class, exit |
| --- | --- | --- | --- | --- |
| Slot at its cap (`pt-cap` / `simple-mode-passthrough-cap-UnknownApiError`) | 403 `permission_error`, `x-should-retry: false`, message `lh-passthrough: slot cap reached` | no retry (one refused request); ended in under 1 s | `api_error_status 403`. The result text is a CLI prefix naming an authentication failure and the status, then the passthrough's message verbatim | `UnknownApiError`, 1 |
| Tranche total (`pt-total` / `simple-mode-passthrough-total-UnknownApiError`) | same, `… tranche total reached` | same | same, with that message | `UnknownApiError`, 1 |
| Tranche stopped (`pt-stopped` / `simple-mode-passthrough-stopped-UnknownApiError`) | same, `… tranche stopped` | same | same, with that message | `UnknownApiError`, 1 |
| Another model (`pt-model` / `simple-mode-passthrough-model-NonZeroAgentExitCodeError`) | 404 `not_found_error`, `x-should-retry: false` | one non-streaming retry, also refused (two refused requests) | `api_error_status 404`. The result text is the CLI's own selected-model notice; the passthrough's message is lost | `NonZeroAgentExitCodeError`, 1 |
| A provider-side tool (`pt-tool` / `simple-mode-passthrough-tool-UnknownApiError`) | 400 `invalid_request_error`, `x-should-retry: false` | two retries (three refused requests), each dropping beta headers (three request shapes) | `api_error_status 400`. The result text holds the passthrough's message | `UnknownApiError`, 1 |

**Proposed form for every passthrough refusal:** HTTP 403,
`{"type":"error","error":{"type":"permission_error","message":"lh-passthrough: <reason>"}}`, and
`x-should-retry: false`.
- It was the only recorded form that the CLI did not retry.
- Its message reaches the result text verbatim, so the launcher can read the reason from the result as
  well as from the passthrough's log.
- Its harness class (`UnknownApiError`) is also the class of a 529, so the class decides nothing.
  `api_error_status 403` plus the `lh-passthrough:` prefix does.
- The model and tool refusals were recorded with 404 and 400 only. That 403 ends them the same way is
  inferred, not recorded.

### Prices (`price_rule.json`, `price_check.py` over the three public archives)

`price_rule.json` is the single source of the rates for this kit and for the long-horizon launcher. The
package's `orchestrator/providers/price_table.json` cannot express this rule: it has one cache-write rate
and a long-context tier, and `pricing.py` prices with base rates and caps with the highest tier for every
token. Per-request long-prompt pricing is therefore new launcher code.

The rule, applied request by request (one row per message id):
- **each cache write is priced at its own lifetime's rate**: 0.125 per million for five minutes, 0.20
  for one hour;
- **every rate is multiplied by five above 100,000 prompt tokens** (prompt = input + cache read +
  cache write).

It reproduces the CLI's three totals exactly: USD 0.120039925, 2.617723155 and 0.746610645
(`tests/test_long_horizon_price_check.py`, when the archives are cached).

The variants `price_check.py` prints, as a share of the CLI's total:

| Variant | Share of the CLI's total |
| --- | --- |
| Every write at 0.20 (the package table's `cache_write`, read per request) | 1.05 to 1.10 |
| The threshold at 200,000 | 0.53 to 0.88 |
| No long-prompt rate | 0.22 to 0.56 |

- The threshold lies between 98,828 and 101,144 prompt tokens (the closest requests on either side).
- The one-hour rate comes from the stub recordings `tok3-cache-writes` (fixture
  `token-one-hour-cache-writes-normal-end`) and `key3-cache-writes`: USD 0.0083 for two requests of
  20,000 one-hour write tokens each, where 0.125 would give 0.0053.
- Nothing stays unexplained on the three archives.
- Not settled: the model's real prompt limit. The largest recorded prompt is 443,427 tokens,
  `modelUsage.contextWindow` says 1,000,000, and no archive reached a limit.

### Task content at 4.1.0 (`tasks.json`)

The 16 packages were fetched by their 4.1.0 digests from the benchmark hub's public storage. Each digest
was recomputed with the harness's own packager (the command is under "Reproduce"), and all 16 match.
Against the copies the feasibility check used (`harbor-framework/terminal-bench` at `adf10d2b`):

- Instruction, environment, solution and tests are identical for all 16.
- `task.toml` differs for all 16, and only by additions:
  - `[environment] docker_image = "harborframework/terminal-bench:<task>-environment-…@sha256:…"`;
  - a `[verifier.environment]` table: CPUs, memory, storage, build timeout, and the `docker_image` of a
    prebuilt verifier image, with `allow_internet = false` for batched-eval-parity and lake-temp-glm;
  - two tasks also gain `mcp_servers = []`.
- Files only in the checked copies, not in the packages:
  - `LICENSE.md` (gsea-proteomics, hof-topology-interpenetration, roy-polymorph-cn);
  - `THIRD_PARTY_NOTICES` (retro-console-soc);
  - `.gitignore` (rs-archive-clone);
  - `environment/.dockerignore` (shadow-relay).
- So 4.1.0 runs **prebuilt images pinned by digest** for both the agent and the verifier, where the
  oracle check built them from the Dockerfiles. The checked copies' oracle evidence therefore rests on
  locally built images, not on the pinned ones.
- The public row's trials ran **4.0.0** content (their task hashes are the 4.0.0 digests).
  - 4.0.0 and 4.1.0 are identical for 9 of the 16: gsea-proteomics, hof-topology-interpenetration,
    production-planning, retro-console-soc, roy-polymorph-cn, rs-archive-clone, shadow-relay,
    vf2-speedup-networkx, vpp-loss-divergence.
  - The other 7 changed their verifier tests between the two versions: batched-eval-parity, lake-temp-glm,
    pretrain-shard-corruption, session-window-debug, sound-change-cascade, vba-userform-port,
    wal-recovery-ordering. All but wal-recovery-ordering also changed their agent environment (a
    Dockerfile, a uv lock).
  - Instructions and reference solutions did not change.
  - For those 7, the public per-task counts were measured on a different environment.
- `tasks.json` now also holds each task's pinned images and withholding result (Task 2b, below), and the
  first oracle pass filled `overlay_digest` and `oracle_evidence` ("First oracle pass"). `cap` and
  `extra_hosts` stay `null` until Task 3.

### Token mode (owner ruling: subscription only)

Recorded with `AUTH=token record.sh …`, the harness's `CLAUDE_FORCE_OAUTH=1` route. The CLI got
`CLAUDE_CODE_OAUTH_TOKEN=lh-fake-oauth-token-not-real`, an empty `ANTHROPIC_API_KEY`, and the base URL
`http://relay:8080`; same CLI 2.1.311, same relay, same allowlist. `DEBUG=1` wrote the CLI's debug log,
which exists only in the local cache. Every claim about a request cites a request fixture under
`fixtures/requests/`, named after the recording.

| Question | Recording / fixture | What it shows |
| --- | --- | --- |
| Token mode in the three-tool configuration (`CLAUDE_CODE_SIMPLE=1`) | `tok-normal-404`, `tok-normal-401`, `tok-usage-limit-60s`, `tok-usage-limit-4h` / `token-simple-mode-AgentAuthenticationError` | **It does not run.** The CLI sent no request at all: the stub logged none (so these recordings have no request fixture), and the egress log has no connection. Its debug log records that no authentication method could be resolved. The result text is the CLI's not-logged-in notice (in the fixture): `terminal_reason api_error`, `is_error true`, `api_error_status null`, cost 0, `modelUsage {}`, init `apiKeySource none`. Harness class `AgentAuthenticationError`, exit 1. The CLI's help text for its minimal mode gives the reason: that mode authenticates only with an API key or an `apiKeyHelper`, and never reads OAuth or the keychain |
| Hosts and paths, default tools | `tok20-normal-404`, `tok20-normal-401`, `tok20-traffic-on`, `tok20-usage-limit-*`, `tok20-unauthorized` | The base URL is honoured: every request the CLI made was `POST /v1/messages?beta=true` to the relay, and nothing else (the request fixtures). The only other connection in each egress log is the stub's own probe command, a `curl` to the vendor's messages URL run by the Bash tool, which the proxy refused. The vendor stays unreachable inside the same session |
| Extra endpoints (profile, usage, refresh, telemetry) | the same; the stub answered every other path with 404 (`tok20-normal-404`) or 401 (`tok20-normal-401`) | **None was called**, through the base URL or elsewhere. The harness always sets `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. The debug log records that bootstrap and the served catalog were skipped for that reason, and `--ae CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=0` did not turn it off (`tok20-traffic-on`). So the 404 and 401 variants end alike. From the bundle, not recorded: the profile fetch would go to a fixed OAuth host rather than the base URL, and the allowlist would refuse it |
| Headers | `tok20-normal-404` (fixture `twenty-tools-token-normal-end`) against `key20-normal-debug` (key mode, same tools) | Token mode sends `authorization: Bearer <dummy>` and no `x-api-key`; key mode sends `x-api-key` and no `authorization`. Token mode adds the betas `oauth-2025-04-20` and `extended-cache-ttl-2025-04-11`. Same user agent product token (`claude-cli/2.1.311`), `x-app: cli`, and the same other header names |
| Body | the same, and `tok3-normal` (fixture `first-token-three-tools-normal-end`) against `key3-normal-system` | The same body fields (`model`, `metadata`, `max_tokens`, `thinking`, `context_management`, `output_config`, `stream`) and the same tool list for the same tools. The same three-block system layout (`key3-normal-system`, `tok3-normal`): a 74-character attribution block, SHA-256 `d87d6703bc46b722feedc6f23ba93ca71f112cb922d33ac503ab57b5010b2ca3`, then a 62-character identity block, SHA-256 `0d7062851dd7bd7e66d4be4f12ac4951e3d2f587ec408295333a49963bd3f6b7`. In token mode the system blocks carry `cache_control {"type":"ephemeral","ttl":"1h"}`; in key mode, `{"type":"ephemeral"}` (five minutes) |
| Three tools without simple mode | `tok3-normal` (`--ak disallowed_tools=` the other 18) / `first-token-three-tools-normal-end` | Init lists `Bash, Edit, Read`, but the request carries a fourth tool (`DeferredToolPlaceholder`). Its third system block is the default system prompt (8,830 characters), where simple mode sends a 26-character block naming the working directory and the date. It is not the public row's configuration |
| Init and result | every token run | Init `apiKeySource` is `none` (key mode: `ANTHROPIC_API_KEY`); no other init field differs. The result event has the same keys. `total_cost_usd`, `usage` and `modelUsage` have the same shape and values; `modelUsage` keeps `costUSD`, `costBasis "list"`, and the split `cacheCreationEphemeral5mInputTokens` / `…1hInputTokens`. The stream gains `rate_limit_event` events: `{"status":"allowed","isUsingOverage":false}` after each response without limit headers. Nothing settlement uses is missing |
| Usage limit: a 429 with `anthropic-ratelimit-unified-status: rejected`, `…-representative-claim: five_hour` and `…-reset`, the headers the bundle reads | `tok20-usage-limit-60s` / `twenty-tools-token-usage-limit-NonZeroAgentExitCodeError`, and `tok20-usage-limit-4h` | **Exits at once**, with no retry, whether the reset is 1 minute or 4 hours away. A `rate_limit_event` `{"status":"rejected","resetsAt":…,"rateLimitType":"five_hour"}` comes first. Then the result: the CLI's session-limit notice with the reset time (in the fixture), `terminal_reason api_error`, `is_error true`, **`api_error usage_limit_reached`**, `api_error_status 429`. Harness class `NonZeroAgentExitCodeError`, exit 1 |
| The same headers in key mode | `key-usage-limit-60s` / `simple-mode-stub-usage-limit-headers-key-mode-UnknownApiError` | Treated as an ordinary 429: 10 retries over 176 s, `api_error` **absent**, `api_error_status 429`; `UnknownApiError` |
| Usage limit with the CLI's unattended retry (`CLAUDE_CODE_RETRY_WATCHDOG=1`, `…_MAX_USAGE_LIMIT_WAIT_MS=150000`) | `tok20-usage-limit-watchdog` / `twenty-tools-token-usage-limit-watchdog-NonZeroAgentExitCodeError` | **Waits** for the reset: `api_retry` events with `max_retries 300` and delays of about 60 s, and a `rate_limit_event` per refusal. The request was repeated at 59 s and 119 s (request fixture). After the 150 s cap it ends as above (`usage_limit_reached`) |
| Credential refused (401 `authentication_error`) | `tok20-unauthorized` / `twenty-tools-token-unauthorized-UnknownApiError` | Two retries (`n_api_retry` 2; three requests), and no refresh request. The debug log says the CLI keeps the user-supplied token rather than adopting a stored credential. The session ends with an authentication-failure result, `api_error_status 401`; `UnknownApiError`, exit 1 |
| One-hour cache writes priced | `tok3-cache-writes` / `token-one-hour-cache-writes-normal-end`, and `key3-cache-writes` (the stub reports 20,000 write tokens per request, all `ephemeral_1h`) | The CLI prices them at **0.20** per million in both modes: it prices by the usage's split, not by the mode. Token mode asks for one-hour caching, so its writes cost 1.6 times those of a key-mode session |

**What the recordings imply for the route.** Which route the ladder takes is the plan's to settle. The
recordings show what each route entails:

- **Key mode with a dummy key in the container** (the configuration of every other recording). The
  passthrough removes `x-api-key`, adds `authorization: Bearer <subscription token>`, and appends
  `oauth-2025-04-20` to `anthropic-beta`. The public row's configuration is kept. The CLI asks for
  five-minute caching. A usage limit reaches it as an ordinary 429 (ten retries over about three
  minutes, `UnknownApiError`), so the passthrough would have to recognise the vendor's usage-limit 429
  itself and answer with its own refusal.
- **Token mode outside simple mode, three tools by `--disallowedTools`.** The CLI sends the token itself
  and ends at a usage limit with `usage_limit_reached`. But the request carries the default system prompt
  (8,830 characters instead of 26) and a placeholder tool, and asks for one-hour caching. It is not the
  configuration the public row measured.

**Only a live request with a real token can settle:**

- whether the vendor accepts a subscription token on the chosen request shape, and whether it requires
  anything else of such a request;
- the real usage-limit 429: its status, body and `anthropic-ratelimit-unified-*` headers, and the headers
  on ordinary responses (the stub sent none, so `rate_limit_event` only ever read `allowed`);
- what a subscription session reports in `usage` and `modelUsage`: whether `costUSD` and the cache split
  are filled the same way, and whether `service_tier` differs;
- whether token mode with nonessential traffic allowed calls the profile or usage endpoints at start (the
  harness never allows it, so the launcher need not either);
- how long a `setup-token` token lives before the 401 recorded above.

## Task 2a: the ladder's configuration (no spend)

**Configuration.** Every recording here ran the CLI the way D2 now runs it (except the contrasts named
as such: `t2a-no-credential-low`, `t2a-forced-empty-low`, `t2a-simple-key-sizes`): token mode
(`AUTH=token record.sh …`, the harness's `CLAUDE_FORCE_OAUTH=1` route), no simple mode, three tools by
the deny list (`--ak disallowed_tools=` the eighteen names of `tok3-normal`),
`CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, CLI 2.1.311, the default system prompt. The container held one
fake token in the launcher's per-slot form, `lh-fake-slot-<32 hex digits>`, drawn by `record.sh` for each
recording; the stub checked every request's bearer against it (`--expect-bearer`) and logged only the
result (`bearer_matches`), never the token. The base URL was the relay, the socket directory one per
recording. `t2a-probe-relay-oracle` ran first and showed the vendor API refused through the proxy
(`t2a-fix1-probe-relay-oracle` again before the fix-round recordings: the vendor's name resolved and the
proxy dropped the TLS connection); in
every recording with an egress log, the CLI's only connections went to the relay (four early recordings
have none or another lane's: `t2a-normal-low`, `t2a-normal-medium`, `t2a-usage-limit-low`,
`t2a-unauthorized-low`). Recording names start
with `t2a-`; each stream fixture's `source` names its recording, and each request fixture is
`fixtures/requests/<recording>.json`. Request fixtures in this set add, per request, the cache marks on
message blocks; for the first request, each message block's role, length and cache mark, and how often
each watched skill or agent name occurs in the system, tool and message text (`first_request`).

**Init and request, at each effort** (`t2a-normal-low`, `-medium`, `-high` /
`token-three-tools-normal-end`, `token-three-tools-normal-end-medium`, `token-three-tools-normal-end-high`):

| Field | Recorded (the same at low, medium and high unless named) |
| --- | --- |
| Init | tools `Bash, Edit, Read`; `apiKeySource none`; `mcp_servers []`; version `2.1.311` |
| Declared tools | `Bash, Edit, DeferredToolPlaceholder, Read`; no server tool |
| `max_tokens`, effort | 128000; `output_config.effort` `low`, `medium`, `high`; `thinking` adaptive |
| Beta flags | ten: those of simple mode plus `oauth-2025-04-20`, `mid-conversation-tool-changes-2026-07-01` and `extended-cache-ttl-2025-04-11` (simple mode, key: seven; `t2a-simple-key-sizes`) |
| Authorization | `Bearer`, the slot's fake token on every request (`bearer_matches true` in every request fixture of this set) |

**Sizes, characters only** (`t2a-normal-low` against `t2a-simple-key-sizes`, simple mode with a key,
same CLI):

| Part | Token mode, three tools | Simple mode |
| --- | --- | --- |
| System blocks | 74 + 62 + 8,830 = 8,966 | 74 + 62 + 26 = 162 |
| Tool definitions (`json.dumps` of each) | Bash 3,788, Edit 1,006, placeholder 214, Read 1,975 = 6,983 | Bash 1,616, Edit 666, Read 1,200 = 3,482 |
| First request's messages | a user message of two blocks (581 and 85) and a system-role message of one block (887) | one user block (85) |

Token mode adds about 13,800 characters to every request: 8,804 in the system blocks, 3,501 in the tool
definitions, about 1,470 in the messages.

**Cache lifetimes.** Tool definitions carry no `cache_control`. System blocks 2 and 3 and the last
message block ask `{"type":"ephemeral","ttl":"1h"}` on every request of every recording in this set,
with two exceptions, where every later request drops `extended-cache-ttl-2025-04-11` and asks
`{"type":"ephemeral"}` (five minutes) on all three marks:
- after a response carrying the paid-extra-usage headers (`t2a-overage-low`, second request);
- after a response reporting a 990,000-token prompt (`t2a-context-late-low`, second and third
  requests). The stub sent no rate-limit header there, so this is not a paid-usage sign. These
  requests also drop `claude-code-20250219`, as the same requests do in simple mode
  (`s3-context-late-low`, `context-late-low`, shape 1), while the paid-usage fallback keeps it:
  the large-prompt case looks like a different request path after a near-full context, not a
  reaction to a header.

**Endings.**

| Ending | Recording / fixture | Recorded fields | Harness class |
| --- | --- | --- | --- |
| Normal | `t2a-normal-low` / `token-three-tools-normal-end` | `completed`, `end_turn`; two requests | none |
| CLI budget | `t2a-budget-medium` / `stub-budget-stop-NonZeroAgentExitCodeError` | `budget_exhausted`, `error_max_budget_usd`; one request; the result has **no `api_error_status` key** | `NonZeroAgentExitCodeError` |
| Refusal | `t2a-refusal-high` / `stub-refusal-AgentSafetyRefusalError` | two refused requests, `model_refusal_no_fallback`, `stop_reason refusal`, `api_error_status null`; the result text names the model and the usage policy | `AgentSafetyRefusalError` |
| Output limit | `t2a-max-tokens-low` / `stub-output-limit-OutputTokenExceededError` | four requests; `api_error max_output_tokens` | `OutputTokenExceededError` |
| Context limit | `t2a-context-low` / `stub-context-limit-NonZeroAgentExitCodeError` | `prompt_too_long`, `api_error_status 400`; one request | `NonZeroAgentExitCodeError` |
| Context limit after compaction | `t2a-context-late-low` / `stub-context-limit-after-compaction-NonZeroAgentExitCodeError` | the compaction request (third request): same tools and system blocks, the first user message cut to 53 characters, the system-role message emptied, a 78-character system message added; refused again, then `blocking_limit` | `NonZeroAgentExitCodeError` |
| Time limit | `t2a-timeout-low` / `stub-timeout-AgentTimeoutError`, `fixtures/after-limit/t2a-timeout-low.json` | no result event; reward 0. The CLI blocked the standalone `sleep 30` with a tool error, as the twenty-tool CLI did, so the session made 1,212 requests (simple mode: 6) | `AgentTimeoutError` |
| Usage limit | `t2a-usage-limit-low` / `token-usage-limit-NonZeroAgentExitCodeError` | 429, no retry, `api_error usage_limit_reached`, `api_error_status 429` | `NonZeroAgentExitCodeError` |
| Credential refused | `t2a-unauthorized-low` / `token-unauthorized-UnknownApiError` | 401, two retries (three requests), `api_error_status 401` | `UnknownApiError` |
| No credential | `t2a-no-credential-low` (`AUTH=none`: no token, no key) / `token-no-credential-AgentAuthenticationError` | the not-logged-in result, `api_error_status null`, no request in the stub's log | `AgentAuthenticationError` |
| Empty token forced | `t2a-forced-empty-low` (`AUTH=forced-empty`) / `token-forced-empty-RuntimeError` | the harness refused before the session: no stream | `RuntimeError` |

**After the time limit** (`fixtures/after-limit/t2a-timeout-low.json`, and `…/s3-timeout-low.json` in
simple mode). The harness ended the agent phase at 21:57:02.408Z (`agent_execution.finished_at`), but
it ends its `exec`, not the CLI: the stub logged **72 more requests in the 18.3 s after that**, all
answered 200 and all with the slot's token, until the container stopped. In simple mode one request
came 7.5 s after the limit. Those requests are in neither the stream nor the session file.

**The refusal of a standalone `sleep`.** Every turn of `t2a-timeout-low` was answered with this tool
error (CLI text, kept in the same fixture):

```text
<tool_use_error>Blocked: standalone sleep 30. To wait for a condition, use Monitor with an until-loop (e.g. `until <check>; do sleep 2; done`). To wait for a command you started, use run_in_background: true. Do not chain shorter sleeps to work around this block.</tool_use_error>
```

Monitor is one of the eighteen tools the deny list removes. In simple mode the same call ran
(`simple-mode-stub-timeout-…`).

**Provider faults** (each fault from the second request on, as in simple mode):

| Fault | Recording / fixture | What the CLI did | Final fields, class |
| --- | --- | --- | --- |
| 429 with `retry-after: 5` | `t2a-f-rate-limit-retry-after` / `stub-rate-limit-retry-after-ApiRateLimitError` | 10 retries; 197 s | `api_error_status 429`; `ApiRateLimitError` |
| 429 without it | `t2a-f-rate-limit` / `stub-rate-limit-ApiRateLimitError` | 10 retries; 178 s. Each 429 also brought a `rate_limit_event` `status rejected` with no limit type or reset; the result text calls it a temporary limit, not the usage limit | `api_error_status 429`, no `api_error`; `ApiRateLimitError` |
| 529 | `t2a-f-overloaded` / `stub-overloaded-UnknownApiError` | 10 retries; 180 s | `api_error_status 529`; `UnknownApiError` |
| 500 | `t2a-f-server-error` / `stub-server-error-ApiInternalServerError` | 10 retries; 177 s | `api_error_status 500`; `ApiInternalServerError` |
| Stream cut | `t2a-f-drop` / `stub-dropped-stream-recovered-normal-end` | one streaming retry, then a non-streaming request | `completed`; none |
| First byte after 120 s | `t2a-f-slow` / `stub-slow-first-byte-UnknownApiError` | 10 retries; 341 s | `api_error_status null`; `UnknownApiError` |
| 429, 529, 500 once each | `t2a-f-transient` / `stub-transient-faults-recovered-normal-end` | three retries; 6 s | `completed`; none |

**The passthrough's seven refusals,** all in the proposed form (403 `permission_error`,
`x-should-retry: false`, message `lh-passthrough: <reason>`), each served on the session's second
request: `t2a-pt-cap`, `t2a-pt-total`, `t2a-pt-stopped`, `t2a-pt-model403`, `t2a-pt-tool403`,
`t2a-pt-path`, `t2a-pt-token` / `passthrough-cap-…`, `passthrough-total-…`, `passthrough-stopped-…`,
`passthrough-model-…`, `passthrough-tool-…`, `passthrough-path-…`, `passthrough-unknown-token-…`
(all `UnknownApiError`). Every one: no retry (two requests), `api_error_status 403`, the passthrough's
message verbatim in the result text. The model and tool refusals, recorded in simple mode only as 404
and 400, now end like the others.

**A refusal on the session's first request** (fix round 1: `t2a-pt-token-first` /
`passthrough-unknown-token-first-request-UnknownApiError`; stub scenario `pt_token_first`), as a model or
token refusal happens in the ladder. The init event came first; then one request, refused with
`lh-passthrough: unknown token`, no retry, `api_error_status 403`, the message in the result text,
`UnknownApiError`, exit 1: the same form as on the second request.

**The three questions.**

| Question | Recording / fixture | What it shows |
| --- | --- | --- |
| Does the CLI read a credential in token mode? | First `t2a-strace-low` / `fixtures/traces/t2a-strace-low.json` (`strace -f` attached from the host to the running CLI, 0.75 s after it started), then `t2a-strace-decoy-low` / `fixtures/traces/t2a-strace-decoy-low.json`, `fixtures/requests/t2a-strace-decoy-low.json`, `token-decoy-credential-normal-end` (`DECOY=1`: a decoy `.credentials.json` holding a generated canary, in the subscription-credential shape, planted in the CLI's config directory just before the harness's `exec`; that `exec` run under `strace -f --pidns-translation`, so the trace holds the CLI's own `execve` and every call after it; the cut keeps only the CLI and its children) | **It opens a stored credential but sends the environment's token.** The CLI `statx`es and **opens** the decoy (`openat ok`); both requests carried the slot's fake token (`bearer_matches` 2 of 2), the canary occurred in no request's system, tool or message text (the stub's count, kept as `<canary>`), and the only file of the recording holding it is the harness's export of the config directory (`agent/sessions/.credentials.json`; `decoy` in the trace fixture). The session completed (init `Bash, Edit, Read`, `apiKeySource none`). **Other credential lookups, all absent (`ENOENT`):** `/root/.config/anthropic/active_config` and `…/configs/default.json`, `/home/claude/.claude/remote/.api_key` and `…/.session_ingress_token`, `/root/.claude/state/unattended-serving-consent.json` (also `…/unattended-serving-runs`), `/logs/agent/sessions/.config.json`. What the CLI does with the consent file is unknown (it bears on owner question 1, unattended runs); the first trace holds none of these lookups (they fall in its untraced first 0.75 s, or follow from the decoy existing). No keychain, secret service or D-Bus path. Programs: `bash`, `git`, the CLI's own binary (as `rg`), `id`, `run-parts`, `head`, `cut`, `grep`, `awk`, `sed`, `cat`, `env`, `curl` (the probe). **Not tested:** an expired stored credential (a refresh would go to the vendor's OAuth host, which the allowlist refuses) |
| What if the model calls the placeholder tool? | `t2a-placeholder-low` / `token-placeholder-tool-normal-end` | The CLI answers with a tool result `is_error true` (its text names no such tool) and the session goes on to `completed` |
| Do the skills and agents listed in init reach the request? | `first_request.mentions` in `fixtures/requests/t2a-normal-low.json` (22 names: 17 skills and 5 agents) | **No distinctive name occurs** in the system, tool or message text. `verify` (system 2, tools 1), `run` (system 4, tools 5, messages 1) and `claude` (system 1, messages 1) do; they are ordinary words as well as names, and the counts keep no context, so reading them as words is a judgement the kept data cannot check |

**Paid extra usage** (`t2a-overage-low` / `token-paid-extra-usage-normal-end`). The stub answered every
response of the session (both were 200s) with `anthropic-ratelimit-unified-status: rejected`,
`…-overage-status: allowed`, `…-overage-in-use: true` and `…-representative-claim: five_hour`. The
stream gained one `rate_limit_event` `{status rejected, rateLimitType five_hour, overageStatus allowed,
isUsingOverage true, overageInUse true}`: the CLI emits the event when the state changes, not once per
response. The session went on and completed normally; its next request asked five-minute caching
(above).
- *Where the header names and the rule came from:* this implementer's reading of the CLI bundle 2.1.311
  (`isUsingOverage` is true when the status is `rejected` and the overage status `allowed` or
  `allowed_warning`; the overage-in-use header gives `overageInUse`). The bundle was downloaded to read
  its strings, never executed, and deleted; no vendor document was read for it.
- *What is not settled:* only this one combination of headers was recorded, so which header the CLI
  needs to turn `isUsingOverage` true is not isolated, and nothing here says what the vendor sends.

**Only a live request can still settle** (in addition to the token-mode list above):
- the real headers on a subscription response, and whether paid extra usage on the owner's plan arrives
  as these headers;
- the vendor's answer to this request shape with a subscription token: the ten betas, the system-role
  message, and the placeholder tool;
- what makes the CLI fall back to five-minute caching after a very large prompt, and whether it happens
  at real prompt sizes;
- token counts of the added system prompt, tool definitions and messages (the stub reports fixed usage).

## Task 2b: the 32 pinned images, measured and checked (no spend)

Run on 2026-11-14 by `image_check.py`, one image at a time in `tasks.json` order (vba-userform-port
first).
- Each image was pulled by digest with rootless Podman 4.9.3, then measured.
- Each agent image was then checked for withholding.
- The image was deleted before the next pull.
- Pulls ran on four CPUs at idle I/O priority.
- The only network use was the public registry.
- No container was started, and no model or provider was called.

There is one JSON line per image in `image_measure.json`. The totals come from `image_check.py totals`.

**Pull by digest works for all 32.**
- Each pull used the pinned reference as written (tag and digest), with `docker.io/` added in front.
  That prefix is the "full name" host-side step of D1: this host's registries configuration has no
  unqualified search registry.
- Every pull succeeded on its first attempt, and the stored image's repository digest equals the pinned
  one.
- No fallback was needed, so no image is a local build and no task carries a different configuration
  label.
- Pull times were 3 to 42 s each, 520 s in all.

### Withholding: what is checked

The check runs against the task's cached package. Before anything else, the package's content digest is
recomputed with Harbor's packager and must equal `digest_4_1_0` in `tasks.json`; a missing or different
package stops the run. Each agent container is created with `--network none` and never started. Its file
system is exported to a tar, and the tar is read on the host.

1. **By path, every member:** regular files, hard links, symlinks (and their targets) and directories.
   A member is a hit if it is a root `solution` or `tests`, or if its path ends in a package file's
   relative path under `solution/` or `tests/`.
2. **By SHA-256, every regular file,** against the package's `solution/` and `tests/` files. Empty files
   and files that the package's `environment/` also ships are left out.
3. **The canary**, in every regular file (below).
4. **Near copies, in every text file** that is not a byte-identical environment copy. The reference is
   the "distinctive lines": stripped lines of at least 25 characters that occur in a `solution/` or
   `tests/` text file, in no `environment/` file, and are not the canary line. Only the SHA-256 of each
   matched line is recorded, never the line.
   - A file is in a system path if it is under `/usr`, `/bin`, `/sbin`, `/etc`, `/lib`, `/lib32`,
     `/lib64`, `/libx32`, `/var/lib/dpkg` or `/var/lib/apt`. Language package directories count too:
     `site-packages`, `dist-packages`, `node_modules`, `.cargo/registry`, `.rustup`, `go/pkg/mod`,
     `gems`, `.npm`, `.cache/pip`, and a uv-managed Python under `.local/share/uv/python`.
   - So does every virtual environment: any directory that holds a `pyvenv.cfg`, with everything below
     it (coordinator ruling, 2026-11-14). The rule is by the file, not by the directory's name.
     gsea-proteomics, hof-topology-interpenetration and roy-polymorph-cn each have one, at `opt/venv`.
   - The verdict is "needs a look" for any match in a file outside these paths, and for 10 or more
     matched lines in a file inside them. Fewer than 10 inside them is noise.
   - **Why 10.** Over the 16 images, no system-path file has more than 6 matched lines. The 6 is a Node
     `package.json` under `usr/share/nodejs` in vba-userform-port, which shares lines with the
     solution's `package-lock.json`. Every other case is at most 3, mostly generic Python standard
     library lines such as a main guard. 10 is above everything observed. A planted copy of a solution
     file would share far more lines than that, unless the file is very short.
5. **Archives and git objects outside system paths** are opened when they are at most 64 MiB, and their
   members get checks 1 to 4.
   - This covers zip and wheel files, tar files of any compression, a `.gz` of a single file, and loose
     `.git` objects.
   - An archive inside an archive, a git pack, an unreadable archive and anything larger are listed as
     "not opened", with path and size.
   - Every `.git` directory outside system paths is listed and is "needs a look".
   - Archives inside system and language paths are neither opened nor listed (the intended scope).
   - A text file over 64 MiB (no NUL byte in its first 8 KiB) is never read by check 4, so it is listed
     (`large_text`, ledger item N3), with its size and whether it is an environment copy.
6. **Each layer of the image is walked**, deleted files included, in Podman's user namespace
   (`podman unshare`). Every entry, whiteouts included, is tested by path, and every regular file by
   SHA-256.

**Passes.**
- The first pass (checks 1 to 3, regular files only) was replaced in the file by the second, and its
  numbers are not in `image_measure.json`.
- Every record now in the file was written by the committed code, after the virtual-environment rule.
  All 16 agent images were checked again during the first oracle pass (below), each while its image was
  in the store for that pass, with the `large_text` listing added; the record says `pass` 5 or 6.
- **Large text files (N3): none.** No agent image holds a text file over 64 MiB, so check 4 skipped
  nothing for size.
- The verdicts are the ones the earlier records predicted under the final rule. The one change is
  roy-polymorph-cn: its two launcher scripts are now inside a virtual environment.
- The earlier passes are kept as `earlier_passes` summaries.

### Withholding: the result

**No solution or test material by path or SHA-256, in any of the 16 agent images, in the merged file
system or in any layer.**
- No file needs a look under the final rule.
- The two `.git` directories (bold in the table) are listed by rule. The coordinator ruled them not hits
  (below).

| Task | Path / digest hits | Layer walk (files, whiteouts) | Canary: copies / name-only / other | Near-copy files needing a look | Archives and git objects opened | `.git` dirs | Not opened | Highest system-path count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vba-userform-port | 0 / 0 | clean (31,289, 12) | 1 / 0 / 0 | 0 | 0 | 0 | 0 | 6 |
| vf2-speedup-networkx | 0 / 0 | clean (82,478, 0) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 3 |
| wal-recovery-ordering | 0 / 0 | clean (5,057, 0) | 15 / 0 / 0 | 0 | 0 | 0 | 0 | 2 |
| session-window-debug | 0 / 0 | clean (4,503, 8) | 8 / 0 / 0 | 0 | 0 | 0 | 0 | 2 |
| production-planning | 0 / 0 | clean (5,269, 8) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 2 |
| vpp-loss-divergence | 0 / 0 | clean (50,619, 64) | 2 / 0 / 0 | 0 | 0 | 0 | 0 | 3 |
| batched-eval-parity | 0 / 0 | clean (5,938, 2) | 17 / 0 / 0 | 0 | 0 | 0 | 0 | 1 |
| pretrain-shard-corruption | 0 / 0 | clean (23,603, 10) | 8 / 0 / 0 | 0 | 9 | **1** | 0 | 2 |
| gsea-proteomics | 0 / 0 | clean (7,771, 0) | 0 / 0 / 0 | 0 | 1 | 0 | 0 | 1 |
| lake-temp-glm | 0 / 0 | clean (29,734, 2) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 2 |
| sound-change-cascade | 0 / 0 | clean (6,834, 7) | 1 / 0 / 0 | 0 | 0 | 0 | 0 | 0 |
| hof-topology-interpenetration | 0 / 0 | clean (7,241, 0) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 1 |
| shadow-relay | 0 / 0 | clean (8,008, 3) | 0 / 0 / 0 | 0 | 23 | **1** | 0 | 1 |
| rs-archive-clone | 0 / 0 | clean (4,721, 2) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 3 |
| retro-console-soc | 0 / 0 | clean (17,465, 52) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 2 |
| roy-polymorph-cn | 0 / 0 | clean (18,590, 2) | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 1 |

**The three items that needed a look, and the coordinator's ruling (2026-11-14): none is a withholding
hit, and none drops a task.**
- **pretrain-shard-corruption, `app/.git`.** It is made by the environment's own Dockerfile (`git init
  /app`, then commits of the environment's files; its comment calls it a decoy history). All 9 objects
  are loose and were opened, and there is no pack. Four blobs hold the canary, and each is a
  byte-identical copy of an environment file. No blob matches a solution or test file by digest, and none
  holds a distinctive line.
- **shadow-relay, `app/.git`.** It is made by the environment's Dockerfile (`git init`, then a commit of
  the build's files, for the verifier's diff hook). All 23 objects are loose and were opened, and there
  is no pack. No digest hit, no canary and no distinctive line.
- **roy-polymorph-cn, `opt/venv/bin/f2py` and `opt/venv/bin/numpy-config`.** These are the console-script
  wrappers pip writes into a virtual environment. Each matched one distinctive line, which is a generic
  Python main guard that `solution/solve.py` and `tests/checks.py` also contain. Under the
  virtual-environment rule they are noise, because `opt/venv` holds a `pyvenv.cfg`.

**Name matches** are files with the same base name as a solution or test file, such as `README.md` or
`package.json`. They are recorded as information only and are not hits. `name_match_dirs` and
`name_match_names` give the top five by directory and by name. Of the 1,840 in vba-userform-port:
- 1,797 are Node `package.json` files, most of them under `usr/share`;
- 29 come from `shared/legacy_app`, which the package's `tests/legacy_app` mirrors.

**The canary.** The identifier was read at run time from each task's cached 4.1.0 package. It is in
neither this repository nor `image_measure.json`.
- **Not found** in 9 images: vf2-speedup-networkx, production-planning, gsea-proteomics, lake-temp-glm,
  hof-topology-interpenetration, shadow-relay, rs-archive-clone, retro-console-soc and roy-polymorph-cn.
- **Found** in 7 images, each time in a byte-identical copy of a file in the task's own `environment/`
  (counts in the table). In pretrain-shard-corruption, 4 of its 8 copies are blobs in `app/.git`.
  There is no name-only match and no other file.
- **Why the environment files carry it.** The benchmark marks its source files with the canary, and all
  16 packages carry it in `environment/` too (1 to 18 files each). Where a Dockerfile copies those files
  in, the agent sees them by design.
- **The coordinator's ruling (2026-11-14).** A canary in a byte-identical copy of an environment file is
  not a hit and drops no task.
- **A name-only match** would get "needs a look", never "clean". It would be recorded with its path, the
  environment file of that name, both sizes, whether the two are identical, and the shared lines other
  than the canary line.

### Sizes and disk

GB = 10^9 bytes.
- *Unpacked* is the store's size of the layers: Podman's image size, and per layer the diff size in the
  store's `layers.json`.
- *Compressed* is the registry's layer size, which is what was downloaded.
- *Shared before* counts the layers that images earlier in the table already had. So adding up the
  unpacked column counts those layers twice (26.96 GB over all 32). The totals below count each layer
  once.

| Task | Role | Digest | Compressed GB | Unpacked GB | Layers | Shared before: layers, GB unpacked | Pull by digest | Pull s | Withholding |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vba-userform-port | agent | `104fb670ee58` | 0.12 | 0.41 | 8 | 0, 0.00 | yes | 9 | clean; canary only in 1 byte-identical environment copies; near copies clean |
| vba-userform-port | verifier | `ce013facbe7c` | 0.55 | 1.54 | 17 | 6, 0.12 | yes | 28 | n/a |
| vf2-speedup-networkx | agent | `b90a92781095` | 0.54 | 2.11 | 6 | 0, 0.00 | yes | 34 | clean; canary not found; near copies clean |
| vf2-speedup-networkx | verifier | `a84e6fc87075` | 0.17 | 0.51 | 7 | 1, 0.08 | yes | 10 | n/a |
| wal-recovery-ordering | agent | `71d215eab08b` | 0.04 | 0.13 | 6 | 0, 0.00 | yes | 4 | clean; canary only in 15 byte-identical environment copies; near copies clean |
| wal-recovery-ordering | verifier | `627bc7812cd0` | 0.17 | 0.50 | 10 | 4, 0.13 | yes | 9 | n/a |
| session-window-debug | agent | `62d159cb3a81` | 0.09 | 0.23 | 10 | 4, 0.12 | yes | 3 | clean; canary only in 8 byte-identical environment copies; near copies clean |
| session-window-debug | verifier | `ae6248a5d486` | 0.17 | 0.50 | 11 | 4, 0.12 | yes | 6 | n/a |
| production-planning | agent | `51110ff01e23` | 0.07 | 0.19 | 12 | 0, 0.00 | yes | 4 | clean; canary not found; near copies clean |
| production-planning | verifier | `0f3eb5e73654` | 0.16 | 0.47 | 11 | 4, 0.13 | yes | 6 | n/a |
| vpp-loss-divergence | agent | `81611f7fdd8d` | 0.73 | 2.42 | 14 | 0, 0.00 | yes | 37 | clean; canary only in 2 byte-identical environment copies; near copies clean |
| vpp-loss-divergence | verifier | `460f7e259689` | 0.86 | 2.79 | 17 | 8, 0.57 | yes | 42 | n/a |
| batched-eval-parity | agent | `f00c28880710` | 0.09 | 0.25 | 11 | 1, 0.08 | yes | 5 | clean; canary only in 17 byte-identical environment copies; near copies clean |
| batched-eval-parity | verifier | `6b04e7760112` | 0.19 | 0.56 | 12 | 1, 0.08 | yes | 10 | n/a |
| pretrain-shard-corruption | agent | `ff18338c6eeb` | 0.34 | 1.14 | 18 | 4, 0.13 | yes | 20 | clean; canary only in 8 byte-identical environment copies; environment-built `.git`, opened, ruled not a hit |
| pretrain-shard-corruption | verifier | `336d1e81ebfa` | 0.39 | 1.30 | 11 | 4, 0.12 | yes | 22 | n/a |
| gsea-proteomics | agent | `e400f6486197` | 0.36 | 0.73 | 9 | 0, 0.00 | yes | 14 | clean; canary not found; near copies clean |
| gsea-proteomics | verifier | `43e108555adb` | 0.14 | 0.40 | 10 | 4, 0.13 | yes | 11 | n/a |
| lake-temp-glm | agent | `8f1f182ad639` | 0.44 | 1.46 | 10 | 1, 0.08 | yes | 31 | clean; canary not found; near copies clean |
| lake-temp-glm | verifier | `496fb5526ea1` | 0.52 | 1.69 | 14 | 2, 0.08 | yes | 34 | n/a |
| sound-change-cascade | agent | `95bd365954df` | 0.08 | 0.23 | 8 | 4, 0.12 | yes | 4 | clean; canary only in 1 byte-identical environment copies; near copies clean |
| sound-change-cascade | verifier | `8980723c9498` | 0.14 | 0.41 | 10 | 4, 0.12 | yes | 9 | n/a |
| hof-topology-interpenetration | agent | `a758f32e5d39` | 0.06 | 0.17 | 5 | 0, 0.00 | yes | 6 | clean; canary not found; near copies clean |
| hof-topology-interpenetration | verifier | `cc54700dda4c` | 0.14 | 0.40 | 9 | 4, 0.13 | yes | 11 | n/a |
| shadow-relay | agent | `584cd120342b` | 0.11 | 0.29 | 12 | 4, 0.13 | yes | 9 | clean; canary not found; environment-built `.git`, opened, ruled not a hit |
| shadow-relay | verifier | `864d9d5dc766` | 0.18 | 0.52 | 12 | 2, 0.08 | yes | 13 | n/a |
| rs-archive-clone | agent | `396a2f9f0af2` | 0.05 | 0.14 | 7 | 2, 0.08 | yes | 6 | clean; canary not found; near copies clean |
| rs-archive-clone | verifier | `a890aca2de72` | 0.26 | 0.75 | 8 | 1, 0.08 | yes | 17 | n/a |
| retro-console-soc | agent | `11b017483cf6` | 0.52 | 1.48 | 5 | 0, 0.00 | yes | 36 | clean; canary not found; near copies clean |
| retro-console-soc | verifier | `359a891415a2` | 0.63 | 1.81 | 7 | 1, 0.17 | yes | 42 | n/a |
| roy-polymorph-cn | agent | `ec42a0858ef1` | 0.30 | 0.90 | 10 | 1, 0.08 | yes | 17 | clean; canary not found; near copies clean |
| roy-polymorph-cn | verifier | `4606480cae2b` | 0.17 | 0.50 | 11 | 4, 0.13 | yes | 11 | n/a |

**Totals for the disk plan.** Each distinct layer is counted once, unpacked; the compressed size is in
brackets.
- **Block order.** D7 orders the blocks by a hash of a seed that is not frozen yet, and runs up to four
  attempts at once, so several blocks can be on disk together.
- **The per-block rows are therefore worst cases** over every choice of 2, 3 or 4 tasks. Any seeded order
  stays within them.

| Strategy | Layers | Store size |
| --- | --- | --- |
| All 32 kept for the tranche | 253 | **23.86 GB** (7.70 GB) |
| Only the 16 agent images kept (verifiers pulled per block) | 130 | **11.46 GB** (3.64 GB) |
| One block on disk (worst: vpp-loss-divergence) | 24 | **4.64 GB** (1.38 GB) |
| Two blocks on disk (worst: retro-console-soc, vpp-loss-divergence) | 35 | **7.76 GB** (2.47 GB) |
| Three blocks on disk (worst: lake-temp-glm, retro-console-soc, vpp-loss-divergence) | 57 | **10.84 GB** (3.40 GB) |
| Four blocks on disk (worst: those three and vf2-speedup-networkx) | 68 | **13.30 GB** (4.06 GB) |

**Free space.** The image store is on `/home`, at `~/.local/share/containers/storage`. Other agents were
writing to both disks throughout, so every figure below holds for its date only and drifts.
- **The first pass:** before its first pull, `/home` had 78.45 GB free and `/` had 57.00 GB. After its
  last delete they had 77.55 GB and 56.20 GB.
- **Room if all 32 are kept**, measured at 77.55 GB on 2026-11-14 around 13:00: about 53.7 GB left, 33.7
  GB above the tranche's 20 GB stop. Measured at 71 GB later that day (`df`): about 47 GB left, 27 GB
  above the stop. Neither allows for the four attempts' output, which was not measured.
- **The pull and the export are guarded.**
  - Before a pull, the script needs the image's compressed size plus its unpacked size to fit above the
    25 GB stop. When the unpacked size is not yet measured, it is estimated as four times the compressed
    size; the 32 images show 2.05 to 3.89 times.
  - Before an export, the image's unpacked size must fit in the same way.
  - An export tar is about the size of its unpacked image: 2.42 GB at most (vpp-loss-divergence). The
    tars' own sizes were not recorded.
- **Low point, from the checkpoints in `image_measure.json`** (before and after each pull, during each
  export, after each delete, over every pass kept there):
  - `/home` 68.25 GB, during the third pass's export of vf2-speedup-networkx;
  - `/` 51.43 GB, during the fourth pass's export of wal-recovery-ordering.
- **At the end of the regeneration** (`df -h`): `/home` 70 GB, `/` 50 GB.
- **Not in the file any more:** the first pass's export figures were overwritten (their low was
  72.18 GB on `/home` and 55.20 GB on `/`).

### First oracle pass on the pinned images (2026-11-14, no spend)

Plan D1's first pass: each task once, reference and untouched, load not controlled. Run by `oracle_check.sh`
(`GATE=none REPEATS=1 CONCURRENCY=1 CPUS=8-31 INSTALL=1`) from 16:18 to 18:36 PST, one task at a time in
`tasks.json` order, vba-userform-port first. Per task:
- both pinned images pulled by digest under their `docker.io/` full name;
- the pinned CLI installed once on the agent image by the harness's own path (`claude-code --install-only`,
  version 2.1.311): the public CLI was downloaded, no session started and no request reached any model API;
- one `oracle` trial (the reference solution) and one `nop` trial (untouched), each graded by the task's own
  verifier image;
- the withholding recheck of the agent image while it was in the store (above);
- both images deleted (never `-f`).
The harness ran with an empty environment: no credential of any kind. Per-trial records (outcome, phase
times, load, the egress sidecar's refused connections, each container's peak memory and affinity, image ids,
digests; no log text) are in `oracle_first_pass.json`; the logs stay in the cache directory.

**The overlay.** Each package's `task.toml` got the two agent-phase keys after `[agent]`: `network_mode =
"allowlist"` and D3's list as drafted (the relay, the Python, Node and Rust indexes, the Debian, Ubuntu and
Fedora mirrors: 13 names, no port, never the host's address). Its digest is `3f99fe3c…c4f6` for all 16
(`overlay_digest` in `tasks.json`). For every copy, removing the two lines gave back the package's
`task.toml` byte for byte.

| Task | Reference | Untouched | CLI install, setup s | Wall s (ref / untouched) | Load 1-min at start (ref / untouched) | Graded checks passed (ref / untouched) | Largest peak memory, GB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vba-userform-port | no reward (RewardFileNotFoundError) | no reward (RewardFileNotFoundError) | ok, 25 | 61 / 50 | 55 / 52 | - / - | 0.02 |
| vba-userform-port-uidfix | pass | fail (0) | (on the unchanged label) | 113 / 66 | 19 / 32 | 29 of 29 / 0 of 29 traces | 0.52 |
| vf2-speedup-networkx | pass | fail (0) | ok, 127 | 330 / 71 | 34 / 35 | 60 of 60 / 0 of 60 | 0.54 |
| wal-recovery-ordering | pass | fail (0) | ok, 155 | 537 / 71 | 34 / 15 | gates 3 of 3 / 1 of 2; suite 10 × 97 of 97 / not run | 0.40 |
| session-window-debug | pass | fail (0) | ok, 174 | 67 / 66 | 40 / 47 | 9 of 9 / 4 of 9 | 0.24 |
| production-planning | pass | fail (0) | ok, 162 | 98 / 61 | 63 / 52 | 20 of 20 / 1 of 20 | 0.31 |
| vpp-loss-divergence | pass | fail (0) | ok, 140 | 234 / 188 | 33 / 38 | 5 of 5 / 4 of 5 | 1.04 |
| batched-eval-parity | pass | fail (0) | ok, 171 | 327 / 107 | 48 / 35 | 5 of 5 / 0 of 5 | 0.47 |
| pretrain-shard-corruption | pass | fail (0) | ok, 178 | 409 / 106 | 41 / 22 | 12 of 12 / 4 of 12 | 1.57 |
| gsea-proteomics | pass | fail (0) | ok, 130 | 107 / 50 | 12 / 14 | 16 of 16 / 0 of 16 | 0.91 |
| lake-temp-glm | pass | fail (0) | ok, 119 | 379 / 71 | 32 / 39 | 1 of 1 / 0 of 1 | 0.77 |
| sound-change-cascade | pass | fail (0) | ok, 157 | 66 / 61 | 35 / 37 | 7 of 7 / 0 of 7 | 0.22 |
| hof-topology-interpenetration | pass | fail (0) | ok, 170 | 112 / 67 | 45 / 50 | 38 of 38 / 0 of 38 | 0.44 |
| shadow-relay | pass | fail (0) | ok, 156 | 66 / 61 | 56 / 48 | 9 of 9 / 2 of 9 | 0.23 |
| rs-archive-clone | pass | fail (0) | ok, 165 | 169 / 72 | 49 / 55 | 57 of 57 / 0 of 57 | 0.23 |
| retro-console-soc | pass | fail (0) | ok, 32 | 309 / 56 | 39 / 17 | 8 of 8 / 0 of 8 | 3.72 |
| roy-polymorph-cn | pass | fail (0) | ok, 121 | 71 / 61 | 52 / 45 | 3 of 3 / 0 of 3 | 0.27 |

**What the pass shows.**
- **All 15 tasks other than vba-userform-port pass both halves** on their pinned images, under the draft
  allowlist, at 1-minute load 11 to 63. That includes the six timing- or speed-sensitive tasks the plan
  names. One run under load says nothing about five quiet runs: the second pass decides.
- **vba-userform-port fails unchanged on the pinned images as on the local build.** Its verifier assigns a
  random uid up to about 10^9 and dies with `OSError: [Errno 22] Invalid argument`, so neither half writes a
  reward. Rootless Podman here maps 65,536 sub-ids (`podman unshare cat /proc/self/uid_map`).
- **The labelled variant (owner question 4) passes both halves**, built as follows:
  - Why a derived image: a pinned verifier image carries its own copy of the tests. The harness uploads no
    tests to it (Harbor's `bundled_tests`), so changing the package's `tests/app_worker.py` alone would
    change nothing.
  - The variant is the package with that one line changed (`secrets.randbelow(1000000000)` to
    `secrets.randbelow(55000)`), run on a verifier image derived from the pinned one by the same `sed`. That
    is one layer, and `podman image diff` shows only `/tests/app_worker.py` changed. The copy's
    `task.toml` names the derived image.
  - The variant's first run lost its untouched half to the harness. podman-compose 1.6.0's teardown (`down
    --rmi local --remove-orphans`) deletes images by two paths, both with `rmi --ignore --force <name>`:
    - `--rmi local`: a service whose compose `image:` string starts with `localhost/`, or that has a `build:`
      section and no `/` in the string (`is_local()`). The string is the one in `task.toml`, not the stored
      name: Podman stores every local image as `localhost/…` either way;
    - `--remove-orphans`: the image of every leftover container of the same compose project, whatever its
      name.
    The first derived image's `task.toml` string began with `localhost/`, so after the reference trial it was
    gone, and the untouched trial failed to start (`RuntimeError`, pull of the missing image).
  - The fix: the `task.toml` string has no prefix, and the variant was run again, both halves. The set-aside
    reference trial had also passed; both lost trials are kept outside the job tree.
  - Fix round 1 gave the variant a recorded identity ("The labelled variant's recorded image", below).
- **The CLI installs on all 16 pinned agent images**, with 25 to 178 s of agent setup:
  - vba-userform-port's image already had Node;
  - retro-console-soc's Fedora image used `dnf`;
  - the harness's install command ends with `claude --version` under `set -euo pipefail`, so a missing binary
    would have failed it.
- **The CPU set reaches every container.** Each sample read the affinity of every process in each
  container's cgroup: the agent's container, its egress sidecar, the verifier's container and, where the
  verifier has no network, its sidecar. Every value was `8-31`. A verifier container was sampled in 32 of the
  34 graded trials; the two vba-userform-port unchanged verifiers ended within a sampling interval.
- **Egress:** only gsea-proteomics's reference had refused connections. There were 8, to two addresses on
  port 443, one per run of the bundled GSEA tool (8 runs), and the reference passed 16 of 16. The log names
  addresses, not hosts. The review named the host: `www.gsea-msigdb.org` resolves today to exactly those two
  addresses, and the GSEA jar holds `https://www.gsea-msigdb.org/gsea`. So the tool calls home at start, and
  the task does not need it. `tasks.json` records this beside the task (`egress_refused`), so that no later
  reader adds the host to `extra_hosts`. Its index traffic was allowed.
- **What the egress logs show of the allowlist: only that it was in force for gsea-proteomics.** A sidecar's
  log holds its start (`initial egress policy is public`, `ok: allow all egress`) and its refusals. The
  harness switches the agent phase to the allowlist by `compose exec … network-policy allow …`, and that
  command's `ok: allowlist applied` is not in the log. For the other 15 tasks the allowlist rests on the
  overlay (each copy minus the two lines is its package's `task.toml`) and on the harness raising when the
  switch fails. From fix round 1 on, `oracle_check.sh` records each sidecar's `network-policy show` (mode and
  number of hosts) in `samples` whenever it changes, and `summarize.py` keeps it as `policies`.
- **Graded checks:** every verifier except vba-userform-port's unchanged run wrote a CTRF report, and its
  counts are in the records. Two tasks grade by something else, so the table gives their own counts:
  - vba-userform-port's CTRF holds one pytest wrapper that only computes the score (1 of 1 in both halves).
    The graded checks are the hidden traces (`verifier/trace_summary.json`): 29 of 29 and 0 of 29. Every
    untouched trace fails with `Missing /workspace/generated_app/run.sh`;
  - wal-recovery-ordering runs gates first (`ctrf_gates.json`), then its suite ten times. The untouched run
    passes the structural gate, fails the isolated recovery gate and stops there (`-x`), so its suite never
    runs.
- **Memory and disk.** The largest cgroup peak was 3.72 GB (retro-console-soc's verifier). The job tree is
  36 MB for all 50 trials. During any trial, free space fell by at most 2.74 GB on `/home` and 2.46 GB on
  `/`, with other sessions writing at the same time. The lowest readings were 31.0 GB on `/` and 68.6 GB on
  `/home`, above the 25 GB stop.

### The labelled variant's recorded image (Task 2b fix round 1, 2026-11-14, no spend)

**Ruling.** The coordinator accepts vba-userform-port-uidfix as the labelled reading of D1's one-line verifier
change, for use only if the owner does not run `podman system migrate` (owner question 4 stays open; nothing
here runs it).

**Built once.** `uidfix_variant.py` built the verifier image once and recorded it under `variant` in
vba-userform-port's `tasks.json` entry:
- base: the pinned verifier image, pulled by digest (`sha256:ce013fac…2a28`, image id `cb25df7d…073d`, the
  id `tasks.json` already held);
- recipe: `FROM docker.io/<pinned ref>` and one `RUN`, which refuses unless exactly one line of
  `/tests/app_worker.py` holds the bound and then runs the `sed`. It was built with no network and no pull;
- image id `01b5f971…67ca`, under two names: `lh-oracle/vba-userform-port-uidfix:verifier` (the one the
  variant's `task.toml` uses) and `lh-keep/vba-userform-port-uidfix:verifier` (in no compose file);
- `/tests/app_worker.py`: SHA-256 `d30b3eaf…6df7` before, which is also the package's file byte for byte,
  and `f760628d…cf2a` after. The diff is line 55, `randbelow(1000000000)` to `randbelow(55000)`;
- file by file, only `tests/app_worker.py` differs. Both images were exported from a created, never started
  container and compared by kind, mode, owner, link target and SHA-256, modification times aside.
  `podman image diff` lists `C /tests` (the directory's modification time, from `sed -i`'s rename) and
  `C /tests/app_worker.py`.

**The guard.** podman-compose's teardown deletes an image by the name its container used (`rmi --ignore
--force <name>`); while a second name holds the image, that only untags. `oracle_check.sh`:
- checks the recorded image id before each launch of the label;
- gives the compose name back from the keeper if it is missing;
- refuses when the copy's changed file is not the recorded one;
- never builds or deletes the variant.

Deleting it is a manual step: `podman rmi` of both names, then the `variant` record. The image and its base
(the pinned verifier image) are in the store now.

**What the second pass must check before running this label four at once.**
- Both names give the recorded id (`podman image inspect -f '{{.Id}}'`).
- A teardown can still untag the compose name while a sibling trial of the label is in its agent phase. That
  happens only through `--remove-orphans`, on a trial's own leftover containers. The sibling's verifier would
  then fail to start with an error, and `summarize.py` counts that as no evidence, never as a pass or a fail.
  The same path can force-remove a shared pinned image by name, together with a sibling trial's container
  (review m7). The script's id check stops the next launch (exit 6) when an image is gone.
- So run one round of the label four at once first, and check its errors. If an image went, run the label's
  trials one at a time.

**Rerun on the recorded image** (`oracle_check.sh`, `GATE=none REPEATS=1 CONCURRENCY=1 CPUS=8-31`, 19:52 PST;
records in `oracle_uidfix_recorded.json`):
- the reference passes 29 of 29 hidden traces (reward 1) in 119 s;
- untouched gets reward 0 and 0 of 29 traces in 62 s;
- 1-minute load 57.9 and 39.5 at the two starts;
- nothing was built, and `summarize.py` prints `qualifies`.

The sidecar's sampled policy shows `allow-all` before and after the agent phase. The oracle's agent phase
lasted 6 s and fell between two samples.

### The stops, checked on the variant (Task 2b fix round 1, no spend)

`oracle_check.sh` ran the variant with `WALL_BOUND_S=45`, and the script got SIGTERM 30 s into the untouched
trial:
- **The reference trial stopped at its wall bound** (`stop=wall bound 45s`). Harbor got SIGTERM, cancelled the
  agent phase (`CancelledError`), took its containers down and exited 130, 61 s after the trial's start.
- **The untouched trial stopped by the request** (`stop=signal`). The script's trap created `$JOBS/.stop`, and
  the follower then stopped the harness. The verifier had started as the signal came; Harbor let it finish
  (reward 0 in `result.json`) and exited 130 after 37 s.
- **Nothing was left:** no container or network named after either trial, so the script had nothing to
  remove. `summarize.py` lists both runs as `stopped: …`, no evidence.
- **The sampled policy** of the reference, stopped in its agent phase, shows `controlled egress` with 13
  hosts.
- **Not captured:** the script's exit code. The driver printed `$?` after a command substitution; the unit
  test covers exit 5.

## Fixtures

**Stream fixtures** (`fixtures/*.json`) are cut by `cut_fixture.py` from one trial. They keep:
- the init event and the last four stream events;
- the number of events and of `api_retry` events;
- the harness's exception class, the CLI's exit code, the trial's `agent_result` and `verifier_result`;
- the harness's exception message, when there is no stream and the class is `RuntimeError` (harness
  text; D5 row 1 reads it).

Model text, tool input and tool output are dropped. CLI-made text is kept: a `<synthetic>` message, or an
error or result string that a classification rule may match. Home paths become `<home>` (the
container's `/home/claude` is kept), IPv4 addresses `<address>` and a fake slot token `<fake slot token>`.

**Request fixtures** (`fixtures/requests/<recording>.json`, one per local recording with a stub log, 77
in all) are cut by `cut_fixture.py requests` from the stub's `stub.jsonl`. They hold the distinct request
shapes, plus one row per request: `[shape, status, messages, seconds since the first request, stub fault
mode]`. A shape keeps:
- the method and path, and every header name;
- the values of `anthropic-beta`, `anthropic-version`, `content-type` and `x-app`, and the user agent's
  product token;
- `model`, `output_config.effort`, `max_tokens`, `stream`, and the names of the other body fields;
- the declared tool names and server-tool types;
- each system block's length and `cache_control`.

They never hold system or message text, `metadata` (a container's device and session ids), or a
credential: `x-api-key` and `authorization` become `<dummy>`, and an authorization keeps its scheme. The
Task 1 request logs predate the system-block logging, so their shapes have an empty `system`. The
`t2a-*` request fixtures add the tool definitions' lengths and cache marks, a sixth row element (the
cache marks on message blocks), `first_request` and `bearer_matches` ("Task 2a"). They also hold key sets,
never values (re-cut in Task 4's fix round 2 from the same files, whose digests did not change):
- per shape, `body_keys` (the body's top-level keys; `messages`, `system` and `tools` when not empty, since the
  stub's log does not tell an empty list from an absent one), and per declared tool `tool_keys` and
  `input_schema_keys`, the top-level keys of its definition and of its `input_schema`. These are read from the
  CLI's own record of the request shape in the recording's session files (`api-request-shape` entries under
  `jobs/*/*/agent/sessions/projects/`), joined to the sent tool by name and JSON length (`tool_chars`); a tool
  with no single match gets `null`. Every tool of every `t2a-*` shape matched;
- per fixture, `message_block_keys`: by block type, the key sets of sent message blocks whose session
  transcript block of the same type and JSON length (`chars`, less a cache mark the stub saw) is the only one;
  `message_block_keys_unrecorded` counts the rest. Every `tool_use` and `tool_result` block matched; no text
  block can (a text block's `chars` is its text's length only).

`make_allowlist.py` builds the passthrough's allowlist from these key sets of the `t2a-*` token-mode shapes.

**After-limit fixtures** (`fixtures/after-limit/<recording>.json`) are cut by `cut_fixture.py
after-limit` from a timed-out trial and its recording's `stub.jsonl`: the time the agent phase ended,
the number of requests after it, the last one's delay, their statuses and bearer checks, and the
distinct `<tool_use_error>` texts of the stream (CLI text); no other tool output.

**Trace fixtures** (`fixtures/traces/<recording>.json`) are cut by `cut_fixture.py trace` from the
`strace` files of a recording run with `STRACE=1` or `DECOY=1`. They keep each path the traced processes
named, with the calls made on it and their results (`ok` or the errno), the programs executed, and the
number of traced processes; never arguments other than paths, nor any data read or written. When the
trace holds the CLI's own `execve` (`cli_started_in_trace`), only the CLI and its children from that
call on are kept: the host-side `podman exec`, `conmon` and `crun` are dropped. A decoy recording's
fixture adds `decoy`: the canary, how many requests carried the slot's token, how many the stub watched
for the canary and how many named it, and which files of the recording hold it. Its request fixture
counts the canary under `<canary>`, never its value.

What each stream fixture supports:

| Fixture | Claim |
| --- | --- |
| `token-three-tools-normal-end`, `-medium`, `-high`, `stub-budget-stop-…`, `stub-refusal-…`, `stub-output-limit-…`, `stub-context-limit-…`, `stub-context-limit-after-compaction-…`, `stub-timeout-…`, `token-usage-limit-…`, `token-unauthorized-…`, `token-no-credential-…`, `token-forced-empty-…` | The D5 endings in the ladder's configuration ("Task 2a") |
| `stub-rate-limit-retry-after-…`, `stub-rate-limit-…`, `stub-overloaded-…`, `stub-server-error-…`, `stub-slow-first-byte-…`, `stub-dropped-stream-recovered-normal-end`, `stub-transient-faults-recovered-normal-end` | Provider faults in the ladder's configuration |
| `passthrough-cap-…`, `-total-…`, `-stopped-…`, `-model-…`, `-tool-…`, `-path-…`, `-unknown-token-…`, `-unknown-token-first-request-…` | The seven passthrough refusals in the 403 form, and one on the session's first request |
| `token-placeholder-tool-normal-end`, `token-paid-extra-usage-normal-end` | A call of the placeholder tool; paid extra usage |
| `token-decoy-credential-normal-end` (with `fixtures/traces/t2a-strace-decoy-low.json`) | A session with a decoy credential file in the CLI's config directory, traced from the CLI's start |
| `simple-mode-stub-normal-end`, `simple-mode-stub-budget-stop-…`, `simple-mode-stub-refusal-…`, `simple-mode-stub-output-limit-…`, `simple-mode-stub-context-limit-…`, `simple-mode-stub-context-limit-after-compaction-…`, `simple-mode-stub-timeout-…` | The same endings in simple mode ("The endings again") |
| `stub-simple-mode-normal-end` | Task 1's first look at `CLAUDE_CODE_SIMPLE=1`: three tools in init (D2 row 1) |
| `simple-mode-stub-rate-limit-retry-after-…`, `simple-mode-stub-rate-limit-…`, `simple-mode-stub-overloaded-…`, `simple-mode-stub-server-error-…`, `simple-mode-stub-slow-first-byte-…`, `simple-mode-stub-dropped-stream-recovered-normal-end`, `simple-mode-stub-transient-faults-recovered-normal-end` | Provider faults in simple mode |
| `simple-mode-passthrough-cap-…`, `simple-mode-passthrough-total-…`, `simple-mode-passthrough-stopped-…`, `simple-mode-passthrough-model-…`, `simple-mode-passthrough-tool-…` | The passthrough's refusals in simple mode (the first five; model and tool as 404 and 400) |
| `token-simple-mode-…`, `twenty-tools-token-normal-end`, `first-token-three-tools-normal-end`, `twenty-tools-token-usage-limit-…`, `twenty-tools-token-usage-limit-watchdog-…`, `twenty-tools-token-unauthorized-…`, `token-one-hour-cache-writes-normal-end`, `simple-mode-stub-usage-limit-headers-key-mode-…` | Token mode's first look (twenty tools, and the first three-tool run), and the key-mode contrast for the usage limit |
| `public-normal-end`, `public-refusal-AgentSafetyRefusalError` | The public row's stream forms (D2, D5): a pass (reward 1) and a refusal |
| `pre-session-agent-install-RuntimeError`, `pre-session-network-switch-RuntimeError` | Pre-session failures (D5): no stream, `RuntimeError` |

**The `twenty-tools-*` set is kept.** It records the same endings with the CLI's default tools (Task 1's
recordings: `normal-low`, `budget-medium`, `refusal-high`, `max-tokens-low`, `context-low`,
`context-late-low`, `timeout-low`), plus three behaviours that exist only with those tools:
- a background subagent (`…-subagent-background-normal-end`);
- a budget stop inside a foreground subagent that asked for model `fable` and effort `max`
  (`…-budget-stop-in-subagent-…`);
- web tools (`…-web-tools-normal-end`).

These back the D2 rows on effort, subagents and the model pin, and the D3 row on web tools. They are also
the evidence that the forms do not depend on the tool set. The token-mode ruling runs the CLI outside
simple mode; its own endings are now recorded with three tools ("Task 2a").
