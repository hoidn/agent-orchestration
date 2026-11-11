# Scientific-value review: ORC roadmap "Usable Pipelines First, Then Program Evolution"

Task id: `review_plan_roadmap_scientific_value`. Role: reviewer (read-only). Artifact type: draft project
roadmap, `docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md` at `87c9325c`.
No repository edits, no provider calls, no test runs. Paths are repo-relative unless absolute.

**Claim markers used throughout**

- **[V]** verified by reading the cited file and line in this checkout.
- **[A]** reported by the audit notes (`scratchpad/audit/research.md`) and not re-verified by me.
- **[L]** from my memory of the published literature; confidence stated; details I am unsure of say
  "I believe, unverified". I had no web access and invented no citation.
- **[I]** inferred by me from the above (reasoning or arithmetic shown).

---

## Verdict

The roadmap is a sound engineering plan and an honest statement of what is not known, but as written it
would produce software and very little knowledge. Of its three claims, only the quality claim has a
pre-committed refutation, and that test is set in the regime where both outcomes are least informative:
small tasks that fit in one context, one run per task, no compute-matched direct baseline, and no rule
separating the tests agents may run from the tests that score. A pass would be attributable to extra
compute or to test leakage; a fail would say nothing about the long multi-stage pipelines the engineering
claim is about. The evolution phase, as designed, either replicates a result the literature already has
(search over agent workflows beats hand-written baselines when fitness is cheap: ADAS, AFlow, GPTSwarm,
AlphaEvolve) or returns a null from a search budget several orders of magnitude below the regimes where
that result was obtained; it drops the two controls (equal-budget unguided search and a Python
representation arm) that would make it a statement about this system. The engineering claim is not stated
as a hypothesis at all, has no comparator, and the roadmap omits the project's own one direct comparison
against LangGraph, which found parity. Meanwhile the result this project is best placed to produce, a
measurement of what exact effect identity and a re-evaluation memo buy (cost of iteration under program
edits, crash behaviour of expensive non-idempotent agent turns, and paired low-variance evaluation of
workflow variants by replaying a shared prefix), is scheduled as a build with a four-step toy exit test and
no measurement. The fix is mostly rewording and three or four added measurements, most of them zero-spend;
it does not require a larger programme.

**Findings: 3 blockers, 7 majors, 5 minors.**

---

## Answers to the six questions (short form; findings carry the evidence)

1. **Falsifiability.** Engineering: not a hypothesis; no refutation condition; "tested in Phases 1–4" is
   inaccurate, those phases build (F4). Quality: the negative is committed (10 points at no more than 3x
   tokens), the positive is not (two inconsistent criteria, "any workflow", point estimate, no holdout)
   (F2, F7). Evolution: "beats the best hand-written one, or a measured negative is recorded" commits to
   neither a margin nor the controls that define support (F3).
2. **Novelty.** Phase 5 replicates known results; Phase 6's generic question is answered positively
   elsewhere under conditions this project cannot afford; the only new parts are typed admission as a
   search constraint and memo reuse as cheap evaluation, and the roadmap does not isolate either (F3, F8).
3. **Low prior on evolution.** Over-read. The project's own Phase 1 report says the result is "not evidence
   that the neighbourhood is flat". The evidence touches one-step, topology-only proposals from a trivial
   parent on tasks with no failing intermediate signal. It does not touch parametric search within a fixed
   structure, model placement, multi-generation search, long tasks, decomposition or evaluator search (F6).
4. **Most valuable result.** A measured account of effect-identity memoisation for agent pipelines. The
   roadmap builds toward it and plans no measurement (F5). A publishable engineering result exists and is
   unplanned (F4, F5).
5. **Informative negatives.** Not as designed. Conditions the task set must satisfy are listed in F1.
6. **Add, cut, reword.** See "Consolidated change list" at the end.

---

## Findings, most severe first

### F1 (blocker). The quality benchmark tests the claim where it is least expected to hold, and its stop rule generalises from that regime

**Section:** Claims table (line 23–25); Phase 5 benchmark steps 2–3 (lines 147–156); stop rule (lines 160–162).

**Evidence.**

- The engineering claim is about "long, expensive, multi-agent pipelines" (line 23) [V]. The quality
  benchmark is "30–50 small tasks", "240–320 short runs" (lines 147, 156) [V]. The two populations are
  disjoint. The consumer in the same phase is long but has no comparator (line 157) [V].
- The stop rule converts a null on the small tasks into "the quality claim is frozen, Phase 6 does not
  open, and the project keeps the engineering claim only" (lines 160–162) [V]. That conclusion does not
  follow from a null on single-context tasks.
- The project's own evidence says structure had nothing to act on in single-context tasks: the
  agent-visible check "passed on the first try in every evaluation that ran it", so check-gated programs
  "are `direct` plus a check" (`docs/reports/2026-10-18-orc-structural-search-phase1.md` lines 384–387)
  [V]; one call shipped a ~1,800-line specified feature passing 16/16 and 14/16 hidden tests
  (`docs/reports/2026-10-14-design-review-execute-versus-single-call.md` lines 27–28) [V].
- The driver design already states the admission condition the roadmap drops: "planning, review and
  escalation choices must be able to matter ... a family every seed solves or every seed fails is
  uninformative" (`docs/design/orc_structural_search_driver.md`, Task Family And Evaluator, the paragraph
  after the family table) [V]. The `AGENTS.md` oracle check the roadmap cites (tests fail at base, pass at
  the reference fix) establishes that the oracle works, not that the family has headroom [V, I].
