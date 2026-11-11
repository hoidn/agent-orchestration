# Practical-value review: ORC roadmap "Usable Pipelines First, Then Program Evolution"

Task id: `review_plan_roadmap_practical_value`. Role: reviewer (read-only). Artifact: draft roadmap
`docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md` (called "the roadmap" below).

Claim marks: **[RAN]** verified by running in the probe directory; **[READ]** verified by reading the
cited file; **[INFERRED]** reasoning or general knowledge of other tools, not checked here.

Probe directory (provider-free, 1.4 MB):
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/roadmap-review/practical-probe/`
(`workflows/examples/` = the copied Python command loop; `mine/`, `mine2/`, `mine3/` = hand-written
three-step command pipelines and deliberate mistakes). Python 3.13.9, `PYTHONPATH` set to the checkout.

## Verdict

The roadmap is ordered the right way round (make the tool usable, then test the research claims) and
its Phase 1 list is accurate: I reproduced every defect it names. But as written it would not yet
produce a tool someone chooses, for two reasons. First, its "cheap to iterate" phase (Phase 3) is
specified and tested on a prompt edit, while the edit a pipeline author makes most often, fixing the
script of the step that just failed, hits a different refusal that the roadmap never mentions: today
that run can never be resumed, and Phase 3's exit test would pass without changing that. Second, the
only real user appears in Phase 5, unnamed and tied to a draft design, after four phases whose exit
tests are all internal (an audit probe, a tutorial, lines deleted, example parity); nothing between
Phase 0 and Phase 5 is pulled by someone trying to get work done. Fix those two and the plan becomes
a credible route to a tool the owner would use for multi-day agent pipelines. The system's real
advantage is narrow and worth stating: cross-vendor CLI coding agents with typed, validated handoffs,
control flow the agent cannot skip, durable human gates and a per-attempt audit trail, all without a
service. The roadmap spends most of its effort elsewhere (deletion, example parity, a benchmark and a
search phase) and omits three things a user of expensive runs asks for first: seeing progress,
seeing cost, and installing it outside this checkout.

## Answers to the six questions

### 1. Who is the user after each phase, and what can they newly do?

| Phase | User | Newly practical job | Mark |
| --- | --- | --- | --- |
| 0 | The maintainer only | None. Finding the next work item | [READ] |
| 1 | A new author (person or agent) with one hour | A short serial pipeline of commands and agent calls that survives a crash: plan, review, revise, execute on one coding task. Works today, but the natural loop form crashes the compiler and a successful run prints nothing | [RAN] |
| 2 | Maintainers and contributors | None for a user, apart from a shorter guide and one target | [INFERRED] |
| 3 | Someone developing a long pipeline | Multi-hour pipelines under development: change step k of n and keep steps 1..k-1. This is what makes a paper-writing pipeline or a train, evaluate, analyse pipeline practical, but only if the script-edit case is included (finding B1) | [RAN] for today's refusals |
| 4 | Python authors | A parallel best-of-N coding run that survives a kill; mapping one procedure over a list (sections of a paper, datasets, backlog items) | [READ] |
| 5 | The owner as a real user | A multi-day agent pipeline with human gates. The gate mechanism exists today at target 2.40 (`workflows/examples/durable_host_input/README.md`), so Phase 5 adds proof by use, not capability | [READ]; example not run |
| 6 | A researcher of program search | Nothing for a pipeline user | [READ] |

A paper-writing pipeline needs human gates (exist), document fills (exist), edit and continue
(Phase 3) and per-section fan-out (Phase 4). It is practical after Phase 3, comfortable after Phase 4.

### 2. Against the alternatives

All comparisons with other tools are **[INFERRED]** from general knowledge; none was run.

| Alternative | Where it beats this system after the roadmap | Where this system wins |
| --- | --- | --- |
| Plain Python with retries and a JSON cache | Zero learning cost; any library; edit anything and rerun, since the cache key is whatever you choose; 60–90 lines for the README example (the repo's own showcase concedes no line-count win) | The pipeline is checked before it runs; result contracts are rendered into the prompt and validated before commit; crash safety is not hand-rolled |
| LangGraph | Checkpoints that tolerate code edits, fork from any checkpoint, interrupts for humans, traces with token and cost, large ecosystem, API-level models and tools | Drives whole CLI coding agents (Claude Code, Codex) from different vendors; whole-pipeline compile-time checking; no service |
| Temporal | Same replay model, plus code versioning, activity timeouts and heartbeats, a UI, schedules, many machines | No server to run; a run is a directory; typed prompt and result contracts |
| Snakemake, DVC, Nextflow, Prefect, Airflow | For command-step pipelines these already are build caches: change a script and only it and its dependents rerun; cluster execution; mature | Agent steps are first class; typed values instead of files only; human gates |
| Claude Code or Codex subagents and built-in workflows | Nothing to install or learn; the agent decomposes the task itself; worktree isolation and interactive steering built in | Deterministic gates the agent cannot skip; a reviewer from another vendor; exact resume across days; an audit trail of every composed prompt |

Does the roadmap spend on the winning ground? Partly. Phases 1 and 3 attack the two largest losses
(learning cost and the iteration loop), which is correct. But Phase 3 as specified competes with the
build-cache tools on general program edits while leaving the command-script case out, and the winning
ground gets one unnamed line in Phase 5. See finding M1.

### 3. The first hour, tried

What I did and hit, in order. All **[RAN]** unless marked.

1. README "Try it" sends a provider-free reader to the Python guide, which says to run from the
   repository root (`docs/python_workflow_drafting_guide.md:22-24`); doing so writes `.orchestrate/`
   into the checkout. I copied the three example files to the probe directory instead. **[READ]**
2. The Lisp drafting guide's first 200 lines are routing, retirements, language-server caveats and a
   migration promotion checklist; the first runnable recipe is at line 480 and depends on a test
   fixture's provider shim. **[READ]**
3. `python -m orchestrator --help`: 1.75 s, 20 subcommands, of which 8 are maintainer or retired
   surfaces (`trial`, `peer-*`, `provider-materialization-submit`, ...). `run --help` lists about 35
   flags including YAML-era ones (`--clean-processed`, `--archive-processed`, `--context`).
4. `py build` 4.4 s; `py run ... --input limit=3` 5.4 s, exit 0, **no output at all**. I found the
   result with `ls .orchestrate/runs` and `report --run-id`. `--verbose` and `--stream-output` on a
   command-only run also print nothing.
5. Every command repeats the manifests: the documented example line is about 200 characters, five
   times. There is no default discovery ("There are no default extern bindings",
   `docs/python_workflow_drafting_guide.md:107`).
6. My own `.orc`, first attempt without a manifest: `[command_adapter_missing_contract] ... is missing
   command boundary metadata`. Correct, but it names neither the flag nor the file shape.
7. `"bash" "-c" "python one.py"` as argv is refused: `[inline_shell_command_in_workflow]`. An existing
   script cannot be wrapped without editing it to write JSON to `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
