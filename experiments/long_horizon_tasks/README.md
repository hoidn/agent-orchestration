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
fixtures among them; `orchestrator/providers/price_table.json`, which D4 names by hash; and
`tests/experiments/test_long_horizon_ladder.py`, the reference reader of the pattern language until the launcher
reads it. **Not covered** (the
list is in `manifest.py` and in `manifest.json`): `manifest.json` itself; `README.md` and `RECORDINGS.md`, prose that
no code reads, so a wording fix makes no new label; `results/`, the readout's output; `__pycache__/`. The allowance
inputs, the meter readings, the raw recordings, the task packages and images, and the token are outside the
repository and in neither file (the last three by their hashes and digests only). The package code the launcher
reuses is bound by the runtime commit (`LH_RUNTIME_COMMIT`), not by the label.

```
python -I experiments/long_horizon_tasks/manifest.py check            # exit 1 names each changed, new or gone file,
                                                                        # or a frozen manifest whose ladder.json is not ready
python -I experiments/long_horizon_tasks/manifest.py write            # rewrite after a kit change; prints the label
python -I experiments/long_horizon_tasks/manifest.py write --freeze   # the freeze (Task 9); refused while anything is pending
                                                                        # (a plain write over a frozen manifest is refused)
pytest -q -n 4 tests/experiments/test_long_horizon_ladder.py
```

**`pending`** lists each value that `ladder.json` cannot take from `main` yet. Each such field is `null`, and its
entry says what fills it: the branch in flight (`feat/long-horizon-oracle-2b`: the qualified tasks, the
load-sensitive list, overlay digests, extra hosts, withholding, the host list, the CPU set), Task 2b (the disk plan,
the contamination terms and the canary's SHA-256, which verifiers report sub-tests), the live probe (the vendor's
header names, the utilisation header), or the freeze (the schedule's seed and hash, the bootstrap seed). The
passthrough's form refusals and its log (keys, and how a row with no slot is joined to an attempt) are filled from
`passthrough.py`; tests read its refusal reasons, its log keys, its paid-usage check and its worst-case bound from the
code and hold `ladder.json` to them. A filled field moves from `pending` to `filled` with
its `type` and a `source` (the commit or ledger row it came from). `--freeze` refuses while `pending` is non-empty, any
`null` is left, or a filled field fails its type or names no source; a test holds every `null` to a `pending` entry.

**`manifest.py write` is rerun at the freeze.** Until then the committed `manifest.json` is unfrozen: it only shows
that the command works, labels nothing, and may be stale after a kit merge without failing a test (a rerun of `write`
in the merge keeps it current, but no step needs it). A test checks that `write` reproduces itself on a copy of the
kit; once the manifest is frozen, a test checks that the committed one is current. A conflict in `manifest.json` is
resolved by running `write` on the merged tree, never by hand. A commit of `ladder.json` or `manifest.json` is a
commit of this directory and so moves the kit's commit that the live probe's approval row must name (`live_probe.sh`).

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

## The readout (plan Task 6)

`readout.py` turns the launcher's export into the readout of D6 and, at the end of the tranche, into
`results/family.json` (step 7). It reads every rule from `ladder.json` (`readout`, `classification`, `attempt`,
`schedule`) and prints no public figure. The record it reads (one JSON document: the current label, the earlier
labels with the ledger row that ended each, how the tranche ended, the schedule's slots and every start) is stated in
its docstring; a start that joins no slot, or any field that does not fit, is an error. Every figure is computed once,
by `compute`, from the starts joined to their slots by slot id: the cells and pooled counts with their exact
intervals and labels, the band effort, the effort test over complete triples with its verdict and the bound on the
fall, the cost per effort, the lists (exclusions, flags, cuts per effort, the pilot's attempts, refused connections),
the graded outcome, an earlier label's counts and the allowance. The last three enter no rule. A readout that ends
in a stop places nothing.

```
python -I experiments/long_horizon_tasks/readout.py <export.json> [--family experiments/long_horizon_tasks/results/family.json]
python -I experiments/long_horizon_tasks/readout.py <export.json> --rehearsal <stand-ins.json> [--family <path>]
pytest -q -n 4 tests/experiments/test_long_horizon_readout.py
```

A final readout is refused while `ladder.json` marks a `readout.*` field pending, and unless the export's label is
the SHA-256 of `manifest.json` and that manifest holds the SHA-256 of the `ladder.json` read. `--rehearsal` takes a
JSON object with a stand-in for each pending readout field (and for nothing else) and stamps the readout and
`family.json` as a rehearsal. `family.json` is written only from a readout whose tranche ended and did not end in a
stop; the same records give the same bytes. `readout.py` is a kit file, so the manifest covers it and a change to it
makes a new label; its test module is not covered.
