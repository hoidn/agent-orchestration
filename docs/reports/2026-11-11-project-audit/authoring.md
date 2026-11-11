# Authoring-surface audit (review_code_authoring_surface_audit)

Repo: /home/ollie/Documents/agent-orchestration, branch main, HEAD bb63b03b. Date 2026-11-11.
Method: read the examples, stdlib and guides; ran provider-free probes with
`PYTHONPATH=<repo>`. Everything marked **[RAN]** was executed in this session;
everything else is from reading. No provider was called; the only "provider" used
was the checked-in `stub_provider.py` shim from `workflows/examples/durable_host_input`.

Repo writes: none to tracked files. `py build` and `compile`, run once each from the repo
root as the README/guide prescribe, wrote build artifacts into the gitignored
`.orchestrate/` (`compile` has no `--state-dir`). All other probes ran in
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/audit/`.

---

## 1. The language as experienced

### Per-example accounting

| Workflow | LOC | Essential logic | Ceremony / repetition | Side files |
| --- | --- | --- | --- | --- |
| `workflows/examples/plan_review_execute.orc` | 35 | 3 records, 4 one-line prompts, 9-line workflow (26-34) | 5 header lines + 6 comment lines; very low | `inputs/plan_review_execute/providers.json` (4), `inputs.json` (3) |
| `workflows/examples/design_review_execute.orc` | 64 | 2 `defpath`, 4 records, 4 prompts, 14-line workflow | 2-line export of 11 names (5-6); `:effort "high" :timeout-sec 3600` repeated 4x (55-62); 12-line prose comment; prompts are single lines up to **1,139 chars** with `\n` escapes (36) | providers.json, inputs.json |
| `workflows/examples/design_review_execute_agents.orc` | 74 | only lines 63-73 differ in substance (2 `agent` bindings) | ~38 lines duplicated verbatim from the baseline (diff: 36 changed lines of 74); comment 17-24 is status jargon ("C8", "PQ-1a qualification report", "bounded adapter smokes", "separate gate") | providers.json, inputs.json |
| `experiments/orc_vs_single_call/workflows/best_of_n.orc` | 66 | union-free; `list/map-effect` over repos + judge | `implement-one` exists only because the map body must be one effect/call (31-40); judge call duplicated verbatim in `select-only` (49-53 vs 61-65); model/effort/timeout repeated | `best_of_n.providers.json`; caller must pre-create clones |
| `workflows/examples/python_command_loop.py` | 20 | a 12-line `loop` | argv written twice: in the `.py` (16) **and** in `python_command_loop.commands.json` (`stable_command` + `closure`); tool must write JSON to `$ORCHESTRATOR_OUTPUT_BUNDLE_PATH` (tool.py:9) | commands.json (11), tool (11) |
| `workflows/examples/durable_host_input/approval.orc` / `approval.py` | 52 / **103** | diagnose → verify → typed approval → 3-way match | Python twin is 2x longer: enums restated as `X = "X"`, `class Evidence(RelPath, under=..., must_exist=True): pass`, lambdas per arm; Lisp side repeats `("python" "action.py" ...)` 4x (38-50) | commands.json, providers.json, stub_provider.py, action.py, README with a 68-line bash recipe |

Overall: the *workflow* code is short and mostly essential. The ceremony is
outside the `.orc`: 1-3 JSON manifests per workflow, long CLI invocations
(the improve example needs 5 flags + `--input-file`), and the
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` protocol for every command.

### At its best

```lisp
;; plan_review_execute.orc:17-18, 29-30 — a prompt is a typed function; field access is checked
(defprompt draft-plan (:fills (task :text)) -> Plan "Plan this task ... Task: {task}")
(feedback (provider-result providers.codex :prompt (review-plan :task task :steps draft.steps)))
```

