# MLE-bench Task Family Plan (Roadmap Phase 5b, Steps 10 To 12)

**Status: Plan; written 2026-11-15; revised 2026-11-15 after an independent review (accept after
fixes: 2 blockers, 9 majors, 13 minors) and the coordinator's rulings on it; accepted by the
coordinator for Tasks 1 to 9; nothing paid is approved.** Tasks 1 to 6 are built and tested
on the fixture (see the [ledger](#ledger)); no review verdict on them was recorded, and Task 4 shows
no review at all. Task 5 is built; Task 8's review of Tasks 1 to 6 found it ready for Task 7, and its fixes are in.
Task 7 is built: on 2026-11-26 `qualify.sh` printed its ten lines, all ok, and the six fixture checks, all ok,
from real runs on containers. It also showed that Harbor's teardown and its regrade remove images named
`localhost/...`, which needs a ruling before Task 9 (ledger row of 2026-11-26). Tasks 9 to 16 are not built.
Nothing is spent. This page turns steps 10 to 12 of
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
line; each tranche also has a ledger file of its own, which the launcher reads (M4). Its commands
are for this machine and are not copyable examples. Spend is authorized only as the
[ledger](#ledger) and the tranche ledgers record. Until this plan's kit exists and has passed its
own review (Task 8), the only long-horizon kit to use is the ladder's.

**The answer first.**

- **Preparation can start today and needs no owner action for its first nine tasks:** the kit, a
  synthetic miniature competition as a test fixture, the verifier that runs the grader, the
  withholding checks, the configuration as data, the wrapper around the reviewed launcher with its
  guard tests, its independent review and a zero-spend rehearsal (about 73 hours, a planner's
  estimate). Task 10a, the download script with its tests and its review, needs no owner action
  either.
- **Real competitions wait for the owner's Kaggle account, token and rule acceptance.** The three
  CPU-only candidates come first: they need neither the GPU nor much disk.
- **No paid attempt can start before five things:** the Terminal-Bench live probe has shown that the
  vendor accepts the subscription route; each competition has passed the qualification check and
  the evaluator's controls on this machine; the wrapper has passed its review and rehearsal; the
  real packages have been reviewed and one has been rehearsed with the real CLI at no spend; and the
  owner has approved the line, because its ceilings are above what the coordinator may approve
  alone.
- **The screen is sequential:** three attempts per competition at effort `medium`, and three more
  for a competition with no medal in the first three. That is 39 to 78 attempts, capped at USD 8 an
  attempt and USD 200 in all. At the central estimate of USD 3 an attempt, USD 200 pays for the
  second three of about six competitions, and more than six are likely to need them; the others are
  then reported as not screened (M9). Every dollar figure on this page is a priced-token figure
  and an estimate until measured.
- **What the screen cannot do:** place a competition. A competition whose true rate is near 10
  percent is excluded about half the time, and one at 50 to 70 percent usually survives, so the
  placement has to catch it (M1).
- **The reviewed launcher is not changed.** A second small kit loads it, points it at this
  family's data and adds its own checks before it. The cost of that choice: no attempt on the GPU
  runs beside another attempt, each tranche has its own ledger file, and neither this line nor the
  Terminal-Bench ladder can launch while the other's launcher is running.

**Headline exit test (fails today):** `experiments/mle_bench_tasks/results/family.json` exists,
names its criteria and package digests, and lists every screened competition with its screen class
and, for each placed competition, its medals of fifteen attempts by effort with the exact interval.
After a stop no `family.json` is written.

## Words used on this page

| Word | Meaning here |
| --- | --- |
| Competition | One past Kaggle competition as MLE-bench repackages it (report §2): a description, public data, a preparation script that builds held-out answers, a grading function and a snapshot of the private leaderboard |
| Medal | A score at or past the competition's bronze threshold, computed by the benchmark's grader from the leaderboard snapshot (report §3.1). "Any medal" is the benchmark's headline measure |
| The band | 10 to 30 percent success for a direct `claude-haiku-5-5` session (owner decisions 14 and 17) |
| The ladder | The Terminal-Bench effort ladder of the ladder plan: three efforts, at most 240 starts and USD 200. Owner decision 16 names 16 tasks; the 15 that qualified run |
| The reviewed kit | `experiments/long_horizon_tasks/`: the launcher `ladder.py`, the passthrough, the relay, the token scanner, the slot record and the readout, on `main` after two independent reviews and two zero-spend rehearsals |
| Passthrough, relay | The one host process that holds the subscription token, and the credential-free container that forwards the agent's requests to it (ladder D4, route B) |
| Attempt, start, slot | One whole agent session on one competition; a start is an attempt the launcher began; a slot is a place in the schedule |
| Observation, cut, infrastructure failure, stop | The launcher's classes for how a start ended (ladder D5). Only an observation enters a count. A cut is an attempt ended by a usage limit; its slot is run again |
| Tranche | One run of the launcher under one configuration label, one state directory, one ceiling and one ledger file |
| Tranche ledger | The file `docs/plans/2026-11-15-mle-bench-ledger-<tranche>.md`: the only ledger the launcher reads for that tranche (M4) |
| Stage | The screen runs each resource class in two stages, each a tranche: stage one is three attempts per competition, stage two three more for the competitions with no medal yet (M1) |
| Configuration label | The SHA-256 of a tranche's manifest. Observations under different labels are never pooled, with one exception fixed here before spend: the screen reads a competition's stage-one and stage-two observations together (M1) |
| Criterion | A tranche's `ladder.json`: every limit and rule as data |
| Priced-token figure | Metered tokens times the frozen price rule (ladder D4). It caps and reports usage. Nothing is billed |
| Scout report | The fact-finding report of 2026-11-15, [MLE-bench as tasks of the long-horizon harness: facts found on this machine](../reports/2026-11-15-mle-bench-machine-facts.md). Cited by its section letters. Each fact cited from it was read in the installed harness's or the reviewed kit's source, or run on this machine with no model call, and the note says which. Tasks 7 and 11 establish again, on this kit, every such fact a decision rests on |

## Scope, and what this line claims

- **Step 10, preparation.** Each candidate competition becomes a task the reviewed launcher can run,
  with the private answers, the grader and the medal thresholds outside the agent's container, and
  passes a qualification check on this machine.
- **Step 11, the screen.** Thirteen candidates at one effort, three attempts each and three more
  for a competition with no medal in the first three: 39 to 78 attempts. Its only purpose is to
  exclude the competitions that are clearly at the floor or clearly above the band, and M1 states
  how often it gets that wrong.
- **Step 12, the placement.** Each competition that survives the screen gets fifteen fresh attempts
  (five at each of `low`, `medium` and `high`, the ladder's size per task) and is admitted by the
  ladder's own rule: 1 to 5 medals of fifteen.
- **What is measured:** how often a direct `claude-haiku-5-5` Claude Code session earns a medal on
  each competition, under this plan's configuration: CLI 2.1.311 signed in through the subscription
  route, the tools Bash, Edit and Read, the allowlist network policy and, if the owner decides M6 as
  recommended, a fixed set of pretrained weights. Every attempt also records its score, its
  leaderboard percentile and whether it is above the leaderboard median.
- **Not claimed:** anything about a workflow; that a competition's true rate lies in 10 to 30
  percent (six attempts cannot show it, and fifteen give an observed count whose exact 90 percent
  interval is 28 to 44 points wide and always reaches outside the band; M1); an ordering of
  competitions; any comparison with a published MLE-bench rate, which used other
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
| The token stays in one host process and enters no container | `AGENTS.md`, "Credential" | The passthrough of the reviewed kit, unchanged. One passthrough process holds the token at a time: the wrapper refuses to launch while the ladder's launcher runs or its passthrough answers, and the ladder's launcher is refused while this line's runs (M5). Stopping this line's passthrough before the ladder's is started is a person's step |
| Haiku only for this line; no Fable in any experiment call | `AGENTS.md`, "Cost default"; decision 17 names `claude-haiku-5-5` | The launcher's and the passthrough's model checks, unchanged |
| No uncalibrated quality claim | `AGENTS.md`, "No uncalibrated experiments" | The qualification check and the separate evaluator check of M2 pass before any paid attempt. The screen and the placement are themselves calibration and make no claim about a workflow |
| "Better" is Pareto dominance over quality and model-aware cost | `AGENTS.md`; [structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator) | No comparison is made here. Cost per attempt is recorded so that a later one can be |
| Decisions and limits in the ledger before the first call | `AGENTS.md`, "Record experiment decisions" | The line's decisions are in this plan's [ledger](#ledger). Each tranche's label, caps and ceiling are in its own tranche ledger before its first start; the launcher reads that file and refuses without the label row (M4) |
| A competition enters the family only at 10 to 30 percent success | Roadmap decisions 14 and 17 | The placement rule of M1, which is the ladder's own. It admits on an observed count, and M1 states how wide the interval around that count is |
| Attempts in parallel up to the benchmark's 24-hour limit; Haiku spend up to USD 200 per calendar day for this family | Roadmap decision 17 ("parallel up to 24 hours ok , haiku spend up to $200 per day ok"), a priced-token figure under decision 18 | M5 and M9. The daily figure holds by the tranche ceilings and by procedure, not by a guard: no tranche's ceiling is above USD 200, one tranche runs at a time (enforced by a lock), and a tranche starts only on a later calendar day than the previous tranche's last settlement (a person's ledger row) |
| The coordinator asks the owner for a tranche above about USD 100, cumulative spend above about USD 300, a new experiment line, or a top-up after a null | `AGENTS.md`, "Budget delegation"; roadmap decision 12 | The screen's GPU tranches and the placement are above USD 100, so the owner approves the line (owner action 9). A subagent never spends on its own authority |
| Usage limits are shared with the owner's own sessions; every tranche says how it pauses and how a cut attempt is counted | `AGENTS.md`, "Credential" | M8 |

## Candidates

The thirteen candidates are the ranked subset of report §8.2. Sizes are the benchmark README's
figures as the report read them (report §3.2, §3.3). **They are a rough guide only:** the repository
does not say what they measure, and the figure for the Russian text-normalization competition cannot
be right, since its preparation script writes 10.5 million rows (scout report C; probably a few
hundred MB, an estimate). Each competition's size on disk is measured after its download (Task 10).
"Class" is the resource class of M5; that a class needs no GPU is the report's estimate, not a
measurement. The competition's id in the benchmark is its Kaggle slug, and its rules page is
`https://www.kaggle.com/competitions/<slug>/rules`.

**Each competition has a short task name, and the launcher sees only that name.** The launcher
refuses a state directory whose longest socket path is above 107 bytes, and that path holds the
task's name; with the Kaggle slugs most tranches would be refused at launch (computed: 123 to 133
bytes). A task name is at most 12 characters, as is a tranche's name, which gives at most 97 bytes
under this machine's home directory. The slug is kept as a field of `family.json` and is what the
download and the benchmark's grader are given. This page uses the short names from here on.

| Order | Name | Kaggle slug | GB | Class | Rank in report §8.2 |
| --- | --- | --- | --- | --- | --- |
| 1 | `leaf` | `leaf-classification` | 0.036 | CPU | 7 |
| 2 | `textnorm-ru` | `text-normalization-challenge-russian-language` | 0.01 | CPU | 10 |
| 3 | `birds` | `mlsp-2013-birds` | 0.59 | CPU | 11 |
| 4 | `patent` | `us-patent-phrase-to-phrase-matching` | 0.002 | GPU | 4 |
| 5 | `tweet` | `tweet-sentiment-extraction` | 0.003 | GPU | 1 |
| 6 | `essay2` | `learning-agency-lab-automated-essay-scoring-2` | 0.036 | GPU | 3 |
| 7 | `chaii` | `chaii-hindi-and-tamil-question-answering` | 0.032 | GPU | 13 |
| 8 | `jigsaw` | `jigsaw-toxic-comment-classification-challenge` | 0.06 | GPU | 8 |
| 9 | `lmsys` | `lmsys-chatbot-arena` | 0.18 | GPU | 12 |
| 10 | `whale` | `whale-categorization-playground` | 0.73 | GPU | 6 |
| 11 | `petfinder` | `petfinder-pawpularity-score` | 1.04 | GPU | 2 |
| 12 | `kuzushiji` | `kuzushiji-recognition` | 4.51 | GPU | 9 |
| 13 | `cassava` | `cassava-leaf-disease-classification` | 6.19 | GPU | 5 |

The order is the order of preparation: the three CPU-only competitions (0.64 GB together by the
README's figures), then the GPU competitions from the smallest. The total is 13.4 GB (report
§8.2), a lower bound. The report expects 2 to 5 of the 13 to fall in the band (report §1, an
estimate). The three further CPU-only competitions that report §8.2 offers as upper anchors are not
in the screen: the roadmap stages 13.

## Decisions

The decisions are numbered M1 to M10, to keep them apart from the ladder plan's D1 to D7. Each
gives the choice, the reason, what it costs if wrong, and who decides: **owner** (the
owner's to make; the plan gives a recommendation) or **coordinator** (the coordinator can rule within
decision 17 and records the ruling under [Rulings](#rulings)). Nothing here is frozen until its
tranche's criterion is frozen and its label is in the tranche's ledger.

### M1. Success, the screen's classes and the placement (owner: the definition; coordinator: the classes)

- **Success is any medal,** as the roadmap proposes: the benchmark's headline measure, predeclared by
  someone else and published for every agent (report §7). The verifier's reward is 1 for a medal and
  0 otherwise, which is the only reward the reviewed slot record accepts.
- **Every attempt also records four graded outcomes:** the raw score; the leaderboard percentile;
  whether the submission is valid; whether it is above the leaderboard median. The benchmark's grader
  gives the other three and no percentile (scout report B), so this plan fixes it: the share of the
  snapshot's scores that the attempt's score beats or ties, in the metric's direction; an attempt
  with no score has no percentile, and it is never written as zero. The outcomes place nothing and
  enter no rule of the screen or the placement.
- **The screen is sequential, and its rule is fixed before spend.** Stage one is three attempts
  per competition. Stage two is three more attempts for each competition that has no medal after
  stage one. Only medals among observations decide.

| After | Observed | Class | What follows |
| --- | --- | --- | --- |
| Stage one | 3 medals of 3 observations | Above the band | Out |
| Stage one | At least one medal, and not 3 of 3 | Survives | Goes to the placement |
| Stage one | No medal | Undecided | Stage two, if it is funded (M9) |
| Stage two | At least one medal among its observations | Survives | Goes to the placement |
| Stage two | No medal in six observations | Excluded low | Out |
| The class's screen has ended | No medal in fewer than six observations | Not screened | Reported with its count; it neither survives nor is out, and nothing is rerun to fill it |

- **What the screen does at a given true rate.** The table takes a competition's attempts as
  independent with one medal rate, and for the last two columns takes the rate pooled over the three
  efforts of the placement to be the same. Both are simplifications; the figures were computed for
  this plan and agree with those of its independent review.

| True rate | Above (3 of 3) | Goes to stage two | Excluded low (0 of 6) | Survives | Mean attempts used | Placement admits (1 to 5 of 15) | Enters the family |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5% | 0.000 | 0.857 | 0.735 | 0.265 | 5.6 | 0.537 | 0.142 |
| 10% | 0.001 | 0.729 | 0.531 | 0.468 | 5.2 | 0.792 | 0.370 |
| 20% | 0.008 | 0.512 | 0.262 | 0.730 | 4.5 | 0.904 | 0.660 |
| 30% | 0.027 | 0.343 | 0.118 | 0.855 | 4.0 | 0.717 | 0.613 |
| 50% | 0.125 | 0.125 | 0.016 | 0.859 | 3.4 | 0.151 | 0.130 |
| 70% | 0.343 | 0.027 | 0.001 | 0.656 | 3.1 | 0.004 | 0.002 |

- **What the screen cannot do.**
  1. *It cannot place a competition.* Six attempts say nothing about 10 against 30 percent.
  2. *It drops the lower part of the band.* A competition near 10 percent is excluded low about half
     the time (0.53), against about one time in eight at 30 percent. The family will therefore lean
     to the upper part of the band, and a competition excluded low is not shown to be below it.
  3. *Three of three does not exclude a competition at 50 to 70 percent reliably.* Such a
     competition survives 86 and 66 percent of the time. The placement then has to catch it, which
     it does (it admits 15 percent of competitions at a true 50 percent and almost none at 70), at
     the cost of fifteen attempts each.
  4. *It still spends most on the floor.* A competition at 5 percent uses 5.6 attempts on average
     and survives a quarter of the time.
- **Why the score is not used.** A rule that kept a competition with no medal when one attempt was
  above the leaderboard median was considered and is not used: how often an attempt without a
  medal is above the median is not known for this model, and for several candidates the published
  runs of another agent put it near never (report §7), so the clause would have decided little and
  nobody could say how much. The score and the above-median flag are still recorded for every
  attempt and printed beside each class.
- **The placement uses the ladder's admission rule and attempt count** (ladder D6, "Per task,
  pooled"), so that the two families are admitted alike. A surviving competition gets fifteen fresh
  attempts: five at each of `low`, `medium` and `high`. With K medals of n observations it is
  admitted at 1/15 ≤ K/n ≤ 1/3 (1 to 5 of fifteen), judged once every effort has at least four
  scored observations; with fewer it is "not screened" and neither in nor out. `family.json`
  carries the ladder's label, "screened at n of 15 attempts".
- **What is claimed for a placed competition: "observed in the band", and nothing about its true
  rate.** Each is reported with its count and the exact (Clopper–Pearson) 90 percent interval, and
  with the 95 percent interval the ladder's readout prints. The interval's width is the limit of
  the placement: for 1, 2, 3, 4 and 5 medals of fifteen the 90 percent intervals are 0.3 to 27.9,
  2.4 to 36.3, 5.7 to 44.0, 9.7 to 51.1 and 14.2 to 57.7 percent. Every one reaches outside 10 to
  30 percent. The rule is wide: it admits a competition at a true 5 percent about half the time and
  one at 40 percent four times in ten (ladder D6). It is kept because a different rule here would
  make the two families incomparable, and a narrower one needs about 90 attempts per competition
  (ladder plan, "What this size can and cannot support").
- **The screen's attempts are never pooled with the fifteen.** They are printed beside them: a
  competition was chosen because of them, so pooling would bias its count upward.
- **If fewer competitions are placed than is useful.** The family supplements the Terminal-Bench
  set, so one placed competition is already useful. If none is placed, the line ends with a report.
  Two other definitions then exist, and each is **a later owner decision with its own request, never
  a silent switch**: above the leaderboard median (published for every agent; an easier bar), and a
  per-competition score threshold frozen from this line's attempts and applied only to fresh
  attempts (report §7; the only definition that can place most competitions by construction). The
  recorded scores let either be assessed on paper first, at no spend.
- **Cost if wrong.** If "any medal" is too coarse, few competitions are placed and the placement's
  spend buys little. The screen's known cost is the table's: about half of the competitions near 10
  percent are lost, and each competition above the band that survives costs fifteen placement
  attempts. The readout prints every excluded competition's scores against its thresholds so that
  the owner can see what was dropped.

### M2. The qualification check and the evaluator check (coordinator)

The benchmark has no reference solution that trains a model. What can be checked is that the grader,
as the verifier runs it, tells a perfect submission from a useless one.

- **Three legs, each through the verifier path an attempt uses** (the same package, the same
  verifier image, the allowlist policy, the tranche's CPU set):
  1. *Answers.* The harness's reference agent writes the held-out answers as the submission. It must
     earn reward 1 with a gold medal. Where the answers file is not itself a valid submission, the
     leg uses the gold submission the competition's configuration names (`kuzushiji`; scout
     report J).
  2. *Sample submission.* The competition's own sample submission is submitted. It must earn reward 0
     and be valid, and its score must equal the floor the benchmark's own test lists for it (report
     §3.2, column "Floor"), where one is listed.
  3. *Untouched.* An agent that does nothing leaves no submission. It must earn reward 0, with a
     reward the verifier wrote, not a missing one.
- **Repetitions: two of each leg.** The grader is deterministic and the legs take seconds, so the
  repeat checks only that the path is stable: the two scores of a leg must be equal. The ladder
  needed five because some of its verifiers depend on timing.
- **A competition qualifies only if all six runs give what is listed and its controls below pass.**
  One that fails and has no
  host-side fix is dropped, is not replaced, and its slots are not given to another competition. A
  failure means one of three things, and the ledger row says which: the preparation is defective (the
  benchmark's README lists some; report §6.4), the thresholds do not fit the rebuilt test set
  (report §3.1), or the wrapper is wrong.
- **What the check does not show:** that a medal is reachable. That rests on the published medal
  rates of report §7, which come from other agents.
- **What is already known.** The benchmark's grader was run on this machine, on the host, with
  hand-made answers for the three CPU-only competitions: the answers file earned gold, the uniform
  submission of `leaf` scored the listed floor, and a missing or malformed file got no score and no
  medal (scout report B). That shows the grader, not the verifier path, which Task 7 builds.
- **The evaluator check is separate, and it tests the measure where it decides: at the lines.** The
  three legs sit at the two ends of the scale, and any grader that orders scores correctly passes
  them, whatever line it draws for a medal. So each qualified competition also gets four synthetic
  controls, built on the host from the answers by replacing a share of the rows with the sample
  submission's values:
  1. *The lines* are the bronze threshold and the leaderboard median that the benchmark's own
     grader reports for the competition when run on the host.
  2. *The controls* are the two submissions nearest the bronze line, one scoring just past it and
     one just short of it, and the same pair at the median. The share of replaced rows is found by
     bisection in a seeded row order, down to one row, or to the smallest step that changes the
     score.
  3. *The expected class* of each control (medal or none, above the median or not) is written down
     from its host score and the two lines, in the metric's direction, before the control goes
     through the verifier.
  4. *The check:* each control, run through the verifier path an attempt uses, gets exactly its
     expected reward and flags, and the percentiles of the four controls and the three legs are in
     the order of their scores.
- **The predeclared margin and error rate.** The margin is the distance between the two controls
  of a pair, recorded per competition; the error rate allowed is zero wrong classes over every
  control and every leg of every competition in the tranche. A competition whose pair cannot be
  built on both sides of a line (a metric too coarse for it) is recorded as such and qualifies only
  on a coordinator's ruling.
- **These controls validate the evaluator only** (`AGENTS.md`, "Task-difficulty calibration"). They
  are constructed, not naturally produced; they say nothing about how hard a competition is and
  replace no part of the screen or the placement. The synthetic fixture competition validates the
  code and qualifies nothing.
- **A paper check beside them, deciding nothing by itself:** where the benchmark's repository holds
  grading reports of published runs for a candidate, their scores and medal flags are compared with
  what this verifier's lines give for the same scores. A disagreement goes in the ledger with the
  competition's name. Whether those reports can be read from the clone is not verified.
- **Cost if wrong.** A grader that scores a competition wrongly would place it wrongly. The
  controls show that this verifier applies the benchmark's lines exactly, ties and direction
  included. They do not show that the benchmark's lines are fair on the rebuilt test set (report
  §3.1); only the screen's scores can.

### M3. Withholding (coordinator)

- **Two images per competition, built here.** The agent image holds the public data, the
  description, the sample submission and, if M6 is decided as recommended, the pretrained weights.
  The verifier image holds the held-out answers, the benchmark's grader and the leaderboard snapshot
  with the thresholds. The
  agent's container never holds any of the last three, and the benchmark's package is not installed
  in it. The installed harness supports this shape: a verifier in its own container, built from its
  own image, receiving only the files the task declares as artifacts (scout report D3).
- **Only the submission crosses.** The task declares the submission directory as its one artifact.
  An attempt that writes no submission still reaches the verifier and gets a written reward of 0
  (run on a scratch task: scout report D5). The verifier trusts nothing in what crosses: its script
  reads only a regular file named `submission.csv`, with `python -I`, from a working directory
  outside the uploaded paths. The harness already drops a symbolic link that points out of the
  artifact when it copies the artifact over (read in Harbor 0.25.0's artifact handler during this
  plan's review); Task 7 holds that with a submission that is a link to the answers' path.
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
  be invalid for the grader. The readout counts the invalid submissions; it cannot tell whether an
  agent ran the check. **The sample it reads is always a public copy.** For `textnorm-ru` the
  benchmark's configuration names a sample submission in the private directory and the public copy
  is inside an archive (scout report B); the wrapper takes the public one, and a test holds that it
  copies nothing from a private directory into an agent image.
- **Two checks, as in ladder D1.** By construction: the build context of the agent image is
  assembled from the public directory alone, and a test holds that with the fixture. On the built
  image: its file system is exported from a container that was never started and searched, on the
  host, for every file of the private directory and of the grader by SHA-256, for the leaderboard
  snapshot, and for lines that occur in a private file and in no public file. A hit drops the
  competition. The ladder kit's image check is written for a package's `solution/` and `tests/`
  directories and its line matching does not fit an answers file (scout report I4), so this check is
  new code.
- **The check's result belongs to one image content.** It is recorded in `tasks.json` against the
  image's digest, and the package names its images by that same digest and never by a tag (M4). An
  image rebuilt under the same name has another digest: the package would have to be rewritten to
  use it, which changes the package's digest and the label, and the wrapper refuses a package whose
  image digest has no withholding result.
- **On the host:** the prepared data, the answers and the images stay outside the repository; the kit
  holds names and digests. The reference agent's copy of the answers exists only in the package
  used for the answers leg, never in the package an attempt runs.
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
  private module, sets a closed list of data names in it, runs its own checks, and then calls the
  launcher's own entry point with an environment it has built. **It replaces or wraps no function
  of `ladder.py` or of `manifest.py`.** What it replaces is this:

| Name | In | The ladder's value | This family's value |
| --- | --- | --- | --- |
| `KIT` | `ladder.py` | The reviewed kit's directory | The tranche's directory, `experiments/mle_bench_tasks/tranches/<tranche>/`: its own `ladder.json` and `tasks.json`, and links to the four reviewed files the launcher addresses through this name (`harbor_patient.py`, `relay-compose.yaml`, `token_scan.py`, `passthrough.py`) |
| `PLAN` | `ladder.py` | The ladder plan | The tranche's own ledger file (below) |
| `EFFORTS` | `ladder.py` | `low`, `medium`, `high` | The screen: `medium` alone. The placement: unchanged |
| `PACKAGES` | `ladder.py` | The Terminal-Bench package directory's name | `packages`, under this line's cache |
| `Ctx` | `ladder.py` | State under `~/.local/state/lh-ladder` | A subclass that differs only in the state root, `~/.local/state/mle-bench/<tranche>` |
| `manifest` | `ladder.py` | The ladder's manifest module | A second private load of the reviewed `manifest.py`, with the four names of the next rows set |
| `KIT`, `MANIFEST` | That load of `manifest.py` | The reviewed kit; its `manifest.json` | This family's kit, `experiments/mle_bench_tasks/`; `manifests/<tranche>.json` in it |
| `NOT_COVERED` | That load of `manifest.py` | The manifest, two prose files, results, caches | The same, and `manifests/` and `tranches/` |
| `EXTERNAL` | That load of `manifest.py` | The price table and the criterion's test module | Those two; every file the ladder's own manifest covers, listed by calling the unmodified module, so the list cannot fall behind; and every file of this tranche's directory, each link hashed through to its content |
| `LH` | The environment given to the launcher | Unset: `~/lh-cache` | `~/mle-cache`, this line's own cache (below) |

- **Each tranche has its own ledger file, and the launcher reads no other.** The launcher takes
  every `Configuration label` row of the ledger it is given as a label of the same tranche, and
  accepts a `Smoke read`, `Pilot read` or `Round 1 read` row that names any of them; it matches a
  `Ruling` row by its date and cause or attempt id, and attempt ids repeat from tranche to tranche.
  With one ledger for the line, the reads of the first tranche would release every later tranche's
  pilot and rounds with no person reading them, and a ruling written for one tranche could lift a
  stop in another. So:
  1. *The file* is `docs/plans/2026-11-15-mle-bench-ledger-<tranche>.md`, one per tranche, with the
     ladder's table layout. The wrapper sets `PLAN` to it, and the launcher reads it as committed on
     `main`.
  2. *It is created with its first row before the tranche's first call,* and this plan's
     [ledger](#ledger) links it in the row that opens the tranche.
  3. *Before the tranche's first paid start it holds,* as dated rows: the tranche's name, model,
     efforts, competitions, slots, starts cap, cap per attempt, ceiling and attempts at once, with
     the approval they run under; each competition's package digest, its two image digests, its
     withholding result against those digests, and the outcomes of its six legs and four controls;
     the review verdict and the rehearsal results the tranche rests on; the owner's two
     confirmations, shares, days and first reading, by date and without any account detail; the
     hand-over (the ladder's launcher is not running, its passthrough is stopped, and the previous
     tranche's last settlement is on an earlier calendar day); free disk on `/` and on `/home`
     against M9's launch condition; and last, at the freeze, the row
     `Configuration label` with the manifest's SHA-256 and the runtime commit.
  4. *During the tranche it receives* the rows the launcher waits for or reads (`Smoke read`,
     `Pilot read`, `Round 1 read`, `Ruling`), each cut and stop, and at the end the priced usage and
     the allowance used.
  5. *This plan's ledger keeps the line's decisions:* approvals, reviews, owner actions, each
     tranche's opening and result, and the links. The launcher never reads it.
- **Images are named by digest, never by tag.** The launcher's task check compares the two image
  references in a package's `task.toml` with `tasks.json` as strings and reads no image id. For the
  ladder those strings are registry digests, which are content addresses. For images built here a
  name with a tag is not: an image rebuilt under the same tag would pass every check and run a paid
  attempt on content no withholding check has seen. So:
  1. *`task.toml` carries each image as `<name>@sha256:<digest>`,* the digest Podman's store reports
     for the built image, and `tasks.json` carries the same strings. The reviewed string comparison
     is then a comparison of content, and a rebuild cannot be used without rewriting the package,
     which changes the package's digest and the label.
  2. *The wrapper refuses* a package or a `tasks.json` entry whose image reference does not end in
     `@sha256:` and 64 hexadecimal digits, and a `tasks.json` entry whose withholding result names
     another digest than its image.
  3. *Task 7 must show on the fixture* that Harbor 0.25.0 with podman-compose 1.6.0 starts a local
     image given by digest without a pull. This is not verified.
  4. *If it cannot,* the images are served from a registry on the loopback address of this machine
     and named `localhost:<port>/<name>@sha256:<digest>`, which is the form the ladder's packages
     already use and is pulled by content. The registry is then part of the kit: its own image is
     pinned by digest, it listens on the loopback address only, and the withholding check runs on
     the image as pulled from it. **No paid start is made until one of the two forms has been shown
     on the fixture,** and the tranche ledger says which.
- **This line has its own cache directory, `~/mle-cache`.** The launcher keeps host-side files
  under its cache: the limits compose file and the containers override, whose content it compares
  with the criterion before every start, and the package directory. This family's limits file
  differs from the ladder's (shared memory, the GPU device), so in a shared cache each line would
  have to overwrite the other's file, and the ladder's next start would stop on "the configuration
  changed". The wrapper therefore gives the launcher `LH=~/mle-cache` and refuses when that
  resolves to the ladder's `~/lh-cache`. In it: `logs/` with this line's two host-side files,
  `packages/<name>/` with the task packages, `prepared/` with the prepared data and the answers,
  `recordings/`, a directory of its own (never a link; Task 7's setup creates it, mode 700), which
  the launcher's read of the whole file set at each round's end scans, and the wrapper refuses a
  launch without it,
  and `hvenv`, a link to the ladder's harness environment, whose versions the criterion pins and
  the launcher checks. The benchmark's clone and its environment stay where the fact-finding put
  them, under `~/lh-cache/mle`, and are only read. Each tranche's jobs and state are under its own
  state root, as in the ladder. Nothing this line writes is under `~/lh-cache`, and Task 5 tests
  that a launch reads nothing under `~/lh-cache/logs`.
- **What the manifest covers, and what that gives.** A tranche's manifest is
  `manifests/<tranche>.json`; its SHA-256 is the tranche's label. It covers by hash every file of
  this family's kit (the wrapper, the criterion generator, the task wrapper, the verifier, the
  withholding check and the readout included; not the prose, the results, the other manifests or
  the other tranches' directories), every file of this tranche's directory, and every file the
  ladder's own manifest covers. The launcher's manifest check runs at launch and again before every
  start, so an edit to `screen.py` or to any other covered file, a new file or a missing one, stops
  the tranche before the next start, committed or not. The launcher's own clean-tree check still
  covers `experiments/long_horizon_tasks` and `orchestrator`, as reviewed.
- **What the wrapper adds, around the launcher and before it is entered.** None of these replaces a
  check of the launcher; each is a refusal of the wrapper's own, tested in Task 5:
  1. The tranche's name is one of the kit's list.
  2. The cache is this line's (above).
  3. Every image reference is pinned and has its withholding result (above).
  4. `experiments/mle_bench_tasks` has no uncommitted change, by the same `git status` test the
     launcher applies to its own kit. This also covers the files the manifest leaves out.
  5. For a live launch or resume: the wrapper takes the ladder's launcher lock and a lock for this
     whole line, holds both until the launcher returns, and refuses when either is held; it refuses
     when the ladder's passthrough, or another tranche's, answers on its socket (M5).
  6. Free disk on `/` and on `/home` meets M9's launch condition.
  7. For a GPU tranche: no process holds memory on the card. While the launcher runs, the wrapper
     records once a minute which processes do, into the tranche's state, for the readout (M5).
- **What holds per start and what holds only at launch.** Per start, by reviewed code: the manifest
  check (and with it this kit's bytes), the label and the runtime commit against the tranche
  ledger, the detached checkout, the harness versions and the two host-side files, the allowance
  guard, the ceiling and the starts cap; continuously, the disk floor and the stops. At launch
  only: the package and image check of each competition (the launcher's own task check runs once,
  as in the ladder) and the wrapper's seven refusals. The two locks are held for the launcher's
  whole life.
- **What stays exactly as reviewed:** the model check, the fake token's form, the money lock with
  its reservation and settlement, the classification, the allowance guard, the usage-limit and
  paid-usage handling, the token scan and the runtime check, the teardown, the reconcile, the
  passthrough and the relay. One key name in `tasks.json` keeps the ladder's spelling
  (`digest_4_1_0` holds the digest of the package the wrapper built), and the file says so.
- **An older ready-made dataset does not save this work.** `mlebench-lite`, made for the first
  Terminal-Bench, is in the old task format, keeps the answers and a Kaggle credential inside the
  agent's image and scores "above median" (scout report E). Two things are taken from it: how the
  instruction is assembled, and its grader call, which is the whole verifier.
- **How a package satisfies the launcher's task check.** The wrapper writes a Harbor task package
  per competition, under its short name: `task.toml` (the agent's time limit, CPUs and memory, the
  artifact, the two images by digest, and a canary line of this family, which the launcher requires
  and scans for), the instruction (the benchmark's instructions adapted to M3, then the
  competition's original description) and nothing else. Identity is "every file of the package
  equals the digest recorded at qualification", with the two network keys exempt as in ladder D1.
- **The verifier's output.** It writes the reward (1 or 0) and the four graded outcomes as further
  numbers, and a test report in the one form the launcher reads: `verifier/ctrf.json`, with
  `results.summary.tests` at five (valid, above median, bronze, silver, gold) and
  `results.summary.passed` at the number that hold. Each competition is mapped to `"ctrf"` in the
  criterion's `readout.graded_outcome.verifiers`; without that entry the launcher exports no graded
  outcome for it. The medal step then reaches the export with no change. The score and the
  percentile are read by this family's readout from the result file that gave the attempt's
  reward: the trial's own, or the regrade's when the reward came from a regrade.
- **What the wrapper cannot give, and what the plan does instead.**
  1. *No "one attempt on the GPU at a time" beside other attempts.* A slot has no resource class
     (scout report I3, I7). So a tranche holds competitions of one class, and a GPU tranche runs one
     attempt at a time (M5).
  2. *No ceiling per calendar day* (scout report I6). So no tranche's ceiling is above USD 200, one
     tranche runs at a time, and a tranche starts only on a later calendar day than the previous
     tranche's last settlement (M9).
  3. *No per-task compose file and no mount.* The launcher passes two fixed compose files and no
     mount setting. The GPU device and the shared-memory size therefore go into the tranche's limits
     file, which is criterion data: a device entry in an extra compose file reached a task's
     container under Harbor 0.25.0 and rootless Podman, where the task field for a GPU is refused
     (run: scout report D5). The public data and the weights go into the agent image, not into a
     mount.
  4. *No disk limit for an attempt.* A container has no storage limit. What the launcher has is one
     floor, checked about once a second on the least free space of `/` and `/home`, attempts in
     flight or not; below it every running attempt is stopped and the tranche stops. M9 sets the
     floor and, separately, the room a launch needs above it.
  5. *No slot that depends on an earlier outcome.* The schedule is fixed by the criterion, and the
     launcher's export refuses a start whose competition is not in the current list. So the
     screen's second stage is a tranche of its own (M9), with its own label, state and ledger.
- **What must be reviewed again, by a reviewer who wrote none of it** (Task 8): the wrapper whole,
  that is, the list of replaced names in both modules with a test that no use of a replaced name is
  bound when the modules are loaded, and each added refusal with a test that it runs before the
  launcher is entered; the criterion generator, with a test that every group it does not replace
  equals the ladder's; the task wrapper, the verifier and the two withholding checks; this family's
  readout. Because every claim above is about what reviewed code reads once the names are
  replaced, the reviewer also reads, in `ladder.py`, the functions that read them: `ledger_text`,
  `ledger_labels`, `hold` and the ruling readers; `_manifest_refusal`, `_live_refusal` and
  `config_refusal`; `harness_refusal` and `attempt_command`; `task_refusal`; `socket_refusal`;
  `free_gb` and `host_stops`; `OneLauncher`; `schedule`, `queue` and `export`; `graded`. Those
  functions are not reviewed again for their own correctness, and neither are `passthrough.py`,
  `token_scan.py`, `slot_record.py` and the relay: their bytes are bound by hash in each tranche's
  manifest.
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
  sized for eight hours (scout report I5) and the GPU's stage one alone is thirty attempts, thirty
  days at 24 hours each. A shorter limit is then a new configuration label, never a change in
  place.
- **The alternative, eight hours from the start,** would triple the worst-case throughput and
  shorten the exposure to usage limits (M8). It was not chosen because it would cap the staged arm of
  a later comparison, which must run under the same limit, and so would force a second calibration.
- **Parallelism.** A CPU tranche runs the three CPU-only competitions at up to three attempts at
  once (its smoke and its pilot each run alone). A GPU tranche runs one attempt at a time. The
  roadmap's "about four at once, one of them on the GPU" is not reachable without a change to the
  reviewed launcher (M4); what is lost is the overlap of the short CPU attempts, under a day at the
  report's estimate.
- **Three at once is an upper bound, and fewer is likely.** Until the allowance guard has a
  five-hour figure it allows at most two attempts at once, and a tranche's own pilot often gives
  none (M8). The load gate is judged on the machine's load averages: one attempt whose libraries
  start a thread for each of its 24 CPUs can close it alone, and other sessions have been seen to
  hold the load near 120 (scout report G). A gate that stays closed for two hours with nothing in
  flight pauses the tranche.
- **Per attempt** (report §9.2, estimates): a CPU-class attempt gets 6 CPUs, 16 GB of memory and 4 GB
  of shared memory; a GPU-class attempt gets 8 CPUs, 32 GB, 8 GB of shared memory and the whole GPU
  (an RTX 5080 with 16 GB; the estimates of report §9.2 were made for a 24 GB card and are not
  rechecked against 16 GB). Shared memory must be set: Podman's default is 64 MB (scout report J). The verifier's
  container gets no GPU. The process limit stays 4,096. These are fields of each package and of the
  tranche's limits
  file, equal for every attempt of a competition, and a later comparison uses the same.
- **CPU set and load:** the ladder's set, CPUs 8 to 31, and its load gate (both load averages at or
  below 24), unchanged.
- **This line and the ladder are never in flight together, and neither are two tranches of this
  line.** Three reasons: the token must be in one host process, and each tranche has its own
  passthrough; each launcher's allowance guard counts only its own usage since the owner's reading,
  so two at once would overdraw the owner's share; and both use the same CPU set and load gate. The
  launcher's own lock is per state root, so by itself it stops none of this. What does:
  1. *In code.* For a live launch or resume the wrapper takes the ladder's launcher lock, on the
     ladder's state root, with the reviewed lock class, and a second lock for the whole line under
     `~/.local/state/mle-bench/`. It holds both until the launcher returns and refuses when either
     is held. An attempt is in flight only while its launcher runs, so no attempt of one line
     overlaps a launcher of the other: the ladder's launcher is refused by its own reviewed lock
     while this line's runs, with no change to it. The wrapper also refuses while the ladder's
     passthrough, or another tranche's, answers on its socket.
  2. *By procedure.* A paused tranche has no launcher running and holds no lock, but its
     passthrough may still be up, and the ladder's launcher does not know this line's sockets. So
     stopping this line's passthrough is part of every hand-over to the ladder, and the hand-over is
     a row in the tranche ledger. A rehearsal takes neither lock (it holds no token and makes no
     request to the vendor) and is run only when the ladder has nothing in flight.
  3. *The allowance.* The ladder has first call on the owner's allowance (it is approved, and its
     effort verdict informs this line); the split is owner action 7.
- **The GPU is checked for other use.** Nothing in the launcher looks at the card, and other work
  on it during an attempt would lower that attempt's result as an observation. The wrapper refuses
  to launch a GPU tranche while any process holds memory on the card, and records once a minute
  which processes do; the readout flags every attempt during which a process outside its own
  container did. A flag excludes nothing by itself; the coordinator rules on it before the class is
  read.
- **Cost if wrong.** If direct sessions use most of 24 hours, a GPU tranche takes weeks and the
  eight-hour read stops it after at most two sessions. If CPU-class competitions needed a GPU for a
  medal after all, they land at the floor for a reason of ours; the report's class is an estimate.

### M6. Network policy and pretrained weights (owner; recommendation: weights in the image)

- **The agent phase runs on the ladder's allowlist, unchanged:** the relay by name, the package
  indexes and the distribution mirrors (ladder D3). No model hub, no code host, no Kaggle host.
- **Pretrained weights are the open question** (report §5.2, §12). Medal-level scores on the image
  and text competitions depend on them.

| Option | Reproducibility | Contamination | Cost |
| --- | --- | --- | --- |
| A. A model hub on the allowlist | The hub's content changes; an attempt next month may fetch something else | A hub also serves datasets and other users' checkpoints, some trained on competition data; the dog-breed test images come from a public labelled set (report §5.2). The egress log names only refused connections, so what an attempt fetched from an allowed host is visible only where the transcript prints it | No image work; several more hosts on the list, since a hub serves files from other names, and the egress filter sees host names only, never paths (scout report H) |
| **B. A fixed set of weights in the agent image** | Fixed by SHA-256 in a committed file that the manifest covers | No model hub is reachable. The package indexes still are, and they can serve any file (M7) | About 7 GB of disk in one shared image layer (an estimate); engineering in Task 11; the list bounds what an attempt can build |

- **Recommendation: B.** It keeps the one network policy for both families, and it is the only
  option under which the readout can say what an attempt had. The image sets the libraries' offline
  switches, so that they read the placed files (scout report H). An agent can still install
  packages, PyTorch included, from the package index, which is on the list.
- **The set is part of the task definition.** Which checkpoints are in the image decides which
  competitions can earn a medal at all: a competition whose medal needs a model the set does not
  hold sits at the floor for a reason of ours, and the readout cannot tell that from the model's
  failure. The set is therefore specified as data, by a rule, before any attempt of this line is
  seen, and it does not change after the first GPU attempt.
- **The rule by which the set is chosen.** The benchmark gives no list to copy: its environment
  pins the libraries (`torch` 2.2.0, `transformers` 4.44.2, `timm` 0.9.7) and names no checkpoint,
  and the published set-ups leave the network open for them (read in the clone's `environment/` and
  `agents/`; report §5.2). So the rule is this plan's:
  1. *Publisher's originals only.* A checkpoint as its authors, or the library that ships it,
     released it, fetched at a named revision.
  2. *General-purpose only.* Pretrained on general data (ImageNet, COCO for the one detector,
     general text). None fine-tuned for a downstream task, and none trained or fine-tuned on a
     Kaggle competition's data or on a dataset one of the thirteen competitions was built from.
  3. *By modality, not by competition.* For each kind of input the ten GPU candidates have, the
     standard base architectures that the benchmark's pinned libraries load by name, in at most two
     sizes. No checkpoint is added because a competition's public solutions used it.
  4. *Bounded.* At most twelve checkpoints and 8 GB in all, one set, the same in every GPU agent
     image, in one shared image layer.
  5. *Usable.* A licence that allows research use and a local copy. A checkpoint that needs an
     account to accept terms is in the set only if the owner accepts them.
- **The proposed set under that rule** is below. The names are from the planner's knowledge of
  these libraries and are not verified; the sizes are rough. Task 11 fixes the exact revisions.

| Modality | Checkpoints proposed | Rough size | Candidates it is meant for |
| --- | --- | --- | --- |
| Image classification and regression | ResNet-50, EfficientNet-B3, ConvNeXt-Small and ViT-B/16, each with its ImageNet weights | 0.7 GB | `whale`, `petfinder`, `cassava`, and `kuzushiji`'s classifier |
| Object detection | Faster R-CNN with a ResNet-50 FPN backbone, COCO weights | 0.2 GB | `kuzushiji` |
| English text | BERT-base (uncased), RoBERTa-base, DeBERTa-v3-base and DeBERTa-v3-large | 2.2 GB | `patent`, `tweet`, `essay2`, `jigsaw`, `lmsys` |
| Multilingual text | XLM-RoBERTa-base and XLM-RoBERTa-large | 3.3 GB | `chaii` |

- **What the proposed set leaves out, stated before the fact.** It holds no generative language
  model and no checkpoint already fine-tuned for question answering. If medals on `lmsys` or
  `chaii` need those, as the planner believes of their public solutions (not verified), these two
  will screen low for a reason of ours. The owner may add to the set under clause 5 before the
  freeze; after it, a change is a new label and a new screen of the GPU class.
- **The committed list.** Before the GPU class's first freeze, `experiments/mle_bench_tasks/weights.json`
  holds for each checkpoint its name, its source and revision, the SHA-256 of every file, its size,
  its licence and the modality it serves. The manifest covers the file, so the set is part of the
  label; the instruction names the set to the agent; Task 11 shows that every checkpoint loads in
  the image with the offline switches set.
- **What B costs if wrong.** Rates are lower than under the benchmark's usual policy and are not
  comparable with it. A competition whose medal needs a model outside the set sits at the floor for
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
- **The allowlist is not closed to the labels.** The package indexes on it serve whatever anyone
  has uploaded, and the held-out rows of every candidate come from the competition's original
  training set, whose labels are public. A package that carries such a copy, or pretrained
  weights, can be installed like any other. Whether one exists for a candidate was not searched.
- **What the logs let the readout flag, and what they do not.** The egress log kept for each
  attempt shows the connections that were refused, by address and count, which is how an attempt
  that reached for a model hub or for Kaggle shows. Of an allowed host it shows at most that the
  host was reached: the filter sees host names, never paths or content. The transcript shows every
  command the agent ran, so the readout lists, per attempt, the packages it installed, and the
  frozen terms are searched in the transcript as above. A package that carries labels under a
  harmless name and is used without comment is not detected. That is an accepted limit, and it is
  the ladder's too: both families run on the same allowlist.
- **What cannot be detected:** a submission that reproduces a public solution from memory. The
  benchmark's own plagiarism check needs the public notebooks and its rule-breaking check calls a
  model outside this project's rules (report §6.4); neither is used.
- **The original description is used,** not the benchmark's obfuscated one: the published rates that
  ranked the candidates used the original. The cost is more recall.

### M8. Usage limits (coordinator; the inputs are the owner's)

The ladder's rules apply unchanged, because the passthrough and the launcher are unchanged (ladder
D4, D5). The ladder's allowance guard is reused as it is; its inputs and readings are entered for
each tranche. Its two figures (priced dollars per meter point, weekly and five-hour) are the ladder
pilot's when that has run, entered with a ledger row; a tranche's own pilot is one cheap attempt,
which will often move a meter by less than two points and then gives only bounds (ladder D7).
Without a five-hour figure the guard allows at most two attempts at once, which caps a CPU
tranche's three.

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

| Tranche | Name | Competitions | Effort | Slots | Starts at most | Cap per attempt | Ceiling | Attempts at once |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Screen, CPU, stage one | `screen-cpu` | The 3 CPU-class | `medium` | 9 | 11 | USD 8 | USD 50 | 1 (smoke), 1 (pilot), then up to 3 |
| Screen, CPU, stage two | `screen-cpu-2` | Those of the 3 with no medal, as funded | `medium` | At most 9 | Its slots and 2 | USD 8 | What stage one left of the USD 50 | As stage one |
| Screen, GPU, stage one | `screen-gpu` | The 10 GPU-class | `medium` | 30 | 34 | USD 8 | USD 150 | 1 |
| Screen, GPU, stage two | `screen-gpu-2` | Those of the 10 with no medal, as funded | `medium` | At most 30 | Its slots and 4 | USD 8 | What stage one left of the USD 150 | 1 |
| Placement, each | `place-cpu`, `place-gpu` | At most 3 survivors of one class | `low`, `medium`, `high` | At most 45 | At most 50 | USD 8 | USD 200 | As its class |

- **The screen: 39 to 78 slots, at most 90 starts, USD 200** (USD 50 for the CPU class and USD 150
  for the GPU class, which gives both the same room per attempt). The cap is the top of the
  report's range for a session that stops by itself.
- **Why stage two is a tranche of its own.** The launcher's schedule is fixed by the criterion, so
  three more attempts for some competitions cannot be added inside a running tranche (M4). Stage
  two of a class is therefore generated after stage one's export, by a rule fixed here:
  1. *Its competitions* are those of the class with no medal among stage one's observations, in the
     order of their rank in report §8.2.
  2. *Its ceiling* is the class's ceiling less everything stage one's launcher committed: the
     settled cost of every start, cuts included, and the live probe's usage it counted. The two
     stages of a class can never pass the class's ceiling.
  3. *Its size.* With m the mean priced cost per start of stage one, it holds the first k
     competitions of that order, k the largest number for which (3k − 1) × m + USD 9.45 is within
     its ceiling: the launcher reserves the cap and USD 1 before the last start and counts the
     probe's usage, at most USD 0.45, again. **k is at least two (ruling M9-R1):** with one
     competition the launcher schedules the smoke and the pilot as one slot, the pilot never starts
     and every export is refused, so where only k = 1 fits nothing is funded. A competition beyond k
     is reported "not screened: the second stage was not funded", and no attempt is spent on a stage
     that cannot finish. With k at zero there is no stage two. A tranche of either stage with fewer
     than two qualified competitions is refused by the generator and by the wrapper.
  4. *Everything else* in its criterion equals stage one's, which a test holds. The generator takes
     stage one's export and gives the same criterion every time; the stage-two ledger's first row
     states the list, m, k and the ceiling.
  5. *It has its own smoke, pilot and reads,* as the launcher requires of every tranche. They are
     its first slots and count as observations like any other.
- **What USD 200 pays for.** The launcher reserves the cap and USD 1 before each start. Stage one
  completes only if its attempts average under about USD 5.05 (CPU) or USD 4.85 (GPU). The second
  stage of every competition, 78 attempts, fits only if attempts average under about USD 2.35. At
  the central estimate of USD 3, the rule funds the second stage of no CPU competition (one would
  fit, and a stage of one is not run: M9-R1) and of five GPU competitions. Competitions at the floor nearly always need it (M1), and the report expects 8 to 11
  of the 13 outside the band (2 to 5 in it), so at USD 3 some competitions will end "not screened".
  **The estimates therefore do not allow USD 200 to cover the whole sequential screen at their
  centre.** The plan keeps USD 200 as its proposed total and funds the second stage in rank order;
  the alternative, USD 250 (CPU 61, GPU 189), funds it for all thirteen at USD 3 and is put to the
  owner in action 9. **If the smoke and the pilot of a stage-one tranche average above its figure,
  the coordinator reports before round 1;** no cap or ceiling changes without a new label and a
  ledger row.
- **The placement: at most six competitions, 90 slots, 100 starts and USD 400,** in at most two
  tranches. A tranche of 45 slots completes only if its attempts average under about USD 4.30, at
  three efforts of which `high` is the dearest. If the ceiling ends it early, the last round is
  lost first; a competition with at least four observations at each effort is still judged (M1),
  and one with fewer is "not screened". If more than six survive, the owner chooses which are
  placed. The placement starts only after the screen's result is reported to the owner (roadmap
  step 12).
- **The line in all: at most 168 slots, 190 starts and USD 600.** The ladder's live probe is counted
  into each tranche's total by the launcher, a conservative double count of at most USD 0.45 a
  tranche.
- **Effort for the screen: `medium`.** The placement pools three efforts, and the middle one is the
  best single guide to that pooled rate whichever way success moves with effort, which the ladder has
  not yet measured. It is also the cheaper choice (report §6.3).
- **The day.** USD 200 per calendar day holds by the ceilings and by procedure; no guard counts a
  day.
  1. *What holds it.* No tranche's ceiling is above USD 200. One tranche of the line runs at a
     time, which the wrapper's lock enforces (M5). A tranche makes its first start on a later
     calendar day than the previous tranche's last settlement, which is a person's row in the
     tranche ledger and is checked by nobody else. Then each day holds the spend of one tranche
     only, and a tranche spends at most its ceiling over all its days.
  2. *An attempt that crosses midnight.* Each request is counted on the calendar day, in this
     machine's local time, on which the passthrough priced it. An attempt of 24 hours is so split
     between two days, and the readout prints the line's priced usage per day from the
     passthrough's request logs.
  3. *What would break it.* A tranche started on the day the previous one settled. Two tranches
     could then spend up to their two ceilings on that day.
- **Each tranche's order,** as the launcher runs it: a smoke (one attempt, then a person's read
  against the ladder's smoke checks), a pilot (one attempt at the screen, the owner reading the
  meters before and after), then the rounds, with a read after round 1. The CPU class's stage-one
  smoke is `leaf` and its pilot `birds`; the GPU class's smoke is `patent`, the smallest that needs
  the weights and the GPU, and its pilot `tweet`. All four have small data, because after a smoke
  and a pilot the launcher exports each agent container's whole file system into the token scan.
  The export has no time limit of its own; the scan around it has three hours, and the export
  includes the image's layers, 8 to 12 GB and the weights for a GPU image (scout report I5).
- **Disk: one floor, checked all the time, and room above it at launch.**
  1. *What the launcher does.* About once a second, attempts in flight or not, it takes the least
     free space of `/`, `/home`, the state root and the cache. Under the criterion's floor it stops
     every running attempt and the tranche. It has no other disk rule.
  2. *The floor is 20 GB,* the ladder's: the level under which the machine itself is at risk. It is
     not raised to hold the attempts' scratch, because a floor is a stop, and a higher one would
     stop a smoke that had only begun to write.
  3. *The room above it is a condition of the launch,* refused by the wrapper and read again by a
     person at each read. On `/home`: the floor and the scratch of the attempts that may be in
     flight, which is three CPU-class attempts at 10 GB or one GPU-class attempt at 30 GB (the upper
     figures of report §9.2), so 50 GB for either class, counted after the tranche's images are in
     the store. On `/`: 40 GB, the floor and 20 GB for what other sessions write there; `/` has 48
     to 50 GB free today and was seen at 31 GB during the ladder's oracle pass. A smoke launched at
     these figures can write its whole estimated scratch and stay above the floor.
  4. *All of these are estimates.* What an attempt writes is first measured by the smoke. An attempt
     that writes more than its estimate, or another session that fills `/`, takes the least free
     space under the floor, and then every attempt in flight is stopped, a 24-hour one included.
     Images are built only while no launcher of either line runs, because a build is staged on `/`.
- **A tranche stops** at any stop of ladder D7.7, which the criterion copies: a failed smoke, another
  model in a response, another CLI version or tool list, a passthrough refusal for model, tool, path
  or token, a vendor 401, a sign of paid extra usage, a match of the token scan, three usage-limit
  answers in a row, contaminated attempts on three competitions, and free disk under the floor. The
  share-of-starts thresholds are judged from fewer starts than the ladder's twenty, because the
  tranches are small: infrastructure failures above 10 percent from 5 starts (CPU) or 10 (GPU), and
  the ladder's pause for cuts from the same counts.
- **The line stops for a competition** when the screen puts it above the band or excludes it low
  (M1). **The line stops altogether** when a tranche ends in a stop that the coordinator does not
  lift, when the eight-hour read or the cost read goes to the owner and the owner ends it, or when
  no competition survives the screen.
- **Nothing is topped up.** No slot is refilled, no threshold moved and no ceiling raised after a
  tranche's first attempt. Stage two is not a top-up: its rule, its list and its ceiling follow from
  stage one's export by the rule above. More attempts, another effort, another competition or
  another definition of success is a new request.
- **Cost if wrong.** A ceiling too low cuts the tail of a tranche's fixed order, and with three
  attempts per competition in each stage, one lost attempt leaves a competition "not screened". A cap
  too low ends long sessions as flagged observations; the verifier still grades whatever submission
  exists. A floor or a launch condition set from wrong estimates stops attempts in flight, and each
  one stopped is a start spent with no observation.

### M10. The Kaggle token (owner places it; coordinator rules the handling)

- **The owner creates and places it,** by the steps of owner action 1, in a terminal outside tmux
  and outside any agent session. It is a file of mode 600 in a directory of mode 700 that lies
  outside every repository and outside anything synced or backed up.
- **It is the legacy credential,** a `kaggle.json` holding the account name and a key: the client
  version the benchmark pins reads nothing else (scout report C).
- **Only the download command reads it,** on the host: `fetch.sh` of this kit, which is given the
  directory's path (`KAGGLE_CONFIG_DIR`) and never the value. The script always sets that variable,
  because the client otherwise creates a configuration directory in the home directory, and it runs
  with no terminal input, because the benchmark asks a question on standard input when rules are
  not accepted (scout report C). Its own output is one fixed line per competition (done, rules not
  accepted or download failed, no room); the download tool's raw output goes to a file inside the
  token's directory, never to a pane. The download request itself carries the account name to
  Kaggle, as any download must.
- **The script is reviewed before it first runs** (Task 10a), by someone who did not write it,
  because it is the only code of this line that touches the credential.
- **The preparation may read it too.** The benchmark's preparation step imports the same Kaggle
  client, which may read the credential when it is imported (scout report C). Until Task 10 has
  shown the download and the preparation apart, the preparation runs inside `fetch.sh`, under the
  same rules.
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
do, and what it blocks. Nothing here blocks Tasks 1 to 9 or Task 10a. The tranche ledgers and the
locks of M4 and M5 ask nothing of the owner.

1. **A Kaggle account and an API credential.** *Why:* the benchmark downloads each competition's data
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
   reads the Kaggle token (M10). *What to do,* once the script has passed its review (Task 10a), in
   the same kind of terminal: `KAGGLE_CONFIG_DIR="$HOME/.local/state/mle-secret" experiments/mle_bench_tasks/fetch.sh
   <slugs>`. It prints one line per competition. *Blocks:* Tasks 10 and 12.
5. **Disk, on `/home` and on `/`.** *Why:* nothing limits what an attempt writes in its container.
   The launcher has one guard: while it runs it reads the free space of `/` and of `/home` about
   once a second, and when the lower of the two is under 20 GB it stops every attempt in flight
   (M9). So a tranche launches only with room above that floor on both, and other work must not
   take either below it while a tranche runs. *Today (2026-11-15):* `/home` has 61 GB free and is
   97 percent full; `/` has 48 to 50 GB free and was seen at 31 GB during the ladder's oracle pass,
   when other sessions wrote to it. *What is needed,* all estimates until the smoke has measured
   an attempt:

   | | CPU tranches | GPU tranches |
   | --- | --- | --- |
   | On `/home`, free at launch, with the images already built | 50 GB | 50 GB |
   | This family's images on `/home` | About 5 GB (images 3, data 2) | About 34 GB more (the shared GPU base 8 to 12, the weights 7, at least 13 of data, the verifier images 2) |
   | So free on `/home` before anything is built | About 55 GB | About 90 GB |
   | The same once the ladder's 23.86 GB of pinned images are in the store (they are not today) | About 80 GB | About 115 GB |
   | To free on `/home` from today's 61 GB | Nothing if the ladder's images are not yet pulled; about 20 GB if they are | About 30 GB; about 55 GB with the ladder's images |
   | On `/`, free at launch | 40 GB | 40 GB; the plan asks for 60 GB, because these tranches run for days and one low reading stops a 24-hour attempt |
   | To free on `/` from today's 48 to 50 GB | Nothing today; whatever brings it back to 40 GB if it has fallen | About 10 to 12 GB |

   *What to do:* free that space, or name another disk for Podman's image store, which would take
   the images and the scratch off `/home`. The scout's listing shows where the space on `/` went
   (319 GB under `/var/tmp`, most of it another project's); it is the owner's to judge. *Blocks:*
   the GPU tranches and Tasks 11 and 12; the CPU tranches once the ladder's images are pulled.
6. **Decide the pretrained-weights policy and the set** (M6). *Why:* the set decides which
   competitions can earn a medal, so it is part of what is measured, and it cannot change after the
   GPU class's first attempt. *What to decide:*
   - The policy. *Recommendation:* a fixed set of weights in the agent image, and no model hub on
     the allowlist.
   - The set. *Recommendation:* M6's rule and the eleven checkpoints proposed under it. The set as
     proposed holds no generative language model and no checkpoint fine-tuned for question
     answering, so `lmsys` and `chaii` may screen low for that reason alone; say whether to add
     any, and whether the owner would accept a model's terms where a checkpoint needs that.

   The exact list, with sizes, licences and digests, is committed in Task 11 and shown to the owner
   before the GPU class's freeze. *Blocks:* Task 11 and the GPU tranches; not the CPU tranches.
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
   - May the GPU be reserved for the GPU tranches? Stage one is three to four days if sessions stop
     by themselves and up to thirty if they use the limit (report §10; estimates; the eight-hour
     read of M5 stops the tranche for a report long before thirty); stage two is at most as much
     again. The owner's own GPU work would have to wait: the wrapper does not launch while another
     process holds memory on the card, and other use during an attempt is flagged in the readout
     (M5).

   *Blocks:* each tranche's smoke.
8. **The two standing confirmations, dated again for this line.** *Why:* the ladder plan requires
   them before any use of the subscription, and this line adds sessions of up to 24 hours. *What to
   confirm:* that paid extra usage is off for the account, and that the subscription's terms allow
   unattended runs of this size. *Blocks:* each tranche's freeze.
9. **Approve the line and its ceilings.** *Why:* the GPU tranches and the placement are above the
   USD 100 the coordinator may approve alone, and the line passes USD 300 in all (`AGENTS.md`,
   "Budget delegation"). *What is asked:* the [rule proposed below](#proposed-wording-for-the-agentsmd-rule):
   the screen at 39 to 78 slots, at most 90 starts and USD 200; the placement at up to six
   competitions, 90 slots, 100 starts and USD 400, starting only after the screen is reported; USD
   8 an attempt; success as any medal (M1). *One choice inside it:* at the estimate of USD 3 an
   attempt, USD 200 pays for the second three attempts of about six competitions, and the others
   with no medal in three end "not screened"; USD 250 pays for all thirteen (M9). The plan proposes
   USD 200. *What the owner should know before approving:* the screen loses about half of the
   competitions whose true rate is near 10 percent, and a placed competition is "observed in the
   band" with an interval 28 to 44 points wide (M1). *Blocks:* every paid attempt.
10. **Later, only if too few competitions are placed:** whether to end the line, or to request
    another definition of success (M1). Nothing is asked now.

**Done, and no longer an owner action: the GPU toolkit.** The owner installed the NVIDIA Container
Toolkit 1.20.2 on 2026-11-15, and rootless Podman 4.9.3 passes the GPU to a container (the
coordinator ran `podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable … nvidia-smi`,
which prints the card: an RTX 5080 with 16 GB since the check of 2026-11-25). **Operating note.** The toolkit's generated device file uses
`cdiVersion: 0.7.0` with a field `additionalGids` that Podman 4.9.3 cannot parse. `/etc/cdi/nvidia.yaml`
is therefore a copy with those blocks removed and `cdiVersion: 0.6.0`: generated as a normal user
with `nvidia-ctk cdi generate --output=<file>`, stripped, and installed by the owner with
`sudo install -m 644`. **After an NVIDIA driver update, a change of card, or any command that writes the toolkit's raw
output to `/etc/cdi/nvidia.yaml`, the copy must be rebuilt the same way,** which
is a root step for the owner then. The symptom of a raw file is `unresolvable CDI devices nvidia.com/gpu=all`. Task 11 begins with that one-line container check.

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

**Task 1: the fixture and the task wrapper** (impl_code; 9 h; report §13 gives 6 to 8 for the
wrapping).
*Files:* create `family.json` (the thirteen candidates: short name, Kaggle slug, class, resources,
the benchmark's commit, each size with its source), `wrap.py`, the fixture and its generator,
`tests/experiments/test_mle_bench_wrap.py`. *Produces:* from a prepared competition directory, the
agent image's build context, the verifier image's build context, the attempt package (its instruction
assembled as the older dataset of M4 does, less the paragraph on the format server), and the two
packages for the answers and sample-submission legs. *Tests first:* every short name is the one in
the Candidates table, at most 12 characters, and maps to one slug; the agent context holds no file
of the private directory, of the grader or of the leaderboard snapshot, by SHA-256; the attempt
package holds `task.toml` and the instruction only; `task.toml` carries the class's limits, the time
limit, the artifact, the canary line and no network key; both images are named by digest, and an
image reference without one is refused; the answers package differs from the attempt package only
by its `solution/` directory; the same input gives the same digests.
*Verify:* `pytest -q -n 4 tests/experiments/test_mle_bench_wrap.py`, and `--collect-only` on it.

**Task 2: the verifier path and the format check** (impl_code; 6 h; report §13 gives 2 for the
format check and 1 for host grading).
*Files:* create `verifier/test.sh`, `verifier/grade_submission.py`, `agent/validate_submission.py`,
`tests/experiments/test_mle_bench_verifier.py`. *Produces:* the reward file (1 or 0 and the four
graded outcomes), the test report `verifier/ctrf.json` in the form the launcher reads (M4), and the
agent-side format check of M3. The call into the benchmark's grader is one function, so the suite
tests everything around it with the fixture's grader. *Tests first:* the answers give reward 1 and
five tests passed of five; the sample submission gives reward 0 and a valid submission; a missing,
empty or malformed submission gives reward 0, not valid, and still a written reward; a submission
that is a symbolic link, a directory or another file name is not read; a score the grader does not
give is left out, never written as zero; the percentile follows the metric's direction and counts a
tie as beaten; the format check accepts the sample and refuses a missing column, a missing id and
an empty value, without reading any answer. *Verify:* the module, and `--collect-only`.

**Task 3: the withholding check on a built image** (impl_code; 4 h).
*Files:* create `withhold_check.py`, `tests/experiments/test_mle_bench_withhold.py`. *Produces:* for
an exported file system, a result per image, recorded against the image's digest: private files,
grader files and the leaderboard snapshot by SHA-256, private-only lines by count, and the
benchmark's package. *Tests first,* on directory trees standing in for an export: a planted answers
file is found by hash under another name; a file holding a share of the answers' lines is found; a
public file that shares lines with the training data is not a hit; an unreadable path fails the
check; a result names the digest it was run on. *Verify:* the module, and `--collect-only`.

**Task 4: the configuration as data** (impl_code; 7 h).
*Files:* create `make_criterion.py`, `tranches/screen-cpu/` and `tranches/screen-gpu/` (each a
`ladder.json` and a `tasks.json`, generated, plus the four links of M4), `manifests/` with one
manifest per tranche, a placeholder `weights.json`, `tests/experiments/test_mle_bench_criterion.py`.
*Produces:* each stage-one tranche's criterion from the ladder's `ladder.json` and a short file of
this family's fields, and each stage-two criterion from a stage-one export by M9's rule. *Tests
first:* every group the generator does not replace equals the ladder's, byte for byte as JSON; the
model is `claude-haiku-5-5` and the efforts are within the ladder's three; the caps, ceilings,
starts and concurrency are M9's; the screen's two class ceilings sum to USD 200 and no ceiling is
above USD 200; the free-disk floor is the ladder's 20 GB; each competition is mapped to `"ctrf"`
in the graded-outcome field; a GPU tranche's limits file names the device and its concurrency is
1; every null has a pending entry; the launcher's own socket check passes for every tranche name
and every task name under this machine's state root. For stage two, on constructed exports: the
list is the competitions with no medal in rank order, the ceiling is the class's less what stage
one committed, k follows M9's formula, a stage of one competition schedules three slots, an export
with a medal for every competition gives no stage, and the criterion differs from stage one's in
those fields only. For the manifest: it lists by hash every file of the family kit outside
`manifests/`, `tranches/` and the prose, this tranche's directory with links hashed through, and
every path the ladder's own manifest lists; two tranches' manifests differ. *Waits on nothing;* the
fields the ladder's live probe fills stay pending here until it has run. *Verify:* the module,
`--collect-only`, and `git diff --stat main -- experiments/long_horizon_tasks` prints nothing.

**Task 5: the wrapper around the launcher, and its guard tests** (impl_code; 14 h).
*Files:* create `screen.py`, `tests/experiments/test_mle_bench_screen.py`. *Produces:* `screen.py
<tranche> plan | launch | status | ruling | resume | allowance | manifest`, the launcher's and the
manifest module's commands under M4's replaced names, behind the wrapper's own refusals. *Tests
first,* against the ladder's stand-in harness and stand-in Podman on a closed `PATH`, with the
fixture as the only competition:
- *The replaced names.* A launch through the wrapper reads this tranche's criterion, this tranche's
  ledger file, this tranche's state root and this line's cache, and never the ladder's or another
  tranche's (each shown by a value that differs between the two); it reads nothing under
  `~/lh-cache/logs`; no use of a replaced name is bound when either module is loaded.
- *The ledger per tranche.* A tranche whose own ledger holds no read is held at its pilot although
  another tranche's ledger holds `Smoke read`, `Pilot read` and `Round 1 read` rows that pass; a
  `Ruling` row in another tranche's ledger lifts no stop here.
- *The launcher's refusals through the wrapper* (the ladder plan's Task 5): no authorization, a
  label that is not this tranche ledger's, a dirty or changed reviewed kit, another model, a package
  whose digest or image differs, a credential variable in the environment, a rehearsal with a spend
  variable, no allowance inputs.
- *The manifest over this kit.* An uncommitted edit to `screen.py`, a new file in the kit and a
  removed one each stop the tranche before its next start.
- *The wrapper's own refusals,* each shown to run before the launcher is entered: a tranche name
  outside the kit's list; a cache that resolves to the ladder's; an image reference with a tag or
  with no digest; a withholding result for another digest; an uncommitted change under
  `experiments/mle_bench_tasks`; the ladder's launcher lock held; the line's lock held by another
  tranche; the ladder's passthrough socket answering; free disk under the launch condition on
  either file system; a process holding GPU memory, for a GPU tranche. While this line's launcher
  runs, the ladder's unmodified launcher is refused on the ladder's state root.
- *The money and the schedule.* The ceiling and the starts cap of the tranche hold under sixty
  concurrent launches; a usage limit cuts, pauses and reruns; the schedule is one effort, three
  rounds, the smoke and the pilot first; a stage-two tranche starts with its own smoke and pilot.

*Not verified while planning:* whether the ladder's own launcher tests can run against the wrapped
module without edits; if they can, they are run as they are and the list above shrinks to what is
new. *Verify:* the module, `--collect-only`, then the ladder's five test modules unchanged, then
the sampled broad check.

**Task 6: the readout** (impl_code; 7 h).
*Files:* create `screen_readout.py`, `tests/experiments/test_mle_bench_readout.py`. *Produces:* from
the launcher's exports of a class's two stages (read through the reviewed `slot_record.py`) and
each attempt's result file, per competition: observations, medals, the scores against the
thresholds, percentile, valid and above-median counts, the screen class of M1, cost and minutes,
cuts, flags, refused connections, the packages the transcript shows installed, and the attempts
during which another process held the GPU; per calendar day, the line's priced usage; and at the
placement, the ladder's pooled label with the count and the exact 90 and 95 percent intervals.
*Tests first:* each row of M1's table, over one export and over two; a competition with no medal
in five observations is "not screened", and one the second stage did not fund says so; the score
and the percentile come from the regrade's result when the reward did; an excluded attempt is
listed and never scored zero; the screen's attempts are never pooled into a placement count; the
intervals for 1 to 5 of fifteen are M1's; a request priced after midnight is counted on the later
day; a stop readout places nothing. *Verify:* the module, and `--collect-only`.

**Task 7: the fixture on containers** (impl_code; 6 h and under an hour of machine time; report §13
gives 3 to 4; no spend, no model call).
*Files:* create `qualify.sh`; `README.md` of the kit begins here. Its setup creates `~/mle-cache/recordings`
as a directory of its own, mode 700 (M4; the wrapper refuses a launch without it). *Produces:* the fixture's two images
built with rootless Podman, and the three legs of M2 run twice and the four controls once through
Harbor 0.25.0 under the allowlist. This is where the benchmark's grader first runs inside a
verifier's container, with the pinned dependency set of M3 (so far it has run on the host only).
*Checks:*
- the six outcomes of M2, and the untouched leg's written reward of 0;
- the four controls of M2, built for the fixture, each in its expected class;
- **a local image named by digest is started without a pull,** and the same package with a tag in
  place of the digest is refused by the wrapper. If the harness cannot start a local image by
  digest, the registry on the loopback address of M4 is built and the check is repeated through it;
  the result and the form chosen go in the ledger, and no paid start is made on the other form;
- an agent image rebuilt under the same name with a planted answers file is not what the package
  starts;
- the withholding check of Task 3 passes on the real agent image, names its digest, and finds a
  planted answers file;
- a submission that is a symbolic link to the answers' path earns reward 0;
- the verifier's container has no relay.

The keys of the reward file are then held to what this run recorded. *Verify:* `qualify.sh` prints
ten lines, all as listed; the results go in the ledger.

**Task 8: the independent review** (review_code; 8 h, and 6 h of fixes and re-review).
By a reviewer who wrote none of Tasks 1 to 7. *In scope:* everything M4 lists under "What must be
reviewed again", the functions of `ladder.py` named there included: the replaced names in both
modules and whether any guard of the launcher reads the ladder's data, or another tranche's,
through the wrapper; each refusal the wrapper adds and that it runs before the launcher is entered;
the criterion generator and each replaced field, the stage-two rule included; withholding, by
construction and on the image, and the image's identity by digest; the verifier and the controls;
the readout's classes and intervals. *The brief lists the holes to look for:* an answers file, a
grader or a threshold in reach of the agent; a ceiling or a cap read from the ladder's criterion; a
read or a ruling of one tranche accepted by another; two tranches sharing a state root, a money
lock or a host-side file; a file of this kit that can change without the label changing; an image
that can change without the package changing; this line and the ladder, or two tranches, in flight
together; a tranche whose efforts or model differ from its ledger row; a missing submission scored
as an infrastructure failure, or an infrastructure failure scored as zero; the Kaggle key or the
account name in a file the kit writes. Each guard is mutated.

**Task 9: the zero-spend rehearsal** (impl_code; 6 h; no spend, no request to the vendor).
On containers, with the fixture, the real pinned CLI, the relay, and the passthrough in its rehearsal
mode against the ladder's stand-in API, as the ladder's Task 7: a session that ends normally with a
submission and is graded; one that ends at the dollar cap; one past a shortened time limit; one cut
by the stand-in's usage limit, with its slot run again; one killed and reconciled; the token
scanner's canary test; a stage-two tranche generated from the rehearsal's own export and run. It
also measures how long the export of the agent's file system into the token scan takes, against the
scan's three hours (scout report I5). *Verify:* the ladder's smoke checks on the rehearsal's records;
results in the ledger.

### Waits for the Kaggle token and the rules (owner actions 1 to 4)

**Task 10a: the download script and its review** (impl_code 3 h; review_code 2 h). It needs no
owner action and can be written with Tasks 1 to 9; it is listed here because only Task 10 uses it.
*Files:* create `fetch.sh`, `tests/experiments/test_mle_bench_fetch.py`. *Tests first,* without
Kaggle, with a stand-in download tool on a closed `PATH`: `fetch.sh` refuses without the directory
variable, refuses a directory or file of another mode, gives the download no terminal input, prints
only its fixed lines when the tool fails noisily or asks a question, and writes the tool's raw
output only inside the token's directory. *Then an independent review, before the script first
runs,* by a reviewer who did not write it: every path by which the key or the account name could
reach a pane, a log, a file outside the token's directory, a process list or an environment that a
child inherits. The script does not run on the real credential before the review's verdict is in
the ledger.

**Task 10: the three CPU-only competitions** (impl_code; 8 h; report §13 gives 2 to 3 for the first
installation and preparation and 1 to 2 for each further competition).
*Files:* fill `tranches/screen-cpu/tasks.json`. *Does:* the download and the benchmark's preparation
on the host, `leaf` first; the secret scan of M10; the two images per competition; the withholding
check, recorded against each image's digest and run with `--withheld ~/.kaggle`, so a copy of the
Kaggle credential in an image is a hit; the six runs and the four controls of M2 per
competition; a dry run of the contamination terms over those jobs, after which the terms are
frozen. `textnorm-ru` is prepared last of the three: its preparation loads about ten million rows
and needs a few GB of memory (scout report C, an estimate). *Verify:* `qualify.sh` on each;
`tasks.json` holds package digests, image digests, sizes on disk, the withholding result and the
ten outcomes; the ledger gets the surviving list and the measured sizes.

**Task 10b: the review of the real CPU packages** (review_code; 3 h). By a reviewer who wrote none
of Task 10. *Reads:* the three attempt packages as they will run (the instruction, `task.toml`, the
images by digest); the two build contexts of each; each withholding result and the digest it names,
against the digest in the package; the outcomes of the legs and the controls, and how each
control's expected class was written down; the frozen contamination terms and their dry run; the
filled `tasks.json` against the criterion. A finding stops the CPU tranches until it is fixed and
read again.

**Task 10c: a zero-spend rehearsal on one real package** (impl_code; 4 h; no spend, no request to
the vendor). On `leaf`'s real package and images, under the conditions of the ladder's rehearsals:
the container holds no credential, the session's token is a fake one, the base URL points at the
local stand-in, and the vendor is shown to be unreachable from the container before the session
starts. The real pinned CLI runs one session to its end through the wrapper in rehearsal mode; the
verifier grades whatever it left; the export, the token scan and the runtime check run as in a
smoke. *Verify:* the ladder's smoke checks on the rehearsal's records; the result in the ledger.

### Waits for disk and the weights decision (owner actions 5 and 6); the GPU itself is ready

**Task 11: the GPU path** (impl_code; 11 h; report §13 gives 6 to 10; no spend).
*Does, in this order:* the one-line container check of the operating note above; the GPU base image,
with the benchmark's own pinned deep-learning stack (PyTorch 2.2.0 with its CUDA 12.1 libraries,
which this driver covers; scout report F; PyTorch itself has not been run here); the fixture run
with a GPU tranche's limits file under the allowlist, the agent's
container seeing the card (shown on a scratch task without the allowlist: scout report D5); the
weights of M6 fetched on the host under its rule, `weights.json` filled (name, source and revision,
the SHA-256 of every file, size, licence, modality) and committed, and the set placed in one image
layer that every GPU agent image shares; each checkpoint loaded in the image, on the card, with the
offline switches set; the rehearsal of Task 9 once more on the GPU image, with the export time
measured on a container that has written several GB. *Verify:* the fixture's ten outcomes on the
GPU image; the agent's container lists the GPU; every checkpoint of `weights.json` loads; the ledger
gets the image's size and the list, which is shown to the owner before the GPU class's freeze.

**Task 12: the ten GPU competitions** (impl_code; 14 h; report §13 gives 1 to 2 each).
As Task 10, in the table's order, into `tranches/screen-gpu/tasks.json`. *Waits also on* owner
actions 1 to 4 for these ten.

**Task 12b: the review and the rehearsal of the real GPU packages** (review_code 3 h; impl_code
2 h). As Task 10b for the ten packages, and for `weights.json` against M6's rule. Then Task 10c's
rehearsal once on `patent`'s real package and image, with a GPU tranche's limits file.

### Waits for the live probe of the subscription route, and for the approval (owner actions 7 to 9)

**Task 13: the CPU tranches** (about 5 h of attention; machine time not known before the pilot).
Before the first attempt the tranche ledger of `screen-cpu` holds everything M4 lists: the
Terminal-Bench live probe's result and the approval of this line with its `AGENTS.md` rule; the
qualified competitions with package digests, image digests, withholding results and outcomes; the
verdicts of Tasks 8, 10a and 10b and the results of Tasks 9 and 10c; the owner's two confirmations,
shares, days and first reading; the hand-over row; the disk row; and the label row. Then the
freeze, the smoke and its read, the pilot and its read, the rounds, and the export. Then stage two
by M9's rule: its criterion from the export, its own ledger, label, smoke, pilot and reads.

**Task 14: the GPU tranches** (about 7 h of attention; three to four days of the GPU for stage one
by report §10's estimate). The same list, with the verdicts of Tasks 11 and 12b, each tranche on a
later calendar day than the previous tranche's last settlement.

**Task 15: the screen's report** (5 h). The readout, a report under `docs/reports/`, the priced usage
and the allowance used in the ledger, the roadmap's step table, and the placement request with
measured cost per attempt in place of this plan's estimates.

**Task 16: the placement** (about 8 h of attention and 5 h for the readout; machine time from the
screen's measurements). Its tranches are generated as in Task 4, each with its own ledger file,
label, smoke and reads; then `family.json`, frozen with roadmap step 7's set.

**Hours in all:** about 73 before any owner action (Tasks 1 to 9), about 50 for the real
competitions (Tasks 10a to 12b) and about 30 for the tranches and their reports: about 153. About
42 of them come from the review's findings: the wrapper's own refusals and their tests, the
manifest and the ledger per tranche, the second screen stage, the controls, the weights list, and
the three reviews and two rehearsals of the real packages. The roadmap's figure for step 10 (about
16 hours for the first CPU-only competition, 6 to 10 for the first on the GPU, 1 to 2 for each
further one) assumed the launcher would be reused as it is; the wrapper, its review and its
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
  While this line's launcher runs, a GPU tranche's for days, the ladder cannot launch, and the other
  way round.
- **More tranches, each with its own ledger file.** The screen is two to four tranches and the
  placement up to two, each with a ledger file on `main`, a label, a smoke, a pilot and three reads
  by a person. A stage-two tranche repeats all of that for as few as three attempts.
- **The screen's second stage may not be funded for every competition.** At the estimated cost,
  some competitions with no medal in three attempts end "not screened", and they are the
  lower-ranked ones.
- **The family is tied to its configuration:** the CLI version and its three tools, the allowlist,
  the weights list, the resource classes, the 24-hour limit and the USD 8 cap. A later comparison
  reuses all of them or qualifies again.
- **The owner is in the loop,** as for the ladder: a reading before every window, and here on whole
  days.
- **The disk is the tightest resource.** An attempt can write tens of GB, and the only guard is a
  floor that stops every attempt in flight. Another session that fills `/` ends a 24-hour attempt
  of this line; a full `/home` would stop every session on this machine.
- **Images are built here,** not pulled by a publisher's digest. A rebuilt image has another digest,
  so the package that names it changes, and with it the label; the prepared data and the answers
  must be kept, or prepared again, to rebuild one. If the harness cannot start a local image by
  digest, a registry on the loopback address becomes one more piece to keep running.
- **The weights set is frozen with the family.** A competition that needs a model outside it cannot
  be told from one the model fails at, and adding a checkpoint later is a new label and a new
  screen of the GPU class.

## Not verified while planning

**Settled by the fixture on containers (Task 7):** that Harbor 0.25.0 with podman-compose 1.6.0 runs
a locally built agent image and a locally built verifier image, each named by digest, without a
pull (the scratch task of scout report D5 built its verifier image at each trial), and which of the
store's digests such a reference must carry; if it cannot, that a registry on the loopback address
serves them by digest; that the benchmark's grader runs in
a verifier's container with the pinned dependency set; that the reference agent can write the answers
as the submission; the reward file's keys; whether a competition can be added to the benchmark's
registry for the fixture, or the fixture needs its own grader call.

**Settled by the rehearsal (Tasks 9 and 11):** that the export of an agent container with a
deep-learning stack, the weights and several GB written, image layers included, fits the token
scan's three hours (if not, the smoke stops as an incomplete scan; the 300-second limit in the
launcher is on reading a container's configuration and logs, not on the export); that a stage-two
tranche generated from an export launches and runs as M9 describes (a tranche of one competition
is never generated: M9-R1); that the process limit of 4,096 is enough for data loaders; how the CLI's Bash tool, which
refuses a standalone `sleep` (ladder D2), lets a session wait on training that runs for hours.

**Settled by the GPU path (Task 11):** that the device entry, the allowlist network mode and the
CLI's install work together in one attempt (each was run without the others: scout report D5); that
PyTorch runs on this card in a container (the driver library was exercised, PyTorch was not
installed: scout report F); the size of the GPU image and of the weights; the names, sizes and
licences of the proposed checkpoints, which are from the planner's knowledge, and whether medals on
`lmsys` and `chaii` need a model outside the set; how the wrapper tells an attempt's own processes
on the card from others.

**Settled by the owner's actions or by Kaggle:** whether Kaggle's site still issues the older
credential the pinned client needs; whether each of the thirteen competitions' rules can still be
accepted, and what the download says when they are not; what the rules and Kaggle's terms allow;
whether a credential can be expired on the site. **Settled by the first preparation (Task 10):**
whether the download and the preparation can be run as two steps, so that only the first can read
the credential; whether the preparation's checksums match under the pinned dependency set; each
competition's real size on disk and the memory its preparation needs.

**Read in source for this revision, and not run:** how the launcher reads its ledger, its
manifest, its host-side files, the free disk, the socket path and its lock, and that its export
refuses a start outside the current schedule. Tasks 5 and 9 hold each with a test. **Corrected from
the scout report:** its section G says the free-disk stop is checked before a start and not during
one; the launcher checks it about once a second and stops attempts in flight, and M9 follows the
launcher. **Not searched:** whether a package on the allowed indexes carries a candidate's labels.

**Settled only by the screen:** the cost, length and medal rate of a direct session on any
competition; how often an attempt without a medal is above the median; whether sessions end by
themselves; whether the thresholds are fair on each rebuilt test
set (report §14); what an attempt costs against the allowance when most of its hours are waiting.

**The scout report was complete when this plan was finished,** and the plan reads all of it. Its own
list of what it left unsettled is covered by the paragraphs above. Its installation of the grader
and its scratch tasks are scratch files outside the repository; Task 7 builds this kit's own.

**Not knowable by reading:** how much of a medal is recall (M7).

## Rulings

Each ruling is recorded in this form: **what is ruled, why, and what it costs if wrong.** Where a
row goes: a ruling on this plan's decisions goes in this table; a row that the launcher reads
(`Configuration label`, `Smoke read`, `Pilot read`, `Round 1 read`, and
`| <date> | Ruling | resume: … |` to lift a stop) goes in the tranche's own ledger file (M4); the
line's approvals, reviews and results go in this plan's [ledger](#ledger). The second column here
names the review finding a ruling answers and is never the word "Ruling", which is the launcher's
key in a tranche ledger.

The rows of 2026-11-15 are the coordinator's rulings on the independent review of this plan. All
its blockers and majors were accepted. The wrapper is kept, and nothing under
`experiments/long_horizon_tasks/` changes.

| Date | On | What is ruled | Why | What it costs if wrong |
| --- | --- | --- | --- | --- |
| 2026-11-15 | B1 | Each tranche has its own ledger file, `docs/plans/2026-11-15-mle-bench-ledger-<tranche>.md`, created with its first row before the tranche's first call, and the wrapper points the launcher at it. This plan's ledger keeps the line's decisions and links each file (M4) | The launcher accepts a read that names any label of the ledger it is given and matches a ruling by date and attempt id. With one ledger, an earlier tranche's reads and rulings would release a later tranche with no person reading it | A file must be on `main` before each tranche. A row put in the wrong file leaves a tranche waiting, which is safe. If the scoping failed, up to thirty attempts of 24 hours could start unread |
| 2026-11-15 | B2 | `task.toml` and `tasks.json` name each image by digest, never by tag, and the wrapper refuses an unpinned reference. Task 7 shows on the fixture that the harness starts a local image by digest without a pull; if it cannot, a registry on the loopback address serves the images by digest. No paid start is made before one of the two is shown. A withholding result is recorded against the digest the task names (M3, M4) | The launcher compares image references as strings. A tag can be rebuilt after its withholding check; a digest cannot | If neither form works, every tranche waits on an addition at function level and its review. If a reference were not content, a paid attempt could run on an image that holds the answers, and the scores would not show it |
| 2026-11-15 | M-a | A tranche's manifest covers this family's kit, the wrapper included, the tranche's directory and everything the ladder's manifest covers. The wrapper adds a clean-tree check over `experiments/mle_bench_tasks` before the launcher is entered. No function of the launcher is replaced: the wrapper sets six names in `ladder.py`, four in a private load of `manifest.py` and one environment variable, and adds seven refusals of its own. Task 8 reads the wrapper whole and the launcher's functions that read the replaced names (M4) | Pointed at a tranche's directory, the manifest covered six files and none of this family's code, and the launcher's clean check names only its own kit | A prose file of the kit changed after a launch is seen only at the next launch. Any change to the reviewed kit now moves this family's labels too |
| 2026-11-15 | M-b | This line's cache is `~/mle-cache`, with its own host-side files, packages and prepared data. The benchmark's sources stay under `~/lh-cache/mle` and are only read (M4) | In one cache each line's limits file overwrites the other's, and each launcher then stops on a changed configuration | One more directory to keep. The harness environment is a link to the ladder's, so an upgrade there reaches this line; the launcher's version check refuses it |
| 2026-11-15 | M-c | The free-disk floor is the ladder's 20 GB, as the launcher applies it: all the time, on the lower of `/` and `/home`, stopping every attempt in flight. Room above it (50 GB on `/home` with the images built, 40 GB on `/`) is a launch condition of the wrapper. Owner action 5 names both file systems. The scout report's sentence is corrected by a dated note (M9) | The first version took the floor to be checked only before a start and put the attempts' scratch inside it, which would have stopped the smoke it was meant to protect | Every figure is an estimate until the smoke. Too little room stops attempts in flight, each a start with no observation. Too much asks the owner to free space for nothing |
| 2026-11-15 | M-d | Task names of at most 12 characters, with the Kaggle slug kept as a field: `leaf`, `textnorm-ru`, `birds`, `essay2`, `patent`, `tweet`, `chaii`, `jigsaw`, `lmsys`, `whale`, `petfinder`, `kuzushiji`, `cassava` (Candidates, Task 1) | The launcher refuses a state root whose socket path passes 107 bytes; the slugs give 123 to 133 | Two names per competition to keep in step. A mix-up would grade a submission against another competition's answers, which the qualification legs would show |
| 2026-11-15 | M-e | Exclusivity is in code: for a live launch the wrapper takes the ladder's launcher lock and a lock for this whole line, and refuses while either is held or another passthrough answers. USD 200 per calendar day holds by the tranche ceilings and by a person's row that a tranche starts on a later day than the last settlement. A request is counted on the day it was priced (M5, M9) | The launcher's lock is per state root, so nothing stopped two tranches, or a tranche and the ladder, at once; and nothing in code counts a day | A paused tranche's passthrough left running when the ladder starts would put the token in two processes. A tranche started on the day another settled could put two ceilings, up to USD 400, on one day |
| 2026-11-15 | M-f | The weights set is data, fixed before any attempt is seen: chosen by M6's rule, committed as `weights.json` with sizes, licences and digests before the GPU class's freeze, and stated to be part of the task definition. It stays the owner's decision, with the recommendation. The package indexes can serve copies of the labels; the readout lists installed packages and refused connections, and the rest is an accepted limit shared with the ladder (M6, M7) | The set decides which competitions can earn a medal, and a set described in a sentence cannot be frozen or reviewed | A competition the set cannot serve screens low for a reason of ours and is dropped. A package that carries labels would make medals on that competition worthless and would not show |
| 2026-11-15 | M-g | The screen is sequential: three attempts; three medals of three is above the band; a medal otherwise survives; none of three brings three more; none of six is excluded low. The above-median clause is dropped. The placement uses the ladder's rule and count (ladder D6) and reports each placed competition as "observed in the band" with its count and exact 90 percent interval. The second three run as a stage-two tranche, because the launcher cannot add slots by outcome, funded from what stage one left of the class's ceiling. The screen stays at USD 200 (M1, M9) | Three attempts with a score clause dropped in-band competitions at a rate nobody could state. M1's table now states what the screen does at each true rate | About half of the competitions near 10 percent are still lost, and each survivor above the band costs fifteen attempts. At USD 3 an attempt USD 200 funds the second stage of about six competitions; the rest end "not screened" |
| 2026-11-15 | M-h | The evaluator check gains four synthetic controls per qualified competition, just either side of the bronze line and of the median, each graded to its expected class, with zero errors allowed. They validate the evaluator only (M2) | The three legs sit at the ends of the scale and pass under any threshold; the measure decides at the bronze line | The controls take the benchmark's lines as given. A line that is unfair on the rebuilt test set is not caught by them |
| 2026-11-15 | M-i | Before the first paid start: an independent review of `fetch.sh` before it first runs (Task 10a); a review of the real packages and their withholding results (Tasks 10b and 12b); and a zero-spend rehearsal with the real CLI on one real package of each class, under the conditions of the ladder's rehearsals (Tasks 10c and 12b) | Task 8 sees only the fixture. The script that reads the Kaggle credential and the real images would otherwise first run unreviewed, in a paid smoke | About 17 hours. Without them, a hole in a real package would cost a paid start and the tranche's label, or leak the key |
| 2026-11-15 | Minors 1 to 13 | All taken: the export is bounded by the scan's three hours, not 300 seconds; the test report's form and mapping are named; the placement's arithmetic and tail rule are stated; the guard's two-at-once limit and the load gate's effect are stated; the GPU is checked for other use; the verifier reads one regular file and a link is tested; this note on where rows go; the readout takes score and percentile from the result that gave the reward; the readout counts invalid submissions only; the proposed `AGENTS.md` wording names `screen.py` and the later-day rule; the preparation is taken to read the credential until shown otherwise; decision 16 names 16 tasks | Each corrects a fact or adds a test the review showed missing | Small: a few hours of tests, inside the tasks' estimates |
| 2026-11-23 | M9-R1 (Task 8, B1) | Only k of two or more is funded: where only k = 1 fits, stage two is not run and its competition is reported "not screened: the second stage was not funded". The generator refuses a tranche of either stage with fewer than two competitions, or fewer than two qualified once that is filled, and the wrapper refuses one with fewer than two qualified (in a rehearsal, the stand-in's list while the field is pending) (M9 rule 3) | With one competition the launcher's schedule gives the smoke and the pilot one key, `r1-<task>-medium`: the pilot never starts, the export lists the slot twice and `slot_record.load` refuses every export, so the stage could neither finish nor be read. The test that should have caught it collected slot ids into a set | A competition that one more stage-two start would have screened ends "not screened". At USD 3 an attempt the CPU class funds no stage two |

## Proposed wording for the `AGENTS.md` rule

`AGENTS.md` is the owner's file; this is wording only, to be placed after the rule for the effort
ladder when the owner approves the line (owner action 9).

> - The owner-approved MLE-bench screen and placement (DATE; roadmap owner decision 17) are one
>   calibration line for a second long-horizon task family, limited to its plan
>   (`docs/plans/2026-11-15-mle-bench-family-plan.md`, written there as a link): the 13 named
>   MLE-bench competitions,
>   each wrapped so that the held-out answers, the grader and the medal thresholds stay out of the
>   agent's container, run by a direct `claude-haiku-5-5` Claude Code session of at most 24 hours.
>   The screen is three attempts each at effort `medium`, and three more for a competition with no
>   medal in the first three as far as its class's ceiling pays for them, by resource class (the
>   three CPU-only competitions, then the ten on the GPU, one at a time): at most 78 scheduled
>   attempts and 90 starts, ceiling USD 200. The placement, which starts only after the screen is
>   reported to the owner, is fifteen fresh attempts (five each at `low`, `medium` and `high`) for at
>   most six surviving competitions: at most 90 scheduled attempts and 100 starts, ceiling USD 400,
>   in tranches of at most USD 200. At most USD 8 per attempt; one tranche runs at a time, and each
>   starts on a later calendar day than the previous tranche's last settlement, so no day passes
>   USD 200 (priced-token figures; an attempt is one whole agent session, not one API call). It is
>   spent only through `experiments/mle_bench_tasks/screen.py`, with each tranche's manifest hash,
>   runtime commit and limits recorded in that tranche's ledger file, which the plan links, before
>   its first start. A tranche may start only after the Terminal-Bench live probe has shown the
>   subscription route, each of its competitions has passed the qualification check and the
>   evaluator's controls on this machine (the answers file earns a gold medal through the verifier
>   an attempt uses; the sample submission and an untouched environment earn none; constructed
>   submissions just either side of the bronze line and of the median are graded as expected), the
>   launcher wrapper has passed an independent review and a zero-spend rehearsal, and the real
>   packages have been reviewed; and never while the effort ladder's launcher is running. Success
>   is any medal; the score and the leaderboard percentile are recorded for every attempt; a
>   competition enters the family only at 1 to 5 medals of fifteen, reported as an observed count
>   with its exact interval. It measures per-competition success and makes no claim about any
>   workflow. No other model, no top-up after a null, and another definition of success or a
>   workflow comparison needs its own approval.

## Ledger

This table keeps the line's decisions: approvals, reviews, owner actions, and each tranche's
opening and result, with a link to that tranche's ledger file. The launcher does not read it; it
reads the tranche's own file as committed on `main` (M4). No tranche ledger exists yet.

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-15 | Plan written | Against `3ac3a2e4` (`integ/20261115b`: `main` with the day's documentation pass and the ladder's 15-task configuration); `main` at `c49d43b7` merged before the final checks. Not reviewed. No spend authorized: this line has no rule in `AGENTS.md` and no approval row. Spend to date: 0. Evidence used: the feasibility report (a desk study) and the scout's fact-finding of the same day (read in source or run on this machine with no model call; not committed) |
| 2026-11-15 | Owner action done: GPU toolkit | NVIDIA Container Toolkit 1.20.2 installed by the owner; rootless Podman 4.9.3 passes the RTX 3090 to a container (coordinator's check). `/etc/cdi/nvidia.yaml` is a stripped copy at `cdiVersion: 0.6.0`, to be rebuilt after a driver update (the operating note under "Owner actions and questions") |
| 2026-11-18 | Task 1 built: the fixture and the wrapper | Commits of 2026-11-15: `01a663ec` (the fixture and its generator), `09e47e9a` (`wrap.py`, `family.json`, the instruction header), `7b11e11d` (subject: "review findings on Task 1"; short task names, digest-pinned images), `a6fb83de` ("Task 1, fix round 1"), `9dd962ed` and `8b3f250b` (tests against Task 2's files and the Candidates table), `36e30c5b` ("Task 1, fix round 2"). The subjects show a review and two fix rounds. No review verdict was recorded at the time, and none is recorded here. Branches `feat/mle-kit-join1` (as first written) and `feat/mle-bench-kit` (with the fix rounds); integrated on `integ/mle-kit` on 2026-11-18. Spend: 0 |
| 2026-11-18 | Task 2 built: the verifier path and the format check | Commits of 2026-11-15: `8be46a91` (tests first), `83bff918` (`verifier/test.sh`, `verifier/grade_submission.py`), `1275a8c8` (`agent/validate_submission.py`), `b21ce557` ("review fix round 1"), `50b668eb` ("re-review minors"). The subjects show a review, one fix round and a re-review whose minors were fixed. No review verdict was recorded at the time. Branch `feat/mle-kit-t2`; integrated on `integ/mle-kit` on 2026-11-18. Spend: 0 |
| 2026-11-18 | Task 3 built: the withholding check | Commits of 2026-11-15: `fdc3902d` (`withhold_check.py`), `dd377e14` (one public exemption, more tests), `94ea4d30` ("review round 1"), `f514b2d9` ("review round 2"). A third round (input digests without bytecode caches, as `wrap.digest`; upper-case competition ids such as `AI4Code`; exemption files with a repeated hash or a non-string reason refused; withheld digests sorted) was written in the Task 3 worktree and left uncommitted; it is `ce62a65d` on `integ/mle-kit` (2026-11-18), with the competition-id pattern narrowed to letters, digits and hyphens, which every id of the benchmark's source uses. The subjects show three review rounds. No review verdict was recorded at the time. Branch `feat/mle-kit-t3`. Spend: 0 |
| 2026-11-18 | Task 4 built: the configuration as data | Commits of 2026-11-15: `dda5109e` (`make_criterion.py`, the two stage-one tranches with their links, their manifests, the stage-two rule, the `weights.json` placeholder), `f80b7d32` (a filled `tasks.packages` that leaves a competition out is refused; more tests), `f3efde57` (stage two's size split to complexity 12). No commit subject names a review: Task 4 has no visible review, and no verdict was recorded. On `integ/mle-kit` the two manifests were rewritten by `make_criterion.py write` (`67c08e39`, 2026-11-18), because they hashed files changed since; neither manifest is frozen and no manifest hash is recorded as a label. Branch `feat/mle-kit-t4` (`feat/mle-kit-t5` merges it with `feat/mle-bench-kit` and holds no Task 5 commit). Spend: 0 |
| 2026-11-18 | Task 6 built: the readout | Commits of 2026-11-15: `66e137bb` (tests first), `726d0f03` (`screen_readout.py`), `8fb72b00` and `b029c2fa` (subject: "review of Task 2"; grader exceptions listed for a ruling, valid submissions with no score counted apart), `6ac3dadf` and `77725a60` ("readout fix round 1"), `3e509e74`, `44e5c46f` and `4cbb77c7` ("readout fix round 2", the last naming "the guards the mutation run found untested"). The subjects show two fix rounds and a mutation run. No review verdict was recorded at the time. Branch `feat/mle-kit-t6`; integrated on `integ/mle-kit` on 2026-11-18. Spend: 0 |
| 2026-11-23 | Task 5 built: the wrapper around the launcher | Commit `81d1608e` on branch `worktree-agent-aff64d547cbee5aca` from `main` at `fc3a7051` (which carries the ladder's per-round whole-file-set read of 2026-11-23): `screen.py` and `tests/experiments/test_mle_bench_screen.py` (60 tests, from the uncommitted tests-first draft of `feat/mle-kit-t5`, checked against Task 5's list and today's ladder), and the two screen manifests rewritten by `make_criterion.py write` (not frozen; no label recorded). The wrapper sets M4's names and replaces no function; it uses `make_criterion.manifest_module` for the manifest load, and writes the freeze and the check itself, because `manifest.py`'s own `write --freeze` and `check` of a frozen manifest read `ladder.json` beside `KIT`, which this kit has not. Dropped from the draft, as outside Task 5's list: refusing a tranche of one competition, flagging Harbor's failed `compose stop` warning, refusing placeholders by name, a withholding result's competition, check version and inputs, a GPU tranche's concurrency (Task 4 holds it). Not settled: a tranche of one competition schedules the smoke and the pilot as one slot id (`r1-<task>-medium` twice), which the export's slot list would carry twice (left to Task 9). The ladder's own launcher tests cannot run against the wrapped module unedited: they run `ladder.py` by its path in a copy of the ladder's kit, with its `tasks41` packages and `lh-ladder` state. `ladder.py` unchanged; its six test modules pass unchanged with this module (1,248 tests); each wrapper guard was mutated once and a test failed. Not reviewed (Task 8). Spend: 0 |
| 2026-11-23 | Task 8: the independent review and its fixes | **Verdict:** ready for Task 7; not ready for Task 9 or a paid start until B1 and S1 were fixed. 38 of 39 guard mutations were caught; the one missed (the GPU record's writer replaced by nothing) now fails a test. The coordinator accepted every finding. **B1** (blocking): a tranche of one competition scheduled one slot twice; ruling M9-R1 (Rulings), fixed in `make_criterion.py` (`_size`, `_stage_two`, `stage_one`) and `screen.py`; the criterion tests now assert the slot list, not a set, and an export of the smallest stage two loads. **S1:** nothing made `~/mle-cache/recordings`, which the launcher's round read scans: the wrapper refuses a launch while it is missing or a link, Task 7's setup creates it (M4), and a rehearsal through the wrapper reads the whole file set clean at round 1's end. **S2:** `screen_readout.py` reads `<state>/screen/gpu.jsonl` and flags each observation whose window meets a row that lists a process or could not read the card (M5); a flag excludes nothing. **S3:** a withholding result must also name the competition's slug and this checkout's `withhold_check.py`. **Nits:** a rehearsal's launch or resume takes the ladder's launcher lock (no change to `ladder.py`); the wrapper refuses `logs/` or `packages/` of the cache resolving into `~/lh-cache`; Task 10 runs the withholding check with `--withheld ~/.kaggle`. **Not judged without containers** (Task 7): a local image started by digest without a pull; the withholding check on a real export; a submission that is a symbolic link; the grader inside the verifier image; nvidia-smi's view of processes in containers; the reward file's keys. Manifests rewritten (not frozen). Spend: 0 |
| 2026-11-26 | Task 7 built: the fixture on containers | Commit `7514e308` (`qualify.sh`, `qualify.py`, `tests/experiments/test_mle_bench_qualify.py`, the kit's `README.md`; manifests rewritten, not frozen), branch `worktree-agent-adedf2767dc000bd1` from `main` at `f1c2590e`. Not reviewed. **Run:** `FIXTURE_CHECKS=1 qualify.sh tiny-tabular …` (third run; the first two are under "Did not match"), rootless Podman 4.9.3, Harbor 0.25.0 with podman-compose 1.6.0, allowlist overlay of `screen-cpu`, CPU set 8-31, one trial at a time, about 12 minutes; host load 25 to 70 from other sessions throughout. **The ten lines, all ok:** answers 1 and 2: reward 1, gold, score 1.0, percentile 100. Sample 1 and 2: reward 0, valid, score 0.5, percentile 0 (the fixture lists no floor). Untouched 1 and 2: a written reward 0, not valid, no score. Controls (lines from the grader: bronze 0.83113, median 0.806165; seed 0; 40 rows): bronze-past 23 rows replaced, 0.83586, reward 1; bronze-short 24 rows, 0.81944, reward 0, above the median; median-past 24 rows, 0.81944, reward 0, above the median; median-short 25 rows, 0.80556, reward 0, not above. Each verifier score equals the grader's outside Harbor; the percentiles are in the order of the scores; margins 0.01642 (bronze) and 0.01388 (median). **The six checks, all ok:** digest-start (every trial started both images by digest from the store, and a pull of either fails: there is no registry at `localhost`); tag-refused (`wrap.py packages` with the tag: exit 2, `unpinned_image`); rebuilt-image; withholding (pass on the agent image, 4,968 files, naming its digest; fail on the rebuilt one with `home/data/planted-answers.csv` as a `private_hash` finding); symlink (reward 0, not valid); relay (resolves in the agent's container, not in the verifier's). **Image form chosen:** the digest directly, `localhost/mle-bench/<name>@sha256:<digest>`; no loopback registry was built. **Images:** base `docker.io/library/python@sha256:61e01f72680f86a5279ad510818ab7b2ee9f049822589d4e34e33e044360356c` (python:3.11-slim, Python 3.11.18, 129,686,422 B); verifier base `@sha256:ada5c64197223669ccce5ccc62c9230a6406c1ac7fd45c603693ca22fa18a765` (562,288,814 B: the benchmark at `507f92e1` and numpy 1.26.4, pandas 2.2.2, scikit-learn 1.5.1, scipy 1.14.1, joblib 1.4.2, py7zr 0.22.0, pyppmd 1.1.1, pillow 10.4.0, appdirs, diskcache, pyyaml, tenacity, tqdm from `~/lh-cache/mle/wheels` with no index; kaggle left out, since grading never imports it); agent `@sha256:3af39a913839f4b1072ed0f761f0f428d8cf2fd1b5665405ce2f4e7827c188d8` (129,702,346 B); verifier `@sha256:faa7ac6a5f3afa28e5652cc9798bf22000e358b9df5ac86be9ef8e11d602807b` (562,326,858 B). The fixture's images were removed afterwards; the base was kept. **The reward file's keys,** as recorded and now held by `qualify.py`: with a score, `reward`, `valid_submission`, `above_median`, `medal`, `grader_exception`, `score`, `percentile` and the four thresholds; without one, the same less `score` and `percentile`. **Did not match the plan, or was not known:** (1) Harbor's default teardown runs `compose down --rmi local`, and podman-compose 1.6.0 force-removes every image named `localhost/…`: on the first run the first trial passed and removed both images, so the other nine could not start (Podman tried a pull). `qualify.sh` now passes `--ek keep_containers=true`, as the launcher's attempts do, and removes the trial's containers by name. (2) **Open, needs a ruling before Task 9:** `harbor trial regrade`, which `ladder.py` runs without that option, removed the verifier image too (run once on the fixture's answers-1 trial: regraded reward 1, image gone). With the reviewed launcher unchanged, a tranche's first regrade would remove that competition's verifier image, and every later attempt of it would fail at its verifier's start. M4's loopback registry form (`localhost:<port>/…`, which podman-compose does not count as local, and which a later start can pull again by content) may avoid it; that was not run. (3) Rebuilding an image under the same name takes the name off the original, so `<name>@<original digest>` no longer resolves and the package does not start at all (fail closed; on the second run that stopped the check). The kit must not rebuild under a name a recorded package uses. (4) Builds are not reproducible by digest: three builds of the same agent context gave three digests (`0e4c0a79…`, `369b9a84…`, `3af39a91…`). This is consistent with M3, because each result names its digest, but every rebuild needs a new withholding check and a new package. (5) The controls are built in the verifier image with no network, outside Harbor, not "on the host": the grader is the image's pinned one, not the host's `~/lh-cache/mle/venv`. (6) On the fixture, bronze-short and median-past are the same 24-row submission, because the two lines are 0.025 apart. (7) For the symlink check, the record does not show whether Harbor's upload dropped the link or the verifier refused it. (8) Reading of "ten lines": the six legs and the four controls, as Task 10's "ten outcomes"; the six fixture checks print after them only with `FIXTURE_CHECKS=1`. (9) `qualify.sh` applies no load gate: the grader is deterministic. Spend: 0; no model call, no provider CLI, no Kaggle access |
| 2026-11-15 | Independent review, and the revision after it | Review of the plan at `cf07b110` by a reviewer who wrote none of it (read-only; no provider call, no Kaggle access, no container run): accept after fixes, 2 blockers, 9 majors, 13 minors; no return to design. The coordinator accepted every blocker and major and ruled on each ([Rulings](#rulings)); the wrapper is kept and nothing under `experiments/long_horizon_tasks/` changes. This revision applies the rulings and all 13 minors. Changed figures: the screen is 39 to 78 slots and at most 90 starts at USD 200 (was 39 and 45); the line at most 168 slots and 190 starts at USD 600 (was 129 and 145); the work about 153 hours (was 111). One ruling was applied in another form than written: the screen's second three attempts cannot run inside the first tranche, because the launcher's schedule is fixed by the criterion and its export refuses a start outside it, so they run as a stage-two tranche funded from what stage one left of the class's ceiling (M9). The roadmap's step 11 still names 39 attempts and is updated with this plan. The coordinator accepted the plan for Tasks 1 to 9. Nothing paid is approved. Spend to date: 0 |
| 2026-11-25 | The GPU device file rebuilt for the RTX 5080; the container check passes (coordinator; the owner installed the file; zero spend) | **Found:** `nvidia-smi` reports one RTX 5080 with 16,303 MiB on driver 615.71.09, not the RTX 3090 of the row of 2026-11-15. `/etc/cdi/nvidia.yaml` had been replaced on 2026-11-22 18:57 by the toolkit's raw output (`cdiVersion: 0.7.0`, three `additionalGids` blocks; byte-identical to a fresh `nvidia-ctk cdi generate`), and a rootless container asking for the GPU failed with `unresolvable CDI devices nvidia.com/gpu=all`. What wrote it is not identified; the toolkit's `nvidia-cdi-refresh` units write `/var/run/cdi/nvidia.yaml`, which Podman skips. **Rebuilt** by the operating note's recipe (a fresh generation, the three blocks removed, `cdiVersion: 0.6.0`) and installed by the owner at 23:34 PST. **Check:** `podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable docker.io/library/ubuntu:24.04 nvidia-smi` prints "NVIDIA GeForce RTX 5080, 16303 MiB, 615.71.09"; `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm` and `libcuda.so.1` are present in the container. **Open, before a GPU tranche:** the per-attempt estimates and each GPU competition's feasibility were judged for 24 GB and are not rechecked against 16 GB; Task 11 still begins with the container check, since the file can be overwritten again. |
| 2026-11-26 | Task 10a: the download script built, reviewed and merged (impl_code by one implementer; review_code and a re-check by a reviewer who wrote none of it; zero spend, no Kaggle access) | **Built** (`b3eeab88`, `7dc23e76`; manifests regenerated in `2f300d7d`, `9cad787e`, not frozen; merged to `main` as `a819e351`): `fetch.sh` and `tests/experiments/test_mle_bench_fetch.py` (50 tests, written first and failing first). The script has run only against stand-in tools on a closed `PATH` with fake keys. **Review verdict:** first "ready after fixes" (one major, seven minor), then, on the revised script, **ready to run on the real credential**. No path was found by which the key or the account name reaches a pane, a file outside the token directory, the process list or a child's environment. **The major finding:** `mlebench` is not a command on this machine, so every slug would have reported "rules not accepted or download failed"; the script now runs `~/lh-cache/mle/venv/bin/python -I -m mlebench.cli prepare` and refuses when that file is missing. **Minor findings fixed:** a shell job line on the pane when the tool dies by a signal; other `KAGGLE_*` variables reaching the client; a link refusal passed by `//` or `/.`; checks made before the paths were used (a planted log link, an old log's mode, a `tmp` link); a `df` reading that is not a number; a tool that ignores TERM; two test gaps. **Left open (a nit, not blocking):** a directory planted at `fetch-<slug>.log` puts two shell error lines with that file name on the pane. **What a shell script cannot close** (reviewer, reproduced with stand-ins; the real tool at 1.6.17 does none of it): a tool that reopens the script's own output, writes to absolute paths, or starts a session of its own. **For Task 10, to rule before it starts:** (1) Task 10 runs the withholding check with `--withheld ~/.kaggle`, a directory that will not exist, because M10 puts the token under `~/.local/state/mle-secret`; `withhold_check.py` refuses a missing path, and pointing it at the token directory would have an agent read the credential, which M10 forbids. (2) M10 says the owner deletes "the file" afterwards; the whole token directory has to go, since the raw logs (which may name the account), `tmp/` and the benchmark's `cache/` are beside it. (3) The benchmark's venv is built on an interpreter under `/var/tmp/sound-analysis/`, another project's scratch space that owner action 5 speaks of clearing; rebuild the venv on an interpreter that stays before the download. (4) The script refuses a link anywhere in the token directory's path; `~/.local/state` resolves to itself today. |
