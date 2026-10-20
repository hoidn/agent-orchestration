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
  a live Phase 2 needs a new owner selection and budget approval. I3 is implemented
  offline for the three-arm compile-only readout (`three_arm.py`; not in mode 2)
  and ran live once in the measure-free three-arm readout
  ([Phase 1 report](../reports/2026-10-18-orc-structural-search-phase1.md#three-arm-readout);
  [three-arm plan](../plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md)).
  The `module` condition, closed-program reservations,
  shim cap, external qualification gates and per-arm model-aware Pareto readout
  are implemented offline with scripted providers. The
  [implementation plan](../plans/2026-10-19-orc-structural-search-module-condition-implementation-plan.md)
  owns current verification, distinct from the
  [decision's prior evidence](../plans/2026-10-19-orc-structural-search-module-rewrite-plan.md#prior-offline-execution-evidence).
  Fresh mode-2 launches and mode-2 finalist validation are unsupported; retained
  mode-2 helpers interpret historical mechanics only. Mode-3 cumulative campaigns
  are implemented offline with scripted providers under the
  [cumulative campaigns design](orc_structural_search_cumulative_campaigns.md) and
  [C1 plan](../plans/2026-10-19-orc-structural-search-cumulative-pilot-plan.md);
  no live C1 criterion or campaign budget is selected. Main's distinct-policy
  allocation comparison, policy/structure endpoint classes and Codex cache-write
  accounting are implemented and reviewed at `9adcf56c`; that plan records
  their focused and full-suite verification evidence. The separate
  [measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)
  records completed and verified offline calibration preparation with independent
  I/F freeze review; Step A completed 8 calls within cap 10 and failed calibration
  (RPI spread; PRR passed). That plan owns A′'s conditional budget authorization
  and the continuing no-Claude restriction, with no assumed expiry; the
  incompatible frozen packet remains blocked. Later live steps keep their own
  owner budget gates. No live structural-search successor study or campaign
  budget is selected. Fixed-workflow comparisons use
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
  (binding, as amended 2026-10-18 for invariants 1 and 6, whose rationale is
  below, and 2026-10-19 for invariant 4, whose rationale is in the
  [cumulative campaigns design](orc_structural_search_cumulative_campaigns.md)),
  the [design lessons](../orc_workflow_design_lessons.md) and the
  [normal-session boundary](orc_reuse_introspection_search_experiment.md#normal-agent-sessions-and-evaluation-boundary).
- **Companion:** [source-site inspection](workflow_lisp_source_site_inspection.md)
  owns the read-only site manifest over a successful compilation. This
  design owns what acts on it: mutable scope, validation, transactions,
  snapshots and identities.
- **Compatibility:** no runtime, spec, target or memo change; candidates are
  ordinary admitted 2.39 programs run through public `compile`/`run`/`resume`
  ([CLI boundary](../../specs/cli.md#executable-support-boundary)).
- **Selection:** the [structural search roadmap](../plans/2026-10-18-orc-structural-search-roadmap.md).
- **Inherited experiment rules:** exact Sonnet/Terra model cap in every new
  experimental role and nested guarded call; Fable remains forbidden;
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
| Evaluation | `.../evaluation.py` | Fresh clones, public `run`/`resume`, public check operation, final evaluator and realized effects from the validated memo view |
| Admission check | `.../check.py` | Workspace validation and compilation against the local parent commit; finalization independently repeats admission |
| Metering | `.../metering.py` | Scoped native-session receipts for episode and evaluation log rows; incomplete coverage is `unavailable` |
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
`shim/model-guard` record every call, run it under bubblewrap and enforce the
exact `claude-sonnet-5-5` / `gpt-5.6-terra` cap, including Fable refusal. An OMP session gets none of that, so mutator
and arm sessions
are restricted to the shimmed Claude and Codex CLIs; an OMP shim with the
same recording, sandbox and guard is a prerequisite before OMP is used.
Within that restriction the session is ordinary (configured tools, project
instructions, skills, context management, LSP). An interface narrows the edit
scope validation accepts, never the agent's facilities; `--no-tools`,
compiler-only feedback or a source-only prompt is a disclosed ablation.

Isolation is by masking, not an allowlist: every shimmed CLI call of an
episode runs with `COMPARE_HIDE` naming the evidence root, the work root's
`episodes`, `records`, `runs`, `agents` and `env-manifests` directories and
the operator's `--hide` roots (other runs' roots); bubblewrap mounts an empty
tmpfs over each and binds the episode's own tree back
(`driver.hidden_roots`). A mutator therefore reads its own copy, its private
`/tmp` and the runtime copy for the compile line, but no sibling episode,
evaluation, archive candidate or log row. Home, the runtime and every other
directory stay readable; the contamination scan, not the mask, reports reads
there. Only the agent CLIs a mutator command starts through `PATH` run in the
sandbox: a wrapper command itself runs unsandboxed.

## Proposal Interfaces

| Id | Interface | Agent receives | Agent returns | Validation |
| --- | --- | --- | --- | --- |
| I1 | Whole-file rewrite | Candidate workspace, objective, mutable scope, frozen surfaces, development feedback | Edited mutable files | Frozen-surface validation over parsed forms, then full ordinary compilation; no manifest needed |
| I1/module | I1 whole-module rewrite under condition `module` | As I1, with the model/effort allowlist, per-call ceiling and module surfaces below | Edited mutable files | Module admission below; a separate measured arm, not a new interface or default |
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
prompt-only, provider-only, joint or module). Everything else is a frozen surface.
`module` requires a nonempty `models` mapping from model IDs to nonempty effort
lists and a finite positive numeric `per_call_timeout_sec`; both fields are
optional for legacy conditions.

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
| module | Entry body and private procedures, workflows, prompts and record/union/enum declarations in mutable `.orc` files, including coordinated additions, removals, renames and rewrites; subject to the module contract below |

**Open decisions before future cross-condition comparisons.** Two gaps in these surfaces are
recorded, not resolved: under topology-only a call may pass new literal text
to a `:text` prompt fill, which changes what the provider reads while prompt
bodies are frozen; and under provider-only the whole expression after
`:model` or `:effort` is masked as a tuning value, so a non-literal
expression there (a conditional, a call) passes as tuning although it is
topology. Each needs a ruling, and the validation to match, before condition
comparisons are read. These rulings are prerequisites for future comparisons,
not for offline module implementation. The module-only literal policy below
does not settle the legacy provider-only question.

**Frozen-surface validation (I1 and I2).** Parse parent and child with the
ordinary reader and compare forms, not text: imports; `deftype`; private
`defrecord`, `defunion` and `defenum` declarations outside `module`; exported entry
signatures; the command boundary file; prompt bodies and provider extern
files unless the condition permits them. Any difference outside the mutable
scope refuses the proposal; comments and formatting are not compared.
Positions are matched by re-reading parent and child with the ordinary
reader; the controller never splices bytes by span offset, since CRLF and
multi-byte UTF-8 misalign character offsets against raw bytes. The
child then compiles through the ordinary full pipeline, which establishes
static admissibility only.

**Whole-module contract (I1/module).** The condition widens the private
source surface while retaining the public entry and bound capabilities. The
admission table below describes the delivered offline implementation. The
delivered v1 guard also computes a sound planned maximum from the checked
closed program and enforces a per-evaluation shim call cap. The legacy authored
source counter is not the module reservation authority. The frozen public contract,
model allowlist and refusal of `provider_phased`, `agent` and `agent_turn` are
required guards. The per-call ceiling, module-graph qualifier check and Claude
shim allowlist are optional hardening; delivered hardening remains in place.

`module` is the intended primary mutation surface for future search; the legacy
conditions and I2 remain maintained controls and ablations. A live arm is measured
first and needs its separate gates and allocation.

| Surface | Module policy and admission |
| --- | --- |
| Module name and exports | Frozen parsed forms |
| Entry signature and resolved types | Exported parameter/result annotations are frozen; `acceptance.compiled_refusal` also compares the closed programs' resolved `params` and `result` (`frozen_surface_changed`). This is a compiled-artifact backstop; the grammar still requires result annotations |
| Entry body; private `defproc`, `defworkflow`, `defprompt` | Add, remove, rename or rewrite, including prompt signatures/bodies; imported-name collisions refuse as `declaration_collision` |
| Private `defrecord`, `defunion`, `defenum` | Add, remove, rename or rewrite; imported-name collisions refuse before compilation. `deftype` remains frozen |
| Public types and other candidate files | Frozen, including `common.orc`, `providers.json` and `commands.json`; listing a plain file in `mutable_files` does not unfreeze it |
| Imports and resolved module graph | Import forms are frozen. The qualifiers in compiled `definitions` and `types` must match the parent's, excluding the candidate's own module and compiler-owned `workflow_lisp/private`; a changed graph refuses as `frozen_surface_changed` |
| Provider model/effort | Every compiled provider `perform` must carry allowlisted string literals from `models`; missing, nonliteral or unlisted values refuse as `model_not_allowed`. Fable remains refused even if listed; the current CLI guard also refuses any model outside the exact Sonnet/Terra cap, which an allowlist cannot raise |
| Per-call ceilings | A positive finite literal `timeout_sec` no greater than `per_call_timeout_sec` is required; missing/nonliteral values or additional unadmitted ceiling policies refuse as `per_call_ceiling_exceeded` |
| Effect shapes | Compiled `provider_phased`, `agent` and `agent_turn` effects refuse as `unsupported_effect_shape`; the ordinary bounded-call check still refuses `unbounded_calls` |
| Runtime, compiler, evaluator, task repositories, hidden checks and scoring | Outside the mutation surface |

Compilation checks the entire child, including new helpers. Ordinary source
errors reject with full structured compile diagnostics; compiler crashes and
internal compiler errors are infrastructure incidents, with diagnostics retained
for repair. A rejected or exhausted episode produces no evaluated child.

The brief exposes `experiments.orc_structural_search.check` with local metadata
outside `cand-1`: the parent Git commit, configuration and optional site facts.
It does not depend on `COMPARE_BASE`, which the shim strips from tool processes.
The check validates a temporary final snapshot against that parent and performs
ordinary compilation. Finalization repeats admission from controller-owned
inputs; a successful intermediate check never admits a later invalid edit.

The optional Claude model allowlist is enforced by the shim guard across all
configured arms, including explicit/default/fallback models and forced subagents.
Codex model enforcement here is at module admission. The guard retains the
harness's disclosed bypass limits. Imports from a study bundle remain deferred:
the checked-program planned maximum and hard per-evaluation shim cap are already
required for module v1, independently of bundle imports
([decision and rationale](../plans/2026-10-19-orc-structural-search-module-rewrite-plan.md#deferred-bundle-imports)).

**Closed-program reservation.** The module bound starts at the checked entry
body and follows only closed-program AST edges, never arbitrary mappings inside
literal data. A provider `perform` contributes one plus the bounds of its
evaluated inputs; the counter includes provider classes that admission separately
refuses. A resolved call contributes its evaluated arguments plus its callee's
body **per invocation**, including imported definitions and resolved procedure
references. Memoizing a callee's bound does not deduplicate its invocations.
Sequencing sums; summing alternative paths is an admitted conservative bound.
Unknown calls, recursive cycles and unsupported accounting shapes refuse as
`unbounded_calls`.

For a loop, use the artifact's actual literal integer `budget`: the bound is
`B(budget) + B(init) + max(0, budget) * B(body) + B(exhausted)`; exhaustion
therefore remains counted at budget zero. Nested loops apply the same recurrence.
A `par-map` uses its checked nonnegative integer maximum and counts the source
once plus that maximum times workspace and body. An effectful `list_map` needs
a source whose literal list cardinality is provable; otherwise it fails closed.
Reserve the resulting maximum before launch and enforce that same cap in both
provider shims, including concurrent attempts, retries, resumes and zero cap.
The existing admission policies, structured diagnostics and refusal codes remain
unchanged; this bound does not admit an otherwise unsupported effect shape.

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
prompt signature, so it is accepted under joint and module; a non-prompt helper
is a topology change, accepted under topology-only, joint and module; under
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
| `evaluation_id` | SHA-256 over candidate, task, evaluator version, environment manifest digest and replicate, plus attempt number for a relaunch after the first attempt; provider settings are covered by candidate content, CLI versions by the environment manifest |
| Lineage record | Parent, child, edited sites, interface, receipt |

Hosted model revisions are recorded as `unavailable` and are not hashed into
`evaluation_id`; an unchanged hosted alias can change server revision. Equal
`candidate_id` means the same
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

The archive is a bounded subset of the frontier, the non-dominated set on
quality and metered deployed cost (the objective below), recomputed from
every evaluated candidate after each generation: a child enters when no
member dominates it and evicts the members it dominates; when the frontier
exceeds the archive size (`ARCHIVE_SIZE`), members are dropped by a
predeclared spread rule that keeps the cheapest and the highest-quality
members, then the members with the largest cost gaps to their neighbours.
Provider calls stand in for the cost axis only when every compared
candidate's provider calls resolve to one and the same (model, effort)
pair; otherwise metered cost is required. Parent and site selection start
uniform; local-feedback targeting is a compared condition. I2 proposals
need the manifest; I1 proposals use frozen-surface validation alone.

**Historical mode-2 mechanics.** `run_mode2` and `validate_finalists` refuse
fresh adaptive work explicitly, including successor criteria. The helpers in
`experiments/orc_structural_search/adaptive.py` retain the following captured
behavior for historical interpretation, not as a selectable search policy.
An archive entry carries per-task primary values and
provider calls of its counted evaluations; the archive is the incumbent
plus at most `ARCHIVE_SIZE` (6) members non-dominated on (mean value
higher, mean calls lower), ranked by mean value, then fewer calls, then the
earlier id. Recorded divergences from the archive rule above, to fix when
Phase 2 is selected: `dominates` applies no tolerance; `prune` truncates
the frontier by quality rank, not by the spread rule; `retain` applies no
quality floor; nothing reads the condition or the cost axis, so mean calls
is the cost axis whatever the candidates' models. The frozen `phase2.json`
(`mean_cost` is wall clock, over a multi-model catalog) predates the
cost-proxy rule and is not changed; a Phase 2 selection needs a successor
criterion with metered cost. Generation 0 seeds the archive from Phase 1's joined rows
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
and `direct` on the validation task. For successor studies this calls-based
archive (incumbent plus six on mean value and mean calls) and its generation
protocol are superseded by mode 3; no calls-only selection returns through a
compatibility fallback.

**Mode 3: cumulative campaigns.** Multi-generation campaigns over whole
programs under `module`: a persistent experiment-owned evidence store shared
by campaigns, campaign checkpoint and resume, a results archive whose
frontier is the objective below, a bounded breeding pool (a frontier subset
plus a reservoir of non-frontier candidates) under two compared parent
policies, diversity pressure with a revisit and futility rule, and a
cumulative budget readout. Owned by the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md);
its selection and spend are gated by the roadmap's Phase 2 Gates. This
design changes nothing for it beyond the pointers here.

**Skeleton diversity (all modes).** LLM mutation chains over a Lisp-like
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
only when both its skeleton and its allocation equal the parent's.

Under `module`, source metrics select the entry first and every private
non-prompt declaration in authored order, including private types and helpers.
Prompts are excluded before ordinal assignment. Private declaration names and
references share ordinal keys in the skeleton and provider allocation; lexical
shadowing and field, variant, member and authored site labels retain their
meaning. The invariant covers coherent renames that preserve declaration order,
including qualified workflow/procedure references and typed `let-proc` forms.
It does not establish invariance under reordering, arbitrary refactoring or
semantic equivalence. Legacy ORC and Python normalization remain unchanged.

Reported: distinct skeletons
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
  roots (`experiments/orc_structural_search/quota.py`). The retained historical
  mode-2 helpers had no quota guard for episodes and started each `evaluate_all`
  with an unpaused guard; fresh mode-2 adaptive launch is unsupported.
- An I3 candidate (a Python entry module) runs through the comparison
  harness's generic-command arm instead: `python -P <candidate>/direct.py
  inputs.json` behind the same shims in the fresh clone, its run state in the
  clone's `.orchestrate/runs/<run_id>/`. Its terminal is that directory's
  `terminal.json` (`outcome` completed or failed, `value`, `failure`, times
  and calls), classified like a memo's terminal row; a run without one is an
  incident, which is not resumable (`evaluation.resume` refuses it), and
  `prepare.collect` takes the last call's patch as the final one.
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
live experiment spends provider calls on quality evaluation (candidate
evaluation runs and judge calls whose purpose is a quality comparison)
unless its quality measure passed a predeclared calibration on known
controls and its family is qualified under its own frozen rule (family (a):
the harness
[difficulty-calibration rule](../plans/2026-10-14-effectiveness-harness-and-experiments-plan.md#task-8-task-difficulty-calibration);
family (b): the oracle qualification below). For a judge measure the
calibration is: for each judge and batch, the upstream anchor's total minus
the stub's is at least `calibration.margin`, and the measure passes when
the fraction of (judge, batch) pairs failing that is at most
`calibration.error_rate` (default 0), both predeclared in the criterion.
Calibration runs (anchor and control batches, difficulty qualification) are
calibration experiments with their own budget, exempt from this rule, and
pass before any candidate is scored; in-run anchors stay a monitored check
reported beside the result. An experiment whose measure is uncalibrated
reports only measure-free figures (compile-only metrics, execution outcomes,
cost) and makes no quality comparison, frontier or improvement claim; the
transition for an experiment frozen before this rule is in the roadmap's
Decision Points.

| Family | Truth | State |
| --- | --- | --- |
| (a) Review/planning improvement on the harness task packages | Structural V1 uses pinned `score.orc` and its frozen qualification identity; generic comparison also supports reference-rubric calibration with four blind controls; hidden acceptance remains secondary | Generic calibration and C1 V2 qualification mechanics are implemented offline; neither implementation establishes live calibration or family qualification; the [C1 plan](../plans/2026-10-19-orc-structural-search-cumulative-pilot-plan.md) owns successor verification and live gates |
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

### Generic Reference Calibration And Current Experiment Policy

The generic comparator supports criterion-selected `score_ref.orc`, four blind
control roles (upstream/stub/partial/mutant), an unscored disclosed reference and
P1/P2/P3/spread verdicts. The
[harness contract](orc_effectiveness_comparison_harness.md#decision)
owns those batch/control rules; the
[measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)
owns current preparation and paid stages. Explicit calibration skips new
per-node hidden acceptance, retaining existing construction diagnostics only.
This generic path does not widen structural V1's rubric or receipt admission.
V1 still validates its pinned historical rubric/family/evaluator inputs unchanged.
C1's V2 qualification mechanics are selected and implemented offline under the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md) and
[C1 plan](../plans/2026-10-19-orc-structural-search-cumulative-pilot-plan.md).
A live successor quality study still requires the accepted measure, real family
and measure qualification evidence and separate owner-approved step budgets.
Fresh mode-2 adaptive launches remain unsupported.

Every new experiment role uses the exact Sonnet/Terra cap: `claude-sonnet-5-5`
or `gpt-5.6-terra`, including judges, controls, diagnosis and nested guarded
calls. The measurement-specific Step-C seed is an external frozen copy with
Sonnet-medium coder and Terra-high diagnosis; historical source retains its Sol
policy and is not the current launch input. Model-cap enforcement and preparation
do not establish family qualification, calibration or quality improvement.

### External Qualification Receipt

The structural-search apparatus validates precalibration already performed; it
does not launch calibration or infer owner approval from a receipt. New
calibration remains a separate, owner-approved experiment with its own declared
positive provider-call cap and only declared control or difficulty jobs. The
generic comparison harness's launchers are outside this structural-search
contract; adding this gate does not claim to govern their independent callers.

A criterion's `purpose` is `quality`, `measure-free` or `calibration`; omission
means `quality`. Structural-search launchers reject `calibration`, so relabeling
a candidate cannot obtain the calibration exemption. Quality requires an
explicit criterion file, a matching configuration `criterion_sha256`, and a
valid `qualification: {file, sha256}` reference. A missing criterion is not a
measure-free request. Launching without qualification requires an explicit
criterion with `purpose: "measure-free"`; it permits compile, execution and cost
figures, but no judging or adaptive selection based on quality.

Readout alone also accepts an explicit `--measure-free` option (and corresponding
function keyword) to project historical evidence without changing frozen
criterion bytes. This projection declares its mode and emits no quality means,
comparisons, frontier, improvements or quality-based decisions. Without that
option or a measure-free criterion, invalid qualification raises an error; there
is no implicit downgrade. Historical criteria and missing-row-hash exceptions
provide no fresh quality-launch or quality-claim exemption.

Both study and measure-calibration criteria use the same `measurement` identity
block below. The study retains its existing top-level `tasks` list of paths;
`measurement.tasks` is a separate map keyed by task ID. A calibration criterion
has `purpose: "calibration"`, `calibration_kind: "measure"`, its own positive
`budget.call_cap`, and this measurement block; it declares no search candidates.
The placeholders illustrate a schema, not a frozen study or provider allocation.

```json
{
  "purpose": "quality",
  "tasks": ["experiments/compare/tasks/resume-projection-integrity"],
  "judges": ["gpt-5.6-terra"],
  "calibration": {"margin": 2.0, "error_rate": 0.0},
  "qualification": {"file": "/external/qualification.json", "sha256": "..."},
  "measurement": {
    "evaluator": {
      "score_workflow": {"file": "/frozen/score.orc", "sha256": "..."},
      "judges": {
        "gpt-5.6-terra": {
          "effort": "high",
          "providers": {"file": "/frozen/score_codex.json", "sha256": "..."}
        }
      }
    },
    "tasks": {
      "resume-projection-integrity": {
        "package_sha256": "...",
        "controls": {
          "upstream": {
            "label": "resume-projection-integrity-upstream",
            "source": {"file": "/frozen/upstream.diff", "sha256": "..."},
            "pooled_patch_sha256": "..."
          },
          "stub": {
            "label": "resume-projection-integrity-stub",
            "source": {"file": "/frozen/stub.diff", "sha256": "..."},
            "pooled_patch_sha256": "..."
          }
        }
      }
    }
  }
}
```

Every reference is `{file, sha256}`, identifying the file's bytes with a bare
hexadecimal SHA-256. Resolve relative paths against the containing JSON file.
Verify referenced bytes before comparing identities. Compare normalized
measurement blocks with references represented by their SHA, ignoring only the
reference's file location. Do not compare whole study/calibration criterion
hashes: their purposes and budgets differ. The declared judge set must equal the
criterion's judges and actual dispatch judges. V1 uses the existing `score.orc`
rubric and its fixed `high` effort. Verify the workflow and provider-binding
bytes actually selected by the study runtime and judge arguments, not merely
files named in the receipt. At a launch boundary without explicit judge arguments,
validate planned bindings from each measurement judge's `providers` reference.
If the criterion also declares legacy `judge_bindings`, it must name exactly the
judge set and its paths, resolved against the selected runtime, must have the
same verified bytes. Do not assume a default backend for planned dispatch.
At pooling, judging and quality readout, explicit judge arguments and recorded
pool inputs own actual dispatch: bare `MODEL` selects that runtime's
`experiments/compare/score.providers.json`, while `MODEL=PATH` selects that file.
Each actual choice must match the calibrated provider reference, independently
of the earlier planned check. Control sources must match the study task's anchors.
The pooled patch SHA identifies the recorded, normalized clone diff, which need
not equal the source diff's bytes after stripping and application.

The external receipt has the following shape. Samples are in their original
order; this abbreviated example shows only one sample, whereas qualification
requires the count specified below.

```json
{
  "schema": "orc-structural-qualification-v1",
  "family": {
    "kind": "review-blockers-r55",
    "rule": {"file": "/frozen/calibration.json", "sha256": "..."},
    "tasks": {
      "resume-projection-integrity": {
        "package_sha256": "...",
        "sources": [{"file": "/evidence/rung-2-calibration.json", "sha256": "..."}],
        "samples": [{
          "direct_record": {"file": "/evidence/direct-1/record.json", "sha256": "..."},
          "direct_inputs": {"file": "/evidence/direct-1/inputs.json", "sha256": "..."},
          "patch": {"file": "/evidence/direct-1/collected/final.diff", "sha256": "..."},
          "review_record": {"file": "/evidence/review-1/record.json", "sha256": "..."}
        }]
      }
    }
  },
  "measure": {
    "criterion": {"file": "/calibration/criterion.json", "sha256": "..."},
    "pools": [{
      "task_id": "resume-projection-integrity",
      "mapping": {"file": "/calibration/records/mapping.json", "sha256": "..."},
      "results": {"file": "/calibration/records/results.json", "sha256": "..."},
      "patches": {
        "clone-upstream": {"file": "/calibration/records/patches/clone-upstream.diff", "sha256": "..."},
        "clone-stub": {"file": "/calibration/records/patches/clone-stub.diff", "sha256": "..."}
      }
    }]
  }
}
```

Validation rejects unknown schemas, malformed fields, duplicate identities,
missing evidence or mismatched hashes. Verify all referenced sources; neither
`qualified` booleans nor summary means are authority. The receipt must cover
every task used. Recompute each package hash using the existing difficulty
criterion's method: sort regular files by their `./` relative paths, hash each,
then hash the concatenated `sha256sum` lines. V1 rejects symlinks and filenames
requiring escaped `sha256sum` output rather than silently changing that method.
Compare the package with both family and measurement evidence.

**Family (a).** V1 admits the frozen R55 rule in
[`calibration.json`](../../experiments/compare/criteria/calibration.json), SHA
`9faa4c01d0e3f231278f85d809a3e0d3bb3f64813cd59afba690089afd355f46`.
The [continuation](../../experiments/compare/criteria/calibration-continuation.json),
SHA `c6cfb85a9b21268fcffb32209fa45974ca139743c3cc1cdb0444d04e7c37efc9`,
and raw rung summaries supply hashed provenance; stored qualification decisions
do not replace the calculation. Exactly one source must match the task's `slug`
and `package_sha256` and declare its complete ordered `single_calls` list with
`run: "direct_task/run-N"` entries. The raw samples must match that entire list,
not a chosen prefix or suffix. Original full run paths are identities, and their
numbers must ascend consecutively within the original root; a rung may start at
any positive number, such as runs 3/4 or 7/8. Direct and review identities must be
unique, even though their numeric suffixes may coincide in different arm roots.

Only the exact known frozen continuation SHA permits a two-sample source plus a
third sample from a different root. Its task/package, reused rung-1 summary SHA
and both original raw record/diff/review hashes must match the frozen rule.
The third direct identity must be the rule's full
`work_root/records/direct_task/run-1`; its nonempty patch requires the full
`work_root/records/review_once/run-1` review identity. Archived reference files
may relocate, but these original identities and bytes cannot change. This narrow
membership exception does not accept replacement histories or summary booleans,
and raw blockers still determine whether exactly two or three samples are needed.

Each sample requires a completed `direct_task`, its frozen control model/effort
inputs and its final diff. Validate common task/base, unique original run
identities and sample order. A nonempty diff requires a completed `review_once`:
its `applied.sha256` must equal the diff's hash and its `applied.path` must name
the direct record's original `records` plus `patches.final`, even when archived
copies live elsewhere. Apply the harness's `pool.exclusion` scan/call rules to
both records. Recompute with `prepare.blockers` from the recorded review value:
`REQUEST_CHANGES` counts every finding, `WRONG_APPROACH` counts one, and `APPROVE`
or `NEEDS_HUMAN` counts zero. Validate variants and findings types first. A
completed empty diff counts one and has `review_record: null`.

For exactly two initial samples, mean blockers below 1 fails and a mean at
least 1.5 qualifies. A mean in `[1, 1.5)` requires exactly a third sample and a
three-sample mean at least 1. An absent third sample is unresolved, not zero;
additional selectively chosen samples do not qualify. Hidden-test fractions
remain descriptive. V1 rejects ambiguous replacement/failure histories instead
of adapting every historical report dialect or accepting its summary boolean.

**Measure.** Verify that the calibration criterion's hash equals both the pool
mapping and results `criterion_sha256`. Its calibration margin and error rate
must match the study's: margin is finite and nonnegative; error rate is finite
in `[0, 1]`, default zero; booleans are not numbers. Reuse the harness's mapping
and clone-ID-joined results shapes. Each nonempty batch contains exactly one
declared upstream and stub control. Every pooled clone is a declared anchor
(`arm: "anchor"`, `run: null`), with matching label and recorded patch hash;
candidate evaluations cannot appear in calibration pools.

For each task, the denominator is all declared judges times all declared
batches, including excluded judges. Recompute each control total from the four
integer `[0, 2]` rating components `root_cause`, `scope`, `generality` and
`layering` in `results.clones[cid].ratings[judge]`. A pair passes iff upstream
minus stub is at least the frozen margin. Excluded judges or missing ratings
fail that pair; contradictory clone identities or batch membership invalidate
the receipt. Every declared judge must have at least one observed pair, so a
wholly absent judge cannot qualify through tolerance. The task passes iff its
failing-pair fraction is at most the frozen error rate; one task cannot compensate
for another. Candidate ranks and `results.verdict` impose no condition. In-run
anchors remain monitoring evidence, never a substitute for this precalibration.

**Family (b).** The narrow alternative is `family.kind: "oracle-controls-v1"`.
The hashed frozen rule has this shape (references use the same `{file, sha256}`
contract; placeholders are schema notation, not selected evidence):

```json
{
  "oracle": {"file": "oracle.py", "sha256": "..."},
  "checks": ["behavior", "result"],
  "tasks": {
    "task-id": {
      "package_sha256": "...",
      "controls": [
        {"id": "correct-a", "expected": "accept", "structure_class": "class-a", "submission_sha256": "..."},
        {"id": "correct-b", "expected": "accept", "structure_class": "class-b", "submission_sha256": "..."},
        {"id": "broken", "expected": "reject", "structure_class": "broken", "submission_sha256": "..."}
      ]
    }
  }
}
```

The receipt's `family` contains `kind`, `rule: {file, sha256}` and
`tasks: {task-id: {package_sha256, controls: [{id, submission: Ref, result: Ref}]}}`.
Each referenced result is
`{task_id, package_sha256, oracle_sha256, submission_sha256, checks: {name: Bool}}`.
Check names are nonempty and unique; result keys match the frozen checks exactly.
Each task declares exactly three controls with distinct IDs and submission hashes. Two controls have `expected: "accept"`, distinct submission
hashes and distinct predeclared `structure_class` values; the third has
`expected: "reject"`. Each control references its submission and result; the
result identifies the submission hash and results for exactly the frozen checks.
All checks must pass for each correct control, and at least one must fail for
the broken control. Structural classes are reviewed, frozen evidence; differing
file hashes alone do not establish structural difference. Unsupported formats
fail closed. This family gate does not add an oracle scoring implementation:
the measure in this apparatus remains the calibrated blind rubric, whose result
must not be presented as a final oracle measurement.

**Enforcement boundaries.** Thread an optional `criterion: Path | None` keyword
from structural entry points through driver/mode1 evaluation, direct `evaluate`,
resume and shared structural `score_pool`. Missing means a failed quality gate,
not an exemption. Validate before budget reservation and again at direct
evaluation, resume, judge dispatch and quality readout boundaries; reread hashed
evidence per operation rather than caching a `qualified: true` permission.
Record the receipt hash and recomputed statistics with the operation. Judging,
quality pooling and adaptive quality selection reject measure-free mode. No
runtime/compiler behavior or generic provenance framework is introduced.

Keep qualification receipts, calibration pools, raw family records, control
sources, oracle rule and oracle engine in dedicated evidence directories. Their
private roots are masked from candidates and added to contamination scans for
launch and resume. A layout that would mask a runtime, task/workspace root or
its whole ancestor refuses; a dedicated task `anchors/` directory is allowed.
Only the known frozen R55/continuation rule hashes are public-rule exceptions.
References may relocate without changing the verified bytes. V1 binds the
shipped scoring workflow SHA and fixed high effort, and validates the actual
runtime workflow, judge model inputs and provider bindings at pool/readout.

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
provider calls; metered cost recorded). Both are means over the candidate's
counted evaluations on the same task set and replicates: q is quality, c is
cost, and the criterion predeclares two tolerances, `tau_q` in the
criterion's units (the same field as the final choice's
`equivalence_tolerance`) and `tau_c` relative (`dominance_cost_tolerance`).
Better means dominance: A dominates B iff q_A >= q_B - tau_q and
c_A <= c_B * (1 + tau_c), and q_A > q_B + tau_q or c_A < c_B * (1 - tau_c).
The frontier is recomputed from all evaluated candidates each time, never
incrementally, so it does not depend on the order candidates arrive in. A
timeout, invalid submission or task failure is an outcome whose
consumption still counts. Failure rule
(criteria amended 2026-10-18; `primary_value` and `scored_outcome` in
`experiments/orc_structural_search/scoring.py`): a failed evaluation and an
envelope timeout (an incident killed at its wall-clock envelope) score 0
rubric points; every other incident is excluded, not scored zero. The
frontier, the non-dominated set, is the object of search: it is retained
and reported and never collapsed into a scalar reward. Frontier membership
requires a predeclared quality floor, so trivially cheap failures never
populate it. The delivered successor supports exactly
`quality_floor: {"kind": "above_stub"}`: quality must be strictly above the
stub mean on the matched task set, without applying the quality tolerance to
this floor. Missing stub evidence makes the floor unavailable. A different
floor requires its own selected implementation. Pareto selection does not repair a weak quality measure: where
the measure does not resolve candidates, cost decides alone and search
drifts toward doing less, so the calibrated-evaluator gate stays a
precondition of any adaptive claim.

The authored reference seed is always evaluated on the validation split
beside the finalists, and its runs are budgeted with them, so every finalist
is compared with the incumbent on the same tasks. Deployment follows a rule
written into the criterion before adaptive work, over every candidate
validated on the validation split, the reference seed included, whether or
not it is a frontier member (`records.final_choice`): among those under a
stated mean-cost ceiling, the ones whose validation success is within a
stated equivalence tolerance of the highest, then lower mean cost, then
fewer provider calls, then the earlier candidate id; the ceiling may be in
provider calls and wall clock only when every validated candidate's
provider calls resolve to one and the same (model, effort) pair, and the
criterion says so. Deployed cost
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

Deployment-frontier membership, finalist selection and promotion require
whole-program evidence (invariant 4 as amended 2026-10-19); contextual
fragment observations and explicit search-value estimates may guide proposal
targeting, parent sampling and exploratory retention, but cannot alone
establish whole-program quality, validate a replacement or authorize
promotion
([cumulative campaigns](orc_structural_search_cumulative_campaigns.md#estimates-and-attribution)).
A branch not taken has no invocation score; a missing measurement is not
zero; edited or recombined fragments inherit nothing from their parents.

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
Episode and evaluation finalization use `metering.receipts`, scoped by workspace
and attempt start time. Episode rows retain identified `native_session_paths` even when
a matched session has incomplete usage; evaluation rows carry consumption but
do not expose those native paths. Consumption is reported only when every
shim call has an unambiguous complete receipt; missing, malformed or truncated
usage remains `unavailable`, never zero. No runtime usage persistence is added.
Per-provider wall clock has no receipt (the shim records no per-call
timing); run-level wall clock is recorded on evaluation records. Provider-call
counts and wall clock are always recorded and reported beside cost; dollar
figures appear only where metering coverage is complete for the compared
conditions.

The cost unit reflects the model: metered tokens priced by a per-model
table frozen in the criterion, with input, output, cache-read and
cache-write prices per model and the table's source and date stated, so a
child that moves to a dearer model pays for it on the cost axis. Metered
cost is the list-price equivalent from that table, not billed spend;
subscription billing and Codex window readings stay bounds. The mapping
from receipt fields to prices is frozen with the table: a Claude usage row
charges `input_tokens` at input, `output_tokens` at output,
`cache_read_input_tokens` at cache-read and `cache_creation_input_tokens`
at cache-write; a Codex `total_token_usage` charges
`cached_input_tokens` at cache-read, `cache_write_input_tokens` at cache-write
and `output_tokens` at output. Use the last cumulative `total_tokens` to resolve
whether cache-write is already included in input: if total equals input plus
output, charge `input_tokens - cached_input_tokens - cache_write_input_tokens`
at ordinary input; if total equals input plus cache-write plus output, charge
`input_tokens - cached_input_tokens`. Zero cache-write makes the two formulas
equivalent. Inconsistent totals, invalid counters or a negative ordinary-input
remainder make usage unavailable. Never add `reasoning_output_tokens`, which `output_tokens`
already contains (in the recorded three-arm rollouts input plus output
equals `total_tokens`). Calls and wall clock are an acceptable cost proxy
only when every compared candidate's provider calls resolve to one and the
same (model, effort) pair; a condition name is not that test, since
topology-only lets a child reuse any model or effort already in the parent.
Otherwise metering is mandatory: a candidate without metered cost has cost
`unavailable`, is not placed on the frontier and is reported as such, unless
this complete calls-proxy proof is available.

The readout's `price_table` is an object with `currency: "USD"`, positive finite
`tokens_per_unit`, nonempty `source`, ISO `date: "YYYY-MM-DD"`, and
`models: {model-id: {input, output, cache_read, cache_write}}`. Rates present in
the table must be finite nonnegative numbers; booleans are invalid. An absent
model or any missing rate category, even an empty model-rate object, makes that
model's cost unavailable. The table belongs to the criterion at readout, not
run configuration. No price or study table is selected by this design.

Calls may substitute only when complete static signatures and actual call
identity evidence agree on one model/effort pair for **every** compared
candidate. Actual proof joins existing call directories, complete unambiguous
native session identities and explicit effort in recorded `calls/<id>/argv.nul`.
Incomplete token counters may still permit that identity proof, but unknown
calls, uncovered nested sessions, contradictions or missing explicit effort
block the proxy globally. Never infer actual effort from a compiled policy or
CLI default. Current I3 evidence has no closed allocation signature and cannot
establish this proxy.

## Evaluation Hygiene

The harness rules apply unchanged: shims first on `PATH` under bubblewrap,
the exact Sonnet/Terra model guard with Claude subagents pinned and independent
Codex dispatch disabled, the contamination scan whose forbidden-model or
solution-prefix hits cannot be cleared,
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
| Episode | `criterion_sha256`, envelope, consumption or `unavailable`, `native_session_paths` or `unavailable`, shimmed CLI and model revision, interventions, outcome, refusal code, `scan_error` |
| Compile | `program_digest`, `build_key`, outcome, diagnostics class on rejection |
| Evaluation | `criterion_sha256`, `evaluation_id`, `task_id`, split, `evaluator_version`, `env_manifest_digest`, `run_id`, `state_dir`, resume count, outcome, consumption or `unavailable`, incidents, `scan_error`, local observations by site |

Hosted server model revisions remain `unavailable`; CLI versions are covered by
the environment manifest used in `evaluation_id`. An identity with an unchanged
hosted alias cannot establish that the server revision stayed fixed.

Successor criteria own their SHA-256 and explicit arm map. `I1/module` stays
separate from topology-only `I1`; no frozen Phase 1, Phase 2 or three-arm row is
reused under the successor. Continuation, subset selection, pools, judging and
readouts validate criterion hashes before collecting or spending. The shared
`config.check_criterion_hashes` permits missing row hashes only for the three exact
frozen Phase 1, Phase 2 and three-arm criterion hashes in `HISTORICAL_CRITERIA`;
explicit mismatches still refuse. The three-arm readout separately accepts a
missing compile-readout hash only under its exact historical three-arm criterion.
Successor records and compile readouts require matching hashes. The illustrative
`criteria/module.json` was removed; no committed successor criterion supplies
selection or launch permission. Its historical hash remains in the decision.

Episode/evaluation `allocation_signature` values map normalized static invocation
paths to `(provider, model, effort)`. Paths expand each resolved helper invocation
separately, retaining call position while normalizing coherent private renames;
they are not dynamic executions or branch counters. `allocation_changed` compares
the set of distinct `(provider, model, effort)` policies with the parent's set;
adding a call site that reuses an existing policy does not change that set.
Endpoint classes are `policy_only`, `structure_only`, `both`, `unchanged` and
`unknown`. Compare the recorded child/parent skeleton hashes to classify
structure independently from the policy-set comparison; missing policy or
skeleton evidence yields `unknown`. Static invocation paths remain diagnostic
rather than the comparison key. Missing/unresolved/recursive or ambiguous owner
evidence yields `unavailable` with a reason. Keep the source metric
`allocation_distinct` separately for collapse reporting.

Every ORC evaluation records `realized_perform_sites` from
`load_evaluated_view` over the validated memo: effect identity, class, attempt
count and status. The judged readout keeps these records beside physical
provider-call counts per evaluation. Memo effects do not identify exercised
source branches: `exercised_branches` is `unavailable`, with
`branch_coverage_reason: memo_records_effects_only`. A generic Python command
has `generic_command_has_no_orc_memo`; a run that never starts has
`run_not_started`. No branch instrumentation or missing-effect zero is inferred.

Malformed or truncated native transcripts that prevent contamination scanning
retain a `scan_error` diagnostic, `scan_pending: true` and unavailable
`scan_hits`; stale scan receipts are removed. These attempts cannot be cleared
or pooled without usable scan evidence. Evaluation outcomes become incidents,
with calls and realized effects retained. An already exhausted episode remains
exhausted unless a quota incident takes precedence; it yields no child.

## Controls, Interface Test And Ablations

| Condition | Question |
| --- | --- |
| Authored direct and planner/implementer seeds | Does structure earn its execution cost? |
| Finite authored catalog, enumerated | Is adaptive search needed in this neighborhood? |
| Prompt/provider tuning with fixed topology | Are gains settings and prompt changes? |
| Equal-budget unguided I1 sampling | Does feedback improve selection efficiency? |
| The same protocol delivered as an agent skill | Does a reusable program beat an instructed agent? |
| ORC structural search (I1, I2) | Can useful orchestration structure be discovered? |
| I1/module, under a successor criterion | What does coordinated private-module rewriting change relative to frozen controls? Offline preparation does not select a live comparison |
| Matched Python structural search (I3) | Does ORC improve the search process over a credible alternative? |

The first comparative experiment is the three-arm interface test: I3 Python
diff, I1 Lisp whole-program and I2 Lisp locus-plus-fragment on one benchmark
workflow, one model and one family, with completed episodes as the budget
unit. The delivered endpoints below supersede the prior offline successor's
failure-inclusive blind rubric means. The offline successor now implements
calibrated metered-cost endpoints; its scripted tests do not qualify a live study. Two pre-registered endpoints, each per completed episode: dominating
improvements, a child that dominates its parent on matched adaptive tasks
under the frozen rule (Objective, Selection And Local Observations), and
frontier entries, a child non-dominated against its own arm's parent and all
that arm's evaluated children, including earlier subsets in a continuation.
Recompute each arm independently; cross-arm candidates do not alter its frontier.
Distinct parents are admitted under every sharing arm before episodes, evaluated
once per unique identity on the declared tasks and replicates, and projected to
sharing arms without new observations. All candidates need the complete matched
task-by-replicate support; harness clone IDs, run labels and criterion hashes
bind the joins. The frontier entries are reported by candidate, and both endpoints are split by whether
the child changed its policies (`allocation_changed`: its set of distinct
(provider, model, effort) triples differs from the parent's), its structure
only or both. An added call site using a parent policy is not a policy change.
The readout exposes `policy_only`, `structure_only`, `both`, `unchanged` and
`unknown` classes using independent skeleton and policy-set evidence. Keep them
beside the collapse figure's `allocation_distinct`, which sees extern names
only; missing or contradictory classification evidence remains `unknown`.
Every terminal
non-quota episode (accepted, rejected, exhausted or incident) remains in the
completed denominator. Unvalued, contaminated or pending children cannot enter
quality numerators or a frontier; they remain visible and in that denominator.
Readout `pareto` contains `quality_floor`, `cost_axis`, `candidates` and `arms`.
Candidate rows report quality, metered cost, calls, selected cost, floor status,
reason and support. Each arm reports its parent, frontier, completed count,
improvement/frontier candidate lists and rates, unvalued children and allocation
splits. There is no pooled global frontier. The per-arm frozen-surface-workaround
figure reads operator `{verdict: "worked_around" | "asked" | "none", note: string}`
adjudications from episode records; absent or malformed rulings stay unadjudicated,
never clean, and this descriptive figure is not a selection gate.
Secondary: skeleton diversity and revisit rate, acceptance
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
([change note](workflow_lisp_program_search_boundaries.md#change-note));
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

A second amendment, 2026-10-19, replaced invariant 4: whole-program evidence
is deployment authority, and contextual fragment observations and
search-value estimates may guide proposal targeting, parent sampling and
exploratory retention but cannot alone establish whole-program quality,
validate a replacement or authorize promotion. It was applied under the
owner's cumulative workflow evolution extension; the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md#boundary-compliance)
carries that rationale, and the boundaries document's change note records
both amendments.

## Boundary Compliance

| Invariant | Driver |
| --- | --- |
| 1 Immutable generations, full compiler, registered runs, no eval | Satisfied under the 2026-10-18 amendment: external launch through public `run`; children are new snapshots compiled by the ordinary pipeline; each evaluation is a new public run; no eval, hot swap or checkpoint import |
| 2 Provider output is untrusted data | The final diff is data until validation and the compiler accept it |
| 3 Neutral substrate versus feature | Archive, selection, validation, transactions, skeleton hashing and fitness live in `experiments/`; the companion exposes read-only facts |
| 4 Whole-program evidence is deployment authority (amended 2026-10-19) | Frontier membership, finalist selection and promotion bind to whole-run evidence; local observations target proposals here and, under mode 3, may guide parent sampling and exploratory retention but cannot alone establish whole-program quality, validate a replacement or authorize promotion |
| 5 Evidence separation | Adaptive, validation and sealed held-out splits are disjoint; the sealed split opens once after generation, choice, evaluator and analysis freeze; near-duplicate defects share a split |
| 6 Honest security boundary | Satisfied under the 2026-10-18 amendment: ordinary configured sessions behind the comparison-harness shims, sandbox and contamination scan, reported as hygiene, not isolation |
| 7 Typed-operation parity without kind erasure | Interfaces move expressions, never runtime callables; provider calls, procedures and workflows stay distinct kinds |
| 8 Role-separated prompt identity | Inherited unchanged; prompt changes allowed only when the condition permits |

## What This Makes Harder

Sequential evaluation in separate clones is slow and disk-heavy. Cost
conclusions are proxies until provider usage is metered, and where the
model may change there are none without it. Lineage views are
rendered from the log, since external runs are joined by id. Frozen-surface
validation refuses legitimate declaration refactors in legacy conditions; the module condition permits private
refactors at the cost of weaker attribution and larger proposals. Family (b) needs a green baseline and
defect authoring; family (a) needs judge spend per evaluation. The interface
factor multiplies conditions, so the three-arm test precedes the ladder.

## Verification

Behavioral checks: a site resolves the right binding under shadowing; an
incompatible replacement is refused with `slot_type_changed` while two
structurally different valid replacements both compile and execute; frozen
surfaces survive a transaction and an unrelated edit in the same file is
refused with `scope_exceeded`; a helper colliding with an import is refused;
`candidate_id` ignores commentary, timestamps and parent and changes with
any source byte; a rejected proposal never enters task evaluation; realized effects are read from validated memo evidence while source-branch
coverage remains unavailable; the skeleton hash preserves its documented
rename/literal invariants and differs for a control-flow change; the final-choice rule refuses without a criterion
hash; a missing receipt serializes as `unavailable`; an incident resume
keeps its evaluation id; a child within both tolerances of its parent
neither dominates nor is dominated; a child below the quality floor stays
off the frontier however cheap; a candidate with cost `unavailable` stays
off the frontier and is reported; the frontier is the same whatever the
order candidates are offered in. One public compile/run integration check runs a
seed candidate through the launch form above with a scripted leaf and
scores it. No prompt-text assertions.

## Affected Surfaces And Handoff

New: `experiments/orc_structural_search/` and `tests/experiments/` coverage.
Reused: `experiments/compare/` shims, scan, pool and layout rules.
Prerequisites outside this design: an OMP shim before OMP sessions; the
harness extension above; the 2.39 catalog port; R2 qualification. Routing (`docs/index.md`,
`docs/design/README.md`, the capability matrix) belongs to the roadmap
change. This design accepts no allocation and selects no study.