```lisp
;; reviewed_change.orc:21-25 — outcomes as a closed union, matched exhaustively at 78-106
(defunion Review
  (APPROVE (report ReviewReport) (notes List[String]))
  (REQUEST_CHANGES (report ReviewReport) (summary String) (findings List[String]))
  (WRONG_APPROACH (report ReviewReport) (reason String))
  (NEEDS_HUMAN (question String)))
```

```lisp
;; durable_host_input/approval.orc:22-25, 35-48 — a human decision is just another typed effect
(defproc approval (...) -> HostReply[Approval]
  (request-input (approval-question :cause cause :summary summary :guide guide)
    :timeout-sec 3600 :show (evidence)))
(match reply ((ANSWERED answer) ...) ((CANCELLED _) ...) ((EXPIRED _) ...))
```

### At its worst

```lisp
;; design_review_execute.orc:36 — a 1,139-character single-line string literal with \n escapes;
;; no multi-line/heredoc prompt literal is used anywhere in the examples
(defprompt draft-design (:fills (task :text)) -> Draft
  "You are designing one feature for this repository, ...\n\nWrite the design document ... Change no other file.\n\nTask:\n{task}\n\nReturn `doc`: ...")
```

```lisp
;; reviewed_change.orc:62-67 and std/improve.orc:31 — :on-exhausted uses `state`
;; before the (fn (state) ...) that binds it; the bound 3 is restated at 82 and 94
(loop/recur :max 3
  :state (loop-state (round Int 1) ...)
  :on-exhausted (variant Outcome UNRESOLVED :reason "round limit reached" :rounds state.round)
  (fn (state) ... (if (= state.round 3) ...
```

```lisp
;; std/improve.orc:7-9 — the stdlib documents a compiler gap I then hit myself (see §5)
; Both hook results are bound with `let*` before use, because the frontend
; does not yet lower an effectful hook call written directly as a `match`
; scrutinee or a `loop-state :like` field (WCC elaboration and pure projection).
```

---

## 2. Abstraction quality

### Core concepts and how they compose

| Concept | Verdict |
| --- | --- |
| `defrecord` / `defunion` / `defenum` / `defpath` | Clean, central. Unions + exhaustive `match` are the strongest idea. `defpath` (root + must-exist) is a good domain type. |
| `defprompt ... -> T` with `:fills` renderers (`:text`, `:value`, `:doc`, `:path`) | Clean: a prompt is a typed function, the result contract is derived from `T`. The renderer kinds are a small extra concept. |
| `provider-result` / `command-result` | Uniform effect call with typed return. `command-result` needs a manifest entry naming the same argv (see §1). |
| `agent` (2.38) | Composes nicely: `(provider-result designer ...)` where `designer` is an `Agent` value (agents.orc:63-65). |
| `request-input` / `HostReply[A]` (2.40) | Composes cleanly with `match`. |
| `loop/recur` + `done`/`continue` + `loop-state :like` | Workable but quirky: `:on-exhausted` scoping, optional exhaustion handler (missing → **runtime** `loop_exhausted`, not a compile error; Python frontend makes it mandatory), and an elaboration gap for effects inside `continue`. |
| `list/map-effect :max N` | Special case: body must be a single effect, so best_of_n invents a wrapper workflow. No filter/fold/index. |
| `defproc`, `let-proc`, `proc-ref`, `ProcRef[...]`, `:forall`, `:where`, `:effects`, `:lowering` | The heaviest layer. Needed for `std/improve`. `:effects`/`:lowering` are target-dependent (explicit at 2.35-2.38, inferred at 2.39). |
| `std/improve` | Two different modules with the **same name** and different signatures, selected by target: `stdlib_modules/std/improve.orc` (5 params, explicit `inputs`) vs `stdlib_modules/w3/std/improve.orc` (4 params, local hooks). |
| run-ref, peer groups, confined children, phased contract delivery, prompt obligations | Specialist surfaces; the guide spends hundreds of lines on them (§8 is 600 lines). Not needed for the common case. |
| Section 13 "Standard high-level forms" | 5 of 7 entries (`run-provider-phase`, `resume-or-start`, `resource-transition`, `finalize-selected-item`, `backlog-drain`) are documented as unavailable / `closed_program_gap` (guide:2666-2704). |

