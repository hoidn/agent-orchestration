# MLE-bench as tasks of the long-horizon harness: facts found on this machine

**Status: historical record, written 2026-11-15.** Role: research (fact finding, no spend), for the
[MLE-bench task family plan](../plans/2026-11-15-mle-bench-family-plan.md), which cites it by section letter. It
records what was true of this machine and of the installed harness on that day and selects no work.
No provider call was made, the Claude Code CLI was not run, nothing was downloaded from Kaggle, no root command
was run, no repository file was changed. Each claim says how it was established: **ran** (I ran it here and
show the output), **source** (I read it in the named installed or cloned source), or **not settled**.

Order: D and I first (the plan's design depends on them), then A, B, C, E, F, G, H, J, and the closing lists.

---

## D. Harbor 0.25.0 as installed (`~/lh-cache/hvenv`, with podman-compose 1.6.0)

Paths below are relative to `~/lh-cache/hvenv/lib/python3.12/site-packages/harbor/` unless stated.

### D1. Data: a read-only host mount is possible, but only for the agent's container, and it is a run setting, not a task field

- **A task definition has no mount field.** `models/task/config.py`, classes `EnvironmentConfig`, `AgentConfig`,
  `VerifierConfig`, `TaskConfig`: none has a mount or volume field. (source)
- **A run can mount a host directory into the agent's container.** `models/trial/config.py`, class
  `EnvironmentConfig` (the run-level one), field `mounts: list[ServiceVolumeConfig]`, described there as
  "Additional mounts for the agent environment only". `ServiceVolumeConfig` (same file) is the Compose long volume
  form: `type` (`bind`, `volume` or `image`), `source`, `target`, optional `read_only: true`, optional `bind`
  (for example `{"selinux": "z"}`). The command line is `harbor run --mounts '<JSON array>'` (`cli/jobs.py`;
  `--mounts-json` is the older spelling). (source)
- **How it reaches the container.** `trial/trial.py`, `Trial._init_agent_environment` passes
  `mounts=self.config.environment.mounts`; `environments/docker/docker.py`,
  `DockerEnvironment._write_mounts_compose_file` writes them to a Compose override (`services.main.volumes`, via
  `write_mounts_compose_file` in `environments/docker/__init__.py`) that `_docker_compose_paths` adds after the
  task's own compose file and after any `--extra-docker-compose`. podman-compose 1.6.0 turns `read_only: true`
  into the `ro` mount option (`podman_compose.py`, the mount-option code that reads `mount_desc.get("read_only")`).
  (source)
- **Two other ways that also work for the agent's container:** a task-authored `environment/docker-compose.yaml`
  with a `volumes` entry on service `main` (it is merged by `_docker_compose_paths`), and an extra compose file
  given with `--extra-docker-compose` (the kit already passes two: the process limit and the relay). (source)
- **None of these reaches a separate verifier container.** `trial/trial.py`, `Trial._separate_verifier_env` builds
  the verifier's environment with `extra_docker_compose` emptied and passes only `auto_mounts` (the verifier log
  directory); `check_trial_config` in the same file prints, for a task with a separate verifier, "Configured
  runtime overrides apply only to the agent environment and are not propagated to separate verifier environments
  ... Bake grading dependencies into the verifier image under tests/ or declare required agent outputs as
  artifacts." (source)
- **Consequence for MLE-bench.** Public data may be mounted read-only (no image rebuild per competition, and the
  data is not copied per attempt) or baked into the agent image. The private answers cannot be mounted into the
  verifier by a run setting: they must be in the verifier image (D3), or be given by a task-authored
  `tests/docker-compose.yaml` volume (the verifier's own compose file is honoured; see D3).

### D2. GPU: Harbor refuses a task that asks for a GPU under Podman; an extra compose file with a device entry is the way

- **`[environment] gpus = N` is wired for the Docker engine only.** `environments/docker/docker.py`,
  `DockerEnvironment.capabilities`: `gpus=self.type() == EnvironmentType.DOCKER and not self._is_windows_container`,
  with the comment "GPUs are reserved with a Compose nvidia device request, which Harbor only wires up for Linux
  containers on the Docker engine". `environments/podman.py`, `PodmanEnvironment.capabilities` only switches
  `windows` off, so `gpus` is False for Podman. `environments/base.py`, `BaseEnvironment._validate_gpu_support`
  then raises `RuntimeError("Task requires N GPU(s) but ... environment does not support GPU allocation ...")` when
  the task's `gpus` (or the run's `override_gpus`) is above zero. So a Podman task must leave `gpus` at 0 or
  unset. (source)
- **An extra compose file is accepted and podman-compose 1.6.0 understands both spellings.**
  `podman_compose.py`, `container_to_args`: `for item in cnt.get("devices", []): podman_args.extend(["--device",
  item])`, so `devices: ["nvidia.com/gpu=all"]` on service `main` becomes `podman run --device nvidia.com/gpu=all`.
  `container_to_gpu_res_args` also maps a Compose reservation (`deploy.resources.reservations.devices` with
  `driver: nvidia`, `capabilities: [gpu]`) to `--device nvidia.com/gpu=all` (or one `--device nvidia.com/gpu=<i>`
  per `count`/`device_ids`) and adds `--security-opt=label=disable`. (source)
- **So the GPU overlay is one more `--extra-docker-compose` file** (agent container only, which is what is
  wanted), for example:

  ```yaml
  services:
    main:
      devices: ["nvidia.com/gpu=all"]
      security_opt: ["label=disable"]
      shm_size: "8g"        # PyTorch data loaders need shared memory; podman-compose passes --shm-size
  ```

  The host has had a working CDI specification since 15:11 today (section F), and this overlay was run through
  Harbor: `nvidia-smi` inside the agent's container shows the RTX 3090 (D5). (source for the mapping; ran for the
  pass-through)

### D3. A verifier in its own container: `environment_mode = "separate"`, image from `docker_image` or from `tests/Dockerfile`

- **Declaration.** `models/task/config.py`, `VerifierConfig`: `environment_mode` (`shared` or `separate`) and
  `environment` (an `EnvironmentConfig`: `docker_image`, `cpus`, `memory_mb`, `build_timeout_sec`, network
  fields). When `[verifier.environment]` is set, the mode defaults to separate. (source)
- **Where the verifier image comes from.** `models/task/verifier_mode.py`,
  `resolve_verifier_environment_definition`: (1) `[verifier.environment] docker_image` if set; else (2) a
  `Dockerfile` or `docker-compose.yaml` in the task's `tests/` directory, built with `tests/` as the context; else
  (3) a fresh copy of the agent's environment. In cases 1 and 2 the definition is marked `bundled_tests`, and
  `Trial._run_separate_verifier` then passes `skip_tests_upload=True`: Harbor uploads nothing from `tests/`, so
  the image itself must hold `/tests/test.sh`, the grader and the answers. (source)
- **What crosses from the agent to the verifier.** Only the paths the task lists under `artifacts = [...]` in
  `task.toml` (and the convention directory `/logs/artifacts`): `Trial._collect_artifacts_phased` downloads them
  from the agent's container to the trial directory on the host, and `_run_separate_verifier` uploads them into the
  verifier container at the same paths (`ArtifactHandler.upload_artifacts`). Nothing flows the other way. (source)
- **What the verifier returns.** `verifier/verifier.py`, `Verifier.verify`: it runs `/tests/test.sh`, then reads
  `/logs/verifier/reward.json` (preferred) or `/logs/verifier/reward.txt`. `_parse_reward_json` accepts a JSON
  object of finite numbers; `models/verifier/result.py`: `rewards: dict[str, float | int]`. So one verifier can
  return several numbers (for example `reward`, `score`, `any_medal`, `above_median`, `percentile`), but no
  strings and no null. A score that the grader gives as `None` (invalid submission) has to be left out or coded
  as a number. (source)
