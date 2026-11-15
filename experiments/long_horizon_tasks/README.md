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
| `oracle_first_pass.json`, `oracle_uidfix_recorded.json`, `oracle_second_pass.json` | The first pass's records, the labelled variant's rerun on its recorded image, and the second (qualifying) pass's: one JSON line per trial (outcomes, timings, load, affinity, peak memory, network policy, image ids, digests; no log text) |
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
`tests/experiments/test_long_horizon_ladder.py`, the criterion's tests, which hold the shared reader of the pattern
language (in `ladder.py`) to the fixtures. **Not covered** (the
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
the contamination terms, the canary's SHA-256 and the tasks whose starting files hold the canary, which the scan
then leaves out for them; which verifiers report sub-tests), the live probe (the vendor's
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
| `token_scan.py` | Finds the token by the passthrough's fingerprint, in plain, hex, base64 and UTF-16LE forms (path, offset and form only); `canary` plants every form and checks the file set. It finds whole copies only: not a part of the token, not compressed, encrypted or escaped, and not base64 wrapped at 76 columns |
| `live_probe.sh` | The live probe of Task 4, items 1 to 4: three sessions through the relay and the passthrough, the stop rule, the runtime check, the file-set scan and `probe.json` |

Tests (no container, no network, no CLI; the upstream is `stub_api.py`):

```
pytest -q -n 4 tests/experiments/test_long_horizon_passthrough.py
```

## The launcher (plan Task 5)

`ladder.py` runs the tranche. It reserves money under one lock and starts each attempt through the harness. At
teardown it scans the attempt and removes its containers by name; only then does it settle the attempt and classify
it by D5. An attempt left open by a launcher that died gets the same teardown at the next launch: the same scans, and
any stop already written for it. **A live launch spends**, so it refuses unless every condition holds. It needs `LH_SPEND_AUTHORIZED=yes`,
plus `LH_MANIFEST_SHA256` and `LH_RUNTIME_COMMIT` that match the ledger's current `Configuration label` row. It
also needs a frozen manifest with nothing pending in `ladder.json`, a detached checkout of that commit and a clean
kit. Its preflight checks the harness environment, the host-side overrides, the 4.1.0 package digests and the
owner's allowance inputs. A rehearsal (`LH_REHEARSAL=<dir>`) spends nothing. It refuses any spend variable, takes a
stand-in for every pending field from `<dir>/stand_ins.json`, and reads its ledger from `<dir>/ledger.md`.

```
python -I experiments/long_horizon_tasks/ladder.py plan                   # the schedule, in the order it runs
python -I experiments/long_horizon_tasks/ladder.py launch [--dry-run]     # run until it ends, waits or stops
python -I experiments/long_horizon_tasks/ladder.py status [--export F]    # the state; F: the readout's record
python -I experiments/long_horizon_tasks/ladder.py ruling ATTEMPT --row N --date YYYY-MM-DD
python -I experiments/long_horizon_tasks/ladder.py resume [--clears THRESHOLD ... --date YYYY-MM-DD]
python -I experiments/long_horizon_tasks/ladder.py allowance inputs|reading|figures ...
```

The launcher never holds the token. A person starts the passthrough with the token file, and `status` prints its
command line; in a rehearsal it prints the rehearsal start (`--rehearsal`, a canary, no token file). The passthrough
records its mode in `fingerprint.json`, and the launcher starts no attempt against a passthrough in the other mode
(it stops the tranche). The launcher refuses to run while `LH_TOKEN_FILE`, `CLAUDE_CODE_OAUTH_TOKEN`,
`ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is in its environment, naming the variable, never its value. Each harness starts from an
empty environment that holds `HOME`, `PATH`, telemetry off, the runtime directory, the containers override, its
slot's relay socket directory and the slot's fake token. It runs under the CPU set in its own session. Each attempt
has its own passthrough socket (`<state>/relay/<slot>/passthrough.sock`) with a cap of 16 connections of its own,
so one attempt's connections never refuse another's requests.

`launch` returns when the tranche waits for a person, and prints why: the smoke read, the pilot's ledger row, the
round-one read, a pause or a stop. It reads these ledger rows:

- `| <date> | Smoke read | <label> pass |` (or `fail`, a stop);
- `| <date> | Pilot read | <label> ... |`;
- `| <date> | Round 1 read | <label> ... |`;
- `| <date> | Ruling | <attempt> row <N> ... |`, which `ruling` needs before it gives a start paused under D5 row
  16 its row.

Before every start the launcher repeats the launch's checks: the manifest hash it checked (the label every start
records), the kit against the manifest and, when live, the ledger's current label, the runtime commit, the detached
checkout and a clean kit; then the harness venv's versions and the two host-side overrides, which the manifest does
not cover. A change stops the tranche, naming it.

One launcher runs per state root: `launch` (with its reconcile) and `resume` hold `<state>/launcher.lock`, and a
second process is refused, naming the holder's pid. The lock is never let go while an attempt of the process runs:
an exception out of the launcher's loop interrupts the attempts in flight, stops the tranche naming the exception,
and the launcher exits only after they have been torn down. A check before a start that cannot read what it checks
(the ledger on `main`, the harness venv) stops the tranche with that reason instead of raising.

A launch refused before its harness runs (the task's package, the overlay's digest, its socket, or any other failure
before the harness started, named by its exception) stops the tranche but is no start: it is not exported, its
token is retired, and the attempt is kept under `<state>/refused/`. Its index is never reused.

A resume lifts a pause or a stop, never a usage limit. Starts stay closed until five minutes after the limit's reset
and then reopen with one start, and with the rest once that session has an answer. If the single start ends with no
answer, the tranche pauses, and a resume allows one more. The one start is enforced as at most one attempt in flight,
so an attempt started before the limit and still running delays it past the reset's five minutes.

The launcher's stream checks (the init event, the paid-usage sign in a `rate_limit_event`, a subagent file) read
files that Harbor copies to the host only when the agent phase ends: they are post-session checks and never stop a
running session. The paid-usage stop during a session is the passthrough's header rule (D4).

At teardown the runtime check reads every container of the attempt: each container's inspected configuration
(its configured environment), the egress sidecar's log, and, for the smoke, the pilot and a rehearsal, every agent
container's (`*_main_1`) exported file system. A failed `podman inspect`, `logs` or `export` is an incomplete scan,
a stop; each read's exit code is kept in the slot's `podman.jsonl`. The process environments are sampled every 2 s
while the harness runs, from running containers only: at teardown every container has exited. A failed `podman exec`
on a running container is logged there and does not by itself make the scan incomplete. A limit of the check: a
container that ran too briefly for any 2 s sample is scanned only through its inspected configuration, so what its
processes held at run time is not read. A failed `podman ps -a` is an incomplete scan too, and never confirms a
removal. Once the containers are removed, `slot.json` says so, and a reconcile after the launcher died before the
close skips the runtime check (its findings were stops already). The pids limit
(`limits-compose.yaml`) reaches the agent's environment only: Harbor does not apply runtime overrides to the
separate verifier containers.

To end a pause or a stop, a person writes the ledger row that D5 asks for and then runs `ladder.py resume`. A stop
needs `| <D> | Ruling | resume: <its cause>: <the decision> |` and `resume --date <D>`, one row for each distinct stop
since the last resume, the whole cause followed by its `:` (a row for a longer cause is not a row for a shorter one) (a resume is refused naming each stop that has none; `status` lists them all); a D7.7
threshold's stop is lifted by its `--clears` ruling. While one
of D7.7's count thresholds is over its bound, a plain resume is refused, naming it. The thresholds are the
infrastructure-failure share of the tranche (`infrastructure-failures`) and at one level, judged from 20 starts at
that level (`infrastructure-failures-at-level`, cleared on its own), five or 24 pre-session failures, the 5% of cuts,
and three load-refusal endings.
`resume --clears <threshold> --date <D>` lifts one after a `| <D> | Ruling | <threshold>: <decision> |` row; when
several are over at once, one resume names each (`--clears cuts --clears infrastructure-failures ...`), each with its
own row, and it is refused naming any threshold over its bound left out or without its row. A cleared threshold then
counts only later endings, and every other threshold keeps counting. The export (`status --export`) follows `slot_record.py`, the layout the
readout reads. The launcher checks the export against that layout before it writes it. It refuses to write the
export while any start still waits for a ruling. State lives in `$HOME/.local/state/lh-ladder`, or `<dir>/state`
for a rehearsal.

Tests run against stand-ins only. Scripts stand in for the harness's Python and for Podman, replaying the recorded
fixtures on a closed `PATH`. The upstream is `stub_api.py`, and the passthrough runs in rehearsal mode. No
container, network or CLI is used:

```
pytest -q -n 4 tests/experiments/test_long_horizon_launcher.py tests/experiments/test_long_horizon_ladder.py \
  tests/experiments/test_long_horizon_passthrough.py tests/experiments/test_long_horizon_slot_record.py \
  tests/experiments/test_long_horizon_readout.py
```

Task 7's rehearsal is where the real harness, Podman, relay and CLI are exercised.

## The readout (plan Task 6)

`slot_record.py` is the one definition of the launcher's export: its fields and types (in its docstring) and
`load`, which joins every start to its schedule slot and its D5 row and refuses anything that does not fit, naming the
record. Each start carries the class the launcher decided (`class`, with `stop_cause` for a stop from the closed
list `LAUNCHER_STOPS`, which also says where each cause can occur, found on a row of another class) and its D5 row as
evidence; a stop is never scored. A `contamination` result may sit on a start of any class: it excludes an
observation, and on any other class is listed and counted for D7.7 without changing the class. A reward is only what
a verifier gave: an observation with none, after any ending, is regraded (case 1), and one still with no reward file
after its regrades is an infrastructure failure on its own row, never scored. A regrade's trial is
`<attempt id>-regrade-<n>`, so its verifier's compose project and containers are `<attempt id>-regrade-<n>__verifier__…`
(Harbor lower-cases them), the attempt's own; it runs in its own session with its pid in `slot.json`, and reconcile
stops a dead launcher's regrade before running it again. A regrade whose load-gate wait was interrupted before any
regrade ran decides nothing: the start is listed open and the next launch's reconcile regrades it. Harbor refuses
to regrade a trial whose declared artifact was not collected (an agent that never wrote its output); the regrade's
output is kept in `regrade/<trial>.log`, and when it ends in that `RegradeError` and in no other problem, case 2's
reward of 0 stands, an observation flagged `artifact_absent` that the readout counts per task and effort; case 1 is
still "no reward after regrades", and any other refusal keeps the handling above (plan D5). A null
`minutes`, token count or `api_retry` was not recorded: the readout prints "not recorded", leaves it out of its
means and gives how many it left out; it never reads a null as zero. The launcher writes that layout and the readout
reads it. The export lists the attempts still open (`open`), which enter no count, and the readout says how many
there are. Both load the module by its path (the kit runs under `python -I`) and neither
imports the other.

`readout.py` turns the export into the readout of D6 and, at the end of the tranche, into `results/family.json` (step
7). It reads every rule from `ladder.json` (`readout`, `classification`, `attempt`, `schedule`) and prints no public
figure. Every figure is computed once, by `compute`, from the starts joined to their slots by slot id: each task's cells
and pooled count with their exact intervals and labels (a count pooled over tasks gets no interval), the band effort,
the effort test over complete triples with its verdict and the bound on the fall, the cost per effort, the lists
(exclusions, a contaminated attempt of any label by the SHA-256 of each term found, counted over every label for D7.7,
flags, cuts per effort, the pilot's attempts, refused connections, relay lookup timeouts apart from them, and the
regrades refused for a declared artifact never collected, per task and effort), the graded outcome, an earlier
label's counts and the allowance. The sidecar logs `bypass` when its lookup of `relay` times out; the launcher counts
a `bypass` toward the relay itself (an address the sidecar resolved `relay` to in the same log) as a relay lookup
timeout, never as a refused connection, so `egress_refused` holds only destinations outside the kit. The last three enter no rule.
**The graded outcome** is read only for the tasks in `readout.graded_outcome.verifiers` (`"ctrf"`: passed and total
of the verifier's `verifier/ctrf.json`), 13 of the 15 qualified tasks (Task 2b's second pass). For the other three of
the 16 the readout prints "pass or fail only": lake-temp-glm's report holds one test; wal-recovery-ordering's total is
the suite's on a pass and its gates' on a gate failure, so it counts unlike things; vba-userform-port runs no attempt
(not qualified; its labelled variant's report is a scoring wrapper, its graded checks hidden traces). The pooled screen applies when every effort has at least four scored
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