- Literature [L, high confidence on the gist]: gains from multi-call structure on short coding tasks come
  from two sources, sample diversity filtered by an executable signal (AlphaCode, Li et al. 2022; CodeT,
  Chen et al. 2022; Agentless, Xia et al. 2024) and stronger or different feedback (Olausson et al.,
  "Is Self-Repair a Silver Bullet for Code Generation?", ICLR 2024, who found self-repair roughly matches
  equal-budget resampling and is limited by feedback quality). Where neither source exists, nothing is
  expected. Reported multi-agent gains are largest on breadth-first tasks that exceed one context
  (Anthropic's 2025 multi-agent research write-up; I believe it attributes most of the variance to token
  spend, unverified figure) and are frequently absent against a strong single-agent baseline
  (Wang et al. 2024, "Rethinking the Bounds of LLM Reasoning"; Smit et al. 2023, "Should we be going
  MAD?"; Cemri et al. 2025, "Why Do Multi-Agent LLM Systems Fail?").
- Training-data contamination [L, high confidence that the problem exists; figures unverified]: public bug
  corpora and SWE-bench-style tasks are in model training data (SWE-bench+ , Aleithan et al. 2024, reported
  solution leakage and weak tests in a large minority of instances, I believe roughly a third each,
  unverified; time-split benchmarks such as LiveCodeBench, SWE-bench-Live and SWE-rebench exist for this
  reason). "Outside this repo's own features" (line 148) removes local contamination, which is the
  project's measured problem, but not memorisation. Memorised tasks push `direct` to the ceiling and bias
  the benchmark toward a null.

**What must be true of the task set for either outcome to be informative** [I]:

1. *Headroom.* The direct arm's pass rate on the chosen model lies in a predeclared mid band (for example
   30–70%). Otherwise ceiling or floor decides the result.
2. *Sample diversity.* Repeated direct runs on the same task do not always agree. Measured as oracle
   headroom, pass@k minus pass@1. If it is near zero, best-of-N cannot help whatever the selector.
3. *An intermediate signal that can fail.* Agents can run something (a reproducer, a visible test subset)
   that fails at base and is distinct from the scoring tests. Without it, repair and check-gated programs
   degenerate to `direct`, as in Phase 1.
4. *Freshness.* Tasks post-date the training cutoff of every model used, or are privately authored.
5. *At least one stratum where one context is not enough,* if the claim is meant to cover long pipelines.
   Otherwise the claim under test must be renamed.

**Proposed change.**

- In Phase 5 step 2, replace the qualification sentence with: "Qualify the family by its oracle check and
  by a predeclared informativeness check on direct runs alone: direct pass rate between 30% and 70% on the
  primary model; pass@3 minus pass@1 at least 10 points; an agent-runnable check that fails at base on at
  least half the tasks and is disjoint from the scoring tests; every task dated after the cutoff of every
  model used. A family failing this check is replaced before any workflow arm runs; the check and its
  result are recorded."
- Reword the stop rule's consequence: "the quality claim is frozen **for single-context coding tasks with
  executable tests**" and add "the claim for long multi-stage pipelines stays untested unless the
  long-task stratum below ran".
- Add a long-task stratum of three to five tasks, or use the Phase 5 consumer for the stage-ablation
  design in F5, so that the regime named in the engineering claim is measured at least descriptively.

---

### F2 (blocker). A Phase 5 "win" is not attributable to structure: no compute-matched baseline, and the agent-visible/scoring test split is undefined

**Section:** Phase 5 step 3 (lines 152–156); exit test (lines 157–159); stop rule (lines 160–162); Python
control (lines 163–164).

**Evidence.**

- The exit test asks whether any workflow "Pareto-dominates direct" (line 159); the stop rule asks for
  "10 pass-rate points over direct at no more than three times the tokens" (lines 160–161) [V]. These are
  different criteria. Under the governing definition, A dominates B only if its cost is no higher within
  tolerance (`docs/design/orc_structural_search_driver.md`, Objective, Selection And Local Observations:
  "A dominates B iff q_A >= q_B - tau_q and c_A <= c_B * (1 + tau_c) ...") [V]. A same-model workflow
  that makes more calls than `direct` can never dominate it. Best-of-3 costs at least three times `direct`
  by construction, so it sits on the edge of the stop rule's cost bound before any selection cost [I].
  `AGENTS.md` fixes "better" as Pareto dominance over quality and model-aware cost [V]; the stop rule is
  not that.
- A 10-point gain at 3x tokens is also what "spend 3x on direct" might buy. The project has evidence that
  effort alone moves token use by a large factor: Luna-low used about 1/20 of Luna-high's tokens [A]. The
  Python control (line 163) removes the tool as an explanation, not compute. The project's own September
  report already says of its positive result: "The gain comes from the pattern. A script that generates
  four candidates and selects one would show it too" (`docs/reports/2026-09-28-orc-versus-single-call.md`
  lines 316–317) [V].
- "Best-of-3 with executed-test selection" and "implement–test–repair" (lines 152–153) do not say which
  tests. If selection or repair uses the scoring tests, best-of-3 is pass@3, which is at least pass@1 by
  arithmetic, and the result is guaranteed and empty. The audit lists "do not score with tests the agent
  can run" as a defect observed in September [A]. If no failing test is visible, repair has no signal
  (Phase 1, lines 384–387) [V].