Minimum concepts for a correct review-revise-execute workflow (hand-written,
like reviewed_change.orc): header (`:language`, `:target-dsl`), `defmodule`
(must equal the file path) / `export`, `defrecord`, `defunion`, `defpath`,
`defprompt` + renderer kinds, `provider-result`, provider manifest +
provider template names, `let*`, `match` + variant binders, `loop/recur` +
`:max/:state/:on-exhausted` + `done`/`continue`, `loop-state` + `:like`,
`variant` construction. **About 14.** With `std/improve` add `import`,
`let-proc`, `proc-ref`, generic `Decision[F B]` and the `Improvement`
variants: **about 18**, plus knowing which target selects which `improve`.

### Against the alternatives

Plain Python + subprocess, same plan_review_execute: ~60-90 lines (4
subprocess calls, a JSON-schema or dataclass validator per result, a
"write result to this file" instruction appended to each prompt, a JSON
cache keyed by step name for resume). The repo's own showcase
(`experiments/orc_vs_python_showcase/README.md`) makes that comparison
honestly and says "There is no general claim that ORC needs fewer lines."

What this system gives that those do not, and whether it is real:

- **Typed provider results with an auto-rendered output contract + validation before commit.** Real, and the most user-visible win. LangGraph/Agent SDK give per-call structured output but not compile-time checking that `feedback.findings` exists and is `List[String]` before the run. **[RAN]** a misspelled field gives `[record_field_unknown] unknown field \`word\`` at line:col before anything runs.
- **Effect memo + resume.** Real **[RAN]**: a failed loop iteration reran only the failed command; earlier commands were reused. Temporal gives the same thing (and more). The limit for users is that **any** source edit blocks resume (§5: a prompt-text edit gives `resume_program_changed` on a suspended run), so "fix the prompt and continue" is not possible. Temporal has workflow versioning; LangGraph checkpoints let you edit code freely.
- **Closure/implementation-file identity.** Real **[RAN]**: editing a command script after it ran gives `effect_input_diverged ... input parts changed: ['implementation_files']`. That protects you, but there is no guided way out beyond `invalidate <run> "<identity string>"`.
- **Invalidation.** Works **[RAN]**, but it does not roll back the workspace, so a non-idempotent command runs twice on the same files and the result is wrong (§5). Users have to know that.
- **Prompt identity / composed-prompt inspection.** Useful for debugging (`effects/<id>/attempt-n/prompt.txt`).

Net: the advantage is real for long, expensive, multi-agent pipelines where
a typed handoff between agents and resume after a crash are worth a new
language. For short scripts, Python + Agent SDK is cheaper to learn. Effect
identity is tied to the frontend: the same workflow in `.orc` and `.py`
gives different provider identities (**[RAN]**: the stub chose
`BROKEN_RECORD` for Lisp and `MISSING_METADATA` for Python).

---

## 3. Python frontend vs `.orc`

- Design (`docs/design/python_workflow_frontend.md:12-30`): registration plus
  symbolic tracing that emits ordinary `.orc`; "never a second interpreter".
  Clean design, small implementation (`orchestrator/py/`, 3,033 lines, ~30
  exported names).
- Excluded today (guide:138-141, design): agent sessions, parallel
  `list/map-effect` (no map at all in `orchestrator/py`), macros, runtime
  callbacks / `ProcRef` construction (so **no `std/improve` from Python**),
  `Prompt.extern` questions, native `if`/`and`/`for` over runtime values.
  So best_of_n, the agents example and the std/improve example cannot be
  written in Python today.