- **How the kit's Terminal-Bench tasks do it today.** Every cached 4.1.0 package (`~/lh-cache/tasks41/<task>/x/
  task.toml`) has `[verifier] environment_mode = "separate"` and `[verifier.environment] docker_image =
  "harborframework/terminal-bench:<task>-verifier-<hash>@sha256:..."`, a second pinned image that holds the tests;
  the agent image is `[environment] docker_image = "...-environment-...@sha256:..."`; the agent's output crosses
  by `artifacts = ["/app/..."]`. The package's `tests/` directory (with its `Dockerfile`) and `solution/` stay on
  the host; the `oracle` agent uploads `solution/` into the agent container and runs `solve.sh`. (ran: read
  `batched-eval-parity/x/task.toml` and listed its tree)
- **Consequence for MLE-bench.** The private answers go into the verifier image (built from `tests/Dockerfile`
  with the answers copied into the build context, or built once and referenced by `docker_image`). The agent
  container never holds them. The oracle agent's `solution/solve.sh` would write the answers file as the
  submission, so for the oracle run only, the answers are also in `solution/` on the host and are uploaded into
  that one container.

### D4. Time limits: all are plain numbers of seconds in `task.toml`; 86,400 s is expressible

- **Task fields** (`models/task/config.py`): `[agent] timeout_sec` (float or none; none means no limit),
  `[verifier] timeout_sec` (default 600), `[environment] build_timeout_sec` (default 600),
  `[verifier.environment] build_timeout_sec`, and the health check's own timings. There is no validator that caps
  any of them. (source)
- **Run-level settings** (`models/trial/config.py`; `cli/jobs.py`): `--agent-timeout-multiplier`,
  `--verifier-timeout-multiplier`, `--agent-setup-timeout-multiplier`,
  `--environment-build-timeout-multiplier`, `--timeout-multiplier`; and in a config file
  `agent.override_timeout_sec`, `agent.max_timeout_sec`, `agent.override_setup_timeout_sec`,
  `verifier.override_timeout_sec`, `verifier.max_timeout_sec`. `trial/trial.py`, `Trial._resolve_timeout_sec`:
  `min(base, max or infinity) * multiplier`. The agent setup limit (CLI install) is the agent class's
  `DEFAULT_SETUP_TIMEOUT_SEC` (360 s in `agents/base.py`) times its multiplier; the kit uses 3. (source)
- **A 24-hour agent limit** is `[agent] timeout_sec = 86400.0` (the Terminal-Bench tasks have `28800.0`), and no
  code path shortens it. What a 24-hour limit meets outside Harbor is in section I (the launcher's wall bounds,
  the allowance guard's windows, the per-attempt dollar cap).

### D5. Hands-on probe of D1 to D4 (ran, 2026-11-15, Harbor 0.25.0 on rootless Podman 4.9.3, no model call)

A scratch task in `~/lh-cache/mle/probe/task` (image `docker.io/library/debian:bookworm-slim`; `[agent]
timeout_sec = 86400.0`; `[verifier] environment_mode = "separate"`; a `tests/Dockerfile` that copies a
two-line answers file to `/private/answers.csv` and a `test.sh` that writes `reward.json`; `artifacts =
["/home/submission/"]`), run with the kit's wrapper and environment
(`~/lh-cache/bin/harbor_patient.py run --env podman -n 1 -q -y --path … --agent <oracle|nop> --mounts '[{"type":
"bind","source":"<host dir>","target":"/home/data","read_only":true}]' --extra-docker-compose …`). Results are in
`~/lh-cache/mle/probe/jobs/`.

| Check | Result |
| --- | --- |
| The host directory in the agent's container, read-only | `/proc/mounts` in the container: `/dev/nvme0n1p1 /home/data ext4 ro,relatime`; `touch /home/data/x` fails with "Read-only file system" |
| The answers and the tests are absent from the agent's container | `ls /private /tests` in the agent's container: "No such file or directory" for both |
| The verifier's container holds the answers and gets the submission | its listing shows `/private/answers.csv` and `/home/submission/submission.csv` (the artifact, carried over) |
| The run's mount does not reach the verifier | `/home/data` does not exist in the verifier's container; Harbor also prints the warning quoted in D1 |
| A reward with several numbers | `result.json`: `verifier_result.rewards = {"reward": 1, "score": 0.0153, "any_medal": 1, "above_median": 1, "percentile": 97.5}`; the job summary prints a mean per key |
| The do-nothing agent | no `/home/submission`: the artifact's status in `artifacts/manifest.json` is `failed`, the verifier still runs, `test.sh` writes `{"reward": 0, …}`, no exception. So "an untouched environment scores zero" holds in a first run without special handling; the kit's regrade path is where an absent artifact is refused (section I2) |
| A 24-hour agent limit | the task loaded and ran with `timeout_sec = 86400.0`; the limit itself was not waited out |
| `[environment] gpus = 1` under Podman | the harness exits 1 before any container: `RuntimeError: Task requires 1 GPU(s) but EnvironmentType.PODMAN environment does not support GPU allocation` (from `_validate_gpu_support`) |
| The GPU through an extra compose file | with `--extra-docker-compose ~/lh-cache/mle/probe/gpu-compose.yaml` (`devices: ["nvidia.com/gpu=all"]`, `security_opt: ["label=disable"]`, `shm_size: "2g"` on `main`) and `gpus` unset, `nvidia-smi` inside the agent's container prints `NVIDIA GeForce RTX 3090, 24576 MiB, 580.178.04`; `/dev/shm` is 2.0 G; the read-only mount, the process limit file and `taskset -c 8-31` were in force in the same run |
| The image must have `bash` | a first try on `alpine:3.20` failed in environment setup: Harbor's readiness probe runs `exec main bash -c true` ("executable file `bash` not found"). Every agent and verifier image needs `bash` |
| Build and teardown | the verifier image is built from `tests/` at each trial and removed with the trial (no image is left in the store); no container or network was left behind; one oracle trial took about 2 minutes at a load average above 100 |
| Compose file order | resources, the prebuilt (or build) file, each `--extra-docker-compose` in order, the environment file, the mounts file (read from the failing command line Harbor printed) |

Not exercised: an agent phase under the `allowlist` network mode together with the mount and the GPU device (the
kit's oracle passes ran the allowlist without them; the egress sidecar shares the network namespace only, so no
interaction is expected, but it was not run), the Claude Code agent's install in such an image, and a verifier
that runs the real `mlebench` grader in its container (the grader was run on the host, section B).

---

## I. What in the kit is tied to Terminal-Bench (facts only; all read in source at the worktree `.worktrees/integ21/experiments/long_horizon_tasks/`)

**Answer.** The credential route (relay, passthrough, fake token, token scan), the money accounting, the stops
and pauses, the D5 ending table and the harness invocation do not depend on the task source. What does is listed
below: the task identity and its image pins, the binary reward, the three-effort schedule and its readout, the
canary and the contamination terms, the 8-hour timings, the fixed CPU set with one concurrency number and no GPU
slot, the per-task dollar cap formula, and the image and oracle checks.

### I1. Task source, identity and digest pins

| Where | Assumption |
| --- | --- |
| `ladder.py`, constant `PACKAGES = "tasks41"`, `package()` | A task's package is `$LH/tasks41/<task>/x`, a Harbor Hub 4.1.0 package fetched by digest. |
| `ladder.py`, `_task_record()` | Looks a task up in `tasks.json` by the last part of its name (`terminal-bench/<task>`). |
| `ladder.py`, `task_refusal()` | Refuses a task unless (a) Harbor's `Packager.compute_content_hash` of the package equals `tasks.json` `digest_4_1_0`; (b) `task.toml` holds `[environment] docker_image` and `[verifier.environment] docker_image` equal to `tasks.json` `environment_image` and `verifier_image` (both `repo:tag@sha256:` pins); (c) `[agent]` sets no network key. A task whose images are built locally from a Dockerfile has no `docker_image` line and no registry digest. |
| `ladder.py`, `overlay()`, `overlay_lines()`; `oracle_check.sh`, `overlay_task()` | The package is copied and exactly two lines (`network_mode`, `allowed_hosts`) are inserted after its one `[agent]` line; removing them must give the published `task.toml` back byte for byte. The digest of the two lines must equal `ladder.json` `tasks.overlay_digests[<task>]`. The identity rule (`ladder.json` `tasks.identity`) is "every file equals the benchmark's published 4.1.0 digest". An MLE-bench wrapper has no published package to be equal to. |
| `tasks.json` | Top-level `dataset` (`terminal-bench/terminal-bench@4.1.0`), `checked_copy`; per task `digest_4_1_0`, `digest_4_0_0`, `checked_copy_digest`, `checked_copy_vs_4_1_0`, `environment_image`, `verifier_image`, `images` (compressed and unpacked sizes of pulled images), `withholding`, `variant`, `oracle_evidence` with `reference: [k, n]` and `untouched: [k, n]`. |
| `ladder.json` `tasks` | `list[]` entries carry `changed_since_4_0_0`, `public_mean_usd_at_max`, `cap_usd`; `qualification` is "reference reward 1 five of five, untouched reward 0 five of five"; `images` is "the ones 4.1.0 pins, pulled by digest; nothing is built". |
| `oracle_check.sh`, `task_json()`, `prepare()`, `ensure_image()` | Reads `tasks.json` by `"terminal-bench/" + <task>`; copies from `$LH/tasks41/<task>/x`; pulls both images as `docker.io/<ref>` by digest and needs their recorded sizes; deletes what it pulled afterwards (`release()`). No path builds an image or checks a local one, except the one labelled variant (`variant_image()`, `prepare_variant()`), which shows the form a locally built verifier image takes: a `localhost/...` name written into the copy's `docker_image` line and an image id recorded in `tasks.json`. |
| `manifest.py`, `files()`, `NOT_COVERED` | Covers every file of the kit directory, so `tasks.json` and `ladder.json` as they are; the task packages and images are outside it "by their hashes and digests only". Prepared competition data, the private answers and locally built images would be outside too, and nothing records their hashes today. |

### I2. The reward's shape