- Literature [L, high confidence on the gist]: Kapoor et al. 2024, "AI Agents That Matter", showed that
  simple baselines (retry, escalation to a stronger model) match or dominate published agent architectures
  on HumanEval once cost is on the axis, and argued for exactly this Pareto reporting. Olausson et al.
  (above) is the equal-budget control for repair. "Are More LLM Calls All You Need?" (Chen et al. 2024)
  showed non-monotone returns to call count in vote systems. A Phase 5 without these baselines repeats the
  design flaw those papers criticise.

**Proposed change.**

- State the quality hypothesis in one sentence the roadmap can be held to: "**H-Q:** on a qualified task
  family, at least one predeclared workflow lies above the direct-call frontier, where the frontier is
  formed by direct calls across the admitted models, efforts and plain retries, by more than the
  predeclared quality tolerance at equal or lower metered cost, confirmed on held-out tasks."
- Add arms to step 3: direct at a higher effort or the next model tier at matched metered cost;
  direct-times-k with an oracle pick (the upper bound for any selector) and with a random pick; and one
  conditional escalation arm (cheap model, executed check, stronger model only on failure). The last is the
  only named structure that can dominate in the strict sense, because it can cost less than the stronger
  direct call [I; L for the precedent: FrugalGPT, Chen, Zaharia and Zou 2023, and the escalation baseline
  in Kapoor et al.].
- Add one sentence fixing the test split: "Agents may run only the visible subset; pass/fail is scored on
  tests no agent process can read; a workflow whose selection or repair step can read a scoring test is
  invalid."
- Replace the two criteria (lines 159 and 160–161) with the single H-Q criterion, and keep "10 points at no
  more than 3x tokens" only as a descriptive figure, or record it explicitly as an owner-approved
  departure from the `AGENTS.md` definition of "better".

---

### F3 (blocker). Phase 6 as designed yields no new knowledge under either outcome

**Section:** Phase 6 (lines 166–193); Claims table row 3 (line 25).

**Evidence.**

- *6a is a search over about eight recorded programs* (line 174–177; "the table Phase 6 searches", line
  155–156) [V]. Random search finds the best of eight in 4.5 evaluations on average; any policy difference
  is one to three evaluations and the "best" cell is itself one noisy run per task [I]. An LLM proposer
  "choosing among recorded programs" (line 175) will pick test-based selection from prior knowledge, which
  measures what the model has read, not search [I]. The charter says fixed-catalog selection does not
  establish the claim ("What does not establish it: ... fixed-catalog selection",
  `docs/plans/2026-09-08-orc-research-charter.md` line 43) [V].
- *6b drops the controls that define support.* The charter requires that "adaptive search later beats
  equal-budget enumeration/random search on independent evaluation" (line 44) [V]. The closed roadmap's
  question was whether compiler-assisted search over typed programs does better "than credible manual and
  Python-based alternatives" (`docs/plans/2026-10-18-orc-structural-search-roadmap.md` lines 53–55) [V],
  and the driver design lists the conditions needed to attribute a result: enumerated catalog,
  prompt/provider tuning with fixed topology, equal-budget unguided sampling, matched Python search
  (`docs/design/orc_structural_search_driver.md`, Controls, Interface Test And Ablations) [V]. Phase 6b
  names none of them. Its exit test, "a generated program beats the best hand-written one on fresh tasks
  at equal or lower cost" (lines 190–191), has no margin, no sample size, no reserved holdout (the whole
  family is consumed by the Phase 5 table), and no baseline that separates search from luck.
- *The generic question is already answered* [L]. Search over agent programs finds designs that beat
  hand-written baselines when fitness is cheap and automatic:
  - ADAS (Hu, Lu and Clune 2024): a meta-agent writes agents in code with an archive; gains over
    hand-designed agents on ARC, reading, maths and science QA, with some transfer across domains and
    models. High confidence on the gist.
  - AFlow (Zhang et al. 2024): Monte Carlo tree search over code-represented workflows built from a small
    operator set (ensemble, review-and-revise, test, and similar) on HumanEval, MBPP and QA/maths sets; I
    believe it reports a gain of a few points over prior methods and that small models with found
    workflows match a larger model at a small fraction of inference cost (figures unverified).
  - GPTSwarm (Zhuge et al. 2024): agents as optimisable graphs, edge and prompt optimisation.
  - DSPy optimisers (MIPRO, Opsahl-Ong et al. 2024; GEPA, Agrawal et al. 2025) and TextGrad (Yuksekgonul
    et al. 2024): search over prompts and demonstrations inside a fixed program structure.
  - FunSearch (Romera-Paredes et al. 2024) and AlphaEvolve (Novikov et al. 2025): evolutionary program
    search with deterministic evaluators and very large sample counts (I believe on the order of a million
    samples for FunSearch, unverified).
  - Darwin Gödel Machine (Zhang, Hu, Lu, Lange and Clune 2025): a coding agent that evolves its own
    scaffold against SWE-bench and Polyglot (I believe from about 20% to about 50% on SWE-bench Verified,
    unverified), at a large compute cost.

  Common conditions of every positive result I know: a cheap, low-noise, automatic fitness; hundreds to
  millions of evaluations; mostly small executor models with large headroom; cost usually off the
  objective. The known critiques are that gains shrink against cost-controlled simple baselines (Kapoor et
  al. 2024) and that found designs are often ensembles plus refinement. I do not know of a published
  result that isolates the value of a typed, compiler-admitted representation for this search, or that
  reuses committed side-effecting prefixes across program variants; my confidence that none exists is
  moderate to low, and it should be checked before any claim of novelty.
