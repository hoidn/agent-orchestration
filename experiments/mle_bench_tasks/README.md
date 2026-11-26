# MLE-bench task family kit

The kit of the [MLE-bench task family plan](../../docs/plans/2026-11-15-mle-bench-family-plan.md) (roadmap Phase
5b, steps 10 to 12). The plan owns the rules (its decisions M1 to M10), the ledger and every result; this page
says how the kit is operated on this machine. Its commands are for this machine and are not copyable examples.

**Nothing paid is approved.** This line has no rule in `AGENTS.md` and no approval row. Nothing on this page
calls a model, a provider CLI or Kaggle: the qualification check below runs the harness with the `oracle` and
`nop` agents only.

This page begins with plan Task 7, the qualification check on containers. Later tasks add their sections.

## Files

| File | What it does |
| --- | --- |
| `family.json` | The thirteen candidates, the class limits, the agent's time limit, the verifier's limits, the canary |
| `wrap.py` | A prepared competition to the agent's and the verifier's build contexts and the attempt, answers and sample packages, images named by digest (Task 1) |
| `verifier/`, `agent/` | The verifier's entry point and its one call into the benchmark's grader; the agent-side format check (Task 2) |
| `withhold_check.py` | The withholding check on an image's exported file system (Task 3) |
| `make_criterion.py`, `criterion_fields.json`, `tranches/`, `manifests/`, `weights.json` | The configuration as data (Task 4) |
| `screen.py` | The wrapper around the reviewed launcher (Task 5) |
| `screen_readout.py` | The readout (Task 6) |
| `qualify.sh`, `qualify.py` | The qualification check of one competition on containers (Task 7; this page) |

## Setup

What the check needs on this machine, and what it makes. Everything it writes is under `~/mle-cache` (this line's
cache, ruling M-b); it only reads `~/lh-cache`.

- **Already in place** (the ladder's kit and the scout's fact-finding put them there): rootless Podman 4.9.3; the
  ladder's harness environment `~/lh-cache/hvenv` (Harbor 0.25.0, podman-compose 1.6.0); the benchmark's clone
  `~/lh-cache/mle/src` at commit `507f92e1` (`family.json`, `benchmark.commit`; the check refuses another);
  its pinned wheels `~/lh-cache/mle/wheels` (scout report A); the egress sidecar's images, which the ladder's oracle
  check pulled.
- **Made by `qualify.sh` on its first run** (each step is idempotent, and a run refuses before it builds anything
  when one cannot be made):

  ```
  mkdir -m 700 -p ~/mle-cache ~/mle-cache/recordings    # a directory of its own, never a link (plan M4)
  ln -s ~/lh-cache/hvenv ~/mle-cache/hvenv               # the harness environment, shared with the ladder
  ```

  and `~/mle-cache/logs/limits-compose.yaml` and `containers-override.conf`, the screen tranche's host-side files
  as its criterion holds them (`tranches/screen-cpu/ladder.json`, `harness.host_side`). A file that is there with
  other content is refused, not overwritten. `screen.py` refuses a launch while `~/mle-cache/recordings` is
  missing or a link.
- **The base image**, `python:3.11-slim`, is pulled once by digest
  (`docker.io/library/python@sha256:61e01f72…`, Python 3.11.18; `BASE` in `qualify.sh`). Nothing is pulled by tag.
- **Room:** the check refuses under 60 GB free on `/home` or 20 GB on `/`. The fixture's images take about 1 GB.

## Running the qualification check

One competition per run, from the repository root, with a Python that has PyYAML (`PY`, default `python3`):

```
FIXTURE_CHECKS=1 experiments/mle_bench_tasks/qualify.sh tiny-tabular \
  tests/experiments/fixtures/mle_bench/tiny-tabular/competition tests/experiments/fixtures/mle_bench
```

For a real competition (plan Task 10) the second argument is the benchmark's competition directory and the third
the data directory the preparation wrote, and `FLOOR` gives the sample submission's score where the benchmark's
test lists one. `OUT` (default `~/mle-cache/qualify/<task name>`) must be empty or new; a run takes about
about 12 minutes for the fixture with its checks (about a minute a trial; the images build in a few minutes the
first time). Harbor runs one trial at a time, on the CPU set `8-31`.

What it does, in order:

1. Builds three images with no network: the verifier's base (the base image, the pinned wheels installed with no
   index, the benchmark's source under `/opt/mle-bench`), then `wrap.py`'s agent and verifier contexts. Each is
   named `localhost/mle-bench/<name>@sha256:<digest>`, the digest Podman reports for it, and the packages name
   both by that reference (plan M4).
2. Runs `withhold_check.py` on the agent image's file system, exported from a container that is never started.
   A fail stops the run: the competition is dropped (plan M3).