| Where | Assumption |
| --- | --- |
| `ladder.py`, `_reward()` | Reads `result.json` → `verifier_result.rewards.reward`, one key. Other keys of `rewards` are ignored and are not exported. |
| `slot_record.py`, docstring and the reward check ("reward ... is not 0, 1 or null") | A start's `reward` must be exactly 0, 1 or null; success is `reward == 1`. A medal coded as 0 or 1 fits; a score or percentile in `reward` is refused. |
| `slot_record.py`, `START` layout | The only graded field is `graded: {"passed", "total"}` (sub-tests). There is no field for a continuous score, a percentile, a medal colour, or "above median". |
| `ladder.py`, `graded()`; `readout.py`, `_graded()`; `ladder.json` `readout.graded_outcome.verifiers` | The graded outcome is read from the verifier's `verifier/ctrf.json` (`results.summary.passed` and `.tests`), a pytest report; the map names tasks with value `"ctrf"`, anything else prints "pass or fail only". |
| `summarize.py` (the oracle summary), its outcome function | "pass" needs reward exactly 1 **and** a `ctrf.json` whose tests all passed; no `ctrf.json` or zero tests is "no evidence". A grader that writes only `reward.json` gives no evidence under this rule. |
| `ladder.py`, `regraded()`, `_regrade_once()`, `absent_artifact()` | A regrade is Harbor's verifier-only rerun of the trial; Harbor refuses it when a declared artifact was not collected (an agent that wrote no `submission.csv`), and the kit then lets a reward of 0 stand (`artifact_absent`) only for tasks on `tasks.load_sensitive`, and otherwise ends in "no reward after regrades", an infrastructure failure. An MLE attempt that wrote no `submission.csv` is such a trial if it ever needs a regrade. In a first run it does not: the verifier still runs and can write a reward of 0 (ran, D5), provided `test.sh` writes one when the file is missing. |

### I3. The schedule, the efforts and the readout

| Where | Assumption |
| --- | --- |
| `ladder.py`, constants `MODEL`, `EFFORTS`; `_criterion_refusal()` | One model (`claude-haiku-5-5`) and exactly the efforts low, medium, high; a criterion with others is refused. |
| `ladder.py`, `schedule()`, `smoke_task()`, `pilot_task()`; `ladder.json` `schedule` | Rounds of blocks, one block per qualified task, each block the three efforts; five rounds; the smoke and pilot tasks are named Terminal-Bench tasks with named fallbacks. The MLE screen of roadmap step 11 is three attempts at one effort. |
| `readout.py`, `compute` and its helpers (`_counts`, `_triples`, `effort_test`, `fall_bound`); `ladder.json` `readout` | Cells of five, pooled over fifteen, "screened in" at 1/15 to 1/3, the effort sign-flip test over complete triples. Every rule is over binary successes per (task, effort). |
| `slot_record.py`, `SLOT` | A slot is (task, effort, round); there is no resource kind (GPU or not). |

### I4. The canary and the contamination terms

| Where | Assumption |
| --- | --- |
| `ladder.py`, `canary_term()`, `scan_terms()` | Every package's `task.toml` holds a line whose SHA-256 is `ladder.json` `readout.contamination_scan.canary_sha256` (the `harbor-canary GUID` line); a live launch refuses a package without it. MLE-bench has no canary. |
| `ladder.json` `readout.contamination_scan.terms` | The terms are `harbor-framework/terminal-bench` and `tasks/<task>/solution` for each task: strings that mark a look at the benchmark's repository. For Kaggle competitions the public solutions are everywhere and in the training data; no term list exists. |
| `ladder.py`, `contamination()` | Scans `agent/` and `artifacts/` of the trial for the terms. With an MLE task the artifacts are a submission CSV (and perhaps code), which can be large (denoising-dirty-documents: one row per pixel). |
| `image_check.py`, withholding check (module docstring, `canary_id`, `canary_bucket`) | Exports the agent image and searches it for the package's `solution/` and `tests/` files by path, by SHA-256, by canary and by near-copy lines. For MLE the thing to withhold is the answers file (`private/`), which the check would find by SHA-256 only if the answers sit in the package's `tests/` or `solution/`; the public data also contains files derived from the same source (the new training set), so near-copy line matching against an answers CSV is not meaningful as written. |
| `ladder.py`, `allowlist()`; `ladder.json` `network.agent_phase.allowed_hosts` | Package indexes and distribution mirrors only (section H lists them). No model hub. |

### I5. Timings (all sized for an 8-hour agent limit)

