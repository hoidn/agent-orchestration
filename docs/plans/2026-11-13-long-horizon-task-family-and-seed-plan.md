# Long-Horizon Task Family And Staged Seed Plan (Roadmap Phase 5b)

**Status: Plan; revised after an independent review (accept after fixes); no spend.** This page
turns the staging of
[roadmap Phase 5b](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed)
into a plan: the effort ladder that owner decision 16 approved (steps 4 to 6), and steps 7 to 9
in outline. The roadmap owns the direction. `AGENTS.md` ("Experiment rules") owns the approval
and its limits. The [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
owns the dominance and cost rules. The
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
- **Kind of experiment.** The family is oracle-scored and qualifies by the oracle check, with
  no judge. The ladder places tasks and measures how success responds to effort, under the same
  task, tools and limits at every level. It is not a calibration whose stronger arm must win.
- **A stated difference from the design.** The driver's rule for an oracle family is an oracle
  that accepts two structurally different correct submissions and rejects a broken one. This
  tranche applies the approval's rule (the reference passes, an untouched environment fails);
  the ladder's passing agent runs can supply the second correct submission before step 9.
- **Not approved:** the seed comparison (step 9), any task outside the 16, any other model. No
  claim about any workflow comes from this tranche. "Better" below always means Pareto
  dominance over quality and priced-token cost.

## What this size can and cannot support

- **Can show:** which tasks are at the floor or clearly above the band for a direct session;
  a pooled change of success with effort of about 17 points or more; cost and time per attempt
  by effort; whether containers, network policy and metering hold over 240 runs.
- **Cannot show:** that any task's true rate lies in 10 to 30 percent (about 90 attempts per
  task and setting; report §9); an ordering of tasks; an effort effect for one task; a pooled
  change under about 12 points (detected half the time); that success "does not fall" with
  effort (only that a fall above a stated bound is ruled out); anything about `xhigh` or `max`,
  another model, or a workflow.
