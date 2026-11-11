# Conceptual review: `docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md`

Task id: `review_plan_roadmap_conceptual`. Role: reviewer, read-only. Artifact: draft roadmap (plan).
Evidence marks: **[V]** verified by reading the cited file at the cited lines (repo at `main`, 2026-11-11);
**[I]** inferred by reasoning from verified facts; **[A]** taken from the audit notes and not independently
verified. No tests, provider calls or probes were run. Paths are relative to
`/home/ollie/Documents/agent-orchestration` unless absolute. "Roadmap" means the artifact under review.

## Verdict

The roadmap is a sound engineering clean-up plan (Phases 0–2) attached to a research plan that cannot settle
the claims it lists. Its three-claim split is clearer than what came before, but the claim it "stands on"
(engineering) is stated as a capability and never tested as a value proposition, although it carries the whole
ordering argument and the repository holds parity evidence against it. The centre of gravity, "memo as build
cache" (Phase 3), borrows a model that needs hermetic effects; the accepted design says agent effects are not
hermetic, and the phase's stop-rule fallback ships exactly the half the design calls unsound while its exit
test passes without the target mechanism. The quality gate (Phase 5) is not the Pareto rule the project
adopted, is predisposed to a null by the project's own lessons, and gates an evolution phase (Phase 6) whose
free first step is a strawman and whose paid step lacks the controls needed to attribute a win to search or to
typed programs. The order defers the two cheapest, most decision-relevant items (the zero-spend benchmark
steps and naming a consumer) behind three phases of capability built ahead of a consumer, which is the failure
pattern the audit itself diagnosed. I recommend not selecting it as written: keep Phases 0–2, rewrite Phase 3
around prefix reuse, pull the zero-spend measurement and the consumer to the front, and restate the claims so
that each has a test that can fail.

Findings: 2 blockers, 6 major, 8 minor.

---

## Findings, most severe first

### B1 (blocker). The engineering claim is unfalsifiable as written, yet it justifies the order

**Section:** Claims (l.21–28); Phase 5 exit test (l.157–159); Owner decision 2 (l.223–224).

**Evidence.**

- The claim reads "long, expensive, multi-agent pipelines get typed handoffs, exact resume and an audit
  trail", state "Supported by the runtime", tested in "Phases 1–4" (roadmap l.23) **[V]**. Phases 1–4 have
  exit tests about delivered features (compile on first attempt, lines removed, a four-step resume, a Python
  version per example). None can fail the claim **[V]**. The only test that touches it is Phase 5's "the
  consumer completes a real multi-day task with at least one resume" (l.157), an existence proof that any
  checkpointing tool passes **[I]**.
- The charter's distinctive claim "concerns the quality and economics of this programming medium"
  (`docs/plans/2026-09-08-orc-research-charter.md` l.32–34) and its decision rule says "Compare credible
  reusable Python/native controls before claiming ORC-specific advantage" and "Abandon the custom platform if
  fair alternatives cover its retained uses more economically" (l.164–170) **[V]**. The roadmap has a stop
  rule for quality and for evolution, and none for the claim it stands on **[V]**.
- Existing comparative evidence is parity or adverse and the roadmap does not cite it:
  `experiments/adversarial_daq/docs/plans/2026-10-23-adversarial-daq-launch.md` l.92: "The observed hypotheses
  did not establish an Orc advantage over the implemented competitors" (LangGraph and strict Python/Pydantic;
  calibration waived, l.9; untracked) **[V]**. The audit's authoring note says of resume "Temporal gives the
  same thing (and more)" and that invalidation "does not roll back the workspace"
  (`…/scratchpad/audit/authoring.md` l.126–128) **[A]**.
- The audit's research note proposed a cheap test of exactly this claim: scripted providers, a long workflow
  against an equivalent LangGraph/Python version, kill-at-every-commit resume, typed routing, provenance
  (`…/scratchpad/audit/research.md` l.393–399) **[A]**. The roadmap dropped it without a disposition **[V]**.
- "Every phase before Phase 5 pays off whichever way the quality and evolution claims turn out" (l.27–28) is
  true only if the engineering claim has a user. That is the one thing no phase before 5 tests **[I]**.

**Proposed change.**

1. Restate the claim comparatively: "for pipelines of at least N provider calls or with a human gate, ORC gives
   resume, typed handoff and audit at lower total authoring-plus-recovery cost than the same pipeline in plain
   Python with a step cache (and one named durable-execution library)".
