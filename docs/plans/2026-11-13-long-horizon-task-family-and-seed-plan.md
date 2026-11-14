# Long-Horizon Task Family And Staged Seed Plan (Roadmap Phase 5b)

**Status: Plan; accepted by the coordinator on 2026-11-13 after an independent review; revised a
second time against the recordings of Task 1; no spend.** This page
turns the staging of
[roadmap Phase 5b](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed)
into a plan: the effort ladder that owner decision 16 approved (steps 4 to 6), and steps 7 to 9
in outline. The roadmap owns the direction. `AGENTS.md` ("Experiment rules") owns the approval
and its limits. The [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
owns the dominance and cost rules. The
[survey and feasibility report](../reports/2026-11-13-long-horizon-benchmark-survey-and-feasibility.md)
holds the evidence cited here as "report §n"; recordings are cited by name, as listed in
`experiments/long_horizon_tasks/recordings.json` and explained in `RECORDINGS.md` beside it
(branch `feat/long-horizon-recordings`). This plan owns its task list, limits, thresholds and
readout. Its commands are for this machine and are not copyable examples. Spend is
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

- **What is measured: the three-tool configuration.** All 330 public trials ran the CLI with
  three tools (Bash, Edit, Read), and so does the ladder (D2). It does not measure the default
  agent with its twenty tools, subagents and skills, and says nothing about that agent.
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
recorded per task and per attempt. Host-side steps change no task file and are part of the
method: an image pulled by full name or a registry alias; a wider sub-id range; the harness
wrapper, which lengthens the harness's probes and passes `-T` where the harness passes a flag
podman-compose rejects (fixture `pre-session-network-switch-RuntimeError`); a containers
override file that silences the compose banner (fixture
`pre-session-agent-install-RuntimeError`). Any other edit to a task file makes a **modified
task**, admitted only as the vba row says. Task files, reference solutions and
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
  Claude Code agent (report §8): one non-interactive session with the task's instruction.
- **In the public row's configuration.** The ladder sets `CLAUDE_CODE_SIMPLE=1` and
  `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`, as all 330 public trials did (their metadata, saved
  with the archives). The init event then lists the tools `Bash, Edit, Read` (fixture
  `public-normal-end`; reproduced here in recording `simple-medium`); without the first
  variable it lists twenty. This also keeps effort equal within an attempt: the Agent tool,
  which the setting removes, let a session at `low` run a subagent at `max` (recording
  `subagent-override-low`). An init event with any other tool list is a stop.
- **The binary: CLI 2.1.311,** the version of the public row. It still installs through the
  harness's own path, inside the container, about four minutes per attempt under load
  (recording `install-only`), and its public archives were fetched. Nothing is mounted, and the
  host's own CLI is never used. **The version evidence is the init event's
  `claude_code_version`:** the harness keeps neither a setup log nor the output of its version
  check. Another version is a stop.
- **Binding.** Model `claude-haiku-5-5` by exact id; effort `low`, `medium` or `high`, which
  reaches each request as `output_config.effort` (recorded at all three). With a base URL the
  harness pins every alias, and no recorded request named another model, a refusal's retry
  included. The advisor and fallback switches exist in the binary, but no recording shows
  their effect, so none is set; the passthrough refuses any other model, and no key enters any
  container (D4).
- **The CLI's own retries are inside the attempt** and are billed: one after a refusal, three
  after an output limit, one compaction attempt before a context-limit ending (recorded).
- **Harness and limits:** Harbor 0.25.0 and podman-compose 1.6.0 from a pinned environment,
  one harness run per attempt, its retry count at zero. Equal at every effort level: the task's
  own agent limit (28,800 s for all 16) and verifier limit, multiplier 1; its CPUs and memory;
  a process limit of 4,096; the dollar cap of D4.
- **Load and CPUs.** Load slows the agent's commands, not the model, and some verifiers depend
  on timing. (1) Attempts and their verifiers run on a fixed set of 24 CPUs, by an affinity the
  launcher sets and its containers inherit; this keeps the ladder off the other eight, not
  other work off the 24. (2) The coordinator runs no other heavy work of this session during
  the tranche. (3) An attempt is launched only when the 1-minute and 5-minute load averages
  are at or below 24 (of 32 cores); the gate is never moved. (4) If the gate stays closed for
  two hours while no attempt is in flight, the tranche pauses and the coordinator reports to
  the owner. Load is recorded at launch, at the session's end and around the verifier.
- **Concurrency:** four attempts, two until every effort level has one clean observation; the
  ladder's own containers count toward the gate, so it will often run two or three.
- **Withheld:** `tests/` and `solution/` never enter the agent's container, and the verifier
  image receives only the declared artifacts (the harness's construction, checked in rehearsal).

### D3. Network policy

- **The agent phase runs on an allowlist,** written as the two `task.toml` keys of D1, because
  the reference solutions are public and with open internet a pass may mean the agent found
  the answer. It works under rootless Podman with the wrapper's fix: an allowed package index
  answered, a code host and the vendor's API were refused, and image build and agent setup ran
  on the open network before the switch (recording `probe-oracle`). Verifiers keep what they
  declare. The rates are not comparable with the public row's on this axis, and the later
  comparison must use the same policy.
- **The list,** the same for every task and effort: the relay of D4, by name; the Python, Node
  and Rust package indexes; the system package mirrors of the three base distributions. A task
  that needs another host gets it by name in `tasks.json`. **The host's own address is never
  listed.** Entries carry no port, and when the host's address was listed the container reached
  the host's ssh port as well as the intended listener (recording `probe-oracle`).
- **A request that names an allowed host but is sent to another address goes to the named
  host:** the proxy dials the name itself (two misrouted requests both reached the package
  index). The earlier plan listed this as unenforceable; it is enforced.
- **Web tools are absent** in the three-tool configuration. Recorded with them on
  (`web2-low`): the fetch tool contacts the vendor directly, outside the base URL (the
  allowlist refused it), and the search tool declares a provider-side tool in a request through
  the base URL. The passthrough refuses any request that declares such a tool.
- **The egress log is kept** by following the sidecar's log while it lives. It names a refused
  connection by address and port, never by the name asked for, so a scan of it is a scan of
  addresses: it shows that an attempt tried to leave the list, how often and toward which
  addresses, not what was asked. The transcript scan (D6) covers names and content, since the
  agent's commands and their output are there. Neither sees what an allowed host served beyond
  what the transcript prints.
- **Cannot be enforced:** what the model remembers (the vendor's help page gives a training
  cutoff of June 2026, read through a search result; the tasks were published in August 2026
  with a canary string); content on an allowed host, since package indexes can hold anything;
  name lookups and ping, which the sidecar's rules let through (source read, not probed).

### D4. Credential, metering, price and the ceiling

**The credential route.** Three facts decide it. The harness puts the agent's container in the
sidecar's network namespace, and leaves a service from an extra compose file alone when that
service declares its own network (source). Allowlist entries carry no port, so a listed
address is reachable on every port (recorded). The proxy dials a listed name itself (recorded).

| Route | Where the key is | What the agent can reach | Verdict |
| --- | --- | --- | --- |
| The host's address on the allowlist (the plan as accepted) | A host process | Every port of the host | Rejected: the recording shows ssh reached |
| A. The passthrough as a container on the attempt's network, the key bind-mounted as a file | One container boundary from the agent, in every attempt | That container's one port | Workable; not chosen |
| **B. A relay container on the attempt's network; the passthrough stays one host process** | **Only in the host process** | **The relay's one port, which forwards to one unix socket** | **Chosen** |

- **Route B.** An extra compose file adds a service `relay` with its own network declaration,
  from an image pulled by digest. It listens on one TCP port and forwards every connection to
  a unix socket, bind-mounted into the relay alone; the passthrough listens only on that
  socket, on the host. The agent's base URL names the relay and the allowlist lists the name
  `relay`. The relay holds no key, no token table and no logic, and the host opens no TCP port.
- **Why B over A.** The key never enters a container, so it cannot appear in a container
  command, a process list or the harness's exception text, which quotes the container command
  with its environment (recorded; the key was absent there only by truncation). One process
  keeps one meter and the one USD 200 total; A delivers the key and shares that state in every
  attempt. B gives up one thing: a flaw in the passthrough's request handling would be reached
  on the host, not inside a container.
- **In the agent's container:** the base URL and a per-slot dummy token, both visible in
  process lists and exception text. The token is random, valid for one open slot, and worth at
  most that slot's cap on the bound model.
- **What the agent can still reach:** the relay's port; the package indexes and mirrors; name
  lookups and ping; the sidecar's own namespace. Not the host, and not the vendor's API.
- **Still to probe** (Task 2, no spend): the harness and podman-compose accept the extra
  service and leave it outside the sidecar's namespace; the agent reaches `relay` by name
  through the proxy; the socket mount works under rootless Podman; the verifier's environment
  has no relay. If B fails, and neither a fixed address on the attempt's network nor route A
  passes the same probes, the plan stops before spend.

**The passthrough** is a small host-side process, part of the kit and of the pre-spend review.
For every request it maps the dummy token to a slot and refuses an unknown one; refuses any
model other than `claude-haiku-5-5`, any request that declares a provider-side tool, and any
path but the messages path (the only one recorded); refuses when the slot's metered spend has
reached its cap, when all slots together have reached USD 200, or when the tranche is stopped;
prices the response's usage with the frozen table and appends it to the slot's log. How the
CLI ends after each kind of refusal is not recorded yet (Task 4).

- **Price table:** `orchestrator/providers/price_table.json` at the frozen commit, by SHA-256.
  The CLI's own cost equals the table on small recorded requests and on a 990,000-token prompt
  (five times the base rates, input and output; recording `context-late-low`). On the three
  public archives the table gives 1.05 to 1.11 times the CLI's figure: the rule for when the
  long-prompt rate applies is not pinned. Task 2 settles it by pricing the archives' rows
  request by request under each candidate rule; the rule that reproduces all three totals to
  the cent is frozen, with the vendor's pricing page read beside it. Until one does, the table
  stands as an upper figure and the readout prints both it and the CLI's.
- **Per-attempt cap:** `max(3.00, 3 × the task's public mean cost per trial at effort max)`
  (the table in D1), the same at every effort, enforced by the passthrough and by the CLI's own
  budget limit. **Each guard acts one response late:** the CLI stops after the response that
  crosses the cap, without running the tool call in it (recording `budget-medium`), and the
  passthrough refuses the next request. With three tools there is one request in flight at a
  time, so the overshoot is one response.
- **Reservation before every attempt:** the cap plus USD 1.00, which covers one response of the
  largest output (128,000 tokens, USD 0.32 at the long-prompt rate) and a freshly cached prompt
  of about 680,000 tokens. Under one lock the launcher computes *committed* = settled cost of
  every start + every open reservation, and launches only if *committed* + reservation ≤
  200.00 and starts < 240.
- **Settlement** replaces a reservation with the largest of four figures, read by these rules:
  1. the passthrough's meter;
  2. the session file's rows priced by the table, one row per message id (a message's usage is
     repeated once per content block);
  3. the result event's `total_cost_usd`;
  4. the result event's `modelUsage` priced by the table.
  The result's `usage` is never read (all zeros at a budget stop, while figures 3 and 4 are
  right), nor are stream events (they carry only the count at the start of a message). A
  timeout kill leaves no result event, so figures 1 and 2 settle it. Subagent rows would sit in
  a separate file; none exists in this configuration, and one is a stop. Unreadable usage
  settles at the full reservation.
