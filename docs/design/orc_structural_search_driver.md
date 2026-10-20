# ORC Structural Search Driver

## Metadata

- **Status:** research apparatus design; roadmap Phases 0 and 1 selected
  2026-10-18 ([live plan](../plans/2026-10-18-orc-structural-search-live-phase1-plan.md));
  not copy-safe. Partial: the offline apparatus
  (`experiments/orc_structural_search/`), mode 1 and mode 2 with I1 and I2
  episodes, is implemented and tested with scripted providers only
  ([Phase 2 plan](../plans/2026-10-18-orc-structural-search-phase2-plan.md));
  live Phase 1 ran on 2026-10-18 and 2026-10-19 and did not select Phase 2
  for family (a) ([Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md));
  a live Phase 2 needs a new owner selection and budget approval; I3 is not implemented. Fixed-workflow comparisons use
  [`experiments/compare/`](../../experiments/compare/README.md) today.
- **Kind:** experiment-side apparatus contract: controller modes, proposal
  interfaces, edit validation and transactions, candidate identities,
  evaluation route, records and controls for searching over `.orc`
  orchestration programs. It refines
  [Experiment O](orc_reuse_introspection_search_experiment.md#experiment-o--program-space-then-search)
  into something executable and schedules no work.
- **Authority:** the [research charter](../plans/2026-09-08-orc-research-charter.md),
  [Experiment O](orc_reuse_introspection_search_experiment.md#experiment-o--program-space-then-search),
  [Conditional Task 6](../plans/2026-09-08-orc-research-demonstration-plan.md#conditional-task-6--test-search-and-representation-value),
  the [program-search boundary invariants](workflow_lisp_program_search_boundaries.md)
  (binding, as amended 2026-10-18 for invariants 1 and 6; the amendment's
  rationale is below), the [design lessons](../orc_workflow_design_lessons.md) and the
  [normal-session boundary](orc_reuse_introspection_search_experiment.md#normal-agent-sessions-and-evaluation-boundary).
- **Companion:** [source-site inspection](workflow_lisp_source_site_inspection.md)
  owns the read-only site manifest over a successful compilation. This
  design owns what acts on it: mutable scope, validation, transactions,
  snapshots and identities.
- **Compatibility:** no runtime, spec, target or memo change; candidates are
  ordinary admitted 2.39 programs run through public `compile`/`run`/`resume`
  ([CLI boundary](../../specs/cli.md#executable-support-boundary)).
- **Selection:** the [structural search roadmap](../plans/2026-10-18-orc-structural-search-roadmap.md).
- **Inherited experiment rules:** no Fable model in any experiment call;
  task difficulty calibrated before treatment runs; missing receipts are
  unavailable evidence, never zero.

## Summary And Scope

The driver is a thin Python controller. It hands a shimmed coding-agent
session a bounded editing job, validates the final diff against the declared
mutable scope and frozen surfaces, compiles the result with the ordinary
compiler into an immutable child snapshot, evaluates the child through
public runs, and records everything. ORC owns compilation and execution; the
evaluator owns task truth; the controller owns selection, lineage and
accounting. No optimizer vocabulary enters `orchestrator/`. Out of scope:
the manifest (companion), fragment archives and crossover, any new runtime
route, a general optimizer framework, dashboards.

## Decision And Alternatives

Catalog enumeration and unguided sampling come first; a sequential adaptive
loop follows only on that evidence. An external engine such as GEPA is
reused only if it accepts a completed agent episode as the proposal and
whole-run evidence as the score. Rejected: restoring the retired `trial`
executor and `TrialRunOptions` (the `trial` subcommand refuses with
`workflow_execution_target_retired`); `run-ref` provider children (public
confined children are command-only: `refuse_confined_run_ref_sites` in
`orchestrator/workflow_lisp/closed/artifact.py`); in-language `eval` or hot
swap (invariant 1); a population database before a query needs one.

## Architecture

| Responsibility | Lives in | Notes |
| --- | --- | --- |
| Driver | `experiments/orc_structural_search/driver.py`; `run_mode1` in `.../mode1.py` | Mode 1 (catalog enumeration, unguided I1 episodes), the episode function I1 and I2 share (`run_episode`: workspace, envelope, child judging), evaluation launches under the call cap, the archive and its tamper check, scans, the mode 1 readout; mode 2 parent and site selection live in `adaptive.py` |
| Candidates | `.../candidates.py` | Candidate identity, snapshots, compilation with the runtime's orchestrator, frozen-surface validation and the one-site transaction |
| Sites | `.../sites.py` | The candidate's source-site manifest, eligible sites, seeded site selection, the site brief and receipt derivation from the child's final files |
| Adaptive loop | `.../adaptive.py`, `.../judging.py` | Mode 2: archive, generations, parent and site selection, finalist validation (`validate_finalists`); per-generation blind judging, scan-verdict waits and the judge retry (`judging.judge_generation`) |
| Scoring | `.../scoring.py`, `.../scoring_phase2.py` | Blind pools, the join of judge scores to evaluation records, primary values, the Phase 1 and Phase 2 readouts |
| Evaluation | `.../evaluation.py` | Fresh clones, public `run`/`resume`, public check operation, final evaluator |
| Metering | `.../metering.py` | Consumption receipts (not yet wired into the driver's log) |
| Records | `.../records.py` | One append-only JSONL log, skeleton hashing, provider allocation, final-choice rule |
| Experiment configuration | `.../config.json` per study | Mutable scope (files and definitions an agent may change), frozen surfaces, condition, interface, envelopes, task splits, criterion hash |
| Manifest | `orchestrator/workflow_lisp/...` (companion) | Read-only site facts; it indexes what the configuration names mutable |

There is no separate mutation module; combine modules while small. The comparison harness (`experiments/compare/`:
`prepare.py`, `repos.py`, `scan.py`, `pool.py`, `shim/`) is reused by import
or subprocess; changes it needs land there with their own tests.

Required harness extension, landing in `experiments/compare/`:

| Change | Why |
| --- | --- |
| An arm spec resolved against a candidate root (source, entry workflow, source root, providers file, typed inputs) instead of the runtime checkout's arm table | A candidate's `.orc` lives in its own immutable root; compile needs `--source-root <candidate root>` and a module path matching the file |
| A generic-command arm: a recorded command run behind the shims with the same inputs and collection | The Python and agent-skill controls |
| Scan patterns for the candidate archive, lineage and score records, holdout roots and other candidates' trees | The contamination channels under Evaluation Hygiene |

## Mutator Sessions

Only shimmed CLIs exist: `experiments/compare/shim/claude`, `shim/codex` and
`shim/model-guard` record every call, run it under bubblewrap and refuse any
Fable model. An OMP session gets none of that, so mutator and arm sessions
are restricted to the shimmed Claude and Codex CLIs; an OMP shim with the
same recording, sandbox and guard is a prerequisite before OMP is used.
Within that restriction the session is ordinary (configured tools, project
instructions, skills, context management, LSP). An interface narrows the edit
scope validation accepts, never the agent's facilities; `--no-tools`,
compiler-only feedback or a source-only prompt is a disclosed ablation.

## Proposal Interfaces

| Id | Interface | Agent receives | Agent returns | Validation |
| --- | --- | --- | --- | --- |
| I1 | Whole-file rewrite | Candidate workspace, objective, mutable scope, frozen surfaces, development feedback | Edited mutable files | Frozen-surface validation over parsed forms, then full ordinary compilation; no manifest needed |
| I2 | Locus plus fragment | As I1 plus one manifest site record: span, enclosing definition, result type, bindings in scope with types, dependencies, inferred effects and restrictions | One replacement expression at that site plus declared fresh helpers | The one-site transaction below, then full ordinary compilation |
| I3 | Matched Python diff | The idiomatic typed Python workflow sharing provider adapters, frozen prompts, evaluator, splits, tools and budgets | A textual diff | AST-level scope validation over the allowed functions plus a real type checker named in the criterion; same check operation and evaluator. Precedent: the [paired specimen](../plans/2026-09-29-mlevolve-orc-python-comparison.md) |
| I4 | Named certified transforms | A menu of rewrites (wrap in bounded retry, insert review stage, delete stage, move escalation) | A choice and parameters | Deferred to compositional work; listed so I1–I3 results are read against it |

A proposal is one completed episode: inputs are the parent snapshot,
objective, mutable scope, interface payload and development feedback;
the envelope is finite wall clock and, where metered, cost, with compile,
test and repair iterations inside it; the output is the final diff plus the agent's hypothesis; for I2 the
controller derives the one-site receipt from the diff, and for I1 and I3
the record is the diff with its frozen-surface or scope verdict.
Outcomes: `accepted` (compiled child), `rejected` (refusal code or
diagnostics class recorded; no task evaluation), `exhausted`, `incident`.

## Edit Validation And Transactions

**Mutable scope.** The experiment configuration names the files and
definitions an agent may change and the condition (topology-only,
prompt-only, provider-only, joint). Everything else is a frozen surface.

**Condition surfaces (as implemented in
`experiments/orc_structural_search/candidates.py`, `_condition_verdict` and
`validate_frozen_surfaces`).** Exported entry signatures are frozen under every
condition.

| Condition | May change |
| --- | --- |
| topology-only | Shape of mutable definitions, including which provider extern a call names; every `:model`/`:effort` value must already occur in the parent module; prompt bodies, `defprompt` signatures and the providers file are frozen |
| prompt-only | `defprompt` template bodies only |
| provider-only | `:model`/`:effort` values in mutable definitions, and the providers file (permitted without listing it in `mutable_files`) |
| joint | The union of the above plus `defprompt` signatures |

**Open decisions before Phase 1 comparisons.** Two gaps in these surfaces are
recorded, not resolved: under topology-only a call may pass new literal text
to a `:text` prompt fill, which changes what the provider reads while prompt
bodies are frozen; and under provider-only the whole expression after
`:model` or `:effort` is masked as a tuning value, so a non-literal
expression there (a conditional, a call) passes as tuning although it is
topology. Each needs a ruling, and the validation to match, before condition
comparisons are read.

**Frozen-surface validation (I1 and I2).** Parse parent and child with the
ordinary reader and compare forms, not text: imports; `deftype`,
`defrecord`, `defunion` and `defenum` declarations; exported entry
signatures; the command boundary file; prompt bodies and provider extern
files unless the condition permits them. Any difference outside the mutable
scope refuses the proposal; comments and formatting are not compared.
Positions are matched by re-reading parent and child with the ordinary
reader; the controller never splices bytes by span offset, since CRLF and
multi-byte UTF-8 misalign character offsets against raw bytes. The
child then compiles through the ordinary full pipeline, which establishes
static admissibility only.

**One-site transaction (I2).** The receipt is derived from the final diff:

```json
{"parent_candidate_id": "...", "site_id": "workflow:m::run@m.orc:41:7",
 "expected_file_digest": "sha256:...", "replacement_expression": "<one form>",
 "supporting_declarations": ["<fresh helper forms>"], "condition": "topology-only",
 "hypothesis": "Use the stronger model only after a failed check."}
```

Preconditions and their refusal codes, proposed here and owned by the
experiment, not the compiler: `digest_mismatch` (the edited file is not the
inspected parent file); `site_unlocatable` (no form starts at the site's
`path:line:col` in the parent); `scope_exceeded` (after parsing, anything
other than the site subtree and the declared helpers differs; whitespace
never fires it); `declaration_collision` (a helper name already resolves in
the parent, imports included); `slot_type_changed` (after compilation the
replacement's inferred result type is not identical, by canonical type
identity, to the parent site's); `condition_mismatch` (the receipt's
condition is not the configuration's); `unreadable_child` (the ordinary
reader rejects a child `.orc` file or receipt text); plus the frozen-surface
rule, refused as `frozen_surface_changed`. When the child's manifest
reports no type at the replacement's start (for example a literal
replacement), the driver refuses with `slot_type_unavailable`
(`slot_refusal` in `experiments/orc_structural_search/acceptance.py`), since
the slot check cannot be made. Any child (I1 or I2) whose planned maximum
of provider calls is unbounded (a provider call under a non-literal
`:max`, or a recursion reaching one; `ledger.max_provider_calls`) is
refused as `unbounded_calls`, so it never reaches an evaluation. Declared helpers obey the condition as a
change from an empty form of their kind (`_definition_verdict` and
`_condition_verdict` in `candidates.py`): a new helper `defprompt` adds a
prompt signature, so it is accepted only under joint; a non-prompt helper
is a topology change, accepted under topology-only and joint; under
topology-only its `:model`/`:effort` values must already occur in the
parent module. Lifted
helpers take explicit parameters; adding one never changes an existing
binding. Edits preserve comments and unrelated text.

## Candidate Snapshots And Identities

An accepted child is an immutable directory holding the candidate source
files, imported dependency digests, entry, provider and prompt extern files
and the command boundary file. The parent is never modified.

| Identity | Definition |
| --- | --- |
| `candidate_id` | Content address over candidate source bytes, imported dependency digests, entry, provider/prompt extern files, command boundary file and orchestrator commit; parent, hypothesis, timestamps and scores excluded |
| `program_digest`, `build_key` | Read from the build's `manifest.json` after ordinary compilation |
| `site_id` | Owner canonical name plus the form's `path:line:col` start, no ordinal; valid for one candidate only |
| Runtime site / invocation | The existing execution identity (owner, label path, activation and loop ordinals); never a fragment identity |
| `episode_id` | One agent session: parent, interface, site, condition, envelope |
| `evaluation_id` | Candidate, task, evaluator version, environment manifest digest, provider settings and model revisions, replicate |
| Lineage record | Parent, child, edited sites, interface, receipt |

Model revisions belong to the evaluation identity, since a hosted alias can
change under an unchanged candidate. Equal `candidate_id` means the same
candidate however it was produced. An archived candidate lives under its
`candidate_id`; before each episode and evaluation the driver recomputes the
id and refuses a candidate whose content no longer matches its directory name
(archive tamper check).

Verified at `90ae778c` (2026-10-18) on `workflows/examples/plan_review_execute.orc`:
a comment-only change leaves `program_digest` unchanged and changes
`build_key`; a `let*` rename changes `program_digest`; a literal change
changes `program_digest`. So `program_digest` deduplicates formatting
variants and detects renames, and the skeleton hash, not the digest,
separates a rename from a structural change.

## Search Modes

**Mode 1: catalog, enumeration and unguided sampling.** The finite authored
catalog of whole policies is enumerated on matched tasks. Then equal-budget
unguided proposals: I1 episodes against a fixed seed with no feedback beyond
the task description and development checks, no archive, no site selection.
Outputs: whether structurally distinct candidates show meaningful
quality/cost differences, acceptance and repair rates, skeleton diversity.
Neither the manifest nor I2 is required. Where the three-arm compile-only
readout runs before the manifest exists, the locus arm's site facts come
from the REPL (`:info` and `:source`; `:type` only for an expression that
typechecks in module context), and the readout states which sites carried
no type.

**Mode 2: adaptive loop.** Enabled only after mode 1 shows distinct
candidates with distinct outcomes.

```python
archive = evaluated_seeds_and_catalog()
while experiment_envelope_remains():
    parent = select_parent(archive)              # uniform, or failure/cost weighted
    site = select_site(manifest(parent), policy) # uniform first; feedback-targeted as a condition
    episode = agent_episode(parent, site, interface, feedback(parent))
    child = validate_snapshot_compile(parent, episode.receipt)
    if child.accepted:
        evidence = evaluate(child, adaptive_tasks)
        archive = retain(archive, child, evidence)
    log(parent, site, interface, episode, child, evidence)
```

The archive is the non-dominated set on quality and metered deployed cost
(the objective below), an incumbent plus a small set (four to eight after
cost calibration): a child enters when no member dominates it and evicts
the members it dominates. Provider calls stand in for the cost axis only
under a condition that freezes model and effort. Parent and site selection
start uniform; local-feedback targeting is a compared condition. I2
proposals need the manifest; I1 proposals use frozen-surface validation
alone.

As implemented (`experiments/orc_structural_search/adaptive.py`,
`run_mode2`): an archive entry carries per-task primary values and
provider calls of its counted evaluations; the archive is the incumbent
plus at most `ARCHIVE_SIZE` (6) members non-dominated on (mean value
higher, mean calls lower), ranked by mean value, then fewer calls, then the
earlier id. Mean calls is the cost axis there, admissible only while model
and effort are frozen (topology-only, prompt-only); under any other
condition the axis is metered cost at the frozen price table (Metering And
Consumption), and a child without it is not placed on the frontier.
Generation 0 seeds it from Phase 1's joined rows
(`scoring readout --joined-out`) as prior evidence, logs a `reference` row
naming the incumbent and re-measures the incumbent on every adaptive task.
Each later generation alternates I1 and I2 episodes, draws parents
uniformly (`random.Random(run_seed)`) and I2 sites uniformly from the
parent's eligible sites, gives the parent's own judged means, outcomes,
terminal variants, calls and wall clock as feedback, evaluates fresh
accepted children once per adaptive task and offers each fully valued
child to the archive (`retain`); `E/archive/gen-<n>.json` records the
archive after each generation. Judging is per generation and task
(`judging.judge_generation`): one blind pool under a pools root outside
the evidence and work roots (and holding neither), every judge's ledger
entry reserved before any judge runs, and one `judging` log row per pool.
Scan hits without a verdict make the run wait for the operator's verdict
(before pooling and before summarizing), never stop it; a judge that fails
is resumed once, and a second failure is a logged judge incident after
which the next generation runs. A generation whose planned episode,
evaluation and judge calls would exceed the call cap is refused before its
episodes, and again before its evaluations. The validation task is a
holdout root of every episode and adaptive evaluation scan.
`validate_finalists` evaluates the top two archive entries, the reference
and `direct` on the validation task.

**Skeleton diversity (both modes).** LLM mutation chains over a Lisp-like
DSL converge to a few recurring forms with mostly terminal variation
(Gurkan, Stonedahl and Wilensky, "Mutation Without Variation",
[arXiv 2606.05408](https://arxiv.org/abs/2606.05408); cited, not
reproduced here); that result used a
whole-program interface, and whether I2 avoids the collapse is an early
question. For every accepted candidate the records module reads the mutable
definitions from authored source with the ordinary reader, never from the
closed program, so site labels, call frames and the `sites` table never
enter the hash. Each binder and every reference to it receive the same
scope-ordinal placeholder (`let*` names, parameters and authored labels
alike); prompt names, literals and provider bindings become kind markers;
form heads and arity are kept; the canonical S-expression is hashed (I3: a
normalized Python AST). A pure rename or a prompt-only change therefore
hashes equal to its parent by construction (a named `defprompt` contributes
nothing); provider allocation is reported separately and is not part of the
skeleton: each episode record holds the provider externs each non-prompt
mutable definition names, in source order, for the parent and the accepted
child, and the readout counts `allocation_distinct` children (the parent's
skeleton with another allocation). The terminal-only share counts a child
only when both its skeleton and its allocation equal the parent's. Reported: distinct skeletons
per accepted candidate, revisit rate, terminal-only share. Stop rule,
predeclared: if the share of accepted children whose skeleton equals the
parent's exceeds the threshold (default 0.75) for an interface, that
interface has collapsed to renames and literals; the adaptive claim is not
tested on it, and the run is reported as collapsed.

## Execution Contract

Each evaluation is one ordinary public run of the accepted child in a fresh
task clone:

```sh
python -m orchestrator run <candidate entry .orc> [frontend flags] \
  --input-file <evaluation inputs> --state-dir <work root>/runs/<evaluation_id>
```

- `--state-dir` outside the clone is a stated deviation from the
  harness's in-clone `.orchestrate/runs/` placement, kept so run records
  survive clone teardown; the harness's work-root, pool and frozen-runtime
  layout rules are inherited unchanged.
- Two roots, neither inside the other (`check_roots` in
  `experiments/orc_structural_search/driver.py` refuses nesting): the
  sandbox-visible work root holds run state, records, clones, environment
  manifests and episode copies; the evidence root, never shown to an agent,
  holds `log.jsonl`, `calls.json`, the `candidates/` archive, mode 2's
  `archive/gen-<n>.json` files and `readout.json`. Mode 2's judging pools
  sit under a third root outside both (`check_pools_root` in
  `adaptive.py`): judges must not see the archive or the log, and agents
  must not find the pools at a known place.
- The solution hash the contamination scan needs is operator-supplied per
  task (`--solution TASK=HASH`), never stored in a task package, which sits
  in the runtime agents can read.
- `evaluate` in `experiments/orc_structural_search/evaluation.py` requires a
  wall-clock limit; at expiry the launcher's process group is killed and the
  run is an incident. Known limit: agent-turn providers start their own
  session and escape that process-group kill.
- A provider quota message in a launch's shim call records (the 2026-10-18
  live Phase 1 incident: the Claude session limit ended 16 of 20 evaluations
  and all 6 episodes) makes an unfinished launch a quota incident, not a
  failure; the driver pauses new launches until the named reset and
  relaunches the job as a new attempt whose evaluation id covers the attempt
  number, and `--continue` reruns a run's quota incidents into its existing
  roots (`experiments/orc_structural_search/quota.py`, README "Quota guard");
  mode 2 has no quota guard for episodes, and each `evaluate_all` starts an
  unpaused guard (README "Not implemented").
- The clone is the working directory, so the workspace lock, guard and build
  cache land in its `.orchestrate/`. The lock admits one active run per
  working directory (`orchestrator/run_lock.py`), so concurrent evaluations
  use separate clones; sequential evaluation is the first configuration.
- No run registry or parent/child linkage exists for external runs; the
  logged run id and state dir are the join key, and "child evaluation" is a
  lineage fact in the log, not a `run-ref` child, C2 adapter, `eval` or hot
  swap. `resume RUN_ID --state-dir ...` continues the same pinned evaluation
  after an incident under the same `evaluation_id`, never as a replicate.
  Cross-candidate provider or effect reuse is disabled initially.
- Run records (`run.json`, memo, attempt files) are the evidence; `report`
  output and summaries are views. Task code comes from pinned revisions and
  dependencies from a recorded environment manifest whose digest is in the
  evaluation identity; a Git clone does not clone the conda environment.
- Evaluator truth and hidden fixtures live outside every tree an agent can
  reach, under the harness layout rules, with hidden files copied onto a
  `.git`-less copy only at scoring. The boundary is the layout plus the
  contamination scan, never an instruction not to read a file.
- For an ordinary attempt (`ORCHESTRATOR_WORKSPACE_ROOT` unset) the
  comparison shims (`experiments/compare/shim/claude`) strip its
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and
  `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY` from the agent and its tool
  processes. Incident of 2026-10-18: the task repository is the orchestrator
  itself, whose own code and tests read these variables, so an agent running
  the task's tests overwrote its attempt's result file; the prompt's
  `- path:` line names the result file relative to the agent's working
  directory. A launch-workspace attempt keeps all three variables, because
  its prompt tells the agent to use them; there the overwrite risk remains
  and is disclosed, not prevented.

## Task Family And Evaluator

R2 task qualification remains its own selection and a prerequisite; this
design absorbs none of it. One family is chosen before candidate work and
not swapped to escape an unfavorable result. No uncalibrated experiment: no
live experiment spends provider calls on quality evaluation unless its
quality measure passed a predeclared calibration on known controls (for a
judge measure, the upstream anchor strictly above the stub for every judge
and batch by a predeclared margin, with the tolerated error rate stated in
the criterion) and its family is qualified under the frozen
difficulty-calibration rule; an experiment whose measure is uncalibrated
reports only measure-free figures (compile-only metrics, execution outcomes,
cost) and makes no quality comparison, frontier or improvement claim.

| Family | Truth | State |
| --- | --- | --- |
| (a) Review/planning improvement on the harness task packages | Blind side-by-side judge `score.orc` under a criterion frozen and hashed before scoring; judge-primary rubric; hidden acceptance descriptive only | Usable now; expensive per evaluation; few calibrated rungs |
| (b) Hard-oracle repair seeded by `examples/demo_task_linear_classifier_port/` with `orchestrator/demo/evaluators/linear_classifier.py` | Deterministic behavioral checks plus a soft quality report | Needs a verified green baseline before defect variants are authored; evaluation cost unknown until then |

Experiment O's catalog
`workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc` is
at a retired target and must be ported to 2.39 or replaced by an authored
2.39 catalog before mode 1 can enumerate it. Selection rule: planning,
review and escalation choices must be able to matter; truth must be
independent; the family is qualified on development cases before searching,
and a family every seed solves or every seed fails is uninformative. Family
(a) applies the harness calibration rule
([Task 8](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md#task-8-task-difficulty-calibration));
family (b) qualification shows the oracle accepting two structurally
different correct submissions and rejecting a broken one.

**Public check operation.** Candidates branch on real development failures
through one command boundary, `dev-check`, declared under the
[command adapter contract](workflow_command_adapter_contract.md): it applies
the submitted patch to a fresh checkout at the pinned task revision, runs the
task package's agent-visible checks, and returns a typed report (passed,
failing check names, bounded output excerpt). The first version
(`experiments/orc_structural_search/seeds/dev_check.py`) runs the checks in
the working clone rather than a fresh checkout; `dev_check.py` and its
`dev-check.json` (argv and timeout) sit at the clone root. Its argv, timeout and report
type are frozen across conditions; invocations count against the task
envelope; it never sees hidden checks. The final evaluator runs hidden checks
or the blind judge separately; those results are unavailable to executing
candidates and to the mutator.

## Objective, Selection And Local Observations

The objective is Pareto over two values per candidate: quality, the mean
task success the family's frozen criterion names, and deployed compute
cost, the metered cost of executing the candidate on a task (Metering And
Consumption), both under a fixed per-task execution envelope (wall clock,
provider calls, metered cost). Better means dominance: A dominates B when
A's quality is not lower and its cost not higher and one is strictly
better, each beyond a predeclared equivalence tolerance on means (quality
in the criterion's units, cost relative). A timeout, invalid submission or
task failure is an outcome whose consumption still counts. Failure rule
(criteria amended 2026-10-18; `primary_value` and `scored_outcome` in
`experiments/orc_structural_search/scoring.py`): a failed evaluation and an
envelope timeout (an incident killed at its wall-clock envelope) score 0
rubric points; every other incident is excluded, not scored zero. The
frontier, the non-dominated set, is the object of search: it is retained
and reported and never collapsed into a scalar reward. Frontier membership
requires a predeclared quality floor (above the stub anchor's mean, or a
failure rate at or below a stated bound), so trivially cheap failures never
populate it. Pareto selection does not repair a weak quality measure: where
the measure does not resolve candidates, cost decides alone and search
drifts toward doing less, so the calibrated-evaluator gate stays a
precondition of any adaptive claim.

The authored reference seed is always evaluated on the validation split
beside the finalists, and its runs are budgeted with them, so every finalist
is compared with the incumbent on the same tasks. Deployment takes one
frontier point by a rule written into the criterion before adaptive work:
among frontier candidates under a stated mean-cost ceiling, those whose
validation success is within a stated equivalence tolerance of the highest,
then lower mean cost, then fewer provider calls, then the earlier candidate
id; only under a condition that freezes model and effort may the ceiling be
in provider calls and wall clock, and the criterion says so. Deployed cost
defines the frontier. Search cost (episodes, compiler and repair work,
evaluations, retries, rejected proposals, preparation, substantive human
assistance) is reported apart from it:
`break_even_uses = additional_search_cost / saving_per_deployed_use`, valid
only when quality is comparable and savings positive.

Local observations live outside authored programs, keyed by candidate, site,
task, evaluator version and the runtime invocation when reached:

| Kind | Example | May drive |
| --- | --- | --- |
| Output assessment | A review's usefulness under a stated rubric | Reporting and feedback text |
| Targeting signal | Contract failures, cost, downstream escalation at a site | Mode-2 site selection, as a compared condition |
| Intervention estimate | Change in whole-run outcome when the site was replaced or removed | Interpretation, with sampling uncertainty stated |

Only whole-candidate evidence selects or promotes (invariant 4). A branch not
taken has no invocation score; a missing measurement is not zero; edited or
recombined fragments inherit nothing from their parents.

## Metering And Consumption

The evaluated runtime persists no provider usage; the comparison harness
collects none; `RunRefAccounting` in `orchestrator/workflow/run_ref/runtime.py`
carries the literal `UNKNOWN`. OMP usage needs no fix or lower-bound
disclosure: `validate_usage` in `orchestrator/providers/omp_protocol.py`
rejects any closed assistant message whose usage lacks `totalTokens` or
`cost.total` before the transport's `_build_metadata` sums them, so its
zero defaults are unreachable on accepted streams. Usage parsing lives in
`experiments/orc_structural_search/metering.py`: Claude session JSONL
(located by `experiments/compare/scan.py::claude_sessions`) is read one row
per assistant message, deduplicated by message id (`claude_usage`); Codex
rollouts under `~/.codex/sessions` are read from the last cumulative
`token_count` event's `total_token_usage` (`codex_usage`); `coverage` joins
shim calls to sessions on user-turn text only and counts an ambiguous join
as unmatched; a figure without a receipt is `unavailable`. Codex
weekly-window and credit readings are account-wide and reported as bounds.
Per-provider wall clock has no receipt (the shim records no per-call
timing); run-level wall clock is recorded on evaluation records. Provider-call
counts and wall clock are always recorded and reported beside cost; dollar
figures appear only where metering coverage is complete for the compared
conditions.

The cost unit reflects the model: metered tokens priced by a per-model
table frozen in the criterion, with input, output, cache-read and
cache-write prices per model and the table's source and date stated, so a
child that moves to a dearer model pays for it on the cost axis. Calls and
wall clock are an acceptable cost proxy only where model and effort are
frozen (topology-only, prompt-only). Under any condition that may change
them (module, provider-only, joint) metering is mandatory: a candidate
without metered cost has cost `unavailable`, is not placed on the frontier
and is reported as such.

## Evaluation Hygiene

The harness rules apply unchanged: shims first on `PATH` under bubblewrap,
the Fable-refusing model guard with the subagent model pinned, the
contamination scan whose Fable or solution-prefix hits cannot be cleared,
blind random-id pools with repeated anchors, and a criterion frozen and
hashed before scoring and bound into `run.json`. Added here: matched tasks
and execution blocks (repetitions are observations, not tasks; a replicate
index is not a seed claim); an incident retry and disposition policy written
before the run, with attempted consumption preserved and sensitivity to
exclusions reported; envelopes enforced by the actual runner, with
cancellation and teardown verified for it before measurement.

Search adds contamination channels the harness scan does not know; the scan
gains these patterns:

| Channel | Pattern |
| --- | --- |
| The candidate archive and the lineage or score records | archive root; `lineage.jsonl`, `episodes.jsonl`, score files |
| The validation and sealed task lists and packages | holdout roots and package names |
| Prior candidates' workspaces and build caches | other candidates' tree names |

A task agent that reads the archive learns which policy scored well; a
mutator that reads the sealed set contaminates the holdout. Either is a
contamination verdict.

## Records

One append-only JSONL log holds episodes and evaluations; an index is added
only when a real query needs one.

| Field group | Fields |
| --- | --- |
| Lineage | `candidate_id`, `parent_candidate_id`, `site_id` (I2), `interface`, `condition`, `mode`, `episode_id`, `hypothesis`, the I2 receipt or the I1/I3 diff verdict |
| Episode | envelope, consumption or `unavailable`, shimmed CLI and model revision, interventions, outcome, refusal code |
| Compile | `program_digest`, `build_key`, outcome, diagnostics class on rejection |
| Evaluation | `evaluation_id`, `task_id`, split, `evaluator_version`, `env_manifest_digest`, `run_id`, `state_dir`, resume count, outcome, consumption or `unavailable`, incidents, local observations by site |

Recorded divergence: `evaluation_id` in
`experiments/orc_structural_search/evaluation.py` currently hashes
candidate, task, evaluator version, environment manifest digest and
replicate; it omits model revisions and CLI versions, which the identity
table above requires. They must be added before any live phase.

## Controls, Interface Test And Ablations

| Condition | Question |
| --- | --- |
| Authored direct and planner/implementer seeds | Does structure earn its execution cost? |
| Finite authored catalog, enumerated | Is adaptive search needed in this neighborhood? |
| Prompt/provider tuning with fixed topology | Are gains settings and prompt changes? |
| Equal-budget unguided I1 sampling | Does feedback improve selection efficiency? |
| The same protocol delivered as an agent skill | Does a reusable program beat an instructed agent? |
| ORC structural search (I1, I2) | Can useful orchestration structure be discovered? |
| Matched Python structural search (I3) | Does ORC improve the search process over a credible alternative? |

The first comparative experiment is the three-arm interface test: I3 Python
diff, I1 Lisp whole-program and I2 Lisp locus-plus-fragment on one benchmark
workflow, one model and one family, with completed episodes as the budget
unit. Two pre-registered endpoints, each per completed episode: dominating
improvements, a child that dominates its parent on matched adaptive tasks
under the frozen rule (Objective, Selection And Local Observations), and
frontier entries, a child non-dominated against the archive; the frontier
entries are reported by candidate, and both endpoints are split by whether
the child changed its provider allocation (`allocation_distinct`) or its
structure only. Secondary: skeleton diversity and revisit rate, acceptance
rate, repair iterations per accepted proposal. Wall clock and provider
calls are always reported; dollars only where metering coverage is
complete, and metered cost is the cost axis of any arm whose model or
effort may change. Compile-only metrics (acceptance per episode,
edit locality, distinct skeletons, exact repeats by `program_digest`) cover
every proposal; paid whole-run evaluation covers a stratified subset of
accepted proposals per arm. Admissibility differs by language and is
reported per arm, never pooled. The test gives a first bounded answer on one
workflow, one model and one family to whether operator-design freedom beats
proposer fluency, and decides whether the wider ladder is worth building.

The three-arm test compares whole interfaces: I1 against I2 changes both
the supplied context and the editable surface, so it attributes nothing to
context alone. Attribution to compiler assistance comes only from
single-factor ablations after a structural signal: I2 with and without the
pre-supplied site record, and one interface with and without pre-supplied
compiler diagnostics.
Ordinary compiler tools stay available and compilation still precedes
execution; records note what the agent retrieved itself. These measure the
value of packaging assistance, not of removing compiler knowledge; a stricter
information-removal condition is a disclosed custom profile.

## Amendment To The Boundary Invariants

The amendment was applied in place in the boundaries document on 2026-10-18
under the owner's directive to execute the structural search roadmap
([change note](workflow_lisp_program_search_boundaries.md#proposed-amendment-2026-10-17));
this design carries the rationale.

Rationale. Invariant 1 names a registered child run, but no route executes a
provider-bearing candidate as a child at `90ae778c`: `run/spawn` is
unimplemented, `trial` refuses, path-mode `run-ref` admits effect-free
children, the 2.38 confined child is command-only, and no run registry or
parent/child linkage exists for external runs. Invariant 6 limits
provider-in-the-loop evaluation to text-only, mock, replay or sandboxed
calls and keeps effect-free deterministic harnesses as the only acceptable
environment until isolation evidence exists; the 2026-09-08 charter places
execution safety outside the research assessment and the normal-session
boundary rejects no-tool or mock-only defaults, and neither amended the
invariant. The block replaces the child-run sentence of invariant 1 and both
restricting sentences of invariant 6 together, so no contradictory sentence
survives, and states the disclosed boundary: ordinary configured
agent sessions under experiment hygiene (separate clones, the
comparison-harness shims and contamination scan, finite envelopes), with
evaluator truth outside every tree an agent can reach; hygiene, not
isolation, reported as such.

The [typed program gates](workflow_lisp_typed_program_gates.md#boundary-compliance)
normative rule ("candidate execution uses generational child runs only") is
read as scoped to candidate execution started from inside a workflow; an
external controller's public runs are outside it. That reading is part of
the same amendment. Scoping is not lifting: the rule exists so that no
in-run path (`eval-workflow`, C3) executes candidate data inside a
workflow, and the typed-gates design ties lifting it to recorded C1/C2
usage evidence. An external controller's public runs execute nothing
inside a workflow, so that evidence condition is not invoked, and
in-workflow candidate execution stays restricted to generational child
runs exactly as written. The typed-gates design records this scoping in its
§Boundary Compliance.

## Boundary Compliance

| Invariant | Driver |
| --- | --- |
| 1 Immutable generations, full compiler, registered runs, no eval | Satisfied under the 2026-10-18 amendment: external launch through public `run`; children are new snapshots compiled by the ordinary pipeline; each evaluation is a new public run; no eval, hot swap or checkpoint import |
| 2 Provider output is untrusted data | The final diff is data until validation and the compiler accept it |
| 3 Neutral substrate versus feature | Archive, selection, validation, transactions, skeleton hashing and fitness live in `experiments/`; the companion exposes read-only facts |
| 4 Whole-candidate evidence | Only whole-run evidence retains or promotes; local observations are diagnostic |
| 5 Evidence separation | Adaptive, validation and sealed held-out splits are disjoint; the sealed split opens once after generation, choice, evaluator and analysis freeze; near-duplicate defects share a split |
| 6 Honest security boundary | Satisfied under the 2026-10-18 amendment: ordinary configured sessions behind the comparison-harness shims, sandbox and contamination scan, reported as hygiene, not isolation |
| 7 Typed-operation parity without kind erasure | Interfaces move expressions, never runtime callables; provider calls, procedures and workflows stay distinct kinds |
| 8 Role-separated prompt identity | Inherited unchanged; prompt changes allowed only when the condition permits |

## What This Makes Harder

Sequential evaluation in separate clones is slow and disk-heavy. Cost
conclusions are proxies until provider usage is metered, and where the
model may change there are none without it. Lineage views are
rendered from the log, since external runs are joined by id. Frozen-surface
validation refuses legitimate declaration refactors; widening the mutable
scope is an explicit condition change. Family (b) needs a green baseline and
defect authoring; family (a) needs judge spend per evaluation. The interface
factor multiplies conditions, so the three-arm test precedes the ladder.

## Verification

Behavioral checks: a site resolves the right binding under shadowing; an
incompatible replacement is refused with `slot_type_changed` while two
structurally different valid replacements both compile and execute; frozen
surfaces survive a transaction and an unrelated edit in the same file is
refused with `scope_exceeded`; a helper colliding with an import is refused;
`candidate_id` ignores commentary, timestamps and parent and changes with
any source byte; a rejected proposal never enters task evaluation; a
provider call in an unexecuted branch is recorded as unobserved; the
skeleton hash is invariant under renaming and literal changes and differs
for a control-flow change; the final-choice rule refuses without a criterion
hash; a missing receipt serializes as `unavailable`; an incident resume
keeps its evaluation id. One public compile/run integration check runs a
seed candidate through the launch form above with a scripted leaf and
scores it. No prompt-text assertions.

## Affected Surfaces And Handoff

New: `experiments/orc_structural_search/` and `tests/experiments/` coverage.
Reused: `experiments/compare/` shims, scan, pool and layout rules.
Prerequisites outside this design: an OMP shim before OMP sessions; the
harness extension above; the 2.39 catalog port; R2 qualification. Routing (`docs/index.md`,
`docs/design/README.md`, the capability matrix) belongs to the roadmap
change. This design accepts no allocation and selects no study.