- Ergonomics **[RAN]**: my probe ported to Python compiled on the **first**
  try, and the hand-written `.orc` took two (the Python emitter let-binds
  every effect, so it avoids the compiler defect). Python diagnostics are
  good: `grow_py.py:25:1: python_symbolic_coercion: Symbolic runtime values
  require when/all_of/any_of/not_ instead of Python truth testing`;
  `python_symbolic_attribute: No readable symbolic field \`wrds\``. The
  column is always 1.
- Costs: `when(cond, then=lambda: ..., else_=lambda: ...)` and lambda-per-arm
  `match` are clumsy (approval.py:86-103 is twice the Lisp). Run state and
  reports show generated names (`run / _e1 / body / loop:_loop0[1] / else /
  _e0`), so the user debugs code they did not write. Build takes ~8 s.
- Verdict: Python is the more promising **primary** surface for
  adoption: mainstream tooling, it avoids the `.orc` elaboration gaps, and it
  has good errors. It should not be a reimplementation: it is a thin emitter,
  so the dual surface is cheap *as long as* `.orc` stays the semantic core
  and Python gets the missing features (map, proc refs, agents). Today the
  two surfaces have diverged (mandatory vs optional `on_exhausted`; the
  feature subset), and the authoring guidance needs a feature-parity
  table. Readable generated names (use the Python variable names) would
  remove most of the debugging cost.

---

## 4. Documentation as product

- **README** (331 lines): the pitch (Motivation, the plan_review_execute
  example, the "what is checked" table, honest experiment outcomes including
  "NOT EVALUATED") is good and honest. The "Scale and provenance" table
  (226,951 Python lines, 8,328 tests) argues against the product: it says "big".
  Release/target paragraphs (279-301) are maintainer material.
- **Clone to first success** **[RAN]**: `pip install -e` → `compile` (3.8 s, prints
  JSON) → the README's `run --dry-run` prints **nothing at all**, exit 0,
  even with `--verbose`. A newcomer cannot tell whether it did anything. The
  first *visible* success is the Python guide's recipe (5 commands of about 170
  chars each). `run` is also silent on success; you have to open `state.json`
  or call `report`. The README offers no provider-free `.orc` run (the
  durable_host_input README has one, but it is a 68-line bash script with a
  PATH shim). CLI startup is ~3 s even for `--help`.
- **Drafting guide**: 3,326 lines, 98 headings; section numbers have gaps (no
  21-25, no 30); §2A "Program shapes: what runs today" is 437 lines
  (367-804); §8 provider results is 600 lines; the opening 88 lines are
  routing, retirement notices and links to five design docs before any
  syntax. `:on-exhausted` is not explained for authors anywhere in the
  guide; the frontend spec explains it in terms of
  `repeat_until.on_exhausted.outputs` and "WCC/schema-2 route"
  (`docs/design/workflow_lisp_frontend_specification.md:1927-1940`).
  The useful "Minimal safe subset" is at §32 (3244), near the end.
  Jargon in the guide + catalog + library reference: "admitted" 41x,
  "bounded" 34x, "qualification" 18x, "copy-safe" 8x, "OPEN_NOT_WAIVED" 2x
  (guide:44 "evaluated F2 remains **OPEN_NOT_WAIVED**").