- *The project's own evidence on the distinctive variable is a small null.* In the three-arm readout the
  acceptance rate was 1.0 in every interface, including the Python diff arm, and all 18 children
  implemented one idea (`docs/reports/2026-10-18-orc-structural-search-phase1.md` lines 231–234, 255–261)
  [V]. Typed admission rejected nothing, so it could not have improved search efficiency in that sample.
- *Budget.* The largest allocation so far was 160 calls [A]. A 6b null "within a fixed budget" (line 192)
  would be a statement about insufficient search, not about the claim [I]. The closed roadmap says the
  same: "a flat or tiny one-step neighbourhood is a finding about that sample, not a verdict against
  cumulative search" (`docs/plans/2026-10-18-orc-structural-search-roadmap.md`, Decision Points,
  Cumulative pilot eligibility row) [V].
- *Process conflict.* The Apparatus row reuses the campaign code "without its qualification gates" (line
  188) while the process rules say the `AGENTS.md` experiment rules "apply unchanged to Phases 4–6" (lines
  242–245) [V]. One of these must give.

**Proposed change.** Replace Phase 6 with one of the following, chosen by the owner under decision 6.

- *Option A, cut:* "The generic evolution claim is not pursued. It is answered in the literature for
  cheap-fitness regimes (ADAS, AFlow, AlphaEvolve) and this project cannot afford those regimes. The
  offline campaign code is archived."
- *Option B, test only what this system can add,* as two hypotheses with predeclared support and
  refutation:
  - "**H-E1 (representation):** at equal mutator budget, typed edit operators with compiler admission
    yield more distinct evaluated ideas, or fewer wasted evaluations per dominating child, than free-form
    Python edits of the matched workflow. Refuted if the rates are within the predeclared tolerance, as
    the 2026-10-19 three-arm readout suggests (18 of 18 accepted in every interface)."
  - "**H-E2 (cheap evaluation):** evaluating a child that shares a committed prefix with its parent costs
    less than a fixed fraction of a from-scratch evaluation and detects the same child-minus-parent
    difference with fewer runs. Measured on the Phase 5 table and the Phase 3 mechanism; needs no
    generation spend." (See F5.)
- In either option delete 6a as written, or replace it with the zero-spend variance decomposition in F7,
  which answers "is there anything to search for" directly.
- If 6b stays in any form, add: an equal-budget unguided arm; a reserved holdout split fixed when the
  family is assembled; a predeclared margin; and the sentence "a null within the budget is recorded as
  'not found at this budget', not as a negative on the claim".

---

### F4 (major). The engineering claim is not a hypothesis, has no comparator, and omits the project's own comparison

**Section:** Claims table row 1 (line 23); "The roadmap is ordered so that ..." (lines 27–28); Phase 5
consumer exit test (line 157); owner decision 2 (lines 223–224).

**Evidence.**

- "Long, expensive, multi-agent pipelines get typed handoffs, exact resume and an audit trail" with state
  "Supported by the runtime" and "tested in Phases 1–4" (line 23) [V]. Phases 1–4 have build exit tests
  (compile on first attempt, `--help` under 0.5 s, lines removed, Python parity) [V]. None can refute the
  claim. The consumer exit test is one existence proof (line 157).
- The charter requires a comparator: "Compare credible reusable Python/native controls before claiming
  ORC-specific advantage ... Abandon the custom platform if fair alternatives cover its retained uses more
  economically" (`docs/plans/2026-09-08-orc-research-charter.md` lines 164–169) [V].
- The project ran that comparison once and the roadmap does not mention it. The adversarial DAQ study
  (untracked, `experiments/adversarial_daq/`) tested four claims, three of them about resume, uncertain
  receipts and implementation drift, against real LangGraph with SQLite checkpoints or strict Python. Its
  ledger concludes: "The observed hypotheses did not establish an Orc advantage over the implemented
  competitors", with equal accepted I/O and zero unapproved dispatches in both arms, and ORC case wall
  time 3 to 4 times LangGraph's (137 s against 40 s in round 1)
  (`experiments/adversarial_daq/docs/plans/2026-10-23-adversarial-daq-launch.md`, "Completed rounds" and
  final paragraph) [V]. The same ledger correctly notes that runtime parity does not refute unmeasured
  compile-time or maintenance benefits.
- The guarantee is narrower than "exact resume" reads. A committed effect is reused; a started attempt
  with no commit is re-run with an `effect_rerun` record unless the boundary declares `must_not_repeat`;
  an agent turn in that state is classified from the provider's native store
  (`docs/design/workflow_lisp_evaluated_execution.md` §8.1 table) [V]. That is committed-once with
  detected re-execution of in-doubt attempts, the same class as activity semantics in Temporal-style
  systems [L, high confidence], plus one distinctive piece: recovering a completed but uncommitted agent
  turn without re-dispatch. Tests cover the kill windows with scripted providers
  (`tests/test_workflow_evaluated_agent_turn_recovery.py`,
  `tests/test_workflow_evaluated_agent_consumer_smoke.py::test_every_kill_point_resumes_to_the_same_value_without_a_turn_running_twice`,
  `tests/test_workflow_evaluated_resume_kills.py`) [V, names read, tests not run].
