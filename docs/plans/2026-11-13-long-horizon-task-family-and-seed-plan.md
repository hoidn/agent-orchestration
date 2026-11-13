# Long-Horizon Task Family And Staged Seed Plan (Roadmap Phase 5b)

**Status: Plan; not reviewed; no spend.** This page turns the staging of
[roadmap Phase 5b](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed)
into a plan: the effort ladder that owner decision 16 approved (steps 4 to 6), and steps 7 to 9
in outline. The roadmap owns the direction. `AGENTS.md` ("Experiment rules") owns the approval
and its limits. The [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
owns the qualification, dominance and cost rules. The
[survey and feasibility report](../reports/2026-11-13-long-horizon-benchmark-survey-and-feasibility.md)
holds the evidence cited here as "report §n". This plan owns its task list, limits, thresholds
and readout. Its commands are for this machine and are not copyable examples. Spend is
authorized only as the [ledger](#ledger) records.

**Headline exit test (fails today):** `experiments/long_horizon_tasks/results/family.json`
exists, names its criterion and task digests, and lists either the screened-in tasks with their
counts by effort and the effort verdict, or the stop that prevented it.

## Scope and approval

- **Approved (decision 16):** one calibration tranche: the 16 named Terminal-Bench 4 tasks, a
  direct `claude-haiku-5-5` Claude Code session at effort `low`, `medium` and `high`, five
  attempts each; at most 240 attempts, ceiling USD 200; no other model, no top-up after a null.
  First: the oracle check passes here, the network policy is fixed, the launcher has passed an
  independent review, and this plan and its ledger exist.
- **Kind of experiment.** The family is oracle-scored: its qualification is the oracle check,
  with no judge. The ladder is the difficulty calibration with effort as the varied quantity,
  under the same task, tools and limits at every level.
- **Not approved:** the seed comparison (step 9), any task outside the 16, any other model. No
  claim about any workflow comes from this tranche. "Better" below always means Pareto
  dominance over quality and priced-token cost.

## What this size can and cannot support

- **Can show:** which tasks are at the floor or clearly above the band for a direct session;
  a pooled change of success with effort of about 17 points or more; cost and time per attempt
  by effort; whether containers, network policy and metering hold over 240 runs.
- **Cannot show:** that any task's true rate lies in 10 to 30 percent (that needs about 90
  attempts per task and setting; report §9); an ordering of tasks; an effort effect for a single
  task; a pooled change under about 12 points (detected half the time); anything about `xhigh`
  or `max`, another model, or a workflow.

## Decisions frozen before spend

### D1. Task list and task identity

A task is **the same task** when every file of its directory equals the benchmark's published
4.1.0 digest. Host-side steps (an image pulled by full name, a registry alias, a wider sub-id
range, longer harness probes) change no task file. The network overlay of D3 changes the
execution condition, not the task, and is recorded. Any other edit makes a **modified task**,
admitted only as the vba row says. Task files, reference solutions and verifier tests stay
outside this repository; the kit holds names and digests.

| Task | Oracle state (report §5) | To do before spend | Per-attempt cap, USD |
| --- | --- | --- | --- |
| vba-userform-port | Fails unchanged | Widen the sub-id range (owner question 2); else the one-line verifier change, labelled "modified verifier" | 14.19 |
| vf2-speedup-networkx | Not tried | Oracle check | 17.37 |
| wal-recovery-ordering | Reference 1 of 2 under load | Five of five on a quiet host; on the load-sensitive list (D5) | 3.00 |
| session-window-debug | Pass, once | Repeat | 3.00 |
| production-planning | Pass, once | Repeat | 3.93 |
| vpp-loss-divergence | Not tried | Oracle check | 9.78 |
| batched-eval-parity | Not tried | Oracle check | 6.09 |
| pretrain-shard-corruption | Not tried | Oracle check | 3.00 |
| gsea-proteomics | Pass, once | Repeat; needs a package index in the agent phase | 3.00 |
| lake-temp-glm | Pass, once | Repeat | 5.22 |
| sound-change-cascade | Pass, once | Repeat | 8.61 |
| hof-topology-interpenetration | Not tried | Oracle check | 7.14 |
| shadow-relay | Pass, once | Repeat | 8.55 |
| rs-archive-clone | Pass, once | Repeat | 22.92 |
| retro-console-soc | Pass, once | Repeat | 17.70 |
| roy-polymorph-cn | Pass, once | Repeat | 5.58 |

- **Qualification rule.** A task runs in the ladder only if, on the pinned 4.1.0 content, under
  the final network policy, with the host load below the gate of D2, the reference solution
  earns reward 1 five times of five and the untouched environment reward 0 five times of five.
  Reason: the harness's guidance asks for five, and single runs hid one unstable verifier.
- **A task that fails the rule and has no host-side fix is dropped.** It is not replaced, and
  its 15 slots are not given to other tasks: the approval names 16 tasks and five attempts per
  cell. The tranche shrinks. Replacement by a task outside the 16 is owner question 3.
- **A task whose reference passes five of five quiet but failed under load** stays, on the
  load-sensitive list, which is frozen from the oracle evidence before spend.

### D2. What an attempt is

- **The agent runs inside the task's agent container,** as the published harness runs its
  Claude Code agent (report §8): one non-interactive session with the task's instruction.
  Reason: this is what the public per-task figures measured, and the instructions assume an
  agent with root, a package manager and background processes there. A host-side session
  driving the container would change the tool surface.
- **How the binary and the credential get in.** The harness downloads the CLI inside the
  container with the vendor's bootstrap script, pinned by version; nothing is mounted (report
  §4), and the host's own CLI, which updates itself, is never used. The credential is one
  dedicated API key, read from a file of mode 600 outside the checkout into the harness
  process's environment, which the harness passes to the container. The host home, its Claude
  configuration and its login never enter a container. The agent can see the key: the upstream
  design, and a stated residual risk (D3).