- **Catalog** (`workflows/README.md`): the "Which example should I copy?"
  table (53-61) is the best newcomer entry point in the repo, but every row
  carries status/qualification prose ("No paid-provider qualification
  follows", "requires separate owner authorization"). The improve example
  needs a `scripts/launch_experiment.py` that does not exist anywhere
  ("workspace-owned launcher required"), so the flagship std/improve example is
  not runnable as shipped; its dry-run passes silently anyway **[RAN]**.
- **Route readiness registry** (`docs/workflow_lisp_route_readiness_registry.json`,
  65 KB, 65 surfaces): 58 are `historical_negative` / `not_current_guidance`;
  6 are `preferred_current_guidance`. It is mostly a graveyard.
- **Volume**: `docs/plans` has 639 tracked `.md` (394 top-level, 959 tracked
  files in all), `docs/design` 100 files / 61,183 lines, `docs/reports` 125
  `.md`; `docs/` in all: 951 tracked `.md`, 409,088 lines. `specs/`: 14 files,
  9,405 lines; `specs/cli.md` 950 lines. CLI exposes 20 subcommands including
  `trial` ("target-2.25"), four `peer-*`, `provider-materialization-submit`.
- **Repo-root pollution** **[RAN]**: 290 `tmp*` + 130 `orc-observe-*`
  directories at the root (460 root entries in all); 372 of them are empty.
  They are **not tracked and not gitignored** (`git check-ignore` matches only
  `tmp/`), and they stay out of `git status` only because they are empty or hold
  ignored contents. `.superpowers/` is 2.2 GB (2 tracked files, rest ignored).
  Test/tooling tempdir leakage into cwd is the likely cause.

---

## 5. Live probes and friction log [RAN]

### 5a. Python guide recipe (docs/python_workflow_drafting_guide.md:28-36)

All 5 commands exit 0 (build ~8 s). Ran from the repo root for `build` only,
then in a scratch copy. `limit=3` → output `2` with 2 command steps;
`limit=0` → `0`, no steps; `--frozen` check ok; `report --format md` renders
nicely. Both `run`s print nothing. Recipe works as written.

### 5b. My own workflow

Spec: two commands (`measure` returns a record, `pad` returns Int), typed
record result, a bounded loop with a conditional. Files in
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/audit/probe-authoring/`
(`grow.orc`, `grow.attempt1.orc`, `commands.json`, `measure.py`, `pad.py`, `grow_py.py`).

**Attempt 1** — natural shape, `(continue (command-result pad ...))`:
```
grow.orc:18:32: [compiler_defect] the program passed typecheck, and elaboration failed on this form: this is a defect of the compiler, not of the program (TypeError: unsupported WCC elaboration node: CommandResultExpr)
kind: validation
form: workflow-lisp > defworkflow > run
```
Quality: honest and located; but it is a crash in
`orchestrator/workflow_lisp/wcc/elaborate.py:4072`, and it tells the user
nothing about how to proceed. The same pattern in a record field gives a good
refusal (`[effect_not_permitted] record field expressions must be pure; bind
effectful work in \`let*\` first`), and `(+ 1 (command-result ...))` compiles,
so this is an ANF gap specific to `continue`. std/improve.orc:7-9 documents
the same gap for `match` scrutinees and `loop-state :like`.

**Attempt 2** — let-bind then `(continue next)`: compiles (`"sites": 2`).
Total: **2 attempts**, ~10 minutes including reading. The Python port compiled
on attempt 1.

**Run**: `--input file=input.txt --input target=5` → exit 0, **silent**;
state `completed {'pads': 2, 'reached': True, 'words': 5}`; step names like
`workflow:grow::run / final / body / loop:pads[2] / else / next` are
readable for hand-written `.orc`.

**Failure + resume**: injected failure on `pad 1` → stderr line
`[command_exit_nonzero] evaluated command failed with exit code 1` (no step
name, no stderr excerpt; the Python traceback is only in
`effects/<sha>/attempt-1/stderr.txt`). `resume` → `[effect_rerun] ... next
attempts=[1]`; `pad 0` not rerun; completed correctly. Resume of a completed
run: exit 0, no-op.