2. Add a zero-spend test early (after Phase 1): one multi-step pipeline with scripted providers, written in ORC
   and in the control; compare lines and concepts, kill-and-resume correctness, time for a fresh agent to
   locate an injected fault from the run records, and behaviour after a prompt edit.
3. Add a stop rule: if the control matches ORC on every measured property, record parity and take the charter's
   branch (retain a narrow subset, or move to the simpler foundation) before Phases 3 and 4 are built.
4. Move owner decision 5 (name the consumer) to selection time, and change Phase 5's consumer exit test to
   name what the consumer needed that the control could not do cheaply.
5. In the Claims table, change "Where it is tested: Phases 1–4" to the phase that holds this test, and list
   Phases 1–4 as "advances, does not test".

### B2 (blocker). Phase 3 inverts which half of "edit and continue" is sound, states an invariant its own exit test violates, and has an exit test that does not need the target

**Section:** Phase 3 (l.94–119); Findings row for Phase 3 (l.38).

**Evidence.**

- *What the design already says.* Invalidation is by journal suffix on purpose. C9: `depends_on` "is evidence,
  not the scope of an invalidation: a dependence through a file, where one effect writes a path that a later
  one reads, leaves no trace in values, and a shipped workflow has that shape"
  (`docs/design/workflow_lisp_evaluated_execution.md` l.1745). The spike tried the alternative: "The spike
  followed values only and reran one of two file-dependent effects, mixing old and new results" (l.1772–1775).
  Narrowing is an explicit later release "when command boundaries declare the files they read and write"
  (l.1745, l.3268). Workspace capture is a stated non-goal: "Capturing or rolling back workspace files"
  (l.213–214) **[V]**.
- *The fallback is the unsound half.* The stop rule says: if reuse cannot be made sound, "ship
  dependency-based invalidation alone and keep the refusal" (roadmap l.114–116) **[V]**. Dependency-based
  invalidation is the part C9 rules out until read and write sets are declared. Provider effects with tools
  edit the workspace with no declared write set, so for agent pipelines the precondition is not close **[I]**.
  The sound half is the other one: accept an edited program and reuse the longest journal prefix the edited
  program reproduces with equal identities and equal resolved-input digests, then invalidate the suffix in
  journal order. That needs no dependency scoping and changes only §8.4's program-equality refusal
  (`orchestrator/cli/commands/evaluated.py` l.190–191) and the "every active commit is reached" check
  (`orchestrator/workflow/evaluated/replay.py` l.72–87, l.172–176) **[V for the code sites, I for the design
  consequence]**.
- *The invariant is self-contradictory.* The stop rule protects "a committed effect never re-runs and never
  runs with different inputs" (l.114–115). The exit test edits step three's prompt and re-runs step three,
  which was committed, with different inputs (l.111–113) **[V]**. The design's rule is E3 with explicit
  invalidation as the only exception (l.91, l.1396–1404, C8 l.1744). The property worth protecting is replay
  equivalence: after the edit, the active memo is one that an uninterrupted run of the edited program could
  have produced with the reused effects returning their recorded results **[I]**.
- *The exit test does not test the target.* In a linear four-step run, the journal suffix from step three and
  the dependents of step three are the same set. "Resume re-runs steps three and four only" (l.111–113) passes
  with suffix invalidation and says nothing about "invalidation follows recorded dependencies, not journal
  order" (l.97–98) **[I]**. If the prompt is an extern file, its content is bound in the effect's resolved
  input by digest (C6, l.1060; §7.2, l.1043–1049), a changed input stops with `effect_input_diverged`
  (l.1399), and `invalidate` at step three followed by `resume` re-runs three and four today (§8.5,
  l.1737–1740, l.1774–1775) **[V for the rules; I that the composite passes today; a ten-minute provider-free
  probe would confirm]**. Only an inline `defprompt` edit changes the program digest.
- *"Build cache" is the wrong model.* A build cache keys on (action, input digest) and assumes hermetic
  actions. The memo keys on position, identity = (activation path, site) (l.936–952), is per run, and treats a
  changed input as a divergence that needs explicit authorization (l.1399), because effects mutate a workspace
  the runtime does not capture **[V]**. The nearer analogy is deterministic replay with a versioned program
  (durable execution), where the standard answer to a code change is prefix compatibility, not content
  addressing **[I]**.
- *Audit trail.* The header's program digest is immutable ("Never replace the header or program after journal
  activity begins", l.1634–1635) **[V]**. A run continued under an edited program is the product of several
  programs; the engineering claim's "audit trail" needs a recorded program lineage. The roadmap's "Makes
  harder" line (l.118–119) does not mention it **[I]**.