8. A failing step prints one line: `[command_exit_nonzero] evaluated command failed with exit code 3`.
   No step name, no stderr, no run id, no next command. The stderr was under
   `.orchestrate/runs/<id>/effects/<sha256>/attempt-1/stderr.txt`; `report` does not show it either.
9. Resume after a transient failure works and reruns only the failed step
   (`[effect_rerun] workflow:pipe::run / b attempts=[1]`). This is the good part.
10. Resume after editing a later step's argv: `[resume_program_changed] current program differs from
    the run header`, no recourse named.
11. Resume after fixing the failing script: refused for good (finding B1).
12. The roadmap's own items reproduce: `(continue (command-result ...))` gives `[compiler_defect] ...
    unsupported WCC elaboration node: CommandResultExpr`; a loop without `:on-exhausted` compiles and
    fails at run time with `[loop_exhausted]`; a source with two mistakes (an undeclared command
    boundary and an unknown callee) reports one.
13. Python-generated effect identities are `workflow:py/python_command_loop::run / _e1 / body /
    loop:_loop0[1] / else / _e0`, and `invalidate` needs that string typed exactly. Hand-written
    `.orc` gives `workflow:pipe::run / b`.

Phase 1 fixes items 4 (at the end of a run), 8 and 12. It does not address 1, 5, 6, 7, 10, 11 or
progress during a run, and it spends an exit criterion on `--help` under 0.5 s, which did not matter
in the probe (finding M2).

### 4. Is Phase 3 what users would value most?

It is the right category and the most valuable listed phase, but specified on the wrong edit (B1).
Things a user of expensive runs would rank at least as high, and which the roadmap omits: per-step
and total token or cost reporting with a spend cap (M3); progress lines while a run is in flight
(M2); installing and running from another repository (M4). A hosted or shareable view ranks lower:
`report --format md` and the local dashboard already exist, and one shareable file is enough.

### 5. Is the Phase 5 consumer a real test?

No (finding B2). It is unnamed, it is to be "built on" a design whose own status line says "draft
target design; not an implemented framework or runnable example", and its exit test ("completes a
real multi-day task with at least one resume") can be met by a staged kill.

### 6. Effort without user value

Phase 2's line-count target ahead of Phase 3 (M5); Phase 4's "every catalog example has a Python
version" and a paid comparison to decide the fate of Agent Sessions (M6); the `--help` latency
criterion (M2); Phase 6 as a full section of a roadmap whose claim it says is unpromising (m3).

## Findings, most severe first

### B1 (blocker). Phase 3 omits the script-fix case, and its exit test passes without it

- **Section:** "Findings this roadmap answers" (row for Phase 3); "Phase 3: Edit and continue".
- **Evidence [RAN]:** `mine2/`: three steps, each its own script and command boundary; `two.py` raises.
  `run` fails at `b`. I deleted the bug from `two.py` and ran `resume`:
  `[effect_input_diverged] workflow:pipe::run / b: effect input diverged (retry implementation files
  changed: ['["workspace","two.py",1]', ...])`, exit 2. `invalidate <run> "workflow:pipe::run / b"`
  gives `[invalidate_not_committed]`. `resume --force-restart` gives `[evaluated_execution_unavailable]`.
  In `mine/` (steps share one script) invalidating the committed step `a` reran `a` and then refused at
  `b` the same way. The only way forward is a new run that repeats every earlier step.
- **Evidence [READ]:** this is the contract, not a bug.
  `docs/design/workflow_lisp_evaluated_execution.md:1410-1420`: the failed attempt's file evidence "is
  the retry baseline ... Restoring the original bytes/targets permits the ordinary next-attempt rule
  ... No override or additional approval surface is introduced. An invalidation ... cannot forgive a
  newer uncommitted attempt's closure mismatch." Same rule in `specs/cli.md:534-541`.
- **Why it matters [INFERRED]:** in a research pipeline (six hours of training, then an analysis script
  with a typo) this is the commonest failure, more common than a prompt edit. The roadmap's finding row
  names only `resume_program_changed`, Phase 3 names only §8.4, and the exit test edits "the third
  step's prompt". A run that meets that exit test still discards six hours on a typo.
- **Proposed change:**
  1. Findings row for Phase 3, add: "A command that failed because of a bug in its own script cannot be
     resumed once the script is fixed (`effect_input_diverged`, retry baseline, evaluated execution
     §8.1 C4); a changed bound file refuses resume instead of rerunning the effects that bind it."
  2. Phase 3 "This changes an accepted contract": name the retry-baseline rule and C7's committed
     divergence refusal alongside §8.4.
  3. Exit test, replace with two cases: "(a) in a four-step run whose third step failed, fix the third
     step's script; resume runs steps three and four only. (b) in a completed four-step run, edit the
     third step's prompt; resume re-runs steps three and four only. Kill-at-every-commit tests still
     pass."
  4. Order inside Phase 3: case (a) first. It needs no identity or journal-order work, because the
     effect has no committed result to protect, so it can ship before the spike's three questions are
     answered. **[INFERRED]**; the design reviewer should confirm.

### B2 (blocker). The only real user arrives last, unnamed, on a draft design

- **Section:** "Phase 5: One real consumer"; "Order and dependencies"; owner decision 5.
- **Evidence [READ]:** roadmap lines 140-142 and 157; `docs/design/workflow_lisp_progressive_execution.md`
  line 5: "Status: draft target design; not an implemented framework or runnable example", scope "a
  software-task demo". README lines 202-205: the physics runs "used an earlier YAML frontend that has
  since been retired".
- **Evidence [RAN]:** `find /home/ollie/Documents/PtychoPINN -maxdepth 6 -name '*.orc'` returns nothing;
  its worktrees hold `workflows/*.yaml`; the newest directory under its `.orchestrate/runs` is dated
  2026-08-26. So the owner's scientific pipelines do not run on the current runtime. Other `.orc`
  consumers do exist outside the repo (for example
  `/home/ollie/Documents/daq-debate-framework-v4-live/workflows/daq_debate.orc`, target 2.40).
- **Why it matters [INFERRED]:** Phases 1–4 are steered by an audit probe and internal counts. The
  friction I found in one hour (B1, M2, M4) differs from the audit's list; a real pipeline will differ
  again. Finding that out in Phase 5 means reworking Phases 1, 3 and 4.
- **Proposed change:**
  1. Move owner decision 5 to selection time and require a name: an existing piece of the owner's work
     that would otherwise be run by hand, by Claude Code subagents, or on the retired YAML release.
  2. Start the consumer after Phase 1 as a running thread, not a phase: port it serially, keep a
     friction log, and let that log choose the Phase 3 and Phase 4 work items.
  3. Drop "built on progressive execution"; say "written as an ordinary workflow; progressive execution
     is used only if the consumer needs it".
  4. Replace the exit test with: "the pipeline's output is used (merged change, figure or section in
     the paper); the run had at least one unplanned failure recovered by resume and one mid-run edit;
     every fallback to manual orchestration and every run restarted from scratch is logged with the
     compute it discarded; the owner records whether the next such task will use the tool, and what
     they would have used instead."

### M1 (major). The roadmap does not say where the tool is chosen, so effort is not aimed there

- **Section:** "Claims"; whole ordering.
- **Evidence:** table in answer 2 **[INFERRED]**; README lines 18-34 state the checked-pipeline
  argument but no phase is tied to it **[READ]**.
- **Proposed change:** add under "Claims" a short "Where this is chosen" statement: "pipelines of CLI
  coding agents from more than one vendor, lasting hours to days, with typed validated handoffs, gates
  the agent cannot skip, human decisions and an audit trail, on one machine with no service. Not
  chosen for: command-only data pipelines (Snakemake, DVC), API-level agent graphs (LangGraph),
  fleet-scale durable execution (Temporal), or tasks one agent session finishes." Then test each
  phase's work list against it. Scope Phase 3 to the two edits in B1, not to general reuse under any
  program edit.

### M2 (major). Phase 1 fixes real friction but misses the friction of a long run

- **Section:** "Phase 1: The first hour".
- **Evidence [RAN]:** answer 3, items 4, 5, 6, 8, 10. A run prints nothing while in flight, even with
  `--verbose`; a failure prints no run id; refusals name no recourse; manifests are repeated on every
  command. `--help` took 1.75 s, `compile` 2.75 s, against steps that take minutes.
- **Proposed change to the work list:** add "print the run id on the first line and one line per
  effect start, commit and failure; every resume refusal (`resume_program_changed`,
  `effect_input_diverged`, `invalidate_not_committed`) names what changed and the command that
  recovers; `commands.json`, `providers.json` and `prompts.json` beside the source are picked up when
  the flags are absent; hide maintainer subcommands and retired flags from `--help`; the tutorial
  includes wrapping an existing script as a command". Replace the exit criterion "`--help` returns in
  under 0.5 s" with "a failed run can be diagnosed and resumed using only what the terminal printed".
  Keep the lazy imports only if they are a one-line change.

### M3 (major). Token and cost accounting is assumed by Phases 5 and 6 and scheduled nowhere

- **Section:** "Phase 5" step 3 ("metered tokens per run"); "Phase 6" fitness; "Dispositions" (backlog
  row).
- **Evidence [RAN]:** `grep -rni "token_usage\|usage" orchestrator/workflow/evaluated` returns nothing;
  the memo records of my runs carry no usage field.
- **Evidence [READ]:** `docs/backlog/active/2026-04-30-provider-step-token-usage-accounting.md`:
  "unselected structured usage-accounting proposal". The owner already hand-built a dollar gate for one
  experiment (`experiments/orc_research_demo/cost_gate.py`, SQLite ledger).
- **Why it matters:** the benchmark's cost axis and the `AGENTS.md` definition of "better" need it, and
  it is the first question about any multi-day agent run. **[INFERRED]**
- **Proposed change:** add to Phase 4's work list: "record per-attempt provider token usage in the run
  where the agent CLI reports it; `report` shows per-step and total tokens and priced cost; an optional
  per-run spend cap stops before the next provider call". Exit test: "the report of a real two-provider
  run shows tokens per step and a total". Change the backlog disposition from "keeping" to "moved to
  Phase 4".

### M4 (major). Nothing makes the tool usable outside this checkout

- **Section:** "Phase 1" exit test; "Phase 5" ("outside this repo").
- **Evidence [READ]:** README lines 220-225 (clone plus `pip install -e`); Python guide line 22-24 (run
  from the repository root); Lisp guide lines 542-545 ("this checkout's `orchestrator` must be the one
  `python -m orchestrator` imports; another installed checkout refuses target 2.35").
  `orchestrator/providers/registry.py:136-141` pins default models (`claude-opus-4-6`) that the README
  example overrides. `pyproject.toml` still depends on PyYAML although the guide says the dependency
  was removed.
- **Proposed change:** Phase 1 exit test, add: "in a fresh virtual environment and an empty directory
  outside the checkout, `pip install` from the repository URL followed by the tutorial succeeds".
  Phase 1 work, add: "tutorial commands run as one smoke test so they cannot rot".

### M5 (major). Phase 2 puts a deletion target ahead of the first feature a user feels

- **Section:** "Phase 2: Delete and unify"; "Order and dependencies".
- **Evidence [READ]:** exit test "at least 30k lines removed"; order "0 → 1 → 2 run in sequence", with
  only Phase 3's spike allowed to overlap. None of the Phase 2 exit criteria is visible to an author
  except the guide length.
- **Proposed change:** move the user-visible parts (cut the drafting guide, one documented target,
  CLI vestiges out of `--help`) into Phase 1. Make the rest of Phase 2 a time-boxed background lane
  with the exit test "suite no worse; removed surfaces listed", and let Phase 3 case (a) of B1 proceed
  without waiting for it. Keep the line count as a readout, not a gate.

### M6 (major). Phase 4's exit test is parity work with no user

- **Section:** "Phase 4: Python first, parallel map".
- **Evidence [READ]:** "every catalog example has a Python version that builds to the same checked
  program shape"; "run the Agent Sessions comparison (PQ-1c) once" with provider spend. **[RAN]:**
  Python-generated identities are unreadable (answer 3, item 13), which is the thing an author meets.
- **Proposed change:** exit test becomes "the Phase 5 consumer is written in Python and uses
  `parallel_map`; a parallel best-of-N run survives a kill and resumes; `invalidate` accepts a readable
  name". Examples are ported only when the consumer or the tutorial needs them. Decide Agent Sessions
  by whether the consumer needs a retained conversation; run PQ-1c only if it does.

### m1 (minor). The first-hour surface is undecided

- **Section:** Phase 1 (tutorial) versus Phase 4 ("Python first").
- **Evidence [READ]:** the tutorial's language is not stated; Phase 4 later makes `.orc` "the generated
  form most authors never write". A Lisp tutorial written in Phase 1 is rewritten in Phase 4.
- **Proposed change:** state in Phase 1 which surface the tutorial teaches. If Python, move "readable
  generated names" from Phase 4 to Phase 1.

### m2 (minor). "A new author finishes the tutorial" has no tester

- **Section:** Phase 1 exit test.
- **Proposed change:** name the tester: the owner on a clean machine, or the smoke test in M4.
  **[INFERRED]**

### m3 (minor). Phase 6 takes a full section for a claim the roadmap calls unpromising

- **Section:** "Phase 6: Program evolution".
- **Proposed change:** keep 6a (free replay on the recorded table) as a closing step of Phase 5; reduce
  6b to two lines under "not selected; opens only on Phase 5's bar and a new owner decision".

### m4 (minor). The benchmark yields no guidance for a user

- **Section:** Phase 5 benchmark.
- **Proposed change:** add to the exit test: "one page states when a workflow is worth using over a
  direct call, with the measured cost multiple", replacing the README "Experiments" table as the
  reader-facing answer. **[INFERRED]**

## What the roadmap gets right

- Engineering value first, research claims after, with stop rules that freeze a claim on a null.
  **[READ]**
- Phase 1's defect list is accurate; each item reproduced in the probe. **[RAN]**
- It identifies the iteration loop as the main gap; resume after a transient failure already works and
  reruns only the failed step. **[RAN]**
- It declares the claims table honestly ("Supported by the runtime; hard to use today"; quality "Not
  shown"). **[READ]**
- Each phase states what it makes harder, and spend is requested once per phase. **[READ]**
- Python-first is the right direction for adoption: the Python loop example built and ran first time,
  where the same loop written the natural way in `.orc` crashed the compiler. **[RAN]**
- The process rules cut ceremony ("full review ceremony only after a consumer has used it"). **[READ]**