**Closure drift**: edited `pad.py` after the failure, then resume:
```
[effect_input_diverged] workflow:grow::run / final / body / loop:pads[1] / else / next: effect input diverged (input parts changed: ['implementation_files']; dependency identities changed: False; previous sha256:4519..., current sha256:cdf2...)
```
Good diagnostic; no hint how to recover. Recovery took two tries:
`invalidate --step ...` → `unrecognized arguments`; `invalidate --help` says
"Full canonical evaluated effect identity", which turns out to be the
human-readable step path (found it by reading `memo.jsonl`).
`invalidate RUN "workflow:grow::run / final / body / loop:pads[1] / else / next"`
→ `{"record": "invalidated", ...}`; resume completed.
**Semantic trap**: invalidation reran `pad 0`, but the file had already been
padded once, so the result was `{'pads': 1, 'words': 5}`: one pad "added"
two words. Invalidation does not restore workspace state, and nothing warns about
a non-idempotent command.

**Prompt edit mid-run** (durable_host_input Lisp copy, suspended at the
approval): changed the diagnose prompt text, then `input answer` →
`input: current program differs from the run header` (exit 2), `resume` →
`[resume_program_changed] current program differs from the run header`. Any
source edit makes a retained run unusable; the message names neither the
change nor the recourse.

### 5c. Deliberate-mistake diagnostics (each compiled separately)

| Mistake | Diagnostic (verbatim) | Quality |
| --- | --- | --- |
| file not named after module | `[module_path_mismatch] module \`grow\` must live at \`mistakes/grow.orc\`` | Clear, but a surprising rule (filename = module) |
| field typo | `16:28: [record_field_unknown] unknown field \`word\`` | Good; no "did you mean `words`" or record name |
| `>=` on Int vs String | `16:24: [pure_expr_operand_type_mismatch] operator \`>=\` requires matching Int or Float operands` | Good |
| command missing from manifest | `15:28: [command_adapter_missing_contract] \`command-result\` \`measurex\` is missing command boundary metadata` | OK; "boundary metadata" means "add it to commands.json", which the message doesn't say |
| no `:max` | `12:14: [loop_recur_contract_invalid] \`loop/recur\` requires :max and :state` | Good |
| no `:returns` | `15:28: [frontend_parse_error] \`command-result\` requires :returns` | Good |
| record field omitted | `17:28: [record_field_missing] missing required field \`reached\` for record \`Outcome\`` | Excellent |
| wrong workflow return type | `11:5: [return_type_mismatch] workflow \`grow::run\` declared return type \`Measure\` but body returned a different type` | Weak: doesn't name the actual type |
| unbound name | `15:81: [name_unknown] unknown name \`fil\`` | Good |
| `continue` wrong state type | `19:34: [loop_recur_continue_type_mismatch] \`continue\` expected \`Int\` but got \`String\`` | Excellent |
| unbalanced paren | `1:1: [frontend_parse_error] unclosed list` | Poor: points at file start, not the open form |
| target 2.34 | `3:16: [workflow_execution_target_retired] target DSL 2.34 execution is retired; use a separately retained complete release/environment qualified for this source or run` | Accurate but jargon-heavy |
| no `:on-exhausted` | **compiles**; at run time `[loop_exhausted] bounded loop exhausted without a result`, run `failed` | Gap: README promises "a loop is bounded with a typed exhaustion outcome" |
| record passed in argv | compiles; command receives `'{"words": 1, "file": "in.txt"}'` | Plausible but undocumented coercion |
| using loop param in `:on-exhausted` | compiles (binder used before its lexical binding site) | Works; surprising scoping |

Overall diagnostic quality is high: stable codes, `file:line:col`, form path.
The weak spots are the compiler-defect crash, parse-error location, and
messages that state the rule without the remedy.

### 5d. REPL [RAN]

`repl grow.orc ...` with `:browse`, `:info Outcome` (fields + source
location), `:type (record Outcome ...)` → `type: Outcome effects: ()`. A pure
expression before `:attach` gives `[repl_not_attached] attach to an evaluated
run first`, although `:help` says "Any other nonempty line is one pure
Workflow Lisp expression". After `:attach RUN`: `:bindings` lists `file :
String, target : Int, final : Outcome`, `:result` prints the JSON, and
`final.words`, `(if final.reached "yes" "no")`, `(+ 2 3)` all evaluate.
`:where final` → `[repl_no_result_file] \`final\` was computed, not performed`.
Loop-internal bindings (`m`) are not inspectable. Useful and cheap.

