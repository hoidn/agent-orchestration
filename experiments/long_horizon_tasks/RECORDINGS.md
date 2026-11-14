# Recordings of the pinned CLI (Tasks 1 and 2 of the long-horizon plan)

Evidence for the [long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md)'s
frozen rules, recorded 2026-11-13 on this machine. No model or provider call was made. The real CLI ran
inside a rootless Podman task container against `stub_api.py`, with a dummy key (or, for the token-mode
set, an obviously fake OAuth token), and the agent phase was on an allowlist that does not list the
vendor's API. Task 2's probes are in their own section after the assumption table. The kit's entry point is
[README.md](README.md).

**What is committed and what is not.**
- **Committed:** the cut fixtures, `fixtures/` (the stream side) and `fixtures/requests/` (the request
  side). The cut rules are in "Fixtures" below.
- **Local cache only:** the raw recordings stay under `/home/ollie/lh-cache/recordings/` (the stub's
  request logs, egress logs, container inspections, harness jobs, session files and debug logs).
  `recordings.json` holds the SHA-256 of each of their files. **That cache is not backed up**, and a
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
python -I experiments/long_horizon_tasks/cut_fixture.py requests $LH/recordings/<name>/stub.jsonl \
  "<source>" fixtures/requests/<name>.json
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
| D4 | The CLI's budget limit is a second guard | The CLI stops after the response that crosses the cap (one response of overshoot), with `subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, exit 1 (`stub-budget-stop-…`). Subagent usage counts: a foreground subagent was stopped mid-run (`twenty-tools-stub-budget-stop-in-subagent-…`). Background agents are killed, and the CLI prints a plain-text line saying the budget limit was reached and background agents are being stopped | Confirmed, with one response of overshoot |
| D4 | Four settlement figures: meter, session records, CLI cost, per-model usage | Session rows repeat one message's usage per content block (dedupe by `message.id`). Subagent rows live in `<session>/subagents/agent-*.jsonl`, and a `cost-state` row holds the CLI's total. Stream assistant events carry the start-of-message usage (1 to 3 output tokens). At a budget stop the result's `usage` is all zero while `modelUsage` and `total_cost_usd` are right (`stub-budget-stop-…`) | Readable, with these rules |
| D5 | A session has started when the stream holds an init event | Every session emitted `init` before its first request | Confirmed |
| D5 | A budget stop matches no harness pattern | `NonZeroAgentExitCodeError`. The harness's budget pattern expects "Budget has been exceeded", which 2.1.311 does not print | Confirmed |
| D5 | Refusal, context and output endings are sibling classes of provider faults | Refusal: `AgentSafetyRefusalError` (two requests, both refused, then exit 1). Output limit: `OutputTokenExceededError` (four requests). Context limit: `NonZeroAgentExitCodeError`, not `ContextWindowExceededError`, at the first request and after a failed compaction, because the CLI rewrites the API's message into its own prompt-too-long text (in `stub-context-limit-…`) | Partly contradicted: the context ending lands in the base class, together with the budget stop |
| D5 | The ending can be read from the stream | The result's `subtype` is `success` for refusal, output and context endings. The ending is in `is_error`, `terminal_reason` (`completed`, `budget_exhausted`, `api_error`, `prompt_too_long`, `blocking_limit`) and `api_error` / `stop_reason`. `api_error` is **absent** from the result except at an output limit (`max_output_tokens`) and a usage limit in token mode (`usage_limit_reached`); `api_error_status` is present and `null` when there was no HTTP status. A harness timeout leaves no result event (`AgentTimeoutError`), and the verifier still ran (`stub-timeout-…`, `verifier_result` reward 0) | Contradicted for `subtype`; use `terminal_reason` |
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
event lists exactly `Bash, Edit, Read`. The fixtures named in the plan's D5 now hold these recordings.

