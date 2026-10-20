# ORC Structural Search: The `module` Condition (Rewrite, Compile, Repair)

- **Status:** revised apparatus implemented offline (scripted providers),
  2026-10-19; final integrated verification is recorded in the
  [implementation plan](2026-10-19-orc-structural-search-module-condition-implementation-plan.md).
  Closed-program reservations, shim caps, external qualification and matched
  per-arm model-aware Pareto endpoints extend the earlier delivery. Evidence
  under "Prior Offline Execution Evidence" remains scoped to that earlier code.
  The implementation plan separately records reviewed main-integration delivery
  of policy-set comparison/classes and Codex cache-write accounting; the earlier
  verification does not cover those later corrections.
  No live successor study or provider budget is selected.
- **Kind:** maintained decision and live-selection gates for the fifth edit condition
  `module` and the separate `I1/module` measured arm. The
  [driver design](../design/orc_structural_search_driver.md#edit-validation-and-transactions)
  owns delivered admission and selection semantics; the active implementation
  plan owns execution and fresh verification. This decision preserves evidence
  and owns live-selection prerequisites. The owner's revision
  makes better Pareto over quality and metered deployed cost.
- **Authority:** the [research charter](2026-09-08-orc-research-charter.md), the
  [program-search boundaries](../design/workflow_lisp_program_search_boundaries.md)
  (as amended 2026-10-18), the [driver design](../design/orc_structural_search_driver.md),
  the [roadmap](2026-10-18-orc-structural-search-roadmap.md) (Phase 1 gates,
  decision points) and the [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md).
- **Baseline:** the three-arm dependency merged at `6f806b83`; the prior offline
  delivery is on `feat/structural-search-module`. Frozen Phase 1, Phase 2 and
  three-arm criteria remain unchanged. The historical offline `module.json`
  artifact in the evidence section is not a selected live criterion.

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

The surface is a new **condition** `module`, a fifth value of
`experiments/orc_structural_search/config.py::CONDITIONS` next to
`topology-only`, `prompt-only`, `provider-only` and `joint`, which it
supersedes as the search surface and which stay as controls. It is not a new
`edit_policy` axis: the condition already enters the episode identity, the brief
and `candidates._condition_verdict`, so a new value changes no historical
identity and needs no second switch. Legacy conditions keep their meaning;
Phase 1 and three-arm results stay comparable.

The `module` condition is the intended primary mutation surface for future
search, replacing the frozen conditions rather than joining them; it is
measured as an **arm first**, selected for live work only on the gate below.
`topology-only`, `prompt-only`, `provider-only`, `joint` and the I2 one-site
machinery are kept as measured controls and ablations: maintained, not
extended with new features.

## What The Live Runs Show

The ADR's premise is that the frozen surfaces are a restrictive default that
blocks coordinated changes. The evidence does not show them blocking anything
yet:

| Run | Episodes judged | Refused by scope or frozen surface | Compile rejections | Skeletons |
| --- | --- | --- | --- | --- |
| Phase 1, I1 `topology-only`, Claude Opus mutator ([report](../reports/2026-10-18-orc-structural-search-phase1.md), Unguided I1) | 6 accepted (4 later excluded as contaminated) | 0 | 0 | the two clean children both rewrote `direct` into implement, `dev-check`, repair-on-failure (`loop/recur :max 3`), distinct from the parent and from each other |
| Three-arm main run, 2026-10-19 (`/home/ollie/ss3-evidence`: `log.jsonl`, `readout.json`, `episodes/*/record.json`; I1, I2, I3 `topology-only`, Codex `gpt-6.1-sol` mutator, one call and 1–4 min per episode) | 18 of 18 accepted (6 per arm); every episode with scan hits (13; 5 had none) adjudicated cleared under the three-arm readout's controller ruling R18 (2026-10-19; its record is the verdict reason in `episodes/*/record.json`, not the harness plan's R18): mutators read main-checkout ORC docs, examples and tests because `~/.codex/AGENTS.md` directs it, reported as tool-retrieved exposure, with catalog exposure named in 5 verdicts, 3 of which may be the three-arm parents; the paid subset of 12 evaluations completed, one provider call each (the repair branch never fired) | 0 | 0 | 17 distinct skeletons over 18 children, one shared between an I1 and an I2 child; every arm acceptance 1.0, locality 0, revisit 0, none collapsed; semantically every child is one pattern (implement, `dev-check`, repair on failure), and none adds review, planning or judging |

