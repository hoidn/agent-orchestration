# `.orc` Effectiveness Comparison Harness

## Metadata

- **Title:** A small reusable harness for workflow-versus-single-call comparisons on the evaluated route, retirement of the apparatus that can no longer run, and two preregistered experiments
- **Status:** implemented, 2026-10-14. The harness is in `experiments/compare/` and both experiments have run: see the [E-A report](../reports/2026-10-14-orc-versus-single-call-evaluated.md), the [E-B report](../reports/2026-10-14-design-review-execute-versus-single-call.md) and the [postmortem](../reports/2026-10-14-effectiveness-experiments-postmortem.md). Decisions made during implementation are recorded in the plan's rulings appendix.
- **Kind:** operational design (experiment apparatus) with experiment preregistration
- **Owner:** experiment and evaluated-runtime maintainers
- **Reviewers:** one independent design reviewer; one code reviewer distinct from the implementer
- **Created:** 2026-10-14
- **Last material update:** 2026-10-19; generic reference-rubric calibration and the current model cap are implemented; live calibration evidence remains separate
- **Related docs / issues / plans:**
  [design lessons](../orc_workflow_design_lessons.md) (methodology authority),
  [workflows versus a single call](../reports/2026-09-28-orc-versus-single-call.md),
  [lean-pilot forensics](../reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md),
  [lean-pilot owner decision](../reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md),
  [executor retirement](workflow_lisp_executor_retirement.md),
  [CLI executable support boundary](../../specs/cli.md#executable-support-boundary),
  [capability matrix](../capability_status_matrix.md) rows for the lean-pilot apparatus and canonical trial runs;
  plan: [harness and experiments plan](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md)
- **Implementation target:** treatments are maintained `.orc` programs at admitted evaluated targets (2.35, 2.36). The harness lives under `experiments/compare/`, outside `orchestrator/`. No new target, header field, memo field, transport or spec change.

## Summary

The repository has had three generations of effectiveness apparatus, and the
heavy ones produced the least evidence. The July lean pilot's ORC arm is a
target-2.20 program the compiler now refuses, and two of its three blocks were
forfeits caused by its own protocol surface. The August ES F1 apparatus never
ran a live arm and the owner has declared the study invalid. The September
single-call study, two `.orc` programs plus a hundred lines of
machine-specific shell and hand-run blind judging, produced the only usable
result; its methodology is recorded in the design lessons, its tooling is
not reusable.

This design keeps the methodology and replaces the machinery with one small
harness: a preparation script that builds one repository per candidate from
the base commit alone, a transparent shim on `PATH` that records every
candidate's patch after every agent call, a scoring workflow in `.orc` whose
judges rate a batch of patches side by side under random ids and return typed
ratings, and a summarizer that evaluates a criterion file whose hash every
scoring run bound as an input in its `run.json`. The treatments are the maintained
workflows, referenced by path and never copied or edited: `best_of_n.orc`,
`reviewed_change.orc`, the `design_review_execute.orc` example, and a control
that is the library's `direct_task.orc` plus a time limit.

Two completed preregistrations are preserved as history. E-A replicated the September comparison on
the evaluated route with the September task, base commit, comparator and
scoring mode, so that the runtime change is the only difference. E-B measures
the class the September report says was never tested, tasks a single call
does not finish, with hidden acceptance tests as the completeness measure and
the design-review-execute shape that built the REPL as the treatment. The
lean-pilot apparatus is retired with the same move as the flat route:
evidence stays, code goes.

## Context And Authority

- [Design lessons](../orc_workflow_design_lessons.md) own the rules a valid
  comparison follows: write the criterion before seeing scores; judge blind
  with random ids; use a judge that is not the workflow's own judge;
  predeclare the paired baseline and report the comparator used; repeat anchor
  patches across batches; do not score with tests the agent can run; report
  judge agreement; run from a frozen copy of the code.
- [The September report](../reports/2026-09-28-orc-versus-single-call.md) owns
  the baseline method: every implementation call in a workflow is a single
  call with the same model, prompt and a fresh repository copy, so the
  single-call result and the workflow result come from the same run. Its base
  commit `468e7908` and task package under `experiments/orc_vs_single_call/task/`
  are in the tree and remain usable: the bug exists at that commit whatever
  `main` does later.
- [`specs/cli.md`](../../specs/cli.md#executable-support-boundary) refuses
  execution of targets through 2.34. The lean pilot's ORC treatment,
  `workflows/experiments/repository_task_pilot/task_loop.orc`, is target 2.20
  and is refused with `workflow_execution_target_retired`.
- [`specs/io.md`](../../specs/io.md) states that the evaluated route hands
  providers the absolute path of their pinned result file; a missing file
  fails the effect with `provider_result_missing` ([providers
  spec](../../specs/providers.md)).
- Before this design, the [capability matrix](../capability_status_matrix.md)
  listed the lean-pilot apparatus as "Implemented", although it could not
  execute its ORC treatment. D1 resolved this: the apparatus was removed, and
  the matrix row is now Retired.
- Owner decisions of 2026-10-14, recorded here: the lean-pilot row was removed
  from the README evidence table; the ES F1 study is invalid and is not a
  candidate comparison; the REPL-shaped workflow is a candidate treatment.

## Problem

| Apparatus | What it is | Why it cannot serve | Evidence it produced |
| --- | --- | --- | --- |
| Lean pilot (July): `orchestrator/experiments/`, `scripts/experiments/lean_pilot.py`, `scripts/experiments/conventional_coordinator.py`, `workflows/experiments/repository_task_pilot/` | 44 modules of apparatus with 13 test modules | Its ORC arm is refused by the compiler; its environment is pinned to one machine; its in-band guard brackets were the failure mode | 3 blocks; 2 forfeits; 1 real comparison, a tie on hidden acceptance decided on maintainability |
| ES F1 (August) | Apparatus deleted in the executor retirement; schemas and data under `experiments/orc_effectiveness/f1_es/` | No live arm; invalid per owner | None |
| Single-call study (September): `experiments/orc_vs_single_call/` | Two `.orc` at 2.35, four shell scripts, rubric, ratings | `harness/` has one machine's paths and variant files not in the tree; judging ran by hand per batch; the wrapper carries a result-file workaround the evaluated route made obsolete | +0.83 and +1.02 for generate-four-select-one with a stronger judge; +0.58 for review-and-revise with a stronger reviewer |

What a reader cannot do: produce a valid comparison on the current runtime
without rewriting the scaffolding, and the one positive result cannot be
repeated as it stands. The pattern across generations: control machinery
placed in the path of the treatment became the failure mode, and methodology
written as rules outlived every apparatus.

## Goals And Non-Goals

Goals:

- G1. One command per arm runs a comparison on current `main`, from a frozen
  checkout, on any machine with the provider CLIs.
- G2. Treatments are the maintained `.orc` programs, unchanged. The harness
  adds nothing to their prompts and reads nothing from their internals beyond
  the run's memo and the candidate repositories.
- G3. Scoring is blind, typed and recorded: random ids, anchors in every
  batch, judges that are not the treatment's judge or reviewer, exact
  agreement reported.
- G4. The success criterion is a file whose hash every scoring run binds as
  an input, recorded in its `run.json` before any rating exists, and the
  summarizer evaluates it mechanically.
- G5. Apparatus that cannot run on the current runtime is retired, with its
  evidence kept.

Non-goals:

- General effectiveness claims. Each experiment reports one task class.
- A trial SDK, run-ref, or any E-series revival. The harness is two command-line
  scripts with their helper modules, two shims and two `.orc` files.
- Token or cost metering beyond call counts and wall clock.
- Parallel candidates. `list/map-effect` runs serially; target 2.37 parallel
  maps are registered, not admitted for this work.
- Reviving or porting `task_loop.orc`.
- Preventing a determined agent from finding a published solution. The
  harness removes the obvious routes and detects the rest (D5).

## Decision

<a id="original-delivery-metadata"></a>

The original apparatus deletion decision is completed history; preserved evidence remains immutable. See the [preserved record](../reports/documentation-history/orc_effectiveness_comparison_harness-history.md#original-delivery-metadata).

- **D2. One harness under `experiments/compare/`.** `prepare.py` with
  its helper modules `repos.py`, `scan.py` and `pool.py`,
  `shim/claude` and `shim/codex`, `score.orc` with `score.providers.json`
  and `providers/score_codex.json`,
  `control/direct_task.orc` (the control, see D3; its module is
  `control/direct_task`, so it sits under `control/` and compiles with the
  harness directory as source root) with `control/direct_task.providers.json`,
  `providers/design_review_execute.json`, `summarize.py`,
  `criterion.template.json`, the frozen criteria under `criteria/`, the task
  packages under `tasks/`, `README.md` (the operator contract). Task packages
  are tracked there so the frozen runtime is a plain checkout of a recorded
  commit; the test paths and the closed-program corpus roots exclude them.
  Size: every Python module at most 500 lines and every function at most
  cyclomatic complexity 12 (the repository rule; the earlier estimate of 500
  lines of Python in total is not a constraint), under 40 lines of shell,
  under 80 lines of `.orc`.
- **D3. The paired baseline comes from the same run where the treatment's
  first call is an implementation.** For `best_of_n` every candidate is a
  single call and the first candidate is the paired baseline; the group mean
  is the September comparator and is reported too. For `reviewed_change` the
  first implementer call is the baseline. For `design_review_execute` the
  first call drafts a design, so its baseline is a separate control run: the
  library's `direct_task.orc` with one difference, a `:timeout-sec` equal to
  the treatment's executor time limit, so neither arm has more time than the
  other. The control copy lives in the harness under `control/`; a test
  asserts it differs from the library file by that one line. The control uses the same provider
  binding, model and effort as the treatment's executor. The comparator of
  every arm is named in the criterion file and reported.
- **D4. Scoring is typed, criterion-selected, in applied-patch clones.**
  The default `score.orc` and the historical batch shapes below remain supported.
  Generic pools select `score_ref.orc` or reference-free `score_absolute.orc`
  through a rubric mapping. Both retain the four 0–2 component Rating shape
  (`completeness`, `correctness`, `scope`, `layering`), total 0–8. The
  prospective absolute rubric scores them independently: correctness earns no
  credit when no required behavior is implemented; missing behavior does not automatically zero scope
  or layering. There is no global-zero rule. The reference rubric binds an
  upstream reference outside the blind clone list. All repositories, including
  the unscored reference, count toward the ten-repository limit. A historical
  missing or descriptive-string rubric selects `score.orc`; a mapping selects
  an explicit workflow. Structural V1 quality admission still rejects the
  reference rubric. The following original default-rubric recipes retain their
  captured two-anchor scope.
  Batches are built by `prepare.py` under random ids with the mapping written
  to the pool's records directory, never an ancestor of the clones, and never reveal which patches belong together: for
  `best_of_n` a batch is one run's four independent candidates, one of the
  six single-call control patches (it looks like a fifth independent
  candidate, and the September second clause is then compared within the
  batch's own scale), plus the two anchors (D6), seven clones; for
  `reviewed_change` the twelve patches are
  split into two batches of one patch per run, the stage of each drawn at
  random, plus the anchors, eight clones each, and a run whose first and
  final patch are identical (approved in round one) is pooled once with its
  rating copied; for E-B a batch is every final patch of both arms plus the
  anchors, at most ten clones. Each judge receives a batch's clone paths in a
  random order and returns one `Rating` per clone in that order. Ratings
  join to clones by position; the `clone` field the judge copies back is a
  cross-check only, and `summarize.py` refuses a batch whose list length or
  any copied-back id disagrees with the positions. Scores are an enumeration
  `S0 S1 S2`, so an out-of-range value fails the effect. This is the
  September mode (several patches rated against each other, anchors
  repeated, no stage or grouping visible) with the September rubric, now
  typed and replayable.
- **D5. Tasks come from this repository's commits with tests.** The base is
  the parent commit, the task text paraphrases the change without quoting the
  commit, and the hidden acceptance set is the commit's test node ids that
  fail at the base and pass at the commit. The task text names every public
  entry those tests call, so an agent that solves the task can match the
  names. Each candidate repository is built from the base commit alone
  (`git init`, a depth-one fetch of that commit, no other refs, no remote),
  so no later commit is readable inside it. Files the task needs inside the
  repository, such as a bug report or a reproduction, live in the package's
  `seed/` directory; `prepare.py` commits them onto the base in every
  candidate, and that seeded commit is the base for patches and anchors, so
  seed files never appear in a diff and cannot mark a candidate. The repository is public and the
  agents are unrestricted: the solution exists on GitHub and in the frozen
  runtime checkout on the same machine. After every run the harness scans the
  shims' stdout and stderr, the Claude CLI's per-project session files for
  the agents' tree and the codex rollouts started in it for: the main
  checkout's path prefix, matched unbounded so sibling worktrees, which also
  hold solutions, count; the frozen checkout; the records root and the
  records layout (a run's state lies in its working directory, so no records
  path is legitimate); another run's tree name; other sessions' transcripts
  and tmux sockets (`.claude/projects`, `.codex/sessions`, `.codex/history`,
  `claude-tmux-sockets`); `github.com`, `gh ` and
  `git fetch`; the solution commit's hash; and, in the Claude sessions, an
  assistant message answered by a Fable model (model policy, below).
  A path also matches when written under `~`, `$HOME` or `${HOME}`; a bare
  path fragment does not, to limit benign hits from file contents. The scan
  records every hit with its file, line and context and decides nothing:
  the experimenter reads a run's hits and records a verdict, `contaminated`
  or `cleared`, with a reason. `pool` refuses an unscanned run and a run with
  hits and no verdict, and excludes contaminated runs; the report lists every
  hit, verdict and reason. Judges are scanned and adjudicated the same way
  (§Flow of one run). The positive mount boundary excludes host checkouts,
  records and peer sessions. Its writable own-tree state and private native
  home remain readable; network activity and model usage still require recorded
  action/receipt audits. Historical records without private-home lineage retain
  their original shared-home interpretation. Whether the
  commits must postdate the models' training data, and from which date, is
  the owner's call (Q5).
- **D6. The frozen criterion distinguishes task difficulty from evaluator controls.**
  Natural task-difficulty calibration selects `purpose: "calibration"`,
  `calibration_kind: "task_difficulty"`, `anchors: []`, a reference-free rubric,
  declared arms and exact per-arm counts. The same direct-task workflow generates
  fresh solutions under frozen weak/strong model bindings. Ordinary blind pools
  contain only those natural outputs; no artificial control or reference enters.
  Summarization requires every declared run and valid judge observation before
  applying the primary arm-mean gap. The selected
  [task-difficulty plan](../plans/2026-10-22-functional-calibration-plan.md)
  owns the models, threshold and budget. A missing observation cannot become a
  passing smaller sample. This route does not reinterpret historical controls
  or qualify structural V1/V2 and campaigns automatically.

  A criterion can select `score_functional.orc`, `score_functional::score`,
  `criteria: [quality]`, `reference: null` for one functional score S0–S8 and a
  reason per clone. The score reflects required behavior that actually works
  through normal entry points; scaffolding, code volume and organization earn
  no independent points. Concrete regressions count against functional quality.
  Only this exact single-field selector admits values through eight; historical
  component selectors retain S0–S2, and mixed quality/component selectors refuse.
  Existing clone-id joins and complete-denominator checks remain authoritative.
  This scale does not reinterpret or numerically continue historical additive
  scores, and implementation alone does not establish evaluator qualification.

  Evaluator control checks instead select
  `calibration: {"rule": "control-means-v1", "margin": 1, "error_rate": 0}`
  and exactly three blind roles per task: upstream, stub and mutant. For each
  task and each declared judge, take each control's mean over every declared
  batch and require `mean(upstream) − max(mean(stub), mean(mutant)) ≥ 1`.
  Every judge must pass; missing, excluded or invalid observations fail rather
  than shrink the denominator. Partial order and spread are not acceptance
  gates for this rule; report spread descriptively. One point is a frozen
  prospective choice, not an estimated error probability or reliability claim.

  For control checks, absence of `calibration.rule` preserves the historical algorithm exactly:
  four declared roles upstream/stub/partial/mutant, P1 upstream−stub ≥margin,
  P2 stub < partial < upstream, P3 upstream−mutant ≥mutant_margin, the declared
  failing-pair error rate and anchor spread gate. Unknown rules refuse. New-rule
  batches contain exactly their three declared controls; extra package anchor
  files do not add roles. Historical pools without a rule retain every package
  anchor. Pool selection does not relax package construction
  or family-qualification gates. A selected reference is unscored and counts toward
  capacity. The mapping binds reference/rubric/control identities and the
  criterion hash; scoring inputs/results must agree with those identities and
  the criterion-selected rule. Later pools use the same selected rule; historical `calibration_over` retains its spread gate,
  whereas `control-means-v1` keeps spread descriptive and requires each pool
  to pass its own control-means check. Frozen AT failure is not reinterpreted.
  Fresh rubric/source identities and fresh responses are required before any
  live qualification under the new rule; the
  [simple evaluation plan](../plans/2026-10-22-simple-evaluation-plan.md)
  selects offline changes only, with implementation verification tracked there.
  Calibration summarization skips fresh hidden-test execution and leaves clone
  `hidden`/`hidden_failed` null. Retained construction fractions are secondary
  diagnostics; A/B2 produce no new filler hidden rates. Other purposes retain
  their existing hidden measurement. The current control construction and its
  disclosed pre-judge amendment live in the
  [measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md).

  **Historical/default two-anchor recipe.** The upstream commit's diff
  without its tests, and a fixed patch written by the experimenter that
  silences the symptom without fixing the cause. Both enter every batch under
  random ids with no scores in the prompt. Each judge's anchor scores are
  reported per batch; drift between batches and a low score for the real fix
  are visible in the report instead of assumed away. Where the task has no
  upstream fix of record (E-A), the first anchor is one single call made
  outside every arm, a drift reference. Each criterion freezes the anchors'
  roles (`anchor_roles`) and what their scores may be used for
  (`anchor_use`).
- **D7. The E-B treatment is `workflows/examples/design_review_execute.orc`
  unchanged.** It is already task-agnostic: its prompts read the documents and
  code the task names, and it takes `task`, `planner_model` and
  `reviewer_model`. `experiments/orc_repl_feature/repl_feature.orc` is that
  shape with prompts that name the REPL's documents; its run of 2026-10-13 is
  the existence proof that the shape completes a real feature, not evidence
  of a gain. The reading list goes in the task text, which both arms receive,
  so it is not a confound.
- **D8. E-B patches are stripped of design artifacts before scoring.** The
  treatment writes `docs/design/<slug>.md` and `artifacts/design/`; a judge
  seeing those paths would know the arm. `prepare.py` removes those paths from
  every pooled patch, baseline and treatment alike, and records the removal in
  the mapping.

## Design Details

### Layout

```
experiments/compare/
  README.md                 operator contract: layout, recipe, measures
  prepare.py                command line: run, collect, scan, pool, verify-pool
  repos.py, scan.py, pool.py  candidate builds and patches; contamination scan; blind pool and its check
  sandbox.py                positive mounts, concrete dependency declarations and private native homes
  shim/claude, shim/codex   transparent wrappers; record prompt, stdout, stderr, patches per call
  score.orc                 blind side-by-side ratings per batch
  score.providers.json      judge binding (Claude); providers/score_codex.json for an OpenAI judge
  control/direct_task.orc   the control: library direct_task plus :timeout-sec (source root: this directory)
  control/direct_task.providers.json, providers/design_review_execute.json   arm bindings
  summarize.py              results.json, agreement, anchor scores, criterion verdict, markdown table
  criterion.template.json   fields to freeze before scoring
  criteria/<experiment>.json  frozen criteria
  tasks/<package>/          task.txt, intent.txt, base_commit, seed/, anchors/, optional hidden_tests.txt and hidden/
tests/experiments/test_compare_harness.py
tests/experiments/test_compare_pool_summarize.py
tests/test_workflow_evaluated_compare_score.py
```

A run's files are split between a records directory and an agents' tree
under the work root (paths in
[`experiments/compare/README.md`](../../experiments/compare/README.md)): the
records directory holds the command, the inputs, the call records, the
collected patches and the log; the agents' tree, under a random name, holds
the candidates and the run's `TMPDIR` (its `/tmp` inside the sandbox), so
nothing an agent works in names the arm, the run or the records. The
fixed-arm state uses the runtime's default, `.orchestrate/runs/`, under the
run's working directory. Custom arms can use an external state root through
the exact result delivery below; native cwd remains inside the unit tree.
`best_of_n` uses another owned-tree location: its
workspace is the tree while its implementers work in `cand-k` and resolve
the workspace-relative result path there, so its state goes to
`<tree>/.orchestrate/best-of-n-runs/` (`--state-dir`) and every candidate's
own `.orchestrate/` (ignored by the task bases, never in a patch) holds the
link `best-of-n-runs -> ../../.orchestrate/best-of-n-runs`, so the path
resolves from either; an agent's own runs in `cand-k` keep
`cand-k/.orchestrate/runs/`. A known limit: an agent that deletes its
candidate's `.orchestrate/` loses the link. A pool holds the clones, one working
directory per judge under a random name with the judge's state directory and
`tmp/` inside it, and a records directory with the mapping, the patches and
the judges' call records.
Only the pool's `clones/` is mode 0311 (traversable, not listable; judges
receive absolute paths): the runtime opens every ancestor of a workspace or
state directory with `O_RDONLY`, so no ancestor of an agents' tree or a judge
directory can be unlistable on the controller. Native processes see synthetic
ancestors and exact grants, rather than the controller's host directories. The work
root and the frozen runtime lie outside the main checkout's path prefix, and
the runtime outside the work root; work roots and pools do not lie under
`/tmp` or `/dev/shm`, which the sandbox replaces; `prepare.py` refuses
otherwise.

### Flow of one run

1. `prepare.py run --task <package> --arm <name> --root <work root> --runtime <frozen checkout>`
   builds `cand-<k>/` in a new agents' tree from the package's
   `base_commit` alone, commits the package's `seed/` files onto it in every
   candidate, writes the arm's `inputs.json` in the run's records directory,
   installs the shim directory first on `PATH` for the run, sets `TMPDIR` to
   the tree's `tmp/`, and writes the `orchestrator run` command, run with
   `python -P` from the frozen runtime checkout and no `--state-dir` except
   for `best_of_n` (§Layout), and its resume script, which resumes from the same working directory; both use the
   working directory the arm requires (§Contracts).
2. The run executes the maintained workflow. On every agent call the shim
   writes, in the run's records directory, `calls/<n>/{prompt.txt,stdout.txt,stderr.txt,patch-cand-<k>.diff}`;
   each diff is taken through a temporary copy of the index, after
   `git add -A -N .`, so new files are included and the agent's own index is
   never changed. Until `50bb27be` the shim reset the real index after each
   call, which unstaged files an agent had staged (E-A report, Limits).
3. `prepare.py collect` reads the run's `memo.jsonl`, pairs provider effects
   with call directories one to one, and copies every patch the arm's
   comparator needs into the run's `collected/`: all candidates for `best_of_n`,
   first and final for `reviewed_change`, the final patch for
   `design_review_execute` and for the control. A failed run is recorded
   with its reason and no patch.
4. `prepare.py scan` runs the contamination scan of D5 over the run and
   records its hits; the experimenter records a verdict for a run with hits.
5. `prepare.py pool` takes the frozen criterion and the judges, builds one
   applied-patch clone per pooled patch under a random id, with `git add -A -N .` so a judge's `git diff` shows new files,
   strips the paths in D8, adds the criterion-selected anchors to each batch, writes the
   batches as one scoring inputs file and command per judge, and writes
   `mapping.json` to the pool's records directory.
6. Run the criterion-selected scoring workflow (`score.orc` by default) once
   per judge, one judge after another, behind the shims, from the judge's own working directory
   with its state directory inside it, with the batches, the intent, the
   judge model and `criterion_sha256` as inputs. Judges receive read-only grants to their exact clones,
   so `prepare.py verify-pool` runs before each judge and after the last:
   every clone's diff must equal its pooled patch, and a clone that differs
   is restored and reported. A judge's provider failure (missing or invalid
   result) is an instrument failure, not a datum: the judge is resumed with
   its resume script and the same state directory, never re-run, and the
   report lists the failure. Each judge is then scanned and adjudicated like
   a run.
7. `summarize.py --pool <pool> --criterion <criterion.json>` reads each
   scoring run's `run.json` bound inputs and memo, refuses unless every
   scoring run bound the file's current hash, joins ratings to clones by
   position, refuses any batch whose list length or copied-back clone id
   disagrees with the positions, refuses a criterion whose `judges` differ
   from the pool's and a judge that is unscanned or has hits and no verdict,
   leaves out and lists a judge adjudicated contaminated, and writes the
   table, the agreement counts, the anchor scores and the verdict.

### The shim

Named after the agent CLI it replaces, the shim records arguments, prompt,
streams and patches, and invokes the compare-owned empty-root builder. One
concrete declaration supplies read-only OS/tool dependencies, explicit PATH and
required environment names. Named executable/installation discovery does not
grant PATH directories. Native processes receive their own writable tree,
persistent private home at `/home/compare`, private `/tmp` and minimal device,
process and IPC namespaces. Judges additionally receive exactly their finalized
batch/reference clone paths read-only, with optional Git locks disabled.

The controller prepares required private credential files once in writable
mode-0600 storage, outside candidates and public captures. Native atomic refreshes
survive resume; launching never recopies host credentials. Minimal public config,
the native-version catalog and declared public tmux resources replace ambient
host config, plugins, hooks, memory and startup files. `COMPARE_SANDBOX` stays
controller-private; native HOME, PATH, model policy and credential environment
are launcher-controlled. Host roots, peer homes and controller/pool records are
absent. Tightening a mixed-provider unit to no-Claude requires an idle unit with
no active or concurrent launches, a caller-owned precondition. A permanent
controller marker prevents subsequent launches/resumes from reopening Claude;
it does not revoke an active native process. Network and uninstrumented direct
APIs remain separate audit limits.

Owned-tree result writes retain their normal missing/invalid and atomic-write
semantics. For a prepared external state root, the builder pins the authorized
parent and mounts a fresh private staging directory at its exact guest pathname.
The real controller parent and its siblings stay absent. After native exit it
publishes only a regular `result.json`, with no repair, through fixed descriptors
and exclusive atomic publication into an unchanged parent and absent target.
Missing output remains missing; malformed or empty output stays byte-identical.
Native exit is retained even when publication fails. External delivery keeps a
pending call marker until publication or legitimate absence completes; a settled
marker is an apparatus refusal in collection and scanning, never an adjudicable
natural failure. An external result destination never grants an external cwd.

Each unit records `sandbox: {home, home_path, declaration}`. Native cwd remains
unremapped; scanners and metering use `home`, the durable backing, rather than
the guest `home_path`. New incomplete/inconsistent lineage refuses, while
historical records keep their original home semantics. The same builder serves
agents and judges; the concrete mounts and remaining limits are in the
[`harness README`](../../experiments/compare/README.md).

### `score.orc`

```lisp
(defenum Score S0 S1 S2)
(defrecord Rating
  (clone String)   ; copied back by the judge; cross-check only
  (root_cause Score) (scope Score) (generality Score) (layering Score)
  (reason String))
(defrecord Batch (clones List[String]))
(defprompt rate-batch (:fills (intent :text) (clones :value List[String]))
  -> List[Rating] "...")
(defworkflow score
  ((batches List[Batch]) (intent String) (criterion_sha256 String)
   (judge_model String))
  -> List[List[Rating]]
  (list/map-effect ((batch batches)) :max 24
    (provider-result providers.judge
      :prompt (rate-batch :intent intent :clones batch.clones)
      :model judge_model :effort "high" :timeout-sec 3600)))
```

This shape compiles at target 2.35 (probe recorded in the plan). The rubric
is the September rubric (`experiments/orc_vs_single_call/evaluation/rubric.md`):
root cause fixed, no validation weakened and nothing outside scope, holds
beyond the reported case, sits in the owning layer and reuses mechanisms. The
judge reads each clone's uncommitted changes and the code around them,
changes nothing, may not run tests, and compares the clones with each other.
`criterion_sha256` is a workflow input, so the run binds it in `run.json`
(`bound_inputs`, [`specs/state.md`](../../specs/state.md)) before any
effect runs; the summarizer reads it there. The memo holds the ratings.

### Completeness for E-B

For tasks a single call may not finish, judge scores alone cannot separate
"a better partial" from "done". `summarize.py` runs each node id listed in the
package's `hidden_tests.txt`, alone, in a copy of each applied-patch clone
without `.git` with the package's `hidden/` test files copied over it, with
the interpreter given by `--python`, `PYTHONPATH` set to the copy (the
editable install points elsewhere), `-p no:cacheprovider` and a time limit
per node id, and reports the pass fraction next to the judge score.
The criterion names which measure is primary.

### Experiment Model Policy

**Current policy.** Experiment roles default to the owner's Sonnet/Terra cap.
The owner-selected functional calibration binds exact `gpt-5.6-luna` high and
`gpt-6.1-sol` low coders, with `gpt-6.1-sol` high judges, and forbids Claude and
native delegation. That exception is scoped to the selected protocol, not a
general increase or spend approval. The generic guard retains
`claude-sonnet-5-5` for legacy callers, defaults Codex to Terra, and admits exact
Luna or Sol 6.1 only through an explicit per-run binding. Fable, other higher
models and unknown IDs refuse.
Both guarded CLI names enforce the cap; Claude native agents are pinned to Sonnet,
Codex native multiagent features and independent model-dispatch routes refuse.
Actual forbidden Claude/Codex session metadata produces non-clearable scan hits.
The [current guard guide](../../experiments/compare/README.md#recipe) owns exact
flags, inherited settings and prevention limits. This cap does not itself
qualify a task family, calibrate a model pair or approve spend. Historical
criteria/workflows keep their bytes and refuse new guarded launches when their
models violate the cap.

The following dated policy and mechanics are a historical record superseded for
new launches by that cap; they preserve the original experiment chronology.

**Historical model policy (owner, 2026-10-15).** No new experiment call uses a Fable
model: no workflow arm, control, review, judge or delegated agent. Claude
planning uses `claude-opus-5-5`. Frozen historical criteria, such as E-B's, keep
the models they recorded.

Agents share `$HOME`, where the user's Claude settings select Fable. So the shims
put a model guard first on the sandboxed agent's `PATH`. Every `claude` started
through `PATH`, top-level or nested, runs through it. It refuses a Fable
`--model` or `--fallback-model`, and adds `--model claude-opus-5-5` when no
`--model` is given. Parallel calls in one tree never write over or replace a guard
in use. A missing guard is created by hard link. An edited one is restored by
rename on the next call. The shims also set `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5` and
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` in the sandbox. Under the CLI's documented
contract ([run every subagent on one model](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model), Claude Code 2.1.257 or later;
2.1.301 is installed), these pin in-process subagents, teammates and workflow
agents to Opus, and they leave the main model unchanged. The D5 scan also reads
each Claude session's answering model, from the `message.model` metadata only,
never from printed text. A Fable answer is a hit that cannot be cleared, and it
excludes the run or judge. The guard and the variables prevent the ordinary
paths. The following bypass prevention; the scan is a backstop only when they leave a Claude session under the tree (a direct API call without one is invisible):
- an absolute path to the real CLI;
- a reset `PATH`;
- an environment that deliberately drops the variables;
- an older CLI;
- a direct API call.

Sessions with a literal sandbox `/tmp` working directory are not attributed to a
run. Earlier runs had no guard: nested Fable probes ran in Task 8 and E-B2 (see
their reports).

**Evaluation policy (owner, 2026-10-15).** Hidden acceptance is descriptive
secondary evidence only; it does not decide the primary claim or its validity.
The owner selected the existing blind quality rubric for E-B3. Its
[judge-primary criterion](../../experiments/compare/criteria/eb3-judge-primary.json)
supersedes the original hidden-primary criterion; historical frozen criteria
remain records of their original decisions.

<a id="experiments"></a>

Completed E-A/E-B preregistrations retain their original task/model/budget and scientific claim limits. Results belong to the linked reports; this is not permission to rerun either study. See the [preserved record](../reports/documentation-history/orc_effectiveness_comparison_harness-history.md#experiments).

## Contracts And Interfaces

- `prepare.py run` arguments: `--task` (a package under
  `experiments/compare/tasks/` with `task.txt`, `intent.txt`, `base_commit`,
  `seed/`, `anchors/`, and optionally `hidden_tests.txt` with `hidden/`), `--arm`
  (`best_of_n`, `reviewed_change`, `design_review_execute`, `direct_task`),
  `--candidates N`, `--root`, `--runtime` (the frozen checkout), and
  `--set NAME=VALUE` for the other typed inputs. It writes `inputs.json` matching the arm's typed
  inputs: `best_of_n` takes `task`, `intent`, `repos`; `reviewed_change` takes
  `task`, `intent`, `repo`; `design_review_execute` takes `task`,
  `planner_model`, `reviewer_model`; `direct_task` takes `task`, `model`,
  `effort`.
- Working directory per arm: `best_of_n` runs from the agents' tree with absolute
  `repos`; `reviewed_change`, `design_review_execute` and `direct_task` run
  from inside their single candidate, because their implement prompts have no
  repository fill and the agent edits where it starts; `repo` for
  `reviewed_change` is that candidate's absolute path. The command runs
  `python -P` with `PYTHONPATH` naming the frozen runtime checkout in every
  arm, so a candidate's own `orchestrator/` cannot shadow it, and `TMPDIR` is
  the tree's `tmp/`, because task texts may name it.
- Shim environment: `COMPARE_ROOT` (the run's records directory),
  `COMPARE_TREE` (the agents' tree), `COMPARE_BASE` (the seeded commit). The
  `COMPARE_SANDBOX` names its prepared concrete declaration. Native execution
  receives only required named environment values and launcher-owned HOME,
  PATH, model policy and prepared credential projection; bookkeeping,
  `PYTHONPATH`, `OLDPWD`, host startup and socket variables are excluded.
- `criterion.json`: `experiment`, `task`, `base_commit`, `arms`, `comparator`
  per arm, `primary` and `secondary` measures with thresholds, `judges`,
  `runs_per_arm`, `anchors` by name, `written_before_scoring: true`. Its
  SHA-256 is the `criterion_sha256` input of every scoring run. Each
  experiment's criterion is frozen as a file under
  `experiments/compare/criteria/` and adds `claims` (the entries each claim
  needs), `verdict_rules`, run floors as `primary` entries on `<arm>.runs`,
  `exclusions`, `anchor_roles`, `anchor_use` and `judge_rules`.
  `summarize.py` evaluates the `primary` and `secondary` entries
  mechanically; the other fields bind how the report reads them. Measure
  names are listed in `experiments/compare/README.md`.
- `results.json`: per run and arm, every pooled patch's ratings per judge and
  criterion, anchor ratings per batch, hidden-acceptance fraction where
  applicable, call count, wall clock, scan hits and verdicts, exclusions of runs and
  judges with reasons,
  agreement counts, verdict.

## Dependencies And Sequencing

Needs current `main`, the provider bindings the treatments already use
(`claude_unrestricted_workspace`, `codex_unrestricted_workspace`, `codex`),
a judge binding per chosen judge family (`score.providers.json` for Claude;
`providers/score_codex.json` for OpenAI, because a judge's directory is not a
git repository; no Google judge, since the `gemini` CLI is absent and its
template has no model binding),
access to the models named above, tmux, and bubblewrap (`bwrap`) for the
agents' sandbox (R35). Sequence: the E-B task's hidden
set check, then the harness and D1 in parallel, then E-A. E-B's design and
criterion do not depend on E-A's results, so E-B may run while E-A runs, from
the same frozen runtime path (one path for the scan pattern) with its own
work root.

## Invariants And Failure Modes

- Treatments are byte-identical to their maintained files; the harness
  references them by path, and the control differs from the library file by
  its time-limit line only. A test asserts both.
- Judges never see arm, stage, run or model; `mapping.json` lives in the
  pool's records directory, never an ancestor of the clones, and is read only
  by `summarize.py` and `verify-pool`; a judge reading it is caught by its
  scan (D5); design artifacts are stripped (D8); a clone a judge changed is
  restored before the next judge (`verify-pool`).
- Every scoring run binds the criterion hash as an input in its `run.json`;
  the summarizer refuses to evaluate when any bound hash differs from the
  file's, and refuses any batch whose ratings do not line up with its clones, a
  criterion whose judges differ from the pool's, and an unscanned or
  unadjudicated judge; a judge adjudicated contaminated is left out and
  listed.
- A run whose effect fails (`provider_result_missing`, an invalid result,
  timeout, non-zero exit) counts as a failed run of its arm, reported with
  its reason, and is never relaunched or replaced. A stop on provider
  infrastructure (rate limit, authentication, CLI crash before agent output)
  is resumed with the same working directory and state instead. Runs are
  never excluded to improve a mean; the only exclusion is a run adjudicated
  contaminated under D5, listed with its hits and reason.
- A result path that cannot resolve through its owned tree or exact prepared
  external delivery is a harness defect, not an outcome. A publication marker
  rejects intake even when native usage is complete. So is an environment shared
  across runs or sessions (`/tmp`, `/dev/shm`, tmux servers, the process
  list). Runs made under either are discarded and rerun (§Experiments).
- A judge's provider failure (missing or invalid result) is an instrument
  failure, not a datum: the judge is resumed, never re-run, and the report
  lists the failure.
- A missing patch file for a call that should have produced one marks the run
  invalid; the cause (shim not first on `PATH`, provider environment not
  inheriting `PATH`) is a harness defect, not an outcome.
- An out-of-range score fails the scoring effect through the enumeration. No
  parsing of judge prose.

## Security, Operations, And Performance

Unrestricted-workspace providers work in candidate repositories in an
agents' tree apart from the records (§Layout), under the shims' sandbox
(§The shim), with no remote and no history past the base commit; they run
with a minimal private projection of required credentials and network access.
The filesystem boundary prevents ambient host reads; D5 also audits native
actions and usage. Runs use a detached worktree of the recorded commit so
edits to `main` cannot leak in (design lesson 5), outside the main checkout's
path prefix and outside the work root. `list/map-effect` is
serial: four candidates take four times one call. Judge calls read one batch
each.

## Evidence And Implementation Boundaries

Evidence for a claim in the README is: the criterion file and its hash
bound in every scoring run's `run.json`, the pool with ratings, `results.json`, every
run's `memo.jsonl` and attempt directories, the scan results, and the report
under `docs/reports/`. The harness is not part of the runtime contract;
nothing under `specs/` changes. The design-lessons document is updated only
with measured columns after a report exists.

## Compatibility And Migration

- D1 removes modules nothing else imports. The matrix and index entries that
  route to the pilot become retired routes that say the apparatus was
  removed and where its evidence is.
- `experiments/orc_vs_single_call/harness/` stays as the September report's
  provenance; the report links it. It is not used by the new harness.
- Nothing in `experiments/orc_vs_single_call/workflows/` or
  `workflows/examples/` changes.

## Verification Strategy

- Unit tests for `prepare.py` and `summarize.py` on temporary git
  repositories: candidate built from the base commit alone with no other refs,
  patches include new files, seed files committed and absent from diffs,
  mapping blind, D8 stripping, batch composition per D4, position join with
  refusal on a wrong list length or a disagreeing copied-back id, agreement
  arithmetic, criterion hash refusal, hidden-acceptance fraction with
  `PYTHONPATH` at the clone.
- A consumer test for `score.orc` with deterministic providers in a new test
  module: compile, run, interrupted and completed resume, one `Rating` per
  clone per batch in the memo, `criterion_sha256` among the run's bound
  inputs in `run.json`, an out-of-range value in the deterministic result
  fails the effect.
- A test that the harness control differs from
  `workflows/library/control/direct_task.orc` by the time-limit line only.
- Provider-free end to end, the orchestrator smoke required by `AGENTS.md`:
  stand-in `claude` and `codex` scripts on `PATH` that write fixed results
  and make a fixed edit including a new file; every arm runs through the shim,
  `reviewed_change` through its request-changes branch, one run killed at a
  commit boundary and resumed with the call count compared; a stand-in judge
  scores a pool; `summarize.py` produces a verdict.
- Live: one run per arm on the chosen task before any batch; its memo, call
  directories and patches are inspected by hand. When the inspection finds no
  harness defect and the runtime commit stays the same, these runs are the
  first run of their arm in the batch; when a defect forces a runtime change,
  they are discarded before the batch and reported as smoke.

## Declarative Acceptance / Integration Scenarios

- S1. Every arm with stand-in agents through the shim: call directories pair
  one to one with the memo's provider effects; every patch contains the
  stand-in's new file; `reviewed_change` reaches its request-changes branch;
  a killed `best_of_n` run resumes with no repeated call.
- S2. Pool one `best_of_n` run and one `reviewed_change` run with the two
  anchors, score with a stand-in judge: batches composed per D4, one `Rating`
  per clone per batch in the memo, joined by position; no arm, stage or
  design-artifact path in anything a judge receives (scoring inputs, clone
  ids, clones); the clones directory cannot be listed. A stand-in judge that returns
  one rating too few, or a copied-back id that disagrees with its position:
  the summarizer refuses that batch and names it.
- S3. A scoring run whose bound `criterion_sha256` differs from the file's
  hash: the summarizer refuses and names both hashes.
- S4. A stand-in agent that writes no result file: the run fails with
  `provider_result_missing`; `results.json` lists a failed run with that
  reason; no mean is computed from it.
- S5. After D1: `task_loop.orc` and `orchestrator/experiments/` do not exist;
  the test suite collects; the matrix row reads Retired and links the
  evidence.

## Success Criteria

- Harness: S1 to S5 pass; the provider-free end to end runs in under five
  minutes; one live run per arm completes on the chosen task.
- E-A and E-B: the predeclared criteria are evaluated and reported whatever
  the outcome; the report states the comparator, the judges, the anchor
  scores, the agreement, the scan results and the exclusions. A README row
  changes only after the report exists.

## Stop / Revise Criteria

- The shim cannot see candidate repositories under a provider binding: revise
  D4's capture to a snapshot step in a harness-owned wrapper workflow rather
  than editing treatments; record the deviation.
- More than one run of a task adjudicated contaminated: change the task, or
  move the task source to a repository that is not the runtime's own; the
  runs are reported as excluded.
- Qualification for E-B fails on two tasks in a row: the class may not exist
  at this size; report that and stop E-B.
- A judge family has no working binding: the owner picks another (Q3); no
  harness change.

## Documentation Impact

- `docs/capability_status_matrix.md`: lean-pilot row to Retired with the
  removal commit; one new row for the comparison harness.
- `docs/index.md` and `docs/design/README.md`: one entry each for this design
  and the plan; pilot entries say the apparatus was removed.
- `README.md` evidence table: rows for E-A and E-B after their reports exist.
- `docs/orc_workflow_design_lessons.md`: measured columns updated after the
  reports; the rules table gains nothing unless an experiment teaches a new
  rule.

<a id="implementation-handoff"></a>
<a id="open-questions"></a>

Historical handoff and owner questions, resolved by the linked implementation plan rulings and experiment reports. They do not select a new study or spend. See the [preserved record](../reports/documentation-history/orc_effectiveness_comparison_harness-history.md#implementation-handoff).