- **Binding.** Model `claude-haiku-5-5` by exact id; effort one of `low`, `medium`, `high`,
  passed as the CLI's `--effort`; every model variable of the CLI (default, small-fast, the four
  tier defaults, subagent model) pinned to the same id; no fallback model; auto-update, the
  advisor tool and the refusal fallback off. A fresh container has no user settings, plugins,
  hooks or memory.
- **CLI version:** 2.1.311, the version of the public row, installed by pin in every container.
  If the release host no longer serves it or it rejects an effort level for this model (both
  probed without spend or in the smoke), the pin becomes the newest version that passes, and the
  ledger records it. The version each session reports is checked; another version is a stop.
- **Harness and limits:** Harbor 0.25.0 and podman-compose 1.6.0 from a pinned environment,
  one harness run per attempt, its retry count at zero. Equal at every effort level: the task's
  own agent limit (28,800 s for all 16) and verifier limit, multiplier 1; its CPUs and memory;
  a process limit of 4,096; the dollar cap of D4.
- **Load.** Load slows the agent's commands, not the model, so the same wall limit buys less
  computing here than in the public row, and one verifier is timing-sensitive. An attempt is
  launched only when the 1-minute and 5-minute load averages are at or below 24 (of 32 cores).
  Load is recorded at launch, at the end of the session and around the verifier; during a
  session it is recorded, not enforced.
- **Concurrency:** four attempts, two until every effort level has one clean observation.
- **Withheld:** `tests/` and `solution/` never enter the agent's container, and the verifier
  image receives only the declared artifacts: the harness's construction, checked in rehearsal.

### D3. Network policy

- **Declared:** no agent network mode on any of the 16 (open internet); no internet for two
  verifiers. **Enforced under rootless Podman:** no-network verifier phases, by the harness's
  egress sidecar (report §7). Its allowlist mode was not tried.
- **Policy for the ladder: agent phase on an allowlist.** One list for every task and effort:
  the model API host; the Python, Node and Rust package indexes; the system package mirrors of
  the three base distributions. A task whose instruction or reference solution needs another
  host gets that host added by name in `tasks.json`. Code hosts, search engines, the benchmark's
  hub and the open web are not on it. Image build and agent setup keep the open network (the
  agent is not running then). Verifiers keep what they declare. The CLI's web search and fetch
  tools are off: the search tool runs at the provider and would bypass the container's egress.
- **Reason and consequence.** The reference solutions are public in the benchmark's repository;
  with open internet a pass may mean the agent found the answer. The rates are then not
  comparable with the public row, and the later comparison must use the same policy.
- **Cannot be enforced:** what the model remembers of the benchmark (published August 2026 with
  a canary string); content reachable through an allowed host; a direct request to the model API
  with the key, for any model the key allows, outside the session records. The last is limited
  by owner question 1 (a workspace spend limit, restricted to this model if the console allows)
  and detected afterwards: transcripts are scanned for the API host and the key's variable
  name, and the console's usage by model is compared with the metered total.