- Live behaviour has diverged from the scripted tests at least once: agent turns inside `loop/recur` hit
  `agent_turn_unresolved` on the second turn (Phase 1 report lines 401–403) [V]. In the project's largest
  experiment, five runs were cut off after 25–70 minutes of work and were relaunched, not resumed; "the
  earlier attempts' work was discarded" (same report, lines 83, 369–371) [V]. That was an owner directive,
  but it is the one recorded occasion on which resume would have saved real spend, and it was not used.
- Durable execution is an established field [L, high confidence]: Temporal and Cadence, Azure Durable
  Functions (Burckhardt et al. 2021), DBOS, Restate, Beldi (Zhang et al. 2020), LangGraph checkpointers.
  A claim that stops at "has resume and an audit trail" is a feature list those systems share.

**Proposed change.** Replace row 1 of the Claims table with three hypotheses and add a measurement line to
the phases that own them:

- "**H-G1 (crash behaviour):** for every kill point and every effect kind, a resumed run produces the same
  value, re-dispatches no committed effect, and recovers a completed uncommitted agent turn without
  re-dispatch. Measured as a published matrix from the existing kill tests (scripted) and from a
  fault-injection run with live low-tier providers in Phase 4. Refuted by any duplicated committed effect
  or any lost completed turn. Compared with the same pipeline on LangGraph checkpoints, citing the
  2026-10-23 adversarial DAQ parity result as the prior."
- "**H-G2 (errors before spend):** the checker rejects, before the first provider call, defect classes
  that the Python/LangGraph equivalent reports only at run time. Measured on a fixed list of seeded
  authoring defects and on the defects found while writing the Phase 5 consumer. Refuted if the typed
  Python control with a standard type checker catches the same set."
- "**H-G3 (iteration cost):** see F5."
- Add to Phase 0 (zero spend): "from the run ledgers of the October experiments, count interruptions,
  resumes attempted, resumes that succeeded, and relaunches, with the provider time lost in each". This is
  a measurement of the claim on real use that the project has already paid for.
- Reword owner decision 2: "confirm H-G1 to H-G3 as the claims the project stands on, each with its
  refutation condition".
- Change "Where it is tested: Phases 1–4" to "Built in Phases 1–4; measured in Phases 3–5".

---

### F5 (major). The most valuable result this project can produce is built but not planned as a measurement

**Section:** Phase 3 target and exit test (lines 96–98, 111–113); Phase 6 "Cost control" row (line 187);
Phase 5 step 1 (lines 144–146).

**Reasoning** [I, with L where marked].

The project's distinctive assets are exact effect identity, compiler admission and a memo that turns
resume into re-evaluation. The audit's central measured obstacle is the cost and noise of one evaluation:
30–80 minutes, per-judgment noise near one point on eight, about 16 samples per arm for a one-point effect
[A]. The memo addresses that obstacle in two ways no other part of the roadmap does.

1. *Iteration cost under edits (H-G3).* Phase 3 turns the memo into a build cache. The mechanism has
   prior art for hermetic tasks: Nextflow `-resume`, Snakemake, Bazel and Nix reuse content-addressed
   results after pipeline edits, and "Build Systems à la Carte" (Mokhov, Mitchell and Peyton Jones 2018)
   gives the theory [L, high confidence]. Temporal-style replay does the opposite: changed code is a
   non-determinism error unless explicitly versioned [L, high confidence], which is the roadmap's
   `resume_program_changed` today. What is not established anywhere I know of is how much reuse is sound
   and how much is realised when the effects are non-hermetic agent turns that edit a shared workspace
   (moderate confidence that this is open). Spike question 3 (lines 109–110) is exactly that question. It
   deserves a number, not only a four-step exit test.
2. *Paired evaluation of variants by replay.* If two programs share a committed prefix, evaluating the
   second re-runs only the suffix. Every comparison of "with and without a review step", "selector A or
   B", "repair loop or none" then holds the implementer's output fixed. This is the common-random-numbers
   design: the difference between variants is estimated within the same draw, which removes the largest
   variance component the audit measured (between-run variation of the implementer). Step 1 of Phase 5
   (lines 144–146) is the offline form of this and is the right first move. The roadmap does not name the
   method, does not plan it for live runs, and mentions reuse only as "cost control" for Phase 6.
   One caveat must be written down with it: a comparison conditioned on one prefix draw is a statement
   about that draw. Variants must be compared over several independent prefixes per task, and a parent
   selected for a lucky prefix passes that luck to every child that reuses it (winner's curse by
   inheritance) [I].

A systems result of the form "typed, effect-memoised agent pipelines: resume as re-evaluation, with a
crash matrix, measured reuse under real edits, and paired evaluation at a fraction of the cost" is, in my
judgement, publishable as an experience or systems paper and useful whether or not any workflow ever beats
a direct call. A quality or evolution result from this project would be a small replication.

**Proposed change.**

- Add to Phase 3, after the exit test: "**Measurement:** replay the recorded edit history of at least
  three real workflows (the Phase 5 consumer and two catalog workflows that were iterated on) against
  their memos. Report, per edit, the fraction of committed provider cost reused, the cost re-spent, and
  every case where reuse was refused or would have been unsound, split by the three spike questions.
  Compare with whole-run restart and with resume-from-checkpoint at stage granularity."
