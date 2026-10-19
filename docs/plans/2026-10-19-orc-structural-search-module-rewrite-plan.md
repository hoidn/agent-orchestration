# ORC Structural Search: The `module` Condition (Rewrite, Compile, Repair)

- **Status:** proposed, unselected (2026-10-19). Revised from the owner's ADR
  "ORC search by rewrite, compile, and repair" of the same date against the
  evidence of the live Phase 1 and the three-arm readout. No provider budget is
  requested here; a live arm needs an owner allocation.
- **Kind:** decision record and implementation plan for one experiment-side
  change: a fifth edit condition for the structural search driver that lets a
  whole-module rewrite add, remove and rewrite private definitions. The contract
  rows below move into the [driver design](../design/orc_structural_search_driver.md)
  ("Edit Validation And Transactions", condition table) when the condition is
  selected; until then this plan is their only home.
- **Authority:** the [research charter](2026-09-08-orc-research-charter.md), the
  [program-search boundaries](../design/workflow_lisp_program_search_boundaries.md)
  (as amended 2026-10-18), the [driver design](../design/orc_structural_search_driver.md),
  the [roadmap](2026-10-18-orc-structural-search-roadmap.md) (Phase 1 gates,
  decision points) and the [Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md).
- **Baseline:** `main` at `bac8c50a`; the three-arm readout runs on
  `feat/orc-structural-search` under its frozen criterion
  (`experiments/orc_structural_search/criteria/three_arm.json` and the plan
  `docs/plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md`, both
  on that branch until it merges).

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
| Three-arm readout, in progress 2026-10-19 (`/home/ollie/ss3-evidence`, I1, I2, I3 `topology-only`, Codex `gpt-6.1-sol` mutator) | 6 I1, 6 I2 and 2 I3 accepted at the time of writing; scan verdicts pending | 0 | 0 | 12 distinct ORC skeletons, none equal to the parent |

So in 20 judged episodes under `topology-only`, no proposal was refused and
none collapsed onto its parent. The brief tells the agent the rules, so agents
comply rather than get refused; the frozen surfaces shape proposals without
blocking them. That is a reason to measure the wider surface as an arm, not a
reason to make it the default.

The transcripts carry the strongest evidence for the arm, which the ADR does
not cite: the frozen surfaces refused nothing and shaped everything. Both clean
Phase 1 children fed the check output back through the `task` fill of the
unchanged prompt, because prompt bodies were frozen; children referenced
`common/CheckReport` by qualified name, because the `import` form was frozen;
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

Everything not listed is a frozen surface, refused as today by
`candidates.validate_frozen_surfaces`.