- **If the allowlist cannot be enforced here,** the plan stops before spend. The ladder does
  not run on an open network on this plan's authority.

### D4. Metering, price and the ceiling

- **Tokens** come from the session's own usage records: the session files the harness copies
  out of the container, one row per assistant message, deduplicated by message id, read by
  `orchestrator/providers/usage.py`. A session that ends by itself also reports its own cost.
- **Price table:** `orchestrator/providers/price_table.json` at the frozen commit, by SHA-256
  (dated 2026-11-11; this model: input 0.10, output 0.50, cache read 0.01, cache write 0.20 USD
  per million tokens, five times that above 100,000 prompt tokens in a request). Cost is the
  list-price equivalent from this table, not billed spend.
- **Per-attempt cap,** passed to the CLI as its own budget limit:
  `max(3.00, 3 × the task's public mean cost per trial at effort max)` (the table in D1). The
  largest public trial of any of the 16 cost 2.45 times its task's mean at `max`, and the three
  levels run here should cost less. **The cap depends on the task, never on the effort.**
  Reason: the calibration rule requires the same limits at every level, and a cap that tightened
  with lower effort, or bound more often at higher effort, would manufacture an effort effect.
- **Reservation before every attempt:** the cap plus USD 1.00 (the CLI may pass its budget by
  the requests in flight; USD 1.00 covers several at the long-context rate). Under one lock,
  the launcher computes *committed* = settled cost of every start + every open reservation, and
  launches only if *committed* + reservation ≤ 200.00 and starts < 240.
- **Settlement** replaces a reservation with the larger of the table price and the CLI's figure.
  Unreadable or missing usage settles at the full reservation, never at zero.
- **What ends the tranche:** nothing in flight and the next slot's reservation does not fit; 240
  starts; a stop rule of D7. The launcher never skips ahead to a cheaper slot.
- **Expected spend (planner's estimate):** about USD 173 for all 240 (low 33, medium 53, high
  87), from the two public cost points (report §9). Plausible range 145 to 255. Above 200 the
  ceiling ends the tranche inside round 4 or 5, which D7's order makes harmless.

### D5. Infrastructure failure against model failure

Classified by a table frozen in the criterion, from the harness's result and the stream's last
event, without reading the reward.

| Outcome | Counts against 240 | Cost against 200 | In k and n | Run again |
| --- | --- | --- | --- | --- |
| **Observation:** the session started and ended by itself, at the task's time limit, at the dollar cap or in a refusal, and the verifier returned a reward | Yes | Yes | Yes, with its reward (limit, cap and refusal are flagged) | Never |
| **Infrastructure failure:** the session started and ended in a provider error, or the host, Podman or the launcher died | Yes | Yes | No; listed, never scored zero | Never |
| **Pre-session failure:** image build, pull, agent setup or version check failed; no session began and no usage exists | No | Nothing was spent | No | At most twice per slot |
| **Verifier gave no reward** after a finished session | (already counted) | (already counted) | See below | Verifier only |

- **The agent is never run twice for one slot.** A retry therefore cannot turn a model failure
  into a pass. With 240 slots and a cap of 240 a replacement would only take a slot elsewhere.
- **Verifier-only regrade** (no model call, the saved artifacts unchanged), in two cases. (1)
  No reward was produced: up to two regrades below the load gate; a reward then stands; a
  verifier timeout twice is reward 0 (the limit is part of the task); still no reward file is an
  infrastructure failure. (2) A task on the load-sensitive list returned reward 0 while the load
  was above the gate during verification: one regrade below the gate, and its reward stands
  either way. If the harness cannot regrade on Podman (unverified), case 1 becomes an
  infrastructure failure and case 2 is excluded as "indeterminate".
- A session that ended in a provider error is excluded whatever its reward: counting it would
  lower the rates of the longer sessions, which are the higher effort levels. An outcome the
  table does not name pauses the launcher for a recorded ruling.

### D6. The readout

- **Per task and effort:** k of n with the exact (Clopper–Pearson) 95% interval; flags;
  exclusions listed. Complete cells have n = 5; a cell with n under 5 is labelled incomplete.