- **For the owner, in plain numbers** (the reviewer's model: public counts at `max` scaled by
  the vendor's effort ratios, before any task is dropped or the allowlist lowers rates). About
  10 of the 16 tasks are expected to screen in (9.7), with about a 45 percent chance of fewer
  than ten, the smallest size step 9 can use. There is about one chance in two that the dollar
  rule ends the tranche before attempt 240 (it does when spend runs above about USD 176). The
  likely effort verdicts are "rises" or "not resolved"; neither confirms decision 14's
  assumption beyond the bound the readout states.

## Decisions frozen before spend

**No frozen rule may name a string, key or value that no recording shows.** The classification
table, the stand-in responses, the smoke checks, the stops and the scan terms are written from
the recordings of Task 1, and a test holds each to a recorded line.

### D1. Task list and task identity

A task is **the same task** when every file of its directory equals the benchmark's published
4.1.0 digest, with `task.toml` compared after removing exactly two keys: the agent phase's
network mode and its allowed hosts. The launcher writes those two keys (D3); their digest is
recorded per task and per attempt. Host-side steps (an image pulled by full name, a registry
alias, a wider sub-id range, longer harness probes) change no task file. Any other edit makes
a **modified task**, admitted only as the vba row says. Task files, reference solutions and
verifier tests stay outside this repository; the kit holds names and digests.

| Task | Oracle state (report §5) | To do before spend | Per-attempt cap, USD |
| --- | --- | --- | --- |
| vba-userform-port | Fails unchanged | Widen the sub-id range (owner question 3); else the one-line verifier change, labelled "modified verifier" | 14.19 |
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

- **Qualification rule.** A task runs only if, on the pinned 4.1.0 content, under the final
  network policy, on the ladder's CPU set at its concurrency of four, with the load below the
  gate of D2, the reference solution earns reward 1 five times of five and the untouched
  environment reward 0 five times of five.
- **A task that fails the rule and has no host-side fix is dropped.** It is not replaced and
  its 15 slots are not given to other tasks. Replacement from outside the 16 is owner
  question 4. A task whose reference passes five of five quiet but failed under load stays, on
  the load-sensitive list, frozen from the oracle evidence before spend.

### D2. What an attempt is

- **The agent runs inside the task's agent container,** as the published harness runs its
  Claude Code agent (report §8): one non-interactive session with the task's instruction. This
  is what the public per-task figures measured, and the instructions assume an agent with root,
  a package manager and background processes there.
- **The binary.** The harness downloads the CLI inside the container with the vendor's
  bootstrap script, pinned by version. Nothing is mounted (report §4), and the host's own CLI,
  which updates itself, is never used. The agent-setup log is kept per attempt; it names the
  system packages the harness adds.
- **The credential: the agent never sees the key.** A host-side passthrough (D4) holds the one
  API key. The container gets a base URL pointing at the passthrough and a per-slot dummy
  token. The host home, its Claude configuration and its login never enter a container. With a
  base URL set, the harness itself pins every tier alias and the subagent model to the bound
  model (report §8).
- **Binding.** Model `claude-haiku-5-5` by exact id; effort `low`, `medium` or `high` as the
  CLI's `--effort`; no fallback model; auto-update off. The switches for the advisor tool and
  the refusal fallback are named in the criterion once a recording shows that they exist.
- **CLI version:** the one with real recordings: 2.1.311 if the public trial archives of that
  row can be fetched and it still installs; otherwise 2.1.323, for which real sessions are on
  file from the Phase 2 smoke. The ledger records the choice. Each session's reported version
  is checked; another version is a stop.
- **Harness and limits:** Harbor 0.25.0 and podman-compose 1.6.0 from a pinned environment,
  one harness run per attempt, its retry count at zero. Equal at every effort level: the task's
  own agent limit (28,800 s for all 16) and verifier limit, multiplier 1; its CPUs and memory;
  a process limit of 4,096; the dollar cap of D4.
- **Load and CPUs.** Load slows the agent's commands, not the model, and some verifiers depend
  on timing. (1) Attempts and their verifiers run on a fixed set of 24 CPUs, by an affinity the
  launcher sets and its containers inherit. This keeps the ladder off the other eight; it does
  not keep other work off the 24, because the CPU-set controller is not delegated to this user.
  (2) The coordinator runs no other heavy work of this session during the tranche. (3) An
  attempt is launched only when the 1-minute and 5-minute load averages are at or below 24 (of
  32 cores); the gate is never moved. (4) If the gate stays closed for two hours while no
  attempt is in flight, the tranche pauses and the coordinator reports to the owner; a ruling
  may resume or end it. Load is recorded at launch, at the session's end and around the
  verifier.
- **Concurrency:** four attempts, two until every effort level has one clean observation. The
  ladder's own containers count toward the gate, so it will often run two or three.
- **Withheld:** `tests/` and `solution/` never enter the agent's container, and the verifier
  image receives only the declared artifacts: the harness's construction, checked in rehearsal.

### D3. Network policy

- **Declared:** no agent network mode on any of the 16 (open internet); no internet for two
  verifiers. **Enforced under rootless Podman:** no-network verifier phases, by the harness's
  egress sidecar (report §7). Its allowlist mode was not tried.
- **Policy for the ladder: agent phase on an allowlist,** applied by the two `task.toml` keys
  of D1, because the harness ignores run-level hosts when a task's policy is open (report §8).
  One list for every task and effort: the passthrough's address, listed explicitly (the harness
  stops adding the inference host once any host is given); the Python, Node and Rust package
  indexes; the system package mirrors of the three base distributions. The vendor's API host
  is not on it. A task that needs another host gets it by name in `tasks.json`. Image build and
  agent setup keep the open network (the agent is not running then). Verifiers keep what they
  declare. The CLI's web search and fetch tools and any built-in web agent are off: the search
  tool runs at the provider and would bypass the container's egress.
- **The egress log is kept:** copied out before the container is deleted, part of the
  attempt's record and of the scan.
- **Reason and consequence.** The reference solutions are public; with open internet a pass may
  mean the agent found the answer. The rates are then not comparable with the public row, and
  the later comparison must use the same policy.
- **Cannot be enforced:** what the model remembers (the vendor's help page gives a training
  cutoff of June 2026, read through a search result; the tasks were published in August 2026
  with a canary string); content on an allowed host, since package indexes can hold anything;
  name lookups and ping, which the sidecar allows; a request that names an allowed host but is
  routed elsewhere, since filtering is by the requested name.
- **If the allowlist cannot be enforced here,** the plan stops before spend.

### D4. Metering, price and the ceiling

- **The passthrough** is a small host-side process, part of the kit and of the pre-spend
  review: the only holder of the key and the only route from a container to the model. For
  every request it maps the dummy token to a slot and refuses an unknown one; refuses any model
  other than `claude-haiku-5-5`; refuses when the slot's metered spend has reached its cap,
  when all slots together have reached USD 200, or when the tranche is stopped; prices the
  response's usage with the frozen table and appends it to the slot's log. What it does with
  requests that declare provider-side tools is fixed from the recordings.