| Ending | Recording / fixture | Recorded fields | Harness class, exit |
| --- | --- | --- | --- |
| Normal | `s3-normal-low` / `stub-normal-end` | `completed`, `is_error false`, `end_turn` | none, 0 |
| CLI budget | `s3-budget-medium` / `stub-budget-stop-NonZeroAgentExitCodeError` | `budget_exhausted`, `error_max_budget_usd`; the result's `usage` is zero, `modelUsage` right | `NonZeroAgentExitCodeError`, 1 |
| Refusal | `s3-refusal-high` / `stub-refusal-AgentSafetyRefusalError` | two requests, both refused (request fixture), then `model_refusal_no_fallback`; `api_error` as `terminal_reason`, `stop_reason refusal` | `AgentSafetyRefusalError`, 1 |
| Output limit | `s3-max-tokens-low` / `stub-output-limit-OutputTokenExceededError` | four requests (request fixture); `terminal_reason api_error`, `api_error max_output_tokens` | `OutputTokenExceededError`, 1 |
| Context limit | `s3-context-low` / `stub-context-limit-NonZeroAgentExitCodeError`; `s3-context-late-low` / `stub-context-limit-after-compaction-NonZeroAgentExitCodeError` | `prompt_too_long` (`api_error_status 400`); after a failed compaction, `blocking_limit` | `NonZeroAgentExitCodeError`, 1 |
| Time limit | `s3-timeout-low` / `stub-timeout-AgentTimeoutError` | no result event; the verifier ran (`verifier_result` reward 0 in the fixture) | `AgentTimeoutError` |

The forms equal the twenty-tool ones, with one difference. With three tools a standalone `sleep 30` runs
(the twenty-tool CLI refused it). So the timeout session made 6 requests, the last 150 s after the first
(`fixtures/requests/s3-timeout-low.json`), where the twenty-tool session made 1,148
(`fixtures/requests/timeout-low.json`).

### Provider faults

Every persistent fault was answered from the second request on; the first turn succeeded. Each row's
request fixture has the recording's name.