So in the 24 episodes judged so far (2026-10-19) under `topology-only`, no proposal was refused and
none collapsed onto its parent. The brief tells the agent the rules, so agents
comply rather than get refused; the frozen surfaces shape proposals without
blocking them. That is a reason to measure the wider surface as an arm before
it carries search, not a reason to skip the arm.

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

The table describes the accepted contract. Revised offline delivery and its
verification are tracked in the active implementation plan; the driver design
and experiment README describe the current configuration and check command.

Everything not listed is a frozen surface, refused as today by
`candidates.validate_frozen_surfaces`.

Required for the arm (the v1 guard tier): the frozen public contract (entry
name, parameters and result, public types), the `models` allowlist, a sound
planned maximum from the closed program plus the shim's call cap, and the
refusal of `agent`, `agent_turn` and `provider_phased` effect shapes until
the runtime defect is fixed. Everything else in the table (the per-call
ceiling, the module-graph qualifier check, the shim-side allowlist for
Claude) is optional hardening, not a gate condition; hardening already
implemented stays.

| Surface | `module` policy | Check |
| --- | --- | --- |
| Entry module name, `export` set, entry parameters and result type | Frozen | `_module_verdict` (module, export forms) and `_definition_verdict` (exported signature); `acceptance.compiled_refusal` compares the closed programs' resolved `params` and `result`. A local `(defunion Outcome …)` beside the frozen import is refused as `declaration_collision` before compilation; the compiled comparison is a backstop; ordinary source grammar requires result annotations |
| Public types (`common.orc`: `Change`, `Outcome`, `CheckReport`) | Frozen; `common.orc` is not a mutable file | `_frozen_verdict` on the file; the seeds already keep public types there |
| Entry body and private `defproc`/`defworkflow` | Add, remove, rename, rewrite | `_definition_verdict` admits added and removed non-exported definitions under `module` (implemented offline) |
| Private `defprompt` (signature and body) | Add, remove, rewrite | as above; `PROMPT_CONDITIONS` and `PROMPT_SIGNATURE_CONDITIONS` gain `module` |
| Private `defrecord`/`defunion`/`defenum` | Add, remove, rewrite | `_split_forms` stops treating a type declaration as frozen when its name is not imported or exported; a declaration shadowing an imported name is refused (`declaration_collision`) |
| `:model`/`:effort` values | Any literal from the successor criterion's `models` allowlist (the delivered configuration maps each model to its allowed efforts). Model and effort selection is a legitimate search dimension, not a confound: the allowlist is policy (never Fable; owner 2026-10-15) and the set of models with a known price in the criterion's table, the metered cost axis charges a dearer model, and the readout splits gains by `allocation_changed` (the set of distinct provider/model/effort policies against the parent's; policy-only, structure-only or both) | Checked on the compiled child's `perform` nodes (`policy.model` and `policy.effort` in `closed_program.json`): a `lit` outside the allowlist, or a `name` reference in place of a literal, is refused, which closes the driver design's open decision on non-literal tuning values; the current guard installs both CLI names, caps them at exact Sonnet/Terra IDs, pins Claude native agents and disables independent Codex model dispatch. A criterion may narrow that cap, never raise it; module admission separately checks its compiled allowlist |
| Provider bindings (`providers.json`) and command boundaries (`commands.json`) | Frozen | `_plain_file_verdict`; candidates compose the bound capabilities only |
| Imports | **v1: frozen**: the `import` forms (in `candidates.FROZEN_HEADS`) and the resolved graph | `_module_verdict` keeps the `import` forms; on the compiled child, the module qualifiers named by the closed program's `definitions` and `types` keys (`common::Outcome`) must equal the parent's. A frozen `:only` list does not stop a qualified reference such as `common/CheckReport` (all six Phase 1 children used one), but such a reference reaches only a module already in the graph. Bundle imports are v2 (below) |
| `:timeout-sec` and every other per-call ceiling | Literals at most the successor criterion's per-call ceiling (a new field) | acceptance check; the evaluation's wall clock and the ledger cap remain the outer bound |
| Runtime, compiler, evaluator, task repositories, hidden checks, scoring | Outside the mutation workspace | unchanged |

**Planned maximum and hard cap (v1).** `ledger.max_provider_calls` is not a
sound bound for a rewritten module: it reads one file, expands only the
module's own definitions by name and counts `provider-result` heads (an agent
turn is one, so turns are counted), so a provider call reached through a
local procedure binding or a `proc-ref` passed as an argument, an imported
effectful definition and `run-provider-phase` count 0, and the runtime's own
retries and unresolved-turn reruns lie outside any static count. Under
`module` both of these are in v1:

1. the planned maximum (the ledger reservation) is computed from the checked
   closed program the child's compile already produces (`closed_program.json`:
   `perform` nodes of class `provider`, `provider_phased`, `agent` and
   `agent_turn`, multiplied by the budgets of their enclosing loops and par-map
   maxima; the checker already refuses a loop without a budget), which covers
   local bindings, imports and phased calls by construction; and
2. the shim enforces the cap at launch: the evaluation's reserved maximum
   reaches the shim as one environment variable beside `COMPARE_ROOT`, and the
   shim refuses the call whose `calls/<n>` index would exceed it, so the run
   fails as a provider failure under the frozen rule. An undercount can then
   cost at most one refused call, never an unbounded run.

## Deferred Bundle Imports

**v2, deferred: imports from a study bundle.** Letting a candidate import
library modules (`std/*`, further `common`-style modules) opens once the v1
bound is in place; the bundle is passed as a second `--source-root`, never
staged into the candidate root: `candidates.candidate_id` hashes every file
under the root, so staging it would change the identity of every candidate
staged afterwards and break comparability with earlier ones.

A child whose compiled program contains a `perform` site of class
`provider_phased` (phased delivery's live qualification is unselected) or `agent`/`agent_turn` (counted, but a second turn inside
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
  configured condition, then the compile. The delivered check uses local
  parent-commit/configuration metadata outside `cand-1`, independent of
  `COMPARE_BASE`, which the shim strips. The controller still re-runs the
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
- Every evaluation and episode row gains the criterion's SHA-256
  (`criterion_sha256`, as the harness pools already carry), so rows from
  different studies cannot be reused by accident.
- A child whose `candidate_id` was already evaluated is a revisit and is not
  re-evaluated (`mode1`, since `e473a00f`); a deliberate replicate is a new
  evaluation record.
- `three_arm.py` keys rows by arm, each with an interface and condition; the
  `module` arm's key carries the condition (`I1/module`), so it never pools
  with the `topology-only` I1 arm. Mode 1's `readout.py` and `scoring.py` are
  not used for the arm.
- The criterion hash is on rows, not in the episode identity: the identity
  distinguishes episodes within a run; the hash joins rows across studies.
- Each episode row records the path of the mutator's native session file
  (`~/.claude/projects/…` or `~/.codex/sessions/…`), or the file is copied
  under `E/episodes/<id>/` at settle. The delivered episode rows retain
  `native_session_paths`; evaluation rows retain consumption without exposing
  those paths. Missing or incomplete usage remains `unavailable`.
- Cost under `module` is metered tokens priced by the successor criterion's
  frozen per-model table (input, output, cache-read and cache-write prices;
  source and date stated), read from the native session files by
  `metering.py`; provider calls and wall clock are always reported beside it
  and stand in for cost only when every compared candidate's provider calls
  resolve to one and the same (model, effort) pair, which no `module` arm can
  assume. A row without metered cost carries `unavailable`, and its candidate is not
  placed on the frontier and is reported. A CLI invocation is not a model
  request.

## Gate For A Live `module` Arm

All of the following, each recorded in the ledger before any provider spend:

1. **The three-arm readout has reported** and its scan verdicts are
   adjudicated. The readout gains one figure per arm: accepted episodes whose
   transcript names a frozen surface the agent worked around or asked for
   (both clean Phase 1 children: 2 of 2). The figure is reported, not a
   trigger; selection rests on gates 2–6 and the owner's allocation. The
   measure-free report satisfies this gate: under the calibration rule
   (roadmap, Decision Points) the readout runs no judge stage (its controller
   ruling R19, 2026-10-19) and reports compile-only figures, execution
   outcomes and cost, with quality `unavailable: evaluator uncalibrated`.
2. **An evaluator calibrated on known controls.** For each judge and batch
   the upstream anchor's total minus the stub's is at least
   `calibration.margin`, and the fraction of (judge, batch) pairs failing
   that is at most `calibration.error_rate` (default 0), both predeclared in
   the successor criterion (`three_arm.json`'s `anchor_trust` is the
   unmargined, reported-only form). Nothing is required of the candidates' ranks: a
   candidate may equal or beat the upstream fix.
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
4. **Metering wired**, with the per-model price table frozen in the successor
   criterion. The arm may change the model, so calls and wall clock are
   reported beside cost and never stand in for it; a candidate without
   metered cost has cost `unavailable`, is not placed on the frontier and is
   reported.
5. **Mutator isolation present** (`COMPARE_HIDE` masking of the evidence root,
   sibling episodes and earlier roots); the `agent_turn_unresolved` defect is
   covered by step 3's refusal of agent classes until it is fixed.
6. **A sealed split** for the arm's final assessment. None exists today
   (Phase 2 plan, Decision 9); authoring one is a cost of the live arm.

Gates 2 and 3 are the blocking work: an evaluator calibrated on known controls
and a family whose agent-visible check fails sometimes. The
[measurement calibration implementation plan](2026-10-19-orc-structural-search-measurement-plan.md)
owns the measurement preparation and live gates under the
[roadmap](2026-10-18-orc-structural-search-roadmap.md#decision-criteria-and-next-commitment).
Its generic calibration and package/helper preparation is implemented; the real
controller matrix, final integration and independently reviewed I/F freeze have
passed. Calibration Step A completed 8 calls within cap 10 and failed
(RPI spread; PRR passed). The compatible Terra-only A′ (`AT`) is now stopped
incomplete: RPI passed both frozen batches, PRR committed none after two
native-agent control incidents, and four CLI plus six native child sessions
exhausted cap10. All dispatches used Terra high; the combined calibration gate
remains OPEN. Enforcement must be fixed and verified before a later new owner
budget; B/B2/C remain unrun and separately gated. I_A2/F2 and the AT freeze are
unchanged. The [AT interrupted readout](../reports/2026-10-20-orc-structural-search-measurement-at.md)
records the evidence and incomplete metering. The owner has selected no live `module` arm;
no such arm precedes the required gate results or its own selection. Both gates instantiate the rule that no uncalibrated
experiment runs (driver design,
Task Family And Evaluator; roadmap, Decision Points), and they bind every
live `module` arm: the rule's measure-free fallback does not apply to it.

When selected, the `module` arm joins the interface test as a fourth arm under
the same envelope (same parent, mutator, episode wall clock, tasks, compile-only
metrics and stratified paid subset) under a successor criterion with its own
SHA-256 that carries the `models` allowlist, a separate `price_table` and
receipt field mapping, the `calibration` object, the quality floor, the
tolerances, the per-call ceiling and the fourth arm (the frozen
`three_arm.json` cannot gain an arm, and no three-arm row is reused), beside
the frozen arms, which stay as controls; the arm relaxes the test's one-model
frame to the allowlist. The successor criterion evaluates each arm's parent
on the same tasks and replicates as the arm's subset, and its endpoints are
computed per arm over the parent and the arm's evaluated children:
dominating improvements (the child dominates its parent on quality and
metered deployed cost beyond the tolerances) and frontier entries
(non-dominated against that set) per completed episode, each split by
`allocation_changed` (policy-only, structure-only or both); an unvalued child is
reported as not valued, excluded from the numerator and kept in the
denominator; a child enters the frontier only above the predeclared quality
floor, so trivially cheap failures never populate it. Attribution of a gain to a single change needs single-factor
ablations, which the measured spread (pooled within-arm SD 0.93 and 1.20
rubric points with two replicates) makes unaffordable at Phase 1 scale. A
whole-module gain is retained when it reproduces on the validation split, at
least three replicates per task under the frozen measure, within the
allocation (a rule this plan owns; the driver design states no replicate
count); a prompt, a decision type and a routing change may help only
together, and that interaction is what the condition exists to find.
Ablations are for claims about why a gain works, never a condition of
retaining it.

The arm makes no prompt-versus-topology claim: `module` changes prompts and
topology together, and the charter requires the single-factor conditions
(`prompt-only`, `topology-only`) before any joint claim; those remain the
ablations, and the driver design's open ruling on `:text` fills under
`topology-only` is closed before conditions are compared again. Nor does it
make a representation claim: ORC against Python is the roadmap's Phase 3 test
with its own budget.

## Implementation Steps (Offline, No Provider Spend)

This original checklist preserves the decision's delivery outline. The
[active delta plan](2026-10-19-orc-structural-search-module-condition-implementation-plan.md)
supersedes its execution details, source-helper locations and verification
commands; the driver design owns current field schemas and guards.

| Step | Change | Completion evidence |
| --- | --- | --- |
| 1. Condition | `config.CONDITIONS` gains `module`; `candidates.PROMPT_CONDITIONS`, `PROMPT_SIGNATURE_CONDITIONS` and `TOPOLOGY_CONDITIONS` include it, `PROVIDER_CONDITIONS` does not (membership would unfreeze `providers.json` in `_plain_file_verdict`); `_definition_verdict` admits added and removed non-exported definitions under it; `_split_forms` frees private type declarations under it; on the compiled child, `perform` policies are checked against the allowlist (a `name` in place of a literal is refused), `:timeout-sec` literals against the ceiling, and the module qualifiers of its `definitions`/`types` against the parent's; compiler crashes and internal compiler errors remain `incident` outcomes with full diagnostics | Existing fixtures for the four legacy conditions keep their outcomes; a child adding a review prompt, a private union, a helper and routing is accepted under `module` and refused under `joint` |
| 1b. Metrics | Under `module`, `driver.skeleton` and `driver.allocation` (`records.skeleton_hash`) cover every non-exported definition of the mutable file, parent and child alike, entry first, instead of `mutable_definitions` only | A child that moves its loop into a new helper hashes by the loop, not by the call; legacy conditions hash as before |
| 2. Public contract | `judge_child` compares the closed program's `params` beside its `result`; tests that a child declaring its own `Outcome` beside the frozen import is refused (`declaration_collision`, before compilation), that a changed entry parameter is refused at the signature (`frozen_surface_changed`), that a `common.orc` type edit is `frozen_surface_changed` and an added definition there `scope_exceeded`, and that the resolved `params`/`result` backstop fires by calling `compiled_refusal` directly (ordinary source grammar requires result annotations) | The refusals, with the code that fires first |
| 3. Effect shapes | `acceptance.judge_child` refuses a compiled child whose closed program has a `perform` site of class `provider_phased` (phased qualification unselected) or `agent`/`agent_turn` (until the unresolved-turn defect and the kill escape are fixed), as `unsupported_effect_shape` | A child using `agent` is refused; `ledger.max_provider_calls` still refuses a non-literal `:max` |
| 3b. Bound and cap | `ledger.planned_calls` for a `module` child walks the closed program (perform classes × loop budgets × par-map maxima); the evaluation launch passes the reserved maximum to the shim, which refuses the call whose `calls/<n>` index would exceed it | A child calling a provider through a local `proc-ref` binding plans the right count; a scripted run whose agent makes one call too many fails at the shim with the cap in its stderr, and the ledger settles the recorded count |
| 4. Check command and brief | `briefs.episode_brief` renders the `module` surfaces, may carry typed-site context from the manifest without a one-site receipt, and gives a check line that runs validation plus compile from the workspace: `episode_workspace` stages only top-level Python modules from `experiments/{compare,orc_structural_search}` under `py/`, without tasks, criteria or evidence; the check reads local parent-commit/configuration metadata outside `cand-1`, independent of the stripped `COMPARE_BASE`; finalization independently rechecks; the shim model guard reads the allowlist for Claude launches | A scripted mutator reads a scope refusal from the check, repairs, and yields one accepted child; the guard refuses a Claude model outside the allowlist, and a Codex model outside it is refused at acceptance |
| 5. Records | `criterion_sha256` on evaluation and episode rows; the native session file path on episode rows; `metering.py` wired for Claude session usage and Codex rollouts where present and priced by the criterion's per-model table, `unavailable` otherwise | Rows carry the hash; a run with a readable session file reports tokens and cost |
| 6. Readout | A successor criterion (own SHA-256; `models` allowlist and separate `price_table`, the `calibration` object, the quality floor, the tolerances, the per-call ceiling, the fourth arm) and `three_arm.py` keyed by interface and condition (`arm_config` per arm); each arm's parent evaluated as the arm's subset; the frontier on quality and metered cost, dominating improvements and frontier entries per completed episode over the parent and evaluated children, split by `allocation_changed`; realized effect identity/class/attempts/status per evaluation (from the validated memo view) are reported beside calls; source-branch coverage remains explicitly unavailable (`memo_records_effects_only`) | A readout row per arm with realized sites, the frontier and both endpoints |
| 7. Documentation | The driver design's condition table gains the `module` row; the roadmap's interface table lists it as an arm; the experiment README and the capability matrix row record the condition | Links resolve; `pytest -q tests/experiments/` green |

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

## Prior Offline Execution Evidence

This evidence records the pre-revision delivery only. It does not establish
the closed-program reservation and shim cap, calibrated comparison, priced cost,
parent evaluation or Pareto endpoints required above. Historical artifact hashes
and results below remain unchanged.


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

This plan owns the decision and the steps. The delivered condition contract
and the revised target are maintained in the driver design, and the roadmap's interface table lists the arm as I1 under `module`; the gate's evaluator and family items are
owned by the roadmap and the Phase 1 report and are cited, not restated. The
original ADR's "search and evaluation" section is retired into those
citations; its one addition kept here is the realized-site readout (step 6).