- Add to Phase 5, between steps 1 and 3: "**Paired design:** where two programs share a prefix, evaluate
  the second by re-evaluation against the first's memo, over at least three independent prefixes per task;
  report the variance of the paired difference beside the unpaired one."
- Use the consumer for a stage ablation by the same method (remove one gate, move one model) so that the
  long-pipeline regime gets a measured comparison at suffix cost. This is also the version of the
  evolution hypothesis most worth testing later: search over suffix variants of a long pipeline where
  intermediate signals exist and prefix reuse makes each evaluation cheap.
- Reword the Phase 6 "Cost control" row to state the dependence: "children reuse the parent's committed
  effects; comparisons are reported over several independent parent prefixes".

---

### F6 (major). The low prior on evolution is over-read from the project's evidence

**Section:** Phase 6 opening paragraph (lines 168–172); Findings table, Phase 6 row (line 41).

**Evidence.**

- The roadmap: "the meaningful structures for one coding task number about five, and enumerating them in
  Phase 1 showed no separation" (lines 169–171) [V].
- The Phase 1 report: "**This is an inconclusive pilot, not evidence that the neighbourhood is flat.**"
  The separation threshold (1.86 and 2.39 points) was as large as or larger than the gap between the merged
  fix and an inert stub on the same measure (lines 21–31) [V]. Two replicates per arm; anchors inverted in
  one batch (lines 126–127, 158–172) [V]. "No separation" on an instrument that could not separate the
  merged fix from a stub is not evidence about the programs.
- "About five" is the audit author's judgement (`scratchpad/audit/research.md` §4 item 2) [A], not a
  measurement. It is consistent with the literature in one sense: the vocabulary of motifs in ADAS, AFlow
  and GPTSwarm is small (generate, critique, vote or select, test, decompose, route or escalate) [L,
  moderate confidence]. It is misleading in another: the space those systems search is the product of
  motifs with model placement, fan-out, loop bounds, context routing and prompts, and that is where
  reported gains sit.
- The 18-of-18 convergence was measured under narrow conditions: one step from a trivial parent
  (`direct`), `topology-only` condition, one mutator model, six episodes per arm, mutators that had read
  the catalog seed implementing the same idea, and a task where the check never failed (Phase 1 report
  lines 212–219, 252–261, 396–398) [V]. "No child changed a model or an effort" (line 252–253) [V].
  Prompt-only and joint conditions never ran live, and adaptive multi-generation search never ran at all
  ("fresh adaptive launches ... refuse", closed roadmap line 167) [V].

**What the evidence does not touch, in my order of scientific interest** [I]:

1. *Parametric search inside a fixed structure:* model placement, fan-out, loop bounds, escalation
   thresholds and prompts. Cheap to enumerate, most likely to show a Pareto gain (cascade and escalation),
   and closest to what DSPy/GEPA-style optimisers already do, so novelty is low but decision value is high.
2. *Search over suffix variants of a long multi-stage pipeline with intermediate signals,* evaluated by
   prefix replay (F5). This is the variant where the project's assets change the economics.
3. *Evaluator search:* optimise a judge prompt against executed-test outcomes on the patches already
   collected. Fitness is cheap and exact (agreement with tests), the data exists, and success would reopen
   families that have no tests. Prior art exists for aligning LLM judges to labels (I believe Shankar et
   al. 2024, "Who Validates the Validators?", unverified), so this is useful more than novel.
4. *Evolving the task decomposition* for tasks that exceed one context. Plausibly where structure matters
   most and the most expensive to evaluate.
5. *Multi-generation structural search on single-context tasks.* Untested, and the least promising given
   the literature and the Phase 1 observations.

**Proposed change.** Replace lines 168–172 with: "The project has no measurement of search benefit. Phase 1
was inconclusive because its measure could not separate the merged fix from a stub. One-step,
topology-only proposals from `direct` converged on one idea (18 of 18) on tasks with no failing
intermediate signal; prompt, model-placement, multi-generation and long-task search were not run. The
prior is therefore low for structural search on single-context coding tasks and unformed elsewhere." In
the Findings table, change "all 18 children converged on one shape" to "all 18 one-step, topology-only
children converged on one idea".

---

### F7 (major). The Phase 5 gate cannot resolve its own threshold, so opening or closing Phase 6 would be decided largely by chance

**Section:** Phase 5 step 3 ("once per task", line 154); exit test and stop rule (lines 157–162).
The experiment-design reviewer owns the statistics; I raise it because it decides whether the result is
knowledge.

**Reasoning** [I; arithmetic by normal approximation to a paired binary comparison].

With 30–50 tasks, one run per cell and 20–40% of tasks discordant between two arms, the standard error of
a pass-rate difference is 6 to 11 points and the 95% half-width is 12 to 22 points. A workflow with no true
effect shows an observed gain of 10 points or more with probability 0.06 to 0.19. With about seven
non-direct arms and "any workflow" as the criterion, the chance that at least one clears the bar under the
null is roughly 0.3 to 0.7 (treating four to seven arms as independent; correlation lowers it somewhat). A
workflow with a true 10-point effect clears the bar half the time. One run per cell also cannot separate a
task-by-program interaction from run-to-run noise, which is the quantity that says whether there is
anything for a search or a per-task router to exploit. The audit's own power table makes the same kind of
point for the rubric measure [A].

