# Recordings of the pinned CLI (Tasks 1 and 2 of the long-horizon plan)

Evidence for the [long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md)'s
frozen rules, recorded 2026-11-13 on this machine. No model or provider call was made: the real CLI ran
inside a rootless Podman task container against `stub_api.py` on the host, with a dummy key (or, for the
token-mode set, an obviously fake OAuth token) and the agent phase on an allowlist that does not list the
vendor's API. Task 2's probes are in their own section at the end. `recordings.json` names every recording with
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
experiments/long_horizon_tasks/record.sh probe-relay-oracle normal oracle --disable-verification
experiments/long_horizon_tasks/record.sh s3-budget-medium budget claude-code --ak version=2.1.311 \
  --ae CLAUDE_CODE_SIMPLE=1 --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 --disable-verification \
  --effort medium --ak max_budget_usd=0.05                     # the other runs: recordings.json
python -I experiments/long_horizon_tasks/cut_fixture.py <trial dir> "<source>" fixtures/<name>.json
python -I experiments/long_horizon_tasks/price_check.py $LH/recordings/archives/*/x
```

`record.sh` now uses the relay route (stub on a unix socket, `relay` on the allowlist). The Task 1
recordings (names without an `s3-`, `f-`, `pt-` or `tok` prefix) were made by its earlier form, with the
stub on the host's address and that address on the allowlist; the plan has since rejected that route.

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
| D4 (Task 2) | The relay route keeps the agent to the relay and leaves the verifier without it | (a) to (d) below | Confirmed |
| D4 (Task 2) | Cache writes cost 0.20 per million | The CLI prices five-minute writes at 0.125 and one-hour writes at 0.20 (archives; `*-cache-writes`); key mode asks for five minutes, token mode for one hour | Contradicted for key mode |
| D5 (Task 2) | Provider faults end in their own harness classes | 429: `ApiRateLimitError`; 500: `ApiInternalServerError`; 529 and a stalled first byte: `UnknownApiError`; each after about three minutes of the CLI's own retries | Partly: a 529 is not told from other faults by its class |
| D5 (Task 2) | A passthrough refusal ends the attempt at once | 403 `permission_error` with `x-should-retry: false`: no retry, message kept in the result; 404 and 400 forms are retried and the 404's message is lost | Confirmed for the proposed 403 form |
| D4 (Task 2, owner ruling) | The CLI can run on a subscription token in the public row's configuration | Simple mode reads no OAuth token: no request is sent, `AgentAuthenticationError` | Contradicted; key mode with a dummy key and a header-swapping passthrough keeps the configuration |
| D2 / D5 (Task 2) | Task content equals the checked copies | 4.1.0 adds prebuilt, digest-pinned agent and verifier images; 7 of 16 tasks changed from the public row's 4.0.0 | Contradicted (see Task content) |

The key's value appeared in no kept file. The harness's exception text quotes the container command,
which carries the environment (`-e NAME=value`); here truncation happened to cut the key out, which a
launcher must not rely on.

## Task 2 probes (no spend)

### The relay route (plan D4, route B)

`relay-compose.yaml` adds a service `relay` (socat, pulled by digest) with its own `networks` entry; it
forwards TCP 8080 to `/run/lh/passthrough.sock`, a directory bind-mounted into the relay alone, where the
stub listens on a unix socket. The allowlist is `relay`, `pypi.org`, `files.pythonhosted.org`.

| Probe | Recording | Result |
| --- | --- | --- |
| (a) The harness and podman-compose accept the extra service and leave it outside the sidecar's namespace | `probe-relay-oracle` (`containers.txt`) | Held: `relay` runs on the compose bridge network; `main` runs in `container:<sidecar>` |
| (b) The agent reaches `relay` by name through the proxy, and nothing new | `probe-relay-oracle` | Held: `relay` resolves (10.89.0.3), `http://relay:8080/…` reached the stub. Every one of the host's 39 listening TCP ports was refused at the host's address, at the network gateway and at 10.0.2.2 (116 proxy denials in the egress log; the 117th connection, TCP 53 to the gateway's name server, passes by the sidecar's DNS rule and returned nothing). The code host and the vendor's API stay refused; the package index answers |
| (c) The socket is mounted into the relay alone | `probe-relay-oracle`, every later run | Held: `relay` has the one bind mount; `main` and the sidecar have none; `/run/lh` is absent inside the agent's container |
| (d) The verifier's environment has no relay | `probe-relay-nop`, `s3-timeout-low` | Held: the verifier runs in its own compose project (`…__verifier__trial_main_1`, bridge, no mounts) with no `relay` service |

What the agent can still reach: `relay:8080` (and so the passthrough), the allowed package indexes, name
lookups at the network's name server, ICMP, and its own network namespace (the sidecar's). Not the host,
not the vendor's API. Not probed: whether the verifier, which has its own network, could reach the
relay's address directly.

### The endings again, with three tools, through the relay

`CLAUDE_CODE_SIMPLE=1`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, CLI 2.1.311: every init event lists
exactly `Bash, Edit, Read`. The fixtures named in the plan's D5 now hold these recordings; the twenty-tool
ones keep their content under a `twenty-tools-` prefix.

| Ending | Recording / fixture | Recorded fields | Harness class, exit |
| --- | --- | --- | --- |
| Normal | `s3-normal-low` / `stub-normal-end` | `completed`, `is_error false`, `end_turn` | none, 0 |
| CLI budget | `s3-budget-medium` / `stub-budget-stop-…` | `budget_exhausted`, `error_max_budget_usd`, result `usage` zero, `modelUsage` right | `NonZeroAgentExitCodeError`, 1 |
| Refusal | `s3-refusal-high` / `stub-refusal-…` | one retry on the same model, then `model_refusal_no_fallback`; `api_error`, `stop_reason refusal` | `AgentSafetyRefusalError`, 1 |
| Output limit | `s3-max-tokens-low` / `stub-output-limit-…` | three retries; `api_error`, `api_error max_output_tokens` | `OutputTokenExceededError`, 1 |
| Context limit | `s3-context-low`, `s3-context-late-low` / `stub-context-limit-…` | `prompt_too_long` (`api_error_status 400`); after a failed compaction `blocking_limit` | `NonZeroAgentExitCodeError`, 1 |
| Time limit | `s3-timeout-low` / `stub-timeout-…` | no result event; the verifier ran (reward 0) | `AgentTimeoutError` |

The forms equal the twenty-tool ones. One difference: with three tools a standalone `sleep 30` runs (the
twenty-tool CLI refused it), so the timeout session made 6 requests in 148 s instead of 1,071.

### Provider faults

Every persistent fault was answered from the second request on; the first turn succeeded.

| Fault (recording / fixture) | What the CLI did | Final fields | Harness class, exit |
| --- | --- | --- | --- |
| 429 with `retry-after: 5` (`f-rate-limit-retry-after` / `stub-rate-limit-retry-after-…`) | 10 retries; waits of 5 s while the header held, then backoff to about 40 s; gave up after 197 s | `api_error`, `is_error true`, `api_error_status 429`, text `API Error: Request rejected (429) · <message>` | `ApiRateLimitError`, 1 |
| 429 without it (`f-rate-limit` / `stub-rate-limit-…`) | 10 retries, backoff 0.5 s doubling to about 37 s; 184 s | as above | `ApiRateLimitError`, 1 |
| 529 (`f-overloaded` / `stub-overloaded-…`) | 10 retries, 181 s | `api_error_status 529`, text `API Error: 529 Overloaded. … check your inference gateway (relay:8080).` | `UnknownApiError`, 1 (the harness pattern expects `API Error: Overloaded`) |
| 500 (`f-server-error` / `stub-server-error-…`) | 10 retries, 180 s | `api_error_status 500`, text `API Error: 500 Internal server error. …` | `ApiInternalServerError`, 1 |
| Stream cut after the first block (`f-drop` / `stub-dropped-stream-recovered-normal-end`) | one streaming retry (`api_retry`, `error unknown`), then a **non-streaming** request (`stream false`, `max_tokens 64000`), which the stub also served | `completed`, `is_error false`: the session went on | none, 0 |
| First byte after 120 s (`f-slow` / `stub-slow-first-byte-…`) | every attempt ended after about 15 s with a reset connection; 10 retries, 325 s | `api_error`, `api_error_status null`, text `API Error: Connection dropped (ECONNRESET). Check the gateway set in ANTHROPIC_BASE_URL…` | `UnknownApiError`, 1 |
| 429, 529, 500 once each, then success (`f-transient` / `stub-transient-faults-recovered-normal-end`) | three retries, 6 s | `completed` | none, 0 |

- Each retry emits a stream event `system/api_retry` with `attempt`, `max_retries` (10), `retry_delay_ms`,
  `error_status` and `error` (`rate_limit`, `overloaded`, `server_error`, `unknown`); a normal ending can
  therefore contain recovered faults.
- Usage: failed requests add nothing to `modelUsage` or the session file. A cut stream does: the CLI
  counted both cut streams' start-of-message usage (`modelUsage` input 4,000, output 202) while the session
  file holds the two complete messages (2,000 and 200). Settlement's largest-figure rule takes the CLI's.
- Whether the 15 s of `f-slow` is the CLI's own first-byte window or a hop of the route (socat, the proxy)
  was not separated.

### The passthrough's refusals (forms proposed; the stub returned them)

| Refusal (recording / fixture) | Form sent | What the CLI did | Final fields | Harness class, exit |
| --- | --- | --- | --- | --- |
| Slot at its cap (`pt-cap` / `passthrough-cap-…`) | 403 `permission_error`, `x-should-retry: false`, message `lh-passthrough: slot cap reached` | no retry; ended in under 1 s | `api_error`, `api_error_status 403`, text `Failed to authenticate. API Error: 403 lh-passthrough: slot cap reached` | `UnknownApiError`, 1 |
| Tranche total (`pt-total`) | same, `… tranche total reached` | same | same with that message | `UnknownApiError`, 1 |
| Tranche stopped (`pt-stopped`) | same, `… tranche stopped` | same | same with that message | `UnknownApiError`, 1 |
| Another model (`pt-model`) | 404 `not_found_error`, `x-should-retry: false` | one non-streaming retry, also refused | `api_error_status 404`, text `There's an issue with the selected model (claude-haiku-5-5)…` (the passthrough's message is lost) | `NonZeroAgentExitCodeError`, 1 |
| A provider-side tool (`pt-tool`) | 400 `invalid_request_error`, `x-should-retry: false` | two retries, each dropping beta headers | `api_error_status 400`, text `API Error: 400 lh-passthrough: provider-side tool refused` | `UnknownApiError`, 1 |

**Proposed form for every passthrough refusal:** HTTP 403, `{"type":"error","error":{"type":"permission_error","message":"lh-passthrough: <reason>"}}`
and `x-should-retry: false`. It was the only form recorded that the CLI did not retry, and its message
reaches the result text verbatim, so the launcher can read the reason from the result as well as from the
passthrough's log. Its harness class (`UnknownApiError`) is the class of a 529, so the class decides
nothing; `api_error_status 403` plus the `lh-passthrough:` prefix does. The model and tool refusals were
recorded with 404 and 400 only; that 403 ends them the same way is inferred, not recorded.

### Prices (`price_check.py` over the three public archives)

Request by request (one row per message id), the rule **5-minute cache write at 0.125 per million and
every rate five times above 100,000 prompt tokens** (prompt = input + cache read + cache write) reproduces
the CLI's three totals exactly: USD 0.120039925, 2.617723155 and 0.746610645. The table as frozen
(cache write 0.20, the one-hour rate) gives 1.05 to 1.11 times; a 200,000 threshold gives 0.56 to 0.88
times; no long-prompt rate gives 0.23 to 0.62 times. The threshold lies between 98,828 and 101,144 prompt
tokens (the closest requests on either side). Nothing stays unexplained on these three. Not settled: the
one-hour write rate (no archive has one), and the model's real prompt limit (the largest recorded prompt
is 443,427 tokens; `modelUsage.contextWindow` says 1,000,000, and no archive reached a limit).

### Task content at 4.1.0 (`tasks.json`)

The 16 packages were fetched by their 4.1.0 digests from the benchmark hub's public storage, and each
digest was recomputed with the harness's own packager: all 16 match. Against the copies the feasibility
check used (`harbor-framework/terminal-bench` at `adf10d2b`):

- Instruction, environment, solution and tests are identical for all 16.
- `task.toml` differs for all 16, and only by additions: `[environment] docker_image =
  "harborframework/terminal-bench:<task>-environment-…@sha256:…"` and a `[verifier.environment]` table
  (CPUs, memory, storage, build timeout, `docker_image` of a prebuilt verifier image; `allow_internet =
  false` for batched-eval-parity and lake-temp-glm). Two tasks also gain `mcp_servers = []`.
- Files only in the checked copies, not in the packages: `LICENSE.md` (gsea-proteomics,
  hof-topology-interpenetration, roy-polymorph-cn), `THIRD_PARTY_NOTICES` (retro-console-soc),
  `.gitignore` (rs-archive-clone), `environment/.dockerignore` (shadow-relay).
- So 4.1.0 runs **prebuilt images pinned by digest** for both the agent and the verifier, where the
  oracle check built them from the Dockerfiles. The checked copies' oracle evidence therefore rests on
  locally built images, not on the pinned ones.
- The public row's trials ran **4.0.0** content (their task hashes are the 4.0.0 digests). 4.0.0 and
  4.1.0 are identical for 9 of the 16 (gsea-proteomics, hof-topology-interpenetration,
  production-planning, retro-console-soc, roy-polymorph-cn, rs-archive-clone, shadow-relay,
  vf2-speedup-networkx, vpp-loss-divergence). The other 7 changed their verifier tests between the two
  (batched-eval-parity, lake-temp-glm, pretrain-shard-corruption, session-window-debug,
  sound-change-cascade, vba-userform-port, wal-recovery-ordering), and all but wal-recovery-ordering
  also their agent environment (Dockerfile, a uv lock). Instructions and reference solutions did not
  change. For those 7 the public per-task counts were measured on another environment.

### Token mode (owner ruling: subscription only)

Recorded with `AUTH=token record.sh …`: the harness's `CLAUDE_FORCE_OAUTH=1` route, so the CLI got
`CLAUDE_CODE_OAUTH_TOKEN=lh-fake-oauth-token-not-real`, an empty `ANTHROPIC_API_KEY`, and the base URL
`http://relay:8080`; same CLI 2.1.311, same relay, same allowlist. `DEBUG=1` wrote the CLI's debug log.

| Question | Recording | What it shows |
| --- | --- | --- |
| Token mode in the three-tool configuration (`CLAUDE_CODE_SIMPLE=1`) | `tok-normal-404`, `tok-normal-401`, `tok-usage-limit-60s`, `tok-usage-limit-4h` / `token-simple-mode-AgentAuthenticationError` | **It does not run.** The CLI sent no request at all (the stub logged none, the egress log has no connection): `Could not resolve authentication method…`, result `Not logged in · Please run /login`, `terminal_reason api_error`, `is_error true`, `api_error_status null`, cost 0, `modelUsage {}`, init `apiKeySource none`; harness class `AgentAuthenticationError`, exit 1. The CLI's own help says why: simple mode's "Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper via --settings (OAuth and keychain are never read)" |
| Hosts and paths, default tools | `tok20-normal-404`, `tok20-normal-401`, `tok20-traffic-on`, `tok20-usage-limit-*`, `tok20-unauthorized` | The base URL is honoured: every request the CLI made went to `relay:8080`, path `/v1/messages?beta=true`, and nowhere else. The only other connection in each egress log is the stub's own probe command (`curl https://api.anthropic.com/v1/messages` run by the Bash tool), refused by the proxy: the vendor stays unreachable inside the same session |
| Extra endpoints (profile, usage, refresh, telemetry) | same; the stub answered every other path 404 (`tok20-normal-404`) or 401 (`tok20-normal-401`) | **None was called**, through the base URL or elsewhere. The harness always sets `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; the debug log shows `[Bootstrap] Skipped: Nonessential traffic disabled` and `[servedCatalog] off (essential_traffic)`, and `--ae CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=0` did not turn that off (`tok20-traffic-on`). The 404 and 401 variants therefore end alike. From the bundle (not recorded): the profile fetch would go to `https://api.anthropic.com/api/oauth/profile`, a fixed OAuth host rather than the base URL, so the allowlist would refuse it |
| Headers | `tok20-normal-404` against `key20-normal-debug` (key mode, same tools) | Token mode sends `authorization: Bearer <token>` and no `x-api-key` (key mode: `x-api-key`, no `authorization`); adds the betas `oauth-2025-04-20` and `extended-cache-ttl-2025-04-11`. Same user agent (`claude-cli/2.1.311 (external, sdk-cli)`), `x-app: cli`, the same other headers |
| Body | same, and `tok3-normal` against `key3-normal-system` | Same fields (`model`, `metadata.user_id` with `device_id`, an empty `account_uuid`, `session_id`; `max_tokens`, `thinking`, `context_management`, `output_config`, `stream`), same tool list for the same tools. Same identity block (`You are a Claude agent, built on Anthropic's Claude Agent SDK.`) after the `x-anthropic-billing-header` block. In token mode the system blocks carry `cache_control {"type":"ephemeral","ttl":"1h"}`; in key mode `{"type":"ephemeral"}` (five minutes) |
| Three tools without simple mode | `tok3-normal` (`--ak disallowed_tools=` the other 18) / `token-three-tools-normal-end` | Init lists `Bash, Edit, Read`, but the request carries a fourth tool (`DeferredToolPlaceholder`) and the default system prompt (8,830 characters) where simple mode sends 26 (`CWD: /app\nDate: …`). It is not the public row's configuration |
| Init and result | every token run | Init `apiKeySource` is `none` (key mode: `ANTHROPIC_API_KEY`); no other init field differs. The result event has the same keys; `total_cost_usd`, `usage` and `modelUsage` have the same shape and values (`modelUsage` keeps `costUSD`, `costBasis "list"`, and the split `cacheCreationEphemeral5mInputTokens` / `…1hInputTokens`). The stream gains `rate_limit_event` events (`{"status":"allowed","isUsingOverage":false}` after each response without limit headers). Nothing settlement uses is missing |
| Usage limit (429 with `anthropic-ratelimit-unified-status: rejected`, `…-representative-claim: five_hour`, `…-reset`; the headers the bundle reads) | `tok20-usage-limit-60s`, `tok20-usage-limit-4h` / `token-usage-limit-…` | **Exits at once**, no retry, whether the reset is 1 minute or 4 hours away: a `rate_limit_event` `{"status":"rejected","resetsAt":…,"rateLimitType":"five_hour"}`, then result text `You've hit your session limit · resets 3:43am (UTC)`, `terminal_reason api_error`, `is_error true`, **`api_error usage_limit_reached`**, `api_error_status 429`; harness class `NonZeroAgentExitCodeError`, exit 1 |
| The same headers in key mode | `key-usage-limit-60s` / `stub-usage-limit-headers-key-mode-UnknownApiError` | Treated as an ordinary 429: 10 retries over 176 s, `api_error null`, `api_error_status 429`; `UnknownApiError` |
| Usage limit with the CLI's unattended retry (`CLAUDE_CODE_RETRY_WATCHDOG=1`, `…_MAX_USAGE_LIMIT_WAIT_MS=150000`) | `tok20-usage-limit-watchdog` / `token-usage-limit-watchdog-…` | **Waits** for the reset: `api_retry` events with `max_retries 300` and delays of about 60 s, the request repeated at 59 s and 119 s, a `rate_limit_event` per refusal; after the 150 s cap it ends as above (`usage_limit_reached`) |
| Credential refused (401 `authentication_error`) | `tok20-unauthorized` | Two retries, no refresh request (the debug log: `OAuth 401: keeping the user-supplied CLAUDE_CODE_OAUTH_TOKEN…`), then `Failed to authenticate. API Error: 401 …`, `api_error_status 401`; `UnknownApiError`, exit 1 |
| One-hour cache writes priced | `tok3-cache-writes`, `key3-cache-writes` (the stub reports 20,000 write tokens per request, all `ephemeral_1h`) | The CLI prices them at **0.20** per million (USD 0.0083 for the two requests; 0.125 would give 0.0053), in both modes: it prices by the usage's split, not by the mode. With the archives' 5-minute writes at 0.125, the CLI's rule is: each write at its own TTL's rate. Token mode asks for one-hour caching, so its writes cost 1.6 times a key-mode session's |

**What this decides.** Token mode cannot run the public row's configuration, because simple mode reads
only an API key or an `apiKeyHelper`. The route that keeps the configuration is the plan's fallback:
the container runs in **key mode with a dummy key** (as every recording but these did), and the
passthrough removes `x-api-key`, adds `authorization: Bearer <subscription token>` and appends
`oauth-2025-04-20` to `anthropic-beta`. The CLI then still asks for five-minute caching (no
`extended-cache-ttl` beta), and a usage limit reaches it as an ordinary 429 (ten retries over about three
minutes, `UnknownApiError`), not as `usage_limit_reached`. The passthrough therefore has to recognise a
usage limit itself (the `anthropic-ratelimit-unified-status: rejected` header of the vendor's 429) and
answer with its own refusal, so the attempt is not spent in retries and the launcher can tell a limit
from a fault. The other route, token mode with three tools by `--disallowedTools`, changes the system
prompt (8,830 characters instead of 26), adds a tool and raises the cache-write rate;
it is not the configuration the public row measured.

**Only a live request with a real token can settle:**

- whether the vendor accepts a subscription token on a request that otherwise has key mode's shape
  (simple mode's short system prompt, no `extended-cache-ttl` beta, the `oauth-2025-04-20` beta added
  by the passthrough), and whether it requires anything else of such a request;
- the real usage-limit 429: its status, body and the `anthropic-ratelimit-unified-*` headers, and the
  headers on ordinary responses (the stub sent none, so `rate_limit_event` only ever read `allowed`);
- what a subscription session reports in `usage` and `modelUsage` (whether `costUSD` and the cache
  split are filled the same way, and whether `service_tier` differs);
- whether token mode with nonessential traffic allowed calls the profile or usage endpoints at start
  (the harness never allows it, so the launcher need not either), and how long a `setup-token` token
  lives before the 401 recorded above.