- **Price table:** `orchestrator/providers/price_table.json` at the frozen commit, by SHA-256
  (dated 2026-11-11; this model: input 0.10, output 0.50, cache read 0.01, cache write 0.20 USD
  per million tokens, five times that above 100,000 prompt tokens in a request). Cost is the
  list-price equivalent, not the bill; the table is checked against public token counts first.
- **Per-attempt cap:** `max(3.00, 3 × the task's public mean cost per trial at effort max)`
  (the table in D1), enforced by the passthrough and, as a second guard, by the CLI's own
  budget limit. The largest public trial of any of the 16 cost 2.45 times its task's mean.
  **The cap depends on the task, never on the effort:** the comparison requires equal limits,
  and a cap that bound more often at higher effort would manufacture an effort effect.
- **Reservation before every attempt:** the cap plus USD 1.00 for requests in flight. Under one
  lock the launcher computes *committed* = settled cost of every start + every open
  reservation, and launches only if *committed* + reservation ≤ 200.00 and starts < 240.
- **Settlement** replaces a reservation with the largest of four figures: the passthrough's
  meter, the session records priced by the table, the CLI's own cost figure, and the CLI's
  per-model usage priced by the table. Unreadable usage settles at the full reservation.
- **What ends the tranche:** nothing in flight and the next slot's reservation does not fit; 240
  starts; a stop rule of D7. The launcher never skips ahead to a cheaper slot.
- **Expected spend (planner's estimate):** about USD 173 for all 240 (low 33, medium 53, high
  87), from two public cost points (report §9); plausible range 145 to 255.

**Worst case when one guard fails** (list-price dollars; the middle column is the design before
the passthrough, kept to show what it changes):

| Guard that fails | Without the passthrough | With it |
| --- | --- | --- |
| The CLI's budget limit does not stop a session, or subagents run past it | Four sessions run to their natural end: about USD 260 to 330 | The passthrough refuses at the cap: USD 200 plus the requests in flight, a few dollars |
| The launcher's reservation | Caps still hold: USD 2,086 in theory, USD 145 to 255 in practice | The passthrough's own total stops at USD 200 |
| The key is used directly from a container | No bound in the kit | Not possible: the container holds no key and has no route to the API |
| The passthrough's meter under-counts | (no such guard) | The launcher's reservation and the CLI's limit still hold, as in the design without it |
| The price table is wrong | The bill differs from every meter by the error | The same: every meter shares the table |
| A process of this host user reads the key file | No bound in the kit | No bound in the kit |

The last two rows make the workspace's own spend limit a precondition, not a backstop (owner
question 1). **The passthrough cannot stop:** requests already in flight when a cap is reached;
spend inside a slot's cap that is not the session's own (a second `claude`, or a direct request
with the dummy token: metered and capped, but absent from the session records); a wrong price
table; another process of the same host user reading the key file.

### D5. Infrastructure failure against model failure

Classified by a table frozen in the criterion, with one recorded fixture per harness exception
class and per ending of the stream, without reading the reward. **A session has started** when
its stream holds an init event or the passthrough has metered a request for its slot.

| Outcome | Counts against 240 | Cost against 200 | In k and n | Run again |
| --- | --- | --- | --- | --- |
| **Observation:** the session started and ended by itself, at the task's time limit, at the dollar cap, in a refusal, or at a context or output limit | Yes | Yes | Yes, with the verifier's reward, and reward 0 if it gives none (each ending is flagged) | Never |
| **Infrastructure failure:** the session started and ended in a provider fault (rate limit, overload, server error, lost connection), or the host, Podman, the passthrough or the launcher died | Yes | Yes | No; listed, never scored zero | Never |
| **Pre-session failure:** image build, pull, agent setup, version check, or an authentication or parameter error before any request; no session started | No | Nothing was spent | No | At most twice; after the third failure the slot is lost and its cell has one observation fewer |
| **Verifier gave no reward** after a session that ended by itself | (already counted) | (already counted) | See below | Verifier only |

- **Model-side endings are never excluded.** A dollar-cap stop, a refusal and a context or
  output limit are the longest and dearest sessions and come mostly from the higher efforts;
  excluding them would let effort decide which attempts are dropped. The harness files several
  of them in the same error family as provider faults, so each class gets its own fixture and
  recorded reason. A class or ending with no fixture pauses the launcher for a recorded ruling.
