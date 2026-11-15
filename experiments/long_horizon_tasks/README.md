# Long-horizon recording kit

The no-spend kit behind the [long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md)'s
Tasks 1 and 2. It records how the pinned Claude Code CLI talks to a model API and how it ends a session,
against `stub_api.py`, a local stand-in for that API. It also pins and checks the plan's 16 tasks. The
evidence and the cut rules are in [RECORDINGS.md](RECORDINGS.md).

**Nothing in this kit spends.** No file here makes a model or provider call, and none holds a credential.

**The one authorised way the real CLI runs.** The CLI runs only inside a rootless Podman task container,
started by the harness through `record.sh`. Three conditions hold:

- the container holds no credential of any kind (a dummy key or an obviously fake token, no host mount);
- the base URL points at the stub, reached through the `relay` service;
- the vendor's API is unreachable from the agent phase (the allowlist; `record.sh` checks it before every
  run).

The CLI is never run on the host. There the no-provider stubs stay first on `PATH`.

| File | Role |
| --- | --- |
| `stub_api.py` | The stand-in API: canned replies and faults by scenario. It binds only loopback or a unix socket |
| `record.sh`, `relay-compose.yaml`, `harbor_patient.py`, `allowlist_probe.py` | One recording through the relay route, and the allowlist probe |
| `cut_fixture.py` | Cuts committed fixtures (stream side and request side) from the local recordings |
| `fixtures/`, `fixtures/requests/`, `fixtures/traces/`, `fixtures/after-limit/` | The committed cuts (see RECORDINGS.md, "Fixtures") |
| `recordings.json` | SHA-256 of every raw recording file kept in the local cache |
| `price_rule.json`, `price_check.py` | The per-request price rule, and its check against the public archives |
| `tasks.json` | The 16 tasks' package digests, their pinned images (digests, sizes) and withholding results, the overlay digest and the oracle evidence |
| `oracle_check.sh`, `summarize.py` | Task 2b's oracle check on the pinned images (overlay, CPU set, load gate, repeats), and its per-label counts and per-trial records |
| `oracle_first_pass.json` | The first pass's records: one JSON line per trial (outcomes, timings, load, affinity, peak memory, image ids, digests; no log text) |
| `image_check.py`, `image_measure.json` | Task 2b: pull, size and withholding check of one pinned image; one line per image (RECORDINGS.md, "Task 2b"); `image_check.py tasks` copies the results into `tasks.json` |

Tests (from the repository root; no container, no network):

```
pytest -q -n 8 tests/test_long_horizon_stub_api.py tests/test_long_horizon_cut_fixture.py \
  tests/test_long_horizon_price_check.py tests/test_long_horizon_image_check.py \
  tests/test_long_horizon_oracle_check.py tests/test_long_horizon_summarize.py \
  tests/test_long_horizon_recordings_index.py
```

The price test reproduces the three public archive totals when the archives are in the cache directory (`$LH`, by default
`~/lh-cache`). When they are absent, it is skipped with a reason. So is the index test that reads each Task 2a
recording's harness arguments back from its trial's `config.json`; its decoy tests read committed fixtures only.

## The passthrough, the token scanner and the live probe (plan Task 4)

`live_probe.sh` is the one file of this kit that can use the owner's subscription: it refuses to start
without `LH_PROBE_SPEND_AUTHORIZED=yes`, which is set only under the plan ledger's approval row, and without
that row naming the kit's commit. Its stand-in run (`LH_PROBE_STAND_IN=<stub scenario>`) puts `stub_api.py`
behind the passthrough's rehearsal switch and spends nothing.

| File | Role |
| --- | --- |
| `passthrough.py` | The one host process that holds the subscription token (D4, route B): listens on the relay's unix socket; refuses in the one 403 form anything outside the recorded request shape; one request in flight per slot; rebuilds the request with three header values set (`authorization`, `host`, `accept-encoding: identity`); checks every byte back to the client and every log row for the token's forms; meters by the price rule; records closed starts and stops in its state directory |
| `make_allowlist.py` | Builds `request_allowlist.json` (the passthrough's allowlist) from the token-mode shapes of `fixtures/requests/t2a-*.json` and their recorded key sets; `--check` fails when the committed file differs, so rerun it when the fixtures change |
| `token_scan.py` | Finds the token by the passthrough's fingerprint, in plain, hex, base64 and UTF-16LE forms (path, offset and form only); `canary` plants every form and checks the file set |
| `live_probe.sh` | The live probe of Task 4, items 1 to 4: three sessions through the relay and the passthrough, the stop rule, the runtime check, the file-set scan and `probe.json` |

Tests (no container, no network, no CLI; the upstream is `stub_api.py`):

```
pytest -q -n 4 tests/experiments/test_long_horizon_passthrough.py
```