- **What ends the tranche:** nothing in flight and the next slot's reservation does not fit; 240
  starts; a stop rule of D7. The launcher never skips ahead to a cheaper slot.
- **Expected spend (planner's estimate):** about USD 173 for all 240 (low 33, medium 53, high
  87), from two public cost points (report §9); plausible range 145 to 255.

**Worst case when one guard fails** (list-price dollars):

| Guard that fails | Bound |
| --- | --- |
| The CLI's budget limit does not stop a session | The passthrough refuses at the cap: USD 200 plus one response per open slot |
| The launcher's reservation | The passthrough's own total stops at USD 200 |
| The passthrough's meter under-counts | The launcher's reservation and the CLI's limit still hold; if both fail too, four sessions run to their natural end, about USD 260 to 330 |
| The relay or the allowlist lets the agent out | No key is in reach; the loss is the network policy, not money |
| The price table is wrong | The bill differs from every meter by the error |
| A process of this host user reads the key file | No bound in the kit |

The last two rows make the workspace's own spend limit a precondition (owner question 1). **The
passthrough cannot stop:** the response in flight when a cap is reached; spend inside a slot's
cap that is not the session's own (a direct request with the dummy token: metered and capped,
but absent from the session file); a wrong price table; another process of the same host user
reading the key file.

