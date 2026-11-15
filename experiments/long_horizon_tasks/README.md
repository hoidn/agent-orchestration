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
| `oracle_check.sh`, `summarize.py` | Task 2b's oracle check on the pinned images (overlay, CPU set, load gate, repeats, stops), and its per-label counts and per-trial records |
| `oracle_first_pass.json`, `oracle_uidfix_recorded.json` | The first pass's records, and the labelled variant's rerun on its recorded image: one JSON line per trial (outcomes, timings, load, affinity, peak memory, network policy, image ids, digests; no log text) |
| `uidfix_variant.py` | Builds once, and records in `tasks.json` (`variant`), the verifier image of the labelled variant vba-userform-port-uidfix |
| `image_check.py`, `image_measure.json` | Task 2b: pull, size and withholding check of one pinned image; one line per image (RECORDINGS.md, "Task 2b"); `image_check.py tasks` copies the results into `tasks.json` |

Tests (from the repository root; no container, no network):

```
pytest -q -n 8 tests/test_long_horizon_stub_api.py tests/test_long_horizon_cut_fixture.py \
  tests/test_long_horizon_price_check.py tests/test_long_horizon_image_check.py \
  tests/test_long_horizon_oracle_check.py tests/test_long_horizon_summarize.py \
  tests/test_long_horizon_recordings_index.py tests/test_long_horizon_uidfix_variant.py
```

The price test reproduces the three public archive totals when the archives are in the cache directory (`$LH`, by default
`~/lh-cache`). When they are absent, it is skipped with a reason. So is the index test that reads each Task 2a
recording's harness arguments back from its trial's `config.json`; its decoy tests read committed fixtures only.

**Stopping a harness run** (`oracle_check.sh`; a launcher of long attempts copies this pattern):
- Start the harness in its own session: `exec setsid env -i … taskset … <harness>` inside the backgrounded
  function, so the shell's `$!` is the harness itself and its process group. A plain backgrounded function
  gives the pid of a bash subshell, which does not pass a signal on.
- To stop it, send SIGTERM to the harness. Harbor 0.25.0 cancels the phase in hand or lets it finish, takes its
  containers down and exits 130 (RECORDINGS.md, "The stops, checked on the variant"). After a grace period
  (`STOP_GRACE_S`, 120 s), send SIGKILL to the whole group.
- Then remove every container and network still named after the trial (`<trial name, lowercased>__`). The
  containers run under conmon, outside the harness's group, so a killed harness leaves them behind.
- The follower that samples the trial applies the stops: free space under the stop, the trial's wall bound,
  and a stop request (`$JOBS/.stop`, which the script's SIGINT or SIGTERM trap creates). Each writes
  `stop=<reason>` to `meta.txt`, and `summarize.py` counts that run as no evidence.
- The run's state: `JOBS` must be new or empty unless `RESUME=1`; `pulled.txt` keeps listed any image a release
  could not delete.
- Anything that reads the shell's list of running trials (the gate's idle clock, the concurrency count) runs in
  the shell that started them, never inside `$(…)`. A subshell's list is a frozen copy, so a finished trial
  would still count as in flight (the re-review's N1). Results come back by exit code, and messages go to stderr.

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

`slot_record.py` is the one definition of the launcher's export: its fields and types (in its docstring) and
`load`, which joins every start to its schedule slot and its D5 row and refuses anything that does not fit, naming the
record. Each start carries the class the launcher decided (`class`, with `stop_cause` for a stop from the closed
list `LAUNCHER_STOPS`, which also says where each cause can occur, found on a row of another class) and its D5 row as
evidence; a stop is never scored. A `contamination` result may sit on a start of any class: it excludes an
observation, and on any other class is listed and counted for D7.7 without changing the class. The launcher writes
that layout and the readout reads it; both load the module by its path (the kit runs under `python -I`) and neither
imports the other.

`readout.py` turns the export into the readout of D6 and, at the end of the tranche, into `results/family.json` (step
7). It reads every rule from `ladder.json` (`readout`, `classification`, `attempt`, `schedule`) and prints no public
figure. Every figure is computed once, by `compute`, from the starts joined to their slots by slot id: each task's cells
and pooled count with their exact intervals and labels (a count pooled over tasks gets no interval), the band effort,
the effort test over complete triples with its verdict and the bound on the fall, the cost per effort, the lists
(exclusions, a contaminated attempt of any label by the SHA-256 of each term found, counted over every label for D7.7,
flags, cuts per effort, the pilot's attempts, refused connections), the graded outcome, an earlier label's counts and
the allowance. The last three enter no rule. The pooled screen applies when every effort has at least four scored
observations (`readout.pooled.min_per_effort`), and is printed "screened at n of 15 attempts"; with fewer at any effort
a task is "not screened", with its counts per effort. A readout that ends in a stop places nothing and still prints the
bound on the fall over the complete triples there are.

```
python -I experiments/long_horizon_tasks/readout.py <export.json> [--dropped <drops.json>] [--family experiments/long_horizon_tasks/results/family.json]
python -I experiments/long_horizon_tasks/readout.py <export.json> --rehearsal <stand-ins.json> [--dropped <drops.json>] [--family <path>]
pytest -q -n 4 tests/experiments/test_long_horizon_slot_record.py tests/experiments/test_long_horizon_readout.py
```

A final readout is refused unless `manifest.json` is frozen, its SHA-256 is the export's label, `ladder.json`,
`tasks.json`, `readout.py` and `slot_record.py` equal its records and no field is pending; the refusal names the
reason. `--rehearsal` takes a
JSON object with a stand-in for each pending readout field (and for nothing else) and stamps the readout and
`family.json` as a rehearsal. `--dropped` takes the coordinator's drops, a JSON list of `{"task", "reason"}`, the
reason naming the ledger row by its date. `family.json` is written only from a readout whose tranche ended and did not end in a
stop, with every task screened or dropped; the same records give the same bytes. `readout.py` and
`slot_record.py` are kit files, so the manifest covers them and a change to either makes a new label; their test
modules are not covered.