- **The agent is never run twice for one slot,** so a retry cannot turn a model failure into a
  pass.
- **Verifier-only regrade** (no model call, the saved artifacts unchanged), in two cases. (1)
  No reward after a normal ending: up to two regrades below the load gate; a reward then
  stands; a verifier timeout twice is reward 0 (the limit is part of the task); still no reward
  file is an infrastructure failure. (2) A task on the load-sensitive list returned reward 0
  while the load was above the gate during verification: one regrade below the gate, and its
  reward stands. Only a reward of 0 is regraded, because the known defect of such a verifier
  under load is a false failure of correct work. If the harness cannot regrade on Podman, case
  1 becomes an infrastructure failure and case 2 is excluded as "indeterminate".

### D6. The readout

- **Per task and effort:** k of n with the exact (Clopper–Pearson) 95% interval and a label:
  k = 0 "floor", 1 or 2 of 5 "screened in", 3 or more "above". A cell with n under 5 is
  labelled incomplete. Flags and exclusions are listed.
- **Per task, pooled** (K of its n attempts): K = 0 is "floor" (upper bound 21.8% at 15);
  1/15 ≤ K/n ≤ 1/3 is "screened in"; above is "above the band". The pooled label admits a
  task to the family; the per-effort labels are printed beside it, because a pooled count mixes
  three rates. The rule accepts a task of constant true rate 2%, 5%, 10%, 20%, 30%, 50% with
  probability 0.26, 0.54, 0.79, 0.90, 0.72, 0.15. The label is "screened at 15 attempts", never
  "in the 10 to 30 percent band".
- **Band effort,** for every screened-in task: among the levels with at least one success, the
  one whose k/n is closest to 0.2, ties to the lower level. Every screened-in task has such a
  level. It is labelled "noisy, one cell of five", and flagged when that cell is 3 or more. A
  floor or above-band task has none.
- **Effort test, fixed before the data.** A (task, round) triple is complete when its three
  slots are all observations. Over complete triples, `s_i(e)` is task i's successes at effort e
  and `d_i` a difference between two levels. The test is the exact one-sided sign-flip
  permutation test over tasks on the sum of `d_i`.
  - **Falls:** high against low sums below zero with p ≤ 0.05, or an adjacent pair sums below
    zero with p ≤ 0.025. **Rises:** pooled successes satisfy low ≤ medium ≤ high, and high
    against low sums above zero with p ≤ 0.05. **Not resolved:** anything else.
  - **Always reported: the bound on the fall,** the one-sided 95% upper bound on the pooled fall
    from low to high in points (bootstrap over tasks, 10,000 resamples, fixed seed). "Not
    resolved" means only that no fall above that bound was ruled out; it is never read as "does
    not fall".
  - Sensitivity (simulated, 16 tasks with five at zero): a pooled change of 12 points is
    detected in about half of runs, 17 points in 79%, 20 points in 88%; false alarm 5%. With
    ten tasks at the floor a 17-point fall is detected in about a fifth of runs.
- **Cost:** per effort, mean priced cost and minutes per observation, tokens by kind, and cost
  per success (the cost of every start at that level over its successes). An effort level is
  named dominated only when another level beats it on the same sign-flip test at p ≤ 0.05 and
  has a lower mean cost; otherwise "not resolved".
- **Adaptive order: rejected.** Running `high` first and skipping the lower levels of a task at
  0 of 5 assumes the thing under test and removes the tasks where a violation would show;
  leaving those tasks out instead keeps tasks selected for success at high.
- **Contamination scan:** over transcripts and the egress log, for specific strings frozen
  after a dry run on the oracle jobs and the recordings (the benchmark repository's path, the
  canary's identifier, the reference solution's full path in that repository). A hit excludes
  the attempt and is listed. A readout that ends in a stop prints no placement.

### D7. Order and stop rules

1. **Smoke:** one attempt, gsea-proteomics at `low` (cheap, short, and it needs a package
   index). Then stop and read, each check against a recorded form: the pinned CLI version ran;
   the passthrough saw only the bound model; the init event lists no web tool or web agent, and
   no provider-side tool was used; effort and cap are as bound; the egress log shows denied
   hosts denied and allowed ones served; the four settlement figures agree within 5%; the
   verifier returned a reward; the key's value is in no kept file and no command line; the slot
   settled. A pass makes it slot 1 of round 1. A kit change after it means a new manifest hash
   and ledger row; the start stays counted and is excluded.
