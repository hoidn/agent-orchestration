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
| `tasks.json` | The 16 tasks' digests and image pins, and the fields the oracle runs will fill |
| `oracle_check.sh`, `summarize.py` | The oracle check of the plan's Task 2 |
| `image_check.py`, `image_measure.json` | Task 2b: pull, size and withholding check of one pinned image; one line per image (RECORDINGS.md, "Task 2b") |

Tests (from the repository root; no container, no network):

```
pytest -q -n 8 tests/test_long_horizon_stub_api.py tests/test_long_horizon_cut_fixture.py \
  tests/test_long_horizon_price_check.py tests/test_long_horizon_image_check.py \
  tests/test_long_horizon_recordings_index.py
```

The price test reproduces the three public archive totals when the archives are in the cache directory (`$LH`, by default
`~/lh-cache`). When they are absent, it is skipped with a reason. So is the index test that reads each Task 2a
recording's harness arguments back from its trial's `config.json`; its decoy tests read committed fixtures only.

## The criterion and the manifest (plan Task 3)

| File | Role |
| --- | --- |
| `ladder.json` | The ladder's frozen configuration: every value and rule of the plan's D1 to D7 as data, each group with a `source` naming the section or kit file it comes from. The D5 table is in `classification.rows`: per row its field patterns, the fixtures it cites, and its class (`classification.classes` says how each class is counted) |
| `manifest.py`, `manifest.json` | The SHA-256 of every file the manifest covers. The SHA-256 of `manifest.json` is the configuration label of D7 |

**Covered:** every file of this directory, `ladder.json`, `tasks.json`, the scripts, `recordings.json` and the
fixtures among them, and `orchestrator/providers/price_table.json`, which D4 names by hash. **Not covered** (the
list is in `manifest.py` and in `manifest.json`): `manifest.json` itself; `README.md` and `RECORDINGS.md`, prose that
no code reads, so a wording fix makes no new label; `results/`, the readout's output; `__pycache__/`. The allowance
inputs, the meter readings, the raw recordings, the task packages and images, and the token are outside the
repository and in neither file (the last three by their hashes and digests only).

```
python -I experiments/long_horizon_tasks/manifest.py check            # exit 1 names each changed, new or gone file
python -I experiments/long_horizon_tasks/manifest.py write            # rewrite after a kit change; prints the label
python -I experiments/long_horizon_tasks/manifest.py write --freeze   # the freeze (Task 9); refused while anything is pending
pytest -q -n 4 tests/experiments/test_long_horizon_ladder.py
```

**`pending`** lists each value that `ladder.json` cannot take from `main` yet. Each such field is `null`, and its
entry says what fills it: one of the two branches in flight (`feat/long-horizon-oracle-2b`: the qualified tasks,
overlay digests, extra hosts, withholding, the host list, the CPU set; `feat/lh-passthrough`: the refusal reasons of
a request's form, its log format, the scope of the paid-usage stop), Task 2b's dry run of the contamination terms,
the live probe, the freeze (the schedule's seed and hash, the bootstrap seed) or a coordinator ruling. `--freeze`
refuses while `pending` is non-empty or any `null` is left; a test holds every `null` to a `pending` entry. Until
the freeze, the committed `manifest.json` is unfrozen and goes stale with every kit change: run `write` again.