**Proposed change.** Rewrite Phase 3 as two steps with separate gates.

- *3a, prefix reuse (the target):* "An edited program resumes if replay under the edited program reproduces a
  prefix of the active journal with equal identities and equal resolved-input digests. The first reached
  effect that is new, missing or diverged invalidates the journal suffix from that point (C8 unchanged,
  including the coordinator refusals). The run records each program digest it ran under." Protected
  invariant: replay equivalence as stated above. Exit test: the four-step prompt edit; plus an edit that
  inserts an effect before step two (must re-run two to four); plus a file-dependence fixture shaped like
  `workflows/library/verified_iteration_drain/drain.orc` (must never mix old and new results); plus the
  kill-at-every-commit suite.
- *3b, dependency-scoped reuse (deferred):* entered only under C9's own entry condition (declared read and
  write sets, narrowed `depends_on`, the §17 file-dependence fixture), or with a workspace snapshot per commit,
  which reverses a stated non-goal and needs its own design decision.
- Delete the fallback "ship dependency-based invalidation alone". Replace it with: "if 3a cannot be made
  sound, keep the refusal and ship a `resume` message that names what changed and prints the `invalidate`
  command."
- Add a pre-step to Phase 1: check whether "prompts in files plus `invalidate`" already gives prompt
  edit-and-continue, and if so document it in the tutorial. That may deliver most of the value before any
  contract change.
- Drop the phrase "memo as a build cache" or mark it as an analogy that holds only for effects whose inputs
  are fully declared.

### M1 (major). Phase 6 cannot settle the evolution claim: 6a is a strawman and 6b lacks the controls

**Section:** Phase 6 (l.166–193); Claims row 3 (l.25); Dispositions (l.212, l.218).

**Evidence.**

- 6a asks whether guided search finds "the best recorded program in fewer evaluations than enumeration" over a
  table that Phase 5 already enumerated, of roughly eight programs (l.174–177; l.152–156) **[V]**. That is
  best-arm identification over a handful of arms. A positive result restates that racing methods work; a null
  says nothing about program structure. The closed roadmap already ruled on this case: "If the valid
  neighbourhood is tiny, enumeration is the result"
  (`docs/plans/2026-10-18-orc-structural-search-roadmap.md` l.501–502) and the charter lists "fixed-catalog
  selection" as not establishing self-programmability (charter l.43) **[V]**. "An LLM proposer choosing among
  recorded programs" (l.175–176) is selection, not variation **[I]**.
- 6b's exit test is "a generated program beats the best hand-written one on fresh tasks at equal or lower
  cost" (l.190–191) **[V]**. The charter requires that "adaptive search later beats equal-budget
  enumeration/random search on independent evaluation" (l.44) and that the same protocol be compared "as an
  agent skill and as idiomatic reusable Python/native orchestration before claiming comparative ORC advantage"
  (l.129–133). The closed roadmap's claim table separates "Useful search space", "Adaptive optimization" and
  "ORC-specific value" and names the control for each (l.489–497) **[V]**. 6b has no random or enumeration
  control at equal budget and no Python-diff arm, so a win cannot be attributed to guidance or to typed
  programs **[I]**.
- The genome is undefined. "Individuals: Typed workflow programs" (l.183) does not say whether the edited text
  is Python or `.orc`, after Phase 4 makes `.orc` "the generated form most authors never write" (l.135–136)
  **[V]**. The closed roadmap fixed "Authored source is the genome" and deferred named typed transforms (I4)
  because "classical subtree operators over lowered forms wait for a printer with round-trip evidence, which
  does not exist" (l.71–74, l.179) **[V]**. "Typed edits (add a review step, change fan-out, move a model, add
  a repair loop)" (l.184) are I4 operators that no existing apparatus implements **[I]**.
- "Admission: The compiler" (l.185) is kept although the roadmap's own finding is "the compiler rejected none"
  (l.41) **[V]**. No element of 6b responds to that finding.
- "Cost control: Children reuse the parent's committed effects where Phase 3 allows" (l.187) needs a forked
  run and a workspace as of the fork point. The memo is per run root and the closed roadmap required "One fresh
  clone per evaluation" (l.87) **[V]**. Reuse also makes a child's fitness share the parent's sampled results,
  which helps paired differences and biases any absolute estimate **[I]**.