**Proposed change.**

- Name at most two primary contrasts before spending (for example executed-test selection against
  direct-times-k random pick, and conditional escalation against the stronger direct call); everything
  else is descriptive.
- Run at least two replicates per cell, or halve the arm count to pay for them, and report the variance
  decomposition into task, program, task-by-program and replicate. State in advance: "if program and
  task-by-program components are within noise, there is nothing to search and Phase 6 does not open."
  This replaces 6a.
- Decide on an interval bound, not a point estimate, and confirm any winner on a held-out split fixed at
  assembly time.

---

### F8 (major). The roadmap has no statement of what is already known, so Phase 5 and Phase 3 would be reported as findings when they are replications

**Section:** whole document; no related-work or prior-results section. The closed roadmap had one
(`docs/plans/2026-10-18-orc-structural-search-roadmap.md` lines 625–653) [V].

**Evidence** [L unless marked].

- *Phase 5 arms.* Test-based selection among samples helps when samples are diverse and tests informative
  (AlphaCode; CodeT; Agentless on SWE-bench Lite): high confidence. Repair is about as good as equal-budget
  resampling and is bounded by feedback quality (Olausson et al.): high confidence on the gist. Review by
  the same model adds little; a different or stronger reviewer adds some. The project replicated the last
  point itself: "Verdicts from a same-model reviewer did not track quality"
  (`docs/reports/2026-09-28-orc-versus-single-call.md` line 283) [V], and +0.58 with a stronger reviewer
  [A]. The mechanism these results share is that structure helps only when it injects information the
  author did not have: another sample, another model, or an executed signal. That is a sharper hypothesis
  than "a workflow beats direct", it predicts which arms will and will not work, and the roadmap does not
  state it.
- *Phase 3.* See F5: prior art in Nextflow, Snakemake, Bazel, Nix and the build-systems literature; the
  open part is soundness and realised reuse for workspace-mutating agent effects.
- *Cost-controlled evaluation.* Kapoor et al. 2024 is the direct methodological precedent for Phase 5.
- I cannot verify the paper the closed roadmap cites for mutation convergence (Gurkan, Stonedahl and
  Wilensky 2026, arXiv 2606.05408); it is at the edge of my knowledge. The roadmap under review inherits
  that conclusion through the audit. Someone with access should confirm what the paper measured.

**Proposed change.** Add a short section "Prior results and what this roadmap adds" with one row per phase:
what is known, with whom; what this project's run would add (current models, metered cost, a typed
representation, effect reuse); and which outcome would be a surprise. Add the mechanism hypothesis to
Phase 5: "**H-Q-mech:** an arm gains over its compute-matched direct baseline only if it adds a sample, a
different model or an executed signal; arms that add none (same-model review, plan-first) do not." This is
falsifiable in both directions on the planned table and costs nothing extra.

---

### F9 (major). Knowledge already paid for is not harvested, and the roadmap's stated basis is not a durable record

**Section:** Basis (lines 15–17); Phase 5 step 1 (lines 144–146); Dispositions (lines 212, 218).

**Evidence.**

- The roadmap's basis is "the project audit of 2026-11-11" (line 15) [V]. No report dated 2026-11 exists
  under `docs/reports/` [V, directory listing]; the audit lives in a session scratchpad under `/tmp`. The
  evidence ledger of about 740 provider calls and its 14 findings [A] exist in consolidated form only
  there.
- The adversarial DAQ study is untracked (`git status` shows `?? experiments/adversarial_daq/`) [V] and is
  the only direct comparison with LangGraph.
- Step 1 computes what selection would have gained on existing pools but not the judge-reliability
  analysis the audit recommended (test–retest spread and rank agreement between rubric scores and hidden
  test fractions on patches that have both) [A]. That analysis needs no generation and decides whether any
  rubric-scored family can ever be used again. Note that E-A has no executed-test results (no "hidden"
  field in `docs/reports/2026-10-14-orc-versus-single-call-evaluated.md`) [V], so "selection by tests" in
  step 1 applies only to the E-B2, E-B3 and Phase 1 pools.
- The existing negative and instrument findings are themselves knowledge: the four-criterion rubric ranked
  the merged fix at or below candidates (Phase 1 report lines 169–172) [V]; the hidden-test rank order did
  not follow the rubric's (lines 152–154) [V]; design-review-execute gained 0.00 on hidden tests
  (`docs/reports/2026-10-15-calibrated-orc-versus-single-call.md` lines 26–27) [V].

**Proposed change.** Add to Phase 0: "commit the research audit as a dated report under `docs/reports/`;
record the adversarial DAQ study as a negative result (commit or archive, with its ledger); write one
consolidated 'what the experiments established' page listing each finding, its evidence and its limits."
Extend Phase 5 step 1 with: "on the pools that have both, report rank agreement between each judge's score
and the hidden-test fraction, and the retest spread of identical code; state which pools have no executed
tests."

---

### F10 (major). The cost axis that every quality and evolution statement depends on is not secured

**Section:** Phase 5 step 3 ("metered tokens per run", line 155); Phase 6 Fitness row (line 186);
Dispositions, Backlog row (line 217).