- **Placement, pooled over a task's 15 attempts** (K of n): K = 0 is "floor" (upper bound 21.8%
  at 15); 1/15 ≤ K/n ≤ 1/3 is "screened in"; above is "above the band". A screened-in task
  records its band effort: the level whose cell has k = 1, else k = 2, ties to the lower
  level. The rule accepts a task of constant true rate 2%, 5%, 10%, 20%, 30%, 50% with
  probability 0.26, 0.54, 0.79, 0.90, 0.72, 0.15. The label is "screened at 15 attempts",
  never "in the 10 to 30 percent band".
- **Effort test, fixed before the data.** A (task, round) triple is complete when its three
  slots are all observations. Over complete triples, `s_i(e)` is task i's successes at effort e
  and `d_i` a difference between two levels. The test is the exact sign-flip permutation test
  over tasks on the sum of `d_i`, one-sided.
  - **Falls** (counts against the assumption): high against low sums below zero with p ≤ 0.05,
    or an adjacent pair sums below zero with p ≤ 0.025.
  - **Rises:** pooled successes satisfy low ≤ medium ≤ high, and high against low sums above
    zero with p ≤ 0.05.
  - **Not resolved:** anything else, reported with the pooled counts.
  - Sensitivity (simulated, 16 tasks with five at zero): a pooled change of 12 points is
    detected in 52% of runs, 17 points in 79%, 20 points in 88%; false alarm 4%. The public
    aggregate difference between `low` and `high` is 12 points.
- **Cost:** per effort, mean priced cost and minutes per observation, tokens by kind, and cost
  per success (the cost of every start at that level over its successes; undefined without
  one). An effort level is named dominated only when another has more pooled successes beyond
  the interval and lower cost; otherwise "not resolved".
- **Adaptive order: rejected.** Running `high` first and skipping the lower levels of a task at
  0 of 5 assumes the thing under test and removes the tasks where a violation would show (high
  fails, low passes); leaving those tasks out instead keeps tasks selected for success at high.
  D7's order gives the saving that matters, a graceful stop, without either.
- **Contamination scan:** transcripts are searched for the benchmark's repository and hub
  names, its reference-solution file names, the canary string and direct API use. A hit excludes
  the attempt and is listed. A readout that ends in a stop prints no placement.

### D7. Order and stop rules

1. **Smoke:** one attempt, gsea-proteomics at `low` (cheap, short, and it needs a package index,
   so it exercises the allowlist). Then stop and read: the pinned CLI version ran in the
   container; every usage row names the bound model; the effort and the dollar cap are on the
   recorded command line; web tools are off; denied hosts are logged and allowed ones work;
   usage is priced and within 5% of the CLI's figure; the verifier returned a reward; the key's
   value is in no kept file; the slot settled. A pass makes it slot 1 of round 1. A kit change
   after it means a new manifest hash and ledger row; the start stays counted and is excluded.
2. **Rounds.** Five rounds, each one attempt of every task at every level (48 slots), in an
   order fixed by a hash of a frozen seed, the round, the task and the effort. A stop for money
   leaves the cells balanced, and effort is not confounded with time of day or load.
3. **Stop and read after round 1:** classification counts, cost per effort against the
   estimate, the scan, the load record. The projection goes in the ledger; no threshold moves.
4. **Stops:** a failed smoke; a usage row naming another model; a session on another CLI
   version; infrastructure failures above 10% of starts (from 20 starts on) or above 20% at one
   level; five pre-session failures in a row or 24 in all; contaminated attempts on three tasks;
   the key's value in a kept file; under 20 GB free; an unclassified outcome (a pause). A high
   load is a wait, not a stop.
5. Nothing is topped up, moved between cells or re-thresholded after the first paid start.

## Steps 7 to 9, in outline

**Step 7: freeze the task set.** `family.json` lists the screened-in tasks with digests, counts
and intervals by effort, band effort, the network policy and harness versions, and the effort
verdict; the floor and above-band tasks are listed beside them. It is reported to the owner with
the ladder's cost. Proposed reading of the verdict for the search: "rises" lets it walk one
role's effort at a time; "falls" drops the walk; "not resolved" keeps the walk and adds both
corners. Fewer than ten screened-in tasks is reported as too few for step 9's smallest design.

