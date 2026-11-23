# Long-Horizon Task Family And Staged Seed Plan (Roadmap Phase 5b)

**Status: Plan; third revision (2026-11-13), after owner decision 18 (subscription only) and the
no-spend probes of Task 2; independently reviewed and accepted by the coordinator on 2026-11-13
(`96adb33d`). In execution: Tasks 1 to 8 and the second oracle pass are done, and the ladder
runs the 15 tasks that qualify unchanged (D1). The live probe (Task 4) ran on 2026-11-17: 3 requests,
priced USD 0.0017, taken as passed (ruling LH-R2). Owed before the ladder's freeze: the round's
whole-file-set read of D4 and the probe's setup-timeout multiplier (in review), and which meter
governs the token (read again at the smoke slot's first request). Not yet run: the freeze, the
smoke, the pilot and the ladder. The [ledger](#ledger) holds each step.** The kit's
[README](../../experiments/long_horizon_tasks/README.md) says how it is operated. This
page
turns the staging of
[roadmap Phase 5b](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed)
into a plan: the effort ladder that owner decision 16 approved (steps 4 to 6), and steps 7 to 9
in outline. The roadmap owns the direction. `AGENTS.md` ("Experiment rules") owns the approval
and its limits. The [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
owns the dominance and cost rules. The
[survey and feasibility report](../reports/2026-11-13-long-horizon-benchmark-survey-and-feasibility.md)
holds the evidence cited here as "report §n"; recordings are cited by name, as listed in
`experiments/long_horizon_tasks/recordings.json` and explained in `RECORDINGS.md` beside it.
This plan owns its task list, limits, thresholds and
readout. Its commands are for this machine and are not copyable examples. Spend is
authorized only as the [ledger](#ledger) records.

**Headline exit test (fails today):** `experiments/long_horizon_tasks/results/family.json`
exists, names its criterion and task digests, and lists the screened-in tasks with their counts
by effort and the effort verdict. After a stop no `family.json` is written; the stop readout
names the stop.

## Scope and approval

- **Approved (decision 16):** one calibration tranche: the 16 named Terminal-Bench 4 tasks, a
  direct `claude-haiku-5-5` Claude Code session at effort `low`, `medium` and `high`, five
  attempts each; at most 240 attempts, ceiling USD 200; no other model, no top-up after a null.
  First: the oracle check passes here, the network policy is fixed, the launcher has passed an
  independent review, and this plan and its ledger exist. Of the 16, the ladder runs the 15
  that qualify unchanged, so its schedule holds 225 attempts; the 240 stays the cap (D1).
- **Credential (decision 18): the owner's Claude subscription, and no API key.** Nothing is
  billed. **Every dollar figure on this page is a priced-token figure:** metered tokens times
  the price rule of D4. It caps and reports usage. The vendor enforces no spend limit for us;
  what it enforces is the subscription's usage limits, which the ladder shares with the owner's
  own sessions and with the coordinating session (D4, "Usage limits").
- **The live probe (Task 4) is not under the ladder's approval.** It is three short sessions
  on a scratch task, before the oracle check and without the launcher. Its authority is the
  budget delegation (`AGENTS.md`) together with roadmap owner decision 18, which names it,
  exercised by a coordinator approval row in this plan's ledger, written before the first
  request. Until that row exists it is not approved. Its priced usage is counted inside the
  USD 200, a conservative choice.
- **Three steps use the subscription before the tranche is scheduled:** the live probe; the
  smoke, one attempt; the pilot, three attempts (D7). The smoke and the pilot are four of the
  240 attempts and run through the reviewed launcher.
- **Owner preconditions** are listed in one place, [below](#owner-preconditions-and-questions).
- **Kind of experiment.** The family is oracle-scored and qualifies by the oracle check, with
  no judge. The ladder places tasks and measures how success responds to effort, under the same
  task, tools and limits at every level. It is not a calibration whose stronger arm must win.
- **A stated difference from the design.** The driver's rule for an oracle family is an oracle
  that accepts two structurally different correct submissions and rejects a broken one. This
  tranche applies the approval's rule (the reference passes, an untouched environment fails);
  the ladder's passing agent runs can supply the second correct submission before step 9.
- **Not approved:** the seed comparison (step 9), any benchmark task outside the 16, any other
  model. The probe's scratch task is no benchmark task and is covered only as the bullet above
  says. No claim about any workflow comes from this tranche. "Better" below always means Pareto
  dominance over quality and priced-token cost.

## What this size can and cannot support

- **What is measured: the Claude Code CLI as a subscription user runs it, held to three
  tools.** The session authenticates with a subscription token, keeps the CLI's default system
  prompt, and has the tools Bash, Edit and Read because the other eighteen are disallowed (D2).
  It does not measure the default agent with its twenty-one tools. The tools that start
  subagents and skills are on the deny list; the init event still lists skills and agents.
  Task 2a found none of their distinctive names in the request text (`t2a-normal-low`): a
  judgement, since `verify` and `run` are both ordinary words and skill names.
- **It is not the public leaderboard row's configuration.** All 330 public trials ran in the
  CLI's simple mode with an API key: a system prompt of 26 characters where the ladder's has
  8,830, three declared tools where the ladder's requests declare a fourth (a placeholder), and
  five-minute caching where the ladder's is one hour. Simple mode refuses a subscription token
  (fixture `token-simple-mode-AgentAuthenticationError`), so the public configuration cannot
  run under decision 18. The public per-task rates are therefore only what chose the 16
  candidates. **The ladder's own measurement is the only evidence of difficulty,** and no
  figure of this plan is read against the public row.
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
  than ten, the smallest size step 9 can use. The likely effort verdicts are "rises" or "not
  resolved"; neither confirms decision 14's assumption beyond the bound the readout states.
- **These numbers are a weaker guide than when they were computed.** They rest on the public
  counts, and three things now separate the ladder from those counts: the configuration above,
  the allowlist, and the task content (seven of the 16 changed their verifier tests after the
  version the public row ran; D1). Which way each moves the rates is not known.
- **About 220 to 235 of the 240 starts are expected, and the last round is likely
  incomplete.** The ceiling ends the tranche once settled usage passes about USD 176 to 196,
  depending on the cap of the task that is next, and the estimate is about USD 0.76 to 0.80 a
  start (USD 182 to 192 for all 240; D4). Each attempt cut off by a usage limit also uses one
  of the 240 starts (D5). Which starts are dropped is fixed before the first attempt (D7).
  These figures were computed for 16 tasks. With the 15 that run (D1) the schedule holds 225
  slots, about USD 171 to 180 at the same estimate per start, so the schedule may end before
  the ceiling does; the estimate itself is not redone.
  The approval's request named about USD 170; that figure was for the public row's prices.
- **How long it takes is not known before the pilot.** The tranche runs only as fast as the
  owner's share of the weekly allowance lets it (D4, D7).

## Decisions frozen before spend

**No frozen rule may name a string, key or value that no recording shows.** The classification
table, the stand-in responses, the smoke checks, the stops and the scan terms are written from
the recordings of Tasks 1 and 2, and a test holds each to a recorded line. Most of those
recordings were made in the public row's configuration. Task 2a records the ladder's own, and
nothing is frozen before it: where a rule below rests on a recording of another configuration,
it says so.

### D1. Task list and task identity

A task is **the same task** when every file of its package equals the benchmark's published
4.1.0 digest, with `task.toml` compared after removing exactly two keys: the agent phase's
network mode and its allowed hosts. The launcher writes those two keys (D3); their digest is
recorded per task and per attempt. All 16 packages were fetched and match their 4.1.0 digests
(`tasks.json`).

- **Images: the ones 4.1.0 pins.** Each 4.1.0 `task.toml` names a prebuilt agent image and a
  prebuilt verifier image by digest. The ladder runs those, pulled by digest, and builds
  nothing. The oracle evidence so far (report §5) used images built here from the Dockerfiles,
  so it shows that the tasks can run on this machine and counts for nothing in the
  qualification rule below.
- **If the pinned images cannot be used as pinned** (Task 2b finds out, at no spend). If only
  the harness or podman-compose cannot take a digest reference, the image is pulled by digest
  with Podman and tagged locally, a host-side step; the local image id is recorded against the
  digest at every attempt. If rootless Podman cannot pull an image by digest at all, that
  task's image is built here from the package's Dockerfile. The record then says that the
  image is not the pinned one, and that is **a different configuration label** (D7), named in
  `tasks.json`, the manifest and the readout.
- **The disk is measured before it is planned for.** `/home` has 78 GB free (96% full), and
  the tranche stops under 20 GB. The 32 pinned images are pulled one at a time, each one's
  size in the store recorded and the image deleted, before anything else is pulled. From the
  sizes Task 2b states, in the ledger: the order of pulls (vba-userform-port first, then the
  schedule's order); what is kept between rounds; and the room left above the 20 GB stop with
  four attempts' output. If all 32 do not fit with that room, the owner decides (question 6):
  free space, name another disk for the image store, or let the launcher keep only the images
  of the blocks in flight and next in the queue, pulling by digest before and deleting after,
  which ties the tranche to the registry for its whole length.
- **Withholding is checked on every pinned agent image before any use.** The harness's
  withholding was shown on images built here; a publisher-built image holds whatever its
  publisher put in it. Each agent image's file system is exported from a container created
  with no network and never started. It is listed and searched, on the host, for the names and
  SHA-256 digests of the files under the task's `solution/` and `tests/`, and for the
  benchmark's canary string. The canary is searched for by its published identifier, read at
  run time from the task package; it is never copied into this repository, and the kit holds
  only its SHA-256. A hit drops the task; the result is recorded in `tasks.json`.
  The search also covers near copies: lines of 25 or more characters that the task's `solution/` or
  `tests/` holds and its `environment/` does not. Every text file of the merged file system is
  matched against them. One matched line needs a look, except in a system path or a language
  package directory (virtual environments included), where a file needs 10 or more. Archives and
  loose `.git` objects outside system and language paths are opened when 64 MiB or smaller and
  searched the same way; inside those paths they are neither opened nor listed (the intended scope).
  Text files over 64 MiB, which the line check does not read, are listed. Every layer of the image is
  walked too, deleted files included, by path and SHA-256 only. A canary found in a
  byte-identical copy of a file of the task's own `environment/` is not a hit (coordinator ruling,
  2026-11-14).
- **Host-side steps change no task file and are part of the method:** an image pulled by full
  name or a registry alias; a wider sub-id range; the harness wrapper, which lengthens the
  harness's probes and passes `-T` where the harness passes a flag podman-compose rejects
  (fixture `pre-session-network-switch-RuntimeError`); a containers override file that silences
  the compose banner (fixture `pre-session-agent-install-RuntimeError`); the relay's compose
  file (D4). Any other edit to a task file makes a **modified task**, admitted only as the vba
  row says. Task files, reference solutions and verifier tests stay outside this repository;
  the kit holds names and digests.
- **Seven tasks are not the tasks the public row ran.** The public trials ran 4.0.0. Nine of
  the 16 are identical in both versions. The other seven changed their verifier tests, and six
  of those also their agent environment (the column below). Instructions and reference
  solutions did not change. For these seven the public count and the public cost describe
  another verifier, so their cap rests on a cost measured on other content. The caps stand as
  frozen numbers all the same: a cap bounds an attempt and predicts nothing.

| Task | Oracle state on local builds (report §5) | Changed since 4.0.0 | Per-attempt cap, USD |
| --- | --- | --- | --- |
| vba-userform-port | Fails unchanged | Tests, environment | 14.19 |
| vf2-speedup-networkx | Not tried | No | 17.37 |
| wal-recovery-ordering | Reference 1 of 2 under load | Tests | 3.00 |
| session-window-debug | Pass, once | Tests, environment | 3.00 |
| production-planning | Pass, once | No | 3.93 |
| vpp-loss-divergence | Not tried | No | 9.78 |
| batched-eval-parity | Not tried | Tests, environment | 6.09 |
| pretrain-shard-corruption | Not tried | Tests, environment | 3.00 |
| gsea-proteomics | Pass, once; needs a package index in the agent phase | No | 3.00 |
| lake-temp-glm | Pass, once | Tests, environment | 5.22 |
| sound-change-cascade | Pass, once | Tests, environment | 8.61 |
| hof-topology-interpenetration | Not tried | No | 7.14 |
| shadow-relay | Pass, once | No | 8.55 |
| rs-archive-clone | Pass, once | No | 22.92 |
| retro-console-soc | Pass, once | No | 17.70 |
| roy-polymorph-cn | Pass, once | No | 5.58 |

- **Qualification rule.** A task runs only if, on the 4.1.0 package and its two pinned images,
  under the final network policy, on the ladder's CPU set at its concurrency of four, with the
  load below the gate of D2, the reference solution earns reward 1 five times of five and the
  untouched environment reward 0 five times of five.
- **What of the oracle evidence is redone, and when.** All of it, in two passes (Task 2b).
  1. *First pass, on any day, load not controlled:* after the disk measurement and the
     withholding check above, each of the 16 once on its pinned images, reference and
     untouched, and the pinned CLI installed once on each pinned agent image (the install was
     recorded on one locally built image only). vba-userform-port goes first: its
     failure was seen on a local build, and the sub-id range decides whether it needs the
     labelled verifier change (owner question 4). A failure here is found before the quiet
     window is asked for.
  2. *Second pass, the rule above, in the quiet window:* five and five for every task, about
     ten hours of machine time. This is the only pass that qualifies a task.
  The seven changed tasks get no extra oracle run: the content checked earlier already was
  4.1.0's, and the pinned images are new for all 16 alike. What they do get is in the bullet
  above: their public figures are not used as an expectation.
- **A task that fails the rule and has no host-side fix is dropped.** It is not replaced and
  its 15 slots are not given to other tasks. Replacement from outside the 16 is owner
  question 5. A task whose reference passes five of five quiet but failed under load stays, on
  the load-sensitive list, frozen from the oracle evidence before spend.
- **The surviving tasks (Task 2b's second pass, 2026-11-15; coordinator ruling).** The ladder runs the
  15 tasks that pass the rule unchanged: vf2-speedup-networkx, wal-recovery-ordering,
  session-window-debug, production-planning, vpp-loss-divergence, batched-eval-parity,
  pretrain-shard-corruption, gsea-proteomics, lake-temp-glm, sound-change-cascade,
  hof-topology-interpenetration, shadow-relay, rs-archive-clone, retro-console-soc and
  roy-polymorph-cn (`tasks.qualified`). vba-userform-port is not among them: unchanged, its verifier
  writes no reward on this machine, and the launcher has no support for its labelled variant
  `vba-userform-port-uidfix`, which would be new launcher code needing its own review before the
  first paid call. The variant's result (5 of 5 and 0 of 5) stays recorded evidence in `tasks.json`
  and the ledger, labelled and never pooled. The cost: the schedule holds at most 225 attempts
  instead of 240 (240 stays the approval's cap, an upper bound), and the family one task fewer. The
  owner can bring the task back before the freeze by deciding question 4 (`podman system migrate`);
  the unchanged task must then pass the oracle check itself.

### D2. What an attempt is

- **The agent runs inside the task's agent container,** as the published harness runs its
  Claude Code agent (report §8): one non-interactive session with the task's instruction.
- **In token mode, with three tools by a deny list.** The harness starts the CLI on its
  subscription route (`CLAUDE_FORCE_OAUTH=1`): the CLI gets a fake token, an empty API key and
  the relay as base URL (D4). The harness passes `--disallowedTools` with the eighteen names of
  recording `tok3-normal`, and `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000`. Simple mode is not set.
  The init event then lists the tools `Bash, Edit, Read` and `apiKeySource: none` (fixture
  `token-three-tools-normal-end`). An init event with any other tool list is a stop: a deny
  list lets through whatever it does not name.
- **What this configuration carries that the public row's did not** (recorded, Task 2a): the
  CLI's default system prompt (8,830 characters against 26); a fourth declared tool, a
  placeholder for deferred tools; three more beta flags (ten against seven); one-hour caching
  of system blocks 2 and 3 and the last message block, dropped for five minutes after a
  response that reports paid extra usage or a very large prompt; `rate_limit_event` events in
  the stream. **The model sees** the system prompt, the placeholder tool, longer tool
  definitions (6,983 characters against 3,482), a system-role message of 887 characters and a
  second user block of 581 in the first request, a 49-character system-role message after
  every tool result, and a Bash tool that refuses a standalone `sleep` and tells the model to
  wait with Monitor, a tool the deny list removes (`t2a-timeout-low`; in simple mode the same
  call ran). Agents on long tasks wait on builds, so this is a difference in behaviour, and
  the readout's naming of the configuration (D6) lists it.
- **Effort stays equal within an attempt.** The deny list names the agent tool, which let a
  session at `low` run a subagent at `max` (recording `subagent-override-low`). A subagent file
  is a stop (D4).
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
  their effect, so none is set. **The passthrough's model check is the only thing that binds
  the model:** a subscription token is good for every model of the account, so the passthrough
  refuses any other model before it forwards anything, and no credential enters any container
  (D4).
- **The CLI's own retries are inside the attempt** and are metered: one after a refusal, three
  after an output limit, one compaction attempt before a context-limit ending, up to ten after
  a provider fault (recorded). The CLI's switch that makes a session wait out a usage limit is
  not set: a session that meets a limit ends at once (D5).
- **Harness and limits:** Harbor 0.25.0 and podman-compose 1.6.0 from a pinned environment,
  one harness run per attempt, its retry count at zero, its agent setup timeout multiplier 3, taken
  from the recordings (the 33 Task 2a recordings of the CLI used 3; the two Task 2a oracle probes
  set none). Equal at every effort level: the task's
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
- **Concurrency:** one for the smoke, three for the pilot, then four (D7); fewer whenever the
  allowance guard of D4 leaves room for fewer. The ladder's own containers count toward the
  load gate, so it will often run two or three.
- **Withheld:** `tests/` and `solution/` never enter the agent's container, and the verifier
  image receives only the declared artifacts. Two checks: the harness's construction, in the
  rehearsal; and what the publisher built into each pinned agent image, for all 16, before any
  use (D1).

### D3. Network policy

- **The agent phase runs on an allowlist,** written as the two `task.toml` keys of D1, because
  the reference solutions are public and with open internet a pass may mean the agent found
  the answer. It works under rootless Podman with the wrapper's fix: an allowed package index
  answered, a code host and the vendor's API were refused, and image build and agent setup ran
  on the open network before the switch (recording `probe-oracle`). Verifiers keep what they
  declare. The rates are not comparable with the public row's on any axis (the size section),
  and the later comparison must use the same policy.
- **The list,** the same for every task and effort: the relay of D4, by name; the Python, Node
  and Rust package indexes; the system package mirrors of the three base distributions. A task
  that needs another host gets it by name in `tasks.json`. **The host's own address is never
  listed.** Entries carry no port, and when the host's address was listed the container reached
  the host's ssh port as well as the intended listener (recording `probe-oracle`).
- **A request that names an allowed host but is sent to another address goes to the named
  host:** the proxy dials the name itself (two misrouted requests both reached the package
  index). The earlier plan listed this as unenforceable; it is enforced.
- **Web tools are absent:** under an allowlist the harness itself disallows both, and the init
  check of D2 would show one. Recorded with them on (`web2-low`): the fetch tool contacts the
  vendor directly, outside the base URL (the allowlist refused it), and the search tool
  declares a provider-side tool in a request through the base URL. The passthrough refuses any
  request that declares such a tool.
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

### D4. Credential, usage limits, metering, price and the ceiling

**The credential route.** Three facts decide it. The harness puts the agent's container in the
sidecar's network namespace, and leaves a service from an extra compose file alone when that
service declares its own network (source; probed). Allowlist entries carry no port, so a
listed address is reachable on every port (recorded). The proxy dials a listed name itself
(recorded).

| Route | Where the credential is | What the agent can reach | Verdict |
| --- | --- | --- | --- |
| The host's address on the allowlist (the plan as first accepted) | A host process | Every port of the host | Rejected: the recording shows ssh reached |
| A. The passthrough as a container on the attempt's network, the credential bind-mounted as a file | One container boundary from the agent, in every attempt | That container's one port | Workable; not chosen |
| **B. A relay container on the attempt's network; the passthrough stays one host process** | **Only in the host process** | **The relay's one port, which forwards to one unix socket** | **Chosen; all four probes held** |

- **Route B.** An extra compose file adds a service `relay` with its own network declaration,
  from an image pulled by digest. It listens on one TCP port and forwards every connection to
  a unix socket, bind-mounted into the relay alone; the passthrough listens only on that
  socket, on the host. The agent's base URL names the relay and the allowlist lists the name
  `relay`. The relay holds no credential, no token table and no logic, and the host opens no
  TCP port.
- **Probed (recording `probe-relay-oracle` and later runs):** the harness and podman-compose
  accept the extra service and leave it outside the sidecar's namespace; the agent reaches
  `relay` by name through the proxy; all 39 listening ports of the host were refused at three
  addresses; the socket is mounted into the relay alone; the verifier's environment has no
  relay. Not probed: whether a verifier could reach the relay by its address.
- **Why B over A.** The credential never enters a container, so it cannot appear in a
  container command, a process list or the harness's exception text, which quotes the
  container command with its environment (recorded). One process keeps one meter and the one
  USD 200 total. B gives up one thing: a flaw in the passthrough's request handling would be
  reached on the host, not inside a container.
- **What the agent can still reach:** the relay's port; the package indexes and mirrors; name
  lookups and ping; the sidecar's own namespace. Not the host, and not the vendor's API.

**Token mode, and the three headers the passthrough sets.**

- **In the agent's container:** the base URL and a per-slot fake token, both visible in process
  lists and exception text. The fake token is the CLI's subscription token variable: a fixed
  prefix that says it is fake, then a random part; it is valid for one open slot and worth at
  most that slot's cap on the bound model.
- **The CLI sends `authorization: Bearer` with the fake token. The passthrough builds the
  upstream request from the client's and sets exactly three header values:** `authorization`
  (the real token), `host` (the vendor's host) and `accept-encoding` (`identity`, so that
  every byte of the answer can be checked for the token). `content-length` is the length of
  the body it read. Nothing else changes: not the other headers, not the ten beta flags of
  token mode (three more than simple mode's seven: `oauth-2025-04-20`,
  `mid-conversation-tool-changes-2026-07-01` and `extended-cache-ttl-2025-04-11`; a request
  after a paid-usage response or a very large prompt drops the last, and the compaction
  request also `claude-code-20250219`), not the body. A request outside the recorded shape is
  refused, not forwarded: the request line, the header names and the values of the recorded
  ones, the body's top-level keys, and each tool's name, its definition's keys and its
  `input_schema`'s top-level keys are held to an allowlist that `make_allowlist.py` builds from
  Task 2a's request fixtures (`fixtures/requests/t2a-*.json`, token mode). The key sets are the
  CLI's own, cut from its record of each request in the recording's session files; none is
  assumed. The placeholder tool's definition carries `defer_loading`.
  This is the route the CLI supports: a subscription token and a base URL.
- **Recorded for token mode against the stand-in** (`tok20-*`, `tok3-*`): the CLI honours the
  base URL and calls no other host or path; with the harness's setting that turns off
  nonessential traffic it makes no profile, usage, refresh or telemetry call; the result event
  has the same cost and usage fields as in key mode.
- **Rejected: key mode in the container, with the passthrough rewriting each request into a
  token request.** It would keep the public row's configuration. It also works around a
  restriction the CLI itself enforces (simple mode reads no subscription token), and whether
  the vendor accepts a request of that shape is unknown.
- **Not yet shown: that the vendor accepts this through the relay and the passthrough.** The
  live probe of Task 4 shows it before the launcher is built. If the route fails, the plan
  stops there: no other credential route is open under decision 18.
- **The real token** is created by the owner with `claude setup-token` and reaches exactly one
  process, by the path below.

**The token's path, closed by construction.**

1. **Creation, by the owner alone** (the exact steps are in owner question 1). A fresh
   terminal window that is not inside tmux: this session and its subagents capture tmux panes,
   and their transcripts are kept files. Not through this session's command prefix, and never
   pasted into any agent session or chat. The token is written by `install -m 600 /dev/stdin`
   into a directory of mode 700 that lies outside every repository and outside any synced or
   backed-up tree, so it is never on a command line or in the shell's history. The terminal's
   scrollback is then cleared and the window closed. The owner tells the coordinator the
   file's path, which is no secret, and nothing else.
2. **Reading.** Only the passthrough process opens the file, once, at its start, and holds the
   token in memory. It refuses to start unless the file is mode 600, its directory 700, and
   both are owned by its own user. It never reads the file again. **Replacing the token**
   needs the owner's step 1 again, a tranche with nothing in flight, a restart of the
   passthrough, and a ledger row with the date.
3. **Where it never is.** Not in process arguments: the passthrough is given the file's path,
   never the value. Not in the environment of any child: the passthrough starts no child
   process. Not in its logs, its request log or its exception text: its error path prints an
   exception's class and the passthrough's own message, never a header or a request object.
   Not in recordings or fixtures. Core dumps are disabled for the passthrough at its start.
   Its output goes to a file in a directory of mode 700 in the launcher's state, never to a
   pane an agent reads. Its upstream client ignores proxy variables, verifies TLS against the
   trust store compiled into Python (not one an environment variable names), and connects to
   the vendor's host only; the live probe starts it with an empty environment but `PATH`.
   With the rehearsal switch, which points it at the stand-in, it refuses to open any token
   file. Not in what goes back to the container, nor in a log row: every byte of the answer
   and every row is checked for the token in each form the scanner knows, across writes, and a
   match sends nothing more, drops the client and stops the tranche (with the place, never the
   bytes); an answer it cannot check (any `content-encoding` but identity) is handled the same
   way.
4. **The check: `token_scan.py`, by fingerprint.** At its start the passthrough writes a
   fingerprint beside its log: a random salt and, for each form of the token (plain; hex in
   both cases; base64, standard and URL-safe, at the three alignments a copy inside a longer
   encoded stream can have; UTF-16LE), its length and its salted hash. The scanner reads files
   and the fingerprint, never the token: it hashes every candidate string of each form's
   length and prints the path, offset and form of a match, never the bytes around it. So no
   agent, and not the launcher, handles the token's value to check for it.
   - *The file set:* the whole kept output of the run (harness job directories, the
     launcher's state with the passthrough's log and output file, the egress logs); the
     recordings directory; the worktree and the detached checkout; the agents' transcript
     directory of this user.
   - *The runtime check,* on the attempt's containers before teardown: the scanner runs over
     the inspected configuration and the process environments of every container of the
     attempt; at the rehearsal, the probe, the smoke and the pilot it also runs over the agent
     container's exported file system.
   - *The steps that run it:* the passthrough's tests; the rehearsal; the end of the live
     probe; the smoke read; every attempt's teardown (the runtime check and that attempt's
     kept output); every round's read (the whole file set).
   - *The canary test* proves the scanner and the construction together. A fake token of the
     real one's length and alphabet is given to the passthrough against the stand-in. Planted
     in a file of the set, it must be found. After a full session it must be found nowhere in
     the file set, and the runtime check must find it in no container's environment or file
     system.
   - *Its limit:* it finds a whole copy in one of those forms, not a part of the token and not
     another encoding (compressed, encrypted, or escaped, such as JSON's `\/` or a URL's
     `%XX`), and not base64 wrapped at 76 columns (`base64(1)`'s default and MIME's). A named path it cannot read whole (missing, unreadable, a symlink, or no file at
     all) fails the scan. A match anywhere is a stop; the owner revokes the token and replaces
     it.

**The passthrough** is a small host-side process, part of the kit and of the pre-spend review.
For every request it maps the fake token to a slot and refuses an unknown one; refuses any
model other than `claude-haiku-5-5`, any request that declares a provider-side tool, and any
path but the messages path (the only one recorded), and any request line, header, body field
or tool outside the allowlist of the recorded shape; refuses when the slot's metered usage has
reached its cap, when all slots together have reached USD 200, or when the tranche is stopped.
It holds one request in flight per slot: a second waits until the first is metered and is then
checked against the caps. It passes every vendor response through unchanged once it is checked
for the token, reading it to its end even when the client has gone; a response whose usage
cannot be read whole, or a request that got no status back, is priced at a bound on what it
could cost and closes starts. The bound takes as prompt the request body's size in bytes, or
the prompt the stream's first event reported when that is larger, all at the one-hour
cache-write rate (the price rule's dearest prompt rate), and the request's `max_tokens` as
output, with the long-prompt multiplier when that prompt is above the threshold. It is an
upper bound as long as the vendor counts no more prompt tokens than that: a text token covers
at least one byte, and the CLI's first request alone carries about 16,000 characters of
system blocks and tool definitions (`t2a-normal-low`); the live probe's first-request prompt
figure (item 2) checks it. It prices the response's usage by the price
rule and appends one row per request to the slot's log: model, effort, declared tool names,
the beta flags as sent, the cache marks (which blocks carry a cache control, with which
lifetime), usage by kind, the vendor's status, every response header's name and the values of
its vendor-prefixed headers. A refused request's row holds fixed-size fields only. It never
logs the `authorization` header. The meter is part of its first slice (Task 4): the live probe's priced
limits and its cost test rest on it. It prices plain responses as well as streams: after a cut
stream the CLI repeats the request with `stream: false` and `max_tokens: 64000`
(`t2a-f-drop`).

- **A slot's lifetime.** A slot opens when the launcher starts its attempt and stays open, and
  metered, until every container of the attempt is gone; only then does the launcher close it
  and retire its fake token. The CLI outlives the harness's time limit: the harness ends its
  `exec`, not the CLI, which goes on sending requests until its container stops (72 more in
  18.3 s in `t2a-timeout-low`, one 7.5 s later in `s3-timeout-low`; `fixtures/after-limit/`).
  Those requests are the attempt's and are metered into it. **An attempt settles when its slot
  closes.** A request on a retired token is an unknown token, a stop (D5 row 13).
- **An optional request count per slot.** Besides the priced cap, a slot may carry a limit on
  its number of requests. It is refused in the same form with the same reason as the priced
  cap, `lh-passthrough: slot cap reached`, so an ending by either is D5 row 11. Only the live
  probe sets one: 6 requests per slot (one slot per session); its total of 18 is the probe's
  own limit across its three sessions, not a slot's (Task 4). The ladder sets none, and its
  bound per slot is the priced cap.

- **One refusal form, for every reason:** HTTP 403, error type `permission_error`, the header
  `x-should-retry: false`, and the message `lh-passthrough: <reason>`. Recorded for the cap,
  the total and the stop (`pt-cap`, `pt-total`, `pt-stopped`): the CLI did not retry, ended in
  under a second, and the message reached the result text. The 404 and 400 forms tried for the
  model and tool refusals were retried, and the 404's message was lost. Recorded in Task 2a:
  the 403 form ends the model, tool, path and unknown-token refusals the same way
  (`passthrough-model-…`, `-tool-…`, `-path-…`, `-unknown-token-…`): no retry,
  `api_error_status 403`, the message in the result text; each was served on the session's
  second request, and the unknown-token refusal also on its first
  (`passthrough-unknown-token-first-request-UnknownApiError`). A refusal is decided before
  any byte of the body is read; the passthrough then reads and drops, for at most 2 s, what
  the client is still sending before it closes, so that a client still sending its body reads
  the refusal.
- **A vendor 401** means the token expired or was revoked. The passthrough passes it on and
  sets the tranche stopped. Recorded form: two retries, no refresh request, then
  `api_error_status: 401` (fixture `token-unauthorized-UnknownApiError`).

**Usage limits are an expected ending.** The subscription has a limit per five-hour window
(recorded as `rateLimitType: five_hour`) and a weekly one. The owner's sessions, the
coordinating session and the ladder draw on the same allowance.

- **How a limit is recognised: two signals, and the passthrough's decides.** (1) The passthrough
  saw, for that slot, a vendor 429 whose `anthropic-ratelimit-unified-status` header is
  `rejected`. (2) The session's result event has `api_error: usage_limit_reached` and
  `api_error_status: 429`, after a `rate_limit_event` with `status: rejected` and a
  `rateLimitType` (fixture `token-usage-limit-NonZeroAgentExitCodeError`; a plain 429 also
  brings a `rejected` event, without a `rateLimitType`: `stub-rate-limit-ApiRateLimitError`). Signal 1 decides the class (D5 row 10), whatever the
  CLI's result says: the vendor's answer, which no model output can produce, keeps a model-side
  ending from being taken for a limit. Signal 2 without signal 1 pauses the tranche for a ruling.
- **Signal 1 is the stand-in's form,** written from the header names the CLI's bundle reads.
  The vendor's real answer is recorded the first time one occurs: a probe of a few requests
  cannot produce one, and the allowance is not spent to provoke one. Until it is recorded,
  **any 429 from the vendor closes all starts,** whatever its headers.
- **Attempts in flight** each meet the vendor's answer on their next request and end at once
  (recorded with twenty-one tools and with three, `t2a-usage-limit-low`). Each is an
  infrastructure failure of the kind "cut by a usage limit": never an observation, its
  verifier reward not read, its slot run again (D5).
- **Pause and resume.** At signal 1 the launcher closes all starts. It reopens by itself five
  minutes after the reset time the answer names (`anthropic-ratelimit-unified-reset`; the
  event's `resetsAt`), with one start; the others follow once that session's first request is
  answered. An answer that names no reset time pauses the tranche for the coordinator.
- **The allowance guard reads the owner's meter.** Its purpose is that the ladder never
  reaches a limit: it closes starts early enough for the attempts in flight to finish. The
  launcher cannot see the account's meters and the owner can, so the guard runs on what the
  owner reads from them.
  - *Fixed inputs, from the owner (question 2):* the share of the weekly allowance kept free
    for the owner's own work, F-week, in points of 100; the same for the five-hour allowance,
    F-five, its own number; the hours in which the ladder may start attempts.
  - *A reading before every window.* At each weekly reset, and before each of the owner's
    windows of hours opens, the owner gives the weekly meter's reading and the five-hour
    meter's, with the time and each meter's reset time. The coordinator enters them
    (`ladder.py allowance`) and writes them in the ledger. **With no reading for a window the
    launcher starts nothing in it.** This holds for the smoke and the pilot too.
  - *From the pilot (D7):* the priced-token dollars that move the weekly meter by one point,
    and the same for the five-hour meter. Each is taken at its cautious end: the pilot's
    priced usage divided by the points the meter moved plus one, since the meter is read in
    whole points. If the five-hour window reset between the pilot's two readings there is no
    five-hour figure, and the launcher runs two attempts at a time (a judgment) until the
    owner has read that meter around a stretch in which only the ladder used the account.
  - *The rule.* The window's weekly budget is (100 − F-week − the weekly reading) × the weekly
    figure, and zero if that is negative. A start is made only if the ladder's priced usage
    since the reading, plus the guard's reservation for every open slot and for this one, fits
    the budget. The five-hour budget is (100 − F-five − the five-hour reading) × the five-hour
    figure, floored at zero, against the ladder's usage since the reading.
  - *After the five-hour meter resets,* no reading exists for the new five-hour window. Until
    the owner gives one, the five-hour form rests on an approximation alone: the ladder's
    usage in any five hours stays within (100 − F-five) × the figure, and the owner's own use
    of that window is unseen.
  - *A window is skipped,* and reported, when its weekly reading is at or above 100 − F-week −
    5: fewer than five points would be left for the ladder (five is a judgment). When the
    five-hour reading is at or above 100 − F-five − 5, starts wait for that meter's reset.
  - *The guard's reservation* is one third of a slot's cap: the task's public mean cost at
    `max` (1.00 for a task at the floor cap). That figure comes from the public row's
    configuration, which this plan uses nowhere as an expectation; here it is only a
    reservation. The pilot's ledger row states beside it the pilot's cost at each effort over
    one third of that task's cap. If any ratio is above one, the reservation is raised by the
    largest ratio for every task before round 1 goes on.
  - *Hours.* A start is made only inside the owner's hours, and not in the last part of a
    window: the length of the longest pilot session, rounded up to the hour. A session that is
    running when a window closes runs on.
  - *If ordinary responses report the account's utilisation* (the probe shows whether, and
    under which header; none is named here because no recording shows one), the launcher also
    closes starts whenever that figure is at or above 100 − F for its window, whoever used the
    allowance. It
    adds a check and replaces no reading.
  - The owner's inputs and readings live in the launcher's state, outside the manifest. Each
    is a ledger row. They decide when an attempt starts and nothing about what is measured.
- **What the guard cannot see:** the owner's and the coordinator's use after a reading, for
  which F is the only margin; how the vendor weighs token kinds against the allowance, beyond
  the pilot's one reading; an attempt that runs past the guard's reservation, whose excess
  comes out of the owner's share.
- **Paid extra usage must be off, and the stop for it comes one request late.** If the
  account allowed paid usage beyond its limits, a limit would not answer 429: the vendor would
  go on answering 200 and bill, against decision 18. Neither usage-limit signal would fire.
  - *The precondition:* the owner confirms that paid extra usage is off for the account. It is
    a precondition of the live probe, of the pilot and of the freeze, written in the ledger
    with its date each time.
  - *The stop.* The `rate_limit_event` carries `isUsingOverage` (recorded: `false`). The
    launcher reads each session's stream, and an event whose `isUsingOverage` is not `false`
    stops the tranche: the passthrough then refuses every further request. The stream reaches
    the host only after the agent phase (Task 7), so this check acts after the session; the
    stop during a session is the passthrough's header rule below. Task 2a recorded,
    against the stand-in, that a 200 carrying `anthropic-ratelimit-unified-status: rejected`,
    `…-overage-status: allowed` and `…-overage-in-use: true` gives `isUsingOverage: true`, and
    the session goes on to `completed` (`token-paid-extra-usage-normal-end`); which header is
    necessary is not isolated. **The paid-usage signal is not only on 429s.** The passthrough
    therefore stops the tranche at any response, a 429 included, that carries
    `anthropic-ratelimit-unified-overage-in-use: true` or an
    `anthropic-ratelimit-unified-overage-status` of `allowed` or `allowed_warning`; and at any
    response other than a 429 that carries an `anthropic-ratelimit-unified-status` other than
    `allowed` or `allowed_warning` (a response without that header is not stopped by it; a
    429's status is the limit's own answer, D5). The stopping response is not passed on: the
    client gets the 403 form with `lh-passthrough: tranche stopped`, and the passthrough still
    reads that response to its end and meters it. A sign the live probe finds under another
    header can be added at the passthrough's start (`--paid-usage HEADER=VALUE`). The
    header names are as recorded against the stand-in and were read from the CLI's bundle
    2.1.311, not from a vendor document; the live probe confirms them (Task 4, item 2). The
    five-minute cache fallback seen after a response reporting a 990,000-token prompt
    (`t2a-context-late-low`) is not a paid-usage sign: no such header was sent.
  - *What the stop cannot do,* unless the live probe finds `overage-status` on ordinary
    responses: precede the first paid request. Without that header the response that carries
    the signal has already been served, and so has any response in flight in the other open
    slots, at most four in all. If ordinary responses do carry `overage-status: allowed` or
    `allowed_warning`, the stop's `overage-status` clause acts on the first response of the tranche, before
    any paid usage, and is revised under a new coordinator row (Task 4, item 2).
  - *Revised 2026-11-17 after the live probe (coordinator ruling LH-R1; ledger).* Ordinary
    responses do carry the header: each of the probe's three 200 responses had
    `anthropic-ratelimit-unified-overage-status: rejected`, with
    `anthropic-ratelimit-unified-overage-disabled-reason: out_of_credits`, and none had an
    `…-overage-in-use` header. The header names read from the CLI's bundle are therefore the
    vendor's. The clause stays as built (stop at `allowed` or `allowed_warning`): with paid
    usage available the first response of a tranche would carry one of those values, so the
    stop precedes the first paid request, and the "at most four in all" exposure above no
    longer applies to it. `rejected` is the value a tranche may run under. The reason
    `out_of_credits` says paid usage is unavailable because the account holds no credit, not
    that it is switched off: adding credit would turn the header to `allowed` and stop the
    tranche at its first response.

**Price, caps and the ceiling.**

- **Price rule (settled; `price_check.py`).** Per million tokens of `claude-haiku-5-5`: input
  0.10, output 0.50, cache read 0.01; a cache write at the rate of its own lifetime, 0.125 for
  five minutes and 0.20 for one hour. For a request whose prompt (input, cache read and cache
  write together) is above 100,000 tokens, every rate is multiplied by five. This reproduces
  the CLI's total on the three public archives exactly, request by request, and the CLI's
  price for one-hour writes on a stand-in recording. The threshold is known to lie between
  98,828 and 101,144 tokens. `orchestrator/providers/price_table.json` at the frozen commit, by
  SHA-256, gives every rate but the five-minute write, which the criterion adds.
- **Token mode writes one-hour entries** (recorded for system blocks 2 and 3 and the last
  message block; five-minute after a paid-usage response or a very large prompt). The same session
  therefore costs more in priced tokens than the public row's: the three archives repriced
  with one-hour writes give 1.05, 1.07 and 1.11 times their totals. The meter prices each
  write by the split the usage reports, so a five-minute write in a token session is priced
  as one.
- **Per-attempt cap:** `max(3.00, 3 × the task's public mean cost per trial at effort max)`
  (the table in D1), the same at every effort, enforced by the passthrough and by the CLI's own
  budget limit. In the ladder's prices that is about 2.7 to 2.9 times the public mean. **Each
  guard acts one response late:** the CLI stops after the response that crosses the cap,
  without running the tool call in it (recordings `s3-budget-medium` and, in this
  configuration, `t2a-budget-medium`), and the passthrough refuses the next request. The
  passthrough holds one request in flight per slot and checks the next against the caps with
  the first metered, so a slot's cap is overshot by at most one response, and the total,
  checked under one lock, by at most one response per open slot.
- **Reservation before every attempt:** the cap plus USD 1.00, which covers one response of the
  largest output (128,000 tokens, USD 0.32 at the long-prompt rate) and a freshly cached prompt
  of about 680,000 tokens at the one-hour long-prompt rate. Under one lock the launcher
  computes *committed* = settled cost of every start + every open reservation, and launches
  only if *committed* + reservation ≤ 200.00 and starts < 240. The live probe's priced usage
  is settled into *committed* before the first attempt.
- **Settlement** replaces a reservation with the largest of four figures, read by these rules:
  1. the passthrough's meter;
  2. the session file's rows priced by the rule, one row per message id (a message's usage is
     repeated once per content block);
  3. the result event's `total_cost_usd`;
  4. the result event's `modelUsage` priced at the base rates (a floor: it cannot apply the
     long-prompt rate, which is per request).
  The result's `usage` is never read (all zeros at a budget stop, while figures 3 and 4 are
  right), nor are stream events (they carry only the count at the start of a message). A
  timeout kill leaves no result event, and the CLI goes on sending requests until its
  container stops (72 in 18 s recorded); figure 1 settles it, figure 2 lags (1,212 requests at
  the stand-in against 1,149 responses in the harness's count, `t2a-timeout-low`). Subagent rows would sit in
  a separate file; none exists in this configuration, and one is a stop. Unreadable usage
  settles at the full reservation. An attempt cut by a usage limit settles like any other: its
  tokens were used.
- **What ends the tranche:** nothing in flight and the next slot's reservation does not fit; 240
  starts; a stop rule of D7. The launcher never skips ahead to a cheaper slot. The allowance
  guard and a limit only make the tranche wait.
- **Expected priced usage (planner's estimate):** about USD 182 to 192 for all 240: the earlier
  USD 173 (low 33, medium 53, high 87, from two public cost points; report §9) times the 1.05
  to 1.11 of one-hour writes. Plausible range about 150 to 285. Not in the estimate, because
  nothing recorded gives them: the larger request (about 13,800 characters more: 8,804 in the
  system blocks, 3,501 in the tool definitions, about 1,470 in the first request's messages;
  about 3,500 tokens at four characters per token, under one percent of an archive's cost when
  read from cache; the live probe's first request gives the count); fewer
  rewrites under a one-hour cache; and how the default system prompt changes what the model
  does. The pilot gives the first measured figure.

**Worst case when one guard fails.** No row is a bill: nothing is billed. Dollar figures are
priced tokens; the last column says what it means for the allowance.

| Guard that fails | Bound in priced tokens | What it costs in allowance |
| --- | --- | --- |
| The CLI's budget limit does not stop a session | The passthrough refuses at the cap: USD 200 plus one response per open slot | Inside the allowance guard |
| The launcher's reservation | The passthrough's own total stops at USD 200 | Inside the allowance guard |
| The passthrough's meter under-counts | The reservation and the CLI's limit still hold; if both fail too, four sessions run to their natural end, about USD 290 to 370 | Bounded only by the account's own limits |
| The allowance guard (a wrong pilot figure, a wrong or stale reading, or heavy use by the owner or the coordinator after a reading) | None of its own; the dollar ceiling still holds | **The weekly allowance runs out: the owner's sessions and the coordinating session stop until the weekly reset, up to seven days. The ladder pauses by itself and loses the attempts in flight.** The five-hour form of the same failure stops them for up to five hours |
| The relay or the allowlist lets the agent out | No credential is in reach | The loss is the network policy |
| The price rule is wrong | Every priced figure is off by the error | None: the vendor's meter does not use our prices |
| The passthrough's model check | None in the kit | Another model draws on the same allowance at its own weight; the response's model is checked on every request, and one other model is a stop |
| A process of this host user reads the token file, or the passthrough's memory | None in the kit; the scanner finds a copy only once it is written somewhere in its file set | That process can use the owner's subscription, any model, up to the account's limits, until the owner revokes the token |
| Paid extra usage is on in the account | None in the kit | A limit becomes a bill. The owner's dated confirmation is the guard; the stop acts after the first paid request, at most four responses late |

**The passthrough cannot stop:** the response in flight when a cap is reached; usage inside a
slot's cap that is not the session's own (a direct request with the fake token: metered and
capped, but absent from the session file); a wrong price rule; another process of the same
host user reading the token file; the owner's and the coordinator's own use of the allowance.
There is no vendor-side spend limit behind any of this: decision 18 removed the workspace
limit the second revision named as a precondition.

### D5. Infrastructure failure against model failure

**A session has started** when its stream holds an init event; every recorded session emitted
one before its first request. **The ending is read from five things:** the result event's
`terminal_reason`, `api_error`, `api_error_status` and `stop_reason`; the `lh-passthrough:`
prefix in the result text; and the passthrough's log. The log is the authority for a usage limit
met before the session's ending (row 10). It is read for the slot, except for the refusals it logs with no slot (rows 12 and 13):
there the reason in the attempt's own result text decides, and the tranche's rows in the attempt's
time window corroborate it. A refusal is logged with no slot when it is decided before the token
is mapped to a slot: the request line, the headers, an unknown token, a stopped tranche, the
connection cap. Such a row is the attempt's when its reason is the one the attempt's result text
names and its time lies between the slot's opening and closing (`ladder.json`,
`classification.passthrough_log.join`). `subtype` decides nothing:
it is `success` for refusal, output-limit and context-limit endings. **The harness class
decides nothing where endings share one,** and they do: a 529, a stalled first byte, a refused
credential and every passthrough refusal end as `UnknownApiError`; a context limit, the CLI's
budget stop and a usage limit end as `NonZeroAgentExitCodeError` (recorded). The class is
read only in the three rows that name it as deciding.

The rows are tried in order and the first match decides, except that row 13 is tried first, so
that a stop whose cause the attempt's own slot shows (an answer withheld for paid extra usage
among them) is a stop whatever else the slot's log holds (a usage-limit 429 that carries an
overage sign is withheld too); then row 10, because the passthrough's log is the authority for a
usage limit met before the session's ending, so row 10 decides over every other ending it meets
(the pairs, each with its reason, are `classification.order_resolves` in `ladder.json`); and row
14 is tried before rows 11 and 12: behind the passthrough, a vendor 401 sets the tranche stopped, so the CLI's
retries meet `lh-passthrough: tranche stopped` and the attempt ends in row 12's form.

| # | Ending | Decided by | Harness class | Fixture | Class of outcome |
| --- | --- | --- | --- | --- | --- |
| 1 | Before a session | No stream at all, and the harness's message does not name `CLAUDE_FORCE_OAUTH`; the class decides | `RuntimeError` | `pre-session-agent-install-…`, `pre-session-network-switch-…` | Pre-session failure |
| 2 | The CLI read no credential, or the harness found none | A result with `api_error_status: null` and no request for the slot in the passthrough's log, the class deciding (`AgentAuthenticationError`); or no stream and a `RuntimeError` whose message names `CLAUDE_FORCE_OAUTH` | `AgentAuthenticationError`, `RuntimeError` | `token-no-credential-AgentAuthenticationError`, `token-forced-empty-RuntimeError` | A stop: the configuration is wrong |
| 3 | Time limit | No result event; the class decides. The CLI's requests after the limit, until its container stops, are metered into the attempt (D4, a slot's lifetime) | `AgentTimeoutError` | `stub-timeout-AgentTimeoutError` (a loop of tool calls the CLI refused locally, not a hung command; below) | Observation, flagged |
| 4 | The host, Podman, the passthrough or the launcher died | No result event and no harness result | none | none (launcher's own record) | Infrastructure failure |
| 5 | Normal | `terminal_reason: completed` | none | `token-three-tools-normal-end`, `-medium`, `-high` | Observation |
| 6 | Dollar cap, by the CLI | `terminal_reason: budget_exhausted`; the result has no `api_error_status` key (absent, which no rule reads as null) | `NonZeroAgentExitCodeError` | `stub-budget-stop-…` | Observation, flagged |
| 7 | Context limit | `terminal_reason: prompt_too_long` (with `api_error_status: 400`) or `blocking_limit` | `NonZeroAgentExitCodeError` | `stub-context-limit-…`, `stub-context-limit-after-compaction-…` | Observation, flagged |
| 8 | Refusal | `stop_reason: refusal`, after a `model_refusal_no_fallback` event | `AgentSafetyRefusalError` | `public-refusal-…`, `stub-refusal-…` | Observation, flagged |
| 9 | Output limit | `api_error: max_output_tokens` | `OutputTokenExceededError` | `stub-output-limit-…` | Observation, flagged |
| 10 | Usage limit | Signal 1 of D4 for the slot in the passthrough's log, in a row timed before the session's ending (the moment its result event arrived; for a time-limit session, the moment the limit fired), whatever the CLI's result says. A usage limit met only by requests after the ending (the after-limit tail of a time-limit session) does not change the attempt's row, which stays its own ending's (an observation where that row says so); the answer still closes starts. The CLI's own form with both signals: `api_error: usage_limit_reached` with `api_error_status: 429`, after a `rate_limit_event` with `status: rejected` and a `rateLimitType`; with signal 1 alone, an ordinary 429 after ten retries | `NonZeroAgentExitCodeError` | `token-usage-limit-…`; `simple-mode-stub-usage-limit-headers-key-mode-…` (signal 1 alone, recorded in key mode) | Cut by a usage limit: excluded, and the slot is run again |
| 11 | The passthrough refused: the slot's cap | `api_error_status: 403`, the result text holds `lh-passthrough: slot cap reached`, and the passthrough's log agrees; the priced cap and the optional request count (D4) end alike | `UnknownApiError` | `passthrough-cap-…` | Observation, flagged |
| 12 | The passthrough refused: total or stop | `api_error_status: 403`, the result text holds `lh-passthrough: tranche total reached` or `lh-passthrough: tranche stopped`, and the passthrough's log agrees, in the tranche's rows of the attempt's time window, and the attempt's own slot's rows show no cause of a stop (that is row 13); the stops that leave no mark on a slot's rows (the token in a response, a response that cannot be checked, an unreadable slots file) end here | `UnknownApiError` | `passthrough-total-…`, `passthrough-stopped-…` | Infrastructure failure |
| 13 | The passthrough refused: model, tool, path or unknown token; and the refusals of a request outside the frozen shape (a field or header not allowed, a header repeated, a malformed request, non-JSON among them, an oversized one); or the attempt's own slot stopped the tranche: an answer withheld for paid extra usage (D4), a form of the token in its log row, a response naming another model | `api_error_status: 403`, the result text holds `lh-passthrough:` and that reason, and the passthrough's log agrees, in the tranche's rows of the attempt's time window; for a stop of the attempt's own slot, the result text holds `lh-passthrough: tranche stopped` and the slot's own rows show the cause (the withheld answer logged as not passed on, the row withheld for the token, the other model's name) | `UnknownApiError` | `passthrough-model-…`, `passthrough-tool-…`, `passthrough-path-…`, `passthrough-unknown-token-…` (and `passthrough-unknown-token-first-request-…`); the refusals of a request outside the shape: none recorded, each read as the recorded form with its own reason; a stop of the own slot: the form of `passthrough-stopped-…` | A stop; after a withheld answer, the coordinator row that lets the tranche resume also records what the owner said (coordinator ruling, 2026-11-14) |
| 14 | The vendor refused the credential | A vendor 401 for the slot in the passthrough's log (the CLI's own form: `api_error_status: 401`) | `UnknownApiError` | `token-unauthorized-…` | Infrastructure failure, and a stop |
| 15 | Provider fault, after the CLI's ten retries; or the passthrough refused under load or timing (too many connections, a busy slot, a timed-out request) | `terminal_reason: api_error` with `api_error_status` 429 (and no `usage_limit_reached`), 500 or 529; or `null` after ten `api_retry` events; or `api_error_status: 403` with `lh-passthrough:` and one of the three load reasons in the result text, which the passthrough's log agrees with in the tranche's rows of the attempt's time window; and in each case no signal 1 of D4 for the slot before the session's ending (that is row 10) | `ApiRateLimitError`, `ApiInternalServerError`, `UnknownApiError` | `stub-rate-limit-…`, `stub-server-error-…`, `stub-overloaded-…`, `stub-slow-first-byte-…`; the load refusals: none recorded, each read as the recorded form of `passthrough-model-…` with its own reason | Infrastructure failure: the passthrough raises the load refusals under load or timing, not for a request outside the frozen shape, so they do not halt the tranche (coordinator ruling N2, 2026-11-14) |
| 16 | Anything else | No row above matches | any | none | The launcher pauses for a recorded ruling |

- **What the fixtures were recorded in.** Rows 2, 3 and 5 to 15 cite recordings in the
  ladder's configuration (Task 2a); row 1's are harness-level failures from Task 1; row 8 also
  cites the public archive. The simple-mode recordings stay under `simple-mode-` names, as
  evidence for D2, except that row 10 cites one, recorded in key mode, for the CLI's form when
  only the passthrough's log shows the limit.
- **Row 3's fixture is a loop, not a hung command.** The stand-in answered every turn with a
  standalone `sleep 30`, which the CLI's Bash tool refuses locally, so the session made 1,212
  requests in 187 s (6.5 per second) until the limit. Cheap at the stand-in's fixed usage
  (USD 0.18); at real prices, with the prompt growing by three messages a turn and read from
  the one-hour cache, the reviewer's estimate is USD 4.0 to 6.2 for the session, passing
  USD 3.00 around request 900 to 1,100. A real attempt looping like this meets the CLI's
  budget (row 6) or the slot's cap (row 11) long before the time limit; both are flagged
  observations, and the overshoot stays one response (D4).
- **A normal ending can hold faults the CLI recovered from:** each retry leaves an `api_retry`
  event (fixtures `stub-transient-faults-recovered-normal-end`,
  `stub-dropped-stream-recovered-normal-end`). They change no class; their count is recorded
  per attempt.
- **What each class means.** An *observation* counts against the 240 and the USD 200 and
  enters k and n with the verifier's reward. A reward is only what a verifier gave: an
  observation whose verifier gave none (one cancelled when the harness was stopped, for
  example) is regraded as case 1 below, never scored 0 (coordinator ruling on Task 7). The
  verifier ran after a timeout kill (recorded). An *infrastructure failure* counts against both and is
  excluded from k and n, listed, never scored zero; its slot is not run again. A *pre-session
  failure* counts against neither; the slot is relaunched at most twice and is lost after the
  third failure. It is one with no cost (the passthrough metered no usage and every settlement
  figure was read as 0): an ending of its form with a cost keeps its row and is an
  infrastructure failure, at the close and at a ruling alike (coordinator rulings on Task 8).
  A *stop* halts the tranche: no new start. The attempt in which it occurred is
  not an observation and is not scored. It counts against the 240 and the USD 200, as every start
  does (D4: every start's settled cost is committed, and launches stop at 240 starts); for row
  2's second form, which ends before a session, that is the conservative count. Its slot is not
  run again, and nothing resumes until a coordinator row in the ledger names the cause and the
  decision.
- **An attempt cut by a usage limit** is an infrastructure failure with one difference: its
  slot is run again, at the head of the queue, when starts reopen. The cut start still counts
  against the 240 and its tokens against the USD 200, so **each cut costs one slot at the
  hashed tail of the schedule** (D7). This is the reading that cannot exceed the approval's
  240 attempts. The cut session's reward is never read.
- **Why the rerun is not a second chance.** The account decides a cut, by the vendor's answer in the
  passthrough's log, which the model cannot produce, and the rule is fixed before any data. One bias remains: a long
  session is more exposed to a cut than a short one, so many cuts would lean the completed
  sessions toward short ones. The readout lists cuts per effort, and cuts above 5% of starts
  (from 20 starts on) pause the tranche for a ruling; the allowance guard exists to keep the
  number near zero.
- **Model-side endings are never excluded:** they are the longest and dearest sessions and
  come mostly from the higher efforts. The one exception is a usage limit met before the
  ending (row 10), which makes the attempt a cut whatever the CLI's result says; a usage limit
  met only by requests after the ending (the CLI's after-limit tail) excludes nothing. **A slot whose session ended in any other way is never
  run again,** so a retry cannot turn a model failure into a pass.
- **Verifier-only regrade** (no model call, the saved artifacts unchanged), in two cases. (1)
  No reward after an observation's ending (a normal ending, or any other observation row
  whose verifier gave none; the row is kept): up to two regrades below the load gate; a
  reward then stands; a verifier timeout twice is reward 0; still no reward file is an
  infrastructure failure, excluded "no reward after regrades". (2) A task on the load-sensitive list returned reward 0 while the load was above the
  gate during verification: one regrade below the gate, and its reward stands. Only a reward of
  0 is regraded, because the known defect of such a verifier under load is a false failure. If
  the harness cannot regrade on Podman, case 1 becomes an infrastructure failure and case 2 is
  excluded as "indeterminate". A regrade the harness refuses because a declared artifact was
  not collected in the source trial (Harbor 0.25.0's `RegradeError` "<path>: collection failed
  in the source trial; the record does not contain it") leaves case 2's reward of 0 standing:
  load cannot make an absent artifact present, so the attempt stays an observation, flagged
  "artifact absent", and the readout counts the flag per task and effort. Case 1 is unchanged by
  it, since a reward is only what a verifier gave: still an infrastructure failure, "no reward
  after regrades". Any other refusal keeps the handling above (coordinator ruling on the
  rehearsal's second run).

### D6. The readout

- **Per task and effort:** k of n with the exact (Clopper–Pearson) 95% interval and a label:
  k = 0 "floor", 1 or 2 of 5 "screened in", 3 or more "above". A cell with n under 5 is
  labelled incomplete. Flags and exclusions are listed; attempts cut by a usage limit are
  counted per effort, and the three pilot attempts are marked.
- **No figure is set beside the public row's.** The readout names the configuration (D2) and
  prints no public rate as a reference.
- **One configuration label per cell.** Every rule below reads the observations of the current
  label alone (D7). Observations under an earlier label are printed in a table of their own,
  with their label and the ledger row that ended it, and enter no rule. A cell with fewer than
  five observations under the current label is printed as it is, with its count, and labelled
  incomplete.
- **Per task, pooled** (K of its n attempts): K = 0 is "floor" (upper bound 21.8% at 15);
  1/15 ≤ K/n ≤ 1/3 is "screened in"; above is "above the band". The pooled label admits a
  task to the family; the per-effort labels are printed beside it, because a pooled count mixes
  three rates. The rule accepts a task of constant true rate 2%, 5%, 10%, 20%, 30%, 50% with
  probability 0.26, 0.54, 0.79, 0.90, 0.72, 0.15. The label is "screened at n of 15 attempts",
  never "in the 10 to 30 percent band". The screen is applied when every effort has at least
  four scored observations (12 to 15 of the planned 15, `readout.pooled.min_per_effort`), to the
  pooled K/n with its exact interval; with fewer at any effort, the readout prints the pooled
  count and interval and "not screened: n of 15 attempts" with the count per effort, and the
  task is neither in nor out of the family. `family.json` is written only when every task is
  screened or recorded as dropped for a reason that names a ledger row by its date (coordinator
  ruling R4, 2026-11-14, revised after review: a screen at exactly 15 made one excluded attempt
  drop the task).
  - **The cost of screening below 15** (computed by the readout's reviewer, 2026-11-14). The
    band admits pooled counts 1 to 5 at 15 attempts and 1 to 4 at 12, 13 and 14. The chance
    that a task of constant true rate is screened in, at 15 and at 12 attempts: 2%, 0.261 and
    0.215; 5%, 0.537 and 0.459; 20%, 0.904 and 0.859; 40%, 0.403 and 0.436; 50%, 0.151 and
    0.194. At 14 attempts a 30% task is screened in 0.577 of the time, against 0.717 at 15. A
    task screened on fewer attempts has a wider interval, which is printed beside its label.
    Under the revised rule about 12 to 15 of the 16 tasks can be screened at all, against about
    4 to 10 under a rule of exactly 15 (exclusions at 2 to 5% of starts, up to seven tail blocks
    dropped).
- **Band effort,** for every screened-in task: among the levels with at least one success, the
  one whose k/n is closest to 0.2, ties to the lower level. Every screened-in task has such a
  level. It is labelled "noisy, one cell of five", and flagged when that cell is 3 or more. A
  floor or above-band task has none.
- **Effort test, fixed before the data.** A (task, round) triple is complete when its three
  slots are all observations. Over complete triples, `s_i(e)` is task i's successes at effort e
  and `d_i` a difference between two levels. The test is the exact one-sided sign-flip
  permutation test over tasks on the sum of `d_i`. The pooled successes by effort are printed
  as counts with no interval, because they pool tasks of different rates (coordinator ruling
  N1, 2026-11-14).
  - **Falls:** high against low sums below zero with p ≤ 0.05, or an adjacent pair sums below
    zero with p ≤ 0.025. **Rises:** pooled successes satisfy low ≤ medium ≤ high, and high
    against low sums above zero with p ≤ 0.05. **Not resolved:** anything else.
  - **Always reported: the bound on the fall,** the one-sided 95% upper bound on the pooled fall
    from low to high in points (bootstrap over tasks, 10,000 resamples, fixed seed). "Not
    resolved" means only that no fall above that bound was ruled out; it is never read as "does
    not fall". It places nothing, so a stop readout prints it too, over the complete triples
    there are ("over N complete triples; no placement is made"), or says there are none
    (coordinator ruling R2, 2026-11-14). The resampling method is frozen in `ladder.json`
    (`readout.fall_bound`; ruling R5).
  - Sensitivity (simulated, 16 tasks with five at zero): a pooled change of 12 points is
    detected in about half of runs, 17 points in 79%, 20 points in 88%; false alarm 5%. With
    ten tasks at the floor a 17-point fall is detected in about a fifth of runs.
- **Cost:** per effort, mean priced cost and minutes per observation, tokens by kind, and cost
  per success (the cost of every start at that level over its successes, cut starts
  included). An effort level is named dominated only when another level beats it on the same
  sign-flip test at p ≤ 0.05 (`readout.cost.dominated_p_at_most`; ruling R3) and has a lower
  mean cost; otherwise "not resolved". Beside it,
  from the owner's meter readings: the share of a weekly allowance the tranche used, in all
  and per priced dollar. It is a report, tied to this account's plan, and enters no rule.
- **Graded outcome, secondary (roadmap Phase 5b, "Making fitness cheaper to measure").** Where
  a task's verifier reports sub-tests, each observation also records passed and total. It is
  printed per task and effort beside k of n, places no task and enters no test above. Task 2b's
  oracle runs establish which verifiers expose it and in what form (no recording shows it yet);
  a task without it prints "pass or fail only".
- **Adaptive order: rejected.** Running `high` first and skipping the lower levels of a task at
  0 of 5 assumes the thing under test and removes the tasks where a violation would show;
  leaving those tasks out instead keeps tasks selected for success at high.
- **Contamination scan:** over transcripts, for specific strings frozen after a dry run on the
  oracle jobs and the recordings (the benchmark repository's path, the canary's identifier, the
  reference solution's full path in that repository). The canary's identifier is read from the
  task packages at run time and is in the criterion only as its SHA-256 (D1). A task whose
  agent-visible starting files already hold the canary (wal-recovery-ordering's `/app` in the
  rehearsal) is scanned without the canary term and with every other term; the dry run lists
  those tasks in `canary_exempt_tasks` (coordinator ruling on Task 7). A hit on an
  observation excludes it; a hit on a start of any other class (a cut, an infrastructure
  failure, a stop, a pre-session failure) leaves its class unchanged. Every hit is listed and
  counts for D7.7's three tasks (coordinator ruling, 2026-11-14, after review M2). The launcher runs the scan at each teardown, beside the token
  scanner, with the frozen terms, and writes the result into the slot's record; the readout only
  reads it and lists every contaminated attempt with the term's SHA-256, never the term
  (coordinator ruling, 2026-11-14). Each start's record carries the class the launcher
  decided, with its D5 row as evidence: the row's class, or a stop the launcher found (a cause
  from the closed list in `slot_record.py`) on a row of another class; a stop is never scored
  and is listed with its cause (after review M1). The egress log adds, per attempt, the refused addresses and their count (D3); a
  refused connection fetched nothing and excludes nothing. A connection to the relay itself that
  the sidecar logged as refused because its lookup of `relay` timed out is no refused egress: it
  is counted and listed apart, as a relay lookup timeout, so the refused list holds only
  destinations outside the kit (coordinator ruling on the rehearsal's second run). A readout that ends in a stop prints no placement.
- **The final readout is bound to the frozen criterion.** Without `--rehearsal` the readout
  runs only when the manifest is frozen, its hash is the export's configuration label, the
  files `ladder.json`, `tasks.json`, `readout.py` and `slot_record.py` match the manifest's
  records and no field is pending; otherwise it is refused with the reason, or run as a stamped
  rehearsal (after review M3).

### D7. Order and stop rules

1. **Freeze, then smoke.** The manifest hash is frozen and in the ledger before the smoke.
   **Smoke:** one attempt, gsea-proteomics at `low` (cheap, short, and it needs a package
   index). Then stop and read, each check against a recorded form: the init event reports CLI
   2.1.311, exactly the tools `Bash, Edit, Read` and `apiKeySource: none`; the passthrough saw
   only the bound model, only the messages path, no provider-side tool, and the same declared
   tools on every request (`Bash, Edit, DeferredToolPlaceholder, Read`); each request carries the bound effort; the cap is on the session;
   the egress log shows no connection outside the list except refused ones; settlement figures
   1, 2 and 3 agree within 1%; the verifier returned a reward; `token_scan.py` finds nothing
   in its file set, and the runtime check nothing in the attempt's containers (D4); no
   `rate_limit_event` reporting paid extra usage (every token-mode session emits one with
   `isUsingOverage: false`) and no response header reporting it; the slot settled. A
   pass makes it slot 1 of round 1. If gsea-proteomics does not qualify, the smoke task is the
   first qualified task in `tasks.json` order that is not on the load-sensitive list.
2. **Pilot: rs-archive-clone at `low`, `medium` and `high`, the three together, before
   anything is scheduled.** What one attempt costs against the weekly allowance is unknown:
   the public row averaged about 37 million tokens per attempt at `max`, almost all of them
   cached re-reads, and nothing says how the vendor weighs those.
   - *Why this task.* It is the dearest of the 16 by its public cost, so its three attempts
     move the meter most: about USD 6 of priced usage by the planner's estimate, about 3
     percent of the tranche. It is unchanged since 4.0.0. If it does not qualify, the pilot
     task is the next dearest qualified task that is unchanged since 4.0.0.
   - *The owner reads the meters.* Every usage meter the account shows, with the time, before
     the three start and after the last ends; the coordinator writes the readings in the
     ledger. The reading before is also the window's reading of D4, and the pilot does not
     start on a window that D4 skips. Use of the account by anyone else in between makes the
     meters move more, which makes the guard more cautious and never less. The reading is most
     useful if the owner and the coordinating session stay off the account for those hours.
   - *What it gives:* the two figures of the allowance guard (D4); priced cost and tokens by
     kind at each effort, for this one task; the length of the longest session.
   - *The pilot runs before the guard has its figures.* If it meets a usage limit itself, its
     cut attempts are run again one at a time after the reset, and the cut is the first
     reading: three such attempts did not fit one five-hour window.
   - *What the plan then states,* in a ledger row before any further start: the dollars per
     meter point; **how many attempts a week can hold** at a reading of zero (the points left
     above F-week, times the weekly figure, over the expected cost of an attempt: the estimate
     of D4 rescaled by the pilot's cost at each effort over the estimate for the same task and
     effort); **the number of weekly windows** that implies for the remaining expected usage,
     rounded up; the guard's reservation (D4); and the hours.
   - *A meter that moved less than two points* gives bounds, not figures. The schedule is
     built on the cautious bound, and the owner reads the meters again at the end of round 1.
   - *More than six weekly windows* is reported to the owner before any further start: a
     tranche that long is the owner's choice. Six is a judgment, not a computed threshold.
   - **The three attempts are observations of the ladder,** and this is fixed here, before
     they run. They are the block of rs-archive-clone in round 1. They run through the
     reviewed launcher, at the frozen manifest, after the task has qualified. The readout
     marks them: they ran first. The allowance inputs and readings are not part of the
     manifest (D4).
3. **Rounds, in blocks.** Five rounds. A round is one block per qualified task (15 after Task 2b,
   so the schedule is 225 slots); a block is that
   task's three efforts, started one after another. The order of the blocks in a round, and of
   the efforts in a block, is fixed by a hash of a frozen seed, the round, the task and the
   effort. The four slots already run are skipped. A slot run again after a cut goes to the
   head of the queue. A task's three efforts thus run next to each other, so effort is not
   confounded with time of day, day of the week or load. The tranche runs over as many weekly
   windows as the pilot implies, inside the owner's hours.
4. **What is dropped when the ceiling or the 240 ends the tranche: the tail of that order,
   fixed before the first attempt.** The launcher never skips ahead, to a cheaper slot or any
   other. So whole blocks drop from the end of the last round reached, and at most one block
   is left partial. Tasks then differ by at most one block, and outside the one partial block
   every task has the same number of starts at each effort. The cells of dropped blocks have
   fewer than five observations and are labelled incomplete (D6); the effort test reads
   complete triples only. The drop is balanced across tasks and efforts to within that one
   block. It is not outcome-blind in one respect, known before the data: the block at which
   the ceiling stops is more often a dear task's, since its reservation is the larger.
5. **Stop and read after round 1:** classification counts, cost per effort against the
   estimate, the scan, the load record, the cuts, and the owner's meter readings against the
   pilot's figures. The projection goes in the ledger; no threshold of the readout moves. The
   allowance figures may be corrected by a ledger row.
6. **A change after the pilot's first attempt makes a new configuration label.** The label is
   the manifest hash, which covers the kit, the configuration and the task and image digests.
   The package code the launcher reuses is bound by the runtime commit (`LH_RUNTIME_COMMIT`), not
   by the label.
   - A change is allowed only to repair a safety or correctness fault. Its ledger row is
     written before the next start and names the fault, the change and the new hash. The
     round-1 read is not an occasion for one.
   - Observations under different labels are never pooled in a cell. The readout places tasks
     and tests effort on the current label alone (D6).
   - The 240 and the USD 200 do not restart: starts under every label count against both.
     Nothing is run again to refill a cell. A cell left with fewer than five observations
     under the current label is reported as it is, with its count.
   - The smoke and the pilot are under the first label like any other start. A change before
     the pilot's first attempt (after the smoke) also means a new hash and a ledger row; the
     smoke's start stays counted and is under the earlier label.
   - The allowance inputs and readings are outside the manifest and make no label.
7. **Stops:** a failed smoke; a response with non-zero usage that names another model; an init
   event with another CLI version, tool list or credential source; a subagent file; a
   passthrough refusal for model, tool, path or token; a vendor 401; a sign of paid extra
   usage (D4); a match of `token_scan.py`; three usage-limit answers in a row with no
   observation between them; infrastructure failures other than cuts above 10% of starts (from
   20 starts on) or above 20% at one level (from 20 starts at that level; a threshold of its
   own, cleared apart: coordinator ruling on Task 8); five pre-session failures in a row or 24 in all;
   contaminated attempts on three tasks; under 20 GB free. The init-event, stream and
   subagent checks read files that reach the host only after the agent phase (Task 7), so
   they act after the session; during a session only the passthrough's own checks act, and the
   paid-usage stop then is its header rule (D4). **Pauses that end by themselves:**
   a usage limit, until its reset (D4); the allowance guard and the owner's hours, which only
   delay starts. **Pauses for a ruling or an owner's input:** a window with no meter reading;
   the load wait of D2; the passthrough down; a limit answer that names no reset; cuts above
   5% of starts (from 20 starts on); an ending that matches no row of D5; three attempts in one
   tranche ended by a load refusal of the passthrough (D5 row 15), which also count toward the
   infrastructure-failure stop above. **How each is lifted** (coordinator rulings on Task 8):
   a stop needs one ledger row `| <date> | Ruling | resume: <its cause>: <the decision> |` for
   each distinct stop since the last resume, then `ladder.py resume --date <date>`; a count
   threshold over its bound (the two infrastructure shares, the pre-session failures, the cuts,
   the load refusals) needs `| <date> | Ruling | <threshold>: <the decision> |` and
   `resume --clears <threshold>`, once for each, and then counts only later endings; a resume
   never lifts a usage limit.
8. Nothing is topped up, moved between cells or re-thresholded after the first attempt. A
   slot run again after a cut is not a top-up: it is one of the 240 starts.

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

**Step 8: merge and freeze the seed.** `milestones.orc` (`experiments/long_horizon_seed/`, 49 lines of at
most 120 columns; beside it the comparison seeds `staged`, 34, `roles`, 50, and `designed`, 62; frozen
by `experiments/long_horizon_seed/seeds.json`)
is written once, after the surface-coherence changes of Lane D stage 5 merge (46 lines
expected). Required: it compiles at the current target under 50 lines; each role's effort is a
string literal at that role's call sites and is no entry input (owner, 2026-11-13, effort per
role; a point of the search is a program, see the
[mutant generator plan](2026-11-13-phase-6-mutant-generator-plan.md#the-first-space-is-programs-not-bindings)); its stand-in scenarios are a test
(`tests/experiments/test_long_horizon_seed.py`); registry rows (`workflows/README.md`); a hash in the
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
USD 180 to 490 of priced usage, after a measure-free smoke of two seed runs (about USD 16), and
excluding any ladder for added tasks. These are the earlier USD 170 to 440 and USD 15 times
the 1.05 to 1.11 of one-hour cache writes; what the default system prompt adds is not known
before the ladder's own figures. Both arms run on the subscription, in the ladder's
configuration, so the request also states what share of how many weekly allowances it needs,
from the ladder's measured figures. Open design work, larger than one line: how a workflow's
steps run inside a task container, and what the seed uses as its visible check, since the
tasks ship none.

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
on `PATH`. The order stands: recordings before the criterion, the passthrough and its live
probe before the launcher, the review before the first attempt.

### Task 1: recordings (done 2026-11-13, no spend; 8 h)

On `feat/long-horizon-recordings`: `stub_api.py`, 17 local recordings of CLI 2.1.311, three
public trial archives, 15 fixtures, and the assumption table the second revision applied.

### Task 2, first part: probes (done 2026-11-13, no spend)

On the same branch (`RECORDINGS.md`, "Task 2 probes"): the relay route's four probes, all
held; the endings again with three tools in simple mode; provider faults; the passthrough's
refusal forms; the price rule; the 16 packages fetched and matched to their 4.1.0 digests
(`tasks.json`, `relay-compose.yaml`); and the token-mode set, which showed that simple mode
refuses a subscription token.

### Task 2a: record the ladder's configuration (impl_code; 7 h; no spend)

Every frozen rule now needs a recording in token mode with the deny list, through the relay,
against `stub_api.py` with a fake token. **Files:** modify `stub_api.py` (any scenario
missing), `record.sh`, `recordings.json`, `fixtures/`, `RECORDINGS.md`.

- [ ] **The init event** at each of the three efforts: tool list, `apiKeySource`, MCP servers,
      CLI version. **The request:** declared tools, effort, `max_tokens`, beta flags, and the
      cache lifetime asked for on every cached block, messages as well as system.
- [ ] **The size of what every request carries:** the system blocks and the tool definitions
      in characters, beside simple mode's (`tok3-normal` against `key3-normal-system`). Tokens
      cannot be counted without the vendor; the live probe's first request gives them.
- [ ] **The endings:** the CLI's budget stop, a refusal, an output limit, a context limit at
      the first request and after a compaction attempt (with the compaction request's form), a
      time-limit kill, a usage limit with three tools, a refused credential.
- [ ] **Provider faults:** a 429 with and without `retry-after` and without the usage-limit
      headers, a 529, a 500, a cut stream, a stalled first byte, transient faults recovered.
- [ ] **Every passthrough refusal in the 403 form:** cap, total, stop, model, tool, path,
      unknown token.
- [ ] **The launcher's fake token form** (prefix and random part) is accepted by the CLI.
- [ ] **No credential read, in token mode:** an empty token variable. Row 2 of D5 gets a
      fixture from the ladder's configuration; its present one is from simple mode.
- [ ] **Paid extra usage:** a stand-in response with the header the CLI's bundle reads for
      it. Recorded: which header and value turn `isUsingOverage` away from `false`, and how
      the session goes on.
- [ ] **The placeholder tool:** what the CLI does when the model calls it.
- [ ] **Skills and agents:** the init event lists them although their tools are denied.
      Recorded: whether any listing of them is in the system blocks or tool definitions the
      model reads.
- [ ] The fixtures named in D5 take the new recordings; the simple-mode ones keep their
      content under a `simple-mode-` prefix, as the twenty-tool ones did.

**Verify:** `pytest -q tests/test_long_horizon_stub_api.py`; D5 and D7 are then rewritten
wherever a new recording differs, before Task 3 freezes them.

### Task 2b: measure, check and qualify the 16 on the pinned images (impl_code; 9 h plus about 16 h of machine time)

**Files:** modify `tasks.json` (image digests and sizes, the withholding result, overlay
digest, extra hosts, oracle evidence; the cap's home is `ladder.json`), `oracle_check.sh` (repeats, the two-key overlay,
the CPU set, the load gate) and `summarize.py` (counts); create `image_check.py` (pull, size,
export, listing and search; D1).

- [ ] The sub-id range is widened first, with no container running (owner question 4).
- [ ] **Measure:** the 32 pinned images, one at a time: pulled by digest, the size in the
      store recorded, the image deleted. If rootless Podman cannot pull one by digest, D1's
      fallback is recorded for that task.
- [ ] **Check withholding** on each of the 16 agent images, in the same pass (D1). A hit drops
      the task.
- [ ] **State the disk plan** in the ledger from the measured sizes (D1); if the images do
      not fit, the owner decides before anything more is pulled (question 6).
- [ ] **First pass (D1), any day:** each task once on its pinned images, reference and
      untouched, vba-userform-port first; the pinned CLI installed once on each pinned agent
      image; the affinity reaches both containers.
- [ ] **Second pass (D1), in the quiet window:** five and five under the final policy, four at
      a time. It also shows which verifiers report sub-tests.
      Its checklist, in this order (the Task 2b re-review's list, "what the second pass must do
      first"):
      1. [x] Fix N1, and test it through `check_task` at concurrency 1 and 4 (fix round 2).
      2. [ ] **Owner question 4 decided.**
         - Migrate route: run vba-userform-port unchanged once, both halves. The variant label
           retires; delete its two names by hand.
         - Otherwise: the variant label, never pooled.
      3. [ ] **Task 3's final allowlist** in place (a new overlay digest), and the CPU set the pass
         will freeze.
      4. [ ] **One round at four at once before the full pass:** the variant (or any task, if
         migrated) with `CONCURRENCY=4`, `REPEATS=2`, a fresh `JOBS`. Check:
         - `podman images` before and after: no image lost or untagged, `lh-oracle/…` still there
           or restored from the keeper;
         - no `podman rmi --force` of a shared image in the harness logs;
         - each record holds only its own trial's containers and egress;
         - peak memory and free space at four.
      5. [ ] **One real SIGTERM stop at four at once**, with the script's exit code captured
         properly (`wait "$pid"; rc=$?`): expect exit 5 and nothing left named after the four
         trials.
      6. [ ] **Then the pass itself**, in a quiet window: `REPEATS=5 CONCURRENCY=4 GATE=24` and the
         frozen `CPUS`. Use a new `JOBS` and `summarize.py --write` to a new records file. Qualify
         only on `qualifies` (which since fix round 2 also needs each reference's CTRF report to
         hold at least one test, all passed).
- [ ] A dry run of the contamination terms over these jobs and the recordings, then the terms
      are frozen.

**Verify:** `python -I experiments/long_horizon_tasks/summarize.py <jobs>` prints, per task,
reference 5 of 5 and untouched 0 of 5; `tasks.json` holds a size and a withholding result for
every image; the ledger gets the disk plan and the surviving list.

### Task 3: criterion and manifest (impl_code; 4 h)

**Files:** create `ladder.json` (model, efforts, CLI version, the token-mode switch, the deny
list, the output-token variable, harness versions and host-side overrides, package and image
digests, caps, ceiling, the schedule's one seed (it orders both the blocks and the efforts in a
block, D7.3), the smoke and pilot slots, allowlist, CPU set, load gate
and wait, the D5 table with the fixture each row cites, the refusal form, the two usage-limit
signals, readout rules, scan terms with the canary as a SHA-256, the
price rule with the table's hash and the five-minute write rate) and `manifest.json` (SHA-256
of every kit file). The manifest hash is the configuration label (D7). The allowance inputs
and readings are in neither. Tests: caps follow the formula and are equal across efforts; every field and value a
frozen rule matches occurs in a fixture; the price rule reproduces the three archives' totals.

### Task 4: the passthrough, the relay and the live probe (impl_code; 15 h, and 3 h for the probe)

**Files:** create `passthrough.py`, `token_scan.py` and `live_probe.sh`. Tests, with
`stub_api.py` as the upstream:

- [ ] **First slice: the request path.** It listens on a unix socket only. It maps a fake
      token to a slot and sets three header values (the real token, the vendor's host,
      `accept-encoding: identity`); no other header or body byte changes. It refuses, in the 403 form, an unknown token; a model other than the
      exact id (Sonnet, Fable, an alias); a request that declares a provider-side tool; a path
      other than the messages path; a request beyond a slot's priced cap, or beyond the total;
      and, for the live probe only, a request beyond a slot's request count (item 1; D4). A
      slot's token stays valid, and metered, until the launcher closes the slot; a token of a
      closed slot is an unknown token.
- [ ] **First slice: the meter.** It prices streamed and plain responses by the price rule,
      each cache write by its own lifetime; a response in flight at the cap is metered to its
      end. The priced caps above are enforced on this meter.
- [ ] **First slice: the token's path (D4).** The file is opened once, at start, and refused
      unless its mode and owner are right. The token is in no argument, log, request log,
      exception text or output; core dumps are off; proxy variables are ignored; with the
      rehearsal switch no token file is opened. Its log holds the rate-limit headers and never
      the `authorization` header. It writes the fingerprint.
- [ ] **First slice: the scanner and the canary.** `token_scan.py` finds a planted canary by
      the fingerprint and prints path and offset only. After a full session through the relay
      with the canary as the token, it finds nothing in the file set, and the runtime check
      finds nothing in any container's environment or file system.
- [ ] **The live probe** (below) runs on the first slice, through `live_probe.sh`.
- [ ] A vendor usage-limit answer is passed on unchanged (unless it carries a paid-usage sign,
      which is withheld, below), recorded with its reset, and closes
      starts; any other vendor 429 closes starts too; a vendor 401 is passed on and stops the
      tranche; a response that carries a paid-usage sign (D4: `overage-in-use: true` or an
      `overage-status` of `allowed` or `allowed_warning`, on any response; on a response other
      than a 429, a unified status present and other than `allowed` or `allowed_warning`)
      stops the tranche and is not passed on.
- [ ] The passthrough going down pauses the tranche.

**The live probe: a few requests of subscription usage, no dollars.**

*Authority.* It is not an attempt of the ladder and not under the ladder's approval. It runs
under the budget delegation of `AGENTS.md` and roadmap owner decision 18, by a coordinator
approval row in this plan's ledger written before the first request, in a fixed form:
`| <date> | Live probe approved | <the kit's commit> <the limits of item 1> |`. Its second
cell is exactly that phrase; its third cell starts with the kit's commit in full (40 hex
characters, then a space or a period: the last commit that changed
`experiments/long_horizon_tasks/`, which `live_probe.sh` takes as `LH_PROBE_COMMIT`).
`live_probe.sh` refuses to start unless exactly one table row of the plan has that form, and
its refusal prints the form; a sentence elsewhere that names the hash and the phrase does not
count.

*Who runs it.* A subagent, under that approval; its brief names the ledger row. The owner
starts nothing by hand except placing the token.

*Before it,* all of: the owner has placed the token by the safe procedure (question 1); the
owner's dated confirmation that paid extra usage is off; the owner's confirmation that the
subscription's terms allow unattended runs of this size; the first slice passes its tests,
the canary test among them; a reader who did not write the first slice has read it; the
coordinator's row.

*The rule line proposed for `AGENTS.md`* (experiment rules, after the ladder's line). This
plan does not apply it; the coordinator does, with the approval row:

```text
- The long-horizon live probe (approved by the coordinating session on <date> under the budget delegation below; roadmap owner decision 18) is limited to Task 4 of the long-horizon plan (docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md): three sessions of a scratch task that is none of the 16, one at each of effort `low`, `medium` and `high`, with no retry; at most 18 requests to `claude-haiku-5-5` on the owner's subscription, priced USD 0.15 per session and USD 0.45 in all; spent only through `experiments/long_horizon_tasks/live_probe.sh` on the passthrough's first slice, with that commit and the approval recorded in the plan's ledger before the first request. It reports measure-free figures only (whether the vendor accepts the token through the relay, the headers and usage fields it returns, priced cost) and makes no quality claim. It is not part of the effort ladder's approval; its priced usage is counted inside the ladder's USD 200.
```

1. **Requests.** Three sessions of the recordings' scratch task (not one of the 16;
   verification off), one after another, at `low`, `medium` and `high`. Each is the ladder's
   configuration exactly: CLI 2.1.311 in a task container, token mode with a fake token, the
   relay as base URL, the deny list, the allowlist of the recordings, model
   `claude-haiku-5-5`. Limits, enforced by the passthrough's meter: 6 requests and priced USD
   0.15 per session, 18 requests and USD 0.45 in all; the CLI's own budget at USD 0.10 per
   session. Expected: two to four requests per session and a few cents of priced usage, which
   is settled into the USD 200.
2. **Recorded.** Per request: the vendor's status, every rate-limit header and `retry-after`
   as sent, any header that reports paid extra usage, the response's model, and its usage with
   the cache split and service tier. Per session: the init event, every `rate_limit_event`,
   the result's `total_cost_usd`, `usage` and `modelUsage`, the egress log, and the first
   request's prompt tokens (what the default system prompt and tools cost per request). From
   the owner: when the token was created and the lifetime `setup-token` stated. For the
   paid-usage stop (D4): whether `anthropic-ratelimit-unified-overage-status` appears on
   ordinary responses, and with which value; the name of every response header, and the value
   of every `anthropic-*` header; and per session the key
   `cachedExtraUsageDisabledReason` in the exported configuration file
   (`agent/sessions/.claude.json`). If ordinary responses carry `overage-status`, the stop's
   `overage-status` clause is revised under a new coordinator row before any ladder attempt. The
   passthrough's request log keeps each request's beta flags, cache marks and declared tools,
   so a fall back to five-minute caching can be seen. Kept with the
   recordings, by SHA-256, with fixtures cut as for the others. The token is never kept.
3. **Stop rule.** The probe ends after the third session, or at once at the first of: a vendor
   status other than 200 (no second try under this approval); a response that names another
   model; a connection outside the allowlist that was not refused; a limit of item 1; a sign
   of paid extra usage. A 429 met by chance is recorded as the vendor's limit answer and ends
   the probe.
4. **A pass** is all of: the three sessions end `completed`; every request of the three
   session files is in the passthrough's log, went out with the real token and was answered
   200 by `claude-haiku-5-5` at the session's effort; the passthrough's priced figure equals
   the CLI's `total_cost_usd` within 1% in each session; the egress logs show the relay and
   refused connections only; `token_scan.py` finds nothing in its file set and the runtime
   check nothing in the containers.
5. **Three ways to fail, with different consequences.**
   - *The route fails:* the vendor refuses the token or the request (a 401 or a 403 of its
     own). The plan stops before the rest of this task and before Task 5, and the owner is
     told; no other credential route is open.
   - *The metering fails:* the 1% test, or a subscription result without the cost fields. The
     route stands. Settlement and the price rule are revised from the recorded usage, and a
     second probe needs a new coordinator row.
   - *The token is found by the scanner:* a stop. The owner revokes and replaces the token
     (D4) before anything else runs.
   A 429 met by chance is none of these: the probe is run again after the reset, under a new
   row.
6. **What it cannot show.** A usage-limit answer, unless it meets one: that is recorded when
   it first occurs (D4). How long the token lasts: that rests on what `setup-token` states and
   on each later week's first request.

### Task 5: the launcher (impl_code; 23 h)

**Files:** create `ladder.py`. **Interface:** `ladder.py plan | launch | status | allowance`.
A live launch needs `LH_SPEND_AUTHORIZED=yes`, `LH_MANIFEST_SHA256` and `LH_RUNTIME_COMMIT`
(both from the ledger); the token file is named only to the passthrough, and the harness's
environment holds no credential. A rehearsal needs `LH_REHEARSAL=<dir>` and refuses if a spend
variable is set. State lives outside the checkout (`$HOME/.local/state/lh-ladder`; another root
for rehearsals): one directory per slot, claimed by `mkdir`, with the reservation, the fake
token, the launcher's pid and start time, and later the settlement; and the allowance inputs
and meter readings with their history. It runs from a detached checkout of the frozen commit and reuses the
package's usage reader and price table.

Tests, against a stand-in harness that replays the recorded fixtures on a closed `PATH`:

- [ ] Refusals: no authorization; a manifest or runtime commit other than the ledger's; a dirty
      kit; a model or effort outside the criterion; a task whose digest differs outside the two
      overlay keys, or whose image digest differs; another harness environment or a missing
      host-side override; an allowlist that names an address of the host; a rehearsal with a
      spend variable; no allowance inputs; a manifest hash that is not the ledger's current
      label; a slot without a fake token in the launcher's form (an empty token ends before the
      session as a `RuntimeError` naming `CLAUDE_FORCE_OAUTH`, `token-forced-empty-RuntimeError`).
- [ ] Money: sixty concurrent launches never commit more than the ceiling; a slot that does not
      fit waits and is never skipped; start 241 is refused, a rerun after a cut included;
      settlement takes the largest of four figures, never reads the result's `usage`, and
      counts a message id once; unreadable usage settles at the full reservation.
- [ ] Classification over every fixture, by the rows of D5 in order: endings of one harness
      class are told apart; a usage limit is decided by the passthrough's log, so a slot whose
      log holds signal 1 is cut whatever the CLI's result says, and a session with signal 2
      alone pauses; an ending with no row pauses. A slot cut by a usage limit is run again as
      a new counted start at the head of the queue and its reward is never read; a slot whose
      session ended in any other way is never launched again; a slot is lost after its third pre-session failure; a
      regrade never starts the agent; reconcile stops only the containers of a dead launcher
      (pid and start time both match).
- [ ] Allowance: a limit answer closes all starts, and they reopen five minutes after its
      reset with one start; an answer with no reset pauses; three limit answers in a row stop
      the tranche; **no start in a window that has no meter reading**; the budgets are computed
      from the reading and floored at zero; a window whose weekly reading is at or above the
      skip threshold is skipped and reported; no start when the weekly or the five-hour budget
      does not hold the guard's reservation of every open slot and of this one; no start
      outside the owner's hours or in a window's closing margin; a sign of paid extra usage in
      a session's stream stops the tranche; a reading or a change of the allowance inputs is
      recorded and leaves the manifest hash alone.
- [ ] Host: the load gate waits, and pauses after two hours with nothing in flight; low disk
      stops the tranche; the egress log is followed out before teardown; a slot is closed, and
      its fake token retired, only after the launcher has seen every container of the attempt
      removed, and the CLI's requests after a time limit are metered into the attempt (D4, a
      slot's lifetime); the harness command
      carries model, effort, version, cap, the token-mode switch, the deny list, the
      output-token variable, the relay's base URL and zero retries; no credential is in any
      file, environment or command line; the token scanner and the runtime check run at every
      teardown, and a match stops the tranche; beside them the contamination scan of D6 runs with
      the frozen terms and writes the SHA-256 of each term it finds into the slot's record
      (`slot_record.py`, the one layout of the export the readout reads). The schedule is deterministic and in blocks,
      begins with the smoke slot and then the pilot's block, and waits for the smoke read, the
      pilot's ledger row and the round-one read; cut at any start, it leaves at most one block
      partial and no task more than one block behind another.
- [ ] Connections: the passthrough's cap of 16 connections is shared by every slot (a
      connection counts before its token is read); before four sessions run at once, the
      launcher decides whether each attempt gets its own passthrough socket (and relay) or the
      cap is raised per slot. **Decided (Task 5): each attempt gets its own socket.** The
      launcher marks every slot `"own_socket": true` in the slots file; the passthrough serves
      such a slot on `<its socket's directory>/<slot>/passthrough.sock` with a cap of 16
      connections of its own, refuses that slot's token on any other socket and any other token
      on it (`unknown token`), and removes the socket when the slot is retired; the attempt's
      relay mounts that directory (`LH_RELAY_SOCKET_DIR`). Reason: the agent controls its
      container and reaches the relay, so it can hold connections open; under one shared cap
      they would turn another attempt's requests into load refusals (row 15, an infrastructure
      failure, never rerun; three of them pause the tranche), and a cap raised per slot cannot
      be applied before the token is read. With a socket per attempt a connection is counted
      against its own attempt before any byte is read. The main socket stays for the live probe.

**Verify:** `pytest -q tests/experiments/test_long_horizon_launcher.py
tests/experiments/test_long_horizon_passthrough.py tests/experiments/test_long_horizon_ladder.py
tests/experiments/test_long_horizon_slot_record.py tests/experiments/test_long_horizon_readout.py`
(the launcher's tests are in their own module, `test_long_horizon_launcher.py`;
`test_long_horizon_ladder.py` holds the criterion's; the export is checked against
`slot_record.py`, which the readout also reads), `--collect-only` on the launcher's module, then
the sampled broad check.

### Task 6: the readout (impl_code; 9 h)

**Files:** create `readout.py`, and `slot_record.py`: the export's layout and its loader, the one
definition the launcher writes and the readout reads. Tests: intervals match the report's table; cell and pooled
labels; the band effort is defined for every screened-in pattern; the effort verdict and the
bound on the fall on constructed tables; a ceiling stop leaves partial rounds out of complete
triples; exclusions are listed and never scored zero; cuts are counted per effort and the
pilot's attempts marked; observations under two labels are never pooled, an earlier label's
are printed apart and enter no rule, and a short cell is printed with its count; the graded outcome is printed and enters no rule; the allowance
figures are printed and enter no rule; a stop readout prints no placement; `family.json` names
the criterion, the configuration and the digests. After review: a launcher stop on any row is
never scored; contamination on a start of any class; a task screened with at least four scored
observations at each effort and "not screened" below; the final readout refused unless the
manifest is frozen and matches.

### Task 7: zero-spend rehearsal (impl_code; 8 h)

- [ ] In the suite: the whole schedule against the stand-in harness, ending inside both caps,
      with a usage limit in the middle: starts close, the cut slots are run again after the
      reset, and the counts hold.
- [ ] On containers, with the rehearsal switch (the passthrough opens no token file and holds
      a canary of the real token's shape): three tasks with the real pinned CLI in the ladder's
      configuration, the relay, the passthrough, and `stub_api.py` as its upstream. One session runs to a budget stop, one
      past a shortened time limit, one is cut by the stand-in's usage limit and its slot run
      again, one is killed and reconciled, one verifier is regraded.

**Verify:** the D7 smoke checks on the rehearsal's records; the canary test of D4: planted, the
canary is found; after the sessions, `token_scan.py` finds it nowhere in the file set and the
runtime check in no container's environment or file system. Results go in the ledger.

### Task 8: independent pre-spend review (review_code; 6 h, plus 6 h of fixes and re-review)

By a reviewer who wrote none of the kit; the passthrough, the relay and the token scanner are
in scope. Its brief
lists the holes earlier reviews and the recordings found: a retry that turns a failure into a
pass; a CLI that updated itself after the pin; a sweep that matched a reused pid; a launch
between reservation and record; a runtime commit recorded but not enforced; a rule written for
output nobody had observed; an identity check the overlay defeats; a credential an agent can
reach; an allowlist entry that opens a whole host. This revision adds: a model the token
allows and the passthrough lets through; a limit taken for a model failure, or a model failure
taken for a limit; a rerun that reads the cut session's reward; a guard that starts attempts
into an exhausted allowance or a window with no reading; the real token in a log, an exception
text, a core dump or a pane; a scanner that cannot find what it is given; observations of two
labels pooled in one cell. Each guard is mutated.

### Tasks 9 to 12: freeze (1 h), smoke and pilot (4 h), the run (about 12 h of attention), readout and step 7 (12 h)

Before the first attempt the ledger holds: the surviving tasks with package, image and overlay
digests, image sizes and withholding results; the disk plan; the manifest hash, which is the
first configuration label, and the runtime commit; the CLI and harness versions; the price
rule and table hash; the network policy; the live probe's result; when the token was created
and the lifetime stated; **the owner's dated confirmation that paid extra usage is off; the
owner's confirmation that the subscription's terms allow unattended runs of this size;** the
owner's two shares and hours; the first window's meter readings; the review verdict; the
rehearsal result with the canary test; priced usage to date. After the pilot it holds the
meter readings, the two guard figures, the guard's reservation, the attempts a week can hold
and the number of weekly windows. Every later window adds its readings.

**Machine and calendar time.** The attempts themselves still need about 35 to 45 hours of a
quiet host at four concurrent attempts, up to about 60 when the ladder's own load holds it to
two or three. Those hours are no longer one window: they are spread over the weekly windows
the pilot implies, inside the owner's hours, with a wait at every usage limit and no start in
a window without a reading. How many weeks that is cannot be said before the pilot. Before
them: about 3 hours to measure and check the images, about 3 for the first oracle pass at any
load, about 10 quiet hours for the second, and up to 8 hours for the pilot. Everything runs in
tmux, except the passthrough, whose output goes to a file (D4). The last task writes
`results/readout.md`, `family.json`, a report under `docs/reports/`, the priced usage and the
allowance used in the ledger, and the roadmap's step table; 8 of its 12 hours are step 7's
failure labels by two readers.

**Hours in all:** about 133 of engineering and review. About 14 are done (Task 1, and the
first part of Task 2 at the 6 hours the second revision allowed for it; the time was not
logged). About 119 are still to do, against 79 for the same remainder before the third
revision. The third revision added 24: the recordings in the ladder's configuration 5, the
criterion 1, the passthrough 2, the live probe 3, the launcher's limit handling and allowance
guard 4, the readout 1, the rehearsal 1, the review 1, the pilot 2, and a run spread over
weeks 4. Its review added 16: three more recordings 2; the image measurement and withholding
check 3; the token's closed path, the scanner and the probe's launcher 3; meter readings,
blocks and labels in the launcher 3; labels in the readout 1; the canary in the rehearsal 1;
the review 1; the readings of each window 2. Machine time is beside these.

## What This Makes Harder

- The family is tied to one benchmark, harness and CLI version, one network policy and one
  configuration: token mode, the deny list, the default system prompt. A later comparison must
  reuse all of them or re-qualify, and step 9 must say which tools its staged arm's sessions
  get. Nothing here can be set beside the public leaderboard.
- **The owner is in the loop for the whole tranche:** a meter reading at each weekly reset and
  before each window, or nothing starts. That is the price of a guard that cannot see the
  meters.
- **The tranche's calendar time is set by the owner's share of one account's allowance, not
  by the machine.** The allowance figures belong to this subscription plan and carry to no
  other. A tranche of weeks is exposed to things a tranche of days was not: the pinned CLI
  being withdrawn from the vendor's download host (a stop: another version is another
  configuration), an image leaving its registry (kept for the tranche if the disk allows; D1),
  a change of the vendor's limits. A repair during those weeks makes a new configuration
  label, and the cells of the old one are not refilled (D7).
- The passthrough and its relay are reviewed code that every later long-horizon run needs, and
  the passthrough now holds a credential that is good for every model of the account.
  Reservations far above expected cost leave the last USD 10 to 25 unusable. No agent retry
  means provider incidents reduce n for good, and each usage-limit cut uses up a start.
- Task files and recordings live outside the repository: a clean clone fetches them by digest.

## Not Verified While Planning

**No longer listed here,** because a recording now shows it and D2 to D5 cite it: the
allowlist under rootless Podman, setup on the open network, the egress log, the misrouted
request, the CLI's install and version, model pinning, the verifier after a timeout kill, the
separability of pre-session failures, the relay route, the provider-fault endings, the price
rule, the 4.1.0 digests, and token mode's hosts, headers and result fields against a stand-in.

**Before the launcher is written:**

1. The ladder's configuration, recorded at no spend (Task 2a): the endings, the init event's
   tool list, the size of the system prompt and tools, the cache lifetimes, the 403 form for
   the model and tool refusals.
2. The live probe (Task 4): the vendor accepts the token through the relay and the
   passthrough; `low` and `medium` are accepted for this model; the rate-limit headers on
   ordinary responses; what a subscription session reports as usage; the prompt tokens every
   request carries.
3. The pinned images (Task 2b): they pull by digest under rootless Podman, their sizes, that
   the disk holds them, that none holds a reference solution, a verifier test or the canary,
   that the references pass on them, and that the pinned CLI installs on each.
4. The contamination terms give no false hit on the oracle jobs and the archives.
5. The host plan: the affinity reaches both containers; the quiet hours; the sub-id widening.
6. Which verifiers report sub-tests; the training cutoff on the vendor's page itself.

**At the rehearsal:** the verifier runs after a budget stop on Podman; a regrade on Podman; kill
and reconcile; a limit, its pause and the rerun, on the stand-in; no credential in any
container, file or command line.

**At the smoke, the pilot or in round 1:** what an attempt costs against the allowance, and
whether priced tokens track it (the pilot is one reading); cost per effort (`low` and `high`
are interpolated); provider errors and ordinary rate limits at four concurrent sessions on a
subscription.

**Only when it happens:** the vendor's real usage-limit answer, in its five-hour and its
weekly form, with its reset time; the vendor's real sign of paid extra usage, which the plan
means never to see; the token's end.

**Owner preconditions, not facts the plan can establish:** that paid extra usage is off, and
that the subscription's terms allow unattended runs of this size. The plan did not read the
terms; it uses only the CLI's own token mode and base URL. An action by the vendor against the
account would stop all of the owner's work, which is worse than a usage limit.

**Not probed, or not knowable by reading:** the sidecar's handling of name lookups and ping
(source read); whether a verifier can reach the relay by its address; whether the 15-second
reset of a stalled first byte is the CLI's or a hop's; the model's real prompt limit (the
largest recorded prompt is 443,427 tokens); which meters the account shows and how finely;
how a token is revoked; whether `setup-token` leaves a copy of the token anywhere but the
terminal; whether the directory chosen for the token is backed up or synced; the benchmark's
licence beyond its text (Apache-2.0, with a canary
asking that data stay out of training sets).

## Rulings

The planner's eleven rulings, adopted with the reviewer's amendments (2026-11-13), are the
rules of D1 to D7 as revised; the coordinator's rulings of all three revisions are in the
ledger. All thirteen review minors are applied; minor 8 (the training cutoff) rests on a
search result until the vendor's page is read.

The independent review of the third revision (accept after fixes: 1 blocker, 7 majors, 14
minors) is applied in full, with the coordinator's rulings where a choice was needed (ledger).

**What the third revision changed in the frozen decisions.** D1: the pinned images, their
measurement and withholding check, the oracle evidence redone on them, seven tasks marked as
changed since the public row. D2: token
mode with a deny list in place of simple mode. D3: nothing but the wording on web tools. D4:
the subscription token, its closed path and the one header, usage limits and an allowance
guard that reads the owner's meter, the stop for paid extra usage, the settled price rule,
the one refusal form, the guard table in usage. D5: rebuilt on `api_error_status`
and the passthrough's prefix, with the usage-limit cut and its rerun. D6: cuts and pilot
attempts marked, no public figure as reference, one configuration label per cell, the
allowance reported. D7: the pilot, blocks and the fixed drop order, configuration labels, the
stops and pauses for limits. **What did not depend on the public row:** the candidate list
(the 16 are named in the approval), the caps as numbers, the placement and effort rules of
D6, and the fixtures of Task 1, which were cut from recordings and stay true of what they
recorded. **What did:** D2's configuration, the fixtures D5 cites, and the owner's numbers in
the size section.

## Owner preconditions and questions

Only what the approval does not cover. The earlier question 1 (an API key in a capped
workspace) was answered by decision 18; its text is in this file at `a4674efa`.

**Preconditions.** Each is written in the ledger with its date. Nothing below it starts
without it.

| Precondition | Before |
| --- | --- |
| The token is in place, by the procedure of question 1 | The live probe |
| The owner confirms that paid extra usage is off for the account | The live probe, the pilot and the freeze (confirmed again each time) |
| The owner confirms that the subscription's terms allow unattended runs of this size | The live probe, and again in the freeze's ledger list |
| The owner's two shares and hours (question 2) | The smoke |
| The meter readings for the window | Every window, the smoke's and the pilot's included; with none, nothing starts |
| The disk decision, if the images do not fit (question 6) | Any pull beyond the measurement |

**State of the token (ledger rows of 2026-11-14).** In place: the owner placed it on 2026-11-14
and replaced it the same day, after its value had been pasted into the coordinating session.
The ledger holds the file's path, mode and size, the time, and the lifetime the command stated
(one year); never the value. The owner used a script that follows the steps of question 1 and
reads the token at a hidden prompt; the script is not in this repository, and the steps below
are the procedure of record. Replacing the token is D4's step ("The token's path", item 2).
Step 8 of question 1 asks how the token is revoked: the vendor documents no way, so whether
the disclosed token was revoked is open, and unrevoked it may stay valid until 2027-11-14.

**Questions.**

1. **The token, by a procedure that keeps it away from every agent.** This session and its
   subagents read tmux panes and keep transcripts, so:
   1. Open a fresh terminal window. Not a tmux pane, not this session's command prefix.
   2. Choose a directory outside every repository and outside anything synced or backed up,
      and tell the coordinator its path. **Is that directory backed up or synced?** If your
      whole home directory is, name a place that is not.
   3. `umask 077`, then `mkdir -m 700 <directory>`.
   4. Run `claude setup-token` and follow it. Note the lifetime it states.
   5. Run `install -m 600 /dev/stdin <directory>/token`, paste the token, press Enter, then
      Ctrl-D. The token is typed into the command's input, never onto a command line.
   6. Check: `stat -c '%a %U' <directory>/token` prints `600` and your user.
   7. Clear the terminal's scrollback and close the window; clear the clipboard, and a
      clipboard manager's history if you run one.
   8. Never paste the token into a chat or an agent session. Tell the coordinator only: the
      path, the time, the stated lifetime, and how the token is revoked.
2. **The account's limits.** The ladder draws on the same allowance as your sessions and the
   coordinating session.
   - May it start attempts while you work, or only in named hours, and which?
   - What share of the **weekly** allowance must stay free for your own work? And what share
     of the **five-hour** allowance? They are two numbers.
   - When does the weekly window reset, and which meters does the account show?
   - **Will you read the meters at each weekly reset and before each window of hours opens,
     one line each time?** The ladder uses only what is left above your share at that reading,
     and it starts nothing in a window without one.
   - You would also read them before and after the pilot (three attempts, up to eight hours,
     best with nothing else on the account) and at the end of round 1.
   **If the guard fails, your sessions and the coordinating session stop until the weekly
   reset.** And for scale: about 220 to 235 of the 240 attempts are expected before the USD
   200 ceiling ends the tranche, so the last round is likely incomplete.
3. **Quiet machine time, re-estimated.** Once, about 10 hours for the oracle check. Then the
   attempts' 35 to 45 hours (up to about 60), no longer in one window: spread over the weekly
   windows the pilot implies, inside the hours of question 2, the load at or below 24 while
   attempts run. Without quiet hours the ladder does not run on this plan. The results that
   would otherwise measure the neighbours are those of wal-recovery-ordering (a thread-timing
   verifier; its reference failed once under load) and, likely but untested,
   vf2-speedup-networkx (a speed target) and the tasks that train or compile inside their
   limits (lake-temp-glm, pretrain-shard-corruption, vpp-loss-divergence, retro-console-soc).
   A smaller tranche without those six is a choice the owner could make.
4. **Two root commands.** Widening the sub-id range (report §5), with no container running;
   without it vba-userform-port runs with the one-line verifier change, labelled. Optionally,
   delegating the CPU-set controller to this user, which turns D2's affinity into a reservation.
5. **Tasks outside the 16.** Fewer than ten screened-in tasks is about as likely as not.
   Replacing a dropped task or adding tasks (the Science suite, the compose tasks) is not
   covered and needs its own ladder and its own approval. Does the owner want a rule for a
   later tranche?
6. **The disk, if the 32 pinned images do not fit** above the 20 GB stop (Task 2b measures
   them first): free space, name another disk for the image store, or accept that images are
   pulled and deleted block by block, which ties the tranche to the registry for its weeks.
7. **Step 9** will be requested once, after step 7, with the size and cost above.

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
| 2026-11-13 | Owner ruling on the credential: "subscription only. No api key for this or anythning else" (roadmap decision 18) | Owner question 1 is answered: no API key is created. **D4 and the guard table are not yet revised and must be before Task 5 starts.** What the revision settles: (1) the passthrough holds a subscription token (from `claude setup-token`, an owner action) and no container holds any; the CLI in the container keeps a dummy credential; whether it runs in key mode or in token mode with a dummy token is decided by a no-spend recording against the stub (which headers and extra endpoints token mode uses); (2) one live probe, a few requests of usage and no dollars, shows that the vendor accepts the token through the relay and the passthrough, before the launcher is built on it; (3) the workspace spend limit named as a precondition no longer exists: the USD 200 ceiling and every reservation are priced-token caps enforced by the passthrough and the launcher alone, and the guard table's worst cases are restated in usage, not money; (4) the subscription's session and weekly limits are shared with the owner's own sessions and with the coordinating session: the launcher pauses at a limit and resumes at the reset, an attempt cut off by a limit is an infrastructure failure that is rerun and never an observation, and the plan states the expected stretch of the 35 to 45 hour window; (5) owner question 1 becomes: create the token, and say whether the ladder may use the account's limits while the owner works. Spend to date: 0. |
| 2026-11-13 | Third revision, after owner decision 18 and the Task 2 probes (no spend); awaits the coordinator's acceptance | Coordinator rulings applied. (R1) The CLI in the agent's container runs in token mode with a fake token and the relay as base URL; the passthrough replaces the bearer token and nothing else. The ladder no longer runs the public row's simple mode, which refuses a subscription token: it measures the CLI as a subscription user runs it, held to Bash, Edit and Read by `--disallowedTools`, with the default system prompt. The public per-task rates only chose the candidates; the ladder's own measurement is the only evidence of difficulty. Key mode with a rewriting passthrough is rejected. (R2) One live probe before the launcher: three sessions of a scratch task, at most 18 requests and priced USD 0.45, `claude-haiku-5-5` only; specified in Task 4; **not approved by this row**: it needs the owner's token and a coordinator approval row. (R3) A usage limit is recognised by two signals; attempts cut by one are excluded and their slots run again, each rerun counting against the 240; starts pause until the reset and reopen by themselves; an allowance guard keeps the owner's declared share free, from the owner's three inputs and the pilot's figures. (R4) A pilot of three attempts (rs-archive-clone at each effort), inside the 240 and the USD 200, through the reviewed launcher, with the owner's meter readings before and after; they are observations of the ladder; the tranche is scheduled over the weekly windows it implies. (R5) Every dollar figure is a priced-token figure under the settled price rule (cache writes by lifetime, five times above 100,000 prompt tokens); one refusal form (403 `permission_error`, `lh-passthrough:` prefix); D5 rebuilt on `api_error_status` and that prefix; the guard table restated without a workspace limit. (R6) The 4.1.0 packages run on their digest-pinned images; all oracle evidence is redone on them in two passes; seven tasks are marked as changed since the public row's 4.0.0. (R7) Owner questions rewritten: the token, the account's limits, quiet machine time. (R8) Expected priced usage about USD 182 to 192 (range 150 to 285), so the ceiling is more likely than not to end the tranche before attempt 240. Hours: about 117 in all, about 103 still to do. Spend to date: 0; subscription usage to date: none. |
| 2026-11-13 | Third revision revised after its independent review (accept after fixes: 1 blocker, 7 majors, 14 minors); no spend; awaits the coordinator's acceptance | Every finding applied, with the coordinator's rulings. (B1) The allowance guard reads the owner's meter: a reading at each weekly reset and before each window; the window's budget is (100 − F − the reading) times the pilot's figure, floored at zero; a window is skipped at a reading within five points of the owner's share; the five-hour meter likewise with its own F; with no reading nothing starts. (M1) The live probe is not under the ladder's approval: its authority is the budget delegation and decision 18, by a coordinator approval row written before the first request; a subagent runs it through `live_probe.sh`; the rule line proposed for `AGENTS.md` is in Task 4 and is not applied by this revision. **This row does not approve the probe.** (M2) The meter is in the passthrough's first slice, before the probe. (M3) The token's path is closed by construction: the owner's creation procedure away from every agent; one read at the passthrough's start; never in arguments, child environments, logs, exception text, recordings or core dumps; a scanner that works from a salted fingerprint over a named file set and the attempt's containers; a canary test. (M4) The owner's dated confirmation that paid extra usage is off is a precondition of the probe, the pilot and the freeze; the stop for it is stated as acting after the first paid request. (M5) The manifest hash is frozen before the smoke and is the configuration label; a change after the pilot's first attempt is allowed only for a safety or correctness fault, by a ledger row before the next start; labels are never pooled in a cell; the 240 and the USD 200 do not restart; short cells are reported with their count. The schedule runs in blocks (a task's three efforts together) and the drop order at the ceiling is its hashed tail, at most one block partial; about 220 to 235 starts are expected. (M6) The 32 pinned images are measured one at a time before any plan for the disk; the fallback of a local build is a different configuration label. (M7) Each pinned agent image is checked for `solution/`, `tests/` and the canary before any use; the canary is never copied into this repository. Minors m1 to m14 applied; the owner's confirmation that the subscription's terms allow unattended runs of this size is a precondition before the probe and in the freeze's list. Hours: about 133 in all, about 119 still to do. Spend to date: 0; subscription usage to date: none. |
| 2026-11-13 | Third revision accepted by the coordinator (`16ff49e4`, merged as `96adb33d`) | The independent review's blocker, seven majors and fourteen minors are applied. Acceptance covers the plan, not any use of the subscription: the live probe needs the owner's preconditions 1 to 3 dated in this ledger, a non-author read of the passthrough's first slice, a coordinator approval row and its line in `AGENTS.md`, all before the first request; the pilot and the tranche need the further conditions the plan lists. The coordinator's rulings kept where they differ from the reviewer's: a kit change after the pilot's first attempt starts a new configuration label and is allowed only for a safety or correctness fault (M5); image sizes are measured by pull and delete (M6). No-spend work may start: Task 2a's re-recordings in token mode and the image measurement. Spend to date: 0. |
| 2026-11-13 | The recording kit of Tasks 1 and 2 merged to `main` (`experiments/long_horizon_tasks/`) after an independent review (accept after fixes: one major, eleven minors; all applied), the coordinator's scan for credentials, long vendor text and machine paths, and the full suite (8 failed: the four nanoBragg baseline tests and four load-sensitive tests that passed alone) | Committed: cut fixtures of the CLI's endings and of its requests (field names, counts and lengths; no prompt text, no credential), the stub, the scripts, the price rule and its check. Not committed: the raw recordings, which stay in the local cache with their hashes in `recordings.json`; the cache is not backed up. No benchmark content is in the repository. The recordings are of key mode in the three-tool configuration and of token mode with the default tools; Task 2a re-records in the configuration the third revision fixes. Spend to date: 0. |
| 2026-11-14 | Task 2b, image measurement and withholding check (no spend; `experiments/long_horizon_tasks/image_check.py`, `image_measure.json`, RECORDINGS.md "Task 2b") | All 32 pinned images pulled by digest on the first attempt; the only host-side step was the `docker.io/` full name. Each was measured and then deleted, one at a time. Store sizes, each distinct layer counted once: all 32 kept, 23.86 GB (253 layers); agent images only, 11.46 GB; block by block, at most 4.64 GB (vpp-loss-divergence); block in flight plus the next, at most 5.45 GB. Free on `/home` (the image store) 78.45 GB before and 77.55 GB after (2026-11-14, about 13:00), so keeping all 32 left about 53.7 GB, about 33.7 GB above the 20 GB stop before the attempts' output. The margin drifts with other sessions' writes: at 71 GB later the same day it was about 47 GB, 27 GB above the stop. Withholding: no solution or test file by path or SHA-256 in any of the 16 agent images. The canary was absent from 9 images. In the other 7, every file holding it is a byte-identical (SHA-256) copy of a file in the task's own `environment/`: vba-userform-port 1, wal-recovery-ordering 15, session-window-debug 8, vpp-loss-divergence 2, batched-eval-parity 17, pretrain-shard-corruption 4, sound-change-cascade 1. That was shown by a second pull and check of all 16 agent images. There were no name-only matches (none "needs a look") and no other file held it. Under the coordinator's ruling of 2026-11-14 (a canary in a byte-identical environment copy is not a hit), no task is dropped. `tasks.json` is not yet updated with sizes or results. Spend to date: 0. |
| 2026-11-14 | Task 2b fix round 1, after the independent review (approve after fixes: one major, ten minors; no spend) | **Near-copy check (M1)** on all 16 agent images, pulled again one at a time under the 25 GB stop. **Method:** a line counts as distinctive when it has at least 25 characters and occurs in the task's `solution/` or `tests/` but in no `environment/` file. Text files are matched against those lines; archives, wheels, tars, single-file gzip and loose `.git` objects outside system paths are opened when 64 MiB or smaller; every layer is walked, deleted files included; every member of the merged file system is path-tested, whatever its type. **Rule:** a match outside system paths needs a look, and so does a system-path file with 10 or more matched lines (the 16 images show at most 6). **Result:** no solution or test material by path or SHA-256, in any image or layer. Three things need a look, each listed in RECORDINGS.md "Task 2b": the `app/.git` of pretrain-shard-corruption and of shadow-relay, both built by the environment's Dockerfile, all objects loose and opened, no hit; and in roy-polymorph-cn, two pip console-script wrappers in `opt/venv/bin` that each share one generic main-guard line with the solution. **Disk, corrected (m6):** the worst case over any choice of blocks, because D7's seed is not frozen: 4.64 GB for one block, 7.76 GB for two, 10.84 GB for three, 13.30 GB for four; all 32 kept stays at 23.86 GB, agent images only at 11.46 GB. **Other fixes:** never `rmi -f`, and no image deleted that was in the store before (m4); the package digest checked, and a missing package is an error (m5); Podman's error text kept and a failed clean-up reported (m7); the pull guarded by the disk stop (m9); a private scratch directory and a test that reads a tar (m10); RECORDINGS.md corrected (m1 to m3). The Task 2b "Files" line now names `image_check.py`, and D1 states the near-copy check and the canary ruling. No task is dropped by this row; the three items above await the coordinator. Spend to date: 0. |
| 2026-11-14 | Coordinator ruling on Task 2b fix round 1, and the records regenerated (no spend) | **Ruling:** none of the three items that needed a look is a withholding hit, and no task is dropped. They are the two pip launcher scripts in roy-polymorph-cn, each sharing one generic main-guard line with the solution, and `app/.git` in pretrain-shard-corruption and in shadow-relay. Each `.git` is built by the environment's own Dockerfile; every object was loose and opened, with no solution or test content (evidence in RECORDINGS.md "Task 2b"). **Rule:** a virtual environment, meaning any directory holding a `pyvenv.cfg` and everything below it, is a language directory; the near-copy threshold for system and language paths stays 10. **Regeneration:** all 16 agent records were regenerated by the committed code, one image at a time under the 25 GB stop. Every verdict equals the one predicted from the earlier records under the final rule; roy-polymorph-cn's launcher scripts are now noise. The result: no file needs a look; no solution or test material by path or SHA-256 in any image or layer; canary only in byte-identical environment copies. Free space at the end: `/home` 70 GB, `/` 50 GB; the lowest checkpoint in the file is 68.25 GB and 51.43 GB. Spend to date: 0. |
| 2026-11-14 | Image measurement and withholding check accepted (independent review and scoped re-review: approve; branch `feat/long-horizon-image-measure`) | All 32 pinned images pull by digest; keeping all needs 23.86 GB. No solution or test material in any of the 16 agent images by path, SHA-256 (every layer, deleted files included) or distinctive line; every canary file is a byte-identical copy of an environment file. **Known limits, accepted:** (N1) a solved file written by a script and stored somewhere other than its place in the environment is not seen by line matching when the fix sits in string literals or in lines under 25 characters (the reviewer applied two solutions in scratch containers: one patched file matched 0 lines); the oracle's untouched run covers a solved file left in place, and 80 of the 85 solution text files that are not environment copies carry the canary, which is checked on every path. **For Task 2b, when it fills `tasks.json`:** (N2) carry the ruling that `app/.git` in pretrain-shard-corruption and shadow-relay is not a hit into the result, which still says "needs a look"; (N3) list any text file over 64 MiB that the line check skips; (N4) D1's sentence must state the 10-line rule for system and language paths, that the layer walk is by path and SHA-256 only, and that archives inside system and language paths are neither opened nor listed (confirmed as the intended scope). Spend: 0. |
| 2026-11-14 | Seeds of step 8 revised after their independent review (`experiments/long_horizon_seed/`; no spend) | The four seeds take two inputs, the task text and the intent; models (`claude-haiku-5-5` for every role), efforts and loop bounds are literals at the call sites; the setup step returns typed paths, so a missing guide fails it; the stand-in scenarios are `tests/experiments/test_long_horizon_seed.py`; registry rows are in `workflows/README.md`. Known gap, stated in the header comments of `milestones.orc` and `roles.orc`: nothing reads a milestone's verdict, so a milestone refused twice is built upon and its reasons do not reach the planner. The fix needs the list operator `list/any`, which is being added on another branch: when it merges, both seeds change (a round stops at a refused milestone and passes its reasons to the planner) and their digests with them, so the freeze of step 8 and the hash in the family record wait for that change. Measured at 120 columns, three of the four seeds exceed the 50-line figure of step 8; the budget question is with the owner. |
| 2026-11-14 | Seeds of step 8, second fix round after the scoped re-review (no spend) | Later steps are given the guide path the setup step reported (and the round plan the log path) as typed fills, so the setup's check is of the file the later steps read. An exhausted design loop in `designed.orc` ends the run `BLOCKED` with the reviewer's reasons; nothing is built on a design refused twice. A round that fails the check keeps the notes of the rounds before it. `experiments/mutants/check.py` binds `repo` only for an entry that declares it, so the reuse readout runs on these seeds. Sizes at no more than 120 columns: `staged` 34 lines, `milestones` 47, `roles` 50, `designed` 65 (over the figure of step 8, left over as ruled). Still open before the freeze: `list/any` (the unread milestone verdicts) and `list/take` (the number of milestones, and so of provider calls, is bounded only by the plan: `(list/take plan.milestones 8)` with `:max 8` when the operator is on `main`). The visible check is protected by prompt wording only (a coder that rewrites `dev-check.json` or `dev_check.py` passes it); no seed-level fix exists, and this is left to step 9's design of the visible check. |
| 2026-11-14 | Seeds of step 8, third fix round after the second re-review (no spend) | A failed check's output now begins with why it failed (the command and its exit status, its timeout, or the missing `dev-check.json`), so the notes a failed round passes on say it; the kit has its own `dev_check.py` for this, because the seed catalog's script is pinned by another kit's candidate ids and recorded runs. `roles` is 49 lines; `designed` is 62 in its layout-only form and stays over the figure of step 8: the owner decides whether it stays in the set. The kit's README states that the seeds compare by a step's last label, not by its key. Recorded, not fixed: the guide path the setup step reports is checked for existence only and may be a directory or a file under `.git`, because the language has no path kind that requires a regular file. For step 9: the check's command inherits the orchestrator's environment and its output goes into the next prompt unfiltered, capped at 4,000 characters a round, so step 9's container design must give the check a clean environment. Still open before the freeze: `list/any` and `list/take`, as in the row above. |
| 2026-11-14 | Task 2a fix round 1, after the independent review (approve after fixes: no blocker, seven majors, twelve minors; no spend; branch `feat/long-horizon-recordings-2a`) | **Recorded, one at a time, the vendor's API shown refused first** (`t2a-fix1-probe-relay-oracle`): `t2a-strace-decoy-low` (a decoy `.credentials.json` with a generated canary in the CLI's config directory, the harness's `exec` of the CLI run under `strace -f` from its start: the CLI opens the decoy but both requests carried the slot's fake token, and the canary reached no request and no file but the harness's export of the config directory; four more credential lookups, all absent) and `t2a-pt-token-first` (the unknown-token refusal on a session's first request: same form as on the second). **Kit:** `recordings.json`'s `harbor_args` of the 30 `t2a-*` recordings read back from each trial's `config.json` (`cut_fixture.py harbor-args`; a hand-written index had substituted `$D` inside `$DENY`), with a test against the cache; `record.sh DECOY=1`; the trace cut keeps only the CLI's process tree and pairs interrupted calls with their results; a no-stream `RuntimeError` keeps the harness's message; written fixtures replace LAN addresses. **Plan, with the coordinator's rulings:** M1 (a slot stays open and metered until the attempt's containers are gone; D4, row 3, Task 5), M4 (the passthrough's paid-usage stop on a non-429 with a non-`allowed` unified status or either overage header; the live probe records `cachedExtraUsageDisabledReason` and whether `overage-status` comes on ordinary responses), M6 (a request count only for the live probe, refused as `slot cap reached`, row 11); M3, M5, M7 and the implementer's eight items; minors m1 to m12. Not applied here: D4's "not the two beta flags token mode adds" (ten flags, three more than simple mode), which sits in the sentence about which request bytes change, left to `feat/lh-passthrough`. Spend: 0. |
| 2026-11-14 | Task 2a, last items after the re-review (approve; no new recording, no spend) | A literal LAN address in a cutter test replaced by a documentation address; written fixtures now map every IPv4 address to `<address>` and a fake slot token to `<fake slot token>`. A test over committed files only checks each `t2a-*` index entry against its fixtures (effort, CLI version, the eighteen-name deny list, every fixture's recording indexed). The after-limit evidence is a fixture (`fixtures/after-limit/t2a-timeout-low.json`: 72 requests in the 18.3 s after the agent phase ended; the CLI's refusal of a standalone `sleep`, which points at Monitor). D4: an attempt settles when its slot closes; the live probe's 6 is per slot and its 18 the probe's total; the stop precedes paid usage only if ordinary responses carry `overage-status`. Live probe item 2 records every response header's name and every `anthropic-*` value, and its request log keeps beta flags, cache marks and declared tools. |
| 2026-11-14 | Task 3, criterion and manifest, built on `feat/lh-criterion` (impl_code; no spend, no container, no request) | `experiments/long_horizon_tasks/ladder.json` holds D1 to D7 as data, each group with its source: the attempt (model, efforts, CLI 2.1.311, token-mode and output-token variables, the eighteen-name deny list, the init event and declared tools), the harness and host-side overrides, the 16 tasks with their public mean at `max` and cap, caps, price (rule file, the table's SHA-256, the five-minute write rate), the credential route and slot, the refusal form, both usage-limit signals, the paid-usage stop, ceiling, settlement, the allowance guard's rules (none of the owner's inputs), network, host, schedule (smoke, pilot and its fallback, blocks), stops and pauses, the label, the readout rules; D5 as sixteen ordered rows of field patterns, each citing its fixtures. `manifest.py write\|check` hashes every kit file but `README.md`, `RECORDINGS.md`, `results/` and caches, plus the price table, and prints the label; `write --freeze` refuses while anything is pending. Tests (`tests/experiments/test_long_horizon_ladder.py`): the cap formula, one cap at every effort, the pilot's fallback, every D5 pattern holding on the fixtures it cites (a misspelt field or a value no fixture shows fails), each cited fixture indexed, the three archives' totals by the kit's price check, the price table's rates, the deny list, the model and efforts, no other model id, every null pending, a one-byte change caught, the freeze refused. **Pending (18), each `null` in the file:** from `feat/long-horizon-oracle-2b`, the qualified tasks, the load-sensitive list, overlay digests, extra hosts, withholding verdicts in `tasks.json`, the agent phase's host list and the CPU set; from `feat/lh-passthrough`, the request-form refusal reasons, the request log's format (and how an unknown-token refusal, which names no slot, is joined to an attempt) and the scope of the paid-usage stop; from Task 2b's dry run, the contamination terms and the canary's SHA-256, and which verifiers report sub-tests; from the live probe, the confirmation of the vendor's header names; at the freeze, the schedule's seed and hash and the bootstrap's seed; by coordinator ruling, how an attempt ending in a stop row (2, 13) is counted and the agent setup timeout multiplier (the recordings used 3). The manifest is committed unfrozen. Spend: 0; subscription usage: none. |
| 2026-11-14 | Coordinator rulings on Task 3's four contradictions and two gaps, applied on `feat/lh-criterion` (revise; no spend) | (1) One frozen seed gives both the schedule's order and the block order (D7.3); Task 3's list now names one seed; it stays pending until the freeze. (2) The paid-usage stop: the two overage clauses apply to any response, a 429 included, and the unified-status clause only to a response that carries the header and is not a 429. This is the reading of `feat/lh-passthrough`, whose D4 text carries it to `main`. `ladder.json` encodes it with `main`'s header names; D4's sentence is left to that branch. (3) The agent phase's host list is frozen after the oracle's second pass has run under it (D1); it stays pending. The oracle script's comment naming Task 3 is only on `feat/long-horizon-oracle-2b`. (4) Row 13 reads the slot's log entries for the model, tool and path reasons and the tranche's for an unknown token, whose refusal names no slot; D5's opening paragraph says so too. (5) D5 defines a stop: it halts the tranche, its attempt is neither an observation nor scored, its slot is not run again, and nothing resumes until a coordinator row names the cause and the decision. `ladder.json` counts the attempt against the 240 and the USD 200 by D7.6. (6) D7.1: if gsea-proteomics does not qualify, the smoke task is the first qualified task in `tasks.json` order that is not on the load-sensitive list. (7) D2: the agent setup timeout multiplier is 3, taken from the recordings; only the Task 2a recordings set one, all to 3. The kit's README says `manifest.py write` is rerun in every merge that changes the kit, and a test fails while the committed manifest is stale. Pending now 15: the oracle branch's seven, the passthrough branch's two (the request-form refusal reasons, the log's field names), Task 2b's three, the live probe's header confirmation, and at the freeze the schedule's seed and hash and the bootstrap's seed. Spend: 0. |
| 2026-11-14 | Task 3 fix round 1 on `feat/lh-criterion`, after the independent review (approve after fixes: 0 blockers, 4 majors, 11 minors), with the coordinator's rulings (revise; no spend) | **(M1)** The passthrough's log is the authority for a usage limit. A slot whose log holds signal 1 is cut (row 10) whatever the CLI's result says. Row 10 is tried first. Row 15 applies only when the slot's log holds no usage-limit signal, and signal 2 alone pauses. D4, D5 rows 10 and 15, the order paragraph and Task 5 say so. Row 10 cites `simple-mode-stub-usage-limit-headers-key-mode-…` for the CLI's form with signal 1 alone. It was recorded in key mode; no token-mode recording of that form exists. **(M2)** Rows 12 and 13 require the specific `lh-passthrough: <reason>` in the attempt's own result text. The passthrough's log corroborates it, read from the tranche's rows in the attempt's time window. How a row with no slot is joined to an attempt is pending until the passthrough branch is on `main`, and D5's opening paragraph says so. **(M3)** New tests: every session fixture classified in order into its row; overlaps only where a listed pair says why the order resolves them; the order pinned, and the natural order shown to misclassify a vendor 401 behind the passthrough and a completed session after a usage-limit answer; each row's class and each class's count. Each of the review's four uncaught mutations now fails a test. **(M4)** The utilisation header is pending for the live probe, and the conditional check of D4 is encoded. **Ruling 5:** a stop's attempt counts against the 240 and the USD 200 (D4 and the approval); D5's stop sentence says so. **Ruling 7:** D2 says the 33 Task 2a recordings of the CLI used 3 and the two oracle probes set none. **Minors:** `read_from` follows D5 (m2); the ruling class counts its start (m4); `check` re-checks a frozen manifest, and a plain `write` over one is refused (m5); a filled field needs its type and a source at the freeze (m6); the cap's one home is `ladder.json`, so `tasks.json` lost its null `cap` and Task 2b's Files line names it no more (m7); readings at each weekly reset, the five-hour approximation, blocks per qualified task, the readout's lists, and the disk plan, pending for Task 2b's ledger row (m8); the overage clauses' scope is an empty condition (m9); the manifest covers the test module that is the pattern language's reference reader, and D7.6 says the package code is bound by the runtime commit (m10); the committed manifest is held current only once frozen (m11). Pending: 18 fields. Spend: 0. |
| 2026-11-14 | Task 4, first slice, built on `feat/lh-passthrough` (impl_code; no spend, and no request left the machine) | `passthrough.py`: the request path (one unix socket; the bearer token and the `host` header replaced, no other byte changed; the one 403 form for an unknown token, another model, a provider-side tool, another path, a slot's or the tranche's request count or priced cap, a stopped tranche, and a body above 64 MiB), the meter (streamed and plain responses by `price_rule.json`, each cache write at its lifetime's rate, a response in flight at a cap metered to its end, the meter restored from the request log at a restart), the token's path of D4 (file mode 600 in a directory of mode 700, read once at the start; the fingerprint; no core dumps and not dumpable; the rehearsal switch opens no token file and makes its own canary), the vendor's answers (a 429 closes starts, a usage limit with its reset; a 401 stops the tranche; a configured paid-usage header stops it before the response is passed on; a response naming another model stops it; unreadable usage closes starts) and its shutdown (closed starts, the socket removed). `token_scan.py`: the fingerprint scan (path and offset only) and the canary check. `live_probe.sh`: the probe's items 1 to 4; it refuses to start without `LH_PROBE_SPEND_AUTHORIZED=yes`. Tests in `tests/experiments/test_long_horizon_passthrough.py` against `stub_api.py`, with a stand-in harness and podman for the probe script. Not run: the live probe (its preconditions, a non-author read and the approval row are open) and the container half of the canary check (a stand-in run of `live_probe.sh` with the real harness and CLI against the stub, zero spend). Readings and what is left for Task 5 are in the implementer's report. Spend to date: 0; subscription usage: none. |
| 2026-11-14 | Task 4 fix round 1 on `feat/lh-passthrough`, after the independent security review of the first slice (approve after fixes, re-review before any live use: 3 blockers, 5 majors, 11 minors), the coordinator's rulings (R-host kept; R-encoding: `accept-encoding: identity` upstream) and three additions from the Task 2a review (its M1, M4, M6) (impl_code; no spend, and no request left the machine) | **The token never goes back:** every byte to the client and every log row is checked for the token in plain, hex, base64 (three alignments, both alphabets) and UTF-16LE form, across writes; a match sends nothing more, drops the client and stops the tranche with the place only; an answer that is not identity-encoded is not passed on. **Allowlist, not deny-list:** the request line, header names and values, and the body (strict JSON, recorded fields, model, efforts, tools, no vendor fetch) are held to `request_allowlist.json`, built by `make_allowlist.py` from `fixtures/requests` (rerun it when the fixtures change). **One request in flight per slot;** the total under one lock: a cap is overshot by less than one response per open slot (measured). The upstream request is built with three header values set (`authorization`, `host`, `accept-encoding`); answers are metered to their end, an incomplete one at the request's worst case (closes starts); the request's headers, body, times and connections are bounded; the scanner finds the encoded forms and fails a scan it cannot make whole. **Paid extra usage on a non-429** (unified status not allowed, overage in use, overage allowed; header names from Task 2a's bundle reading) stops the tranche and the answer is not passed on (403 "tranche stopped"). A slot is retired by the launcher only; a slot at a cap answers "slot cap reached" with the limit named (`cap_requests` is the live probe's only). The request log keeps each request's beta flags, cache marks and tools and each answer's header names and vendor-prefixed values (re-review G.1, G.4). A refusal closes with a bounded lingering read, so a client still sending its body reads it. `live_probe.sh` claims its run only after the passthrough listens, starts it with an empty environment, passes `--stop-on-non-200`, and needs a ledger line naming the kit's commit with "live probe" and "approv". D4 and D5 row 13 corrected. Open: tool keys are not in today's fixtures (the allowlist uses the API's client-tool fields), so the zero-spend rehearsal with the real CLI must show its requests admitted before the probe; the re-review. Spend to date: 0; subscription usage: none. |
| 2026-11-14 | Task 4 fix round 2 on `feat/lh-passthrough`, after the coordinator's rulings on fix round 1 (revise_code; no spend, no new recording, and no request left the machine) | **Merged `integ/batch5`** (the Task 2a recordings): both sides' ledger rows kept; for paid usage, slot lifetime, the request count and row 13 the recordings branch's text. **Tool keys closed from the recordings:** the request cut now records, per declared tool, the top-level keys of its definition and of its `input_schema`, the body's top-level keys, and the message blocks' key sets, key names only, read from the CLI's own record of each request in the recording's session files and joined to the stub's log by name and JSON length; every tool of every `t2a-*` shape matched. The 32 `t2a-*` request fixtures were re-cut (a second cut is byte-identical; the files they are cut from already had their digests in `recordings.json`, unchanged). `make_allowlist.py` builds the allowlist from these key sets over the token-mode `t2a-*` shapes, per tool name, and assumes nothing. **The assumed tool keys would have refused every recorded ladder request:** the placeholder tool's definition carries `defer_loading`. The rebuilt allowlist is also narrower: the four tools of the ladder's configuration, efforts low to high, no subagent header and no `advanced-tool-use` flag. **`live_probe.sh`** needs exactly one ledger line holding the kit's last commit in full and the exact approval phrase, and prints that requirement when it refuses. D4: the ten beta flags of token mode (three more than simple mode); the bounded read after a refusal; the paid-usage clauses as built (the overage clauses on any response, a 429 included; the unified-status clause only on a response that carries the header and is not a 429). Not recorded: the keys of text blocks (the stub logged a text block's length only). Spend to date: 0; subscription usage: none. |
| 2026-11-14 | Task 4, the re-review's three minors on `feat/lh-passthrough` (re-review: approve; revise_code; no spend, and no request left the machine) | `main` merged (no conflict). **n1:** `live_probe.sh` counts only table rows whose second cell is exactly the approval phrase and whose third cell starts with the kit's full commit and a space or a period; exactly one such row, else it refuses and prints the row form (Task 4, "Authority"). Tested: a negated sentence naming the hash, the phrase in the wrong cell, two rows, eight characters, backticks, a hash running on, lowercase, a line that is not a row (all refused); the row with a space or a period after the hash, and beside a negated sentence (admitted). **n3:** the price of a response whose usage cannot be read whole is a bound: the body's bytes, or a larger prompt from the stream's first event, at the one-hour write rate, and `max_tokens` as output (D4, with the assumption it rests on); a test checks it against every corner of the price rule for two constructed requests. **n2:** Task 5 decides per-attempt sockets or a per-slot connection cap before four sessions run at once. Spend to date: 0; subscription usage: none. |
| 2026-11-14 | Task 4, negative cases for the passthrough on `feat/lh-passthrough` (tests only; no spend, and no request left the machine) | Table-driven tests of malformed input: 40 rows of request line and framing (methods, paths, versions, lengths, `transfer-encoding`, short, long and trailing bodies), 22 of headers (authorization forms, forbidden headers, beta flags, values, sizes), 50 of JSON bodies (trailing data, duplicates, unrecorded keys and values, models, effort, nesting past the parser's limit, very long integers); the connection cap with an admitted request completing; descriptors back to their start after 200 connections; and one process taking every row, then admitting and metering a normal request, with nothing unhandled in its output. No row found a defect; the kit's code is unchanged. Bytes after an admitted body are read as the next request and pass every check on their own. Spend to date: 0; subscription usage: none. |
| 2026-11-14 | Task 3 after the passthrough merge on `feat/lh-criterion` (revise; no spend, no container, no request) | `main` (`718617bb`) merged: plan row 13 keeps the passthrough's form refusals in its ending and Task 3's reading in the tranche's rows; every ledger row kept; the kit's README keeps both sections. **Filled from `passthrough.py`:** `refusal.form_reasons` (nine reasons beside the seven recorded; a test reads every reason the code refuses with from its source and requires the sixteen to be the criterion's, each once) and `classification.passthrough_log` (the keys of a refused and a forwarded row; `slot` null before the token is mapped; the join: a slot-less row is the attempt's when its reason is the one the attempt's result text names and its time lies in the slot's window). Row 13 grows by one alternative per form reason; with no recording of them, each rests on the recorded model refusal with its own reason. Row 12 gains the answer withheld for paid extra usage (`tranche stopped` to the client, `passed_on: false` in the slot's row). A test classifies a refusal for each of the sixteen reasons, with and without a slot, into row 11, 12 or 13. **The paid-usage stop** quotes D4 as merged; `ladder.json` adds what the code does beyond the sentence (values lower-cased, an empty header read as none), and a test feeds 2,187 combinations of the three signals through the rule as data and through `Passthrough.paid_signal` and finds no difference. **The worst case** is in `price.worst_case` (the prompt at the one-hour write rate, `max_tokens` at the output rate, the long-prompt multiplier), and a test holds it to `_worst_case`. `credential.passthrough` states the allowlist, the three headers set and the pass-on rule of D4 as merged. The live probe's approval row is not named in `ladder.json` (the probe runs under its own gate in `live_probe.sh`); the README notes that a criterion commit moves the kit's commit that row must name. The manifest covers `passthrough.py`, `token_scan.py`, `request_allowlist.json`, `make_allowlist.py` and `live_probe.sh` (a test checks it), and was rewritten; it is still not frozen. Pending: 16. |
| 2026-11-14 | Coordinator ruling on Task 3's judgment call, applied on `feat/lh-criterion` (revise; no spend) | An attempt whose answer the passthrough withheld for paid extra usage is a **stop**, not an infrastructure failure: paid usage is the one event the owner must hear of before anything resumes. Rows keep one class each, so the alternative moved from row 12 to row 13 (a stop), with the stop's definition unchanged; the coordinator row that lets the tranche resume after it also records what the owner said (row 13, `stops`). Row 13 is now tried first (order 13, 10, 1–9, 14, 11, 12, 15, 16): a usage-limit 429 that carries an overage sign is withheld too (D4), and it must be a stop, not a cut; the pair (13, 10) is listed with a constructed session, which the natural order would put in row 10. Row 12's `tranche stopped` alternative now excludes an answer withheld from the attempt's own slot, so another slot's slot-less refusal in the window cannot make it an infrastructure failure. Row 13 reads `passthrough-stopped-…`, row 12's fixture, as a shared fixture for the withheld answer's form. The manifest was rewritten (still not frozen). |
| 2026-11-14 | Task 3 final round on `feat/lh-criterion`, after the re-review (approve after fixes: 2 majors, 4 minors) and the coordinator's rulings N1 and N2 (revise; no spend, no container, no request) | `main` (`644870e7`, documents only) merged. **N1:** a usage limit makes the attempt a cut only when the slot's log holds signal 1 in a row timed before the session's ending (the result event's arrival; for a time-limit session, the moment the limit fired). Row 10 and row 15's exclusion now read the new field `passthrough.requests_before_ending`. A usage limit met only by the after-limit tail leaves the attempt in its own row and still closes starts. D5 row 10, the order paragraph and "Model-side endings are never excluded" state the exception. `order_resolves` now lists (10, 3), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9), (10, 11), (10, 12) and (10, 14), beside (13, 10) and (14, 12). Each pair has a constructed session; a test checks that each lands in the row its pair names first and that the natural order would take the lower row. A test checks that a time-limit session with a usage limit only after its limit stays in row 3, and a provider fault in row 15. **N2:** `too many connections`, `slot busy` and `request timed out` moved from `refusal.form_reasons` to a new `refusal.load_reasons`, and from row 13 to row 15 (an infrastructure failure; each row keeps one class). Row 15's three new alternatives rest on the recorded model refusal's form. D7 gains a pause: three attempts in one tranche ended by a load refusal; they also count toward the infrastructure-failure stop. Note: the class rule says an infrastructure failure's slot is not run again; the ruling's "run again as for the other infrastructure rows" is read as that rule. **Minors:** (n1) an attempt whose own slot's rows show a stop's cause (the withheld paid-usage answer, a token in its log row, another model named) is row 13 by the new field `passthrough.own_stops`. The token in a response, a response that cannot be checked and an unreadable slots file leave no mark on a slot's rows and stay row 12. (n2) `in_flight` states the 300 s wait, the third open request and the 16-connection cap. (n3) Task 4's pass-on sentence names the withheld exception. (n4) A test holds rows 12 and 13 apart. Pending: 16. |
| 2026-11-14 | Task 2b: disk plan, `tasks.json` filled, first oracle pass on the pinned images (no spend; `oracle_check.sh`, `summarize.py`, `oracle_first_pass.json`, RECORDINGS.md "First oracle pass") | **Disk plan** (from `image_measure.json`): keep all 32 pinned images for the tranche, 23.86 GB in the store (253 layers, each counted once), on `/home`. They are pulled by digest one at a time before the smoke, vba-userform-port first and then the schedule's order, and the same images serve every round. Nothing else is kept between rounds: the harness deletes each attempt's containers, a first-pass job directory is under 25 MB, and the derived vba verifier image (one layer of about 10 kB) exists only while its label runs. **The stop** stays D1's: no start under 20 GB free on `/home` or `/`, checked before every start. The oracle and image checks stop at 25 GB. **Room:** `/home` had 68.6 to 76 GB free during the pass (74.4 GB at its end), so it has about 50 GB after the pull, 30 GB above the stop. Four first-pass trials took at most 4 × 2.74 GB of free space, which leaves about 19 GB above the stop with four attempts in flight. An agent attempt's own writes are not measured; the smoke measures them. `/` holds no image store but is shared: 35.9 GB free at the end, 31.0 GB at its lowest during the pass, from other sessions' writes. The 32 fit today; the reading is repeated at the freeze, and question 6 goes to the owner if `/home` then has less than about 60 GB free (20 + 23.86 + 11 + 5 margin). **`tasks.json`:** each task's two images (digest, image id, compressed and unpacked size, layer count) and its withholding result are written by `image_check.py tasks`. The coordinator's ruling is printed beside `app/.git` in pretrain-shard-corruption and shadow-relay (N2). All 16 have verdict `withheld`, with nothing unruled. Text files over 64 MiB, which the line check skips, are now listed (N3): there are none in any of the 16 agent images, from a recheck of each during the pass (records `pass` 5 or 6). D1's sentence now states the 10-line rule, the layer walk by path and SHA-256 only, and that archives in system and language paths are neither opened nor listed (N4). `overlay_digest` (`3f99fe3c…c4f6`, the two keys with D3's list as drafted, 13 names) and `oracle_evidence` come from `summarize.py --write`. `cap` and `extra_hosts` stay null for Task 3. **First pass** (D1; 16:18 to 18:36 PST; one task at a time; CPU set 8-31; gate off; draft allowlist). Each entry gives reference / untouched, wall s for each, and 1-minute load at each start: vba-userform-port unchanged no reward / no reward (61 / 50; 55 / 52); vba-userform-port-uidfix pass / fail (113 / 66; 19 / 32); vf2-speedup-networkx pass / fail (330 / 71; 34 / 35); wal-recovery-ordering pass / fail (537 / 71; 34 / 15); session-window-debug pass / fail (67 / 66; 40 / 47); production-planning pass / fail (98 / 61; 63 / 52); vpp-loss-divergence pass / fail (234 / 188; 33 / 38); batched-eval-parity pass / fail (327 / 107; 48 / 35); pretrain-shard-corruption pass / fail (409 / 106; 41 / 22); gsea-proteomics pass / fail (107 / 50; 12 / 14); lake-temp-glm pass / fail (379 / 71; 32 / 39); sound-change-cascade pass / fail (66 / 61; 35 / 37); hof-topology-interpenetration pass / fail (112 / 67; 45 / 50); shadow-relay pass / fail (66 / 61; 56 / 48); rs-archive-clone pass / fail (169 / 72; 49 / 55); retro-console-soc pass / fail (309 / 56; 39 / 17); roy-polymorph-cn pass / fail (71 / 61; 52 / 45). The CLI 2.1.311 installed on all 16 pinned agent images (25 to 178 s). Every process sampled in the agent, sidecar and verifier containers ran on 8-31. Only gsea-proteomics's reference met refused connections (8, to two addresses), and it passed. **Findings.** (1) vba-userform-port fails unchanged on the pinned images as on the local build (`Errno 22`; the user namespace maps 65,536 ids). (2) The labelled one-line change cannot act through the package alone, because a pinned verifier image carries its own tests. The variant therefore runs on a verifier image derived from the pinned one by the same one-line change, named in its `task.toml`: a modified task with its own label. (3) podman-compose's teardown force-removes images named `localhost/…`. That cost the variant's first untouched run, which is set aside as infrastructure; the variant was rerun after the derived image was renamed. (4) `/etc/subuid` and `/etc/subgid` already list a second range `165536:1000000000` for the user (dated 2026-11-13), but the running user namespace has not taken it up. `podman system migrate`, which stops every container of the user, was not run: owner question 4 stays open. **Not done here:** the second pass (five and five in a quiet window under the final policy, the only qualifying pass), the contamination-terms dry run and freeze. Spend: 0; no model or provider call, no credential. |
| 2026-11-14 | Task 2b fix round 1 on `feat/long-horizon-oracle-2b`, after the independent review (0 blockers, 3 majors, 11 minors) and the coordinator's rulings (revise_code; no spend: no agent, no model or provider call, no credential) | **M1:** `summarize.py` counts a run only as evidence: reward exactly 1 (pass) or exactly 0 (fail), no error, no stop, its tests run. A label qualifies only when every reference run passes and every untouched run earns 0; any other run blocks it and is listed. On the first pass's jobs the table is unchanged for the 15 tasks, and the set-aside run now prints `does not qualify` (`nop 1: RuntimeError`). **M2:** the harness runs in its own session (`exec setsid`), so `$!` is the harness and its group. A stop sends it SIGTERM, then SIGKILL to the group after 120 s, then removes the containers and networks named after the trial. A test with a hung stand-in harness and a stand-in podman: the stop ends the harness and its child within seconds and leaves nothing. Checked for real on the variant: a wall-bound stop and a stop by SIGTERM to the script, both runs exited 130 within 40 s, nothing left (RECORDINGS.md). The README describes the pattern for Task 5's launcher. **M3:** `uidfix_variant.py` built the variant's verifier image once and recorded it under `variant` in `tasks.json`: base digest `ce013fac…2a28` (id `cb25df7d…073d`), image id `01b5f971…67ca`, `/tests/app_worker.py` SHA-256 `d30b3eaf…6df7` before and `f760628d…cf2a` after, the diff (line 55), and differing paths file by file: exactly `tests/app_worker.py`. It is kept as `lh-oracle/vba-userform-port-uidfix:verifier` and `lh-keep/vba-userform-port-uidfix:verifier`; the teardown deletes by name, so with two names it only untags. `oracle_check.sh` checks the id before each launch, restores the name from the keeper, and never builds or deletes the variant. Before four at once, the second pass runs one round of the label at four and checks for a lost image. Rerun on the recorded image: reference 29 of 29 traces, untouched 0 of 29, `qualifies` (`oracle_uidfix_recorded.json`). **Minors:** release keeps listed what it could not delete, and SIGINT or SIGTERM stops every running trial (m1). A pull needs its size above the stop on both mounts first (m2). Each trial has a wall bound: the task's agent, verifier and both build limits plus 1,800 s, about 9.4 h for vba-userform-port; the follower's podman calls time out after 60 s (m3). The gate's two-hour clock runs only while no trial is in flight (m4). A non-empty `JOBS` is refused unless `RESUME=1` (m5). The table's graded-check column gives vba's traces (29/0 of 29) and wal's gates and suite separately, and the records keep the trace counts (m6). The teardown's two deletion paths are described exactly (m7). The egress logs show the allowlist only for gsea-proteomics, and the sidecars' policy is now sampled, which a short agent phase can miss (m8). Every changed Python function is at radon complexity 11 or less (m9). gsea-proteomics's refused host `www.gsea-msigdb.org` (the GSEA tool calling home; the reference passed 16 of 16 without it) is recorded beside the task (m11). **Disk plan, amended (m10):** the image store is on `/home`, but Podman stages every pull in `/var/tmp` on `/` (`ImageCopyTmpDir`), and the withholding exports went to `/tmp`, also on `/`. Both are transient, so a pull counts its compressed plus unpacked size against both mounts. The variant's own layer is 10.2 kB over its base, which the plan keeps among the 32; it stays in the store with that base. Spend: 0; subscription usage: none. |
| 2026-11-14 | Task 2b after `feat/lh-criterion` reached `main` (`524ed71a`): `main` merged into `feat/long-horizon-oracle-2b` and `ladder.json` reconciled (revise_code; no spend, no container) | **Merge:** `tasks.json` keeps this branch's digests, sizes, withholding results and oracle evidence. The `cap` field is gone from all 16 entries, since caps live only in `ladder.json`, and `extra_hosts` is as `main` has it (null). Every ledger row of both sides is kept, and the kit's README keeps both sections. **Filled in `ladder.json`**, each moved to `filled` with its source: `tasks.withholding`, per task the verdict, the agent image digest and the ruled items (all 16 `withheld`, nothing unruled; from `tasks.json` at `aaa7ac74`); and `host.disk_plan`, from the two Task 2b rows above (keep all 32 images, 23.86 GB on `/home`; the pull order; nothing else kept between rounds; pulls staged on `/`; the room; D1's 20 GB stop). **Recorded:** the labelled variant `vba-userform-port-uidfix`, beside vba-userform-port in `tasks.list`, with its derived verifier image by id and its base by digest. It is used only if the owner does not run `podman system migrate`. **Left pending:** `host.cpu_set`, because D2 fixes 24 CPUs but names none, so the first pass's 8-31 stays a draft until the qualifying pass runs on it. Also `tasks.overlay_digests`: the recorded digest is that of D3's draft list, and it is filled when the allowlist is frozen. Also `tasks.qualified`, `tasks.load_sensitive`, `tasks.extra_hosts`, `network.agent_phase.allowed_hosts` and Task 2b's three `readout.*` fields. `manifest.py write` was rerun (unfrozen; `check` passes). Spend: 0; subscription usage: none. |
| 2026-11-14 | Task 2b fix round 2 on `feat/long-horizon-oracle-2b`, after the re-review at `eddda783` (M1 to M3 closed; one new major, N1, and three minors) (revise_code; no spend, no container) | **N1:** the load gate's two-hour end works on the real launch path again. `check_task` ran the launch checks inside `$(…)`, where the list of running trials is a frozen copy. Above concurrency 1 a finished trial still counted as in flight and the wait never ended; at concurrency 1 the gate's message reached the exit code, giving exit 2. Now `launch_ok` runs in the calling shell and returns its code, and every message of the script goes to stderr. No other `$(…)` in the script holds a function that reads or changes that list. Two new tests run the real `check_task` and `wait_gate`, with one 4 s trial and a 2 s idle limit. On `eddda783`, concurrency 1 exits 2 (6.1 s) and concurrency 4 is still running at the 60 s timeout. Now both exit 4 (6.2 s and 5.1 s). The README states the rule for Task 5's launcher. **n1:** a reference counts as a pass only with a CTRF report holding at least one test, all passed. A run with no report is "no tests ran" in both halves, and a label with no run in one half lists it. No verifier of the 16 lacks a report by design: vba-userform-port's holds the scoring wrapper, and its hidden traces are the evidence. The first pass's verdicts are unchanged. **n2:** the builder is named `uidfix_variant.py` in `oracle_check.sh`. **n3:** the worktree's untracked `.tmp/` is deleted. **The second pass's checklist** (the re-review's six items) is under Task 2b. The second pass needs the owner's window and the owner's answer on `podman system migrate`. `manifest.py write` was rerun (unfrozen; `check` passes). Spend: 0; subscription usage: none. |
| 2026-11-14 | Seeds of step 8: the number of milestones is bounded (finding N3 closed; no spend; branch `feat/lh-seed-bound`) | `milestones.orc` and `roles.orc` build at most the first eight milestones of a plan: the map's source is `(list/take plan.milestones 8)` and its `:max` is the literal 8. A plan of nine or more is cut and the run goes on; stand-in plans of 9, 20 and 50 milestones make exactly the 20 provider calls of a plan of 8, and a plan of 3 is unchanged (10). Every loop and map of the four seeds now has a literal bound, and the worst case of the two milestone seeds is 6 + 8 × 8 = 70 provider calls (before: 6 + 8M with M the planner's own count; 50 milestones made 104 calls on a clean run). The planner prompt keeps "at most eight". Of the two conditions the rows above set for the freeze, `list/take` is met. `list/any` is on `main` too, but the seeds do not use it yet: the unread milestone verdicts stay open. |
| 2026-11-14 | Seeds of step 8: the milestone verdicts are read and a cut plan is named (no spend; branch `feat/lh-seed-bound`) | `milestones.orc` and `roles.orc`: each milestone returns whether it was met and its last notes; when one was refused in both attempts the run ends `BLOCKED` ("milestone refused twice") with how every milestone ended, after the map (a serial map builds the plan's other milestones first) and before the round's check and acceptance. The gate is `(list/all (list/map ((b built)) b.met))`. A plan of more than eight milestones adds a row with the count planned and the count built to the outcome's `cut` field, in `DONE` and in `BLOCKED`; a plan of eight or fewer adds none. Both seeds end with the new type `Ending` (`Outcome` with those two fields). Sizes at no more than 120 columns: `milestones` 54 lines and `roles` 56, over the figure of step 8 and left over as ruled; `staged` 34 and `designed` 62 are unchanged. With this, both conditions the rows above set for the freeze are met (`list/any` was not needed: `list/all` reads the results). Found on the way: a `match` in the body of a `list/map` used as an `if` condition inside a loop crashes the compiler (`KeyError` in `wcc/elaborate.py:_infer_expr_type`), which is D8 of the defect backlog; the seeds avoid it by returning a record with a `met` field. |
| 2026-11-14 | Seeds of step 8 frozen after their freeze review (no spend; branch `feat/lh-seed-bound`) | **Freeze record:** `experiments/long_horizon_seed/seeds.json`, SHA-256 `64f2bdb375d3c8f80871f4130f9a50dcb16d7e036a76b4bba1cee6803d228d16`. It holds each seed's source hash, program digest and target (2.40) and the hashes of `common.orc`, `dev_check.py`, `providers.json` and `commands.json`; a program digest does not cover the bytes of `dev_check.py`, so the seeds are frozen by the record, not by digests alone. `python -I experiments/long_horizon_seed/freeze.py check` and a test of the seed test module recompute every entry. **Program digests:** `staged` `sha256:289903d6d3e9107a073eab6f33fd3c3a031bc521d1830c02582111545283e8ca`; `designed` `sha256:4298f71042b79ba54fb81374994de952eecf225bc43a35da192493fffe7c017e`; `milestones` `sha256:fa41381174ee3051cb2ccc8226f76e919ce84b00199ab60e06163d3164763c9c`; `roles` `sha256:7d312c9dc73ccaec00581d85a49418afa0c5fdbfe1627d473a73dd1222817322`. **Sizes** (physical lines of at most 120 columns; stripped code characters; prompt characters): `staged` 34, 2,125, 3,869; `designed` 62, 3,975, 5,601; `milestones` 49, 3,080, 4,288; `roles` 50, 3,092, 4,288. **What changed before the freeze:** one `Outcome` for all four seeds (the row above's `Ending`, `cut` and per-milestone rows are withdrawn: the journal holds both, and the kit's README says where); a milestone gives `true` or `false` and the round tests `(list/all built)`; the round's check runs before that test, so a run that ends on a refused milestone still records the visible check; a milestone's check is labelled `check`, so every last label is used once in a seed. **Left for the search:** a variant that ends at the first refused milestone. The frozen seeds build the plan's other milestones first, which spends at most 28 provider calls after a first refusal with a plan of eight; stopping at once would spend 7 in all. The milestone cap is fixed by the freeze (two literals that must change together; no operator edits them). |
| 2026-11-14 | Task 6, the readout, built on `feat/lh-readout` (impl_code; no spend, no container, no request) | `experiments/long_horizon_tasks/readout.py` reads the launcher's export (a record shape it states and checks, since the launcher is built in parallel: the current and earlier labels, how the tranche ended, the schedule's slots and every start with its D5 row, reward, exclusion, cost, minutes, tokens, sub-tests and refused connections) and computes every figure of D6 once, from the starts joined to their slots by slot id, with every rule read from `ladder.json`. A final readout is refused while a `readout.*` field is pending and unless the label is the manifest's and the manifest holds the `ladder.json` read; `--rehearsal` takes stand-ins and stamps every output. `family.json` is written only after a tranche that ended and did not stop, and is a pure function of the records. Tests (`tests/experiments/test_long_horizon_readout.py`, every record constructed): the report's interval table; labels and the band effort over the 55 screened-in patterns; the verdict and the bound on constructed tables; partial rounds out of complete triples; every excluded class listed and never scored zero; cuts per effort and the pilot marked; labels never pooled; the graded outcome and the allowance entering no rule; a stop readout with no placement; `family.json`'s content and bytes. Open for the coordinator, each marked in the code (R1 to R5): whether `family.json` also records a stop (the headline says so; it is not written after one); whether a stop readout withholds the bound on the fall (it does); the dominance threshold, in `ladder.json` as prose only (the effort test's 0.05 is used); the pooled ratio applied below 15 attempts; the bootstrap's generator and quantile, which D6 does not name. Spend: 0. |
| 2026-11-14 | Task 6 revised on `feat/lh-readout` after the coordinator's rulings on its open points (revise_code; no spend, no container, no request) | **R1:** after a stop no `family.json` is written and the stop readout names the stop; the headline sentence says so. **R2:** a stop readout prints the bound on the fall over the complete triples there are ("over N complete triples; no placement is made"), or says there are none; D6 says so. **R3:** `readout.cost.dominated_p_at_most` (0.05) in `ladder.json`, a filled field of the new type `number` (which `manifest.py` now accepts), with the prose it encodes and the ruling; the readout reads it and no other field. **R4:** the pooled screen is applied only at 15 attempts (`readout.pooled.at_n`); with fewer a task prints its pooled count and interval and "not screened: n of 15 attempts"; `family.json` is written only when every task is screened at 15 or dropped for a stated reason, which the readout takes as `--dropped` (a list of task and reason, the reason naming the ledger row); D6 says so. **R5:** the bootstrap is frozen in `readout.fall_bound` (`random.Random(seed)`, tasks in name order, 10,000 resamples, the ceil(0.95 R)-th smallest fall; the seed stays pending), and a test pins the bound for one table and one seed. **Contamination:** the launcher runs the scan at each teardown beside the token scanner and writes the SHA-256 of each term found into the slot's record; the readout lists every contaminated attempt by that SHA-256 and never the term (D6, Task 5). **One layout:** `experiments/long_horizon_tasks/slot_record.py` holds the export's fields, types and the loader that fails fast; the readout loads it by path, and the launcher is to do the same; its tests are `tests/experiments/test_long_horizon_slot_record.py`. The manifest was rewritten (not frozen). Spend: 0. |
| 2026-11-14 | Task 6 fix round 1 on `feat/lh-readout`, after the independent review (4 majors, 13 minors), with the coordinator's rulings; `main` (`c24fb97d`) merged (revise_code; no spend, no container, no request) | **M1:** each start's record carries the class the launcher decided (`class`, `stop_cause`); the loader accepts the row's class, or `stop` with a cause from the closed list `slot_record.LAUNCHER_STOPS` on a row of another class, and refuses anything else; a stop is never scored and is listed with its cause. **M2:** `contamination` on a start of any class; it excludes an observation, and on other classes is listed and counted for D7.7 without changing the class; `excluded: "contaminated"` is gone from the layout. **M3:** the final readout runs only on a frozen manifest whose hash is the label, with `ladder.json`, `tasks.json`, `readout.py` and `slot_record.py` equal to its records and no pending field; otherwise refused with the reason, or a stamped rehearsal. **M4 (R4 revised):** a task is screened when every effort has at least four scored observations (`readout.pooled.min_per_effort: 4`, replacing `at_n: 15` as the condition; 15 stays the planned count), printed "screened at n of 15 attempts"; below it "not screened" with counts per effort; D6 states the cost (a wider interval at 12, printed). Bootstrap: the reviewer's 16-task table at seed 20261114 pinned at 15.151515151515152. Minors m1 to m13 applied (finite figures; repeated keys, NaN and Infinity refused on reading; D5's forbidden sequences and contradicting exclusions refused; pilot marks and `end.by: "starts"` cross-checked; one USD total; decodable labels; `--family` prints the stop readout, then refuses; the Python version printed and in `family.json`; an in-progress readout labelled interim; a drop reason names a dated ledger row; the launcher's four disagreements mapped in `slot_record.py`'s docstring). The reviewer's six scripts rerun: each constructed failure now behaves as ruled. Manifest rewritten (not frozen). |
| 2026-11-14 | Task 6 fix round 2 on `feat/lh-readout`, after the re-review at `32d6dab9` (M1 to M3 closed, 12 of 13 minors closed; one new major and three minors), with the coordinator's rulings; `main` (`5d3dacb6`) merged (revise_code; no spend, no container, no request) | **N1:** no interval beside a count pooled over tasks: the pooled successes by effort print their counts and "pooled over tasks with different rates: no interval is given; see the per-task intervals"; only a single task's counts carry an interval (test over the whole readout); D6's effort test says so. **N2:** `slot_record.LAUNCHER_STOPS` names where each cause can occur: the init-event causes, paid extra usage and a subagent file on a session's start only (refused on a pre-session failure), a `token_scan.py` match on any start, a failed smoke check on the smoke's slot only (`smoke_cell`: `schedule.smoke`, with D7.1's fallback, round 1). **N3:** a slot is lost after its third pre-session failure counted in all (D5), not in a row. **N4:** D7.7 names no label, and D7.6 confines only placement and the effort test to the current label, so the contaminated attempts are listed and their tasks counted over every label, each attempt with its label; the printed line says what is counted. D6 states the cost of screening below 15 with the reviewer's figures. The report's "what the launcher must write" points to `slot_record.py`'s docstring. Manifest rewritten (not frozen). |
| 2026-11-14 | Owner precondition: the token is in place | The owner created a subscription token with `claude setup-token` by the procedure of question 1 (a script run in a terminal outside tmux and outside any agent session; the token typed into the script's hidden prompt, never on a command line) and reported "done" at 22:28 PST. The coordinator checked metadata only, never the content: `$HOME/.local/state/lh-secret/token`, mode 600 in a mode-700 directory, owner the owner's user, 109 bytes, outside every repository; no sync or backup tool covering the home directory was found on this machine. **Not yet recorded:** the lifetime `setup-token` stated and how the token is revoked (asked of the owner). **Still open before the live probe:** the owner's confirmation that paid extra usage is off; the owner's confirmation that the subscription's terms allow unattended runs of this size; the launcher's independent review (Task 8); the zero-spend rehearsal with the real CLI in a container (Task 7); the coordinator's approval row. The token is named to the passthrough only; no agent, test or the coordinator reads it. Spend: 0. |
| 2026-11-14 | Token: lifetime recorded; its value was disclosed to the coordinating session | **Lifetime:** `claude setup-token` states the token is valid for 1 year. **Revocation:** the command's output says nothing about it; how to revoke is being looked up. **Disclosure:** at about 22:58 PST the owner pasted the command's whole output, token included, into the coordinating session. The value is therefore in that session's context and in its transcript file on disk, which breaks this plan's rule that no agent, test or the coordinator handles the value. The coordinator has not copied it anywhere, wrote it into no file, brief or commit, and does not use it. **Coordinator's recommendation:** the owner revokes this token and places a new one by the same script (after removing the old file); a revoked token makes every copy worthless, so no transcript needs editing. **Hold:** the live probe does not use the token placed at 22:28 until the owner has replaced it or has said in words that it stays. Spend: 0. |
| 2026-11-14 | Token revocation: not documented | A read of the official Claude Code documentation (authentication page, CLI reference) found how `claude setup-token` creates the token and that it "does not save the token anywhere", and nothing on listing or revoking such a token, on whether a new token invalidates an earlier one, or on whether revoking signs out other sessions. Third-party pages describe a list of authorization tokens in the claude.ai account settings; this is unverified. **Consequence:** the owner looks for that list in the account settings and revokes the entry created on 2026-11-14 at 22:28; if no such list exists, revocation stays an open point of this plan and the ledger says so before the live probe. Spend: 0. |
| 2026-11-14 | Token replaced by the owner | The owner reported "done" after the coordinator's request to replace the disclosed token. Metadata only, content never read: `$HOME/.local/state/lh-secret/token` rewritten at 23:00:11 PST, mode 600 in a mode-700 directory, 109 bytes, the only file there; lifetime 1 year as the command states. The hold of the earlier row is lifted for this file: the passthrough may be given its path once the other preconditions hold. **Open:** whether the disclosed token of 22:28 was revoked (asked of the owner; the documentation gives no way, so it may stay valid until 2027-11-14). The coordinator cannot tell from metadata that the new value differs from the disclosed one and takes the owner's word for it. Spend: 0. |
| 2026-11-14 | Task 5, the launcher, on `feat/lh-launcher` (impl_code; no spend: no live launch, no token, no container, no request left the machine; every test against stand-ins) | `ladder.py` (commands `plan`, `launch [--dry-run]`, `status [--export FILE]`, `ruling`, `allowance`) and its tests in `tests/experiments/test_long_horizon_launcher.py` (`test_long_horizon_ladder.py` keeps the criterion's tests; Task 5's Verify line says so). The six groups: refusals, money, classification (the reader of `ladder.json`'s pattern language moved into `ladder.py`; the criterion's tests import it), allowance, host, connections. **Decisions:** the passthrough is started by a person with the token file (`status` prints its command line) and the launcher refuses to run while `LH_TOKEN_FILE` is set; the live probe's priced usage is read from its own request log; the ledger rows the launcher reads are `Configuration label` (`<manifest sha256> <runtime commit> ...`), `Smoke read` (`<label> pass` or `<label> fail`), `Pilot read`, `Round 1 read` and `Ruling` (`<attempt> row <N> ...`); `schedule.order.hash` is `ladder.ORDER_HASH` (SHA-256 of `<seed>:<round>:<task>:<effort>`, a block's key with an empty effort), and a criterion naming another is refused; **connections: each attempt has its own passthrough socket** (Task 5's Connections item states the reason: one attempt's held connections can no longer turn another's requests into load refusals); the export is `slot_record.py`'s layout (the file as on `feat/lh-readout` at `37d40d82`, byte for byte), checked against it before it is written. Open rulings are in the implementer's report. |
| 2026-11-14 | Task 5 revised on `feat/lh-launcher` after the coordinator's rulings on its five open points; `main` (`27a5b30b`, the readout and the slot record) merged (revise_code; no spend: no live launch, no token, no container, no request left the machine; every test against stand-ins) | **1:** D7.7's four count thresholds (the infrastructure-failure share, five or 24 pre-session failures, the 5% of cuts, three load-refusal endings) stop or pause the tranche; one is lifted only by `ladder.py resume --clears` with the date of a Ruling row naming it, and then counts only later endings; a plain resume is refused while any is over its bound. **2:** the runtime check's match and both incomplete scans are causes of `slot_record.LAUNCHER_STOPS` on any start; a launch refused before the harness ran is no start (the tranche stops, the attempt is kept under `refused/` beside its stop event, its token is retired, nothing is exported); a Smoke read row that says fail gives the smoke's start the cause "a failed smoke check". **3:** regrade case 1 still with no reward file is an infrastructure failure (`ladder.json`, D5): the layout accepts that class on the normal ending's row with excluded "no reward after regrades", the launcher exports it so, and the readout lists it, never scored. **4:** a null `minutes`, token count or `api_retry` was not recorded: the readout prints "not recorded", leaves it out of its means and counts how many it left out, never zero. **5:** the per-slot sockets' diff range in `passthrough.py`, and what a valid fake token gets on another attempt's socket (403 "unknown token", logged with slot null), are in the implementer's report. **Found and fixed:** `reconcile` closed a dead launcher's attempt without its scans, its regrades or the stop already written for it, so a stopped start could have been exported as a scored observation; it now runs the same teardown, and the record's stop is the first launcher stop written for the slot. Task 5's Verify line names the launcher's module and the slot record's and readout's. Spend to date: 0; subscription usage: none. |
| 2026-11-15 | Task 7, the zero-spend rehearsal, on `feat/lh-rehearsal` (impl_code; spend: 0, no request reached the vendor, no credential read or named) | **In the suite** (`5e0e27d6`): the whole schedule (3 stand-in tasks, 45 slots) against the stand-in harness ends inside both caps; a usage limit at start 20 closes starts until five minutes after its reset, its cut slot is the first start after they reopen, 46 starts, every slot one observation, the export loads. **On containers:** the real CLI 2.1.311 (each init event) in rootless Podman, in the ladder's configuration, through the relay, the passthrough in `--rehearsal` (a 108-character canary; no token file) and `stub_api.py` with a scenario per task and effort; agent time limit shortened to 576 s (multiplier 0.02, in a kit copy only). Tasks: the three smallest images that passed the first pass, wal-recovery-ordering (env `sha256:71d215ea…6657`, verifier `sha256:627bc781…46ef`), sound-change-cascade (`sha256:95bd3659…ecc0`, `sha256:8980723c…acf0`), hof-topology-interpenetration (`sha256:a758f32e…7c1d`, `sha256:cc54700d…1b65`), image ids equal to `tasks.json`'s; relay `alpine/socat@sha256:beb4a68d…015e`. **Vendor unreachable, before the first session:** `allowlist_probe.py` as the oracle solution of hof's package under the 13-host overlay: `vendor api: refused URLError … UNEXPECTED_EOF_WHILE_READING`, the sidecar's row `dst 160.79.104.10:443 … outputBytes 0` then `bypass`; in every `normal` session the agent's curl to the vendor got `curl_rc=35`, kept as one refused address. **Ten starts, the five endings:** budget stop (hof low, USD 7.176 metered against the cap 7.14) row 6, observation; past the time limit (hof medium, 3,010 requests, 15 after the limit metered into the slot) row 3, observation; usage limit (hof high, 429 with the unified reset) row 10, cut, run again as start 5 (row 5, observation); launcher killed with SIGKILL and reconciled (wal medium) row 3, observation; regraded (wal low and wal high, case 2 with the load stand-in above the gate during their verifiers, one `trial regrade` each, reward 0 stands) row 5, observation. The smoke (sound low) passes all 13 D7.1 checks; settlement figures agree on every attempt with a result event. **Allowlist:** 6,187 requests, every one admitted by `request_allowlist.json`; no refusal of any shape. **Canary (D4):** planted, found (`token_scan.py canary`: pass, before and after); after the sessions found nowhere in 9,447 files (the state with the job directories, the passthrough's logs and output, the egress logs, the stub's log, the kit copy, this worktree, `~/lh-cache/recordings`); the container records (inspect and process environments) scan clean; the launcher's exported-file-system scans recorded no match. Not scanned: the agents' transcript directory (a credential-adjacent path this task may not name). `readout.py --rehearsal` on the export runs (exit 0). **Fixed:** the kept egress log dropped the proxy's standard error, where every connection and refusal is (`5795c3b7`). **Reported, not fixed:** reconcile's SIGTERM cancels a harness inside its verifier, and the attempt is scored 0 from no reward (D5 needs a ruling); the stream reaches the host only after the agent phase, so the launcher's stream checks act after the session; the reopening's one start waits for attempts already in flight; every wal attempt is contaminated by the real canary GUID in the task's own `/app` files (Task 2b's terms); `~/lh-cache/logs/containers-override.conf` carries a comment and is refused; the review's B1 (two `_main_1` containers in every attempt), M1 (all containers exited at teardown, `podman exec` 255) observed. Full report: the coordinator's scratchpad, `lh-rehearsal-report.md`. Spend: 0. |
| 2026-11-15 | Task 8 (two independent reviews of the launcher at `61ebca3c`) and Task 7 (the rehearsal, `feat/lh-rehearsal` at `0808ac5c`): results and coordinator rulings; spend 0 | **Review part B, token handling ("ready after fixes"):** no path on which the real token leaves the passthrough process; a planted fake token found in all 42 places the scanner covers. Two blockers in the runtime check (a later container's clean scan replaced an earlier match; no matching container read as clean), three majors (a failed `podman exec` or `inspect` read as clean; in a rehearsal `status` printed the live `--token-file` command and the launcher did not check its passthrough's mode), nine minors. **Review part A, scheduling and records ("not ready" until fixed):** nothing lets a start pass 240 or the USD 200 ceiling; one blocker (a usage limit followed by a pause and a resume reopened starts before the reset), seven majors (a silent wait after a reset; a stop lifted with no Ruling row; a launcher death before a regrade leaves an unexportable record; a refused launch's start index reused; no single-launcher lock; the runtime commit, manifest and label checked only at launch; the at-one-level infrastructure share tripping on one failure in three), twelve minors; 11 of 55 guard mutations not caught by any test. **Rehearsal (real CLI 2.1.311 in containers, fake token, vendor shown unreachable first):** ten starts covering a budget stop, a time limit, a usage-limit cut and its re-run, a kill and reconcile, and two regrades; all 6,187 requests admitted by the allowlist, none refused; the canary found when planted and in none of 9,447 files afterwards. **Rulings:** every finding of both reviews is accepted and goes to the launcher's author with a test that fails first; the at-one-level share needs at least 20 starts at the level and is its own threshold name; lifting a stop needs a Ruling row; a reward is only what a verifier gave (an attempt with no verifier result is regraded, else `infrastructure_failure`, "no reward after regrades"); every container must have a successful `inspect` scan and each exported one a successful `export` scan, else the scan is incomplete, and `podman exec` samples are taken from running containers only (the containers have exited at teardown); the stream file reaches the host only after the agent phase, so the live stop for paid extra usage is the passthrough's and the launcher's stream checks are after the session (accepted limit); the reopening start after a limit may wait for older attempts (accepted, it only delays); the canary term is applied per task and is not applied to a task whose starting files hold it (`wal-recovery-ordering` does; the list is a pending criterion field filled by Task 2b's dry run); the pids limit does not reach the verifier containers (accepted limit). **Host state:** the cached `containers-override.conf` carried a comment line the launcher refuses; the coordinator rewrote it to the criterion's content. **Not yet done:** the fixes and their scoped re-review; the scan of the env container's exported file system could not be verified by the rehearsal (the first blocker of part B) and is re-run after the fix. |
| 2026-11-15 | Task 8 fixes on `feat/lh-launcher`: part B (the secret-handling review, "ready after fixes") and part A (the scheduling-and-records review, "not ready" until B1, M1 to M7 and four test gaps), with the coordinator's rulings; then the coordinator's rulings on the Task 7 rehearsal, after merging `feat/lh-rehearsal` (`0808ac5c`) (revise_code; spend 0: no live launch, no token, no container, no request left the machine; every test against stand-ins) | **Part B:** any container's finding is the attempt's, and every `*_main_1` (agent and verifier) is exported (B1); a session with no container under its prefix, or an export due with no agent container, is an incomplete scan (B2); a failed or empty `podman inspect`, `logs` or `export` is an incomplete scan (M2); a rehearsal's `status` prints the passthrough's `--rehearsal` start, the passthrough records its mode, and the launcher stops on a mismatch either way (M3); a scanner crash is incomplete, skipped links and special files are named, base64 wrapped at 76 columns is a stated limit (m1 to m3); reconcile retires every settled attempt's token, an exception tears the attempt down first, a shell holds the harness until its pid is recorded, the rehearsal canary has a setup-token token's prefix and 108 characters, and the launcher refuses `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` in its environment, naming the variable (m4 to m8); six guards got tests (m9). **Part A:** a resume lifts a stop or a pause, never a usage limit, and no order of events opens a start before reset + 5 min (B1); an unanswered single start after the reopening pauses, a plain resume allows one more (M1); a stop is lifted only after `\| D \| Ruling \| resume: <cause>: <decision> \|` and `resume --date D`, or its threshold's `--clears` ruling (M2); reconcile finishes an interrupted regrade (M3); an index is never reused (M4); one launcher per state root (`launcher.lock`), a second refused with the holder's pid (M5); the launch's checks repeat at every start and a start records the hash checked (M6); the at-level share needs 20 starts at that level and is its own threshold `infrastructure-failures-at-level` (M7); m1 to m3 and m6 to m11 as the review proposed (m4 and m5 are part B's m5 and m6); tests for the eleven surviving mutations. **m12 not applied** (it would change D5's "a pre-session failure counts against neither"); the coordinator ruled that D5 stands and that a pre-session failure has no metered usage: an ending of row 1's form for which the passthrough metered usage keeps its row and is an infrastructure failure, which counts against both (D5's sentence, the launcher and the slot record). **Task 7 rulings:** (1) process environments are sampled from running containers only; a failed exec on a running one is logged and does not by itself make the scan incomplete, while every inspect and export must succeed; each inspect, logs and export exit is kept per slot (`podman.jsonl`); (3) a reward is only what a verifier gave: an observation with none, after any ending, is regraded as case 1 on its own row, and with still none is an infrastructure failure excluded "no reward after regrades" (D5's text revised; the row is kept, so a time limit stays flagged); (4) the stream checks are post-session, the live paid-usage stop is the passthrough's header rule (D4, D7.7, README); (5) the reopening's one start is at most one attempt in flight (README); (6) the pending field `readout.contamination_scan.canary_exempt_tasks` (Task 2b's dry run): a listed task is scanned without the canary and with every other term (D6); (7) D7.1 reads "no `rate_limit_event` reporting paid extra usage", and the criterion's check says so; the pids limit does not reach the verifier containers (README); (8) the kit writes no `containers-override.conf`, no change. **Mutations** (each guard disabled in a scratch tree of the tip, the tests run, the file restored): the reviewers' 55 of part A (six adapted where a fix changed the guarded text) and the 31 of part B, with 24 more for the part B fixes and the Task 7 rulings: 110 of 110 caught, each by a test of the guard it disabled (four were rerun on their own tests: two first caught only by the disk-stop test, which compared free space read at two moments and now allows for other processes' writes, one by the whole-schedule test, and one whose mutation was itself a syntax error). The rehearsal's whole-schedule test failed twice under load: the stand-in harness took its plan entry from a count of calls two harnesses started together could share, so two attempts met the usage limit; the stand-in now counts up to its own call (a test fix; the launcher is unchanged). **Re-review** (scoped, `61ebca3c..cf29ef3e`: the first reviews' 3 blockers and 10 majors closed; its own 1 blocker, 2 majors, 6 minors, all fixed, each with a test that failed first): a pre-session failure has no cost, so one rule settles the class at the close and at a ruling (a ruling to row 1 for a start with a cost gives an infrastructure failure, counted against both caps) and the slot record refuses a pre-session failure with a cost (R-B1); a resume needs a Ruling row for every distinct stop since the last resume and names each one missing, and `status` lists them (R-M1); a regrade's trial is `<attempt id>-regrade-<n>`, so concurrent regrades never share a compose project and removal by prefix stays the attempt's own; the regrade runs in its own session with its pid recorded, and reconcile stops a dead launcher's regrade (R-M2); a death after the containers' removal is no runtime stop at reconcile (R-m1); an interrupted load-gate wait decides nothing and the start stays open for reconcile (R-m2); the harness venv and the host-side overrides are checked before each start (R-m3); a failed `podman ps -a` is an incomplete scan and no confirmed removal (R-m4); any failure before the harness ran is a refused launch, no start (R-m5); a test for M4's refused newest claim (R-m6). **Mutations at the re-review tip:** the 110 again (55 of part A, 55 selector mutations), 13 more for these fixes, and the re-reviewer's 17 (three adapted where a fix changed the guarded text): 140 of 140 caught, each by a test of the guard it disabled (M42's guard, no regrade while the load gate is closed, is now pinned by R-m2's test, since m8's test has its regrade run); the kit's modules three times, 1342 passed each; radon at most 12 (`_has_ruling` and `_fits_row` split out, behaviour unchanged). **After merging `feat/lh-rehearsal` (`fc8ead76`), the coordinator's rulings on its second run:** a case-2 regrade that Harbor refuses because a declared artifact was not collected (its `RegradeError` "<path>: collection failed in the source trial; the record does not contain it", matched in the regrade's kept output with whitespace collapsed, every problem of that form, a non-zero exit and no trial written) leaves the verifier's 0 standing, an observation flagged `artifact_absent` that the readout counts per task and effort; case 1 is unchanged ("no reward after regrades") and any other refusal keeps its handling (D5 amended; `01519d62`); a `bypass` toward the relay itself (an address the sidecar resolved `relay` to in the same log) is a relay lookup timeout, counted and listed apart, so `egress_refused` holds only destinations outside the kit (D6; `3214c702`). **The scoped check of the re-review fixes** ("ready for a live probe"): `resume --clears` takes several thresholds, each after its own Ruling row, and resumes only when every threshold over its bound is named and ruled, naming the ones missing (S-M1); a Ruling row's cause is the whole cause, ended by its `:` (S-m1; both `35b6d89b`); a check before a start that cannot read the ledger returns it as a stop's reason, and an exception out of the launcher's loop interrupts the attempts in flight, stops the tranche naming it and joins them before the lock is let go (S-m2; `a464dfa2`). Each with a test that failed first. **Mutations:** six new, one per guard (CR-1, CR-2, SC-M1, SC-m1 and two for S-m2), each caught by its guard's test; three patterns adapted where a fix changed the guarded text (M24, X13, RR-m3), each caught again, as are X1, M25, X14, M42, RR-M2 and RR-m2 run again near the changes; every pattern of the three scripts (55, 74 and 17) matches once; the kit's modules three times at `a464dfa2`, 1359 passed each; radon at most 12. Spend to date: 0; subscription usage: none. |
| 2026-11-15 | Task 7, the rehearsal's second run, on `feat/lh-rehearsal` after merging `feat/lh-launcher` at `8b7cc8c6` (impl_code; spend: 0, no request reached the vendor, no credential read or named) | Six starts with the real CLI 2.1.311 in rootless Podman, on hof-topology-interpenetration and wal-recovery-ordering (images by digest as in `tasks.json`), the passthrough in `--rehearsal` (canary `sk-ant-oat01-` + 95 characters), agent limit 576 s in a kit copy. **Vendor unreachable before any session:** `vendor api: refused URLError … UNEXPECTED_EOF_WHILE_READING`, sidecar `dst 160.79.104.10:443 … outputBytes 0`, `bypass`. **Passthrough mode:** with a plain socket in the passthrough's place and no passthrough, `launch` stopped with "the passthrough records mode none, and this launch is rehearsal" and claimed no attempt. **1, the runtime check:** the canary written into the smoke's agent container (wal low) stopped the attempt, "a match of the runtime check in the attempt's containers"; a clean attempt's `podman.jsonl` shows inspect 0 for all four containers, logs 0 for the sidecar and export 0 for both `_main_1`, no finding. **2, regrades at once:** wal high and medium, case 2 under the load stand-in: `005-…-regrade-1__verifier__trial_main_1` and `006-…-regrade-1__verifier__trial_main_1` up together in 27 of 67 `podman ps -a` snapshots, each verifier ran to its end with reward 0, each container removed on its own (2 s apart). **3, a verifier cancelled by a kill:** SIGKILL to the launcher during hof high's verifier, reconcile cancelled it ("Trial … cancelled", `verifier_result` null); record regrade case 1, one regrade whose verifier gave 0.0, observation. **4, the canary exemption:** wal with `canary_exempt_tasks` [wal] not contaminated; with [] contaminated (15 hits, the GUID in `/app`), by the launcher's records and its own `scan_terms`/`contamination` on one trial. D7.1: 13 of 13 on two attempts; 2,784 requests, none refused by the allowlist; `readout.py --rehearsal` exit 0; canary after the sessions: pass over 8,302 files. **Reported:** Harbor refuses `trial regrade` of a trial whose declared artifact was not collected (`RegradeError … /app/solution/output.json: collection failed`), so hof's two case-2 regrades ran no verifier and are indeterminate, and a case 1 without the artifact ends as an infrastructure failure; a DNS timeout resolving `relay` is logged `bypass` and counted as a refused address (start 2: the relay, twice). No defect fixed in this run. Spend: 0. |
| 2026-11-15 | The launcher is on `main` (`ad016fc1`, merge of `feat/lh-launcher` at `23fa7153`); spend 0 | After Task 8's two reviews, the re-review and its scoped check ("ready for a live probe" at `8b7cc8c6`), the two container rehearsals of Task 7, and the last five items (the two findings of the second rehearsal; two thresholds over at once cleared by one resume; a Ruling row's cause matched whole; a ledger that cannot be read is a stop and the lock is held until the process's attempts end), which the coordinator checked by reading the diff. Kit modules 1,359 passed three times; 146 guard mutations, each caught by a test of its own guard. Full suite on the merge: 23,975 passed, 5 failed (the four nanoBragg tests of the standing baseline; one load failure that passes alone). The kit's last commit is `a464dfa2220e808565811fadde904b88cb98fa15`. **Not approved:** no `Live probe approved` row is written. It waits for the owner's two confirmations (paid extra usage is off for the account; the subscription's terms allow unattended runs of this size); the token of 23:00 on 2026-11-14 is in place, and whether the disclosed token of 22:28 was revoked is still open. **After the probe:** the second oracle pass in a quiet window, with the dry run of the contamination terms and the per-task canary exemption list; the freeze; the pilot; the ladder. |
| 2026-11-15 | Task 2b, second oracle pass (the qualifying pass), and the dry run of the contamination terms, on `feat/lh-oracle2` (impl_code; spend 0: no agent, no model or provider call, no credential read or named) | **Settings** (checklist items 2 and 3, coordinator rulings): owner question 4 is not decided, so vba-userform-port runs only as the labelled variant **`vba-userform-port-uidfix`**, never pooled; no `podman system migrate`, no sub-id or system change. The allowlist is the one on `main` (`oracle_check.sh`, D3's 13 names, overlay digest `3f99fe3c…c4f6` for all 16, no extra hosts). **CPU set `8-31`**: `host.cpu_set` is pending, so chosen by D2's rule (24 CPUs, the ladder off the other eight), the first pass's set, used for every trial. **Item 4** (the variant, `CONCURRENCY=4 REPEATS=2`): four trials overlapped; reference 2 of 2, untouched 0 of 2; `podman images` identical before and after; `podman events` shows no removal but the script's own release (no `-f`) of the one image it pulled; no `rmi` in the harness logs; each record holds only its own three containers and its own egress; largest cgroup peak 0.91 GB, free space at least 55.5 GB on `/` and 67.0 GB on `/home`. **Item 5** (SIGTERM to the script with four trials running, `wait "$pid"; rc=$?`): **exit 5** after 23 s, each trial `stop=signal` (harness exit 130); one verifier container and network that outlived its harness were removed by the script; nothing named after the four trials was left. The stop untagged `lh-oracle/vba-userform-port-uidfix:verifier`; `lh-keep/…` kept the image (same id) and the name was given back from it (the normal teardown of item 4 and of the pass lost no name). **Item 6, the pass:** `REPEATS=5 CONCURRENCY=4 GATE=24 CPUS=8-31`, 07:12:12 to 08:59:01 PST (**1 h 47 min**), 160 trials, `summarize.py --write oracle_second_pass.json`. Reference / untouched / qualifies: vba-userform-port-uidfix 5/5, 0/5, yes; vf2-speedup-networkx 5/5, 0/5, yes; wal-recovery-ordering 5/5, 0/5, yes; session-window-debug 5/5, 0/5, yes; production-planning 5/5, 0/5, yes; vpp-loss-divergence 5/5, 0/5, yes; batched-eval-parity 5/5, 0/5, yes; pretrain-shard-corruption 5/5, 0/5, yes; gsea-proteomics 5/5, 0/5, yes; lake-temp-glm 5/5, 0/5, yes; sound-change-cascade 5/5, 0/5, yes; hof-topology-interpenetration 5/5, 0/5, yes; shadow-relay 5/5, 0/5, yes; rs-archive-clone 5/5, 0/5, yes; retro-console-soc 5/5, 0/5, yes; roy-polymorph-cn 5/5, 0/5, yes. All 16 labels pass the rule. **Coordinator ruling: the ladder runs the 15 tasks that qualify unchanged** (`tasks.qualified`, `tasks.json` `second_pass.qualified`; D1 states it): vba-userform-port is not listed, because the unchanged task fails the rule here (its verifier writes no reward) and the launcher has no support for the labelled variant, which would be new launcher code needing its own review before the first paid call. The variant's result stays recorded evidence (`second_pass.variant_evidence`), labelled and never pooled. The cost: at most 225 attempts in the schedule instead of 240, one task fewer in the family; the owner can bring the task back before the freeze by deciding question 4, after which the unchanged task must pass the oracle check itself. Load at trial starts 8.4 to 22.1 (1-minute), 9.6 to 21.1 (5-minute), highest sample 31.6; no gate wait reported. **Peak memory** 3.74 GB (retro-console-soc's verifier), host memory used at most 81.1 GB of 125 (other sessions' mostly); **free space** at its lowest 54.8 GB on `/`, 62.5 GB on `/home`; images identical before and after. Only gsea-proteomics refused egress (40, the GSEA tool's two addresses, as in the first pass). The agent sidecar was sampled on the allowlist (`controlled egress`, 13 hosts) in 87 of 160 trials, 3 to 8 per label. **Sub-tests:** `verifier/ctrf.json` is a sub-test count for 13 tasks; lake-temp-glm's holds one test (pass or fail only); vba-userform-port's is a scoring wrapper, its graded checks being the hidden traces (`trace_summary.json`, 29 of 29 / 0 of 29); wal-recovery-ordering's total is the suite's (97) on a pass and the gates' (2) on a gate failure, so it is read as pass or fail only. **Contamination terms, frozen in `ladder.json`:** `harbor-framework/terminal-bench` and `tasks/<task>/solution` for the 16 (held by a test to `tasks.json`'s checked copy), and the canary by its SHA-256 `2c7c9d04…6452` (one identifier in all 16 packages). **`canary_exempt_tasks`:** vba-userform-port, wal-recovery-ordering, session-window-debug, vpp-loss-divergence, batched-eval-parity, pretrain-shard-corruption, sound-change-cascade: the seven whose pinned agent image holds the canary in copies of its own `environment/` files (`tasks.json` withholding; held by a test). **Dry run** (the launcher's `contamination` over 106 reference, 106 untouched and 16 install trials of every oracle job, the 90 recordings and the 3 public archives; each package's files; each agent image's whole file system, pulled again one at a time and mounted read-only, for the 17 non-canary terms): the 17 terms fired nowhere. With the exemptions applied, the canary fired on no untouched run, install run or recording. It fires on reference runs of four non-exempt tasks (vf2-speedup-networkx, rs-archive-clone, retro-console-soc, shadow-relay; 24 trials), in files the reference solution wrote, which carry the canary: the term finding reference material, which is what it is for (coordinator ruling: correct, no change). Every `instruction.md` carries the canary on its first line; Harbor strips it before the agent sees it. A public archive shows the canary reaching a transcript through a tool result printing a starting file outside the declared artifacts, which is why the list comes from the whole image. **Filled in `ladder.json`** (coordinator rulings; pending entries moved to `filled` with this row as source): `tasks.qualified` (the 15), `tasks.load_sensitive` (`[]`: no reference failed on the pinned images in either pass; wal-recovery-ordering's failure under load was on a local build), `tasks.overlay_digests` (`3f99fe3c…c4f6` for each of the 15, equal to the launcher's digest of its allowlist), `tasks.extra_hosts` (`{}`), `network.agent_phase.allowed_hosts` (the 13 names of `oracle_check.sh`), `host.cpu_set` (`8-31`), `readout.graded_outcome.verifiers` (`"ctrf"` for the 13 qualified tasks whose report gives a sub-test count; lake-temp-glm and wal-recovery-ordering print pass or fail only, and vba-userform-port runs no attempt: README). **Still pending, and who fills it:** `usage_limits.vendor_headers_confirmed` and `allowance_guard.utilisation_header` (Task 4, the live probe); `schedule.order.seed`, `schedule.order.hash` and `readout.fall_bound.seed` (the freeze, Task 9). The allowance inputs are outside `ladder.json` (the owner's, D4). **What changed for 15:** the schedule (`ladder.schedule` already follows `tasks.qualified`: 15 blocks a round, 225 slots, smoke gsea-proteomics and pilot rs-archive-clone unchanged; no code change); `schedule.blocks_per_round` (`if_none_drops: 16` replaced by `count: 15` with its source); the caps (per task, `tasks.list` keeps all 16 entries; `ceiling.starts` stays 240, an upper bound the schedule does not reach; reruns after cuts count against it); the readout's cells (per task in the export, so 15; no code change); tests: new ones hold `tasks.qualified` to the second pass's unchanged-task evidence, the schedule to 15 × 3 × 5 slots and `blocks_per_round.count`, and the overlay digests to the launcher's; the launcher tests' kit copy puts the seven fields back to pending so its three stand-in tasks run as before (`_unfilled`); the readout's graded tests pick a task with and one without a reported verifier from the criterion; plan D1 (the surviving tasks) and D7.3 (15 blocks, 225 slots). **Manifest** rewritten (unfrozen; `check` passes): `e76e0b06010e5ea4bf7274efddbdc52d8ba59e4b6cafcd5a6faa1598050efe2a`. Spend: 0; subscription usage: none. |
| 2026-11-15 | Correction to the row "The launcher is on `main`" (ordering) | Kept as written; it lists the second oracle pass "after the probe". The pass does not depend on the live probe: it spends nothing and uses no token. It ran on 2026-11-15 and is recorded in the row "Task 2b, second oracle pass" above. What is left, in order: the owner's two confirmations, the `Live probe approved` row and the probe, the freeze, the smoke, the pilot, the ladder. Spend: 0. |
| 2026-11-15 | The 15-task configuration and the second oracle pass are on `main` (`034bffd8`) | Merged with the documentation pass of the day after a whole-suite run on the integration branch (23,912 passed; the four standing nanoBragg failures; 67 failures in `test_prompt_resume_child`, the provider isolation backend modules and `test_executor_retirement_cutoff` that come from starting the run in a new tmux session and pass when the modules are run directly, 263 of 263 with one load-sensitive test passing alone). The kit's last commit, which a `Live probe approved` row must name: `4e1936955e269dc5ddd15495cc7f6722ec62747d` (`git log -1 --format=%H -- experiments/long_horizon_tasks`). Manifest `e76e0b06010e5ea4bf7274efddbdc52d8ba59e4b6cafcd5a6faa1598050efe2a`, not frozen, `check` passes. Owed at the freeze, when `ladder.json` changes anyway: its description string `classification.classes.observation.reward` still reads "0 when the verifier gives none", against the ruling that a reward is only what a verifier gave (no code reads the string). The live probe is still not approved: the owner's two confirmations are open. Spend: 0. |
| 2026-11-17 | The owner's answers to the open decisions (given in the coordinating session) | **Paid extra usage is off for the account:** "yes". **The subscription's terms allow unattended runs of this size:** "yes". These are the two confirmations the live probe needs; the first is owed again at the pilot and the freeze, the second again at the freeze. **Whether the token disclosed on 2026-11-14 was revoked:** "dont knwn". Recorded as not known: it is treated as possibly valid until 2027-11-14, and the replaced token (`$HOME/.local/state/lh-secret/token`) stays the one in use. **The allowance (question 2):** "30 percent weekly". Not settled, and asked again: whether 30 percent is the share kept free or the share the ladder may use; the five-hour share; the hours in which attempts may start; the meter readings. Nothing is entered with `ladder.py allowance` until it is; the smoke stays closed. Spend: 0. |
| 2026-11-17 | Live probe approved | 4e1936955e269dc5ddd15495cc7f6722ec62747d Three sessions of the recordings' scratch task at effort low, medium and high, no retry; 6 requests and priced USD 0.15 a session, 18 requests and USD 0.45 in all, `claude-haiku-5-5` only, the CLI's own budget USD 0.10 a session; through `live_probe.sh` and the passthrough only. Approved by the coordinating session under the budget delegation of `AGENTS.md` and roadmap owner decision 18, on the owner's two confirmations of this date. One try. |
| 2026-11-17 | The live probe (Task 4): the three sessions ran and the route works; the script was cut off before its verdict (run_experiment; 3 requests, priced USD 0.0017, `claude-haiku-5-5` on the owner's subscription) | **First start refused, nothing spent.** `live_probe.sh` exited 3: `~/lh-cache/scratch/recording-task/task.toml` was missing (the scratch tree did not exist). No state was claimed, so the one try was unused. The coordinator rebuilt the task with `record.sh make_task` (a local copy, no request; the kit unchanged). The README's run order does not name `make_task`; owed. **The one try, started 00:54 PST at kit commit `4e193695`.** Sessions at effort low, medium and high (00:54 to 01:05), each: one request (the scratch task says there is no task, so the session answers once and ends), vendor status 200, response model `claude-haiku-5-5`, credential `live`, `terminal_reason: completed`, CLI 2.1.311, `apiKeySource: none`; egress log: `relay:8080` only; runtime checks `exit 0`, `exit 0`. **Priced** USD 0.0012861, 0.00018273 and 0.00019923 (0.00166806 in all; 3 of the 18 requests allowed), each equal to the CLI's `total_cost_usd`. The first request's prompt was 6,164 tokens (2 input, 6,162 written to the one-hour cache); the later sessions read 5,823 from that cache and wrote 339. Cache marks `system.1:1h`, `system.2:1h`, `messages.1.content.0:1h` on all three; no fall back to five-minute caching. **Headers (item 2).** Names, the same on all three: `date`, `content-type`, `transfer-encoding`, `connection`, `cache-control`, `anthropic-ratelimit-unified-overage-status`, `-representative-claim`, `-upgrade-paths`, `-reset`, `-7d-surpassed-threshold`, `-7d-reset`, `-7d-status`, `-fallback-percentage`, `-overage-disabled-reason`, `-7d-utilization`, `-status`, `strict-transport-security`, `request-id`, `traceresponse`, `anthropic-organization-id`, `anthropic-workspace-id`, `content-security-policy`, `vary`, `server`, `server-timing`, `cf-cache-status`, `x-robots-tag`, `cf-ray`. Values: `overage-status: rejected`, `overage-disabled-reason: out_of_credits`, `upgrade-paths: overage`, `status: allowed_warning`, `7d-status: allowed_warning`, `7d-utilization: 0.98`, `7d-surpassed-threshold: 0.75`, `representative-claim: seven_day`, `fallback-percentage: 0.5`, `reset` and `7d-reset: 1795280400` (2026-11-21 09:00 PST). No five-hour header and no `overage-in-use` header was sent. The stream's `rate_limit_event` had `isUsingOverage: false`; `cachedExtraUsageDisabledReason` in the exported configuration is `out_of_credits`. **Ruling LH-R1:** the paid-usage stop's `overage-status` clause stays as built and now precedes the first paid request (D4, revised paragraph). **For the allowance:** the owner's weekly limit stood at 98% at 01:00 and resets on 2026-11-21 at 09:00 PST, so no tranche can start before then whatever share is set; the vendor reported no five-hour figure on these responses. **What did not finish.** The file-set scan (the script's last step but one) began at 01:05 and was still running when the machine restarted at 09:23 for a kernel update: `file-set-scan.txt` is empty and no `probe.json` was written. The scanner read about 3 MB/s on one core, over about 31 GB (the repository and `~/.claude/projects`). The three egress sidecar containers and their networks were still present (exited) after the script's `remove_containers`; the coordinator removed them. Cause not established; owed before the launcher is trusted to clean up. **Finished by hand, no request made.** From 10:57 the coordinator ran the script's two remaining steps unchanged (the scanner at `4e193695`, then the script's own verdict code, copied to `~/lh-cache/logs/live-probe-2026-11-17/`); that scan is still running as this row is written, and its verdict gets its own row. A second pass over the same five paths with the parallel scanner (below) read 304,157 files in 33.5 minutes on 24 processes: no match, nothing unreadable, 103 symlinks or special files skipped, exit 0 (`parallel-scan.txt` there, sha256 `6b91636e…`). The passthrough's request log is `~/.local/state/lh-probe/passthrough/requests.jsonl` (sha256 `f4b6046b…`). Cutting fixtures from the probe's recordings (item 2) is owed. **The approval row above is used up:** one start claimed the state, and the kit has changed since. |
| 2026-11-17 | `token_scan.py` reads files in parallel (impl_code, revised once; reviewed and merged by the coordinator as `aa7139ce`; no spend) | `--jobs N` on `scan` and `canary`, default the CPU count; `--jobs 1` is the serial path. Files are read in forked worker processes, at most 256 handed out ahead; each file's kind is taken in the parent when the walk lists it, and the workers are started before the walk. Output lines, their order and the exit codes are the serial scan's; a worker that raises or dies ends the scan as incomplete (exit 2, `failed <class>`). The first version took the kind in the worker, which let a slot socket removed just after an attempt be reported unreadable: `test_no_credential_is_in_any_file_environment_or_command_line` failed in the whole suite and 1 time in 72 alone under load; after the fix, 0 in 156. Checks: the four long-horizon modules, 735 passed; the whole suite on the first version, 73 failed, of which this one was the change's; 67 pass when run outside a new tmux session (the known launch context), 4 nanoBragg demo tests need the main checkout's sibling path, and the seed-set build test fails on `main` as well (under diagnosis; see the seed-set plan). Large files are not split: the 677 MB largest file sets the floor. |
| 2026-11-17 | The live probe's verdict file, and ruling LH-R2: Task 4's probe is taken as passed (no request made) | **The script's own verdict is `fail`.** The unchanged scanner at `4e193695` ended at 16:21 after 5 h 24 min: 297,631 files read, no match, exit 2 (incomplete). Its 15 `unreadable … FileNotFoundError` lines are all transcript folders under `~/.claude/projects` that were listed when the walk reached that directory and were gone when it came to them: 13 folders of structural-search candidate checkouts (`-home-ollie-ss-work…-agents-<id>-cand-N`), one of a pool smoke's judges and `-tmp-clitest`. The script's verdict code then wrote `probe.json`: `pass: false`, one failure, "the file-set scan did not end clean", `stopped: null`, no tranche event; per session one request, `terminal_reason: completed`, priced USD equal to the CLI's `total_cost_usd`, runtime check `exit 0`, `exit 0`. `probe.json` sha256 `2fb7c71c…`, `file-set-scan.txt` `fd8380d4…`, both kept as written in `~/lh-cache/recordings/live-probe/` and copied to `~/lh-cache/logs/live-probe-2026-11-17/`. **Ruling LH-R2: the probe is taken as passed.** Every condition of item 4 holds on the record: three sessions `completed`; every request in the passthrough's log, sent with the real token and answered 200 by `claude-haiku-5-5` at the session's effort; the priced figure equal to the CLI's in each session; the egress logs show the relay only; the runtime checks found nothing in the containers. The scan condition is held by the second pass (the row above): 304,157 files over the same five paths, read between 13:39 and 14:12, no match and nothing unreadable. None of item 5's three failures occurred (the vendor accepted the token; the meter agrees; the scanner found no copy). The serial scan was incomplete because folders were removed during its five hours, not because a file could not be read — if wrong, a copy of the token lay in one of those 15 folders and nowhere else, in a folder removed before 13:39 so that neither pass read it; the remedy is then D4's (the owner revokes and replaces the token), and a later scan cannot show it either way. **What this opens:** the rest of Task 4 and Task 5 may proceed; no ladder attempt is approved by it. **Owed, for Task 5:** a scan over a live file set reports a folder removed between listing and reading as unreadable, so a long scan is likely to end incomplete; the launcher needs a stated rule for that case (for instance one more pass over the named paths, which a 33-minute scan allows) before its scan result can gate anything. Spend of the probe: 3 requests, priced USD 0.0017, counted inside the ladder's USD 200. |
| 2026-11-17 | The owner's answer on the allowance | Asked whether "30 percent weekly" is the share experiments may use or the share kept free, the owner answered at about 22:10 PST: "share experimnets may use". So experiments may take up to 30% of the weekly limit. The same evening: "dont hold it. need to burn 10% of my weekly limit between now and 9 am" (said of the development work the coordinator was holding back to spare the limit; that work was started). **Not settled by this:** the five-hour share, the hours and the meter-reading protocol, and the state of the meter itself: the vendor's headers of 01:00 that day gave the weekly limit as 98% used with its reset on 2026-11-21 09:00 PST, which leaves 2%, not 10%. The coordinator asked the owner for both meters' readings; no paid call starts before a reading is recorded here, because a unit cut by a usage limit fails the smoke and a smoke slot is never run again. Spend to date: 3 requests, priced USD 0.0017 (the live probe). |
| 2026-11-17 | The owner's meter reading differs from the probe's headers (open before the ladder's freeze) | The owner's usage screen at about 22:15 PST: five-hour 69% used, resets 23:49; week, all models, 56% used, resets 2026-11-18 08:59; week, Fable, 72%; usage credits off. The probe's three responses at 01:00 the same day carried `7d-utilization: 0.98`, `7d-reset` 2026-11-21 09:00 PST and `representative-claim: seven_day`, with no five-hour header. The two cannot be one meter: the reset days differ, and 98% at 01:00 cannot be 56% at 22:15 in the same week. Not explained. Candidates, none checked: the `setup-token` token is metered in its own weekly window; the header reports a per-model window (the requests were `claude-haiku-5-5`); the usage screen and the header round or define use differently. **What it changes:** the sentence "no tranche can start before 2026-11-21" in the probe's row rested on the header and is withdrawn for the seed-set study, whose units use the owner's login (its smoke was approved on the owner's reading, seed-set ledger ruling R13). For the ladder, whose requests use the token, the launcher's allowance guard takes the owner's reading while the vendor's limit answer follows the token's meter; which meter governs the token is owed before the ladder's freeze (the first request of the smoke slot shows the header again at no extra cost; if it still reads near 98% with another reset than the owner's screen, the allowance inputs are set from the header). Spend: none by this row. |
| 2026-11-18 | On `main`: the teardown fix, ruling LH-R3 and the probe's fixtures (impl_code by two agents; coordinator integration; no spend) | **Sidecars left after the probe (cause confirmed):** the agent container shares the egress sidecar's network namespace, `podman ps -a` lists oldest first, and `live_probe.sh` removed containers one at a time, so Podman refused the sidecar (`has dependent containers`) behind `/dev/null`, and the network stayed in use. Fix `4240d62f`: one `podman rm -f -t 5 --depend` call, then the networks, then a listing that names anything left; a stand-in podman that models the dependency backs a test that fails on the old script. `ladder.py` was not affected (it retries until no container of the attempt is listed); it does not check the networks afterwards, which the plan does not ask. **Ruling LH-R3 (coordinator):** an entry inside a walked directory gone (`FileNotFoundError`) when it is read is printed `vanished <path>` and leaves the scan complete; a named path, every other error and "no file read" stay incomplete. Reason: one pass over a changing set is not atomic anyway, and the copy that was at a vanished path is gone from it. If wrong: a copy in a file deleted during a scan is missed by that scan; the next scan reads wherever it went. The launcher's teardown scan covers only the attempt's directory, its kept container files and (smoke, pilot, rehearsal) the exported container file system (`ladder.py` near 2263 and 1937), not the whole file set of D4; the round's whole-set read in D4's list has no code yet, owed before the ladder. **Fixtures (Task 4 item 2):** `fixtures/live-probe/session-{low,medium,high}.json` and `passthrough-log.json` cut by `cut_fixture.py live-probe`, indexed with SHA-256 in `recordings.json`; every vendor and account identifier replaced by one shared placeholder; the scanner with the probe's fingerprint finds nothing (exit 0); the coordinator's own check found none of the raw log's identifiers in any changed file. Tests now drive the passthrough and the launcher with the recorded 200s (`overage-status: rejected`): passed on, no stop, priced at the CLI's figure (LH-R1). **Found by the fixtures agent:** the probe ran without `--agent-setup-timeout-multiplier 3` (the ladder's 3; install time only), owed in `live_probe.sh` before any second probe. Manifest rewritten (not frozen, label `f67c7f99…`). **Checks:** long-horizon modules 1,207 passed; whole suite on the integration branch twice (the second with the authoring and MLE-bench merges): 24,659 passed, 71 failed, all in the four modules that fail only under a whole-suite launch (263 of 263 pass rerun directly) and the four nanoBragg tests that need the main checkout's sibling path. `main` fast-forwarded. |