3. Builds the four controls of M2 with the benchmark's own grader, in the verifier image with no network and
   outside Harbor: the answers with rows replaced by the sample's, in a seeded order, bisected to one row either
   side of the bronze line and of the median. Each control's expected class is written down
   (`controls/controls.json`) before it goes through the verifier.
4. Runs each leg through Harbor as an attempt's path runs it: the package copied with the allowlist overlay of the
   tranche's criterion (by `ladder.py`'s own `overlay`), the limits file and the relay's compose file, an empty
   environment, the CPU set, and `--ek keep_containers=true` as the launcher passes it; the check then removes
   the trial's containers and networks by name, as the launcher does. The answers and sample legs run the
   `oracle` agent, the untouched leg the `nop` agent; each twice. Each control runs once with the `oracle` agent.
   After each trial the two images must still be in the store, or the run stops.

   **Why `keep_containers`:** without it Harbor's teardown runs `compose down --rmi local`, and podman-compose
   1.6.0 then force-removes every image whose name starts with `localhost/`, the packages' own images included
   (seen on the first run, 2026-11-26). `harbor trial regrade`, which the launcher runs without that option, does
   the same to the verifier image (seen once on the fixture). The plan's ledger row of 2026-11-26 carries this.
5. Prints the ten lines and exits 0 when all ten are ok, 1 otherwise (2: refused before anything was built).

### The ten lines

Each line is `<run>: ok|FAIL reward=… valid=… medal=… above_median=… score=… percentile=…`, from the reward file the
verifier wrote and Harbor read (`-` for a key the file does not hold), and after a FAIL the reason.

| Line | Is ok when |
| --- | --- |
| `answers 1`, `answers 2` | reward 1 with gold (medal 3) |
| `sample 1`, `sample 2` | reward 0, valid, with a score; equal to `FLOOR` when given |
| `untouched 1`, `untouched 2` | a written reward of 0 (a missing reward is a FAIL) |
| `control bronze-past`, `bronze-short`, `median-past`, `median-short` | the reward and the above-median flag written down for it, valid, the same score as the grader gave outside Harbor, and the percentiles of every scored run in the order of their scores |

On every line the second run's score must equal the first's, and the reward file must hold exactly the keys this
check recorded on 2026-11-26 (`qualify.py`, `SCORED_KEYS` and `UNSCORED_KEYS`): a change to the verifier's output
fails every line until the keys are recorded again. A control line also shows the grader's score outside Harbor
(`host_score`) and the rows replaced. A line that cannot be straddled (a metric too coarse) is `not built` and
FAIL; it qualifies only on a coordinator's ruling (plan M2).

### The fixture's six checks (`FIXTURE_CHECKS=1`)

After the ten lines, one `check <name>: ok|FAIL …` line each (plan Task 7):

| Check | Is ok when |
| --- | --- |
| `digest-start` | the legs ran on the two images named by digest, and `podman pull` of either reference fails (there is no registry at `localhost`), so no trial pulled them |
| `tag-refused` | `wrap.py packages` with the agent image's tag in place of its digest exits 2 with `unpinned_image` and writes nothing |
| `rebuilt-image` | after the agent image is rebuilt under the same name with the answers planted in `/home/data/`, the tag names the new digest, and the package's trial does not run on it. On this machine the trial does not start at all: the rebuild takes the name off the original image, so `<name>@<original digest>` no longer resolves in the store, Podman tries a pull, and the pull fails. A trial that did start and saw no planted file would also pass |
| `withholding` | the check passed on the real agent image and names its digest, and fails on the rebuilt one with the planted file as a `private_hash` finding |
| `symlink` | a submission that is a symbolic link to the answers' path inside the verifier earns reward 0, not valid. The record does not say whether Harbor's upload dropped the link or the verifier refused it; either gives this outcome |
| `relay` | a probe verifier image (the verifier image with another `test.sh`) cannot resolve `relay`, while the agent's container of the same trial can |

The probe images (the planted image and the relay probe) are removed at the end; the competition's three images
are kept, because the tranche's `tasks.json` names them by digest. To remove the fixture's after a check:

```
podman rmi localhost/mle-bench/tiny-tabular-agent:qualify localhost/mle-bench/tiny-tabular-verifier:qualify
```

### Outputs

Under `OUT`: `qualify.log` (every step, the harness's exit codes, the load at each start), `images.txt` (each
image's reference and size), `contexts.json` and `packages.json` (`wrap.py`'s records), `withholding.json`,
`controls/`, `outcomes.json` (the rewards of every trial by label), `jobs/<label>/` (Harbor's trial directories)
and `run/<label>/` (the overlaid package each trial ran).

## Tests

No container, network or provider; the grader is a stand-in with the fixture's grade function:

```
pytest -q -n 4 tests/experiments/test_mle_bench_qualify.py
```