2. **Rounds.** Five rounds, each one attempt of every task at every level (48 slots), in an
   order fixed by a hash of a frozen seed, the round, the task and the effort. A stop for money
   leaves the cells balanced, and effort is not confounded with time of day or load.
3. **Stop and read after round 1:** classification counts, cost per effort against the
   estimate, the scan, the load record. The projection goes in the ledger; no threshold moves.
4. **Stops:** a failed smoke; a response with non-zero usage that names another model; a
   session on another CLI version; infrastructure failures above 10% of starts (from 20 starts
   on) or above 20% at one level; five pre-session failures in a row or 24 in all; contaminated
   attempts on three tasks; the key's value in a kept file; under 20 GB free. **Pauses:** the
   load wait of D2; the passthrough down; an outcome with no fixture.
5. Nothing is topped up, moved between cells or re-thresholded after the first paid start.

## Steps 7 to 9, in outline

**Step 7: freeze the task set.** `family.json` lists the screened-in tasks with digests, counts
and labels by effort, band effort, the network policy and harness versions, the effort verdict
and the bound on the fall, with the floor and above-band tasks beside them. It is reported to
the owner with the ladder's cost. Reading for the search: only "rises" lets it walk one role's
effort at a time; "falls" drops the walk; on "not resolved" the ladder has not confirmed the
assumption, and the owner chooses, with the bound in hand, between the walk with both corners
added and a direct comparison of the points. Fewer than ten screened-in tasks, about as likely
as not, is reported as too few for step 9's smallest design.

**Step 8: merge and freeze the seed.** `milestones.orc` (49 lines on `spike/long-horizon-seed`)
is written once, after the surface-coherence changes of Lane D stage 5 merge (46 lines
expected). Required: it compiles at the current target under 50 lines; an effort input per role
(owner, 2026-11-13); its five stand-in scenarios become a test; a registry row; a hash in the
family record. **The deterministic check on the setup step earns its place, in its cheapest
form:** the setup step returns the paths of the files later steps read, typed so that a missing
file fails that step, as the spec and plan paths already are. Prompt wording of the setup step
is a search dimension, so a mutated prompt needs a mechanical floor. It checks existence only;
a content check would freeze what the search may vary. No command step and no new script.