### D5. Infrastructure failure against model failure

**A session has started** when its stream holds an init event; every recorded session emitted
one before its first request. The ending is read from the result event's `terminal_reason`,
`is_error`, `api_error` and `stop_reason`, with the harness exception class as a second key.
`subtype` decides nothing: it is `success` for refusal, output-limit and context-limit endings.
The class alone decides nothing either: a context-limit ending and a budget stop share one.

| Ending | Recorded fields | Harness class | Fixture | Class of outcome |
| --- | --- | --- | --- | --- |
| Normal | `terminal_reason: completed`, `is_error: false`, `stop_reason: end_turn` | none | `public-normal-end`, `stub-simple-mode-normal-end` | Observation |
| Dollar cap, by the CLI | `terminal_reason: budget_exhausted`, `is_error: true` (`subtype: error_max_budget_usd`) | `NonZeroAgentExitCodeError` | `stub-budget-stop-NonZeroAgentExitCodeError` | Observation, flagged |
| Refusal | `terminal_reason: api_error`, `is_error: true`, `stop_reason: refusal`, after a `model_refusal_no_fallback` event | `AgentSafetyRefusalError` | `public-refusal-…`, `stub-refusal-…` | Observation, flagged |
| Output limit | `terminal_reason: api_error`, `is_error: true`, `api_error: max_output_tokens` | `OutputTokenExceededError` | `stub-output-limit-…` | Observation, flagged |
| Context limit | `terminal_reason: prompt_too_long` or `blocking_limit`, `is_error: true` | `NonZeroAgentExitCodeError` | `stub-context-limit-…`, `stub-context-limit-after-compaction-…` | Observation, flagged |
| Time limit | no result event | `AgentTimeoutError` | `stub-timeout-AgentTimeoutError` | Observation, flagged |
| Before a session | no stream at all | `RuntimeError` | `pre-session-agent-install-…`, `pre-session-network-switch-…` | Pre-session failure |
| Provider fault (rate limit, overload, server error, lost connection) | **not recorded** | not recorded | none yet (Task 2) | Infrastructure failure, once recorded |
| The passthrough refused (cap, total, stop, model, tool) | **not recorded**; read from the passthrough's own log | not recorded | none yet (Task 4) | Cap: observation, flagged. Total or stop: infrastructure failure. Model or tool: a stop |
| The host, Podman, the passthrough or the launcher died | no result event and no harness result | none | none (launcher's own record) | Infrastructure failure |

- **What each class means.** An *observation* counts against the 240 and the USD 200 and
  enters k and n with the verifier's reward, 0 if the verifier gives none; the verifier ran
  after a timeout kill (recorded). An *infrastructure failure* counts against both and is
  excluded from k and n, listed, never scored zero. A *pre-session failure* counts against
  neither; the slot is relaunched at most twice and is lost after the third failure.
- **An ending that matches no row pauses the launcher** for a recorded ruling. Today that
  includes every `api_error` ending that is neither a refusal nor an output limit: the
  provider-fault rows are frozen only from recordings.
- **Model-side endings are never excluded:** they are the longest and dearest sessions and
  come mostly from the higher efforts. **The agent is never run twice for one slot,** so a
  retry cannot turn a model failure into a pass.
- **Verifier-only regrade** (no model call, the saved artifacts unchanged), in two cases. (1)
  No reward after a normal ending: up to two regrades below the load gate; a reward then
  stands; a verifier timeout twice is reward 0; still no reward file is an infrastructure
  failure. (2) A task on the load-sensitive list returned reward 0 while the load was above the
  gate during verification: one regrade below the gate, and its reward stands. Only a reward of
  0 is regraded, because the known defect of such a verifier under load is a false failure. If
  the harness cannot regrade on Podman, case 1 becomes an infrastructure failure and case 2 is
  excluded as "indeterminate".

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
- **Graded outcome, secondary (roadmap Phase 5b, "Making fitness cheaper to measure").** Where
  a task's verifier reports sub-tests, each observation also records passed and total. It is
  printed per task and effort beside k of n, places no task and enters no test above. Task 2's
  oracle runs establish which verifiers expose it and in what form (Task 1 did not record it); a task without it prints
  "pass or fail only".
- **Adaptive order: rejected.** Running `high` first and skipping the lower levels of a task at
  0 of 5 assumes the thing under test and removes the tasks where a violation would show;
  leaving those tasks out instead keeps tasks selected for success at high.
- **Contamination scan:** over transcripts, for specific strings frozen after a dry run on the
  oracle jobs and the recordings (the benchmark repository's path, the canary's identifier, the
  reference solution's full path in that repository). A hit excludes the attempt and is
  listed. The egress log adds, per attempt, the refused addresses and their count (D3); a
  refused connection fetched nothing and excludes nothing. A readout that ends in a stop prints no placement.

### D7. Order and stop rules

1. **Smoke:** one attempt, gsea-proteomics at `low` (cheap, short, and it needs a package
   index). Then stop and read, each check against a recorded form: the init event reports CLI
   2.1.311 and exactly the tools `Bash, Edit, Read`; the passthrough saw only the bound model,
   only the messages path and no provider-side tool; each request carries the bound effort; the
   cap is on the session; the egress log shows no connection outside the list except refused
   ones; the three table-priced settlement figures agree within 1%, and their ratio to the
   CLI's own figure is recorded; the verifier returned a reward; no key is in any container,
   kept file or command line; the slot settled. A pass makes it slot 1 of round 1. A kit change
   after it means a new manifest hash and ledger row; the start stays counted and is excluded.
2. **Rounds.** Five rounds, each one attempt of every task at every level (48 slots), in an
   order fixed by a hash of a frozen seed, the round, the task and the effort. A stop for money
   leaves the cells balanced, and effort is not confounded with time of day or load.
3. **Stop and read after round 1:** classification counts, cost per effort against the
   estimate, the scan, the load record. The projection goes in the ledger; no threshold moves.
4. **Stops:** a failed smoke; a response with non-zero usage that names another model; an init
   event with another CLI version or tool list; a subagent file; a passthrough refusal for
   model or tool; infrastructure failures above 10% of starts (from 20 starts on) or above 20%
   at one level; five pre-session failures in a row or 24 in all; contaminated attempts on
   three tasks; a key's value in a kept file; under 20 GB free. **Pauses:** the load wait of D2;
   the passthrough down; an ending that matches no row of D5.
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
Also in step 7, at no spend: every failed attempt's transcript is labelled process (lost track
of the task, stopped early, did not verify, broke earlier work) or capability, by a fixed
rubric written before the transcripts are read and applied by two readers; `family.json`
carries the counts per task. The staged comparison of step 9 is read per label, since a
structure can repair a process failure and not a capability gap. Tasks with a sub-test count
are marked, for a later graded fitness.

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
`claude-haiku-5-5`, same container, limits, network policy and tool configuration: a direct session at the task's
band effort, in fresh runs (the ladder's runs chose the tasks), and the seed with every role at
that effort. The bar is the direct arm's re-roll curve `Q(k*)`, `k*` being the seed's mean
priced cost over a direct run's: a seed that costs eight direct runs must pass about 83% of the
time where direct passes 20%, so the most likely outcome is a null against re-rolling. Smallest
useful size: ten tasks, 8 direct and 4 seed runs each, which detects about 32 points (twenty
tasks, about 21; the seed design's computation on its own assumed rates). Rough cost: about
USD 170 to 440, after a measure-free smoke of two seed runs (about USD 15), and excluding any
ladder for added tasks. Open design work, larger than one line: how a workflow's steps run
inside a task container, and what the seed uses as its visible check, since the tasks ship none.

**Owner direction for step 9 (2026-11-13): "code quality is compounding and matters".** A task's
verifier scores pass or fail at the end and does not see the quality of what was built; on a
long task, later work builds on earlier work, so quality early can decide cost and success
later. Step 9's design therefore reports two things beside the pass rate, and a null on pass
rate against re-rolling is not by itself the answer:
- a blind quality rating of the final repository (the functional rubric of the experiment
  rules, with a judge qualified by its own predeclared check on natural controls before any
  rating is read; that qualification is separate spend to be sized in the request);
- a compounding measure inside the staged arm: with the milestone reviewer present and absent,
  the priced cost and the refusals of each later milestone, and whether the final check passes.
  Earlier studies here measured review on one change (a small gain with a stronger reviewer on
  an easy bug, none on a harder task scored by hidden tests) and could not see compounding.
Step 9 also records, at each stage boundary of the staged arm, the visible check's pass
fraction and the agents' typed verdicts beside the final verifier result, and reports how well
each predicts the end (roadmap Phase 6, readiness item R1 stops candidates only on a signal
that does).
The re-roll bar above stays as the pass-rate comparison: it is best-of-k direct sessions with an
ideal selector, which no real selector reaches, and the request says so.

## Tasks

Branch `feat/lh-ladder` from `feat/long-horizon-recordings`, in its own worktree; kit under
`experiments/long_horizon_tasks/`, tests in `tests/experiments/test_long_horizon_ladder.py`,
each failing first for its stated reason. Every command has the blocking provider stubs first
on `PATH`. The order stands: the relay probe sits in Task 2, before the criterion, and the
passthrough before the launcher.

### Task 1: recordings (done 2026-11-13, no spend; 8 h)

On `feat/long-horizon-recordings`: `stub_api.py`, 17 local recordings of CLI 2.1.311, three
public trial archives, 15 fixtures, and the assumption table this revision applies. Left open:
the endings were recorded with twenty tools (only the normal end with three); provider faults
and the verifiers' sub-test forms were not recorded.

### Task 2: pin, probe and qualify the 16 (impl_code; 12 h plus about 10 h of machine time)

**Files:** create `tasks.json` (name, 4.1.0 digest, overlay digest, cap, extra hosts, oracle
evidence) and `relay-compose.yaml`; modify `oracle_check.sh` (repeats, the two-key overlay, the
CPU set, the load gate), `stub_api.py` (fault scenarios) and `summarize.py` (counts).

- [ ] The sub-id range is widened first, with no container running (owner question 3). The 16
      are fetched at the 4.1.0 digests; any mismatch with the copies checked is recorded.
- [ ] The relay route (D4), with the `oracle` agent: the extra service is accepted and stays
      outside the sidecar's namespace; `relay` is reached by name through the proxy and
      forwards to the socket; no host port answers; the verifier's environment has no relay.
- [ ] Recordings in the three-tool configuration: the endings of Task 1 again, and provider
      faults (rate limit, overload, server error, a dropped connection). A fixture that differs
      replaces the old one.
- [ ] The affinity reaches both containers. Oracle and do-nothing runs, five each, under the
      final policy, four at a time; they also show which verifiers report sub-tests.
- [ ] A dry run of the contamination terms over these jobs and the recordings, then the terms
      are frozen. The long-prompt price rule is settled as D4 says, and the archives give the
      model's real prompt limit.

**Verify:** `python -I experiments/long_horizon_tasks/summarize.py <jobs>` prints, per task,
reference 5 of 5 and untouched 0 of 5; the ledger gets the surviving list.

### Task 3: criterion and manifest (impl_code; 3 h)

**Files:** create `ladder.json` (model, efforts, CLI version, the two configuration variables,
harness versions and host-side overrides, digests, caps, ceiling, schedule seed, allowlist, CPU
set, load gate and wait, the D5 table with the fixture each row cites, readout rules, scan
terms, price rule and table hash) and `manifest.json` (SHA-256 of every kit file). Tests: caps
follow the formula and are equal across efforts; every field and value a frozen rule matches
occurs in a fixture.

### Task 4: the passthrough and the relay (impl_code; 10 h)

**Files:** create `passthrough.py`. Tests, with `stub_api.py` as the upstream:

- [ ] It listens on a unix socket only. It refuses an unknown token; a model other than the
      exact id (Sonnet, Fable, an alias); a request that declares a provider-side tool; a path
      other than the messages path; a request for a slot at its cap; any request once the total
      reaches USD 200 or while the tranche is stopped.
- [ ] Its meter prices streamed and plain responses by the frozen rule; a response in flight at
      the cap is metered to its end; the key appears only in the upstream request.
- [ ] The passthrough going down pauses the tranche.
- [ ] Recorded with the real CLI through the relay: how a session ends after each kind of
      refusal. Each gets a fixture and its row in D5.

### Task 5: the launcher (impl_code; 16 h)

**Files:** create `ladder.py`. **Interface:** `ladder.py plan | launch | status`. A paid launch
needs `LH_SPEND_AUTHORIZED=yes`, `LH_MANIFEST_SHA256` and `LH_RUNTIME_COMMIT` (both from the
ledger); the key file is named only to the passthrough, and the harness's environment holds no
credential. A rehearsal needs `LH_REHEARSAL=<dir>` and refuses if a spend variable is set.
State lives outside the checkout (`$HOME/.local/state/lh-ladder`; another root for
rehearsals): one directory per slot, claimed by `mkdir`, with the reservation, the dummy token,
the launcher's pid and start time, and later the settlement. It runs from a detached checkout
of the frozen commit and reuses the package's usage reader and price table.

Tests, against a stand-in harness that replays the recorded fixtures on a closed `PATH`:

- [ ] Refusals: no authorization; a manifest or runtime commit other than the ledger's; a dirty
      kit; a model or effort outside the criterion; a task whose digest differs outside the two
      overlay keys; another harness environment or a missing host-side override; an allowlist
      that names an address of the host; a rehearsal with a spend variable.
- [ ] Money: sixty concurrent launches never commit more than the ceiling; a slot that does not
      fit waits and is never skipped; start 241 is refused; settlement takes the largest of
      four figures, never reads the result's `usage`, and counts a message id once; unreadable
      usage settles at the full reservation.
- [ ] Classification over every fixture, by the fields of D5: a budget stop and a context limit
      of one harness class are told apart; an ending with no row pauses. A slot whose session
      started is never launched again; a slot is lost after its third pre-session failure; a
      regrade never starts the agent; reconcile stops only the containers of a dead launcher
      (pid and start time both match).
- [ ] Host: the load gate waits, and pauses after two hours with nothing in flight; low disk
      stops the tranche; the egress log is followed out before teardown; the harness command
      carries model, effort, version, cap, the two configuration variables, the relay's base
      URL and zero retries; no key is in any file, environment or command line; the schedule is
      deterministic, balanced, begins with the smoke slot, and waits for the round-one read.

**Verify:** `pytest -q tests/experiments/test_long_horizon_ladder.py`, `--collect-only` on it,
then the sampled broad check.

### Task 6: the readout (impl_code; 7 h)

**Files:** create `readout.py`. Tests: intervals match the report's table; cell and pooled
labels; the band effort is defined for every screened-in pattern; the effort verdict and the
bound on the fall on constructed tables; a ceiling stop leaves partial rounds out of complete
triples; exclusions are listed and never scored zero; the graded outcome is printed and enters
no rule; a stop readout prints no placement; `family.json` names the criterion and the digests.

### Task 7: zero-spend rehearsal (impl_code; 6 h)

- [ ] In the suite: the whole schedule against the stand-in harness, ending inside both caps.
- [ ] On containers, with no key on the machine: three tasks with the real pinned CLI in the
      three-tool configuration, the relay, the passthrough, and `stub_api.py` as its upstream.
      One session runs to a budget stop, one past a shortened time limit, one is killed and
      reconciled, one verifier is regraded.

**Verify:** the D7 smoke checks on the rehearsal's records; a dummy key value in no container,
file or command line. Results go in the ledger.

### Task 8: independent pre-spend review (review_code; 4 h, plus 6 h of fixes and re-review)

By a reviewer who wrote none of the kit; the passthrough and the relay are in scope. Its brief
lists the holes earlier reviews and the recordings found: a retry that turns a failure into a
pass; a CLI that updated itself after the pin; a sweep that matched a reused pid; a launch
between reservation and record; a runtime commit recorded but not enforced; a rule written for
output nobody had observed; an identity check the overlay defeats; a credential an agent can
reach; an allowlist entry that opens a whole host. Each guard is mutated.

### Tasks 9 to 12: freeze (1 h), smoke (2 h), the run (6 h of attention), readout and step 7 (12 h)

Before the first attempt the ledger holds: the surviving tasks with task and overlay digests;
the manifest hash and runtime commit; the CLI and harness versions; the price rule and table
hash; the network policy; the workspace limit and rate-limit tier as read in the console; the
quiet window; the review verdict; the rehearsal result; spend to date 0. The run needs about 35
to 45 hours of a quiet host at four concurrent attempts, up to about 60 when its own load holds
it to two or three; it runs in tmux. The last task writes `results/readout.md`, `family.json`,
a report under `docs/reports/`, the actual spend in the ledger, and the roadmap's step table;
8 of its 12 hours are step 7's failure labels by two readers.

**Hours in all:** about 93 of engineering and review, 85 of them still to do (79 before the
recordings: the relay probe and fault recordings add 2, the criterion 1, the passthrough and
relay 2, the graded outcome 1, the failure labels 8), plus machine time.

## What This Makes Harder

- The family is tied to one benchmark, harness and CLI version, one network policy and the
  three-tool configuration; a later comparison must reuse all five or re-qualify, and step 9
  must say which tools its staged arm's sessions get. The allowlist ends comparability with the
  public leaderboard.
- The passthrough and its relay are reviewed code that every later long-horizon run needs. Reservations far
  above expected cost leave the last USD 10 to 25 unusable, and "no agent retry" means provider
  incidents reduce n for good.
- Task files and recordings live outside the repository: a clean clone fetches them by digest.

## Not Verified While Planning

**No longer listed here,** because a recording now shows it and D2 to D5 cite it by name: the
allowlist under rootless Podman, setup on the open network, the egress log, the misrouted
request, the CLI's install and version, the budget stop's form, model pinning, the verifier
after a timeout kill, and the separability of pre-session failures.

**Before the launcher is written** (Task 2 unless stated; several were opened by the
recordings):

1. The relay route: the four probes of D4.
2. Endings in the three-tool configuration, and provider-fault endings, which no recording
   shows. How a session ends when the passthrough refuses (Task 4).
3. The long-prompt price rule, and the model's real prompt limit, from the archives.
4. The console's spend limit is hard and prompt; the rate-limit tier; the training cutoff on
   the vendor's page itself.
5. The contamination terms give no false hit on the oracle jobs and the archives.
6. The host plan: the affinity reaches both containers; the quiet window; the sub-id widening.
7. Task content equals the 4.1.0 digests; which verifiers report sub-tests.

**At the rehearsal:** the verifier runs after a budget stop on Podman; a regrade on Podman; kill
and reconcile; no key in any container, file or command line.

**At the smoke or in round 1:** `low` and `medium` are accepted for this model at the real API
(the stand-in accepted all three; only `high` was seen against the vendor); cost per effort
(`low` and `high` are interpolated); provider errors at four concurrent sessions; image builds
stay reproducible over days.

**Not probed:** the sidecar's handling of name lookups and ping (source read); the benchmark's
licence beyond its text (Apache-2.0, with a canary asking that data stay out of training sets).

## Rulings

The planner's eleven rulings, adopted with the reviewer's amendments (2026-11-13), are the
rules of D1 to D7; the coordinator's rulings of both revisions are in the ledger. All thirteen
review minors are applied; minor 8 (the training cutoff) rests on a search result until the
vendor's page is read in Task 2.

## Owner questions

Only what the approval does not cover.

1. **One API key,** in a workspace with a spend limit of USD 200, readable only by the
   passthrough on the host; it enters no container. This is billed API usage, not the
   subscription, and would be the project's first. Will the owner create it, and confirm in the console that the limit is hard and what
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
| 2026-11-13 | Plan accepted by the coordinator | The review's blocker and six majors are applied (all thirteen minors too). Confirmed readings: a budget stop, a refusal or a context-limit ending is an attempt and takes the verifier's reward (0 only when the verifier gives none); the two-hour load-wait clock runs only while no attempt is in flight. Acceptance covers the plan, not spend: the first attempt still needs Tasks 1 to 8, the owner's answers to questions 1 and 2, and the ledger rows of Task 9. Tasks 1 and 2 (recordings and probes, no spend) may start. |
| 2026-11-13 | Second revision, against the recordings of Task 1 (no spend) | Coordinator rulings applied: the ladder runs the public row's three-tool configuration (`CLAUDE_CODE_SIMPLE=1`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`) on CLI 2.1.311 and measures that configuration, not the default agent; the host's address is never allow-listed (it opened every host port), and the passthrough is reached through a relay container that forwards one port to one unix socket, the key staying in one host process (route B of D4; four probes outstanding, no spend if they fail); D5 is rebuilt row by row from recorded fields and fixtures, with provider-fault and passthrough-refusal endings still to be recorded; settlement rules follow the recorded forms (one row per message id, never the result's `usage`), each cap guard acts one response late and the USD 1.00 margin covers it; the long-prompt price rule is unpinned (the table gives 1.05 to 1.11 times the CLI's figure on the archives) and is settled in Task 2; the egress log names addresses only; the `-T` flag, the containers override and the harness wrapper are host-side parts of the method; the version evidence is the init event. Hours: about 93 in all, 85 still to do. Spend to date: 0. |
| 2026-11-13 | Second revision accepted by the coordinator (`a4674efa`), after Task 1 and the two Task 2 probes | The recordings (CLI 2.1.311 in a task container against a local stub; no credential, a dummy key, the vendor API refused before the first run; no spend) contradicted assumptions of D2 to D5, and the plan now follows them: the three-tool configuration of the public trials; classification on `terminal_reason`, `is_error` and `api_error`; settlement de-duplicated by message id; the key in no container (a relay container forwarding to a unix socket of the one host passthrough, because allow-listing the host's address opened every host port to the agent). Still open before the launcher is written, all without spend: the relay route's four probes, the endings re-recorded with three tools, provider-fault and passthrough-refusal recordings, the long-prompt price rule. One incident, no damage: the planner's branch command ran once in another worktree (`.worktrees/coh-c1`) and was reversed at once; the coordinator checked that worktree's branch, tip and status and reran its changed tests. |