**Evidence.** All 79 Phase 1 log rows recorded `consumption: "unavailable"` (Phase 1 report lines 102–103)
[V]; in the three-arm run "metering is not wired" (lines 314–315) [V]; the closed roadmap lists "no
persisted usage in the evaluated runtime" as a standing limit (Routing And Records) [V]. Token-usage
accounting is an unselected backlog item (`docs/backlog/README.md` line 31) [V] that the roadmap keeps but
assigns to no phase (line 217) [V]. With mixed model placements, provider calls are not an admissible
cost proxy under `AGENTS.md` [V]. Without metering, Phase 5 can report pass rates only, and no Pareto
statement of any kind [I].

**Proposed change.** Add to Phase 4's work and exit test: "per-effect metered token usage recorded for
every provider and agent effect; a run's total reconciles with the provider's own receipt within a stated
tolerance". Add to Phase 5 step 3: "a run without complete metering is reported and excluded from the
frontier".

---

### F11 (minor). The consumer exit test records an event, not data

**Section:** Phase 5 exit test (line 157); Phase 1 exit test (line 72).

"The consumer completes a real multi-day task with at least one resume" and "a new author finishes the
tutorial without opening another document" are the charter's programmability and reuse hypotheses in
miniature (charter lines 40–41) [V], observed once each. **Proposed change:** state what is recorded:
author hours, defects by the stage that caught them (checker, run time, human gate), interruptions and
resumes with provider cost saved or lost, human interventions; for the tutorial, at least three authors
with time and failure points. Label both as case studies.

### F12 (minor). "Frozen" has no reopening condition

**Section:** stop rule (line 161). A frozen claim with no stated trigger is either permanent or arbitrary.
**Proposed change:** "Reopened only by a new task regime qualified under the informativeness check, or a
model generation for which the direct-call frontier is re-measured."

### F13 (minor). The Claims table understates what the project has learned about mechanism

**Section:** Claims table row 2 (line 24): "One small positive (E-A); the rest null, incomplete or
unmeasured". The September study's contrast between same-model and stronger-reviewer review (F8) and the
E-B2 executed-test null are the two most decision-relevant results. **Proposed change:** "Not shown.
Small rubric gains when a stronger or different model selects or reviews (2026-09-28, E-A); none from
same-model review; 0.00 on executed tests for design-review-execute (E-B2)."

### F14 (minor). Phase 6b's apparatus line conflicts with the process rules

**Section:** line 188 against lines 242–245. Covered in F3. **Proposed change:** "reused under the
oracle-family qualification of Phase 5; the judge-measure gates do not apply because no judge is used."

### F15 (minor). Selection inside programs and selection by the experimenter share an oracle

**Section:** Phase 5 step 3 and Phase 6 Fitness. If visible tests are a subset of scoring tests, a program
that overfits visible tests scores well on the overlap. **Proposed change:** report pass rate on scoring
tests that are not visible, separately.

---

## What the roadmap gets right

- It states the claim states honestly: "Not shown" and "Never measured" (lines 24–25) are accurate
  against the reports I read [V].
- It orders the work so that the engineering phases pay off whichever way the research turns out (lines
  27–28), and it gates the expensive, low-prior phase behind the cheap one.
- It moves the primary measure from an LLM rubric to pre-existing executable tests. The project's own
  evidence (anchors inverted, rubric not tracking tests) fully supports that move [V].
- It commits to a numeric refutation bar for the quality claim before spending, and to "no extension after
  a null" for Phase 6. Pre-committing the negative is rare and should be kept.
- It puts zero-spend analyses before spend in both research phases.
- It includes a Python control, which the charter has required since September and no study has run [A].
- Phase 3's stop rule preserves the soundness invariant ("a committed effect never re-runs and never runs
  with different inputs") over the feature, and its three spike questions are the right ones.
- It stops the calibration loop and the per-step governance that consumed spend without producing a
  completed comparison [A], and every phase carries a "makes harder" line.

---

## Consolidated change list

**Add**

1. Hypotheses with support and refutation conditions for all three claims: H-G1, H-G2, H-G3 (F4, F5),
   H-Q and H-Q-mech (F2, F8), H-E1 and H-E2 or an explicit cut (F3).
2. A task-family informativeness check on direct runs alone, before any workflow arm (F1).
3. Compute-matched direct arms, oracle and random pick bounds, one escalation arm, and a fixed
   visible/scoring test split (F2).
4. Measurements for the memo: reuse under real edit histories, the crash matrix, paired evaluation by
   prefix replay over several prefixes (F4, F5).
5. Replicates and a variance decomposition in place of 6a; at most two primary contrasts; a holdout fixed
   at assembly (F7).
6. A "prior results and what this adds" section (F8).
7. Phase 0 zero-spend records: the audit as a report, the DAQ result, the resume-use retrospective, the
   judge-against-tests analysis (F4, F9).
8. Token metering as a Phase 4 deliverable (F10).

**Cut**

1. Phase 6a as written (search over about eight recorded programs).
2. Phase 6b as a generic "does search find better programs" test, unless reframed as H-E1 and H-E2 with
   controls.
3. "Tested in Phases 1–4" for the engineering claim.

**Reword**

1. The stop rule's consequence, scoped to single-context coding tasks, with a reopening condition (F1,
   F12).
2. The exit test and stop rule of Phase 5 into one criterion consistent with the `AGENTS.md` definition of
   "better" (F2).
3. The Phase 6 prior paragraph and the Findings row, to match the Phase 1 report's own reading (F6).
4. Owner decision 2, to confirm named hypotheses and their refutation conditions (F4).