- Contradictions: Dispositions stop "Live cumulative campaigns" (l.218) while 6b's apparatus is "the offline
  campaign code from the closed search roadmap" (l.188); that code is "reused without its qualification gates"
  (l.188) while the process rules say the `AGENTS.md` rules "apply unchanged" (l.242–245) **[V]**. The roadmap
  does not say whether 6b is one generation or cumulative, or which gate replaces the removed ones.
- The exit test is "X, or a measured negative is recorded" (l.190–191). The charter says "An inconclusive
  pilot calls for a better-targeted experiment, not a verdict" and "Record uncertain results without treating
  them as disproof" (closed roadmap l.505–506; charter l.170) **[V]**. A fixed budget with no power statement
  yields "unresolved at budget B", not a negative **[I]**.

**Proposed change.**

- Replace 6a with a zero-spend question the table can answer: design the Phase 5 catalog as a small factorial
  over the same factors 6b will edit (review step yes/no, candidates 1/3, repair loop yes/no, model placement),
  then report main effects, interactions and whether programs one edit apart have correlated outcomes. That
  tests "useful search space" and whether a typed edit is a meaningful move.
- Gate 6b on "the factorial shows separation beyond bootstrap noise and a non-additive structure enumeration
  has not exhausted", not on Phase 5's quality bar.
- Give 6b the charter's controls: equal-budget random generation and enumeration; one Python-source arm with
  the same proposer; fresh tasks for both the generated winner and the hand-written best.
- State the genome (which text is edited) and the variation operators that exist today (whole-file and
  locus-plus-fragment edits) versus those that must be built.
- Say whether 6b is single-generation or cumulative, reconcile it with the "Stop" row, and name the replacement
  for each removed gate (family: oracle check; measure: executed tests on known controls).
- Reword the exit test: "…or the result is recorded as unresolved at the stated budget and detectable effect".

### M2 (major). The Phase 5 gate is not the project's Pareto rule and is predisposed to a null

**Section:** Phase 5 benchmark, exit test and stop rule (l.143–164).

**Evidence.**

- Exit test: "whether any workflow Pareto-dominates direct" (l.158–159). Stop rule: "if no workflow gains 10
  pass-rate points over direct at no more than three times the tokens" (l.160–162) **[V]**. A workflow at
  three times the cost does not Pareto-dominate direct; these are two different criteria in one phase **[I]**.
  `AGENTS.md` defines "better" as Pareto dominance over quality and "model-aware deployed compute cost (metered
  tokens times a frozen per-model price table)" and allows a call or token proxy only when every candidate
  uses one model and effort **[V]**. Step 3 runs "two or three model placements" (l.153–154), so raw tokens
  are not the cost axis **[I]**. The rule is one-sided: a cheaper-model workflow that matches direct at lower
  cost extends the frontier and fails the stop rule **[I]**.
- "Direct" is undefined. A direct call through an agent CLI already runs tests and repairs in its own loop.
  The project's lessons say: "What does each step add that the previous agent did not have?" and "Do not score
  with tests the agent can run | agents test themselves until they pass; every arm reached 100 percent"
  (`docs/orc_workflow_design_lessons.md`, Before Drafting table l.38–42; Evaluating A Workflow table, about
  l.150) **[V]**. The two treatment arms, "best-of-3 with executed-test selection" and
  "implement–test–repair" (l.152–153), use as their signal the thing a direct agent already has. The roadmap
  does not say which tests the workflow may run and which score it **[V]**.
- No headroom condition. The roadmap's oracle check is "tests fail at base, pass at the reference fix"
  (l.148–149). The authority `AGENTS.md` cites says "a family every seed solves or every seed fails is
  uninformative" and that oracle qualification "shows the oracle accepting two structurally different correct
  submissions and rejecting a broken one" (`docs/design/orc_structural_search_driver.md` l.600–607) **[V]**.
  If direct passes most of the "small tasks" on a mid-tier model, a 10-point gain is impossible by ceiling
  **[I]**.
- Domain mismatch. The engineering claim is about "long, expensive, multi-agent pipelines" (l.23); the quality
  benchmark is "30–50 small tasks … short runs" (l.147, l.156) **[V]**. The lessons record that on "a task one
  call solved every time, every workflow tied and cost twice as much" (l.41) **[V]**. A null on small tasks
  would then "freeze" the quality claim (l.161–162) for the domain where it was not tested **[I]**.
- Scope narrowing is silent. The charter's preferred family is review/planning improvement (l.116–118); moving
  to executable-test code tasks restricts the claim to oracle-scorable code changes **[V/I]**.

**Proposed change.**