| Where | Assumption |
| --- | --- |
| `ladder.json` `harness.agent_timeout` | "the task's own", `seconds_for_all_16 = 28800`, multiplier 1. The launcher itself adds no wall bound on an attempt (`Attempt.follow()` waits for the harness to exit), so a 24-hour `timeout_sec` would be honoured by Harbor. |
| `oracle_check.sh`, `wall_bound()` | A trial's bound is the task's agent + verifier + two build limits + `WALL_MARGIN_S` (1,800 s). With 86,400 s an oracle trial would be allowed about 25 hours; the oracle itself takes seconds. |
| `ladder.py`, `token_scan()` | The scan subprocess has a 3-hour timeout. It reads the attempt's files; `runtime_check()` with `export` (the smoke, the pilot, a rehearsal) scans every agent container's exported file system. An agent container holding a deep-learning stack, downloaded weights and checkpoints is many GB (bind-mounted data is not in a `podman export`). |
| `ladder.py`, `podman()`, `_kept()`, `_export_scan()` | `podman inspect` and `podman logs` have a 300 s timeout. `podman export` is streamed into the token scan with no timeout of its own, under the scan's 3 hours; a failed export is "an incomplete scan", which is a stop. An egress log kept in memory for a 24-hour attempt (`_kept` reads the whole `podman logs` output) grows with every connection the agent makes. |
| `ladder.json` `usage_limits`; `ladder.py`, `check_limits()`, `gate_state()` | A usage limit cuts every attempt in flight (row 10, class cut) and the slot is run again as a new counted start. The subscription's windows are five hours and weekly; a 24-hour attempt spans at least four five-hour windows, so one limit anywhere in them loses the whole attempt. |
| `ladder.json` `allowance_guard` (`closing_margin`: "the length of the longest pilot session, rounded up to the hour"); `ladder.py`, `_hours_refusal()`, `window_at()` | Starts are allowed only in the owner's windows of hours, each with a meter reading, and not within the closing margin of a window's end. With sessions of up to 24 hours the margin exceeds any daily window. |
| `ladder.json` `host.load_wait` (`gate_closed_s = 7200`), `load_gate` (24 of 32 cores) | The load gate is judged before each start; a GPU training run by one attempt raises the load other starts see for hours. |
| `passthrough.py` (per `ladder.json` `credential.passthrough.in_flight`) | One request in flight per slot, a second waits at most 300 s. No slot lifetime limit was found (read: the `credential.slot` rules; the slot closes when the attempt's containers are gone). |
| Harbor, `agents/base.py` `DEFAULT_SETUP_TIMEOUT_SEC = 360`, times the kit's multiplier 3 | 18 minutes for the CLI install; unrelated to the agent limit. |

### I6. Money

| Where | Assumption |
| --- | --- |
| `ladder.json` `caps` (`formula`: `max(3.00, 3 × public_mean_usd_at_max)`); `ladder.py`, `cap()` | A task's per-attempt cap comes from the public Terminal-Bench mean cost per trial. No such figure exists for an MLE competition under Claude Code. Caps today are USD 3.00 to 22.92. |
| `ladder.json` `ceiling` (`total_usd = 200`, `starts = 240`, reservation = cap + 1) | The tranche's totals; a new family needs its own. The roadmap's decision 17 speaks of USD 200 per calendar day; the kit has no per-day ceiling, only a total. |
| `ladder.json` `allowance_guard.reservation` ("one third of the slot's cap") | Sized from the pilot's sessions of one task. |

### I7. Host resources

| Where | Assumption |
| --- | --- |
| `ladder.json` `host.cpu_set = "8-31"`, `cpu_count = 24`; `ladder.py`, `attempt_command()` (`taskset -c`); `oracle_check.sh`, `CPUS` | One CPU set for every attempt and verifier; the containers inherit the affinity. The task's own `cpus` and `memory_mb` are passed through (`harness.cpus_and_memory = "the task's own"`; the 16 Terminal-Bench packages ask for 2 to 8 CPUs and 4 or 8 GB, no GPU; ran: read from their `task.toml`). |
| `ladder.json` `host.concurrency` (smoke 1, pilot 3, rounds 4); `ladder.py`, `CONCURRENCY`, `Tranche` | One number per kind of entry. Nothing says "at most one attempt on the GPU at a time". |
| `ladder.py`, `attempt_command()` | The extra compose files are fixed: `limits-compose.yaml` (`pids_limit: 4096`) and `relay-compose.yaml`. A GPU device file and a data mount would be a third and a fourth `--extra-docker-compose` / `--mounts`, per task. `ladder.py`, `harness_refusal()` checks the content of the two host-side files against `ladder.json` `harness.host_side`. A `pids_limit` of 4,096 is tight for PyTorch data loaders with many workers but not prohibitive. |
| `ladder.json` `host.disk_plan`, `disk_stop_free_gb = 20`; `ladder.py`, `disk_paths()`, `free_gb()`; `oracle_check.sh`, `STOP_GB = 25`, `room_ok()` | No start under 20 GB free on `/` or `/home` (25 for the oracle and image checks). The plan counts 23.86 GB of pinned Terminal-Bench images and 2.74 GB of output per trial. `/home` has 62 GB free today (section G). |
| `ladder.py`, `tear_down()` / `remove_containers()`, `--ek keep_containers=true` | The attempt's containers are kept until the launcher has scanned them, then removed by name. A kept GPU container holds no GPU memory once its processes have exited. |

### I8. The agent's instruction and tools

| Where | Assumption |
| --- | --- |
| `ladder.json` `attempt.deny_list`, `init_event.tools = ["Bash", "Edit", "Read"]` | Unchanged for MLE. Note that long training under `Bash` meets the CLI's own per-command timeout (not read here: the CLI is not run and its bundle was not opened for this). |
| `ladder.json` `attempt.output_tokens_env`, `cli_version = "2.1.311"` | Unchanged. |
| The instruction | A Terminal-Bench package's `instruction.md` is the published one. An MLE task's instruction has to be assembled (the benchmark's `environment/instructions.txt` plus the competition's `description.md`); section B shows both. |

---

## A. The benchmark package

**Answer.** The clone is at commit `507f92e1138bb6e40dac5c6ee7a6758e6424bf97` (2026-04-24, the same commit the
feasibility report read). The package needs Python 3.11 or later and declares 23 direct dependencies, of which
the grader and the preparation scripts of the 16 candidates need eight (`appdirs`, `diskcache`, `kaggle`, `pandas`,
`py7zr`, `pyyaml`, `scikit-learn`, `tenacity`; `tqdm`, `numpy` and `scipy` come with them). I installed those and
`pillow` (325 MB) and left the rest out. The leaderboard snapshots are Git LFS files and all 16 were fetched from the public media address
without Git LFS tooling (1.4 MB together), each matching its pointer's SHA-256.

- **Clone.** `~/lh-cache/mle/src`, shallow, with `GIT_LFS_SKIP_SMUDGE=1`; `git-lfs` is not installed on this
  machine (`git: 'lfs' is not a git command`). 7 MB. (ran)
- **What installing needs** (`pyproject.toml`; source): `requires-python = ">=3.11"`; dependencies `appdirs`,
  `docker`, `fastparquet`, `kaggle>=1.6,<1.7`, `levenshtein`, `openai`, `pandas>=2.2`, `pyyaml`, `py7zr`,
  `scikit-learn>=1.5`, `tensorflow>=2.16`, `pillow`, `python-dotenv`, `aiohttp`, `tenacity`, `nbformat`,
  `nbconvert`, `ipython`, `pymongo`, `pycocotools`, `diskcache`, `pyquaternion`, `shapely`. None has an upper
  bound except `kaggle`. `tensorflow` alone is about 2 GB installed with its dependencies (estimate), and no
  file under `mlebench/` imports it (ran: grep over the package's imports).
- **The versions are not pinned, and today's latest do not all fit Python 3.11.** A first unpinned fetch brought
  `pandas 3.1.1`, and `numpy 2.5.5` and `scipy 1.18.1` only as source archives (no CPython 3.11 wheel). I pinned
  to the versions the benchmark's own agent image uses (`environment/requirements.txt`): `numpy 1.26.4`,
  `pandas 2.2.2`, `scikit-learn 1.5.1`, `scipy 1.14.1`, `pillow 10.4.0`, `py7zr 0.22.0`, `kaggle 1.6.17`; that
  also needs `joblib 1.4.2` (the latest wants a package that scikit-learn 1.5.1 does not) and `pyppmd 1.1.1`.
  (ran) A verifier image should pin the same set: the preparation's output is verified by checksum, and a newer
  pandas could change it.
- **What I installed** (ran): a virtual environment `~/lh-cache/mle/venv` on CPython 3.11.13 with 38 packages
  from a local wheel directory `~/lh-cache/mle/wheels` (95 MB, each file checked against PyPI's SHA-256), installed
  offline. `mlebench` itself is not built: a one-line `mlebench-src.pth` in the environment's `site-packages`
  points at the clone, because the registry reads its files relative to the repository (`mlebench/utils.py`,
  `get_module_dir`, `get_repo_dir`). The command line is `venv/bin/python -m mlebench.cli ...`.
- **Left out:** `tensorflow`, `docker`, `openai`, `fastparquet`, `levenshtein`, `python-dotenv`, `aiohttp`,
  `nbformat`, `nbconvert`, `ipython`, `pymongo`, `pycocotools`, `pyquaternion`, `shapely`. They are needed only by
  the upstream agent runner (`run_agent.py`, `agents/`), the extras, and graders or preparation scripts of
  competitions outside the 16 (ran: the imports of the 16 candidates' `grade.py` and `prepare.py` are `pandas`,
  `numpy`, `sklearn`, `scipy`, `tqdm` and the standard library).
- **The leaderboard snapshot** (source and ran): one file per competition,
  `mlebench/competitions/<id>/leaderboard.csv`, tracked by Git LFS (`.gitattributes`: `*.csv`, the
  `top_solutions` directories and `runs/**/*.json[l]`). A plain clone holds a three-line pointer (`oid sha256:…`,
  `size …`). The real file is at
  `https://media.githubusercontent.com/media/openai/mle-bench/<commit>/mlebench/competitions/<id>/leaderboard.csv`.
  Columns: `scoreNullable, teamId, hasTeamName, submissionDate, score, hasScore`, one row per team, best first.
  The medal thresholds are not stored: the grader computes them from this file at grading time (section B).
- **Fetched** (ran): the 16 candidates of the report's section 8.2 (13 ranked and the 3 CPU-only extras), 4 kB
  to 245 kB each, 1,427,635 bytes together, every SHA-256 equal to its pointer's. Kept in `~/lh-cache/mle/lfs/<id>/`
  and copied over the 16 pointers in the clone (so `git -C ~/lh-cache/mle/src status` shows 16 modified files;
  `git checkout -- .` restores the pointers). Team counts (rows): tweet-sentiment 2,225; petfinder 3,538;
  essay-scoring-2 2,708; us-patent 1,889; cassava 3,901; whale-categorization 529; leaf-classification 1,596;
  jigsaw-toxic 4,539; kuzushiji 294; text-normalization-russian 163; mlsp-2013-birds 81; lmsys 1,688; chaii 943;
  text-normalization-english 261; nomad2018 879; spooky 1,242. They equal the report's "Teams" column.
  `experiments/competition_categories.csv` (6 kB, the size table) was fetched the same way.

## B. Grading offline

**Answer.** Grading one submission needs three things and no network: the answers file under
`<data dir>/<id>/prepared/private/`, the competition's directory in the `mlebench` package (with the real
`leaderboard.csv`), and pandas, numpy, scikit-learn and scipy. I ran the real grader on hand-made answers for
the three CPU-only candidates: the answers file graded as a submission gets a gold medal, a missing or malformed
file gets `score: null` and no medal. The grader returns booleans and thresholds; it computes no percentile, but
the leaderboard file it reads is enough to compute one.

### What `grade_csv` reads (source: `mlebench/grade.py`, `grade_helpers.py`, `registry.py`, `data.py`)

- `Registry.get_competition(id)` loads `competitions/<id>/config.yaml`, **reads `description.md`**, and
  **imports both `grade.py` and `prepare.py`** of the competition (so the preparation script's imports must be
  installed even for grading). It reads no data.
- `is_dataset_prepared(competition, grading_only=True)` needs only: the `prepared/private` directory, not empty,
  and the answers file. The public directory is not needed. (ran: my synthetic data directory held nothing else)
- `competition.grader(submission_df, answers)` calls the competition's `grade` function; an
  `InvalidSubmissionError`, or any other exception, gives `score = None`. The score is rounded to 5 decimals.
- `Grader.rank_score(score, leaderboard)` reads the `score` column of `leaderboard.csv`. Direction: lower is
  better when the first row's score is below the last row's. Thresholds by the number of teams n: n < 100: gold at
  position max(1, ⌊0.1n⌋), silver ⌊0.2n⌋, bronze ⌊0.4n⌋; 100 ≤ n < 250: gold at position 10, silver ⌊0.2n⌋,
  bronze ⌊0.4n⌋; 250 ≤ n < 1000: gold at 10 + ⌊0.002n⌋, silver at 50, bronze at 100; n ≥ 1000: gold at
  10 + ⌊0.002n⌋, silver ⌊0.05n⌋, bronze ⌊0.1n⌋. The median threshold is the median of the column. A medal is
  `score <= threshold` (lower better) or `>=`; "above median" is strict.
- **Side effects of importing the grader:** `mlebench/data.py` opens a `diskcache` in a directory named `cache`
  under the **current working directory** at import; the default data directory is
  `appdirs.user_cache_dir()/mle-bench/data` (that is `~/.cache/mle-bench/data`, on `/home`) unless `--data-dir` is
  given. A verifier should set both. (source; ran: a `cache/` directory appeared where I ran it)

### The three CPU-only candidates (source: each `config.yaml`, `prepare.py`, `grade.py`, `checksums.yaml`)

| | leaf-classification | text-normalization-challenge-russian-language | mlsp-2013-birds |
| --- | --- | --- | --- |
| Answers file | `prepared/private/test.csv` | `prepared/private/answers.csv` | `prepared/private/answers.csv` |
| Its shape | `id` and 99 one-hot species columns; 99 rows (10% of 990, `train_test_split(test_size=0.1, random_state=0)`) | `id` (`<sentence>_<token>`), `after`; 1,059,191 rows (10% of the sentences, same split call on sentence ids) | `Id` (`rec_id*100 + species`), `Probability` 0/1; 64 recordings × 19 species = 1,216 rows (the script asserts 64) |
| What `prepare` does | unzips `train.csv.zip` and `images.zip`; splits the old training set; writes `public/train.csv`, `public/test.csv` (no labels), `public/sample_submission.csv` (uniform 1/99), all images to `public/images/`, labels to `private/test.csv` | unzips three files; splits `ru_train.csv` by sentence; renumbers sentence ids; writes `private/answers.csv` and `private/sample_submission.csv`; writes the new train, test and sample files to `public/` as three zip files | unzips `mlsp_contest_dataset.zip`; takes the old training fold (fold 0) only, moves a 20% sample of it (`random_state=0`) to a new test fold, renumbers the recordings; rewrites the fold, file-name and label files with the test labels as `?`; copies the wav files and four kinds of spectrogram images; filters three feature files |
| Where the sample submission is | public | **private** (`config.yaml` names `prepared/private/sample_submission.csv`); the public copy is inside `ru_sample_submission_2.csv.zip` | public |
| Metric code | `sklearn.metrics.log_loss` after checks (columns equal `id` plus the 99 classes of `classes.py`, same row count, rows sum to 1 within 1e-6, values in [0, 1]); helper `mlebench/competitions/utils.py` | `sklearn.metrics.accuracy_score` on `after` as strings, rows matched by sorted `id` (same length and ids required) | `sklearn.metrics.roc_auc_score` over all 1,216 pairs; helper `prepare_for_auroc_metric` in `competitions/utils.py` |
| Thresholds computed today from the fetched snapshot (ran) | gold 0.0, silver 0.00791, bronze 0.01526, median 0.108345; lower is better; 1,596 teams | gold 0.99012, silver 0.98232, bronze 0.97592, median 0.97591; 163 teams | gold 0.93527, silver 0.90038, bronze 0.87372, median 0.86572; 81 teams |
| Checksums the preparation verifies | zip, `private/test.csv`, three public CSVs | zip, the two private CSVs (public holds only zips, which are not checksummed) | zip, `private/answers.csv`, `public/sample_submission.csv` |

Leaf-classification's gold threshold is exactly 0.0: gold needs a log loss that rounds to 0.00000.

### The grader exercised without competition data (ran)

Script: a scratch file `grade_probe.py` (not kept in the repository),
run with `~/lh-cache/mle/venv/bin/python -I` in `~/lh-cache/mle/synth`. For each of the three it writes a small
synthetic answers file where the registry expects it (same columns and row counts as the table above, except
200 rows for the Russian one), then calls `mlebench.grade.grade_csv` on four files. Output (`out.txt` there),
shortened to the fields that differ:

| Competition | Submission | `score` | `any_medal` | `gold_medal` | `above_median` | `submission_exists` | `valid_submission` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| leaf-classification | the answers file | 0.0 | true | true | true | true | true |
| | uniform probabilities | 4.59512 (the floor `tests/constants.py` lists) | false | false | false | true | true |
| | a column missing | null | false | false | false | true | false |
| | no file | null | false | false | false | false | false |
| text-normalization-russian | the answers file | 1.0 | true | true | true | true | true |
| | one eighth wrong | 0.875 | false | false | false | true | true |
| | one row short | null | false | false | false | true | false |
| | no file | null | false | false | false | false | false |
| mlsp-2013-birds | the answers file | 1.0 | true | true | true | true | true |
| | all zero | 0.5 | false | false | false | true | true |
| | wrong column name | null | false | false | false | true | false |
| | no file | null | false | false | false | false | false |

The full report object (`CompetitionReport.to_dict()`), for the first row:

```json
{"competition_id": "leaf-classification", "score": 0.0, "gold_threshold": 0.0, "silver_threshold": 0.00791,
 "bronze_threshold": 0.01526, "median_threshold": 0.108345, "any_medal": true, "gold_medal": true,
 "silver_medal": false, "bronze_medal": false, "above_median": true, "submission_exists": true,
 "valid_submission": true, "is_lower_better": true, "created_at": "...", "submission_path": "..."}
```

- **So the oracle-style check of roadmap step 10 works as the report said:** the answers file earns gold; no
  submission scores null with no medal. It checks the grader, not that a model can be trained.
- **Percentile.** Not a field. It can be computed from the same `leaderboard.csv`: the share of the `score`
  column that the attempt's score beats or ties, by `is_lower_better`. My probe does this in six lines
  (`percentile()`): the answers file gives 100.0, the poor submissions 3.13, 4.91 and 8.64. The definition (ties,
  strictness, what a null score maps to) is the plan's to fix; the grader offers none.
- **The upstream format checker** (`environment/grading_server.py`; source) calls
  `mlebench.grade.validate_submission`, which runs the real grade function against the answers. It therefore
  needs the answers in the agent's container (upstream mounts them at `/private`). The agent instruction
  (`environment/instructions.txt`) tells the agent to use it at `http://localhost:5000/validate`, and names
  `/home/data/description.md`, `/home/data/` and `/home/submission/submission.csv`. A wrapper that keeps the
  answers out must drop or replace that paragraph and the server.
- **Upstream's own tests** (`tests/integration/test_eval.py`) download and prepare real data, so they cannot run
  without Kaggle; `tests/unit/test_data.py` was not run (pytest is not in the environment I made).

## C. What the download needs

**Answer.** `prepare` makes two Kaggle calls with the legacy username-and-key credential: a competitions listing
to test the login, then `GET /competitions/data/download-all/<id>` for one zip. The credential is
`kaggle.json`, looked for in `$KAGGLE_CONFIG_DIR`, else `~/.kaggle/` if that directory exists, else
`~/.config/kaggle/`; or the variables `KAGGLE_USERNAME` and `KAGGLE_KEY`. Without rule acceptance it does not
fail cleanly: it asks a question on standard input. The README sizes are a hand-kept table whose basis the
repository does not state, and for the two text-normalization competitions it cannot be right.

- **The calls** (source: `mlebench/data.py`, `download_dataset`; `mlebench/utils.py`, `authenticate_kaggle_api`;
  kaggle 1.6.17, `kaggle/api/kaggle_api_extended.py`, `competition_download_files`, and `kaggle/api/kaggle_api.py`):
  `KaggleApi().authenticate()`, then `api.competitions_list()` ("a cheap op that requires authentication"), then
  `api.competition_download_files(competition=<id>, path=<data dir>/<id>, quiet, force=False)`, which requests
  `/competitions/data/download-all/{id}` with HTTP basic authentication, follows the redirect and writes
  `<data dir>/<id>/<id>.zip`. The client's User-Agent is `Swagger-Codegen/1/python`; the request carries the
  Kaggle user name (basic authentication), as any Kaggle download must.
- **The credential** (source: the class body of `KaggleApi` and `authenticate`, `read_config_file`): first the
  environment (`KAGGLE_USERNAME`, `KAGGLE_KEY`); else the file `kaggle.json` in the configuration directory:
  `$KAGGLE_CONFIG_DIR` if set; else `~/.kaggle` if it exists; else, on Linux, `$XDG_CONFIG_HOME/kaggle` or
  `~/.config/kaggle`. It warns when the file is readable by group or others (`chmod 600`).
  **Importing `kaggle.api.kaggle_api_extended` creates the configuration directory when it is missing**
  (`os.makedirs(config_dir)` in the class body), so merely importing it on this machine would create
  `~/.config/kaggle`. I ran the login step once with `KAGGLE_CONFIG_DIR` pointed at an empty scratch directory:
  it raised `PermissionError: Kaggle authentication failed!` (cause: `OSError: Could not find kaggle.json`)
  before any network call, and neither `~/.kaggle` nor `~/.config/kaggle` exists afterwards. (ran)
- **The pinned client is the legacy one.** `kaggle>=1.6,<1.7` reads only a user name and key. Kaggle's newer
  access tokens (a single token string) are read by later client versions, not by this one (background
  knowledge, not verified today: no Kaggle page was read). The owner should create the legacy `kaggle.json`
  credential, or the plan should say which client is used for the download.
- **A recommended placement:** set `KAGGLE_CONFIG_DIR` to a mode-700 directory outside every repository for the
  one preparation run; nothing else needs the credential (grading does not import `kaggle`: `data.py` imports it
  inside the download functions only).
- **Rules not accepted** (source: `download_dataset`, `_need_to_accept_rules`, `_prompt_user_to_accept_rules`):
  when the API error's text contains "You must accept this competition", the code logs a warning and calls
  `input("Would you like to open the competition page in your browser now? (y/n): ")`. An answer other than `y`
  raises `RuntimeError("You must accept the competition rules before downloading the dataset.")`; `y` opens a
  browser, waits for Enter and tries again. With no terminal the `input` call raises `EOFError`. Any other API
  error is retried three times, five seconds apart, then raised. So a preparation script should run with standard
  input from `/dev/null` (or answer `n`) and treat a non-zero exit as "rules not accepted or download failed",
  reading the log line. Whether Kaggle's present error text still contains that sentence is not settled (no
  credential).
- **Preparation's footprint** (source: `download_and_prepare_dataset`, `cli.py`): under `<data dir>/<id>/`: the
  zip (kept), `raw/` (the extracted zip; **deleted at the end unless `--keep-raw`**, the default deletes it),
  `prepared/public/` and `prepared/private/`. It verifies an MD5 of the zip and of the CSV, JSON and Parquet
  files directly under `public/` and `private/` against `checksums.yaml`, and raises on a difference. The
  competition's `description.md` is copied into `prepared/public/`. Peak use is zip + raw + prepared; afterwards
  zip + prepared.
- **Are the README sizes archives or prepared data? Not settled, and the question is partly moot.** No code
  measures them: the figures are a column (`dataset_size_GB`) of `experiments/competition_categories.csv`, and the
  README table repeats it; neither says what was measured (source; ran: grep for a size computation finds none).
  Two checks against the scripts:
  - leaf-classification, 0.036 GB, and mlsp-2013-birds, 0.5851 GB, are plausible as the Kaggle archive; the
    prepared birds data is smaller than its archive, because `prepare.py` keeps only the old training fold
    (about half of the recordings). (source; sizes not measured, no download)
  - **text-normalization-challenge-russian-language is listed at 0.01 GB, and that cannot be either figure:**
    `prepare.py` states the new training file has 9,515,325 rows and the answers 1,059,191 rows; 10.5 million
    five-column rows do not fit in 10 MB in any encoding. The same holds for the English one (also 0.01). The true
    figure is probably a few hundred MB each on disk (estimate), and the preparation loads the whole file with
    pandas, which needs a few GB of memory (estimate).
  So the table is a rough guide only; the plan should measure each competition after its download.

---

## E. The older `mlebench-lite` dataset

**Answer.** It exists, but as a Terminal-Bench 1 dataset, not on Harbor's registry, and it would not save the
wrapper work: it is in the old task format, it keeps the answers and the Kaggle credential inside the agent's
image, and it scores "above median", not a medal. Two small pieces are worth copying.

- **Where** (ran: GitHub's contents API, read today): `laude-institute/terminal-bench-datasets`, directory
  `datasets/mlebench-lite`, 20 task directories (the lite split less the two competitions whose rules cannot be
  accepted), added 2025-08-14, last changed 2025-08-29 ("download kaggle data while in Dockerfile"). Its generator
  is `laude-institute/terminal-bench`, `adapters/mlebench`. Of this report's 16 candidates it holds seven:
  leaf-classification, mlsp-2013-birds, both text-normalization tasks, jigsaw-toxic, nomad2018 and spooky.
- **Not on Harbor's registry** (ran): Harbor's legacy `registry.json` (80 datasets) has no entry with "mle" in
  its name, and `harbor dataset download` answers "not found" for `mlebench-lite`, `terminal-bench/mlebench-lite`
  and `laude-institute/mlebench-lite`. Harbor's `adapters/` directory has no MLE-bench adapter (the report's
  finding, confirmed).
- **What a task looks like** (ran: read `leaf-classification/`): four files. `task.yaml` (the instruction: the
  benchmark's `instructions.txt`, an "additional notes" block with empty hour and step counts, then the
  competition's description; `parser_name: mlebench`; `max_agent_timeout_sec: 86400.0`;
  `max_test_timeout_sec: 86400.0`; `run_tests_in_same_shell: true`). `docker-compose.yaml` (one service `client`
  in the old `T_BENCH_*` variable form, with build arguments `KAGGLE_USERNAME`, `KAGGLE_KEY`, `TASK_ID`).
  `Dockerfile` (the upstream `mlebench-env` image: Ubuntu 20.04, Miniconda, the full pinned package list with
  PyTorch 2.2.0 and TensorFlow 2.17, then a build step that **downloads and prepares the competition with the
  Kaggle credential given as build arguments**). `run-tests.sh` (a ten-line grader call).
- **Where the answers live:** in the agent's own image, at `/private/data/<id>/prepared/private/`, in a directory
  with mode 700 owned by root; the public data is moved to `/home/data`. The tests run in the same container and
  shell as the agent. The Kaggle user name and key are written into the image as `ENV` values.
- **Its success rule** (`run-tests.sh`): `report["valid_submission"] and report["above_median"]`, not a medal.
- **Why it does not save the work:** the format needs conversion to Harbor's (`task.toml`, `environment/`,
  `tests/`, `solution/`); the answers and a credential inside the agent's image break the plan's D2 and D4; there
  is no oracle solution; and the image is the 25 GB kind.