### 5e. Other probes [RAN]

- `design_review_execute_agents` rewritten to `import design_review_execute
  :only (Execution draft-design ...)` compiles on the first try (`sites: 6`), so
  the 74-line example could be ~20 lines. The examples don't show reuse.
- durable_host_input recipe, both frontends: works (Python ~29 s end to end).
- `improve_experiment_proposal` and `plan_review_execute` dry-runs: exit 0,
  no output, nothing written to `--state-dir`.

---

## 6. Verdict

### Five best things
1. Typed prompt → typed result → checked field access (`defprompt ... -> T`, `draft.steps`): the core idea is right and pleasant.
2. Closed unions with exhaustive `match`, used for review outcomes and human replies (`HostReply`).
3. Resume that actually works: failed effect rerun only; closure-byte and program drift detected and refused.
4. Diagnostics: stable codes, precise locations, mostly actionable; the Python frontend's errors are equally good.
5. Inspectability: composed `prompt.txt` per attempt, `report --format md`, REPL `:attach` over a finished run, a small README example that is the real file.

### Five worst things
1. Docs are written for the maintainer, not the user: a 3,326-line guide that leads with routing and retirements, status jargon in example comments and catalog rows, 5/7 "standard forms" documented as unavailable, 950 doc `.md` files.
2. Sharp edges in the core loop: `(continue <effect>)` crashes the compiler; `:on-exhausted` optional in `.orc` (runtime failure) but mandatory in Python; odd binder scoping; effect positions that need let-binding by folklore (std/improve.orc:7-9).
3. Resume is all or nothing on source edits (`resume_program_changed` for a prompt-text change), and invalidation silently re-executes non-idempotent workspace effects.
4. Silent CLI: `run`, `run --dry-run` and `--verbose` dry-run print nothing on success; failures print the code without step or stderr.
5. Version/target fragmentation in the authoring surface: examples at 2.35/2.38/2.39/2.40, two `std/improve` modules with different signatures, effects/lowering rules that change at 2.39, Python feature subset missing map/ProcRef/agents. Plus repo hygiene: 420 untracked, unignored `tmp*`/`orc-observe-*` dirs at the root.

### Highest value-to-cost changes
1. **Fix the `continue`/`match`-scrutinee/`:like` elaboration gap** by let-binding effectful subexpressions in the frontend (the Python emitter already does this). Until then, refuse with a remedy message instead of `compiler_defect`. Also make missing `:on-exhausted` a compile error, as in Python.
2. **Make the CLI talk**: one-line success summary on `run`/`resume`/`--dry-run` (run id, status, output, sites), and on failure the step identity, the stderr tail, and the exact `invalidate`/`resume` command to run next. Make `resume_program_changed` name what changed.
3. **A 150-line "first workflow" tutorial** at the top of the guide: one provider-free `.orc` (like the probe in 5b) with compile → run → fail → resume → REPL, then one stub-provider review loop. Move routing/retirement/status prose out of the guide, the example comments and the catalog rows into the capability matrix.
4. **Deduplicate the examples through imports** (agents variant imports the baseline's prompts; best_of_n `select-only` reuses one judge proc) and add a multi-line prompt literal or a prompt-file convention, so long prompts aren't 1,000-char lines.
5. **Repo hygiene**: add `tmp*/` and `orc-observe-*/` to `.gitignore`, fix the tempdir leak at its source (tests creating dirs under cwd), and hide maintainer subcommands (`trial`, `peer-*`, `provider-materialization-*`) from top-level `--help`.

Also worth deciding: whether Python becomes the documented primary surface
(it already avoids attempt-1 failures). That would mean closing the
map/ProcRef/agent gap and emitting readable binding names.