- One criterion: "a workflow is on the bootstrap-supported Pareto frontier of (pass rate, priced cost) and is
  not direct at any model tier". Use the frozen price table. Drop "10 points at 3× tokens", or keep it as a
  secondary, labelled exchange-rate readout.
- Define direct (CLI, tools, turn limit, test access). Split tests into visible (any arm may run) and held-out
  (score only). Require visible tests to fail at base for a stated share of tasks so feedback exists.
- Add a family headroom condition before step 3: direct pass rate on the lower model inside a declared band,
  measured in a small pilot that counts as calibration spend.
- Add at least one arm built on the lessons' two measured levers: an independent stronger selector or reviewer.
- Scope the stop rule: "the quality claim is frozen for small oracle-scored code tasks"; say that long
  pipelines remain untested.

### M3 (major). The order defers the cheapest decisive items and builds capability ahead of a consumer

**Section:** Order and dependencies (l.195–203); Claims (l.27–28); Process rules (l.238–239).

**Evidence.**

- Benchmark steps 1 and 2 are zero spend (l.144–150) and sit in the fifth phase **[V]**. Their outcome decides
  whether Phase 6 exists and how much of Phase 4's best-of-N work has a purpose **[I]**.
- "Phase 5 depends on Phase 4 (best-of-N)" (l.198–199). Serial best-of-N already exists at target 2.35:
  "Serial best-of-N migration at 2.35 no longer waits for Phase 5; optional parallel best of N does"
  (`docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` l.763–765) **[V]**. Pass rate and tokens
  do not depend on parallel execution, so the benchmark does not need Phase 4 **[I]**.
- The audit's diagnosis of the project's history is "Capability ahead of consumer … Most were retired within
  2–12 weeks" and "principle 26 was applied by argument at design time, not by consumer pull"
  (`…/scratchpad/audit/roadmaps.md` l.93, l.106) **[A]**. The roadmap's own process rule says "a feature gets
  full review ceremony only after a consumer has used it" (l.238–239) **[V]**. Phase 3 (a contract change) and
  Phase 4 (Python `parallel_map`, procedure references) are built before the consumer of Phase 5 is named
  (decision 5, l.230) **[V]**. The axis lifecycle requires "a named recurring use, an expected observable
  improvement, and a predeclared stop rule" for each improvement
  (`docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md` l.237–241) **[V]**.
- "Pays off either way" fails for parts of Phases 3 and 4: best-of-N exists to buy quality; Phase 3's reuse is
  justified partly as Phase 6 cost control (l.187) **[I]**.
- The evolution-first variant (l.202–203) moves Phase 3 ahead although "6b is cheaper after Phase 3 but does
  not require it" (l.200) **[V]**.

**Alternative orders considered.**

- *Evolution-first, strongest case.* Durable execution with typed handoffs is available elsewhere; a closed,
  statically checked program representation is the project's only uncommon asset, and its only uncommon use is
  machine manipulation of programs. If the engineering claim is at parity with existing tools (B1), evolution
  is the one claim that could justify the language, so test it before polishing. *Why it is not better:* the
  closed roadmap failed on measurement, not on usability or apparatus (closure, closed roadmap l.597–608)
  **[V]**. Evolution cannot be measured before a cheap, low-noise oracle exists. Going to generation first
  repeats October.
- *Research-first on the charter's five axes.* Honest to the charter, but four of the axes have no affordable
  credible measure today, and the charter itself says to leave such an axis unassessed (l.96–98) **[V]**.
- *Measurement-and-consumer-first (recommended).* Phase 0; then Phase 1 in parallel with benchmark steps 1–2
  and the B1 engineering comparison (all zero spend); name the consumer and build it on today's system with a
  friction log; run benchmark step 3 with the existing serial catalog; then select Phases 2–4 items by what the
  consumer and the benchmark showed. This is better because it buys the decisions that change later scope at
  zero spend, and it ends the capability-ahead-of-consumer pattern. Phase 2 deletion can run at any point; it
  depends on none of this.

**Proposed change.** Replace the dependency paragraph with the recommended order. State that Phase 3 and each
Phase 4 item enter only with a named friction item from the consumer or a benchmark need. Delete the sentence
at l.27–28 or restrict it to Phases 0–2. Rewrite the decision-6 branch to "benchmark steps 1–3 and the
factorial readout first; Phase 3 only if generation cost proves limiting".

### M4 (major). Five charter axes are collapsed to three claims without dispositions; the actual authors are agents and Phase 1 does not measure them

**Section:** Claims (l.19–28); Phase 1 exit test (l.70–72); Dispositions rows for the evolution roadmap and the
agent authoring plan (l.210–211).