**Step 9: seed against a direct session at matched priced-token cost. NOT APPROVED.** Arms, all
`claude-haiku-5-5`, same container, limits and network policy: a direct session at the task's
band effort, in fresh runs (the ladder's runs chose the tasks), and the seed with every role at
that effort. The bar is the direct arm's re-roll curve `Q(k*)`, `k*` being the seed's mean
priced cost over a direct run's: a seed that costs eight direct runs must pass about 83% of the
time where direct passes 20%, so the most likely outcome is a null against re-rolling. Smallest
useful size: ten tasks, 8 direct and 4 seed runs each, which detects about 32 points (twenty
tasks, about 21; the seed design's computation on its own assumed rates). Rough cost: about
USD 170 to 440, after a measure-free smoke of two seed runs (about USD 15), and excluding any
ladder for added tasks. Open design work, larger than one line: how a workflow's steps run
inside a task container, and what the seed uses as its visible check, since the tasks ship none.

## Tasks

Branch `feat/lh-ladder` from `spike/long-horizon-tasks`, in its own worktree; kit under
`experiments/long_horizon_tasks/`, tests in `tests/experiments/test_long_horizon_ladder.py`,
each failing first for its stated reason. Every command has the blocking provider stubs first
on `PATH`. Tasks 1 and 2 come before the criterion and the launcher, because they set both.

### Task 1: recordings (impl_code; 8 h)

**Files:** create `stub_api.py` (a local stand-in for the model API: canned streams with chosen
usage, tool calls and a subagent) and `recordings.json` (name, source and SHA-256 of each
recording; the recordings stay outside the repository).

- [ ] The pinned CLI, installed in one task image by the harness's install-only mode, run
      against the stub on the host with no key and no route to the real API (the task's brief
      says in words that this run makes no provider call). Recorded: the init event with its
      tools and built-in agents; the stream, exit code and harness exception class for a normal
      end, a budget stop, a refusal, a context-limit end and a timeout kill; the session files'
      usage rows; per-model usage; every model id the CLI asks for; whether subagent usage
      reaches the records and the budget; whether the advisor and refusal-fallback switches
      exist.
- [ ] Two or three public trial archives of the leaderboard row for the same CLI version,
      fetched as public data with a generic client.
- [ ] One fixture per harness exception class and stream ending, cut without task content.

**Verify:** `recordings.json` lists every scenario with a digest; a note records each
assumption of this plan that a recording contradicts.

### Task 2: pin, probe and qualify the 16 (impl_code; 10 h plus about 10 h of machine time)

**Files:** create `tasks.json` (name, 4.1.0 digest, overlay digest, cap, extra hosts, oracle
evidence); modify `oracle_check.sh` (repeats, the two-key overlay, the CPU set, the load gate)
and `summarize.py` (counts).

- [ ] The sub-id range is widened first, with no container running (owner question 3). The 16
      are fetched at the 4.1.0 digests; any mismatch with the copies checked is recorded.
- [ ] Allowlist probe with the `oracle` and `nop` agents: an allowed index answers; a code host
      is denied and logged; a request that names an allowed host but goes to a denied address
      is refused; setup runs on the open network; a host listener is reached through the list;
      the egress log is captured before teardown. The affinity reaches both containers.
- [ ] Oracle and do-nothing runs, five each, under the final policy, four at a time.
- [ ] A dry run of the contamination terms over these jobs and the recordings, then the terms
      are frozen. The price table is checked against the archives' token counts.

**Verify:** `python -I experiments/long_horizon_tasks/summarize.py <jobs>` prints, per task,
reference 5 of 5 and untouched 0 of 5; the ledger gets the surviving list.

### Task 3: criterion and manifest (impl_code; 2 h)

**Files:** create `ladder.json` (model, efforts, versions, digests, caps, ceiling, schedule
seed, allowlist, CPU set, load gate and wait, the classification table with the recording each
row cites, readout rules, scan terms, price-table hash) and `manifest.json` (SHA-256 of every
kit file). Tests: caps follow the formula and are equal across efforts; every string a frozen
rule matches occurs in a recording.

### Task 4: the passthrough (impl_code; 8 h)

**Files:** create `passthrough.py`. Tests, with `stub_api.py` as the upstream:

- [ ] It refuses an unknown token; a model other than the exact id (Sonnet, Fable, an alias);
      a request for a slot at its cap; any request once the total reaches USD 200 or while the
      tranche is stopped.
- [ ] Its meter prices streamed and plain responses as the table does; a request in flight at
      the cap is metered to its end; the key appears only in the upstream request.
- [ ] The passthrough going down pauses the tranche.

### Task 5: the launcher (impl_code; 16 h)

**Files:** create `ladder.py`. **Interface:** `ladder.py plan | launch | status`. A paid launch
needs `LH_SPEND_AUTHORIZED=yes`, `LH_MANIFEST_SHA256` and `LH_RUNTIME_COMMIT` (both from the
ledger) and `LH_KEY_FILE`, which only the passthrough opens; a rehearsal needs
`LH_REHEARSAL=<dir>` and refuses if any of those is set. State lives outside the checkout
(`$HOME/.local/state/lh-ladder`; another root for rehearsals): one directory per slot, claimed
by `mkdir`, with the reservation, the dummy token, the launcher's pid and start time, and later
the settlement. It runs from a detached checkout of the frozen commit, refuses code imported
from elsewhere, and reuses the package's usage reader and price table.

Tests, against a stand-in harness that replays the recorded fixtures on a closed `PATH`:

- [ ] Refusals: no authorization; a manifest or runtime commit other than the ledger's; a dirty
      kit; a model or effort outside the criterion; a task whose digest differs outside the two
      overlay keys; another harness environment; a key file inside the checkout or readable by
      others; a rehearsal with a key.
- [ ] Money: sixty concurrent launches never commit more than the ceiling; a slot that does not
      fit waits and is never skipped; start 241 is refused; settlement takes the largest of
      four figures; unreadable usage settles at the full reservation.
- [ ] Classification over every recorded fixture: a budget stop, a refusal and a context limit
      are observations; a class with no fixture pauses. A slot whose session started is never
      launched again; a slot is lost after its third pre-session failure; a regrade never
      starts the agent; reconcile stops only the containers of a dead launcher (pid and start
      time both match).
- [ ] Host: the load gate waits, and pauses after two hours with nothing in flight; low disk
      stops the tranche; the egress log is kept before teardown. The harness command carries
      model, effort, version, cap, base URL and zero retries; the key's value is in no file and
      no command line. The schedule is deterministic, balanced and begins with the smoke slot;
      round two waits for the recorded round-one read.

**Verify:** `pytest -q tests/experiments/test_long_horizon_ladder.py`, `--collect-only` on it,
then the sampled broad check.

### Task 6: the readout (impl_code; 6 h)

**Files:** create `readout.py`. Tests: intervals match the report's table; cell and pooled
labels; the band effort is defined for every screened-in pattern; the effort verdict and the
bound on the fall on constructed tables; a ceiling stop leaves partial rounds out of complete
triples; exclusions are listed and never scored zero; a stop readout prints no placement;
`family.json` names the criterion and the digests.

### Task 7: zero-spend rehearsal (impl_code; 6 h)

- [ ] In the suite: the whole schedule against the stand-in harness, ending inside both caps.
- [ ] On containers, with no key on the machine: three tasks with the real pinned CLI, the
      passthrough, and `stub_api.py` as its upstream. One session runs to a budget stop, one
      past a shortened time limit, one is killed and reconciled, one verifier is regraded.

**Verify:** the D7 smoke checks on the rehearsal's records; the stub's streams match the
recordings in form; a dummy key value in no file under the job and state roots and in no
command line. Results go in the ledger.

### Task 8: independent pre-spend review (review_code; 4 h, plus 6 h of fixes and re-review)

By a reviewer who wrote none of the kit; the passthrough is in scope. Its brief lists the holes
earlier reviews found: a retry that turns a failure into a pass; a CLI that updated itself after
the pin; a sweep that matched a reused pid; a launch between reservation and record; a runtime
commit recorded but not enforced; a rule written for output nobody had observed; an identity
check the overlay defeats; a credential an agent can reach. The reviewer mutates each guard.

### Tasks 9 to 12: freeze (1 h), smoke (2 h), the run (6 h of attention), readout and step 7 (4 h)

Before the first attempt the ledger holds: the surviving tasks with task and overlay digests;
the manifest hash and runtime commit; the CLI and harness versions; the price-table hash; the
network policy; the workspace limit and rate-limit tier as read in the console; the quiet
window; the review verdict; the rehearsal result; spend to date 0. The run needs about 35 to 45
hours of a quiet host at four concurrent attempts, up to about 60 when its own load holds it to
two or three; it runs in tmux. The last task writes `results/readout.md`, `family.json`, a
report under `docs/reports/`, the actual spend in the ledger, and the roadmap's step table.

**Hours in all:** about 79 of engineering and review (56 before the review; the recordings and
the passthrough add 8 each, the probes, launcher, readout and review 7 between them), plus
machine time.

## What This Makes Harder

- The family is tied to one benchmark, harness and CLI version and one network policy; a later
  comparison must reuse all four or re-qualify. The allowlist ends comparability with the
  public leaderboard.
- The passthrough is reviewed code that every later long-horizon run needs. Reservations far
  above expected cost leave the last USD 10 to 25 unusable, and "no agent retry" means provider
  incidents reduce n for good.
- Task files and recordings live outside the repository: a clean clone fetches them by digest.

## Not Verified While Planning

**Before the launcher is written** (Tasks 1 and 2; these set its design and the criterion):

1. The allowlist under rootless Podman: allowed, denied and wrongly routed requests; setup on
   the open network; the passthrough's address reachable; the egress log captured.
2. What Task 1 records: stream, session-file and result forms; a real budget stop and its
   harness class; the model ids requested; subagent accounting; the switches for web tools, the
   advisor and the refusal fallback; whether a custom base URL changes the CLI's behaviour.
3. The pinned CLI still installs, in one image per base distribution, and reports its version.
4. The credential route: the console's spend limit is hard and prompt; the rate-limit tier.
5. The contamination terms give no false hit on the oracle jobs and the archives.
6. The price table and the training cutoff against the vendor's pages and public token counts.
7. The host plan: the affinity reaches both containers; the quiet window; the sub-id widening.
8. Task content at the checked commit equals the 4.1.0 digests (the checked copies carry other
   version numbers; every task is re-run in Task 2 either way).

**At the rehearsal:** the verifier runs after a timeout and after a budget stop on Podman (the
harness source says it does); a regrade on Podman; kill and reconcile; the model variables
reach the session; the dummy key is in no file and no command line; the stub reproduces the
recordings in form.

**At the smoke or in round 1:** `low` and `medium` are accepted for this model at the API (only
`high` was seen here); cost per effort (`low` and `high` are interpolated); provider errors at
four concurrent sessions; image builds stay reproducible over days.

**Not probed:** the benchmark's licence beyond its text (Apache-2.0, with a canary asking that
data stay out of training sets); no redistribution is planned.

## Rulings

The planner's eleven rulings are adopted with the reviewer's amendments (2026-11-13) and are the
rules of D1 to D7: no replacement of a dropped task; host-side fixes and the two network keys
keep task identity; an allowlist or no spend; cap and reservation by task, not by effort; a
launch that fails before a session starts is not an attempt; no agent retry, and regrade of the
verifier only; balanced rounds, no adaptive order; the load gate, four slots, the task's own
time limit and the CLI version with real recordings; placement per effort and pooled with a
bound on the fall; a passed smoke as slot 1; settlement at the largest of four figures. The
coordinator's rulings of the revision are in the ledger's last row. All thirteen review minors
are applied and none is rejected; minor 8 (the training cutoff) rests on a search result until
the vendor's page is read in Task 2.

## Owner questions

Only what the approval does not cover.

1. **One API key,** in a workspace with a spend limit of USD 200, readable only by the
   passthrough. This is billed API usage, not the subscription, and would be the project's
   first. Will the owner create it, and confirm in the console that the limit is hard and what
   the workspace's rate-limit tier is?
2. **A quiet window on this machine, about 35 to 45 hours** (up to about 60), as a condition of
   the run: no other heavy work, the load at or below 24. Without it the ladder does not run on
   this plan. The results that would otherwise measure the neighbours are those of
   wal-recovery-ordering (a thread-timing verifier; its reference failed once under load) and,
   likely but untested, vf2-speedup-networkx (a speed target) and the tasks that train or
   compile inside their limits (lake-temp-glm, pretrain-shard-corruption, vpp-loss-divergence,
   retro-console-soc). A smaller tranche without those six is a choice the owner could make.
3. **Two root commands.** Widening the sub-id range (report §5), with no container running;
   without it vba-userform-port runs with the one-line verifier change, labelled. Optionally,
   delegating the CPU-set controller to this user, which turns D2's affinity into a reservation.
4. **Tasks outside the 16.** Fewer than ten screened-in tasks is about as likely as not.
   Replacing a dropped task or adding tasks (the Science suite, the compose tasks) is not
   covered and needs its own ladder, new spend. Does the owner want a rule for a later tranche?
5. **Step 9** will be requested once, after step 7, with the size and cost above.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Owner approval (roadmap decision 16; `AGENTS.md` experiment rules): the long-horizon effort ladder, one calibration tranche. |
| 2026-11-13 | Cap: at most 240 attempts (16 tasks × 3 effort levels × 5), ceiling USD 200. An attempt is one whole agent session. No top-up after a null. |
| 2026-11-13 | Model: `claude-haiku-5-5` only, effort `low`, `medium`, `high`. No other model; no judge. Reason for nothing higher: none is needed. |
| 2026-11-13 | Conditions before the first attempt, all open: oracle check on this machine; network policy fixed; launcher independently reviewed; plan and ledger written. |
| 2026-11-13 | Plan proposed. Expected spend about USD 173 (range 145 to 255) under a ceiling of USD 200 enforced by reservation. Spend to date: 0. |
| 2026-11-13 | Independent review of the plan and the report: accept after fixes (1 blocker, 6 majors, 13 minors); nothing exceeds the approval; the stated arithmetic was recomputed and holds. Coordinator rulings, all applied in this revision: recordings of the real CLI and the public archives before the criterion and the launcher, and no frozen rule naming what no recording shows; budget stops, refusals and context-limit endings are attempts, never excluded; the allowlist as two exempt `task.toml` keys with a recorded digest; a host-side passthrough that holds the key, admits only the bound model, meters, and enforces each reservation and the USD 200 ceiling; the load gate kept, with a fixed CPU set, no other heavy work of the session, and a pause after a two-hour wait; placement per effort, a band effort for every pattern, the verdict as a bound on the fall; the unverified list ordered by probe time; the worst case per failed guard (about USD 260 to 330 without the passthrough if the CLI's limit fails; USD 200 plus requests in flight with it; the workspace limit as precondition). The planner's eleven rulings adopted with the reviewer's amendments. Hours re-estimated at about 79. Spend to date: 0. |
