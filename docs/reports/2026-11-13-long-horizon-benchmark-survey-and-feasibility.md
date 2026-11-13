# Long-Horizon Benchmark Survey And Machine Feasibility, 2026-11-13

**Status: Captured evidence, not a contract.** This page records two zero-spend pieces of work
done for [roadmap Phase 5b](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed):
a survey of public benchmarks for long tasks, and a check that candidate tasks build, run and
grade on this machine without Docker. It selects no work; the
[Phase 5b plan](../plans/2026-11-13-long-horizon-task-family-and-seed-plan.md) does. No model or
provider call was made. Every public figure is labelled "reported by"; figures marked "computed"
are arithmetic on public rows; figures marked "measured" were observed on this machine. The
working notes, downloaded rows and job directories were session scratch and are not kept in the
repository.

## 1. Survey: what was found

- **A per-task, repeated measurement of the bound model exists.** The Terminal-Bench 4.0
  leaderboard holds a row for Claude Code 2.1.311 with `claude-haiku-5-5` at effort `max`: 132 of
  330 trials passed (40.0%), five trials on each of 66 tasks, mean USD 2.89 and 68 minutes per
  trial, about 37 million tokens per trial, almost all cached input (reported by the submission
  file `2026-11-06-haiku-5-5-max-claude-code` in the `harbor-framework/terminal-bench` repository
  and by the public trial rows of the benchmark's hub).
- **Per task, that row splits** (computed, 4.1.0 regrade): 0 of 5 on 26 tasks, 1 on 5, 2 on 8,
  3 on 8, 4 on 8, 5 on 11. All five trials of one task ended in a safety refusal, not a failed
  attempt; they were the only errored trials.
- **The aggregate depends strongly on effort.** The vendor's launch chart gives Haiku 5.5 on
  Terminal-Bench 4.0 as 12.7% (`low`), 20.3% (`medium`), 24.8% (`high`), 31.5% (`xhigh`), 39.2%
  (`max`), with Claude Code `--bare`, 66 tasks, ten trials each, and USD 0.68 per attempt at
  `medium` (reported by a secondary write-up quoting the launch post and system card; only the
  39.2% headline was confirmed on the vendor's page).
- **Per-effort cost is public at two points only:** USD 0.68 at `medium` and USD 2.89 at `max`,
  from two different harness settings. No per-task figure exists below `max`.

## 2. Benchmarks compared

| Benchmark | Task and grading | Runs here? | Licence | Evidence for a small model | Fit to staged work |
| --- | --- | --- | --- | --- | --- |
| Terminal-Bench 4.0 / 4.1 | 66 terminal tasks with a deliverable (software 18, science 14, ML 11, operations 9, hardware 5, security 5, media 4); expert time median about 4 h; agent limit 8 h; a separate verifier container, all tests must pass | 52 of 66 are one image without a GPU; 11 use compose; 3 ask for a GPU | Apache-2.0; canary string asking that the data stay out of training corpora | Haiku 5.5 with Claude Code `max`: 40.0%, per trial and per task; with mini-swe-agent 36.4% (reported by Vals) | Good: multi-hour build, port and repair tasks; some are single-insight debugging |
| Terminal-Bench-Science 0.1 | 70 research-workflow tasks; expert time 1.6 to 600 h; author-written verifier | Same format; no GPU task; at most 4 CPUs and 16 GB | Apache-2.0; same canary | Haiku 5.5 with mini-swe-agent: 10.0%, USD 4.52, 94 min, one attempt (reported by Vals); no per-task Haiku rows | Good; scientific toolchains are the hardest images |
| NL2Repo-Bench | Build an installable Python library from one requirements document; 104 tasks; upstream test suite | Needs Docker images of another agent framework; a virtual-environment replacement is unverified | Not stated | Sonnet 4.5 with Claude Code: 3 of 104 fully passed (reported by the paper); no Haiku 5.5 figure, no per-task results | Best fit; every target is a published package, so leakage is high |
| ReplicationBench | Reproduce one numeric result of an astrophysics paper; about 100 tasks | Docker base image; datasets up to 10 GB | Not stated | Haiku 4.5 with Claude Code: 14.4% on 90 tasks, one run (reported by the harness adapter) | Fair: one number per task |
| FeatureBench | Implement a feature in a real repository; 200 tasks (lite 30) | Images of 2 to 8 GB each; 44 tasks need a GPU | Not stated | Best 2025 agents 11 to 12.5%; no Haiku 5.5 figure | Good for its from-scratch level; disk rules it out here |
| ProgramBench | Rebuild a program from its binary and documentation; 200 tasks; hidden behavioural tests | Docker images per task | MIT | Haiku 5.5: 2.5% resolved, USD 6.83, 73 min (reported by Vals) | Excellent fit; below the band on the binary measure |

Excluded, one line each: SWE-bench Verified, Pro, V2 and Multilingual (saturated or far above
the band; localized patches); SWE-bench Multimodal (in band in aggregate, but visual front-end
patches); SWE-Marathon and its extension (far above a Haiku budget; half of the extension is
model-judged); MLE-bench (158 GB minimum data, 24 h runs); PaperBench and ScienceAgentBench
(graded wholly or mostly by a model); RExBench (10 of 12 tasks withheld); SciCode and
ResearchCodeBench (function-level); AlgoTune (hardware-sensitive timing); Commit0 (stale and
contaminated); Vibe Code Bench and FrontierCode (tasks private). LHTB (46 tasks, continuous
reward) was not examined: its licence and task content were not established.

## 3. The 16 named tasks

Public evidence is the Haiku 5.5 `max` row: k of 5 trials (4.1.0 regrade) and mean USD and
minutes per trial from the original run; the last public column is the largest single-trial cost
of the five (computed). The oracle columns are measured on this machine (section 5).

| Task | Area | Public k/5 at `max` | USD / min per trial | Largest trial USD | Base image | Oracle state here |
| --- | --- | --- | --- | --- | --- | --- |
| vba-userform-port | Software | 1 | 4.73 / 50 | 5.04 | python:3.12-slim | Fails unchanged; passes both halves with a wider user-id range or a one-line verifier change |
| vf2-speedup-networkx | Software | 0 (1 before the regrade) | 5.79 / 70 | 8.34 | ubuntu:24.04 | Not tried |
| wal-recovery-ordering | Software | 0 | 0.90 / 20 | 1.04 | python:3.13-slim | Reference passed 1 of 2 under load; untouched fails |
| session-window-debug | Software | 0 | 0.71 / 25 | 1.24 | python:3.12-slim | Pass, both halves, once |
| production-planning | Operations | 2 | 1.31 / 32 | 1.56 | python:3.13-slim | Pass, once |
| vpp-loss-divergence | ML | 1 | 3.26 / 44 | 4.22 | python:3.11-slim | Not tried |
| batched-eval-parity | ML | 2 | 2.03 / 30 | 2.20 | python:3.11-slim | Not tried |
| pretrain-shard-corruption | ML | 0 | 0.69 / 26 | 1.15 | python:3.11-slim | Not tried |
| gsea-proteomics | Science | 1 | 0.75 / 23 | 1.02 | ubuntu:22.04 | Pass, once; the reference solution installs packages during the agent phase |
| lake-temp-glm | Science | 1 | 1.74 / 81 | 2.86 | ubuntu:24.04 | Pass, once, after a base image was pulled by full name |
| sound-change-cascade | Science | 2 | 2.87 / 82 | 3.36 | python:3.12-slim | Pass, once |
| hof-topology-interpenetration | Science | 0 | 2.38 / 56 | 2.60 | ubuntu:24.04 | Not tried |
| shadow-relay | Security | 2 | 2.85 / 47 | 4.18 | python:3.13-slim | Pass, once |
| rs-archive-clone | Software | 3 | 7.64 / 81 | 9.83 | ubuntu:24.04 | Pass, once; the agent user can neither read nor re-mode the binary |
| retro-console-soc | Hardware | 3 | 5.90 / 81 | 9.34 | fedora:42 | Pass, once, after a base image was pulled by full name |
| roy-polymorph-cn | Science | 3 | 1.86 / 111 | 4.57 | ubuntu:22.04 | Pass, once |

The 16 means sum to USD 45.42 per set of one trial each (computed), a mean of USD 2.84, close to
the benchmark's USD 2.89. Within a task the largest trial cost at most 2.45 times the task's mean.
Every one of the 16 declares an 8-hour agent limit (28,800 s), 2 to 8 CPUs and 4 to 8 GB, and no
agent network setting, which means open internet. Two verifiers (batched-eval-parity,
lake-temp-glm) declare no internet. Verifier limits run from 120 s to 1,800 s.

## 4. Sandboxing on this machine

**Without containers** (tried first). `bwrap` works through its AppArmor profile but maps one
user id and grants no capabilities; `unshare -Ur` is refused. A daemon-free image export plus
`bwrap` runs simple images (`apt` needs its sandbox user set to root). It cannot reproduce a task
that separates users, and it means re-implementing the harness's build and verifier flow. It was
set aside when Podman became available.

**Rootless Podman** (installed by the owner during the work): Podman 4.9.3, crun, overlay store
under the user's home, cgroup v2 with `cpu`, `memory` and `pids` delegated, a sub-id range of
65,536. Inside a container user 0 maps to the host user and users 1 to 65,536 to the sub-id
range, so task users are distinct real ids.

The published Harbor harness (0.25.0 from the package index) runs unchanged with its Podman
backend, given:

1. `podman-compose` 1.6.0 installed in a user environment (the harness refuses to start without
   a compose frontend). No Docker socket and no Podman socket are needed.
2. Its fixed 10-second probes lengthened. Under load `podman info` took 9.6 to 14.7 s, the run
   aborted, and the rootless probe silently answered "not rootless" on timeout. A 40-line wrapper
   (`experiments/long_horizon_tasks/harbor_patient.py` on branch `spike/long-horizon-tasks`)
   raises exactly those timeouts to 180 s.
3. Two images pulled by their full registry name beforehand, because Podman resolves short names
   differently from Docker: `fedora` (resolved to another registry) and the harness's own egress
   sidecar image (no search registry defined). A registries configuration with the Docker Hub
   alias does the same.

Observed on the containers (measured): CPU and memory limits come from the task file; **no bind
mounts** in the agent or the verifier container (files move by tar stream); the task's `tests/`
and `solution/` directories are absent from the agent container under the do-nothing agent; the
verifier runs in a separate image that bakes the tests in and receives only the declared
artifacts; built task images are deleted after each trial. The harness's extra-compose option
(used for a process limit of 4,096) reaches only the agent container; the verifier keeps
Podman's default of 2,048.

## 5. Oracle check

Each cell is one harness trial on rootless Podman: the harness's `oracle` agent (runs the
reference solution) and its `nop` agent (does nothing), each graded by the task's own verifier.
Pass means reward 1 for the reference and reward 0 untouched. Host load average was 100 to 165
on 32 cores throughout. Task sources: `harbor-framework/terminal-bench` at commit `adf10d2b` and
`harbor-framework/terminal-bench-science` at `77039bac`.

| Task | Build s (oracle / nop) | Solve s | Verify s (oracle / nop) | Reference passes | Untouched fails |
| --- | --- | --- | --- | --- | --- |
| wal-recovery-ordering | 65 and 38 / 19 | 17 and 20 | 924 and 1106 / 192 | 1 of 2 runs (the first failed) | yes |
| production-planning | 96 / 228 | 38 | 321 / 133 | yes | yes |
| sound-change-cascade | 57 / 64 | 13 | 119 / 181 | yes | yes |
| session-window-debug | 136 / 46 | 15 | 245 / 185 | yes | yes |
| shadow-relay | 71 / 74 | 5 | 125 / 139 | yes | yes |
| gsea-proteomics | 225 / 101 | 90 | 125 / 202 | yes | yes |
| roy-polymorph-cn | 205 / 193 | 16 | 218 / 105 | yes | yes |
| retro-console-soc | 156 / 161 | 9 | 591 / 181 | yes | yes |
| rs-archive-clone | 38 / 53 | 30 | 198 / 181 | yes | yes |
| lake-temp-glm | 120 / 141 | 307 | 332 / 234 | yes (second run) | yes |
| vba-userform-port, unchanged | 123 / 206 | 4 | 401 / 439 | no reward file | no reward file |
| vba-userform-port, one-line verifier change | 244 / 182 | 15 | 540 / 193 | yes | yes |
| rdkit-ic-constraints (Science suite) | 104 / 90 | 30 | 945 / 241 | yes | yes |

Summary: 11 of the 16 named tasks were tried. Ten pass both halves with the task files
unchanged, wal-recovery-ordering in one of two reference runs. Five were not tried
(vf2-speedup-networkx, vpp-loss-divergence, batched-eval-parity, pretrain-shard-corruption,
hof-topology-interpenetration); a read of their image and verifier files found none of the
hazards met so far. Of two Science-suite tasks, one passes after an upstream defect is fixed and
the other (spin-glass-groundstate) had not finished when this was written. No task was run five
times, which is what the harness's own guidance asks for.

**What needed fixing, and where the fix lives.**

| Problem | Evidence | Fix | Touches task files? |
| --- | --- | --- | --- |
| 10-second harness probes time out under load | "Podman is not responding" | The wrapper above | No |
| Short image names resolve differently | `manifest unknown` for `fedora`; the sidecar image "did not resolve to an alias" | Pull by full name, or a registries alias | No |
| vba-userform-port verifier changes ownership to a random user id up to about 10^9 | `OSError: [Errno 22] Invalid argument` | A wider sub-id range (one root command, then `podman system migrate`), or the verifier's upper bound lowered to 55,000 in a local copy | Only the second |
| wal-recovery-ordering reference failed 1 of 70 test executions once | A thread-timing test with a 0.2 ms delay; the verifier used 1,106 s of its 1,800 s | None; a quiet host | No |
| An upstream Science task file is invalid TOML (a key twice) | The harness reports only "Either datasets or tasks must be provided" | Remove the duplicate line | Yes (not one of the 16) |

## 6. Timing and cost under load

Measured at load 100 to 165; an idle host should roughly halve them.

- Per attempt, because built images are deleted after each trial: agent environment 38 to 244 s
  (median about 105 s) with a warm layer cache; verifier 105 to 1,106 s (median about 200 s)
  including its own image build; transient images 0.4 to 3.3 GB per trial. Peak image store
  during four concurrent trials: 5.7 GB.
- An oracle check of one task (both halves): 4 to 20 minutes, median about 9.
- Not measured: the Claude Code install inside a container, and any agent run.

Load changes grading, not only speed: one reference solution failed a timing test under load,
and a Science-suite task grades against a CPU-time budget.

## 7. Network observations

- All image builds need the network (base images, system packages, language package indexes).
- Of the tasks tried, one reference solution needs a package index during the agent phase
  (gsea-proteomics) and one verifier needs package indexes (vba-userform-port).
- No-network verifier phases are enforced under rootless Podman by the harness's egress sidecar:
  from inside one such verifier, requests to a code host, a package index and a plain web site
  all failed, and the sidecar logged each as denied. A bare TCP connect succeeds, because the
  proxy accepts and then drops it, so connect-only probes mislead.
- The harness also supports an allowlist mode with named hosts, by the same sidecar. **It was
  not tried.**
- The reference solutions are public in the benchmark's repository, the tasks allow internet,
  and the instructions only ask the agent not to cheat.

## 8. How the published harness runs its Claude Code agent

Read from the harness source at commit `b06002e0`; not run.

- It installs Claude Code **inside the task container** during agent setup: missing system
  packages (`curl`, `bash`, `nodejs`, `npm`, `procps`), then the vendor's bootstrap script with
  an optional version argument (the package manager route on Alpine images). An image that
  already holds the requested version is not reinstalled.
- It runs `claude --verbose --output-format=stream-json … --print` in the container as the
  task's agent user, with the permission mode `bypassPermissions`, the model in
  `ANTHROPIC_MODEL`, the effort as `--effort`, the session directory under the container's log
  directory, and the API key in the container's environment. Options exist for `--max-budget-usd`,
  disallowed tools and a version pin.
- Setup runs before the agent-phase network policy is applied; when the policy is not open, the
  harness disables the CLI's web tools.
- Host settings, memory and skills are uploaded only when the matching option is given.
- Results: per-trial `result.json` with phase timings, the verifier reward, an exception type
  and token and cost fields (empty for the oracle and do-nothing agents); the session files are
  copied out of the container.
- The harness's retry count defaults to zero.

## 9. Arithmetic used by the plan

Exact binomial 95% intervals (Clopper–Pearson; computed):

| n | k = 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | 0–70.8% | 0.8–90.6% | 9.4–99.2% | 29.2–100% | | |
| 5 | 0–52.2% | 0.5–71.6% | 5.3–85.3% | 14.7–94.7% | 28.4–99.5% | 47.8–100% |
| 15 | 0–21.8% | 0.2–31.9% | 1.7–40.5% | 4.3–48.1% | 7.8–55.1% | 11.8–61.6% |

An interval wholly inside 10 to 30 percent needs about 90 attempts for one task at one setting.
A task with a true rate of 20 percent shows 0 of 5 about a third of the time.

Cost by effort (computed from the two public points, by assuming equal ratios between adjacent
levels from `medium` to `max`): about USD 0.42 at `low`, 0.68 at `medium` (reported) and 1.10 at
`high` per attempt on the benchmark's average task. Scaled to the 16 tasks: about USD 35 for one
attempt of each task at each of the three levels, about USD 173 for five. The `low` and `high`
figures are an interpolation, not a report.

## 10. Not established

- Any behaviour of the model on these tasks in this setting: nothing was run with an agent.
- Whether the allowlist mode works under rootless Podman, and which hosts each task needs.
- Whether the task content at the checked commit equals the published 4.1.0 digests.
- Oracle results for five named tasks, and repeat stability for all 16.
- The Claude Code install inside these images (time, hosts contacted, whether an old version is
  still served), and whether each effort level is accepted for this model.
- Compose tasks and GPU tasks were not tried.
- Licences of the benchmarks marked "not stated".
- Whether the model's training data includes these tasks. They were published in August 2026
  with a canary string; the reference solutions are public.

## 11. Sources (public names; read 2026-11-13)

- Repositories: `harbor-framework/terminal-bench` (tasks, leaderboard submissions, dataset
  digests, licence), `harbor-framework/terminal-bench-science`, `harbor-framework/harbor` (the
  harness, its Podman backend, its Claude Code agent, the benchmark adapters).
- The benchmark hub's public leaderboards "Terminal-Bench 4.0", "Terminal-Bench 4.1" and
  "Terminal-Bench-Science 0.1 Evaluation Results", and their public trial rows.
- The vendor's Haiku 5.5 launch post; a secondary write-up of its benchmarks (effort sweep and
  per-attempt cost); the Vals benchmark pages for Terminal-Bench 4, Terminal-Bench-Science and
  ProgramBench.
- Papers and repositories of NL2Repo-Bench, FeatureBench, ProgramBench, ReplicationBench,
  SWE-Marathon, SWE-EVO, Commit0, MLE-bench, PaperBench and RE-Bench.
- Local tools: Podman 4.9.3, podman-compose 1.6.0, Harbor 0.25.0, crane 0.22.1, bwrap 0.9.0.