**Evidence.**

- The charter sets "Five Independently Falsifiable Hypotheses": programmability, reusability, introspection,
  self-programmability, program-space optimization (l.36–44) **[V]**. The roadmap keeps "the axis lifecycle"
  (l.210) but that lifecycle requires each axis to have its own assessment and, on retirement, "Record the
  retained scope and the abandoned claim explicitly" (evolution roadmap l.39–42, l.323–327) **[V]**. The
  roadmap records no state for reuse, introspection or self-programmability **[V]**.
- The roadmap's quality claim, "a workflow beats one direct call" (l.24), is the claim the charter declines:
  the distinctive claim is "not … an assumption that more agents produce better answers" (l.32–34), and "A
  fixed RICH arm beats DIRECT" is listed as not establishing optimization (l.44) **[V]**. Making it the gate
  for evolution couples hypotheses the charter made independent: "ES … informs topology choice, not whether
  the five hypotheses may be investigated" (l.111–112) **[V]**.
- AA-1 says: "Record a baseline authoring trial before any selected AA-1 improvement lands" and "Measure
  success by correct programs and the effort to obtain them" (evolution roadmap l.727–736) **[V]**. The
  roadmap folds AA-1's guide and diagnostics into Phase 1 (l.211) and drops the baseline. Phase 1's exit test
  is "a new author finishes the tutorial without opening another document" (l.71–72), with "new author"
  undefined **[V]**. The audit says the work "targets the actual authors (agents)"
  (`…/scratchpad/audit/roadmaps.md` l.114) **[A]**. Without a before measurement the phase cannot show it
  improved the first hour **[I]**.
- R1b (agent authoring, feedback-driven revision, one agent-chosen orchestration revision; evolution roadmap
  l.73) is closed with the workstream ledger (l.210) **[V]**. It is the nearest test of the idea that agents
  can program this medium, which is what Phase 6b's "free-form LLM proposals" silently assumes **[I]**.

**Proposed change.** Add an "Axis state" table under Claims with one row per charter axis: state (supported
within scope, adverse, inconclusive, untested), the phase that tests it or "parked, reopened by X". Define
"new author" as a fresh agent session with only the tutorial and the CLI; record the same task before Phase 1
lands and after (first-attempt compile, attempts to a passing run, tokens). Record this as a usability check
with a small declared spend, not a quality comparison. Say explicitly that quality is a gate for evolution by
owner choice for cost reasons, not because the charter requires it.

### M5 (major). Python-first is compatible with the design principles, but the roadmap does not follow through on what it implies

**Section:** Phase 4 (l.121–136); Phase 1 (l.61–75); Phase 3 spike question 1 (l.105–106); Phase 6 (l.183).

**Evidence.**

- It is compatible: principle 1, "Workflow Lisp and typed Python generation are authoring surfaces over the
  same validated workflow semantics" (`docs/design/workflow_language_design_principles.md` l.90–94), and the
  frontend design, "Python is a source generator, never a second workflow interpreter"
  (`docs/design/python_workflow_frontend.md` l.14–16) **[V]**. The checked closed program stays the authority,
  so the typed core is supported, not undermined.
- Phase 1 spends on the `.orc` first hour (let-binding in `continue`, a prompt literal, a tutorial; l.63–69),
  then Phase 4 makes `.orc` "the generated form most authors never write" (l.135–136) **[V]**. The roadmap
  does not say which surface the tutorial teaches. The Python emitter already avoids the `continue` defect
  ("as the Python emitter already does", l.64) **[V]**.
- Phase 3 precedes Phase 4, but identity stability for Python authors is a Phase 4 item ("readable generated
  names", l.126). The emitter names bindings from a positional counter (`orchestrator/py/trace.py` l.194–195,
  l.271–279), and those names become authored labels, so adding an effect shifts later identities in the same
  scope **[V for the counter; I for the consequence, consistent with I4 at evaluated-execution l.946 and the
  edit table l.986–993]**. Edit-and-continue for Python authors therefore depends on Phase 4 naming.
- "Every catalog example has a Python version that builds to the same checked program shape" (l.130–131):
  "shape" is undefined. The audit reports that the same workflow in `.orc` and Python yields different effect
  identities (`…/scratchpad/audit/authoring.md` l.134–136) **[A]**, so it cannot mean equal digest or equal
  site table.