- **Worth copying:** the way the instruction is assembled, and the grader call, which is the whole verifier:
  `grade_csv(Path("/home/submission/submission.csv"), registry.set_data_dir(Path("/private/data")).get_competition(<id>)).to_dict()`.

## F. GPU on this machine

**Answer.** Rootless Podman passes the GPU now. The coordinator reported (15:11 today) that the owner installed
the NVIDIA Container Toolkit 1.20.2 and that `/etc/cdi/nvidia.yaml` is a hand-corrected CDI file; I confirmed the
state and ran a CUDA check in a container and a Harbor trial with the device. The benchmark's pinned PyTorch
2.2.0 (CUDA 12.1 libraries from PyPI) suits the driver; so does any current build. No owner command is left for
the GPU, except after a driver update.

- **State found** (ran): `nvidia-container-toolkit 1.20.2-1` installed from
  `nvidia.github.io/libnvidia-container/stable/deb`; `nvidia-ctk` at `/usr/bin`; `/etc/cdi/nvidia.yaml`
  (`cdiVersion: 0.6.0`, kind `nvidia.com/gpu`, devices `0`, the GPU's UUID and `all`; written 15:11);
  `/var/run/cdi/nvidia.yaml` (the refresh service's copy, written 15:06). `nvidia-ctk cdi list` shows three
  devices. Driver 580.178.04, RTX 3090, 24,576 MiB, compute capability 8.6.
- **Why the file is hand-corrected** (coordinator's report, established by running at 15:11; not re-run by me):
  the generated file has `cdiVersion: 0.7.0` and `additionalGids` fields, which Podman 4.9.3 refuses to parse
  ("unknown field additionalGids"), making every CDI device unresolvable. The file in `/etc/cdi` is a copy with
  the three `additionalGids` blocks removed and the version set to 0.6.0. The service's copy in `/var/run/cdi`
  still fails to parse and is skipped. **After a driver update the `/etc/cdi` copy must be rebuilt the same way**
  (commands in the closing section). Before 15:11 the GPU could not be passed: there was no CDI file at all
  (ran: at about 15:00 my listing showed no `/etc/cdi` and no `nvidia-ctk`).
- **A CUDA check in a rootless container** (ran, 1.3 s, no training): `podman run --rm --device
  nvidia.com/gpu=all --security-opt=label=disable docker.io/library/debian:bookworm-slim` with a host Python
  mounted read-only, calling the driver library through `ctypes`: `cuInit` 0, one device, `cuDriverGetVersion`
  13000 (CUDA 13.0), "NVIDIA GeForce RTX 3090", 24,122 MiB, a context created, 23,374 MiB free, a 256 MiB
  allocation made and freed, every call returning 0.
- **Through Harbor 0.25.0 on Podman** (ran; D5): an extra compose file with `devices: ["nvidia.com/gpu=all"]`
  on `main` gives the agent's container the GPU (`nvidia-smi` prints the card). A task that sets `gpus` is
  refused. The verifier's container gets no GPU (extra compose files do not reach it), which is right for a
  grader.
- **Which PyTorch and CUDA build** (PyPI metadata read today; compatibility from NVIDIA's published minimum
  driver versions, which is background knowledge and was not re-read today; PyTorch itself was not run, since
  installing it is a 2.8 GB download):
  - The benchmark pins `torch==2.2.0` with torchvision 0.17.0, torchaudio 2.2.0, torchtext 0.17.0, and
    `tensorflow[and-cuda]==2.17` (`environment/Dockerfile`, `environment/requirements.txt`). The PyPI wheel of
    torch 2.2.0 for CPython 3.11 depends on the CUDA 12.1 libraries (`nvidia-cuda-runtime-cu12 12.1.105`,
    `nvidia-cudnn-cu12 8.9.2.26`, and nine more): 756 MB for torch and 2,769 MB for torch with its CUDA
    libraries, as downloads; about twice that installed (estimate).
  - CUDA 12.1 needs a driver of at least 525.60; this driver is 580.178 and reports CUDA 13.0 through the driver
    library (ran), and drivers run older CUDA runtimes. The RTX 3090's compute capability 8.6 is inside what the
    2.2.0 binaries were built for. **So the pinned PyTorch is usable as it is**; TensorFlow 2.17 with CUDA 12.3
    likewise.
  - The latest PyPI torch is 2.15.0 (needs Python 3.11 or later, CUDA 13 libraries), which this driver also
    covers. The choice between the pinned and a current build is therefore not forced by the hardware; it is a
    comparability choice (the pinned set is what published runs had) against what a 2026 model expects to find.
- **One card, one attempt** stays true: the device is passed whole; nothing limits GPU memory per container.

## G. Disk

**Answer.** Everything Podman owns (images, each attempt's writable layer, image builds) is on `/home` (61 GB
free); pulls and builds are staged in `/var/tmp` on `/` (48 GB free). Read-only competition data can sit on
either file system. The three CPU-only candidates need about 2 GB of data; one GPU candidate adds little data
but an image of 8 to 12 GB and scratch of 15 to 30 GB per attempt. Nothing large is removable in `~/lh-cache`
or in Podman's store: together they hold about 3 GB. The disk is full for other reasons.

- **Now** (ran, 15:16): `/` 457 GB, 48 GB free (90%); `/home` 1.8 TB, 61 GB free (97%). Memory 125 GB, 45 GB
  available, swap full; 32 CPUs; load average about 120 while the test suite ran.
- **Where things live** (ran: `podman info`):
  - images and every container's writable layer: `~/.local/share/containers/storage` (overlay on
    ext4, rootless). Whatever an agent writes inside its container that is not on a mount (packages it installs,
    downloaded weights, checkpoints, its working directory) lands here, on `/home`.
  - pull and build staging: `/var/tmp` on `/` (`ImageCopyTmpDir`).
  - the launcher's state and each attempt's trial directory (transcript, artifacts): `~/.local/state/lh-ladder`
    on `/home`; the kit's cache `~/lh-cache` on `/home`.
  - **No storage limit applies to a container.** Harbor's local environment never reads the task's
    `storage_mb` (ran: grep of `environments/docker/`), and the overlay on ext4 has no quota. Only the launcher's
    free-space stop (20 GB) protects the disk, and it is checked before a start, not during one.
    *Correction, 2026-11-15, after the independent review of the family plan: the last clause is
    wrong. The launcher checks the stop on every pass of its loop, about once a second, attempts in
    flight or not, on the least free space of `/`, the state root, the cache and the home directory,
    and under it stops every running attempt and the tranche (source: `ladder.py`, `Tranche.step()`,
    `host_stops()`, `free_gb()`, `disk_paths()`). The plan's M9 follows the launcher.*
- **Where the data could live.** Under `~/lh-cache/mle/data` (`/home`) or under a directory on `/`; the mount
  is a plain bind, so either works. `/` has less contention with Podman's store, as the feasibility report says.
- **Needs** (README figures where marked "table"; the rest are estimates, nothing was downloaded):

  | Item | CPU-only three | One GPU candidate |
  | --- | --- | --- |
  | Archives (kept by `prepare`) | leaf 0.04 GB and birds 0.59 GB (table); text-normalization-russian: the table's 0.01 GB is wrong, probably 0.1 to 0.5 GB | tweet-sentiment, us-patent and essay-scoring are under 0.04 GB each (table); petfinder 1.04 GB (table) |
  | Prepared data | about the archive's size or less (birds: about half) | about the archive's size |
  | Peak while preparing | archive + extracted + prepared: about 3 GB in all, one competition at a time | under 4 GB |
  | Agent image | a slim Python image with pandas, scikit-learn, LightGBM, XGBoost: 1 to 2 GB | the same plus PyTorch with CUDA libraries: 2.8 GB to download, 6 to 8 GB unpacked; with transformers and timm 8 to 12 GB. The upstream full image is about 25 GB (the report's figure) |
  | Verifier image | a slim Python image with the grader's packages and the answers: about 0.6 GB (my environment is 325 MB plus the base) | the same |
  | Pretrained weights, if placed on disk | none | 0.4 to 2 GB per model family (for example a base text encoder 0.4 to 0.7 GB, a large one 1.5 to 2 GB) |
  | Scratch per attempt (container layer) | 2 to 5 GB | 15 to 30 GB (the report's figure; checkpoints and packages the agent installs) |
  | Pull and build staging on `/` | up to the image's size | up to the image's size |

  So the CPU-only three fit easily (about 2 GB of data, 3 GB of images, 4 attempts × 5 GB). One GPU candidate
  needs roughly 12 GB of image plus up to 30 GB of scratch on `/home`, which leaves about 20 GB above nothing:
  **with 61 GB free on `/home` and a 20 GB stop, a GPU attempt beside three CPU attempts is tight**, and the
  Terminal-Bench ladder's own plan wants 23.86 GB of images there (they are not in the store today).
- **What is large and looks removable** (ran: `du`, `podman system df -v`; nothing removed):
  - `~/lh-cache`: 1.7 GB in all. `mle` 469 MB (mine), `hvenv` 328 MB, `jobs` 222 MB (175 MB is
    `second-pass-20261115`, 36 MB `first-pass-20261114`), `src` 217 MB, `tasks41` 175 MB, `recordings` 172 MB,
    `oracle` 102 MB. Nothing here is worth removing for space, and most of it is evidence the kit cites.
  - Podman's store: 1.8 GB. One 1.54 GB Terminal-Bench verifier image under three names (kept on purpose for the
    labelled variant), the egress sidecar and its base (52 MB), two dangling 52 MB images that share those
    layers, `alpine` twice (8 MB each), `ubuntu:24.04` (81 MB, pulled for the coordinator's GPU check) and
    `debian:bookworm-slim` (78 MB, mine). No containers, no volumes. Nothing worth removing.
  - Outside the question's scope but the real answer to "where did the space go": `/var/tmp` holds 319 GB on `/`,
    of which `/var/tmp/sound-analysis` is 236 GB (another project) and two `eb3-*-tmp-20261015.tar.zst` archives of
    this repository's October experiment are 3.4 and 3.5 GB. I did not look further, and none of it is mine to
    judge.

## H. Pretrained weights and the network allowlist

**Answer.** Of what an MLE agent needs, only `pip` from PyPI is on the kit's list. No model hub is. The egress
sidecar filters by host name only, so allowing a model hub also allows that hub's datasets and discussion pages;
the alternative that keeps the list unchanged is a read-only weights directory, which D5 shows Harbor can mount.

- **The kit's list** (`ladder.json`, `network.agent_phase.allowed_hosts`; source): `relay`, `pypi.org`,
  `files.pythonhosted.org`, `registry.npmjs.org`, `crates.io`, `index.crates.io`, `static.crates.io`,
  `deb.debian.org`, `security.debian.org`, `archive.ubuntu.com`, `security.ubuntu.com`,
  `mirrors.fedoraproject.org`, `dl.fedoraproject.org`. A task may add hosts by name through
  `tasks.extra_hosts` (empty today). `relay-compose.yaml` adds no host: it defines the `relay` service only.
- **How the filter works** (source: Harbor's `environments/docker/harbor-docker-egress-control-sidecar/`,
  `gost.yaml` and `bin/network-policy`): a transparent proxy that sniffs the host name of each connection and
  passes the ones on the list; DNS is allowed only to the container's configured name servers. It sees host names
  (the TLS server name), never paths. Harbor's
  validator accepts exact names and leading-wildcard names (`*.example.com`) (`models/task/config.py`,
  `_validate_allowed_host_names`); the kit's `allowlist_refusal()` forbids addresses and the host's own names,
  not wildcards.
- **Hosts by need** (background knowledge of where these clients fetch from; not probed today, because that
  would mean running the clients, and the list of content-delivery hosts changes):

  | Need | Hosts | On the kit's list? |
  | --- | --- | --- |
  | `pip install` from PyPI, including the default GPU build of PyTorch and its `nvidia-*` libraries | `pypi.org`, `files.pythonhosted.org` | **Yes** |
  | PyTorch builds for another CUDA version or CPU-only; torchvision and `torch.hub` checkpoints | `download.pytorch.org` (and the storage host it redirects to) | No |
  | Hugging Face Hub (transformers, sentence-transformers, most `timm` weights, tokenizers) | `huggingface.co`, plus its file hosts: `cdn-lfs.huggingface.co` and regional variants, and the newer `*.xethub.hf.co` storage hosts; in practice `huggingface.co`, `*.huggingface.co`, `*.hf.co` | No |
  | Older `timm`, `torch.hub` repositories, spaCy and NLTK data | `github.com`, `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `raw.githubusercontent.com`, `codeload.github.com` | No |
  | Keras and TensorFlow application weights | `storage.googleapis.com` | No |
  | TensorFlow Hub and Kaggle Models | `tfhub.dev`, `www.kaggle.com` | No, and Kaggle must stay off: it serves the competitions' solutions |
  | conda packages | `repo.anaconda.com`, `conda.anaconda.org` | No |
  | Misc. research checkpoints | `dl.fbaipublicfiles.com`, `openaipublic.blob.core.windows.net` | No |

- **What each allowance also opens.** `huggingface.co` serves datasets (including re-uploads of Kaggle
  competition data, some with labels) and model cards under the same host name; `github.com` and
  `raw.githubusercontent.com` serve public solution repositories; `storage.googleapis.com` is a general bucket
  host. A host-name filter cannot separate these from weights.
- **The alternative without any new host:** place a fixed set of weights on the host and mount it read-only
  (for the Hugging Face libraries: a populated cache directory with `HF_HOME` pointing at it and
  `HF_HUB_OFFLINE=1`; for torchvision: `TORCH_HOME`). The mount mechanism is the same `--mounts` entry as the
  data (D1, D5), so the weights need not be in the image. Which models to place is a decision the plan has to
  make per competition; the instruction must then tell the agent what is there.
- **PyTorch from PyPI works under the present list** (the default Linux wheel carries CUDA libraries from
  PyPI), so a GPU image can also let the agent install or upgrade packages itself without any new host.

## J. Where this contradicts or sharpens the feasibility report

| Report says | Found |
| --- | --- |
| §5.2, §12.3: the GPU is "not available today"; one root action is needed | No longer true: the toolkit is installed and rootless Podman passes the GPU (section F). What the report did not foresee: the generated CDI file is refused by Podman 4.9.3 and needs a hand-corrected copy, to be redone after driver updates |
| §5.2: GPUs are wired for Docker only, "so a Podman run needs an extra compose file that names the device" | Confirmed for 0.25.0 as installed, and run: `devices: ["nvidia.com/gpu=all"]` in an extra compose file works; a task-level `gpus` is refused outright (D2, D5) |
| §14.5: whether Harbor can mount a data directory | Yes, read-only, by a run-level `--mounts`; not a task field; never into a separate verifier (D1, D5) |
| §3.1, §14.3: README sizes, archive or prepared | Still unknown, and the table is wrong for the two text-normalization competitions (0.01 GB against 10.5 million rows); the 13.4 GB total is a lower bound (section C) |
| §3.2: thresholds and team counts | Confirmed for the three I computed and for all 16 team counts |
| §4: the credential is a `kaggle.json` "in the user's home directory" | More exactly `$KAGGLE_CONFIG_DIR`, `~/.kaggle` or `~/.config/kaggle`, or two environment variables; importing the client creates the directory; the pinned client is the legacy user-name-and-key one (section C) |
| §4: an unaccepted competition "fails; the code then offers to open the rules page" | It asks on standard input and can open a browser; unattended it ends in `EOFError` or `RuntimeError` (section C) |
| §5.2: "Oracle agent copies the answers file from the task's `solution/` directory" | Works (D5). For kuzushiji-recognition (rank 9) the answers file is not a valid submission: its config names a separate `gold_submission.csv`, which the oracle must use (`mlebench/competitions/kuzushiji-recognition/config.yaml`). The sample submission of the two text-normalization tasks lives in `private/` |
| §5.2: the older `mlebench-lite` dataset's state could not be established | Established: Terminal-Bench 1 format on GitHub, 20 tasks, answers and Kaggle credential in the agent image, success "above median"; not on Harbor's registry (section E) |
| §5.2: "No maintained Harbor adapter exists" | Confirmed (88 entries in `adapters/` today, none for MLE-bench) |
| §13: 2 to 3 hours to install the package and fetch the snapshots | Done here in the scratch area (`venv`, `wheels`, `lfs`), except the Kaggle preparation. One addition to the estimate: the grader's dependencies must be pinned, because today's unpinned latest versions do not install on Python 3.11 (section A) |
| §13: 6 to 10 hours more for the first GPU competition, including "GPU pass-through for Podman under Harbor" | The pass-through is shown working with a five-line compose file; the remaining GPU work is the image and the weights decision |
| §14.6: is PyTorch 2.2.0 the right pin for this driver | Usable; not forced either way (section F) |
| §9.2: `/home` 76 GB and `/` 55 GB free | Today 61 GB and 48 GB |
| §5.1: the container file's default gives 4 CPUs, 4 GB shared memory | Confirmed (`environment/config/container_configs/default.json`). Under Harbor on Podman, shared memory is set by `shm_size` in an extra compose file (run with 2 GB, D5); Podman's default is 64 MB, too small for PyTorch data loaders |
| Not in the report | Harbor needs `bash` in every image; a reward file may carry several numbers but no null; the kit's oracle summary demands a `ctrf.json` and its slot record demands a reward of exactly 0 or 1 (sections D, I) |

---

## Closing

### What is on disk, and where (all under `~/lh-cache/mle/`, 469 MB, plus one image and scratch files)

| Path | Size | What |
| --- | --- | --- |
| `src/` | 8 MB | the shallow clone at `507f92e1`, with 16 `leaderboard.csv` pointers replaced by the real files |
| `lfs/` | 1.5 MB | the 16 fetched leaderboard snapshots and `competition_categories.csv`, each matching its pointer's SHA-256 |
| `wheels/` | 95 MB | 39 wheels and one source archive (kaggle 1.6.17), SHA-256 checked against PyPI; enough to rebuild the environment, or a verifier image, offline |
| `venv/` | 325 MB | CPython 3.11.13 environment with the grader's dependencies and a `.pth` file pointing at `src/`. Its interpreter is a link to a Python under `/var/tmp/sound-analysis/…` (the machine's `~/.local/bin/python3.11`), so it breaks if that directory is removed |
| `.uvcache/` | 10 MB | the installer's cache; safe to delete |
| `synth/` | under 1 MB | the grader probe's synthetic answers, its output (`out.txt`, `err.txt`), the grader's `cache/` directory and an empty `kagglecfg/` |
| `probe/` | under 1 MB | the scratch Harbor tasks (`task`, `task-gpu`, `task-cdi`), `gpu-compose.yaml`, a two-line data directory and the four trial directories under `jobs/` (`oracle`, `nop`, `gpu`, `cdi`) |
| Podman's store | 78 MB | `docker.io/library/debian:bookworm-slim`, pulled for the probe (remove with `podman rmi docker.io/library/debian:bookworm-slim`) |
| The session scratchpad | small | `fetch_wheels.py`, `grade_probe.py`, `harbor-registry.json`, this report |

Nothing was written to the repository, to `~/lh-cache/hvenv`, `tasks40`, `tasks41`, `oracle*`, `recordings` or
`jobs`; no `~/.kaggle` or `~/.config/kaggle` exists; no container, network or built image is left. The total is
well under the 8 GB allowance.

### Commands the owner would have to run as root

None is needed now. One becomes needed after every NVIDIA driver update (the coordinator's procedure, not re-run
by me): regenerate the CDI file as a normal user, strip what Podman 4.9.3 cannot parse, install it.

```
nvidia-ctk cdi generate --output=/tmp/nvidia-cdi.yaml        # as the normal user
# remove every `additionalGids:` block and set `cdiVersion: 0.6.0` in /tmp/nvidia-cdi.yaml
sudo install -m 644 /tmp/nvidia-cdi.yaml /etc/cdi/nvidia.yaml
podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable docker.io/library/ubuntu:24.04 nvidia-smi   # the check, no root
```

Not root, but the owner's alone: a Kaggle account with a legacy API credential (`kaggle.json`: user name and
key), placed in a mode-700 directory named by `KAGGLE_CONFIG_DIR` (or `~/.kaggle`), and the acceptance of each
chosen competition's rules in a browser.

### What remains unsettled

1. Whether Kaggle still lets a new account accept the rules of each candidate, and what its error text is when
   they are not accepted (no credential; no Kaggle page read).
2. Whether the legacy user-name-and-key credential can still be created on Kaggle's site, which the pinned client
   needs (background knowledge only).
3. The real archive and prepared sizes of every candidate, and the memory the text-normalization preparation
   needs (no download).
4. That the preparation's checksums match with the pinned package set I installed (it can only be shown by
   preparing one competition).
5. The real grader running inside a verifier container, and an agent phase under the allowlist together with the
   data mount and the GPU device (each part was run; the combination and the in-container grader were not).
6. PyTorch itself on this GPU in a container (the driver library was exercised; PyTorch was not installed).
7. How the Claude Code CLI behaves around training commands that run for hours (its per-command time limit), and
   how long a session works before it stops: the CLI was not run.
8. The exact content-delivery host names a model hub uses today (section H lists them from background knowledge).
9. Each competition's rules on research use, and the fairness of the thresholds on the rebuilt test sets (the
   report's open questions 1 and 9; nothing here bears on them).
