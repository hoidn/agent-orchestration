# ORC Structural Search Experiment

## Metadata

- **Status:** proposed (2026-10-17); selects no study or budget
- **Kind:** experiment design
- **Owner:** experiment maintainers
- **Reviewers:** one independent design reviewer
- **Created / last material update:** 2026-10-17
- **Related:** [charter](../plans/2026-09-08-orc-research-charter.md) (thesis, hypotheses, decision rule);
  [Experiment O](orc_reuse_introspection_search_experiment.md#experiment-o--program-space-then-search) (extended, not superseded);
  [program-search boundaries](workflow_lisp_program_search_boundaries.md) and their
  [proposed amendment](workflow_lisp_program_search_boundaries.md#proposed-amendment-2026-10-17);
  [comparison harness](orc_effectiveness_comparison_harness.md) and [README](../../experiments/compare/README.md);
  [source-site inspection](workflow_lisp_source_site_inspection.md) (the frontend component this design consumes);
  [roadmap](../plans/2026-10-17-orc-structural-search-roadmap.md) (sequencing, gates, budgets)
- **Implementation target:** candidates at target 2.39; imported 2.35–2.38 modules keep their contracts. Experiment-local code under `experiments/orc_structural_search/`; nothing under `orchestrator/` carries search concepts.

## Summary

An external Python controller runs ordinary coding-agent sessions that edit the
authored source of an immutable parent candidate, compiles each proposal with
the full ordinary compiler, executes accepted candidates as fresh registered
runs behind the comparison harness, and selects on whole-run evidence. The
compiler is a free, exact admissibility filter; it supplies no fitness. The
proposal interface (what the agent is asked to emit) is an explicit
experimental axis. The search objective is hidden acceptance; the sealed
assessment uses the blind rubric with anchors.

## Context And Authority

| Authority | What it fixes here |
| --- | --- |
| Charter, Five Independently Falsifiable Hypotheses and Decision Rule | The claims below map onto those hypotheses; a DIRECT winner is valid; credible Python/native and agent-skill controls precede any ORC-specific claim |
| Experiment O (existing design) | Finite catalog before search; testable GP properties (closure, behavioral locality, compositional utility, manageable interactions, affordable selection); invalid proposals consume proposal budget |
| Boundaries §1–§8 | Immutable candidates, full compilation, no `eval`, neutral substrate, whole-candidate evidence, evidence separation, role-separated prompt identity. §1 and §6 as amended once the amendment is approved; until then this design is not executable |
| Harness design and README | Shims, sandbox, model guard, scan and adjudication, task packages, blind pooling, criterion hashing, `summarize` measures; the model policy and evaluation policy of 2026-10-15 |
| Design lessons | Every evaluation rule of its "Evaluating A Workflow" table |
| `specs/cli.md` and `orchestrator/cli/commands/compile.py` | `compile --diagnostics-json`: success is `{"build_key","program_digest","status":"accepted"}`; rejection is `workflow_lisp_compile_diagnostics.v1` with `code`, `path`, `line`, `column`, `phase`, `form_path`, `expansion_stack`, `message`; `explain`, every `--emit-*` flag and `trial` refuse |
| `specs/versioning.md`, target 2.39 | New `defproc`s omit `:effects` for inference and reject authored `:lowering`; phased delivery is excluded from the mutable vocabulary |

Facts verified on 2026-10-17 against main `90ae778c`: `program_digest` is unchanged
by a comment line, and changed by a `let*` binding rename and by a literal change
(the closed program keeps authored binding names); `build_key` changes with any
source byte. The REPL's `:browse` prints the loaded snapshot's sha256; `:type`
typechecks an expression in module context without creating a run.

## Claims And Hypotheses

| Claim | Charter hypothesis | Evidence that supports it | Not evidence |
| --- | --- | --- | --- |
| Structural feasibility | Self-programmability | Agents produce previously unlisted working compositions through ordinary editing and full compilation | Compile acceptance alone |
| Useful search space | Program-space optimization (bounded variation) | Structurally distinct candidates show whole-run quality/cost differences beyond the within-arm spread on independent tasks | A fixed arm beating DIRECT on one task |
| Adaptive optimization | Program-space optimization (adaptive search) | Feedback-guided search beats feedback-free proposal and the enumerated catalog at equal evaluation counts on the validation split, confirmed on the sealed split | Training-set improvement |
| Compiler assistance | Introspection | Pre-supplied typed site context or diagnostics raise acceptance per episode, edit locality or final outcome against the whole-program and no-feedback arms; tool-retrieved exposure is reported | Any claim before the manifest exists; until then the three-arm study's compile-only metrics are its proxy |
| ORC-specific value | Programmability / compositionality; Reusability | The matched Python and agent-skill controls show a search, transformation-reliability or integration disadvantage, named | ORC search succeeding without those controls |
| Compositional evolution | Program-space optimization (recombination) | Extracted fragments transfer and recombine usefully across contexts (Phase 4) | Type-compatible insertion compiling |

## Search Space And Proposal Interface

The initial family exercises model allocation and feedback placement. The
policies are the Phase 0 catalog; they map onto existing seeds and are
examples of a neighborhood, not a menu imposed on the mutator.

| Policy | Structural choice | Seed |
| --- | --- | --- |
| Direct implementation | Remove stages whose benefit does not justify cost | `experiments/compare/control/direct_task.orc` |
| Strong plan → cheap implementation | Expensive inference before implementation | `workflows/examples/design_review_execute.orc`, `plan_review_execute.orc` |
| Implement → review → revise when requested | An intermediate decision and a repair branch | `experiments/orc_vs_single_call/workflows/reviewed_change.orc`; `std/improve` |
| Cheap implementation → tests → strong diagnosis on failure → cheap repair | Expensive inference after evidence | Authored in Phase 0 from the above |
| Plan each subtask → implement each → integration test | Planning granularity | Authored in Phase 0 |
| Generate N → select | Independent candidates with a judge | `experiments/orc_vs_single_call/workflows/best_of_n.orc` |

Every seed is at 2.35 today; Phase 0 retargets the chosen seed module to 2.39
so mutator-added `defproc`s need no authored `:effects`, removes any authored
`:lowering`, and records the compile. Phased delivery and 2.38 agent sessions
are outside the initial mutable surface; agent sessions are a later vocabulary
expansion for context-transfer policies.

Mutable surface (initial): one value-producing expression in an existing
workflow or procedure; its sequencing, conditionals, compatible calls and
bounded repetition; provider selection from the configured set; prompt wording
only in the prompt-only and joint conditions; local helper declarations in the
same transaction. Frozen: the exported entry signature, task/result protocol,
evaluator, command interfaces, tools, environment, imports and type/protocol
declarations. Effect summaries constrain kinds of operations, not call counts,
cost, termination or correctness; runtime envelopes stay necessary.

Proposal interface, an explicit axis. Ordered from what the agent must keep
globally well-formed to what the compiler owns:

| Interface | Agent emits | Needs | Phase |
| --- | --- | --- | --- |
| Whole program | A complete replacement module | Compile only | 0 (three-arm) |
| Textual diff | A patch to the authored file | Compile only | 0 (Python control's form) |
| Locus + typed fragment | One replacement expression for a selected site, plus declared helpers | Site facts from REPL `:info`/`:source` in Phase 0; the source-site manifest and transaction from Phase 1 | 0 (three-arm), 1–3 |
| Typed hole | A fill for a hole the controller chose, with its expected type and environment | The manifest | 4 |
| Ranked classical candidates | A choice among compiler-generated type-compatible candidates | The manifest and a generator | 4 |
| Named certified rewrite | A rewrite name and its arguments ("wrap in bounded retry", "insert a critic") | Source templates over existing library procedures | 4 |

## Mutator Sessions And Search Loop

The mutator is a normal installed Codex or OMP session with its configured
tools, project instructions, skills, documentation, context management and LSP.
It receives the candidate workspace, the objective, the mutable scope, the
selected site with its compiler facts, and development feedback; it may
inspect code, compile, test and debug inside a finite time and call envelope.
A proposal is one completed session producing a snapshot; internal tool calls
and compile repairs are part of that episode, not separate milestones, and no
two-edit cutoff replaces the envelope. A `--no-tools`, compiler-only or
source-only mutator is a disclosed ablation, never the default. ORC and Python
mutators receive comparable facilities and budgets.

The loop: select a parent from an incumbent plus a small archive (four to
eight candidates spanning the quality/cost frontier); select a site, uniformly
at first; run the episode; compile; on acceptance evaluate the whole candidate
on the screening tasks; retain by the selection rule; record the episode
whatever its outcome. Edit intentions offered to the agent (insert a review or
repair stage, move stronger-model effort from planning to diagnosis, delete a
stage, change an escalation condition, replace a call with a larger composition
of the same type) are prompts, not a menu of prewritten workflows.

## Genome

The authored `.orc` surface is the genome; the closed program
(`workflow-lisp/closed-program/1`, representation `table/1`) is the executable
identity; they do not round-trip. No printer from closed nodes or frontend
`ExprNode`s to `.orc` exists, the reader drops comments, and the closed form is
lowered with compiler temporaries. Edits are span splices on the authored
snapshot, validated by re-reading and by the full compiler
([source-site design](workflow_lisp_source_site_inspection.md#edit-transaction-and-scope-validation)).

## Task-Family Qualification

Reuse the frozen calibration rule: mean review blockers on single-call patches
at least 1 over two patches, with one more sample when the mean is in
[1, 1.5); hidden fraction is reported and never qualifies. The first family is
one of calibration rungs 1, 2 or 4 (qualified on recorded samples), rung 3
after its third sample, or a new family qualified by the same rule and built in
the harness package layout. Qualification by blockers does not give the
objective headroom: on rung 1 single calls already pass 0.90–0.94 of hidden
nodes. Phase 0 reports headroom before choosing. Near-duplicate tasks and
variants of one defect stay in one split. Development checks the agent can run
are never the objective.

## Evaluator, Objective And Selection Rule

Hidden acceptance (the package's hidden node set, each node alone, the
package's dropped-node rules, `summarize.hidden_failures`) is the search
objective and the selection measure during the adaptive and validation stages:
it is automatic, local and cheap. The sealed assessment's primary measure is the
blind rubric with repeated anchors and two judges, hidden acceptance reported
descriptively, as the owner's evaluation policy of 2026-10-15 requires; the
final claim therefore does not depart from that policy. Both are stated because
a search loop needs an automatic objective and the measured judges do not track
hidden acceptance (E-B2: r = 0.64, the upstream reference scored below arm
patches in one batch; E-B3: the judges disagreed on the sign of the revision
gain).

Selection rule, frozen before adaptive work: highest validation hidden mean
under a stated mean-cost ceiling (calls and wall clock per run), then lower cost
among candidates within a predeclared tolerance in hidden-fraction units derived
from the measured within-arm SD (0.13–0.16 on rung 3; measured per family in
Phase 0). Screening is a conservative filter: with one replicate per task,
differences below about two SD are noise; advance fewer candidates and replicate
finalists at least three times; report the shrinkage from screening to
validation (winner's curse). A task failure, invalid submission or timeout is
an outcome; its cost counts. Deployed-workflow cost is tracked apart from search
cost; the break-even form `break_even_uses = additional_search_cost /
saving_per_deployed_use` applies only when quality is comparable, and its
inputs are reported in the accounting units below.

## Splits And Contamination Channels

Three disjoint task groups: adaptive (drives mutation and screening), validation
(chooses among produced candidates; never feeds mutation in the same study),
sealed (opened after candidate generation, selection and analysis freeze).
Development checks visible to agents are not the hidden set.

Every provider call (mutator, candidate, judge) runs behind the harness shims
and bubblewrap sandbox with the model guard. The disclosed isolation boundary
is the harness's: private `/tmp`, `/dev/shm`, PID namespace and empty `/var/tmp`;
home, the network and other sessions' transcripts are shared and detected, not
prevented. Search adds channels the scan does not know; the scan gains these
patterns:

| Channel | Pattern added |
| --- | --- |
| The candidate archive and lineage/score records | archive root; `lineage.jsonl`, `episodes.jsonl`, score files |
| The validation and sealed task lists and packages | holdout roots and package names |
| Prior candidates' workspaces and build caches | other candidates' tree names |

A task agent that reads the archive learns which policy scored well; a mutator
that reads the sealed set contaminates the holdout. Either is a contamination
verdict under D5. The stale editable install and sibling worktrees are covered
by the existing main-prefix pattern.

## Controls Ladder

| Arm | Question | Definition |
| --- | --- | --- |
| DIRECT | Does structure earn its execution cost? | `control/direct_task.orc` |
| Authored catalog | Is adaptive search necessary? | The Phase 0 policies, enumerated, best by validation |
| Prompt/provider tuning, fixed topology | Are gains settings changes? | Same mutator and envelope; mutable surface restricted to prompt bodies and provider/model options |
| Random | Does feedback improve selection efficiency? | Same mutator, uniform site selection, no run feedback in its context, same episode envelope and evaluation count |
| Agent skill | Is the protocol ORC-specific? | The same protocol written as a skill document for one agent, same model and budget, run as a generic-command arm |
| ORC structural search | Treatment | This design |
| Matched typed Python structural search | Does ORC improve the search process? | Same shims, evaluator, splits, models, tools, limits; idiomatic reusable Python, Pydantic-or-equivalent schemas, AST tooling and a real type checker; internal composition edits allowed; recovery responsibilities matched or the asymmetry disclosed |

Comparisons use equal evaluation counts and equal episode envelopes, not equal
metered expenditure. Prompt-only, topology-only and joint conditions answer
different questions and are reported separately. The two assistance ablations
(omit pre-supplied typed site context; omit pre-supplied diagnostics) are the
whole-program and no-feedback arms of the three-arm study and run there first;
ordinary compiler tools stay available in every arm and what agents retrieve
themselves is recorded.

## Three-Arm Proposal-Interface Study

Early and cheap: one seed workflow, one model, matched episode envelopes, `E₀`
episodes per arm.

| Arm | Form |
| --- | --- |
| Python diffs | The seed policy as Python; the agent emits a patch; admissibility = import, schema validation of the arm interface and the type checker |
| Lisp whole program | The agent emits a complete module; admissibility = full compile |
| Lisp locus + fragment | The agent receives one site and emits one replacement. Site facts in Phase 0 come from the REPL: span, enclosing definition and declaration-level facts from `:info`/`:source`; the inferred type and effects from `:type` only for a site whose expression typechecks in module context, because `:type` has no lexical values without an attached run and a `let*`-bound name is `name_unknown` there. Sites whose expression references such names carry no type in Phase 0; the readout states which sites did. Admissibility = full compile; locality checked by an experiment-local reader-tree comparison outside the site's span |

Compile-only metrics, no paid evaluation: acceptance per episode; edit locality
(changed spans outside the selected site; for whole-program and Python arms,
hunks outside the site's span); structural distinctness (distinct skeletons
among accepted proposals; exact repeats by `program_digest`). Paid whole-run
evaluation only on a stratified subset of accepted proposals, to give cost per
accepted improvement. Admissibility differs by language and is reported per arm,
not pooled.

## Diversity Metric And Collapse Stop Rule

Skeleton projection, experiment-local, over the closed program: keep each
node's `k`, each `perform` node's `class` and its `provider` (the extern
binding, so a provider swap is structural), and the `case`/`select`/`loop`
structure; drop `lit` values, prompt text, the `policy` values (model, effort,
delivery, whether `lit` or `name` nodes), `let` names and `@` provenance. Two
candidates are structurally distinct when their skeletons differ; exact semantic
repeats are deduplicated by `program_digest`, which is rename-sensitive and so
is not the diversity measure. The Python arm uses the analogous projection over
its `ast` with names and literals dropped.

Readout per search run and per interface: distinct skeletons among accepted
candidates; the share whose skeleton equals their parent's. Stop rule,
predeclared: if that share exceeds the threshold (default 0.75), the interface
has collapsed to renames and literals, the Adaptive-optimization claim is not
tested on that run, and the run is reported as collapsed.

## Identities And Minimum Records

| Identity | Meaning |
| --- | --- |
| Candidate ID | Content address of the immutable snapshot: source bytes, imported dependency digests, entry, provider/prompt bindings, compiler/runtime/configuration versions |
| Program digest | `program_digest` of the closed program: semantic identity modulo provenance; formatting-invariant, rename-sensitive |
| Search site ID | A locator within one candidate's source (file, span, enclosing definition, form path) |
| Runtime site / invocation identity | The closed program's `(owner, "#n")` site rows plus activation context; execution identity, not fragment lineage |
| Lineage record | Parent, edited sites, declared helpers, hypothesis, run id and state root of every evaluation (as `record.json` names `state_root` and `runtime_commit`); the runtime is not changed |
| Evaluation ID | Candidate, task, evaluator and environment version, settings, replicate |

Parent IDs, commentary, timestamps and scores are lineage metadata and do not
change a candidate's identity. Hosted model revisions are recorded where
available. Fresh runs across candidates; no cross-candidate effect reuse; a
cached evaluation is not a replicate. Minimum retained records: candidate
source and configuration, parent and edit, compile outcome, task/replicate/
evaluator identity, run id and state root, final outcome, calls and wall clock,
session-file tokens where read, missing-data indicators, substantive
interventions. Storage is immutable candidate files plus append-only JSONL
episode and evaluation logs.

## Cost Accounting

The accounting record per call is: calls, wall clock, and tokens read from
session files where a reader exists; `UNKNOWN` otherwise. Named proxies:
Claude session JSONL `message.usage` (parsed by `experiments/compare/scan.py::claude_sessions`
and `orchestrator/providers/native_store_claude.py`); Codex rollouts under
`~/.codex/sessions` are located by the scan, their token events unverified.
Dollars for subscription CLIs are not recoverable; Codex weekly-window and
credit readings are account-wide and reported as bounds. Search cost includes
mutator work, compile and debugging episodes, evaluations, retries, rejected
proposals, preparation and substantive human assistance. Missing receipts are
unavailable, never zero.

## Harness Reuse And Required Extension

Reused unchanged: `prepare.py` (`run`, `collect`, `scan`, `pool`, `verify-pool`),
`repos.py`, `pool.py`, `scan.py`, `summarize.py`, the shims and model guard, the
criterion template and hashing, task packages and the stand-in agent CLI of
`tests/experiments/compare_harness_support.py` for plumbing checks.

Required extension (Phase 0), in `experiments/compare/`:

| Change | Why |
| --- | --- |
| Arm spec from a candidate root: `(source, entry workflow, source root, providers file, typed inputs)` resolved against a candidate directory instead of `prepare.py::ARMS`'s paths in the runtime checkout | A candidate's `.orc` lives in its own immutable root; compile needs `--source-root <candidate root>` and a module path matching the file |
| Generic-command arm: a recorded command run behind the shims with the same inputs and collection | Python and skill controls |
| Scan patterns for archive, lineage/score records and holdout paths | The channels above |

## What Compile Acceptance Establishes

The compiler can reject invalid bindings, incompatible types, malformed
composition, and violations of supported effect/contracts. Acceptance
establishes static admissibility under current language rules.

Acceptance does not establish a useful strategy, semantic equivalence, correct
scientific reasoning, a better answer, or cheaper execution. A well-typed
reviewer that always approves still needs outcome evaluation.

Corollaries: the compiler is a free, exact admissibility filter that removes
invalid proposals before paid evaluation, not a reward; DIRECT and a
constant-returning workflow both pass. Hacking resistance comes from the
evaluation harness (hidden tests outside the workspace, sandbox, scan), not from
runtime contracts, which contribute lineage. Type compatibility is necessary,
not sufficient, for substitution (boundaries §7).

## Local Observations

Local feedback is stored outside authored programs, keyed by candidate, source
site, runtime invocation if reached, task and evaluator version. Three things
are distinct: an output assessment (was this review useful under a rubric), a
diagnostic targeting signal (which expression the mutator should investigate),
and an intervention estimate (how whole-run outcomes changed when the expression
was replaced). Only the third estimates a contextual contribution, with sampling
uncertainty. A local score is not a fragment's fitness; a branch not taken has
no score; recombined fragments do not inherit parents' fitness. The MVP starts
with diagnostics already in run evidence and compares uniform targeting with
local-feedback targeting later.

## Fragment Contract (Phase 4)

An archived fragment carries formal inputs for its free bindings with canonical
types, result type and path obligations, resolved prompt/provider/module/command
dependencies, operation kind and effect requirements, and its origin and
contextual evidence. Insertion requires an explicit input mapping, hygienic
renaming (capture analysis by `expression_traversal.free_expr_names`), compatible
nominal types and dependencies, and full recompilation in the destination.
Begin with explicitly parameterized procedures and source templates; then
extraction for a documented subset of value-producing expressions, excluding
nonlocal control, unresolved captures and lifecycle-sensitive values. Procedures,
workflows and provider calls stay distinct kinds.

## Related Work

Background only; details as given by the inputs. Strongly typed GP (Montana,
1995) and PolyGP (Yu and Clack) constrain operators by type; grammar-guided GP
(Whigham) and Grammatical Evolution (O'Neill and Ryan) by grammar; Push
(Spector) by typed stacks; Cartesian GP fixes topology. ELM, FunSearch and
AlphaEvolve use an LLM as the mutation operator over Python. Automated Design
of Agentic Systems (Hu, Lu and Clune, arXiv 2408.08435) searches agent
implementations with a meta-agent and an archive; the general agent-search idea
is not claimed as novel here. GEPA (optimize_anything,
https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/)
is an unverified external option whose scope the two owner inputs describe
differently; adopting it is a new dependency under the repository's tooling
rule. "Mutation Without Variation" (LLM mutations over a Lisp-like DSL collapsing
to renames) is an unverified citation; the collapse risk it names is handled by
the stop rule above regardless. The repository's own historical evolution
substrate design and the MLEvolve architecture are historical.

## Non-Goals

No optimizer vocabulary in `orchestrator/`; no `eval`, hot swap or candidate
mode; no population database, dashboard, distributed scheduler or attribution
algorithm as prerequisites; no revival of `trial` or the flat route; no claim
from compile acceptance; no second family to replace unfavorable results.

## Verification

Behavioral checks the implementation owes, in the experiment-local package and
its tests: an incompatible replacement is refused and two structurally different
valid replacements both compile and execute; frozen entry/protocol/evaluator
boundaries survive a transaction and an unrelated edit in the same file is
refused; execution uses the accepted candidate and pinned dependencies with
fresh state; a provider call in an unexecuted branch has no local score; a
deterministic-leaf run distinguishes a bad policy while accepting several
correct structures; the skeleton projection separates a rename from a structure
change and the digest separates a comment from a literal; the scan flags a read
of the archive or holdout. Plumbing through the stand-in agent CLI, then a live
smoke before any criterion freezes.

## Open Questions

| Question | Owner | Blocks |
| --- | --- | --- |
| Approval of the boundaries amendment (§1, §6) | Owner | Any execution |
| Family and headroom tolerance | Owner, at Phase 0 selection | Phase 0 |
| Whether Codex rollout token events are readable as a proxy | Phase 0 cost calibration | Token columns only |
| Whether the locus arm needs the Phase 1 manifest to avoid collapse | Three-arm study | Phase 1 scope |