| Fault (recording / fixture) | What the CLI did | Final fields | Harness class, exit |
| --- | --- | --- | --- |
| 429 with `retry-after: 5` (`f-rate-limit-retry-after` / `stub-rate-limit-retry-after-ApiRateLimitError`) | 10 retries (`n_api_retry` 10). Waits were 5 s while the header held, then backoff to about 40 s. Gave up after 197 s | `terminal_reason api_error`, `is_error true`, `api_error_status 429`. The result text is a CLI line naming the rejected request and status, then the stub's message (in the fixture) | `ApiRateLimitError`, 1 |
| 429 without it (`f-rate-limit` / `stub-rate-limit-ApiRateLimitError`) | 10 retries, backoff 0.5 s doubling to about 37 s; 184 s | as above | `ApiRateLimitError`, 1 |
| 529 (`f-overloaded` / `stub-overloaded-UnknownApiError`) | 10 retries; 181 s | `api_error_status 529`. The result text names the status and the base URL's host (`relay:8080`), and differs from the harness's overload pattern | `UnknownApiError`, 1 |
| 500 (`f-server-error` / `stub-server-error-ApiInternalServerError`) | 10 retries; 180 s | `api_error_status 500` | `ApiInternalServerError`, 1 |
| Stream cut after the first block (`f-drop` / `stub-dropped-stream-recovered-normal-end`) | One streaming retry (`api_retry`, `error unknown`), then a **non-streaming** request (`stream false`, `max_tokens 64000`; request fixture), which the stub also served | `completed`, `is_error false`: the session went on | none, 0 |
| First byte after 120 s (`f-slow` / `stub-slow-first-byte-UnknownApiError`) | Every attempt ended after about 15 s with a reset connection. 10 retries; the last request started 325 s after the first, and the session ended at 340 s (`duration_ms` 340,168) | `terminal_reason api_error`, `api_error_status null`. The result text names a dropped connection and the base URL (in the fixture) | `UnknownApiError`, 1 |
| 429, 529, 500 once each, then success (`f-transient` / `stub-transient-faults-recovered-normal-end`) | three retries; 6 s | `completed` | none, 0 |

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
| Slot at its cap (`pt-cap` / `passthrough-cap-UnknownApiError`) | 403 `permission_error`, `x-should-retry: false`, message `lh-passthrough: slot cap reached` | no retry (one refused request); ended in under 1 s | `api_error_status 403`. The result text is a CLI prefix naming an authentication failure and the status, then the passthrough's message verbatim | `UnknownApiError`, 1 |
| Tranche total (`pt-total` / `passthrough-total-UnknownApiError`) | same, `… tranche total reached` | same | same, with that message | `UnknownApiError`, 1 |
| Tranche stopped (`pt-stopped` / `passthrough-stopped-UnknownApiError`) | same, `… tranche stopped` | same | same, with that message | `UnknownApiError`, 1 |
| Another model (`pt-model` / `passthrough-model-NonZeroAgentExitCodeError`) | 404 `not_found_error`, `x-should-retry: false` | one non-streaming retry, also refused (two refused requests) | `api_error_status 404`. The result text is the CLI's own selected-model notice; the passthrough's message is lost | `NonZeroAgentExitCodeError`, 1 |
| A provider-side tool (`pt-tool` / `passthrough-tool-UnknownApiError`) | 400 `invalid_request_error`, `x-should-retry: false` | two retries (three refused requests), each dropping beta headers (three request shapes) | `api_error_status 400`. The result text holds the passthrough's message | `UnknownApiError`, 1 |

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
- `tasks.json` keeps `overlay_digest`, `cap`, `extra_hosts` and `oracle_evidence` as `null`. The plan's
  Task 2 oracle runs fill them; those runs were not part of the recording rounds.

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
| Headers | `tok20-normal-404` (fixture `token-normal-end`) against `key20-normal-debug` (key mode, same tools) | Token mode sends `authorization: Bearer <dummy>` and no `x-api-key`; key mode sends `x-api-key` and no `authorization`. Token mode adds the betas `oauth-2025-04-20` and `extended-cache-ttl-2025-04-11`. Same user agent product token (`claude-cli/2.1.311`), `x-app: cli`, and the same other header names |
| Body | the same, and `tok3-normal` (fixture `token-three-tools-normal-end`) against `key3-normal-system` | The same body fields (`model`, `metadata`, `max_tokens`, `thinking`, `context_management`, `output_config`, `stream`) and the same tool list for the same tools. The same three-block system layout (`key3-normal-system`, `tok3-normal`): a 74-character attribution block, SHA-256 `d87d6703bc46b722feedc6f23ba93ca71f112cb922d33ac503ab57b5010b2ca3`, then a 62-character identity block, SHA-256 `0d7062851dd7bd7e66d4be4f12ac4951e3d2f587ec408295333a49963bd3f6b7`. In token mode the system blocks carry `cache_control {"type":"ephemeral","ttl":"1h"}`; in key mode, `{"type":"ephemeral"}` (five minutes) |
| Three tools without simple mode | `tok3-normal` (`--ak disallowed_tools=` the other 18) / `token-three-tools-normal-end` | Init lists `Bash, Edit, Read`, but the request carries a fourth tool (`DeferredToolPlaceholder`). Its third system block is the default system prompt (8,830 characters), where simple mode sends a 26-character block naming the working directory and the date. It is not the public row's configuration |
| Init and result | every token run | Init `apiKeySource` is `none` (key mode: `ANTHROPIC_API_KEY`); no other init field differs. The result event has the same keys. `total_cost_usd`, `usage` and `modelUsage` have the same shape and values; `modelUsage` keeps `costUSD`, `costBasis "list"`, and the split `cacheCreationEphemeral5mInputTokens` / `…1hInputTokens`. The stream gains `rate_limit_event` events: `{"status":"allowed","isUsingOverage":false}` after each response without limit headers. Nothing settlement uses is missing |
| Usage limit: a 429 with `anthropic-ratelimit-unified-status: rejected`, `…-representative-claim: five_hour` and `…-reset`, the headers the bundle reads | `tok20-usage-limit-60s` / `token-usage-limit-NonZeroAgentExitCodeError`, and `tok20-usage-limit-4h` | **Exits at once**, with no retry, whether the reset is 1 minute or 4 hours away. A `rate_limit_event` `{"status":"rejected","resetsAt":…,"rateLimitType":"five_hour"}` comes first. Then the result: the CLI's session-limit notice with the reset time (in the fixture), `terminal_reason api_error`, `is_error true`, **`api_error usage_limit_reached`**, `api_error_status 429`. Harness class `NonZeroAgentExitCodeError`, exit 1 |
| The same headers in key mode | `key-usage-limit-60s` / `stub-usage-limit-headers-key-mode-UnknownApiError` | Treated as an ordinary 429: 10 retries over 176 s, `api_error` **absent**, `api_error_status 429`; `UnknownApiError` |
| Usage limit with the CLI's unattended retry (`CLAUDE_CODE_RETRY_WATCHDOG=1`, `…_MAX_USAGE_LIMIT_WAIT_MS=150000`) | `tok20-usage-limit-watchdog` / `token-usage-limit-watchdog-NonZeroAgentExitCodeError` | **Waits** for the reset: `api_retry` events with `max_retries 300` and delays of about 60 s, and a `rate_limit_event` per refusal. The request was repeated at 59 s and 119 s (request fixture). After the 150 s cap it ends as above (`usage_limit_reached`) |
| Credential refused (401 `authentication_error`) | `tok20-unauthorized` / `token-unauthorized-UnknownApiError` | Two retries (`n_api_retry` 2; three requests), and no refresh request. The debug log says the CLI keeps the user-supplied token rather than adopting a stored credential. The session ends with an authentication-failure result, `api_error_status 401`; `UnknownApiError`, exit 1 |
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