**Step 8: merge and freeze the seed.** `milestones.orc` (49 lines on `spike/long-horizon-seed`)
is written once, after the surface-coherence changes of Lane D stage 5 merge (46 lines
expected). Required: it compiles at the current target under 50 lines; an effort input per role
(owner, 2026-11-13); its five stand-in scenarios (clean, a failed check, a refused review, a
kill and resume, a kill inside a second attempt) become a test; a registry row; a hash in the
family record. **The deterministic check on the setup step earns its place, in its cheapest
form:** the setup step returns the paths of the files later steps read, typed so that a missing
file fails that step, as the spec and plan paths already are. Prompt wording of the setup step
is a search dimension, so a mutated prompt needs a mechanical floor. It checks existence only;
a content check would freeze what the search may vary. No command step and no new script.

**Step 9: seed against a direct session at matched priced-token cost. NOT APPROVED.**

- Arms, all `claude-haiku-5-5`, same container, limits and network policy: a direct session at
  the task's band effort, fresh runs (the ladder's runs chose the tasks and would bias the
  baseline); the seed with every role at that effort.
- Bar: the seed's pass rate against the re-roll curve `Q(k*)` of the direct arm, `k*` being the
  seed's mean priced cost over a direct run's. Beating one direct run but not `Q(k*)` is a null.