- Once authors write Python and the compiler output is the authority, the residual role of hand-written Lisp
  (macros, S-expression subtrees as edit loci) is the search genome and nothing else. The roadmap neither
  states that nor decides whether hand-authored `.orc` stays a supported surface. This also sharpens B1: the
  fair alternative becomes "a Python library over a durable step memo" **[I]**.

**Proposed change.** State the roles: "Python is the authoring surface; `.orc` is the checked interchange and
inspection form; hand-authored `.orc` is supported for X or frozen." Teach the Phase 1 tutorial in the surface
the roadmap makes primary, and limit Phase 1 `.orc` fixes to defects (the `continue` crash, `:on-exhausted`).
Move "readable, author-derived binding names" ahead of Phase 3 or make it a Phase 3 entry condition. Define
"same shape" (for example: same site count per effect class, same skeleton under label renaming, same result
on the scripted fixtures). Name the Phase 6 genome.

### M6 (major). Phase 5 fuses two unrelated tests, and its consumer rests on an unaccepted draft

**Section:** Phase 5 (l.138–164); Order and dependencies (l.198–200); Process rules (l.237).

**Evidence.**

- The consumer tests the engineering claim; the benchmark tests the quality claim. They share no apparatus.
  One exit test requires both (l.157–159), so a multi-day consumer run blocks the benchmark readout and Phase 6
  **[V/I]**. The process rule is "One plan per phase, each with one exit test" (l.237) **[V]**.
- The consumer is "built on progressive execution as an ordinary workflow" (l.140–142). That design's status is
  "draft target design; not an implemented framework or runnable example" and "selecting this target requires
  a separately accepted route for every required effect"
  (`docs/design/workflow_lisp_progressive_execution.md` l.3–5) **[V]**. It also says the fixed loop "does not
  guarantee better results than an ordinary agent" (l.34–35) **[V]**. The dependency paragraph does not list
  this acceptance step.
- Its planning agent benefits from continuity, and Phase 4 may "retire Agent Sessions" (l.128–129) on a
  comparison whose decision rule the roadmap does not state. The delivery plan's rule is an "explicit owner
  judgment that context retention justifies lost recoverability/repeated paid work" (delivery plan l.674)
  **[V]**. The audit notes continuity is one of three capabilities that were rebuilt after retirement
  (`…/scratchpad/audit/roadmaps.md` l.107) **[A]**.

**Proposed change.** Split Phase 5 into "5C consumer" (engineering claim, see B1) and "5B benchmark" (quality
claim), each with one exit test; 5B and Phase 6 do not wait for 5C. Add "accept the progressive-execution
design as an ordinary workflow, or pick a consumer that needs no draft design" as a 5C entry condition. Run
PQ-1c on the consumer, so the retain-or-retire decision for Agent Sessions is made by the pipeline that would
use them.

---

### Minor findings

**m1. Process rule broken by the roadmap's own phases.** "One plan per phase, each with one exit test" (l.237);
Phase 1 lists four exit conditions (l.70–72), Phase 4 two (l.130–132), Phase 5 two (l.157–159) **[V]**.
*Change:* say "one exit checklist" or give each phase a single headline test with the rest as entry items.

**m2. "Tested in Phases 1–4" wording.** The Claims table's third column mixes "delivered in" and "tested in"
(l.23) **[V]**. *Change:* two columns, "Advanced by" and "Tested by".

**m3. Threshold provenance.** The stop rule uses 3× tokens (l.161). The audit note gives ≤ 2× in one place and
3× in another (`…/scratchpad/audit/research.md` l.359, l.380) **[A]**. *Change:* state the reason for the
number, or drop it as M2 proposes.

**m4. Phase 6 keeps "Admission: The compiler" with no response to "rejected none".** (l.41, l.185) **[V]**.
*Change:* either add a discriminating admission test that exists offline (the closed-program call maximum,
closed roadmap l.162–165 **[V that it is described as implemented offline]**) or say admission is expected to
be a no-op and is not part of the claim.

**m5. CE-1 is kept alive with no phase that needs it.** "Checked evaluation of generated source only if
generation must run inside a workflow" (l.188, l.210). The search driver runs outside workflows by decision
("The optimizer and evaluators run in Python", "no in-language `eval`", closed roadmap l.103, l.124–126), and
the design is "proposed, unselected, unimplemented" (`docs/design/workflow_lisp_checked_program_evaluation.md`
l.3) **[V]**. *Change:* park CE-1 with the evidence that reopens it (a positive self-programming result, M4),
and remove it from the Phase 6 table.