| Surface | `module` policy | Check |
| --- | --- | --- |
| Entry module name, `export` set, entry parameters and result type | Frozen | `_module_verdict` (module, export forms) and `_definition_verdict` (exported signature); `acceptance.judge_child` compares the closed program's resolved result type with the parent's (`entry_result`), extended to the closed program's `params`, which today are not compared: a candidate that stops importing `common::Outcome` and declares its own `Outcome` is refused as `slot_type_changed` |
| Public types (`common.orc`: `Change`, `Outcome`, `CheckReport`) | Frozen; `common.orc` is not a mutable file | `_frozen_verdict` on the file; the seeds already keep public types there |
| Entry body and private `defproc`/`defworkflow` | Add, remove, rename, rewrite | `_definition_verdict` admits added and removed non-exported definitions under `module` (today: `scope_exceeded`) |
| Private `defprompt` (signature and body) | Add, remove, rewrite | as above; `PROMPT_CONDITIONS` and `PROMPT_SIGNATURE_CONDITIONS` gain `module` |
| Private `defrecord`/`defunion`/`defenum` | Add, remove, rewrite | `_split_forms` stops treating a type declaration as frozen when its name is not imported or exported; a declaration shadowing an imported name is refused (`declaration_collision`) |
| `:model`/`:effort` values | Any literal from the criterion's allowlist | Checked on the compiled child's `perform` nodes (`policy.model` and `policy.effort` in `closed_program.json`): a `lit` outside the allowlist, or a `name` reference in place of a literal, is refused, which closes the driver design's open decision on non-literal tuning values; the shim model guard enforces the same allowlist at launch (`shim/model-guard`, which today refuses Fable and defaults to `claude-opus-5-5`) |
| Provider bindings (`providers.json`) and command boundaries (`commands.json`) | Frozen | `_plain_file_verdict`; candidates compose the bound capabilities only |
| Imports | **v1: frozen** (the parent's resolved module graph) | The compiled child's `configuration.imports` must equal the parent's. The `import` form alone freezes nothing: three Phase 1 children referenced `common/CheckReport` by qualified name although the import was `:only (Change Outcome)`, and the compiler accepted it. Bundle imports are v2 (below) |
| `:timeout-sec` and every other per-call ceiling | Literals at most the criterion's per-call ceiling | acceptance check; the evaluation's wall clock and the ledger cap remain the outer bound |
| Runtime, compiler, evaluator, task repositories, hidden checks, scoring | Outside the mutation workspace | unchanged |

**v2, deferred: imports from a study bundle.** Letting a candidate import
library modules (`std/*`, further `common`-style modules) changes its planned
provider calls and effects in ways `ledger.max_provider_calls` does not count:
it reads one file, expands only the mutable module's own definitions and
counts `provider-result` heads (an agent turn is one, so turns are counted),
so an imported effectful definition and `run-provider-phase` count 0, and the
runtime's own retries and unresolved-turn reruns lie outside any static
count. The bundle is passed as a second `--source-root`, never staged into the
candidate root: `candidates.candidate_id` hashes every file under the root, so
staging would change every candidate's identity. Bundle imports open when both
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

Two additions:

- The brief exposes one **check command** that runs the same admission the
  controller runs at finalization: frozen-surface validation for the
  configured condition, then the compile. Today the brief gives only the
  compile line (`briefs.episode_brief`), so an agent learns about a
  scope refusal only after its episode ends. The controller still re-runs the
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
- `readout.py` and `scoring.py` group by interface and condition, so
  `module` children never pool with legacy I1 children.
- Each episode row records the path of the mutator's native session file
  (`~/.claude/projects/…` or `~/.codex/sessions/…`), or the file is copied
  under `E/episodes/<id>/` at settle; today only the final message
  (`E/episodes/episode-<n>.log`) and the shim's per-call records are kept.
- Cost is provider calls and wall clock until `metering.py` is wired into the
  evaluation and episode rows; dollars are reported only with complete
  metering coverage, per the roadmap. A CLI invocation is not a model request.

## Gate For A Live `module` Arm

All of the following, each recorded in the ledger before any provider spend:

1. **The three-arm readout has reported.** Its per-arm acceptance, locality,
   distinct skeletons and the paid subset exist. A `module` arm is selected
   only if that readout, or the mutator transcripts, show the frozen surfaces
   binding: a refused proposal, an agent asking for a prompt, type or
   definition it may not change, or a collapse verdict on I1. Twenty judged
   episodes with zero refusals do not show it; the arm then waits for a
   neighbourhood where they do.
2. **An evaluator whose anchors discriminate** on the family (upstream above
   the stub and above every candidate, in every batch, for every judge), or
   hidden acceptance as the primary measure for the arm's adaptive stage, per
   the roadmap's decision points.
3. **A family whose agent-visible check fails sometimes**, so repair and
   escalation branches execute and realized calls differ between structures.
   The Phase 1 report records that `dev-check` never failed on
   `resume-projection-integrity` and `pure-result-replay`. The fix is
   task-package authoring with its own cost: a `seed/dev-check.json` argv that
   fails at the base and passes at the solution, or a promoted subset of the
   hidden tests.
4. **Metering wired**, or the comparison stated in calls and wall clock only.
5. **Mutator isolation present** (`COMPARE_HIDE` masking of the evidence root,
   sibling episodes and earlier roots) and the `agent_turn_unresolved` defect
   either fixed or excluded from the arm's vocabulary.
6. **A sealed split** for the arm's final assessment. None exists today
   (Phase 2 plan, Decision 9); authoring one is a cost of the live arm.

When selected, the `module` arm joins the interface test as a fourth arm under
the same envelope (same parent, mutator, episode wall clock, tasks, compile-only
metrics and stratified paid subset), never as a replacement for the frozen
arms. Its primary endpoint is the test's: accepted improvements per completed
episode. Attribution of a gain to a single change needs single-factor
ablations, which the measured spread (pooled within-arm SD 0.93 and 1.20
rubric points with two replicates) makes unaffordable at Phase 1 scale. An
ablation is a paired comparison with at least three replicates per task on the
validation split under the frozen measure (the driver design's evidence rules),
and a whole-module gain is retained only when it survives one.

The arm makes no prompt-versus-topology claim: `module` changes prompts and
topology together, and the charter requires the single-factor conditions
(`prompt-only`, `topology-only`) before any joint claim; those remain the
ablations, and the driver design's open ruling on `:text` fills under
`topology-only` is closed before conditions are compared again. Nor does it
make a representation claim: ORC against Python is the roadmap's Phase 3 test
with its own budget.

## Implementation Steps (Offline, No Provider Spend)

| Step | Change | Completion evidence |
| --- | --- | --- |
| 1. Condition | `config.CONDITIONS` gains `module`; `candidates.PROMPT_CONDITIONS`, `PROMPT_SIGNATURE_CONDITIONS`, `PROVIDER_CONDITIONS` and `TOPOLOGY_CONDITIONS` include it; `_definition_verdict` admits added and removed non-exported definitions under it; `_split_forms` frees private type declarations under it; on the compiled child, `perform` policies are checked against the allowlist (a `name` in place of a literal is refused), `:timeout-sec` literals against the ceiling, and `configuration.imports` against the parent's | Existing fixtures for the four legacy conditions keep their outcomes; a child adding a review prompt, a private union, a helper and routing is accepted under `module` and refused under `joint` |
| 2. Public contract | `judge_child` compares the closed program's `params` beside its `result`; tests that a child declaring its own `Outcome` is refused (`slot_type_changed`), that a changed entry parameter is refused at the signature (`frozen_surface_changed`) and at the closed program, and that `common.orc` edits are refused (`scope_exceeded`) | The refusals, with their codes |
| 3. Effect shapes | `acceptance.judge_child` refuses a compiled child whose closed program has a `perform` site of class `provider_phased` (until the closed-program planned maximum exists) or `agent`/`agent_turn` (until the unresolved-turn defect and the kill escape are fixed), as `unsupported_effect_shape` | A child using `agent` is refused; `ledger.max_provider_calls` still refuses a non-literal `:max` |
| 4. Check command and brief | `briefs.episode_brief` renders the `module` surfaces and a check line that runs validation plus compile from the workspace (`PYTHONPATH=../py`); the shim model guard reads the allowlist | A scripted mutator reads a scope refusal from the check, repairs, and yields one accepted child; the guard refuses a model outside the allowlist |
| 5. Records | `criterion_sha256` on evaluation and episode rows; the native session file path on episode rows; `metering.py` wired for Claude session usage and Codex rollouts where present, `unavailable` otherwise | Rows carry the hash; a run with a readable session file reports tokens |
| 6. Readout | The three-arm readout accepts a fourth arm; realized `perform` sites per evaluation (from the memo) and exercised branches are reported beside calls | A readout row per arm with realized sites |
| 7. Design rows | The driver design's condition table gains the `module` row; the roadmap's interface table lists it as an arm | Links resolve; `pytest -q tests/experiments/` green |

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

## What This Makes Harder

Whole-module moves are less interpretable than one-site edits: a gain cannot
be attributed to one change without ablations, and the measured spread makes
those expensive. Larger moves raise proposal variance and may raise episode
cost. A fifth condition adds one more surface set to keep consistent across
`candidates.py`, the brief and the design table.

## Placement

This plan owns the decision and the steps. The condition's contract rows move
into the driver design at selection, and the roadmap's interface table lists the arm as I1 under `module`; the gate's evaluator and family items are
owned by the roadmap and the Phase 1 report and are cited, not restated. The
original ADR's "search and evaluation" section is retired into those
citations; its one addition kept here is the realized-site readout (step 6).
