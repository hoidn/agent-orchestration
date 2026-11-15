# MLE-bench Task Family Plan (Roadmap Phase 5b, Steps 10 To 12)

**Status: Plan; written 2026-11-15; not reviewed; nothing built, nothing run, nothing spent, and no
spend authorized.** This page turns steps 10 to 12 of
[roadmap Phase 5b](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed)
into a plan: a second long-horizon task family built from single MLE-bench competitions (owner
decision 17). The roadmap owns the direction. [`AGENTS.md`](../../AGENTS.md) ("Experiment rules")
owns the approvals and their limits; this line has no rule there yet, and the
[wording proposed for it](#proposed-wording-for-the-agentsmd-rule) is at the end of this page. The
[feasibility report](../reports/2026-11-13-mle-bench-subset-feasibility.md) holds the evidence cited
here as "report §n"; it is a desk study and nothing in it was run. The
[long-horizon plan](2026-11-13-long-horizon-task-family-and-seed-plan.md) (cited as "the ladder
plan", with its decisions as "ladder D1" to "ladder D7") owns the credential route, the passthrough,
the launcher and the rules this plan reuses; its kit is described in the kit's
[README](../../experiments/long_horizon_tasks/README.md). This plan owns the competition list, the
success definition, the qualification check, the limits, the stop rules and the ledger of this
line. Its commands are for this machine and are not copyable examples. Spend is authorized only as
the [ledger](#ledger) records. Until this plan is reviewed and its kit exists, the only long-horizon
kit to use is the ladder's.

**The answer first.**

- **Preparation can start today and needs no owner action for its first nine tasks:** the kit, a
  synthetic miniature competition as a test fixture, the verifier that runs the grader, the
  withholding checks, the configuration as data, the wrapper around the reviewed launcher with its
  guard tests, its independent review and a zero-spend rehearsal (about 57 hours, a planner's
  estimate).
- **Real competitions wait for the owner's Kaggle account, token and rule acceptance.** The three
  CPU-only candidates come first: they need neither the GPU nor much disk.
- **No paid attempt can start before four things:** the Terminal-Bench live probe has shown that the
  vendor accepts the subscription route; each competition has passed the qualification check on
  this machine; the wrapper has passed its review and rehearsal; and the owner has approved the
  line, because its ceilings are above what the coordinator may approve alone.
- **The screen is 39 attempts in two tranches** (9 on the three CPU-only competitions, then 30 on
  the GPU), at effort `medium`, capped at USD 8 an attempt and USD 200 in all. Every dollar figure
  on this page is a priced-token figure and an estimate until measured.
- **The reviewed launcher is not changed.** A second small kit loads it and points it at this
  family's data. The cost of that choice: no attempt on the GPU runs beside another attempt, and
  this line never runs while the Terminal-Bench ladder has an attempt in flight.

**Headline exit test (fails today):** `experiments/mle_bench_tasks/results/family.json` exists,
names its criteria and package digests, and lists every screened competition with its screen class
and, for each placed competition, its medals of fifteen attempts by effort. After a stop no
`family.json` is written.

## Words used on this page

| Word | Meaning here |
| --- | --- |
| Competition | One past Kaggle competition as MLE-bench repackages it (report §2): a description, public data, a preparation script that builds held-out answers, a grading function and a snapshot of the private leaderboard |
| Medal | A score at or past the competition's bronze threshold, computed by the benchmark's grader from the leaderboard snapshot (report §3.1). "Any medal" is the benchmark's headline measure |
| The band | 10 to 30 percent success for a direct `claude-haiku-5-5` session (owner decisions 14 and 17) |
| The ladder | The Terminal-Bench effort ladder of the ladder plan: 15 tasks, three efforts, at most 240 starts and USD 200 (owner decision 16) |
| The reviewed kit | `experiments/long_horizon_tasks/`: the launcher `ladder.py`, the passthrough, the relay, the token scanner, the slot record and the readout, on `main` after two independent reviews and two zero-spend rehearsals |
| Passthrough, relay | The one host process that holds the subscription token, and the credential-free container that forwards the agent's requests to it (ladder D4, route B) |
| Attempt, start, slot | One whole agent session on one competition; a start is an attempt the launcher began; a slot is a place in the schedule |
| Observation, cut, infrastructure failure, stop | The launcher's classes for how a start ended (ladder D5). Only an observation enters a count. A cut is an attempt ended by a usage limit; its slot is run again |
| Tranche | One run of the launcher under one configuration label, one state directory and one ceiling |
| Configuration label | The SHA-256 of a tranche's manifest. Observations under different labels are never pooled |
| Criterion | A tranche's `ladder.json`: every limit and rule as data |
| Priced-token figure | Metered tokens times the frozen price rule (ladder D4). It caps and reports usage. Nothing is billed |
| Scout report | A fact-finding note of 2026-11-15, written beside this plan and not committed. Cited by its section letters. Each fact cited from it was read in the installed harness's or the reviewed kit's source, or run on this machine with no model call, and the note says which. Tasks 7 and 11 establish again, on this kit, every such fact a decision rests on |

## Scope, and what this line claims

- **Step 10, preparation.** Each candidate competition becomes a task the reviewed launcher can run,
  with the private answers, the grader and the medal thresholds outside the agent's container, and
  passes a qualification check on this machine.
- **Step 11, the screen.** Thirteen candidates, three attempts each at one effort: 39 attempts. Its
  only purpose is to exclude the competitions that are clearly at the floor or clearly above the
  band.
- **Step 12, the placement.** Each competition that survives the screen gets fifteen fresh attempts
  (five at each of `low`, `medium` and `high`, the ladder's size per task). One enters the family
  only at 1 to 5 medals of fifteen.
- **What is measured:** how often a direct `claude-haiku-5-5` Claude Code session earns a medal on
  each competition, under this plan's configuration: CLI 2.1.311 signed in through the subscription
  route, the tools Bash, Edit and Read, the allowlist network policy, and a fixed set of pretrained
  weights (M6). Every attempt also records its score, its leaderboard percentile and whether it is
  above the leaderboard median.
- **Not claimed:** anything about a workflow; that a competition's true rate lies in 10 to 30
  percent (three attempts cannot show it, and fifteen give "screened at n of 15", as in ladder D6);
  an ordering of competitions; any comparison with a published MLE-bench rate, which used other
  agents, an open network and 24 hours of prompting (report §6.1, §9.1); that a medal reflects work
  from scratch and not recall (M7).
- **Kind of experiment.** The family is oracle-scored: a deterministic grader scores each attempt
  and there is no judge. Its qualification is the check of M2, which stands in for the oracle check
  of the ladder. "Better", wherever a later comparison uses this family, means Pareto dominance over
  quality and priced-token cost.
- **Not in this plan:** the comparison of a staged workflow with a direct session on these
  competitions. It needs its own approval, like roadmap step 9.

## The owner's standing rules, as constraints

| Rule | Where it comes from | What it means here |
| --- | --- | --- |
| Subscription only, no API key | `AGENTS.md`, "Credential"; roadmap decision 18 | Every model call goes through the owner's Claude subscription. The benchmark's own harness, which puts an API key in the agent's container (report §5.1), is not used |
| The token stays in one host process and enters no container | `AGENTS.md`, "Credential" | The passthrough of the reviewed kit, unchanged. One passthrough process at a time, so this line and the ladder never have attempts in flight together (M5) |
| Haiku only for this line; no Fable in any experiment call | `AGENTS.md`, "Cost default"; decision 17 names `claude-haiku-5-5` | The launcher's and the passthrough's model checks, unchanged |
| No uncalibrated quality claim | `AGENTS.md`, "No uncalibrated experiments" | The qualification check and the evaluator check of M2 pass before any paid attempt. The screen and the placement are themselves calibration and make no claim about a workflow |
| "Better" is Pareto dominance over quality and model-aware cost | `AGENTS.md`; [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator) | No comparison is made here. Cost per attempt is recorded so that a later one can be |
| Decisions and limits in the ledger before the first call | `AGENTS.md`, "Record experiment decisions" | The [ledger](#ledger) holds each tranche's label, caps and ceilings before its first start; the launcher refuses without that row |
| A competition enters the family only at 10 to 30 percent success | Roadmap decisions 14 and 17 | The placement rule of M1 |
| Attempts in parallel up to the benchmark's 24-hour limit; Haiku spend up to USD 200 per calendar day for this family | Roadmap decision 17 ("parallel up to 24 hours ok , haiku spend up to $200 per day ok"), a priced-token figure under decision 18 | M5 and M9. The daily figure is kept by construction: no tranche's ceiling is above USD 200, and a tranche starts only on a later calendar day than the one on which the previous tranche's last attempt settled |
| The coordinator asks the owner for a tranche above about USD 100, cumulative spend above about USD 300, a new experiment line, or a top-up after a null | `AGENTS.md`, "Budget delegation"; roadmap decision 12 | The screen's second tranche and the placement are above USD 100, so the owner approves the line (owner action 9). A subagent never spends on its own authority |
| Usage limits are shared with the owner's own sessions; every tranche says how it pauses and how a cut attempt is counted | `AGENTS.md`, "Credential" | M8 |

## Candidates

The thirteen candidates are the ranked subset of report §8.2. Sizes are the benchmark README's
figures as the report read them (report §3.2, §3.3). **They are a rough guide only:** the repository
does not say what they measure, and the figure for the Russian text-normalization competition cannot
be right, since its preparation script writes 10.5 million rows (scout report C; probably a few
hundred MB, an estimate). Each competition's size on disk is measured after its download (Task 10).
"Class" is the resource class of M5; "needs a GPU" is the report's estimate, not a measurement. The competition's id in the benchmark is its Kaggle slug, and
its rules page is `https://www.kaggle.com/competitions/<slug>/rules`.

| Order | Kaggle slug | GB | Class | Rank in report §8.2 |
| --- | --- | --- | --- | --- |
| 1 | `leaf-classification` | 0.036 | CPU | 7 |
| 2 | `text-normalization-challenge-russian-language` | 0.01 | CPU | 10 |
| 3 | `mlsp-2013-birds` | 0.59 | CPU | 11 |
| 4 | `us-patent-phrase-to-phrase-matching` | 0.002 | GPU | 4 |
| 5 | `tweet-sentiment-extraction` | 0.003 | GPU | 1 |
| 6 | `learning-agency-lab-automated-essay-scoring-2` | 0.036 | GPU | 3 |
| 7 | `chaii-hindi-and-tamil-question-answering` | 0.032 | GPU | 13 |
| 8 | `jigsaw-toxic-comment-classification-challenge` | 0.06 | GPU | 8 |
| 9 | `lmsys-chatbot-arena` | 0.18 | GPU | 12 |
| 10 | `whale-categorization-playground` | 0.73 | GPU | 6 |
| 11 | `petfinder-pawpularity-score` | 1.04 | GPU | 2 |
| 12 | `kuzushiji-recognition` | 4.51 | GPU | 9 |
| 13 | `cassava-leaf-disease-classification` | 6.19 | GPU | 5 |

The order is the order of preparation: the three CPU-only competitions (0.64 GB together by the
README's figures), then the GPU competitions from the smallest. The total is 13.4 GB (report
§8.2). The report expects 2 to 5 of the 13 to fall in the band (report §1, an estimate). The three further CPU-only competitions that
report §8.2 offers as upper anchors are not in the screen: the roadmap stages 13.

## Decisions

Each decision gives the choice, the reason, what it costs if wrong, and who decides: **owner** (the
owner's to make; the plan gives a recommendation) or **coordinator** (the coordinator can rule within
decision 17 and records the ruling under [Rulings](#rulings)). Nothing here is frozen until its
tranche's criterion is frozen and its label is in the ledger.

### M1. Success, the screen's classes and the placement (owner: the definition; coordinator: the classes)

- **Success is any medal,** as the roadmap proposes: the benchmark's headline measure, predeclared by
  someone else and published for every agent (report §7). The verifier's reward is 1 for a medal and
  0 otherwise, which is the only reward the reviewed slot record accepts.
- **Every attempt also records four graded outcomes:** the raw score; the leaderboard percentile;
  whether the submission is valid; whether it is above the leaderboard median. The benchmark's grader
  gives the other three and no percentile (scout report B), so this plan fixes it: the share of the
  snapshot's scores that the attempt's score beats or ties, in the metric's direction; an attempt
  with no score has no percentile, and it is never written as zero. The outcomes place nothing by
  themselves, except as the screen's floor rule below says.
- **The screen's classes, fixed before spend.** With three observations of a competition:

| Observed | Class | What follows |
| --- | --- | --- |
| 3 medals of 3 | Above the band | Out. A competition at 30 percent shows this 2.7 percent of the time |
| 0 medals of 3, and no attempt above the leaderboard median (an invalid or missing submission counts as not above) | Floor | Out |
| Anything else: 1 or 2 medals, or 0 medals with at least one attempt above the median | Survives | Goes to the placement |
| Fewer than 3 observations | Not screened | Reported with its count; it neither survives nor is out, and nothing is rerun to fill it |

- **Why the floor rule uses the score.** Zero medals of three cannot exclude a competition: one at
  20 percent shows it about half the time. The continuous score can (report §7): where scores are
  stable between runs, three attempts below the median mean a medal is far away, and where they are
  noisy against the medal margin (report §6.2), a competition near the band is unlikely to land
  below the median three times.
- **The placement.** A surviving competition gets fifteen fresh attempts: five at each of `low`,
  `medium` and `high`. It enters the family at 1 to 5 medals of fifteen, labelled "screened at n of
  15 attempts" and never "in the band", with the ladder's rule for fewer than fifteen observations
  (ladder D6). The screen's three attempts are printed beside the fifteen and are not pooled with
  them: a competition was chosen because of them, so pooling would bias its count upward.
- **If fewer competitions are placed than is useful.** The family supplements the Terminal-Bench
  set, so one placed competition is already useful. If none is placed, the line ends with a report.
  Two other definitions then exist, and each is **a later owner decision with its own request, never
  a silent switch**: above the leaderboard median (published for every agent; an easier bar), and a
  per-competition score threshold frozen from this line's attempts and applied only to fresh
  attempts (report §7; the only definition that can place most competitions by construction). The
  recorded scores let either be assessed on paper first, at no spend.
- **Cost if wrong.** If "any medal" is too coarse, few competitions are placed and the placement's
  spend buys little. If the floor rule is too strict, a competition near the band is dropped after
  three attempts; the readout prints every dropped competition's three scores against its
  thresholds so that the owner can see it.

### M2. The qualification check and the evaluator check (coordinator)

The benchmark has no reference solution that trains a model. What can be checked is that the grader,
as the verifier runs it, tells a perfect submission from a useless one.

- **Three legs, each through the verifier path an attempt uses** (the same package, the same
  verifier image, the allowlist policy, the tranche's CPU set):
  1. *Answers.* The harness's reference agent writes the held-out answers as the submission. It must
     earn reward 1 with a gold medal.
  2. *Sample submission.* The competition's own sample submission is submitted. It must earn reward 0
     and be valid, and its score must equal the floor the benchmark's own test lists for it (report
     §3.2, column "Floor"), where one is listed.
  3. *Untouched.* An agent that does nothing leaves no submission. It must earn reward 0, with a
     reward the verifier wrote, not a missing one.
- **Repetitions: two of each leg.** The grader is deterministic and the legs take seconds, so the
  repeat checks only that the path is stable: the two scores of a leg must be equal. The ladder
  needed five because some of its verifiers depend on timing.
- **A competition qualifies only if all six runs give what is listed.** One that fails and has no
  host-side fix is dropped, is not replaced, and its slots are not given to another competition. A
  failure means one of three things, and the ledger row says which: the preparation is defective (the
  benchmark's README lists some; report §6.4), the thresholds do not fit the rebuilt test set
  (report §3.1), or the wrapper is wrong.
- **What the check does not show:** that a medal is reachable. That rests on the published medal
  rates of report §7, which come from other agents.
- **What is already known.** The benchmark's grader was run on this machine, on the host, with
  hand-made answers for the three CPU-only competitions: the answers file earned gold, the uniform
  submission of `leaf-classification` scored the listed floor, and a missing or malformed file got no
  score and no medal (scout report B). That shows the grader, not the verifier path, which Task 7
  builds.
- **The evaluator check that `AGENTS.md` requires on known controls** is the same six runs, read as
  a test of the measure: the controls are the answers (known gold), the sample submission (known no
  medal) and no submission (known zero). The predeclared margin is "gold on the answers, no medal on
  the other two"; the predeclared error rate is zero wrong outcomes over every control of every
  competition in the tranche. The synthetic fixture competition validates the code and qualifies
  nothing.
- **Cost if wrong.** A grader that scores a competition wrongly would place it wrongly; the three
  legs bound the two ends of the scale and nothing in between.

### M3. Withholding (coordinator)

- **Two images per competition, built here.** The agent image holds the public data, the
  description, the sample submission and the pretrained weights (M6). The verifier image holds the
  held-out answers, the benchmark's grader and the leaderboard snapshot with the thresholds. The
  agent's container never holds any of the last three, and the benchmark's package is not installed
  in it. The installed harness supports this shape: a verifier in its own container, built from its
  own image, receiving only the files the task declares as artifacts (scout report D3).
- **Only the submission crosses.** The task declares the submission directory as its one artifact.
  An attempt that writes no submission still reaches the verifier and gets a written reward of 0
  (run on a scratch task: scout report D5).
- **The verifier image** pins the benchmark at commit `507f92e` and the dependency versions of the
  benchmark's own image (scout report A: unpinned, today's versions do not install together, and a
  newer pandas could change what the preparation writes). It sets the grader's data directory and
  working directory, because the grader writes a cache where it is run (scout report B). Both images
  need `bash`, which the harness's readiness probe calls (scout report D5).
- **The benchmark's format checker is replaced.** Upstream, a server in the agent's container checks
  a submission's format by running the real grader on the answers, which is why the answers sit in
  that container (report §5.1). Here the agent image holds a script that compares a submission with
  the sample submission only: the same columns, the same ids, the same number of rows, no empty
  value. The instruction names it. It is weaker than upstream's: a submission it accepts can still
  be invalid for the grader. The readout counts such attempts. **The sample it reads is always a
  public copy.** For the Russian text-normalization competition the benchmark's configuration names
  a sample submission in the private directory and the public copy is inside an archive (scout report
  B); the wrapper takes the public one, and a test holds that it copies nothing from a private
  directory into an agent image.
- **Two checks, as in ladder D1.** By construction: the build context of the agent image is
  assembled from the public directory alone, and a test holds that with the fixture. On the built
  image: its file system is exported from a container that was never started and searched, on the
  host, for every file of the private directory and of the grader by SHA-256, for the leaderboard
  snapshot, and for lines that occur in a private file and in no public file. A hit drops the
  competition. The ladder kit's image check is written for a package's `solution/` and `tests/`
  directories and its line matching does not fit an answers file (scout report I4), so this check is
  new code.
- **On the host:** the prepared data, the answers and the images stay outside the repository; the kit
  holds names, digests and image ids. The reference agent's copy of the answers exists only in the
  package used for the answers leg, never in the package an attempt runs.
- **Cost if wrong.** An answers file in reach of the agent makes every medal on that competition
  worthless, and it would not show in the scores.

### M4. How a competition becomes a task of the launcher (coordinator)

**A second small kit wraps the reviewed launcher. Nothing under `experiments/long_horizon_tasks/`
changes, so the ladder's configuration and manifest do not move.**

- **Why not extend the launcher.** The ladder's manifest covers every file of its kit, the launcher
  included. A change to `ladder.py` makes a new configuration label for the ladder, which its plan
  allows after the freeze only to repair a fault (ladder D7), and before the freeze would put a
  twice-reviewed file back into review ahead of its first paid run.
- **What the launcher already takes as data.** Almost every limit is a field of the criterion: the
  competitions and their caps, the ceiling and the number of starts, the concurrency, the CPU set,
  the load gate, the number of rounds, the allowlist, the content of the extra compose file that
  sets container limits, the stops and their thresholds, the scan terms. This family's criteria
  change those fields and copy every other group unchanged: the classification of endings, the
  credential route, the refusal form, the usage-limit and paid-usage rules, the settlement, the
  allowance guard, the price rule.
- **What is bound in the launcher's code** (scout report I1 to I7), and what the wrapper does about
  each. The wrapper, `experiments/mle_bench_tasks/screen.py`, loads `ladder.py` by its path as a
  private module and replaces a closed list of that module's names before calling it:

| Name in `ladder.py` | The ladder's value | This family's value |
| --- | --- | --- |
| `KIT` | The reviewed kit's directory | The tranche's directory: its own `ladder.json`, `tasks.json` and `manifest.json`, and links to the four reviewed files the launcher addresses through this name (`harbor_patient.py`, `relay-compose.yaml`, `token_scan.py`, `passthrough.py`) |
| `PLAN` | The ladder plan | This plan, so the label, the reads and the rulings are read from this ledger |
| `EFFORTS` | `low`, `medium`, `high` | The screen: `medium` alone. The placement: unchanged |
| `PACKAGES` | The Terminal-Bench package directory's name | This family's |
| `Ctx` | State under `~/.local/state/lh-ladder` | A subclass whose state root is `~/.local/state/mle-bench/<tranche>` |
| `manifest` | The ladder's manifest module | The same file loaded again, pointed at the tranche's directory, and covering by hash every reviewed file this family runs |

- **What stays exactly as reviewed:** the model check, the fake token's form, the money lock with
  its reservation and settlement, the classification, the allowance guard, the usage-limit and
  paid-usage handling, the token scan and the runtime check, the teardown, the reconcile, the
  passthrough and the relay. The wrapper replaces no function; the one class it replaces, `Ctx`,
  differs only in the state root. Two key names in `tasks.json` keep the
  ladder's spelling (`digest_4_1_0` holds the digest of the package the wrapper built); the file says
  so.
- **How a package satisfies the launcher's task check.** The wrapper writes a Harbor task package
  per competition: `task.toml` (the agent's time limit, CPUs and memory, the artifact, the two images
  by their local names, and a canary line of this family, which the launcher requires and scans
  for), the instruction (the benchmark's instructions adapted to M3, then the competition's original
  description) and nothing else. The images are referenced as local images, the form the ladder's
  labelled variant already uses (scout report I1), with their image ids in `tasks.json`. Identity is
  "every file of the package equals the digest recorded at qualification", with the two network keys
  exempt as in ladder D1.
- **The verifier's output.** It writes the reward (1 or 0), the four graded outcomes as further
  numbers, and a five-line test report (valid, above median, bronze, silver, gold). The launcher
  already exports the count of passed tests as its graded outcome, so the medal step reaches the
  export with no change; the score and the percentile are read by this family's readout from each
  attempt's kept result file.
- **What the wrapper cannot give, and what the plan does instead.**
  1. *No "one attempt on the GPU at a time" beside other attempts.* A slot has no resource class
     (scout report I3, I7). So a tranche holds competitions of one class, and a GPU tranche runs one
     attempt at a time (M5).
  2. *No ceiling per calendar day* (scout report I6). So no tranche's ceiling is above USD 200, and
     two tranches never start attempts on the same calendar day (M9).
  3. *No per-task compose file and no mount.* The launcher passes two fixed compose files and no
     mount setting. The GPU device and the shared-memory size therefore go into the tranche's limits
     file, which is criterion data: a device entry in an extra compose file reached a task's
     container under Harbor 0.25.0 and rootless Podman, where the task field for a GPU is refused
     (run: scout report D5). The public data goes into the agent image, not into a mount.
- **What must be reviewed again, by a reviewer who wrote none of it:** the wrapper's list of replaced
  names, with a test that no use of a replaced name is bound when the module is loaded; the
  criterion generator, with a test that every group it does not replace equals the ladder's; the
  task wrapper, the verifier and the two withholding checks; this family's readout. Not reviewed
  again: `ladder.py`, `passthrough.py`, `token_scan.py`, `slot_record.py` and the relay, whose bytes
  are bound by hash in each tranche's manifest.
- **Cost if wrong.** A replaced name that the launcher read before the replacement would make a guard
  read the ladder's data, for example the ladder's ceiling. The guard tests of Task 5 run the
  launcher's refusals through the wrapper to catch that, and the rehearsal runs the whole path. If
  the replacement proves unsound in review, the fallback is to extend the launcher after the ladder
  has finished, which delays this line by the ladder's weeks.

### M5. Time limit, parallelism and machine share (coordinator)

- **Time limit: 24 hours per attempt, with a read after the first sessions.** Decision 17 allows it,
  the roadmap names it, and it is the regime in which published work shows the largest effect of
  workflow structure (report §9.3). The harness takes 86,400 seconds as a plain task field (a task
  with it loaded and ran; the limit was not waited out) and the launcher adds no bound of its own
  (scout report D5, I5). A direct session is expected to end by
  itself after one to four hours (report §9.1, an estimate), so the limit should rarely bind.
  **If the smoke's or the pilot's session of a tranche runs longer than eight hours, the tranche
  waits and the coordinator reports to the owner before round 1,** because the kit's timings are
  sized for eight hours (scout report I5) and thirty GPU attempts at 24 hours are thirty days. A
  shorter limit is then a new configuration label, never a change in place.
- **The alternative, eight hours from the start,** would triple the worst-case throughput and
  shorten the exposure to usage limits (M8). It was not chosen because it would cap the staged arm of
  a later comparison, which must run under the same limit, and so would force a second calibration.
- **Parallelism.** The screen's first tranche runs the three CPU-only competitions at up to three
  attempts at once (one for its smoke, one for its pilot). The second runs the ten GPU competitions
  one attempt at a time. The roadmap's "about four at once, one of them on the GPU" is not reachable
  without a change to the reviewed launcher (M4); what is lost is the overlap of nine short attempts,
  under a day at the report's estimate.
- **Per attempt** (report §9.2, estimates): a CPU-class attempt gets 6 CPUs, 16 GB of memory and 4 GB
  of shared memory; a GPU-class attempt gets 8 CPUs, 32 GB, 8 GB of shared memory and the whole RTX
  3090. The process limit stays 4,096. These are fields of each package and of the tranche's limits
  file, equal for every attempt of a competition, and a later comparison uses the same.
- **CPU set and load:** the ladder's set, CPUs 8 to 31, and its load gate (both load averages at or
  below 24), unchanged.
- **This line and the ladder are never in flight together.** Three reasons: the token must be in one
  host process, and each tranche has its own passthrough; each launcher's allowance guard counts only
  its own usage since the owner's reading, so two at once would overdraw the owner's share; and both
  use the same CPU set and load gate. A tranche of this line starts only when the ladder's launcher
  has nothing in flight and its passthrough is stopped, and the other way round. The ladder has first
  call on the owner's allowance (it is approved, and its effort verdict informs this line); the split
  is owner action 7. Every hand-over is a ledger row.
- **Cost if wrong.** If direct sessions use most of 24 hours, the GPU tranche takes weeks and the
  eight-hour read stops it after at most two sessions. If CPU-class competitions needed a GPU for a
  medal after all, they land at the floor for a reason of ours; the report's class is an estimate.

### M6. Network policy and pretrained weights (owner; recommendation: weights in the image)

- **The agent phase runs on the ladder's allowlist, unchanged:** the relay by name, the package
  indexes and the distribution mirrors (ladder D3). No model hub, no code host, no Kaggle host.
- **Pretrained weights are the open question** (report §5.2, §12). Medal-level scores on the image
  and text competitions depend on them.

| Option | Reproducibility | Contamination | Cost |
| --- | --- | --- | --- |
| A. A model hub on the allowlist | The hub's content changes; an attempt next month may fetch something else | A hub also serves datasets and other users' checkpoints, some trained on competition data; the dog-breed test images come from a public labelled set (report §5.2). The egress log names only refused connections, so what an attempt fetched from an allowed host is visible only where the transcript prints it | No image work; several more hosts on the list, since hubs serve files from other names |
| **B. A fixed set of weights in the agent image** | Fixed by SHA-256 in the criterion | Nothing is reachable that the image does not hold | A few GB of disk (report §5.2); engineering in Task 11; the list bounds what an attempt can build |

- **Recommendation: B.** It keeps the one network policy for both families, and it is the only
  option under which the readout can say what an attempt had. The list is general-purpose image and
  text encoders, the same for every competition, chosen before the screen and named in the
  instruction; it is fixed in Task 11 and recorded in the ledger.
- **What B costs if wrong.** Rates are lower than under the benchmark's usual policy and are not
  comparable with it. A competition whose medal needs a model outside the list sits at the floor for
  a reason of ours. The readout counts refused connections per attempt, which shows an agent that
  reached for a hub.
- **The three CPU-only competitions do not depend on this decision.**

### M7. Contamination (coordinator)

- **The fact.** The competitions ran from 2012 to 2024 and their winning write-ups and notebooks are
  public; all of it predates the model's training cutoff (report §6.4). This is the opposite of the
  Terminal-Bench tasks.
- **What the family can show:** how often this configuration earns a medal, recall included. For a
  later comparison of two workflows on the same model, recall is the same on both sides.
- **What it cannot show:** that a medal reflects machine-learning work from scratch; that a rate
  carries to a competition the model has not seen.
- **What the readout flags.** A transcript that holds one of the frozen terms: this family's canary,
  the benchmark repository's path, and the terms a dry run on the qualification jobs shows to be free
  of false hits (a competition's own description may name its Kaggle page, so page addresses are
  tested before they are frozen). A hit on an observation excludes it, as in ladder D6. Per attempt,
  the refused connections and their count.
- **What cannot be detected:** a submission that reproduces a public solution from memory. The
  benchmark's own plagiarism check needs the public notebooks and its rule-breaking check calls a
  model outside this project's rules (report §6.4); neither is used.
- **The original description is used,** not the benchmark's obfuscated one: the published rates that
  ranked the candidates used the original. The cost is more recall.

### M8. Usage limits (coordinator; the inputs are the owner's)

The ladder's rules apply unchanged, because the passthrough and the launcher are unchanged (ladder
D4, D5).

- **How a tranche pauses.** When the passthrough sees the vendor's usage-limit answer, the launcher
  closes all starts and reopens them by itself five minutes after the reset the answer names, with
  one start first. The allowance guard is there so that this rarely happens: it starts an attempt
  only inside the owner's hours, only with a meter reading for the window, and only while the
  tranche's usage since that reading fits what is left above the owner's share.
- **How an attempt cut by a limit is counted.** It is a cut: never an observation, its reward never
  read, its tokens counted against the ceiling, and its slot run again as a new counted start. Each
  tranche therefore has a few more starts than slots (M9); a cut beyond them drops the last slot of
  the schedule's fixed order.
- **What a 24-hour attempt changes.**
  1. *Exposure.* An attempt of 24 hours spans at least four five-hour windows, and one limit anywhere
     in them loses the whole attempt (scout report I5). A long session is more exposed than a short
     one, so many cuts would lean the observations toward short sessions; the readout lists cuts,
     and cuts above the ladder's threshold pause the tranche.
  2. *The guard decides at the start only.* A running attempt is not stopped when a window closes or
     a meter resets. Its further usage is bounded by its cap, USD 8, so at most USD 8 for each attempt
     in flight can land in a window the guard did not budget.
  3. *The closing margin.* The launcher starts nothing in the last part of a window, as long as the
     longest pilot session. With long sessions that margin can exceed a daily window (scout report
     I5), and then nothing starts. For this line the owner's hours are therefore asked as whole days
     (owner action 7), and the owner's account is not free of this line during those days.
- **Paid extra usage** stops the tranche through the passthrough's header rule, as in the ladder.
  The owner's confirmation that it is off is dated again before each tranche.
- **Cost if wrong.** If the guard fails, the owner's sessions and the coordinating session stop until
  the window resets, up to seven days for the weekly one (ladder D4). A 24-hour attempt lost to a
  limit also loses up to a day of the GPU.

### M9. Caps, ceilings and stop rules (owner: the ceilings; coordinator: the rest)

Every figure is a priced-token figure. The estimates come from report §9.1 and §10 (a direct session
that stops by itself: USD 1 to 8, central about USD 3) and are not measured.

| Tranche | Competitions | Effort | Slots | Starts at most | Cap per attempt | Ceiling | Attempts at once |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Screen, CPU | The 3 CPU-class | `medium` | 9 | 11 | USD 8 | USD 60 | 1, 1, then 3 |
| Screen, GPU | The 10 GPU-class | `medium` | 30 | 34 | USD 8 | USD 140 | 1 |
| Placement, each | At most 3 survivors of one class | `low`, `medium`, `high` | At most 45 | At most 50 | USD 8 | USD 200 | As its class |

- **The screen: 39 slots, at most 45 starts, USD 200.** The cap is the top of the report's range for
  a session that stops by itself. Before each start the launcher reserves the cap plus USD 1, so a
  tranche completes only if its attempts average under about USD 6 (CPU) or USD 4.50 (GPU). **If the
  smoke and the pilot of a tranche average above that figure, the coordinator reports before round
  1;** no cap or ceiling changes without a new label and a ledger row.
- **The placement: at most six competitions, 90 slots, 100 starts and USD 400,** in at most two
  tranches. If more than six survive, the owner chooses which are placed. The placement starts only
  after the screen's result is reported to the owner (roadmap step 12).
- **The line in all: at most 129 slots, 145 starts and USD 600.** The ladder's live probe is counted
  into each tranche's total by the launcher, a conservative double count of at most USD 0.45.
- **Effort for the screen: `medium`.** The placement pools three efforts, and the middle one is the
  best single guide to that pooled rate whichever way success moves with effort, which the ladder has
  not yet measured. It is also the cheaper choice (report §6.3).
- **The day.** No tranche's ceiling is above USD 200. A tranche makes its first start only after the
  previous tranche has nothing in flight (M5), and on a later calendar day than the one on which
  that tranche's last attempt settled. So no calendar day can pass USD 200 for this family, with no
  new guard.
- **Each tranche's order,** as the launcher runs it: a smoke (one attempt, then a person's read
  against the ladder's smoke checks), a pilot (one attempt at the screen, the owner reading the
  meters before and after), then the rounds, with a read after round 1. The CPU tranche's smoke is
  `leaf-classification`; the GPU tranche's is `us-patent-phrase-to-phrase-matching`, the smallest
  that needs the weights and the GPU.
- **A tranche stops** at any stop of ladder D7.7, which the criterion copies: a failed smoke, another
  model in a response, another CLI version or tool list, a passthrough refusal for model, tool, path
  or token, a vendor 401, a sign of paid extra usage, a match of the token scan, three usage-limit
  answers in a row, contaminated attempts on three competitions, under 20 GB of free disk. The
  share-of-starts thresholds are judged from fewer starts than the ladder's twenty, because the
  tranches are small: infrastructure failures above 10 percent from 5 starts (CPU) or 10 (GPU), and
  the ladder's pause for cuts from the same counts.
- **The line stops for a competition** when the screen puts it at the floor or above the band (M1).
  **The line stops altogether** when a tranche ends in a stop that the coordinator does not lift, when
  the eight-hour read or the cost read goes to the owner and the owner ends it, or when no
  competition survives the screen.
- **Nothing is topped up.** No slot is refilled, no threshold moved and no ceiling raised after a
  tranche's first attempt. More attempts, another effort, another competition or another definition
  of success is a new request.
- **Cost if wrong.** A ceiling too low cuts the tail of a tranche's fixed order, and with three
  attempts per competition one lost attempt leaves a competition "not screened". A cap too low ends
  long sessions as flagged observations; the verifier still grades whatever submission exists.

### M10. The Kaggle token (owner places it; coordinator rules the handling)

- **The owner creates and places it,** by the steps of owner action 1, in a terminal outside tmux
  and outside any agent session. It is a file of mode 600 in a directory of mode 700 that lies
  outside every repository and outside anything synced or backed up.
- **It is the legacy credential,** a `kaggle.json` holding the account name and a key: the client
  version the benchmark pins reads nothing else (scout report C).
- **Only the download command reads it,** on the host: `fetch.sh` of this kit, which is given the
  directory's path (`KAGGLE_CONFIG_DIR`) and never the value. It always sets that variable, because
  the client otherwise creates a configuration directory in the home directory, and it runs with no
  terminal input, because the benchmark asks a question on standard input when rules are not
  accepted (scout report C). Its own output is one fixed line per competition (done, rules not
  accepted or download failed, no room); the download tool's raw output goes to a file inside the
  token's directory, never to a pane. The download request itself carries the account name to
  Kaggle, as any download must.
- **Where it never is:** in a container or an image (the build contexts are assembled from the
  prepared data alone); in a committed file; in a log outside its own directory; in an agent's
  output. No agent, test or subagent reads the directory. The file holds the account name beside the
  key, and **the account name is private:** it appears in no committed file, no ledger row and no
  report. The ledger records the path, the time and "placed", as it does for the subscription token.
- **A check before the first image is built:** the prepared data, this kit's cache and the worktree
  are scanned for the key and the account name by a salted fingerprint, with the reviewed token
  scanner if it can take a second secret's fingerprint unchanged, and otherwise with a few lines of
  this kit (not verified while planning).
- **After the last competition is prepared** the owner deletes the file and expires the token on
  Kaggle's settings page, if that page offers it (not verified).
- **Cost if wrong.** A leaked key lets someone download and submit as the owner on Kaggle until it is
  expired; it reaches nothing of the subscription.

## Owner actions and questions

The list is written to be put to the owner as it stands. Each item says why it is needed, what to
do, and what it blocks. Nothing here blocks Tasks 1 to 9.

1. **A Kaggle account and an API token.** *Why:* the benchmark downloads each competition's data
   through Kaggle's API under the user's own account (report §4). *What to do:*
   1. Use or create a personal Kaggle account, and verify a phone number if the site asks (report
      §4: accounts without one are reported to be unable to accept rules).
   2. On Kaggle's account settings page, create an API credential of the older kind, the one that
      saves a file `kaggle.json` with a user name and a key. The benchmark's pinned client cannot
      read Kaggle's newer single-string access tokens (scout report C; the page itself was not read).
   3. In a fresh terminal window, not a tmux pane and not an agent session:
      `umask 077; mkdir -m 700 "$HOME/.local/state/mle-secret"`, then
      `install -m 600 "$HOME/Downloads/kaggle.json" "$HOME/.local/state/mle-secret/kaggle.json"`,
      then `shred -u "$HOME/Downloads/kaggle.json"`.
   4. Tell the coordinator only "placed" and the time. Never paste the file's content or the account
      name into a chat or an agent session. If `$HOME/.local/state` is synced or backed up, name
      another directory instead.

   *Blocks:* Tasks 10 and 12 (every real competition).
2. **Accept each competition's rules, in a browser.** *Why:* a download fails for a competition whose
   rules the account has not accepted, and it can only be done by hand (report §4). *What to do:*
   open each rules page below, join the competition ("Late Submission" where offered) and accept.
   The first three are enough to start. Report any that cannot be accepted: two other competitions of
   the benchmark are known to be closed, and more may have closed since (report §4, §14).
   - First, the CPU-only three:
     <https://www.kaggle.com/competitions/leaf-classification/rules>,
     <https://www.kaggle.com/competitions/text-normalization-challenge-russian-language/rules>,
     <https://www.kaggle.com/competitions/mlsp-2013-birds/rules>.
   - Then the ten on the GPU, by the same address form with these slugs:
     `us-patent-phrase-to-phrase-matching`, `tweet-sentiment-extraction`,
     `learning-agency-lab-automated-essay-scoring-2`, `chaii-hindi-and-tamil-question-answering`,
     `jigsaw-toxic-comment-classification-challenge`, `lmsys-chatbot-arena`,
     `whale-categorization-playground`, `petfinder-pawpularity-score`, `kuzushiji-recognition`,
     `cassava-leaf-disease-classification`.

   *Blocks:* the preparation of each competition not yet accepted.
3. **Read the rules for this use, and say whether it is acceptable.** *Why:* no rules page and no
   terms page could be read while planning (report §4, §14), so the plan cannot say what they allow.
   *What to check:* that the data may be used for research on this machine by an automated agent,
   and that nothing is redistributed (the plan keeps all data, answers and images out of the
   repository). *Blocks:* the preparation of any competition whose rules the owner has not cleared.
4. **Run the download, or allow the coordinator to start it.** *Why:* it is the one command that
   reads the Kaggle token (M10). *What to do,* once Task 10's script exists, in the same kind of
   terminal: `KAGGLE_CONFIG_DIR="$HOME/.local/state/mle-secret" experiments/mle_bench_tasks/fetch.sh
   <slugs>`. It prints one line per competition. *Blocks:* Tasks 10 and 12.
5. **Disk for the GPU tranche.** *Why:* `/home`, where Podman keeps its images and where the caches
   are, has 62 GB free and is 97 percent full; the report estimates 65 to 110 GB for a slim image,
   the data and four scratch areas, and asks for about 60 GB free (report §9.2, §12; estimates, and
   the ladder's 23.86 GB of pinned images come out of the same space). *What to do:* free space on
   `/home`, or name another disk for Podman's image store and this kit's cache. The CPU tranche is
   small enough to fit today (0.64 GB of data and one image without a deep-learning stack; not
   measured). *Blocks:* Tasks 11 and 12 and the GPU tranche.
6. **Decide the pretrained-weights policy** (M6). *Why:* it changes what is measured and cannot be
   changed after a tranche's first attempt. *Recommendation:* a fixed set of weights in the agent
   image, and no model hub on the allowlist. *Blocks:* Task 11 and the GPU tranche; not the CPU
   tranche.
7. **The allowance for this line.** *Why:* it draws on the same subscription as the owner's sessions,
   the coordinating session and the ladder (M8). *What to answer:*
   - How is the weekly allowance split between the ladder and this line? The plan assumes the ladder
     goes first and this line takes windows the ladder does not use.
   - On which whole days may this line start attempts? A session may run up to 24 hours and is not
     stopped when a day ends.
   - What share of the weekly and of the five-hour allowance stays free for the owner (the ladder's
     two numbers, or others for this line)?
   - Will the owner read the meters before each window and before and after each tranche's pilot, as
     for the ladder? With no reading nothing starts.
   - May the GPU be reserved for the GPU tranche: three to four days if sessions stop by themselves,
     up to thirty if they use the limit (report §10; estimates)? The owner's own GPU work would have
     to wait.

   *Blocks:* each tranche's smoke.
8. **The two standing confirmations, dated again for this line.** *Why:* the ladder plan requires
   them before any use of the subscription, and this line adds sessions of up to 24 hours. *What to
   confirm:* that paid extra usage is off for the account, and that the subscription's terms allow
   unattended runs of this size. *Blocks:* each tranche's freeze.
9. **Approve the line and its ceilings.** *Why:* the GPU tranche and the placement are above the
   USD 100 the coordinator may approve alone, and the line passes USD 300 in all (`AGENTS.md`,
   "Budget delegation"). *What is asked:* the [rule proposed below](#proposed-wording-for-the-agentsmd-rule):
   the screen at 39 slots, at most 45 starts and USD 200; the placement at up to six competitions,
   90 slots, 100 starts and USD 400, starting only after the screen is reported; USD 8 an attempt;
   success as any medal (M1). *Blocks:* every paid attempt.
10. **Later, only if too few competitions are placed:** whether to end the line, or to request
    another definition of success (M1). Nothing is asked now.

**Done, and no longer an owner action: the GPU toolkit.** The owner installed the NVIDIA Container
Toolkit 1.20.2 on 2026-11-15, and rootless Podman 4.9.3 passes the GPU to a container (the
coordinator ran `podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable … nvidia-smi`,
which prints the RTX 3090). **Operating note.** The toolkit's generated device file uses
`cdiVersion: 0.7.0` with a field `additionalGids` that Podman 4.9.3 cannot parse. `/etc/cdi/nvidia.yaml`
is therefore a copy with those blocks removed and `cdiVersion: 0.6.0`: generated as a normal user
with `nvidia-ctk cdi generate --output=<file>`, stripped, and installed by the owner with
`sudo install -m 644`. **After an NVIDIA driver update the copy must be rebuilt the same way,** which
is a root step for the owner then. Task 11 begins with that one-line container check.

## Tasks

Branch `feat/mle-bench-kit` from `main`, in its own worktree. The kit is
`experiments/mle_bench_tasks/`; its tests are `tests/experiments/test_mle_bench_*.py`, each written
first and failing first for its stated reason. Every command has the blocking provider stubs first
on `PATH`. No test reads Kaggle data, the Kaggle token or the subscription token. Tests assert
behaviour, codes and values, never prompt text. Hours are planner's estimates unless a report section
is named; machine time is beside them.

**The fixture** used by Tasks 1 to 9 is a synthetic miniature competition, generated by a seeded
script and committed under `tests/experiments/fixtures/mle_bench/tiny-tabular/` (a few kilobytes): a
public training table, a public test table without labels, a sample submission, the held-out
answers, a leaderboard snapshot of twenty rows and a ten-line grading function. It has the shape of
a prepared competition, so the wrapper, the verifier path and the withholding checks are tested
without Kaggle.

### Can start now (no owner action)

**Task 1: the fixture and the task wrapper** (impl_code; 8 h; report §13 gives 6 to 8 for the
wrapping).
*Files:* create `family.json` (the thirteen candidates: slug, class, resources, the benchmark's
commit, each size with its source), `wrap.py`, the fixture and its generator,
`tests/experiments/test_mle_bench_wrap.py`. *Produces:* from a prepared competition directory, the
agent image's build context, the verifier image's build context, the attempt package, and the two
packages for the answers and sample-submission legs. *Tests first:* the agent context holds no file
of the private directory, of the grader or of the leaderboard snapshot, by SHA-256; the attempt
package holds `task.toml` and the instruction only; `task.toml` carries the class's limits, the time
limit, the artifact, both images, the canary line and no network key; the answers package differs
from the attempt package only by its `solution/` directory; the same input gives the same digests.
*Verify:* `pytest -q -n 4 tests/experiments/test_mle_bench_wrap.py`, and `--collect-only` on it.

**Task 2: the verifier path and the format check** (impl_code; 5 h; report §13 gives 2 for the
format check and 1 for host grading).
*Files:* create `verifier/test.sh`, `verifier/grade_submission.py`, `agent/validate_submission.py`,
`tests/experiments/test_mle_bench_verifier.py`. *Produces:* the reward file (1 or 0 and the four
graded outcomes), the five-line test report, and the agent-side format check of M3. The call into the
benchmark's grader is one function, so the suite tests everything around it with the fixture's
grader. *Tests first:* the answers give reward 1 and five tests passed; the sample submission gives
reward 0 and a valid submission; a missing, empty or malformed submission gives reward 0, not valid,
and still a written reward; a score the grader does not give is left out, never written as zero; the
percentile follows the metric's direction; the format check accepts the sample and refuses a missing
column, a missing id and an empty value, without reading any answer. *Verify:* the module, and
`--collect-only`.

**Task 3: the withholding check on a built image** (impl_code; 4 h).
*Files:* create `withhold_check.py`, `tests/experiments/test_mle_bench_withhold.py`. *Produces:* for
an exported file system, a result per image: private files, grader files and the leaderboard snapshot
by SHA-256, private-only lines by count, and the benchmark's package. *Tests first,* on directory
trees standing in for an export: a planted answers file is found by hash under another name; a file
holding a share of the answers' lines is found; a public file that shares lines with the training
data is not a hit; an unreadable path fails the check. *Verify:* the module, and `--collect-only`.

**Task 4: the configuration as data** (impl_code; 5 h).
*Files:* create `make_criterion.py`, `tranches/screen-cpu/` and `tranches/screen-gpu/` (each a
`ladder.json`, a `tasks.json` and a `manifest.json`, generated, plus the four links of M4),
`tests/experiments/test_mle_bench_criterion.py`. *Produces:* each tranche's criterion from the
ladder's `ladder.json` and a short file of this family's fields. *Tests first:* every group the
generator does not replace equals the ladder's, byte for byte as JSON; the model is `claude-haiku-5-5`
and the efforts are within the ladder's three; the caps, ceilings, starts and concurrency are M9's;
the screen's two ceilings sum to USD 200 and no ceiling is above USD 200; the GPU tranche's limits
file names the device and its concurrency is 1; every null has a pending entry; the manifest covers
the reviewed files by hash. *Waits on nothing;* the fields the ladder's live probe fills stay pending
here until it has run. *Verify:* the module, `--collect-only`, and
`git diff --stat main -- experiments/long_horizon_tasks` prints nothing.

**Task 5: the wrapper around the launcher, and its guard tests** (impl_code; 9 h).
*Files:* create `screen.py`, `tests/experiments/test_mle_bench_screen.py`. *Produces:* `screen.py
<tranche> plan | launch | status | ruling | resume | allowance`, the launcher's commands under M4's
replaced names. *Tests first,* against the ladder's stand-in harness and stand-in Podman on a closed
`PATH`, with the fixture as the only competition: a launch through the wrapper reads this tranche's
criterion, this plan's ledger and this tranche's state root, and never the ladder's (each shown by a
value that differs between the two); no use of a replaced name is bound when the launcher is loaded;
the refusals of the ladder plan's Task 5 hold through the wrapper (no authorization, a label that is
not this ledger's, a dirty or changed kit, another model, a package whose digest or image differs, a
credential variable in the environment, a rehearsal with a spend variable, no allowance inputs); the
ceiling and the starts cap of the tranche hold under sixty concurrent launches; a usage limit cuts,
pauses and reruns; the schedule is one effort, three rounds, the smoke and the pilot first; a
tranche name outside the kit's list is refused. *Not verified while planning:* whether the ladder's
own launcher tests can run against the wrapped module without edits; if they can, they are run as
they are and the list above shrinks to what is new. *Verify:* the module, `--collect-only`, then the
ladder's five test modules unchanged, then the sampled broad check.

**Task 6: the readout** (impl_code; 5 h).
*Files:* create `screen_readout.py`, `tests/experiments/test_mle_bench_readout.py`. *Produces:* from
the launcher's export (read through the reviewed `slot_record.py`) and each attempt's kept result
file, per competition: observations, medals, the three scores against the thresholds, percentile,
valid and above-median counts, the screen class of M1, cost and minutes, cuts, flags, refused
connections; and at the placement, the ladder's pooled label. *Tests first:* each row of M1's table;
a competition with two observations is "not screened"; an excluded attempt is listed and never
scored zero; the screen's attempts are never pooled into a placement count; a stop readout places
nothing. *Verify:* the module, and `--collect-only`.

**Task 7: the fixture on containers** (impl_code; 4 h and under an hour of machine time; report §13
gives 3 to 4; no spend, no model call).
*Files:* create `qualify.sh`; `README.md` of the kit begins here. *Produces:* the fixture's two images
built with rootless Podman, and the three legs of M2 run twice through Harbor 0.25.0 under the
allowlist. This is where the benchmark's grader first runs inside a verifier's container, with the
pinned dependency set of M3 (so far it has run on the host only). *Checks:* the six outcomes of M2;
the untouched leg gets a written reward of 0; a local image name is accepted without a pull; the
withholding check of Task 3 passes on the real agent image and finds a planted answers file; the
verifier's container has no relay. The keys of the reward file are then held to what this run
recorded. *Verify:* `qualify.sh` prints six lines, all as listed; the results go in the ledger.

**Task 8: the independent review** (review_code; 6 h, and 5 h of fixes and re-review).
By a reviewer who wrote none of Tasks 1 to 7. *In scope:* M4's list of replaced names and whether
any guard of the launcher reads the ladder's data through the wrapper; the criterion generator and
each replaced field; withholding, by construction and on the image; the verifier; the readout's
classes. *The brief lists the holes to look for:* an answers file, a grader or a threshold in reach
of the agent; a ceiling or a cap read from the ladder's criterion; two tranches sharing a state root
or a money lock; a tranche whose efforts or model differ from its ledger row; a missing submission
scored as an infrastructure failure, or an infrastructure failure scored as zero; the Kaggle key or
the account name in a file the kit writes. Each guard is mutated.

**Task 9: the zero-spend rehearsal** (impl_code; 6 h; no spend, no request to the vendor).
On containers, with the fixture, the real pinned CLI, the relay, and the passthrough in its rehearsal
mode against the ladder's stand-in API, as the ladder's Task 7: a session that ends normally with a
submission and is graded; one that ends at the dollar cap; one past a shortened time limit; one cut
by the stand-in's usage limit, with its slot run again; one killed and reconciled; the token
scanner's canary test. It also measures how long the launcher's export of the agent's file system
takes, which the launcher bounds at 300 seconds for the smoke and the pilot (scout report I5).
*Verify:* the ladder's smoke checks on the rehearsal's records; results in the ledger.

### Waits for the Kaggle token and the rules (owner actions 1 to 4)

**Task 10: the three CPU-only competitions** (impl_code; 6 h; report §13 gives 2 to 3 for the first
installation and preparation and 1 to 2 for each further competition).
*Files:* create `fetch.sh`; fill `tranches/screen-cpu/tasks.json`. *Does:* the download and the
benchmark's preparation on the host, `leaf-classification` first; the secret scan of M10; the two
images per competition; the withholding check; the six runs of M2 per competition; a dry run of the
contamination terms over those jobs, after which the terms are frozen. *Tests first,* without Kaggle:
`fetch.sh` refuses without the directory variable, refuses a directory or file of another mode, gives
the download no terminal input, and prints only its fixed lines when the download tool fails noisily
or asks a question (a stand-in tool on a closed `PATH`). The Russian text-normalization competition
is prepared last of the three: its preparation loads about ten million rows and needs a few GB of
memory (scout report C, an estimate). *Verify:* `qualify.sh` on each; `tasks.json` holds digests, image ids, sizes on disk, the
withholding result and the six outcomes; the ledger gets the surviving list and the measured sizes.

### Waits for disk and the weights decision (owner actions 5 and 6); the GPU itself is ready

**Task 11: the GPU path** (impl_code; 8 h; report §13 gives 6 to 10; no spend).
*Does, in this order:* the one-line container check of the operating note above; the GPU base image,
with a deep-learning stack that fits this driver (the benchmark pins PyTorch 2.2.0, which may not;
report §14); the fixture run with the GPU tranche's limits file under the allowlist, the agent's
container seeing the card (shown on a scratch task without the allowlist: scout report D5); the
weights of M6 fetched on the host, recorded by SHA-256 and
placed in the image; the rehearsal of Task 9 once more on the GPU image, with the export time
measured on a container that has written several GB. *Verify:* the fixture's six outcomes on the GPU
image; the agent's container lists the GPU; the ledger gets the image's size and the weights list.

**Task 12: the ten GPU competitions** (impl_code; 12 h; report §13 gives 1 to 2 each).
As Task 10, in the table's order, into `tranches/screen-gpu/tasks.json`. *Waits also on* owner
actions 1 to 4 for these ten.

### Waits for the live probe of the subscription route, and for the approval (owner actions 7 to 9)

**Task 13: the CPU tranche** (about 4 h of attention; machine time not known before the pilot).
Before the first attempt the ledger holds: the Terminal-Bench live probe's result; the approval of
this line with its `AGENTS.md` rule; the qualified competitions with package digests, image ids and
withholding results; the tranche's manifest hash and runtime commit; the review verdict and the
rehearsal result; the owner's two confirmations, shares, days and first reading; the row that the
ladder has nothing in flight. Then the freeze, the smoke and its read, the pilot and its read, the
rounds, and the export.

**Task 14: the GPU tranche** (about 6 h of attention; three to four days of the GPU by report §10's
estimate). The same list, on a later calendar day than Task 13's last start.

**Task 15: the screen's report** (5 h). The readout, a report under `docs/reports/`, the priced usage
and the allowance used in the ledger, the roadmap's step table, and the placement request with
measured cost per attempt in place of this plan's estimates.

**Task 16: the placement** (about 8 h of attention and 5 h for the readout; machine time from the
screen's measurements). Its tranches are generated as in Task 4, each with its own label, smoke and
reads; then `family.json`, frozen with roadmap step 7's set.

**Hours in all:** about 57 before any owner action (Tasks 1 to 9), about 26 for the real competitions
(Tasks 10 to 12) and about 28 for the tranches and their reports: about 111. The roadmap's figure for
step 10 (about 16 hours for the first CPU-only competition, 6 to 10 for the first on the GPU, 1 to 2
for each further one) assumed the launcher would be reused as it is; the wrapper, its review and its
rehearsal are the difference.

## What this makes harder

- **A second kit that depends on the first.** A change to the reviewed launcher after this kit exists
  must be checked against the wrapper's list of replaced names, and each of this line's tranches
  binds the launcher's bytes by hash, so such a change makes new labels here too.
- **No mixed tranche.** The GPU runs one attempt at a time and CPU-class attempts never run beside
  it. If a later comparison wants four attempts at once, the launcher needs a resource class per
  slot, which is a change to reviewed code.
- **The two lines share one account, one CPU set and one passthrough at a time.** Each
  hand-over between the ladder and this line is a person's step, and the calendar time of both grows.
- **The family is tied to its configuration:** the CLI version and its three tools, the allowlist,
  the weights list, the resource classes, the 24-hour limit and the USD 8 cap. A later comparison
  reuses all of them or qualifies again.
- **The owner is in the loop,** as for the ladder: a reading before every window, and here on whole
  days.
- **Images are built here,** not pulled by a publisher's digest. A rebuilt image is a new image id and
  so a new label; the prepared data and the answers must be kept, or prepared again, to rebuild one.

## Not verified while planning

**Settled by the fixture on containers (Task 7):** that Harbor 0.25.0 with podman-compose 1.6.0 runs
a locally built agent image and a locally built verifier image by name without a pull (the scratch
task of scout report D5 built its verifier image at each trial); that the benchmark's grader runs in
a verifier's container with the pinned dependency set; that the reference agent can write the answers
as the submission; the reward file's keys; whether a competition can be added to the benchmark's
registry for the fixture, or the fixture needs its own grader call.

**Settled by the rehearsal (Tasks 9 and 11):** that the launcher's 300-second export fits an agent
container with a deep-learning stack and several GB written (if not, the smoke stops as an incomplete
scan; lengthening that one timing through the wrapper is then a reviewed change, and it weakens no
guard); that the process limit of 4,096 is enough for data loaders; how the CLI's Bash tool, which
refuses a standalone `sleep` (ladder D2), lets a session wait on training that runs for hours.

**Settled by the GPU path (Task 11):** that the device entry, the allowlist network mode and the
CLI's install work together in one attempt (each was run without the others: scout report D5); which
PyTorch build fits driver 580.178.04; the size of the GPU image and of the weights.

**Settled by the owner's actions or by Kaggle:** whether each of the thirteen competitions' rules can
still be accepted; what the rules and Kaggle's terms allow; whether the token page lets a token be
expired; whether the benchmark's download and preparation can be run as two steps, so that only the
first can read the token.

**Settled only by the screen:** the cost, length and medal rate of a direct session on any
competition; whether sessions end by themselves; whether the thresholds are fair on each rebuilt test
set (report §14); what an attempt costs against the allowance when most of its hours are waiting.

**From the scout report, still open when this plan was written:** the state of the older
`mlebench-lite` dataset of the harness's registry (if it holds usable task packages, Task 1's
wrapper is checked against them; this plan does not depend on it); the measured disk figures; the
hosts a model hub would add to the allowlist. The plan reads its sections A to D and I.

**Not knowable by reading:** how much of a medal is recall (M7).

## Rulings

None yet. Each ruling is recorded in this form: **what is ruled, why, and what it costs if wrong.**
The rows that the launcher reads to lift a stop (`| <date> | Ruling | resume: … |`) go in the
[ledger](#ledger), not here; this table's second column is deliberately not named "Ruling", because
the launcher reads any table row of this file whose second cell is exactly that word.

| Date | What is ruled | Why | What it costs if wrong |
| --- | --- | --- | --- |

## Proposed wording for the `AGENTS.md` rule

`AGENTS.md` is the owner's file; this is wording only, to be placed after the rule for the effort
ladder when the owner approves the line (owner action 9).

> - The owner-approved MLE-bench screen and placement (DATE; roadmap owner decision 17) are one
>   calibration line for a second long-horizon task family, limited to
>   [its plan](docs/plans/2026-11-15-mle-bench-family-plan.md): the 13 named MLE-bench competitions,
>   each wrapped so that the held-out answers, the grader and the medal thresholds stay out of the
>   agent's container, run by a direct `claude-haiku-5-5` Claude Code session of at most 24 hours.
>   The screen is three attempts each at effort `medium`, in two tranches (the three CPU-only
>   competitions, then the ten on the GPU, one at a time): at most 39 scheduled attempts and 45
>   starts, ceiling USD 200. The placement, which starts only after the screen is reported to the
>   owner, is fifteen fresh attempts (five each at `low`, `medium` and `high`) for at most six
>   surviving competitions: at most 90 scheduled attempts and 100 starts, ceiling USD 400, in tranches
>   of at most USD 200. At most USD 8 per attempt; no tranche starts on the calendar day another
>   ended, so no day passes USD 200 (priced-token figures; an attempt is one whole agent session, not
>   one API call). A tranche may start only after the Terminal-Bench live probe has shown the
>   subscription route, each of its competitions has passed the qualification check on this machine
>   (the answers file earns a gold medal through the verifier an attempt uses; the sample submission
>   and an untouched environment earn none), the launcher wrapper has passed an independent review
>   and a zero-spend rehearsal, and the plan's ledger holds the tranche's label and limits; and never
>   while the effort ladder has an attempt in flight. Success is any medal; the score and the
>   leaderboard percentile are recorded for every attempt; a competition enters the family only at 1
>   to 5 medals of fifteen. It measures per-competition success and makes no claim about any workflow.
>   No other model, no top-up after a null, and another definition of success or a workflow
>   comparison needs its own approval.

## Ledger

The launcher reads this table as committed on `main`: the second cell names the kind of row, the
third holds its content.

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-15 | Plan written | Against `3ac3a2e4` (`integ/20261115b`: `main` with the day's documentation pass and the ladder's 15-task configuration). Not reviewed. No spend authorized: this line has no rule in `AGENTS.md` and no approval row. Spend to date: 0. Evidence used: the feasibility report (a desk study) and sections A to D and I of the scout's fact-finding of the same day, which was still in progress |
| 2026-11-15 | Owner action done: GPU toolkit | NVIDIA Container Toolkit 1.20.2 installed by the owner; rootless Podman 4.9.3 passes the RTX 3090 to a container (coordinator's check). `/etc/cdi/nvidia.yaml` is a stripped copy at `cdiVersion: 0.6.0`, to be rebuilt after a driver update (the operating note under "Owner actions and questions") |