**m6. The offline campaign code is retained against Phase 2's intent.** "Offline code kept for Phase 6b"
(l.212) keeps about 11.6k lines plus about 21k lines of tests **[A, `…/scratchpad/audit/research.md` l.254]**
alive through Phase 2 for a gated phase. *Change:* freeze it outside the default suite now; delete it if
Phase 5's stop rule fires.

**m7. Dynamic branch.** Decision 4 recommends "tag and stop" (l.227–229) with no reason given. The
simplification record kept "dynamic research and its native function-value benefit"
(`docs/plans/2026-10-15-orc-simplification-roadmap-extension.md` l.99) **[V]**, and the axis lifecycle asks
that alternative foundations be compared before a claim is retired (evolution roadmap l.264–272) **[V]**. I
did not inspect the branch. *Change:* give the reason, and name what evidence would reopen it (for example,
M4 showing typed authoring is the agents' bottleneck).

**m8. Phase 6 comparison fairness.** "The best hand-written one" is chosen on Phase 5's table and the generated
winner on search tasks; both carry selection bias (l.190–191) **[I]**. *Change:* re-evaluate both on the same
fresh tasks; say so in the exit test.

---

## Answers to the five review questions, in brief

1. **Thesis coherence.** The split into engineering, quality and evolution is a reasonable public framing, and
   better than the previous record. It is not the right decomposition of what the project has to decide. It
   omits the representation question (is a custom typed language worth it against Python or an existing
   durable-execution tool), which cuts across all three and is the charter's decision rule. Phases 1–4 advance
   the engineering claim and test nothing; Phase 5 tests a quality claim the charter declined to make central;
   Phase 6 cannot attribute a win. See B1, M1, M2, M4.
2. **Ordering.** Not justified as stated. Evolution-first and axis-first are both worse than the proposal;
   measurement-and-consumer-first is better. See M3.
3. **Missing or wrong.** The distinctive idea is replay of a closed, statically checked program against a memo
   keyed by structural effect identity (evaluated execution l.79–93, l.936–952) **[V]**. "Build cache" is the
   wrong model for it (B2). The unexamined gap in all three claims is workspace state: the memo covers values;
   the pipelines' product is edits to a repository the runtime neither captures nor restores (non-goal,
   l.213–214) **[V]**. Phase 3, the Phase 5 consumer and Phase 6 reuse all meet it, and the roadmap treats it
   as spike sub-question 3. Python-first supports the typed core but removes most reasons for hand-written
   Lisp, which the roadmap does not say (M5). Phase 6a is a strawman; 6b is under-controlled (M1).
4. **Dispositions.** Dropped and worth keeping: the AA-1 baseline authoring trial and the R1b question (M4);
   the audit's offline engineering comparison (B1). Kept and better parked or cut: CE-1 (m5); the campaign
   code inside the suite (m6); the "dependency-based invalidation" fallback (B2). The remaining drops (LSP
   P-series and L6, OMP-I2, confined provider children, provider-phase isolation, substrate track, private
   runtime C2–C6) look right from the capability matrix's Retired rows **[V for the matrix rows at
   `docs/capability_status_matrix.md` l.57–140; I for the judgement]**.
5. **Contradictions and undefined terms.** Stop rule against exit test in Phase 5 (M2); Phase 3 invariant
   against its exit test (B2); "Stop live cumulative campaigns" against the 6b apparatus, and "without its
   qualification gates" against "rules apply unchanged" (M1); one exit test per phase (m1); Phase 1 `.orc`
   investment against Phase 4 demotion (M5). Undefined: "direct", "new author", "same checked program shape",
   "typed workflow programs" as individuals, "acceptable cost", "measured negative".

---

## What the roadmap gets right and should keep

- Claims are separated from their evidence state, and "Not shown" and "Never measured" are said plainly
  (l.21–25).
- Phases 0–2 are cheap, spend-free and worth doing under any outcome. The `continue` crash, silent `run`,
  import cost and compile-time `:on-exhausted` are real defects with clear fixes.
- Phase 3 is gated on an accepted design revision before code (l.99–102), and its three spike questions are
  the right questions. Question 3 deserves to be the headline.
- Executable tests replace the judge as the primary measure; zero-spend steps come before paid ones; a Python
  control is included (l.143–164).
- Every phase has a stop rule and a "Makes harder" line; Phase 6 has "no extension after a null".
- The draft status, the explicit owner decisions and "selects no work, authorizes no spend" are correct.
- "A feature gets full review ceremony only after a consumer has used it" (l.238–239) is the right rule. The
  phase order should obey it.
- The axis lifecycle is kept (l.210). The Claims section should use it.