- Smallest useful size: ten tasks, 8 direct and 4 seed runs each. It detects a difference of
  about 32 points; twenty tasks, about 21 (the seed design's computation, not re-derived).
- Rough cost: 80 direct runs at USD 0.7 to 1.1 is about USD 55 to 90. A seed run's cost is
  unknown; at four to eight direct runs each, 40 seed runs are about USD 110 to 350. Total about
  USD 170 to 440, after a measure-free smoke of two seed runs (about USD 15) that measures the
  seed's cost in direct-run equivalents.
- Open design work first: how a workflow's steps run inside a task container, and what the
  seed uses as its visible check, since these tasks ship none.

## Tasks

Branch `feat/lh-ladder` from `spike/long-horizon-tasks`, in its own worktree; kit under
`experiments/long_horizon_tasks/`. Every command has the blocking provider stubs first on
`PATH`. Roles are named per the subagent policy.

### Task 1: pin and qualify the 16 (impl_code; 8 h plus about 8 h of machine time)

**Files:** create `tasks.json` (name, 4.1.0 digest, cap, extra hosts, oracle evidence); modify
`oracle_check.sh` (repeat count, the network overlay, a load gate); `summarize.py` (counts).

- [ ] Fetch the 16 at the published 4.1.0 digests; record any mismatch with the copies checked.
- [ ] Probe the allowlist with the `oracle` agent (no model call): a package index answers, a
      code host is denied and logged, and the route that sets the mode leaves task files
      byte-identical if the harness offers one.
- [ ] Oracle and do-nothing runs, five each, under the final policy and the load gate.
- [ ] Install-only probe of the pinned CLI in one image of each base distribution.

**Verify:** `python -I experiments/long_horizon_tasks/summarize.py <jobs>` prints, per task,
reference 5 of 5 and untouched 0 of 5; the ledger gets the surviving list.

### Task 2: criterion and manifest (impl_code; 2 h)

**Files:** create `ladder.json` (model, efforts, versions, digests, caps, ceiling, schedule
seed, allowlist, load gate, classification table, readout rules, price-table hash) and
`manifest.json` (SHA-256 of every kit file). Test:
`test_criterion_caps_follow_the_frozen_formula_and_are_equal_across_efforts`.

### Task 3: the launcher (impl_code; 14 h)

**Files:** create `experiments/long_horizon_tasks/ladder.py` and
`tests/experiments/test_long_horizon_ladder.py`.

**Interface:** `ladder.py plan | launch | status`. A paid launch needs `LH_SPEND_AUTHORIZED=yes`,
`LH_MANIFEST_SHA256` and `LH_RUNTIME_COMMIT` (both from the ledger) and `LH_KEY_FILE`; a
rehearsal needs `LH_REHEARSAL_STANDINS=<dir>` and refuses if any of those is set. State lives
outside the checkout (`$HOME/.local/state/lh-ladder`; another root for rehearsals): one
directory per slot, claimed by `mkdir`, with the reservation, the launcher's pid and start
time, and later the settlement. It runs from a detached checkout of the frozen commit and
refuses code imported from elsewhere. It reuses the package's usage reader and price table.

Tests, each failing first for its stated reason, against a stand-in harness on a closed `PATH`:

- [ ] Refusals: no authorization; a manifest or runtime commit other than the ledger's; a dirty
      kit; a model or effort outside the criterion (Sonnet, Fable, an alias, `max`); a task
      whose digest differs; a harness environment other than the pinned one; a key file inside
      the checkout or readable by others; a rehearsal with a key; a stand-in without its marker.
- [ ] `test_sixty_concurrent_launches_never_commit_more_than_the_ceiling`.
- [ ] `test_a_slot_that_does_not_fit_waits_and_is_never_skipped`; `test_start_241_is_refused`.
- [ ] `test_unreadable_usage_settles_at_the_full_reservation`;
      `test_settlement_takes_the_larger_of_table_price_and_cli_figure`.
- [ ] `test_classification`, over one fixture per row of D5 and an unknown exception.
- [ ] `test_a_slot_whose_session_started_is_never_launched_again`;
      `test_a_pre_session_failure_is_relaunched_at_most_twice`.
- [ ] `test_reconcile_stops_only_the_containers_of_a_dead_launcher`: pid and start time must
      both match; an open reservation without a live launcher is stopped, then settled.
- [ ] `test_harness_command_carries_model_effort_version_cap_and_zero_retries`;
      `test_the_key_value_is_in_no_file_under_the_job_and_state_roots`.
- [ ] `test_schedule_is_deterministic_balanced_and_begins_with_the_smoke_slot`;
      `test_round_two_waits_for_the_recorded_round_one_read`.

**Verify:** `pytest -q tests/experiments/test_long_horizon_ladder.py`, `--collect-only` on it,
then the sampled broad check.

### Task 4: the readout (impl_code; 5 h)

**Files:** create `experiments/long_horizon_tasks/readout.py`; tests in the same test module.

- [ ] `test_intervals_match_the_report_table`; `test_placement_labels_on_constructed_counts`.
- [ ] `test_effort_verdict_falls_rises_and_not_resolved`; `test_incomplete_triples_are_left_out`.
- [ ] `test_exclusions_are_listed_and_never_scored_zero`;
      `test_a_stop_readout_prints_no_placement`; `test_family_json_names_criterion_and_digests`.

### Task 5: zero-spend rehearsal (impl_code; 6 h)

- [ ] In the suite: the whole schedule against the stand-in harness, ending inside both caps.
- [ ] On containers, no key on the machine's path: three tasks with a stand-in `claude` placed
      in a rehearsal copy of the agent image at the pinned version, so the harness skips the
      install. The stand-in records its command line and environment, probes an allowed and a
      denied host, looks for `/tests`, `/solution` and any host path, and writes session
      records. One slot is killed mid-session and reconciled; one verifier is regraded.

**Verify:** the rehearsal's readout, the D7 smoke checks on its records, and a `grep` for a
dummy key value over the job and state roots finding nothing. Results go in the ledger.

### Task 6: independent pre-spend review (review_code; 3 h, plus 5 h of fixes and re-review)

By a reviewer who wrote none of the kit. Its brief lists the holes earlier launcher reviews
found: a retry that turns a failure into a pass; a CLI that updated itself after the pin; a
sweep that matched a reused pid; a launch between reservation and record; a runtime commit
recorded but not enforced. The reviewer mutates each guard and reports the survivors.

### Task 7: freeze and ledger (coordinator; 1 h)

Before the first attempt the ledger holds: the surviving task list and digests; the manifest
hash and runtime commit; the CLI and harness versions; the price-table hash; the network
policy; the key's workspace limit; the review verdict; the rehearsal result; spend to date 0.

### Tasks 8 to 10: smoke (2 h), the run (6 h of attention), readout and step 7 (4 h)

The run needs about 35 to 45 hours of a quiet host at four concurrent attempts, in tmux. The
last task writes `results/readout.md`, `family.json`, a report under `docs/reports/`, the
actual spend in the ledger, and the roadmap's step table. **Hours in all:** about 56 of
engineering and review, plus machine time.

## What This Makes Harder

- The family is tied to one benchmark, harness and CLI version and one network policy; a later
  comparison must reuse all four or re-qualify. The allowlist ends comparability with the
  public leaderboard.
- Reservations far above expected cost leave the last USD 10 to 25 unusable, and "no agent
  retry" means provider incidents reduce n for good.
- Task files live outside the repository: a clean clone must fetch them by digest to rerun.

## Not Verified While Planning

| Assumed | Probe that settles it |
| --- | --- |
| Allowlist mode works under rootless Podman, and the mode can be set without editing a task file | Task 1's oracle probe; the harness's config print |
| Agent setup runs outside the agent-phase policy, so the installer's host need not be allowed (source read) | Task 1's install-only probe under the allowlist |
| The release host still serves CLI 2.1.311; the installed version is checked by the harness | Install-only probe; the version in the result record |
| `low` and `medium` are accepted for this model (only `high` was seen here) | The smoke (`low`); the first `medium` observation |
| The CLI's budget limit stops a session in a container, subagents included | Recorded command line in rehearsal; cost against cap in round 1; the console limit as backstop |
| Session records copied out of the container cover subagent usage and survive a killed session | Rehearsal kill; the 5% agreement check in the smoke |
| The harness keeps the key out of its job files | The rehearsal's `grep` with a dummy value |
| The verifier still runs after an agent timeout or a dollar-cap stop | Rehearsal with a stand-in that sleeps past a shortened limit |
| The harness can regrade saved artifacts on Podman | Rehearsal regrade |
| Task content at the checked commit equals the 4.1.0 digests | Task 1's fetch by digest |
| Per-effort costs at `low` and `high` (interpolated); the secondary source's USD 0.68 | Round 1 |
| The price table's rates are still the vendor's | Re-read at freeze; no lookup was made while planning |
| Benchmark licence allows this use (Apache-2.0 read in the repository; the canary asks only that data stay out of training sets) | Owner's reading if redistribution is ever wanted; none is planned |
| Four concurrent sessions stay inside the key's rate limits | Round 1's provider-error count |
| Image builds stay reproducible over a multi-day run | Pre-session failure count; image digest per attempt |
| The host can be held at or below a load of 24 | Scheduling by the coordinator; today it ran at 80 to 165 |

## Rulings Made While Planning

Each is a coordinator ruling to confirm; all stay inside the approval.

1. A dropped task is not replaced and its slots are not reassigned (D1).
2. Host-side fixes keep a task the same task; the vba verifier change, if used, is labelled (D1).
3. The agent phase runs on an allowlist, not the declared open network; unenforceable means
   no spend (D3).
4. The dollar cap and reservation depend on the task, not on the effort as this plan's request
   suggested: the calibration rule requires equal limits (D4).
5. A launch that fails before a session begins is not an attempt and is not counted against
   the 240; every started session is, with its cost (D5).
6. No agent retry at all; verifier-only regrade in two stated cases (D5).
7. No outcome-adaptive order; balanced rounds instead (D6, D7).
8. Load gate 24, four concurrent attempts, the task's own time limit, CLI 2.1.311 (D2).
9. Placement by the pooled count with a band effort; the three effort verdicts (D6).
10. A passed smoke is slot 1 of round 1 (D7).
11. Settlement at the larger of two figures; unreadable usage costs the full reservation (D4).

## Owner questions

Only what the approval does not cover.

1. **Credential.** The ladder needs a dedicated API key that the agent can see, in a workspace
   with a spend limit of USD 200, restricted to `claude-haiku-5-5` if the console allows it.
   This is billed API spend, not subscription usage. Is that the route, and will the owner
   create the key?
2. **vba-userform-port.** Will the owner run the one root command that widens the sub-id range
   (report §5)? If not, the task runs with the one-line verifier change, labelled.
3. **Tasks outside the 16.** Replacing a dropped task, or adding tasks if fewer than ten screen
   in (the Science suite, the compose tasks), is not covered and needs its own ladder: new
   spend. This plan does neither. Does the owner want a rule for a later tranche?
4. **Step 9** will be requested once, after step 7, with the size and cost above (about USD 170
   to 440 after a USD 15 smoke); nothing is asked now.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Owner approval (roadmap decision 16; `AGENTS.md` experiment rules): the long-horizon effort ladder, one calibration tranche. |
| 2026-11-13 | Cap: at most 240 attempts (16 tasks × 3 effort levels × 5), ceiling USD 200. An attempt is one whole agent session. No top-up after a null. |
| 2026-11-13 | Model: `claude-haiku-5-5` only, effort `low`, `medium`, `high`. No other model; no judge. Reason for nothing higher: none is needed. |
| 2026-11-13 | Conditions before the first attempt, all open: oracle check on this machine; network policy fixed; launcher independently reviewed; plan and ledger written (this page, unreviewed). |
| 2026-11-13 | Planner's proposals awaiting coordinator confirmation: rulings 1 to 11 above. Expected spend about USD 173 (range 145 to 255) under a hard ceiling of USD 200 enforced by reservation. Spend to date: 0. |
