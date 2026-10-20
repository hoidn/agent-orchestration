# ORC Structural Search: The `module` Condition (Rewrite, Compile, Repair)

- **Status:** executed offline steps 1–7 (including 1b), 2026-10-19; verified
  with scripted providers. No live successor study, provider budget or live gate
  completion is implied; a live arm remains separately gated and unselected.
- **Kind:** decision record and implementation plan for the fifth edit condition,
  `module`, and the separate `I1/module` measured arm. The accepted condition
  contract is maintained in the [driver design](../design/orc_structural_search_driver.md#edit-validation-and-transactions);
  this plan owns scoped execution, evidence and live-selection prerequisites.
- **Authority:** the [research charter](2026-09-08-orc-research-charter.md), the
  [program-search boundaries](../design/workflow_lisp_program_search_boundaries.md)
  (as amended 2026-10-18), the [driver design](../design/orc_structural_search_driver.md),
  the [roadmap](2026-10-18-orc-structural-search-roadmap.md) (Phase 1 gates,
  decision points) and the [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md).
- **Baseline:** merged three-arm dependency `6f806b83`; implementation isolated
  on `feat/structural-search-module`. Frozen Phase 1, Phase 2 and three-arm criteria
  remain unchanged; the offline successor is `criteria/module.json`.

## Decision

A mutator may rewrite the candidate module as a whole, compiling and repairing
as often as its episode envelope allows, and submit one final child. The
editable unit is the module's private definitions: its entry body, private
procedures, prompts and private types. Its exported entry signature, the public
types it imports, the available provider bindings, the evaluator and the
resource ceilings stay fixed. The ordinary full compiler checks composition.

Compilation is admission, not fitness: a failed compile is development work
inside the episode, and selection uses whole-run results of executed
candidates. This is already the driver's contract; the change here is the
edit surface, nothing else.

The surface is a new **condition** `module`, beside `topology-only`,
`prompt-only`, `provider-only` and `joint`
(`experiments/orc_structural_search/config.py::CONDITIONS`). It is not a new
`edit_policy` axis: the condition already enters the episode identity, the brief
and `candidates._condition_verdict`, so a new value changes no historical
identity and needs no second switch. Legacy conditions keep their meaning;
Phase 1 and three-arm results stay comparable.

The `module` condition is an **arm, not the default.** It is selected for live
work only on the gate below. The one-site interface I2 and the frozen
conditions remain the measured controls.

## What The Live Runs Show

The ADR's premise is that the frozen surfaces are a restrictive default that
blocks coordinated changes. The evidence does not show them blocking anything
yet:

| Run | Episodes judged | Refused by scope or frozen surface | Compile rejections | Skeletons |
| --- | --- | --- | --- | --- |
| Phase 1, I1 `topology-only`, Claude Opus mutator ([report](../reports/2026-10-18-orc-structural-search-phase1.md), Unguided I1) | 6 accepted (4 later excluded as contaminated) | 0 | 0 | the two clean children both rewrote `direct` into implement, `dev-check`, repair-on-failure (`loop/recur :max 3`), distinct from the parent and from each other |
| Three-arm readout, in progress 2026-10-19 (`/home/ollie/ss3-evidence`, I1, I2, I3 `topology-only`, Codex `gpt-6.1-sol` mutator) | 6 I1, 6 I2 and 6 I3 accepted (recount of 2026-10-19, before the paid subset); every I1 and I2 scan verdict pending | 0 | 0 | 6 distinct per arm, none equal to the parent; one skeleton shared between an I1 and an I2 child |

So in the 24 episodes judged so far (2026-10-19) under `topology-only`, no proposal was refused and
none collapsed onto its parent. The brief tells the agent the rules, so agents
comply rather than get refused; the frozen surfaces shape proposals without
blocking them. That is a reason to measure the wider surface as an arm, not a
reason to make it the default.

The transcripts carry the strongest evidence for the arm, which the ADR does
not cite: the frozen surfaces refused nothing and shaped everything. Both clean
Phase 1 children fed the check output back through the `task` fill of the
unchanged prompt, because prompt bodies were frozen; all six accepted children
referenced `common/CheckReport` by qualified name, because the `import` form's
`:only` list was frozen;
episode 11's child moved to an agent session to carry context across retries
and hit `agent_turn_unresolved`. A `module` arm measures what those
workarounds cost.

What did limit the pilot is the measure, as the Phase 1 report states:

- the upstream anchor scored at or below every candidate in its batch, and
  one anchor pair was inverted;
- the agent-visible `dev-check` passed on the first try in every evaluation
  that ran it, so every check-gated structure realized one coder call, like
  `direct`;
- `consumption` is `unavailable` in all 79 log rows (`metering.py` is not
  wired);
- four of six mutator episodes read sibling episodes or the evidence root
  (now masked: `driver.hidden_roots`, `COMPARE_HIDE` in the shim, on the
  three-arm branch; home stays readable and scan-detected).

A wider edit surface changes none of these. A live `module` arm before they are
fixed would produce children the evaluator cannot rank.

## The `module` Condition

The accepted mutable/frozen surface table and compiled admission rules now live
in the [driver design](../design/orc_structural_search_driver.md#edit-validation-and-transactions).
The [experiment README](../../experiments/orc_structural_search/README.md#module-condition-offline-configuration-and-check)
provides the actual configuration and episode-local check recipe. Private
`defproc`/`defworkflow`/`defprompt` and record/union/enum declarations can be
added, removed, renamed and rewritten; `deftype`, imports, public entry/types
and provider/command bindings stay frozen. This is a separate arm, not a default.

## Deferred Bundle Imports

**v2, deferred: imports from a study bundle.** Letting a candidate import
library modules (`std/*`, further `common`-style modules) changes its planned
provider calls and effects in ways `ledger.max_provider_calls` does not count:
it reads one file, expands only the mutable module's own definitions and
counts `provider-result` heads (an agent turn is one, so turns are counted),
so an imported effectful definition and `run-provider-phase` count 0, and the
runtime's own retries and unresolved-turn reruns lie outside any static
count. The bundle is passed as a second `--source-root`, never staged into the
candidate root: `candidates.candidate_id` hashes every file under the root, so
staging it would change the identity of every candidate staged afterwards and break comparability with earlier ones. Bundle imports open when both
of these exist:

1. a planned maximum computed from the checked closed program the child's
   compile already produces (`closed_program.json`: `perform` nodes of class
   `provider`, `provider_phased`, `agent` and `agent_turn`, multiplied by the
   budgets of their enclosing loops), which covers imports, agent turns and
   phased calls by construction; and
2. a hard per-evaluation cap in the shim: the shim refuses the call whose
   `calls/<n>` index would exceed the evaluation's reserved maximum, so an
   undercount can cost at most one refused call, never an unbounded run.

Until then a child whose compiled program contains a `perform` site of class
`provider_phased` (uncounted, and phased delivery's live qualification is
unselected) or `agent`/`agent_turn` (counted, but a second turn inside
`loop/recur` hits the `agent_turn_unresolved` runtime defect, and an agent
session escapes the evaluation's process-group kill, per the driver design's
Execution Contract) is refused at acceptance (`unsupported_effect_shape`), and
`driver.seed_files` keeps copying only the parent's transitive imports.

## Episode

Unchanged from `driver.run_episode`: a private copy of the archived parent,
the ordinary shimmed session with `EPISODE.md` on stdin, compile and repair
inside the wall clock, the copy's final content files as the child, the scan,
`acceptance.judge_child`, the archive, one log row. A session killed at the
wall clock is `exhausted` and yields no child; a session that exits submits
its final state, whatever it compiled earlier.

No driver-controlled repair loop is added: the agent's own session repairs
against the check command, which keeps the charter's normal-session boundary.
A compiler or checker crash is an infrastructure incident, never a rejection.

Two additions:

- The brief exposes one **check command** that runs the same admission the
  controller runs at finalization: frozen-surface validation for the
  configured condition, then the compile. The original baseline brief exposed
  only compilation; the admission check now makes scope refusals available
  during the episode for repair. The controller still re-runs the
  check on the final snapshot; the agent's own output is never trusted.
- The brief states the allowlist, the per-call ceiling and the frozen
  surfaces of `module` in the same sentence shape the other conditions use.

## Records, Identities And Cost

- The condition is already part of the episode identity
  (`run_episode`: `[parent_id, interface, condition, wall_clock, index, …]`)
  and of the brief; a `module` episode can never collide with a legacy one.
- The candidate identity (`candidates.candidate_id`: content files, transitive
  imports included, plus the runtime commit) is unchanged and independent of
  the condition that produced the child.
- Every evaluation and episode row carries the criterion's SHA-256
  (`criterion_sha256`, as the harness pools already carry), so rows from
  different studies cannot be reused by accident.
- A child whose `candidate_id` was already evaluated is a revisit and is not
  re-evaluated (`mode1`, since `e473a00f`); a deliberate replicate is a new
  evaluation record.
- The successor `three_arm.py` uses explicit criterion arm records, with
  interface and condition independent; the `module` arm's key carries the condition (`I1/module`), so it never pools
  with the `topology-only` I1 arm. Mode 1 ranking/readout is not the arm's
  route; shared `scoring.py` pool, score-join and policy-statistics utilities
  remain part of the successor readout.
- The criterion hash is on rows, not in the episode identity: the identity
  distinguishes episodes within a run; the hash joins rows across studies.
- Episode rows record identified native session paths; evaluation rows carry
  consumption without exposing native paths. Scoped complete native receipts
  supply consumption; missing, ambiguous or incomplete usage stays
  `unavailable`. Calls and wall clock remain the comparison units without full
  metering coverage; a CLI invocation is not a model request.

## Gate For A Live `module` Arm

All of the following, each recorded in the ledger before any provider spend:

1. **The three-arm readout has reported** and its scan verdicts are
   adjudicated. The readout gains one figure per arm: accepted episodes whose
   transcript names a frozen surface the agent worked around or asked for
   (both clean Phase 1 children: 2 of 2). The figure is reported, not a
   trigger; selection rests on gates 2–6 and the owner's allocation.
2. **An evaluator whose anchors discriminate** on the family (upstream above
   the stub and above every candidate, in every batch, for every judge).
   Making hidden acceptance the primary measure would reverse the owner's
   evaluation policy of 2026-10-15; that is an owner decision, not an
   alternative this plan offers.
3. **A family whose agent-visible check fails sometimes**, so repair and
   escalation branches execute and realized calls differ between structures.
   The Phase 1 report records that `dev-check` never failed on
   `resume-projection-integrity` and `pure-result-replay`. The fix is
   task-package authoring with its own cost: a `seed/dev-check.json` argv that
   fails at the base and passes at the solution, or a promoted subset of the
   hidden tests.
4. **Metering wired**, or the comparison stated in calls and wall clock only.
5. **Mutator isolation present** (`COMPARE_HIDE` masking of the evidence root,
   sibling episodes and earlier roots); the `agent_turn_unresolved` defect is
   covered by step 3's refusal of agent classes until it is fixed.
6. **A sealed split** for the arm's final assessment. None exists today
   (Phase 2 plan, Decision 9); authoring one is a cost of the live arm.

When selected, the `module` arm joins the interface test as a fourth arm under
the same envelope (same parent, mutator, episode wall clock, tasks, compile-only
metrics and stratified paid subset) under a successor criterion with its own
SHA-256 that carries the `models` allowlist, the per-call ceiling and the
fourth arm (the frozen `three_arm.json` cannot gain an arm, and no three-arm
row is reused), never as a replacement for the frozen arms. The delivered offline
criterion/readout reports the failure-inclusive blind rubric mean per task and arm
descriptively. Accepted improvements per completed episode remains a proposed
future live objective, requiring separate criterion selection and allocation.
Attribution of a gain to a single change needs single-factor
ablations, which the measured spread (pooled within-arm SD 0.93 and 1.20
rubric points with two replicates) makes unaffordable at Phase 1 scale. An
ablation is a paired comparison with at least three replicates per task on the
validation split under the frozen measure (a rule this plan owns; the driver
design states no replicate count),
and a whole-module gain is retained only when it survives one.

The arm makes no prompt-versus-topology claim: `module` changes prompts and
topology together, and the charter requires the single-factor conditions
(`prompt-only`, `topology-only`) before any joint claim; those remain the
ablations, and the driver design's open ruling on `:text` fills under
`topology-only` must be closed before future cross-condition comparisons. It is
not a prerequisite for offline steps 1–7; the module-only literal policy does not
resolve the separate legacy provider-only nonliteral-tuning question. Nor does it
make a representation claim: ORC against Python is the roadmap's Phase 3 test
with its own budget.

## Implementation Steps (Offline, No Provider Spend)

| Step | Change | Completion evidence |
| --- | --- | --- |
| 1. Condition | `config.CONDITIONS` gains `module`; `candidates.PROMPT_CONDITIONS`, `PROMPT_SIGNATURE_CONDITIONS` and `TOPOLOGY_CONDITIONS` include it, `PROVIDER_CONDITIONS` does not (membership would unfreeze `providers.json` in `_plain_file_verdict`); `_definition_verdict` admits added and removed non-exported definitions under it; `_split_forms` frees private type declarations under it; on the compiled child, `perform` policies are checked against the allowlist (a `name` in place of a literal is refused), `:timeout-sec` literals against the ceiling, and the module qualifiers of its `definitions`/`types` against the parent's; compiler crashes and internal compiler errors become `incident` outcomes with complete diagnostics | Existing fixtures for the four legacy conditions keep their outcomes; a child adding a review prompt, a private union, a helper and routing is accepted under `module` and refused under `joint` |
| 1b. Metrics | Under `module`, `driver.skeleton` and `driver.allocation` (`records.skeleton_hash`) cover every non-exported definition of the mutable file, parent and child alike, entry first, instead of `mutable_definitions` only; private declaration names/references and allocation keys use ordinals only for coherent order-preserving renames, preserving labels and lexical shadowing; prompts are excluded before ordinal assignment | A child that moves its loop into a new helper hashes by the loop, not by the call; legacy conditions hash as before |
| 2. Public contract | `judge_child` compares the closed program's `params` beside its `result`; tests that a child declaring its own `Outcome` beside the frozen import is refused (`declaration_collision`, before compilation), that a changed entry parameter is refused at the signature (`frozen_surface_changed`), that a `common.orc` type edit is `frozen_surface_changed` and an added definition there `scope_exceeded`, and that the resolved `params`/`result` backstop fires by calling `compiled_refusal` directly (ordinary source grammar requires result annotations) | The refusals, with the code that fires first |
| 3. Effect shapes | `acceptance.judge_child` refuses a compiled child whose closed program has a `perform` site of class `provider_phased` (until the closed-program planned maximum exists) or `agent`/`agent_turn` (until the unresolved-turn defect and the kill escape are fixed), as `unsupported_effect_shape` | A child using `agent` is refused; `ledger.max_provider_calls` still refuses a non-literal `:max` |
| 4. Check command and brief | `briefs.episode_brief` renders the `module` surfaces, may carry typed-site context from the manifest without a one-site receipt, and gives a check line that runs validation plus compile from the workspace: `episode_workspace` stages only top-level Python modules from `experiments/{compare,orc_structural_search}` under `py/`, without tasks, criteria or evidence; the check reads local parent-commit/configuration metadata outside `cand-1`, independent of the stripped `COMPARE_BASE`; finalization independently rechecks; the shim model guard reads the allowlist for Claude launches | A scripted mutator reads a scope refusal from the check, repairs, and yields one accepted child; the guard refuses a Claude model outside the allowlist, and a Codex model outside it is refused at acceptance |
| 5. Records | `criterion_sha256` on evaluation and episode rows; the native session file path on episode rows; `metering.py` wired for Claude session usage and Codex rollouts where present, `unavailable` otherwise | Rows carry the hash; a run with a readable session file reports tokens |
| 6. Readout | A successor criterion (own SHA-256; `models`, the per-call ceiling, the fourth arm) and `three_arm.py` keyed by interface and condition (`arm_config` per arm); realized effect identity/class/attempts/status per evaluation from the validated memo view are reported beside calls; source-branch coverage is explicitly unavailable (`memo_records_effects_only`), and generic commands have no ORC memo | A readout row per arm with realized effects and explicit branch-coverage limits |
| 7. Documentation | The driver design's condition table gains the `module` row; the roadmap's interface table lists it as an arm; the experiment README and the capability matrix row record the condition | Links resolve; `PYTHONPATH=. pytest -q -n 16 --dist=worksteal tests/experiments/` passes |

Steps 1–7 are offline and need no allocation. A live arm (step 8) is its own
owner selection with a call cap, after the gate.

## Verification

- A candidate introduces private declarations and coordinated caller changes
  while its exported signature and resolved result type are unchanged.
- A child with a type error gets ordinary `workflow_lisp_compile_diagnostics.v1`
  diagnostics through the check command, repairs within one episode, and
  yields exactly one child.
- A final invalid edit is rejected despite an earlier successful compile; an
  exhausted episode never launches an evaluation and its calls are settled.
- A changed public type meaning, a model outside the allowlist, a per-call
  ceiling above the criterion's, an `agent` turn, an added import and a
  modified external file are each refused with their code.
- Legacy I1/I2 fixtures keep their outcomes; `module` episode identities differ
  from legacy identities for the same parent and index.
- The evaluated snapshot equals the finalized candidate identity.
- A scripted task run exercises a failed check followed by repair and a
  successful no-repair path.
- No test asserts prompt wording.

## Offline Execution Evidence

Selected scope: steps 1–7 and 1b, with scripted providers only; no live successor
study, provider budget, hidden-primary change, runtime/spec change or frozen
criterion rewrite. Final verification at code commit `8e33cff7`:

- `PYTHONPATH=. pytest -q -n 16 --dist=worksteal tests/experiments/`: **774 passed
  in 215.88 s**, exit 0 (`/tmp/module-full-verification-final.log`). The test-only
  baseline-fixture synchronization fix in `8e33cff7` waits for observable file
  recreation before deliberate failure, retaining quiescence/restoration checks.
- Eight changed Markdown files: **745 local links/anchors passed**, including
  explicit HTML anchors; README configuration and arm assertions passed without
  providers (`python /tmp/check-module-docs-final.py`); `git diff --check` passed.
- Phase 1, Phase 2 and three-arm criterion SHA-256 hashes remain unchanged:
  `84ee6307ab39e74710154654133585e53aaa9b329e5c7f9918dc9ee2f055cc80`,
  `f3fd229cc5bafa51cfdd3442f47af6a5edec0bb4fcd31c58f35c3546a6688e97`,
  `d994f8daad608b76e342fa4bedcbc03f1e3c771f719877937331035eb0ae97ba`.
  The separate offline module criterion is
  `8b5cf9253e6d171ae5645305ab2595b04d450d3d63716d7007cae2a53219fba8`.

The public-run fixtures cover a passing check without repair (one physical
provider call, two realized effects) and a failed check followed by repair
(three calls, four effects), plus effect-free execution and corrupt-memo refusal.
The memo supplies effects, not source-branch coverage. Module metric invariance
covers coherent order-preserving renames, not reordering or semantic equivalence.
Malformed/truncated scan evidence stays pending and cannot be cleared or pooled;
calls/effects are retained and exhausted episodes yield no child.

## What This Makes Harder

Whole-module moves are less interpretable than one-site edits: a gain cannot
be attributed to one change without ablations, and the measured spread makes
those expensive. Larger moves raise proposal variance and may raise episode
cost. A fifth condition adds one more surface set to keep consistent across
`candidates.py`, the brief and the design table.

## Placement

This plan owns the decision and the steps. The accepted condition contract is maintained
in the driver design, and the roadmap's interface table lists the arm as I1 under `module`; the gate's evaluator and family items are
owned by the roadmap and the Phase 1 report and are cited, not restated. The
original ADR's "search and evaluation" section is retired into those
citations; its one addition kept here is the realized-site readout (step 6).
