# Agent Authoring Improvements

- **Status:** draft, pending and unselected. This is a proposal, not authority
  to implement its workstreams. Record the owner decisions below first.
- **Purpose:** improve how often an agent given the documentation and CLI
  produces a correct `.orc` workflow, and how much correction that takes.
- **Authority:** `specs/` owns current behavior; [evaluated execution](../design/workflow_lisp_evaluated_execution.md)
  and its [delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md)
  own target 2.35 and its release order. [EL-1](../design/workflow_lisp_effect_ledger_simplification.md)
  owns the delivered target-2.39 effect contract; AA trials remain unselected.
- **Copy safety:** the new guide, remedy field and `simulate` command below
  do not exist. Use the [drafting guide](../lisp_workflow_drafting_guide.md),
  `orchestrator compile --diagnostics-json` and `orchestrator run --dry-run`
  today. Targets 2.35–2.39 use the evaluated runtime; follow the
  [current target-2.39 recipe](../lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239)
  and capability limits rather than treating this proposal as a release gate.
- **Selection and progress:** [roadmap AA-1](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#aa-1--agent-authoring-improvements-pending-unselected).

## 1. The smallest useful change

Keep four independently useful workstreams: one current authoring guide,
diagnostics that explain a repair, an evaluator-backed outcome preview, and
inferred effects. Measure each against the same baseline before enlarging it.
Do not require a general quick-fix framework, exhaustive scenario generator,
or new effect representation to deliver those benefits.

| Workstream | First useful result | Dependency after selection |
| --- | --- | --- |
| A: guide | A short single-target guide and checked examples | Baseline trial; use the latest runnable target |
| B: remedies | Actionable guidance for codes authors actually encounter | Baseline codes; diagnostics compatibility decision |
| C: outcome preview | Bounded synthetic outcomes run through the real evaluator without launches | Phase 2 type descriptors; Phase 3 evaluator and performer seam for execution |
| D: effects | Measure authoring with delivered inference-default restrictions | Reuse EL-1 at 2.39; AA baseline/trial selection and budget remain required |

No workstream changes 2.35's first-release scope. B need not spend effort on
flat-route refusals the evaluated route removes. C has no flat-route version.
Checked evaluation of generated source is a separate [proposal](../design/workflow_lisp_checked_program_evaluation.md),
not a prerequisite for any of these workstreams.

## 2. A: one guide for the target an author can run

Proposed locations are `docs/agent_authoring_guide.md` and
`workflows/agent_examples/`. Add `LATEST_AUTHORING_TARGET` in
`orchestrator/workflow_lisp/syntax.py` so the guide and examples name the
latest **runnable** target, independently of versions accepted by the parser.
Current authoring can use 2.39 within its documented capability limits;
pre-2.35 source is no longer admitted. Use the selected runnable target in
the selected implementation checkout. Update the constant, guide and
examples together when a newer target becomes runnable; this does not
default an omitted source header.

Keep the guide short enough to read before authoring. State its target once,
omit target history and compiler internals, and teach only that target's
available behavior. Cover the file skeleton; typed records, unions, enums and
paths; provider and command result contracts; `match` and typed conditions;
pure values; bounded repetition; and the distinct roles of `defworkflow`,
`defproc` and `defun`. Show when the existing review/revise, `improve` and
drain helpers save work. Explain the supported alternatives to recursion,
runtime procedure values and unsupported parallel effects.

Use a small example set that covers real compositions rather than one file
per language feature. Together it must show:

- a typed provider result, a union success/blocked outcome and enum routing;
- a certified command adapter and a path-typed producer/consumer handoff;
- review/revise, candidate generation with a judge, and a bounded state loop
  including exhaustion;
- a reusable procedure with a `ProcRef` hook and a pure helper;
- a contract failure that stops safely, followed by resume without repeating
  committed work.

Choose effect classes within 2.35's admitted first release: commands,
portable providers, calls and path-mode run references. The guide can point
once to the drafting guide for human input, trials, sessions and resource
transitions. Keep the drafting guide as the maintainer reference.

Quote source only from checked example files, with a quote-to-file check
for the new guide's examples. Historical program-shape behavior remains
covered by `tests/test_workflow_lisp_guide_programs.py`.
Route `AGENTS.md`, `CLAUDE.md` and `docs/index.md` to the new guide once it
exists. Until then their authoring entry stays on the drafting guide.

**Evidence:** collect every example, check its header against the constant,
compile it through `--diagnostics-json`, and run `--dry-run` with its required
inputs. The failure/resume example additionally needs a public CLI integration
fixture; dry-run alone cannot establish recovery. Check that the prose does
not teach other targets. After C lands, record each example's actual outcome
and branch coverage, supplementing it with scenarios where useful. Judge the
guide by the authoring trial, not a fixed line or example count.

## 3. B: tell the author what to change

Attach a remedy when diagnostics are collected for output. Start with a
small code-to-builder mapping for the baseline's most frequent refusals and
the surviving typecheck errors: unknown names/fields, variant proof, operand
types, equality restrictions, loop budgets, recursion and path contracts.
Use the drafting guide's supported alternatives and known-defect examples.
Add structured facts at an individual raise site only when the remedy needs
information absent from the diagnostic; do not parse prose as authority.

A remedy needs a short action and a classification: an author error, an
intentional language restriction, or a compiler limitation. A corrected form
or guide link is useful when it makes the action clearer. Compiler defects
must say that the program hit a compiler problem and give a known workaround
or reporting route; they must not blame the author.

The current `workflow_lisp_compile_diagnostics.v1` boundary is closed:
`orchestrator/workflow/run_ref/child.py` validates exact document and row
shapes, and `specs/dsl.md` specifies that boundary. Preserve its output for
existing consumers. Recommend a v2 document for structured remedies; decide
the public selection mechanism and migrate consumers explicitly before
changing defaults. Human-readable remedies can ship independently if that
avoids blocking useful guidance on a schema migration.

Automatic edits and LSP quick fixes are optional follow-ups, driven by a
demonstrated repair case. A future edit must be local, preserve meaning and
be recompiled in memory before it is offered: the original diagnostic must
disappear without introducing an earlier error. A guessed name or a stub
`match` arm is not automatically safe. No registry of every historical code,
editor framework, or required expansion of every raise site precedes the
first useful remedies.

**Evidence:** failing/fixed fixture pairs establish the code and remedy kind
and compile the corrected form through the public CLI. Test classifications
and repair behavior, not exact wording. List trial codes that remain without
a remedy, and add coverage as they recur. The trial records whether the
guidance actually reduces correction iterations.

## 4. C: preview outcomes without launching effects

Propose a separate `orchestrator simulate` command for the evaluated route,
with the usual entry and input selection, an optional scenario file, a
scenario cap and text/JSON output. Targets below 2.35 are refused. This is
an authoring tool for routing and handling; it does not check prompt quality,
real command behavior or file contents.

Reuse the closed program and evaluator. Replace external performers with
synthetic results that pass through the ordinary result contract validator.
Calls remain evaluation. At a path-mode run reference, synthesize the
declared child result without starting a child. Assemble prompts normally
to catch missing assets and bad fills, then discard them without delivery.
If an operation cannot be simulated safely, refuse it before dispatch.

Read real workspace inputs, but direct every write, memo, attempt and
placeholder artifact to a scratch root. Normal `resume` must refuse a
simulation. Path-type synthesis needs an explicit mapping from declared
roots to scratch roots, including absolute roots: retaining a production
path and writing a placeholder there is forbidden. Qualify that mapping
before promising path coverage. Workspace comparison excludes only the
documented simulation scratch root and must otherwise be byte-identical.

Synthesize deterministic baseline values from the declared types: first
union/enum member, false, one-element collections, a present optional,
small numeric/string values and recursively populated records. Try the
other union/enum members, true, absent optional, empty collections and zero
one factor at a time. For a site inside a loop, a site assignment holds
across its activations; a scenario may override a specific activation.
Use the type's existing wire format, not a parallel value encoding.

Bound the planner and report truncation. It may miss branches requiring a
combination of values, a threshold, or a different outcome on successive
iterations. A validated scenario file keyed by site or existing effect
identity supplies those cases. Unreached sites are uncovered, not proven
unreachable. A report of tested alternatives must never claim that every
branch or valid value has been explored.

Record each scenario's assignments, ordered effect identities and final
value or located failure. Add evaluator observations for branches and loop
exits, keyed by existing node provenance, and show uncovered items first.
Keep generated IDs, scratch paths and timing out of canonical JSON so that
the same inputs yield the same report. Measure elapsed time separately.

**Evidence:** launch traps prove zero provider/command/child launches;
workspace comparisons prove write isolation; repeated runs produce identical
JSON. Seed a wrong outcome route, an empty/zero pure fault and an unintended
exhaustion result, and show them in reports checked against fixture
expectations. Cover examples with the planner plus targeted scenarios and
explain remaining gaps. Record latency and authoring-trial benefit before
adding a more ambitious search strategy.

## 5. D: Measure The Delivered Inferred-Effects Contract

Reuse delivered EL-1 at target 2.39 rather than planning another inference
implementation or target allocation. Its contract infers the fully resolved
transitive effect set `I`:

| Authored clause | Contract |
| --- | --- |
| Omitted | Infer `I`; no authored restriction |
| `:effects ()` | Require `I` to be empty |
| `:effects D` | Require `I` to be a subset of `D` |

Preserve atom kinds and resolved subject identities. Procedure calls
contribute their bodies' effects, not procedure-call edges; workflow calls
retain the tracked dependencies required by EL-1. Check after generic and `ProcRef`
specialization, locating a violation at the responsible use and retaining
the declaration's origin. Keep older targets' exact-clause rules unchanged.
Use the existing compiler-derived REPL/LSP inspection described by EL-1;
B’s proposed remedy/schema changes remain separately unselected.

Review migrated clauses against the fully specialized transitive set: an
old forwarding empty clause is not a purity proof in the new regime. Teach
omission in A when using 2.39. Reuse EL-1’s resolution, origin and
specialization evidence, including an effectful hook violating an empty
bound; preserve admitted old-origin compatibility. AA still needs a
separately selected trial to measure annotation removal and authoring benefit;
no new internal effect-analysis rewrite follows.

## 6. Measure before and after

Before any workstream lands, the owner fixes a task selection rule and a
cost budget, then selects a small set of unattended multi-step workflows
with failure outcomes within A's scope. Run fresh agent sessions with only
the guide in force, task statement and CLI; keep model and budget comparable.
Count total cost, including attempted workflow runs.

Record first-compile success, iterations to compilation, every diagnostic
code, and correctness under declared outcomes, malformed/missing results
and interruption followed by resume. Once C exists, record coverage before
submission as well. Preserve task statements, generated programs and grading
inputs so a faster compile cannot disguise incorrect behavior.

Repeat after each workstream, recording confounders when changes overlap.
Put results in `docs/reports/`, including negative results. These trials can
serve the later `.orc`-versus-Python comparison; that comparison is not a
prerequisite for useful authoring changes.

## 7. Decisions and verification

The owner still needs to select workstreams, confirm guide/example locations,
decide diagnostics schema migration, accept the separate evaluated-only
simulation command, and set the trial’s task rule and budget. EL-1 is
delivered at 2.39; this proposal neither reselects it nor treats that delivery
as AA trial acceptance. No missing AA decision is inferred from this update.

For selected implementation, follow `AGENTS.md`: narrow pytest selectors
first, collect new/renamed test modules, then the broad suite with
`pytest -q -n 16 --dist=worksteal` in tmux. Include a public CLI check for
each frontend/runtime change and use fresh output as evidence.

The smaller scope leaves editor automation, exhaustive code coverage and
multi-factor scenario search for demonstrated demand. Authors may still
need manual repairs and targeted scenarios; no initial result depends on
building those frameworks first.