## Fixtures

**Stream fixtures** (`fixtures/*.json`) are cut by `cut_fixture.py` from one trial. They keep:
- the init event and the last four stream events;
- the number of events and of `api_retry` events;
- the harness's exception class, the CLI's exit code, the trial's `agent_result` and `verifier_result`.

Model text, tool input and tool output are dropped. CLI-made text is kept: a `<synthetic>` message, or an
error or result string that a classification rule may match. Home paths become `<home>`.

**Request fixtures** (`fixtures/requests/<recording>.json`, one per local recording with a stub log, 47
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
Task 1 request logs predate the system-block logging, so their shapes have an empty `system`.

What each stream fixture supports:

| Fixture | Claim |
| --- | --- |
| `stub-normal-end`, `stub-budget-stop-…`, `stub-refusal-…`, `stub-output-limit-…`, `stub-context-limit-…`, `stub-context-limit-after-compaction-…`, `stub-timeout-…` | The D5 endings in the three-tool configuration ("The endings again") |
| `stub-simple-mode-normal-end` | Task 1's first look at `CLAUDE_CODE_SIMPLE=1`: three tools in init (D2 row 1) |
| `stub-rate-limit-retry-after-…`, `stub-rate-limit-…`, `stub-overloaded-…`, `stub-server-error-…`, `stub-slow-first-byte-…`, `stub-dropped-stream-recovered-normal-end`, `stub-transient-faults-recovered-normal-end` | Provider faults |
| `passthrough-cap-…`, `passthrough-total-…`, `passthrough-stopped-…`, `passthrough-model-…`, `passthrough-tool-…` | The passthrough's refusals |
| `token-simple-mode-…`, `token-normal-end`, `token-three-tools-normal-end`, `token-usage-limit-…`, `token-usage-limit-watchdog-…`, `token-unauthorized-…`, `token-one-hour-cache-writes-normal-end`, `stub-usage-limit-headers-key-mode-…` | Token mode, and the key-mode contrast for the usage limit |
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
simple mode, so they are its nearest recorded endings until the re-recordings come.
