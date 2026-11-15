# Phase 6 Readiness R3: Mechanical Mutants Of The Seeds: Implementation Plan

**Status: Plan, proposed 2026-11-13; revised 2026-11-13 after an independent review (accept after
fixes: no blocker, 8 majors, 12 minors) and the coordinator's rulings on it, recorded
[below](#rulings).** It plans readiness item R3 of
[Phase 6](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-6-program-evolution)
("Mutants never crash the compiler") and the zero-spend check of H-E2's reach named in the same
section. It is a plan, not a contract and not copy-safe guidance. Behavior is owned by `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md). No task makes or authorizes
a provider or model call; every run in it uses stand-ins on a closed `PATH`. Probed on `main` at
`b399076b`, re-measured by the review on `8a61b143`; revised against `main` at `a9f9e410`.

**Goal:** a generator of a few hundred mechanical mutants of the seeds, deterministic from a seed
number; a check that each mutant compiles or is refused with a diagnostic code, with every crash
reported under the defect backlog's key and never silently accepted; and, per mutation operator,
how much of a completed run `resume` would keep under the mutant.

**Approach:** operators are generators of character-range edits found by reading the source with
the package's reader and spliced into the text, so no printer is needed and comments and layout
survive. One script compiles every mutant in process, asks `plan_resume` for the plan under each
compiling mutant on a stand-in run, and writes one readout. What this makes harder is listed
[below](#what-this-makes-harder).

**Not in this plan:** a search driver, selection, fitness, crossover between programs; fixing any
defect the mutants find (the
[defect backlog plan](2026-11-13-compiler-and-runtime-defect-backlog-plan.md) owns fixes);
a change to `resume`; the `conversation` operator (deferred, Task T4); mutants made of two or
more mutations (an operator accepts any source, a mutant included, so a search composes by
applying them again).

**R3's gate.** The roadmap's gate is that no mutant ends in `compiler_defect`. It is unmet while
any mutant crashes: the command of Task T5 exits 1 until the crash of probe P8 is fixed, and this
plan does not declare the gate met before that.

## Probes That Shaped The Plan

On `main` at `b399076b` unless a row says otherwise, with `experiments/thread_m/no_provider` first
on `PATH`, `PYTHONPATH` set to the tree under test, scratch under `/tmp/r3p` (deleted). Seeds were
exported with `git archive BRANCH PATH | tar -x -C DIR`. "Compile" is
`python -m orchestrator compile P.orc --entry-workflow P::run --source-root . --provider-externs-file providers.json --command-boundaries-file commands.json`
run in the seed's directory. The stand-in run uses the answers of the spike branch's
`experiments/long_horizon_seed/demo.py` and the fake `claude` of `tests/agent_session_shims.py` on
`closed_path`, the sources copied beside the workspace so that an edit never touches a tracked
file. The independent review re-ran P1, P2, P5 (two samples of 50 files), P6, P8's crash, P10 and
every example of the operators' "before and after" list on `8a61b143`; all hold.

| # | Question | Command or method | Outcome |
| --- | --- | --- | --- |
| P1 | Do the long-horizon seeds compile on `main`? | Compile `milestones`, `staged`, `roles` and the two programs under `variants/` from `spike/long-horizon-seed` (`aa7ae4a0`) | All five build (exit 0; 8, 6 and 12 sites for the three seeds). No construct fails. The same digests on `feat/coherence-e1` (`588faf29`) |
| P2 | Do they run? | The seed's `demo.py`, scenario `clean`, for each | All end in `DONE`: 11, 6 and 17 committed steps; 8, 5 and 8 provider calls |
| P3 | Do the seed-set programs compile on `main`? | Compile the four programs of `experiments/seed_set/programs/` from `feat/seed-set-prep` (`5449db80`) | All four build, on `main` and on E1. `plan_implement_review.orc`, the seed the seed-set plan names, does not exist on any branch |
| P4 | What fails on `main`? | Compile the seeds as rewritten in the staged-authoring idiom (`spike/authoring-revisions`, `experiments/authoring_revisions/seeds/`), then one module per construct | Refused, on `main` and on E1 alike: `Prompt[T]` (`generic_union_not_generic`), a provider as an argument (`provider_result_provider_invalid`), `(list :of String)` (`keyword_argument_invalid`), `list/take` and `list/all` (`pure_expr_operator_unsupported`), a timeout as a name (`provider_result_timeout_literal_required`). All wait for the staged-authoring revisions; none waits for E1. An input with a literal default builds today |
| P5 | Is there a reader and a printer that round-trip a `.orc` file? | `orchestrator.workflow_lisp.reader.read_sexpr_text`; a search of `orchestrator/` for a printer; for each of the 644 tracked and seed `.orc` files, re-read the text slice `text[span.start.offset:span.end.offset]` of every node | A reader with character-offset spans; no printer. The slice of every one of 91,844 nodes re-reads to the same form in 641 files; 3 files are unreadable on purpose. Offsets index characters, also after non-ASCII text (a synthetic string: no tracked `.orc` file holds non-ASCII text). So a mutation is a splice of the decoded text at a node's span |
| P6 | Does the compiler check a model or an effort? | Compile a call with `:model "claude-fable-5-2" :effort "bogus"` | Builds; only a non-string effort is refused. The compiler is no backstop: the operators' value sets must be closed and pinned by a test |
| P7 | What is the compile entry and the crash key? | `prepare_closed_program_bundle(FrontendBuildRequest(...))` in process; a reading of the backlog's Task T0 on `test/defect-backlog-t0` (`a8b08d98`, in review) | In memory, nothing written under the work directory. T0's module computes the key (exception class and a function under `orchestrator/` from the cause's traceback) and classifies a build; its `KNOWN` stores the key for every crash row. The command line cannot give the function, so the check compiles in process, as T0 does. Measured by the review: 0.02 s for a tiny program, 0.3 s `staged`, 0.6 s `milestones` and `roles` when they build, 0.06 s when refused |
| P8 | What do mechanical mutants do today? | A throwaway prototype of the operators (without `conversation`): 427 mutants of the three long-horizon seeds and 350 of the four seed-set programs (number 1), then 750 `graft` mutants (number 7) | Every mutant builds or is refused with a code, except one crash key, hit four times, by `graft` mutants only, on three programs (`milestones`, `staged`, `retry_until_check`): `TypeError workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump`, cause `unsupported WCC control rewrite node: WccLoopDone`. `effort`, `model` and `rounds` mutants all build, each with its own digest; `graft` builds 5 percent of the time (38 of 750). These numbers describe that sample, not the compiler: the review found a second uncaught exception by hand (below) that no mutant reached |
| P9 | Does E1 change a mutant's outcome? | The same 750 `graft` mutants against an export of `feat/coherence-e1` (`588faf29`; the branch has moved since) | No outcome differs |
| P10 | What does `resume` keep under a hand-made edit of each dimension? | A completed stand-in run, one edit, `orchestrator resume RUN_ID` (no token, so read-only) and `plan_resume(run_root, workspace)` in process, the source restored | Table below, as re-measured by the review. The run's files and the fake's request log were byte-identical before and after every row |
| P11 | Does the stand-in run need a test module's driver? | `python -m orchestrator run ...` with the fake `claude` on `closed_path`, for `milestones` and `roles` (`clean`) and `milestones` (`review-rejects-once`) | No: exit 0 and `DONE` for all three (8, 8 and 10 calls; 4 to 5 s each on a quiet machine, 6 to 19 s under load), the Agent Sessions seed included; no tmux server is left |

**The crash of P8.** Smallest program (review):
`(loop/recur ((s 0)) :max 2 :on-exhausted 0 (let* ((x (done 1))) x))` as the body of
`run () -> Int`. The same key for `continue` as the binding's value, for
`(let* ((x (done 1))) (done 2))`, for `(let* ((x (if true (done 1) (done 2)))) x)` and for the
same inside an operand. Sibling positions are refused with a code today. It is not in the
backlog's table and E1 does not close it. The right outcome is a refusal (frontend specification
§13.1 gives `done` and `continue` only as what the loop body returns); the code is the fix's
choice. The roadmap lists it in the tenth batch of its defect list.

**A second crash, found by hand by the review, outside every sample.**
`(done (list/length (list (done 1))))` in a loop body, and the same with `continue`: an uncaught
`AttributeError` in `workflow_lisp/typecheck_structural_values.py:typecheck_structural_value_expr`.
`graft` as defined cannot reach it on these seeds (no list item there is a list form).

P10, `milestones`, scenario `clean`: 11 committed steps, 8 provider calls.

| Edit | `resume` | Kept (steps) | Kept (provider calls) |
| --- | --- | --- | --- |
| Planner: effort literal at its three calls; model literal the same | a plan | 0 of 11 | 0 of 8 |
| Coder: effort literal; model literal | a plan | 3 of 11 | 3 of 8 |
| Reviewer: effort literal at its two calls; model literal | a plan | 5 of 11 | 4 of 8 |
| Reviewer: a literal equal to the bound value | a plan | 5 of 11 | 4 of 8 |
| Coder and reviewer effort together | a plan | 3 of 11 | 3 of 8 |
| Effort or model through `inputs.json` | `resume_inputs_changed`, no plan | none | none |
| An input's default changed (the run used the default) | `resume_program_changed`, "no plan can be accepted: `resume_inputs_changed`" | none | none |
| A loop's `:max`, either loop, up or down; the map's `:max` 8 to 4 | a plan, no cut | 11 of 11 | 8 of 8 |
| The map's `:max` 8 to 1 (two items had run) | no plan: `list_map_effect_cap_exceeded` | none | none |
| The coder's timeout | a plan | 3 of 11 | 3 of 8 |
| Prompt wording: `guides`, `specify`, `plan`, `work`, `review` | a plan | 0, 1, 2, 3, 5 of 11 | 0, 1, 2, 3, 4 of 8 |
| Drop the unused first binding; swap the first two | a plan | 0 of 11 | 0 of 8 |
| The planner's three calls continue one session | a plan | 0 of 11 | 0 of 8 |
| Comment only | exit 0, the run's result | all | all |

Other runs:

| Run | Edit | Kept |
| --- | --- | --- |
| `milestones`, `review-rejects-once` (14 steps) | milestone loop `:max` 2 to 1 | 9 of 14 (the second attempt and what follows are cancelled) |
| the same | milestone loop `:max` 2 to 3 | 14 of 14 |
| the same | reviewer effort literal | 5 of 14 |
| `staged`, `clean` (6 steps) | planner, coder, reviewer effort literal | 0, 3, 5 of 6 |
| `roles`, `clean` (17 steps) | effort at an `agent` form, a prompt, the coder's timeout, continued to fresh | no plan: `invalidate_coordinator_committed` |
| `roles`, `clean` | a loop's `:max` | 17 of 17 |

**What the reuse probe shows, and what it does not.** On these seeds and scenarios `resume` keeps
the steps before the first changed call in journal order, so an edit to a role that runs first
keeps nothing. That follows from two things together: `resume` cancels the journal suffix from the
first step whose declaration changed, and a per-role edit changes every call of the role, the
first of which, for the planner, is the run's first step. It is a property of the journal-suffix
cut and of where roles run in these seeds, not of search in general; the checkpoint controller of
readiness item R1 is where it can change. A share of 1 means the recorded run does not exercise
the edit (the `clean` run never reaches a loop bound), not that the mutant is cheap to evaluate.
The share depends on the seed and the scenario (a reviewer edit keeps 5 of 11 on `milestones`,
5 of 6 on `staged`, 5 of 14 after a rejected review), and steps are not cost (5 of 11 steps is 4
of 8 provider calls). For the first space, by arithmetic on the measured rows: of the 26 other
points around a parent, 18 change the planner (nothing kept), 6 change the coder and not the
planner (3 of 11), 2 change the reviewer only (5 of 11). `plan_resume` in process gave the command
line's counts in all 21 cases with a plan and the same code for every coded refusal; an uncoded
failure (a moved inputs file, an entry parameter that lost its default) arrives as a bare
exception where the command line prints `resume_preflight_failed`.

**Prior art.** The October search (`experiments/orc_structural_search/`) has no mechanical
mutator: its mutators are model sessions that rewrite a file (I1) or one site (I2). What is reused
from it is its rule for text (decode UTF-8, normalise line ends, index characters:
`sites.py:_forms_and_text`) and nothing else, because its code is closed and its tests are opt-in.
`experiments/orc_gp_example/` mutates a grammar genotype and renders a program from it; it cannot
mutate a seed's source, and its model list holds models above the ceiling. Neither is imported.

## Global Constraints

- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`; no
  `git stash`. One worktree; `PYTHONPATH` set to it; `experiments/thread_m/no_provider` first on
  `PATH`; `mkdir -m 700` for any basetemp.
- No provider or model call. The only process `check.py` launches is the seed's own stand-in
  run, with the fake `claude` on `closed_path(...)`. No mutant is ever run: `check.py` holds no
  call of `run` for a mutant and no call of `resume`, with or without `--accept-changes`.
- Operators live under `experiments/`, never under `orchestrator/`: the
  [boundary invariants](../design/workflow_lisp_program_search_boundaries.md) (invariant 3) keep
  mutation out of the package. Every mutant goes through the ordinary compile (invariant 1).
- Tests assert outcomes, diagnostic codes, digests and parsed forms, never prompt or message
  text. Test sources declare `(:target-dsl "2.40")`. A new test fails first for its stated
  reason. Function complexity at most 12.
- **Closed value sets, in one place.** `experiments/mutants/operators.py` is the only module that
  holds them: `MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")` and
  `EFFORTS = ("low", "medium", "high", "xhigh", "max")`, with no override from the environment, a
  file or the command line. A caller may narrow them (the first space is `low`, `medium`,
  `high`) and can never widen them. The test module repeats both tuples as literals, so adding a
  Fable model, a model above the Sonnet ceiling or an undeclared effort fails a test
  (`AGENTS.md`, experiment rules).
- **Frozen surfaces.** No operator changes the module name, imports, exports, the target, a type
  declaration, a prompt's `:fills` or return type, the entry workflow's parameter list or the
  manifests; `common.orc` is never a mutant
  ([driver design](../design/orc_structural_search_driver.md#edit-validation-and-transactions)).
  No operator but `graft` adds a line, so a 49-line seed stays under the 50-line limit.
- **Gate:** the narrow run, `pytest --collect-only` on the new module, then
  `pytest -q -n 16 --dist=worksteal --sample 10`. The whole suite before the merge is the
  coordinator's.

## Files

Nothing in `orchestrator/` changes.

| File | New or edited | Responsible for |
| --- | --- | --- |
| `experiments/mutants/operators.py` | New | The operators, the closed sets and the sample. Depends on `orchestrator.workflow_lisp.reader` and `sexpr` only. Holds no state, reads no file |
| `experiments/mutants/check.py` | New | Measuring mutants: the compile outcome, the reuse figures, the readout, and the one command. Depends on `prepare_closed_program_bundle`, on `plan_resume` (the documented library entry: [lifecycle guide](../runtime_execution_lifecycle.md)), and on two test-support modules that are not test modules: `tests/workflow_lisp_closed_program_helpers.py` (`crash_signature`, `build_outcome`) and `tests/agent_session_shims.py` (`FAKE_CLAUDE`, `closed_path`). It imports no `tests/test_*` module and reads no known list |
| `tests/experiments/test_mutants.py` | New | The operators' tests and the default-suite sample, on fixture sources written in the module. The only reader of the backlog's `KNOWN` |
| `experiments/mutants/readout.json` | New, written by the command | The last readout: the sample it was drawn with, the outcomes per operator, one record per crash key, the reuse figures |
| `tests/test_workflow_lisp_defect_backlog.py` | Edited (T2) | Two rows: P8's family and the review's second crash |
| The defect backlog plan | Edited (T2, T5) | The two rows in its table; a ledger row for each readout |

`tests` is a package and imports from the repository root, so `check.py` can import the two
support modules as the suite does. The move of `_signature` and `_build_outcome` into
`tests/workflow_lisp_closed_program_helpers.py` under the names `crash_signature` and
`build_outcome` is the backlog's Task T0 fix round, not a task here.

Interfaces:

```python
# operators.py
MODELS: tuple[str, ...]; EFFORTS: tuple[str, ...]

@dataclass(frozen=True)
class Mutation:
    operator: str                               # a key of OPERATORS
    params: str                                 # e.g. "reviewer=low", "loop1=3", "9<-18"
    edits: tuple[tuple[int, int, str], ...]     # disjoint (start, end, replacement) character ranges

def effort(text: str, levels: Sequence[str] = EFFORTS) -> Iterator[Mutation]   # ValueError outside EFFORTS
def model(text: str, models: Sequence[str] = MODELS) -> Iterator[Mutation]     # ValueError outside MODELS
def replace_prompt(text: str, name: str, raw: str) -> Mutation                 # the primitive a proposer uses
OPERATORS: dict[str, Callable[[str], Iterator[Mutation]]]   # every mutation of one source, in document order
def apply(text: str, mutation: Mutation) -> str             # splice, right to left; ValueError on overlap
def sample(sources: Mapping[str, str], cap: int, number: int,
           operators: Sequence[str] = tuple(OPERATORS)) -> list[tuple[str, Mutation]]   # (program, mutation)

# check.py
def outcome(work: Path, program: str) -> tuple               # ("compiles", digest) | ("refused", *codes)
                                                             # | ("crash" or "traceback", class, where)
def compile_report(seed_dir: Path, programs: Sequence[str], cap: int, number: int,
                   operators: Sequence[str] = tuple(OPERATORS)) -> dict
def plan_outcome(run_root: Path, workspace: Path) -> tuple   # ("plan", kept, cancelled, calls_cancelled)
                                                             # | ("no_plan", code)
def reuse_report(seed_dir: Path, program: str, standin: Mapping, scenario: str,
                 mutants: Sequence[tuple[str, Mutation]]) -> dict
```

Text is `path.read_bytes().decode("utf-8")` with `\r\n` and `\r` turned into `\n`; spans index that
text. `sample` takes, for each program in name order and each operator in `OPERATORS` order, all
its mutations when there are at most `cap`; else it draws one `random()` per mutation from
`random.Random(f"{number}/{program}/{operator}")` and keeps the `cap` mutations with the smallest
draws, in document order. Only `random()` is used, the one method whose sequence the Python
documentation fixes across versions; the readout records the Python version all the same. A
mutant's name is `program/operator/params`; it reproduces the mutant without the number.

## Operators

Shared terms. A **call form** is a list headed `provider-result` or `agent`; its **role** is its
first operand when that is a symbol `providers.R` (role `R`). The **operand of** `:k` is the item
after the keyword `:k` among a form's own items. Forms are numbered from zero, in order of start
offset. An operator yields no mutation whose replacement equals the text it replaces. Examples
are from `milestones.orc`.

| Operator | Sites and edit | Parameters | Must not produce |
| --- | --- | --- | --- |
| `effort` | The operand of `:effort` in every call form of one role, all of them in one mutation, replaced by a string literal | role; level in `levels` | A level outside `EFFORTS`; an edit of some of a role's sites; an inserted `:effort`; an edit of an input or its default |
| `model` | The same for `:model` | role; model in `models` | A model outside `MODELS` |
| `rounds` | The operand of `:max` of one `loop/recur`, when an integer literal | loop number; n in 1 to 4 | 0, a value above 4, a `list/map-effect` cap, a non-literal bound |
| `drop_step` | One binding pair of one `let*` inside a `defworkflow` or `defproc`, deleted | `let*` number; binding number | Anything but one whole pair |
| `replace_prompt` (primitive) and `prompt` (its generator) | The body of one `defprompt` (its last item, a string), as raw source text between the quotes, so escapes are never re-encoded. `replace_prompt` puts the given raw text there. The generator calls it twice over: `drop k` gives the pieces of the body split at `". "` without piece k, joined by `". "`; `append` gives the body followed by the constant `" Check the result before you report."` (no brace, quote or backslash) | prompt name; raw text, or `drop k`, or `append` | An empty body; an edit of two prompts; a change to `:fills`; raw text with an unescaped quote or a line end (`ValueError`) |
| `graft` | One expression form replaced by the source text of another of the same module. An expression form is a list inside the body of a `defworkflow` or `defproc` whose head is in the constant `EXPRESSION_HEADS` (`provider-result command-result call loop/recur let* if match list/map-effect list/map done continue variant record loop-state agent not and or = + list/append list/length`) and which is not in a name position: not a binding pair of a `let*` or of a `loop/recur` binder list, not the parameter list of `fn`, not the pattern of a `match` arm | target number; donor number | A donor from another file; a donor that contains the target; a replacement equal to the target; a pair or a parameter list named like a head taken for an expression |

Before and after:

- `effort`, `reviewer=low`: `(provider-result providers.reviewer :model reviewer :effort effort :timeout-sec 1200 ...)`
  becomes `(provider-result providers.reviewer :model reviewer :effort "low" :timeout-sec 1200 ...)`
  at both reviewer calls. Builds; a new digest.
- `rounds`, `loop0=3`: `(loop/recur :max 2 :state ...` becomes `(loop/recur :max 3 :state ...`.
- `drop_step`, `let1.0`: the binding `(ready (provider-result providers.planner ... (guides ...)))`
  disappears; refused `name_unknown` (every later step reads `ready.guide`; it built while nothing read
  `ready`, before the seeds' second fix round). `let1.1` (`spec`) is refused `name_unknown`.
- `prompt`, `work.drop2` removes the sentence that holds `{milestone}`: refused
  `prompt_placeholder_missing`. `work.append` builds.
- `graft` on `staged`, target the coder's call, donor the acceptance arm: the coder's
  `provider-result` becomes `(done (variant Outcome DONE :summary "accepted"))`: today's crash.

### Coverage Of The Declared Dimensions

The dimensions are those of the [seed-set plan](2026-11-11-seed-set-calibration-plan.md), "Search
dimensions around one seed". "As is" means a search uses the operator unchanged; "check only"
means it exists to feed the compile check.

| Declared dimension | Operator | Seeds that can express it | Not reachable on today's seeds |
| --- | --- | --- | --- |
| Effort per role (first space: three levels) | `effort`, as is | All seven programs (one role in `direct`, `retry_until_check` and `implement_check_repair`, two in `implement_review_revise`, three in the long-horizon seeds) | — |
| Model per role | `model`, as is | The same | — |
| Revision rounds | `rounds`, as is | Programs with a `loop/recur`: the three long-horizon seeds, `implement_check_repair`, `retry_until_check` | `direct` and `implement_review_revise` have no loop |
| Planner absent | None | None | Dropping `ready` is refused `name_unknown`, by design since the seeds' second fix round (every later step reads the guide path it reports), so "setup absent" is not reachable by `drop_step`; `spec` and `plan` are read too (`name_unknown`). It needs a seed where the plan is optional (`plan_implement_review.orc`, which does not exist); built when that dimension is searched |
| Reviewer absent | None that can be relied on | One `graft` pair per site: it builds in `staged` and in `milestones::run`, and is refused `name_unknown` in `milestones::milestone` | A cap of 100 among about 1,500 pairs seldom draws that pair; built when that dimension is searched |
| Conversation (fresh or continued) | None: T4 is deferred | — | The hand edit of P10 gives its reuse (0 of 11; no plan on `roles`) |
| Prompt wording | `replace_prompt`, as is, with text from a proposer; `prompt` (`drop k`, `append`) is check only | All | The mechanical generator is not what a search would use: the seed-set plan says wording "is searched by proposal" |
| A step absent; a subtree moved (not declared values) | `drop_step`, `graft`: check only | All | `graft` stands for "the program's structure also mutates"; it is the only operator that found a crash |

## The First Space Is Programs, Not Bindings

Coordinator's ruling (M8 of the review), recorded here because other documents still say
otherwise. In the first search space a point is a program. Effort per role is a string literal at
each of that role's call sites, and a mutation rewrites it; the 27 points are 27 programs with 27
digests, named `program/effort/role=level` and joined by name. Inputs cannot vary under `resume`
(P10: a changed input, or a changed default that takes effect, gets no plan), so a point that is
a binding of one program shares nothing with its neighbours.

Sentences that must change before the seed is frozen (the coordinator edits them; this plan
edits none):

| Document | Sentence |
| --- | --- |
| [Seed-set plan](2026-11-11-seed-set-calibration-plan.md), "Search dimensions around one seed" | "The dimensions a later search may vary, each a binding of that program and not a new program:" |
| The same, ledger row of 2026-11-13 ("mutate model and effort per role") | "Consequences: a seed's entry takes a model and an effort per role (the long-horizon seed has one shared effort input today);" |
| [Long-horizon plan](2026-11-13-long-horizon-task-family-and-seed-plan.md), step 8 | "Required: it compiles at the current target under 50 lines; an effort input per role (owner, 2026-11-13);" |
| [Roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md), Lane D item 6 | "model and effort per role are already one-token edits today through inputs with literal defaults, so the first search space needs none of this" (true of a fresh run; under `resume` such an edit gets no plan) |
| [Staged-authoring design](../design/workflow_lisp_staged_workflow_authoring.md), the table of edits | "Model per role \| One token: the literal default of that role's model input" and "Effort per role \| One token, once the seed has an effort input per role (two more signature lines; possible today)" |
| The same, after the table | "Model and effort were already one-token edits. The first space the owner selected (one model, an effort per role) is three such tokens and needs nothing from this design;" |
| The seed, `milestones.orc` and its two neighbours on `spike/long-horizon-seed` | The parameter `(effort String)` of `run` and of `milestone`, the operand `:effort effort` at every call form, the argument `:effort effort` of `(call milestone ...)`, and `"effort": "medium"` in `demo.py`'s inputs: a literal `:effort "medium"` at each call form replaces them |

## Tasks

Order: T1; then T2, T3 and T5 once the backlog's T0 is on `main`; T6 and T7 when what they wait
for exists.

| Task | Hours | Waits for |
| --- | ---: | --- |
| T1 Operators and the sample | 7 | Nothing |
| T2 Compile check, crash records, command | 4 | T1; the backlog's T0 merged with `crash_signature` and `build_outcome` in the helper |
| T3 Reuse figures | 5 | T2 |
| T4 The `conversation` operator | deferred (3) | A decision to search that dimension |
| T5 First readout and hand-off | 2 | T3 |
| T6 The frozen seeds in the suite | 2 | The seed's merge to `main` (roadmap Phase 5b, step 8) |
| T7 Sites of the role idiom | 3 | Only if a seed in the staged-authoring spelling replaces the frozen one |

Nothing waits for E1 (P1, P9). After E1 merges the command of T5 is run again, which is a new
readout.

### Task T1: Operators and the sample (7 h)

Files: `experiments/mutants/operators.py`, `tests/experiments/test_mutants.py`.

- [ ] The fixture `SEED` in the test module: one module at target 2.40, under 25 lines, with
      its own record and union types, three prompts, an entry
      `run ((task String) (repo String) (planner String) (coder String) (reviewer String))`,
      one planner call, then a `loop/recur :max 2` holding a coder call, a `command-result` and a
      `match` on a reviewer call. It is spelled as ruling M8 has the frozen seed: the entry has no
      effort parameter, each of the three calls holds the literal `:effort "medium"`, and model per
      role is an entry input (`:model planner`). It is the only source the default suite mutates
      until T6.
- [ ] `Mutation`, `apply`, `effort`, `model`, `rounds`, `drop_step`, `replace_prompt`, `prompt`,
      `graft`, `OPERATORS` and `sample`, as defined above.
- Tests, each failing first because `experiments.mutants.operators` or the operator's key in
  `OPERATORS` does not exist:
  - `test_the_closed_sets_are_the_declared_ones`: `operators.MODELS` and `operators.EFFORTS`
    equal the two tuples written out in the test.
  - `test_effort_and_model_write_only_declared_literals`: for every mutation of `effort` and of
    `model`, every replacement string in `Mutation.edits` is the quoted form of a member of the
    tuple written out in the test. No "or the seed" clause.
  - `test_a_value_outside_the_sets_is_refused`: `effort(SEED, levels=("turbo",))` and
    `model(SEED, models=("claude-fable-5-2",))` raise `ValueError`;
    `effort(SEED, levels=("low", "medium", "high"))` yields 6 mutations: 3 roles times 3 levels
    is 9, and the 3 that would write `"medium"` where the fixture already holds it are not
    mutations (an operator yields no mutation whose replacement equals the text it replaces, so
    the parent is never its own neighbour). On the spike's spelling, where the operand is the
    name `effort`, the same call yields 9.
  - `test_no_other_operator_introduces_a_model_or_effort`: for `rounds`, `drop_step`, `prompt`
    and `graft`, the string literals in `:model` and `:effort` position of every mutant occur in
    the seed.
  - `test_each_operator_yields_mutations_of_the_fixture`: the count per operator is the one the
    fixture fixes: `effort` 12 (3 roles times 5 levels, less the 3 identities), `model` 6 (3
    roles times 2 models; the operands are names, so none is an identity), `rounds` 3,
    `drop_step` 3, `prompt` 12, `graft` 143 (14 expression forms: 196 pairs less the 53 whose
    donor is or contains the target).
  - `test_effort_edits_every_call_of_one_role_and_nothing_else`: re-read the mutant; the operand
    of `:effort` is the string `low` at each `providers.reviewer` form and unchanged elsewhere;
    every other top-level form is equal to the seed's.
  - `test_frozen_surfaces_survive`: module name, exports, target, type declarations, each
    prompt's `:fills` and the entry's parameter list are equal forms in every mutant.
  - `test_only_graft_adds_a_line`.
  - `test_graft_skips_name_positions`: a source with a binding named `record` and an `fn`
    parameter named `call` yields no `graft` whose target or donor is that pair or that list.
  - `test_prompt_edit_keeps_escapes`: every `prompt` mutant re-reads; `replace_prompt` with the
    body's own raw text raises `ValueError` (an identity), and so does a raw text with a bare
    quote.
  - `test_apply_refuses_overlapping_edits`.
  - `test_sample_is_deterministic_and_capped`: equal lists for one number, different for
    another, at most `cap` per program and operator, names unique, document order kept.
- Run: `pytest -q -n 8 tests/experiments/test_mutants.py` (expected: all pass; under 5 s).
- Reviewer: that sites are found by form and keyword, never by line or offset constants.

### Task T2: Compile check, crash records, command (4 h; after the backlog's T0)

Files: `experiments/mutants/check.py`, `tests/experiments/test_mutants.py`,
`tests/test_workflow_lisp_defect_backlog.py`, the defect backlog plan.

- [ ] `outcome`: copy the seed directory to a work directory once, write the mutant over its
      program there, and classify `prepare_closed_program_bundle` (the seed directory is never
      written) with `build_outcome` of `tests/workflow_lisp_closed_program_helpers.py`; a build
      gives `("compiles", digest)`, the digest kept by the closure handed to `build_outcome`.
      No second classifier and no second `except` is written.
- [ ] **The key** is `crash_signature`'s pair as T0 defines it after its review (the exception
      class and a function under `orchestrator/` that is not a raising helper), without the
      kind, so the backlog's TP1 (a traceback becomes a crash) moves no key. A key is a
      location, not a defect: three of T0's rows share one key, and the closed-program
      checker's single raising method is the key of every checked-form violation. So a crash is
      never accepted because its key is known.
- [ ] `compile_report`: the sample (cap, number, programs, operators, Python version); per
      operator the counts of `compiles`, each refusal code, each key and mutants of 50 lines or
      more; `distinct_digests`, `equal_to_seed`; and `crashes`, one record per key:
      `{"key": [class, where], "kinds": [...], "mutants": n, "operators": [...], "pairs": [[operator, program], ...], "cause": first line of the cause's message, "smallest": {"name": ..., "source": the shortest crashing mutant's whole text}}`.
- [ ] `python -m experiments.mutants.check SEED_DIR --programs a,b,c [--operators x,y] [--cap 100] [--number 0] [--out readout.json]`:
      prints the table and every crash record, writes the readout, exits 1 when any mutant ends
      in a crash or a traceback, else 0. A seed that does not build itself is a usage error
      (exit 2). The command reads no known list.
- [ ] Two rows in T0's module (`ROWS`, `KNOWN`, `KNOWN_AT_T0`) and in the backlog's table, each
      with a ledger row there, unless T0's fix round has entered them: P8's family (`done` or
      `continue` as a `let*` binding's value in a loop body, with the nested forms above; wanted
      outcome `None` until the fix chooses a refusal code) and the review's second crash
      (`(done (list/length (list (done 1))))`; found by hand, not a mutant's hit).
- Tests, failing first because `check.outcome` does not exist:
  - `test_outcome_kinds`: a `rounds` mutant gives `compiles` with a digest other than the
    seed's; `drop_step` of a binding that is read gives `("refused", "name_unknown")`; a
    `prompt` drop of a sentence holding a placeholder gives
    `("refused", "prompt_placeholder_missing")`.
  - `test_an_escaped_exception_is_a_crash_record_and_exit_1`: with `build_closed_program` in
    `orchestrator.workflow_lisp.closed.artifact` replaced by a function that raises
    `RuntimeError` (probed: the exception escapes with a package frame), `compile_report` on the
    fixture with `operators=("rounds",)` has one crash record whose class is `RuntimeError`,
    whose `mutants` is the number of `rounds` mutants, whose `pairs` is `[["rounds", "fixture"]]`
    and whose `smallest` source re-reads; `main([...])` called in process returns 1. This test
    does not depend on a live defect and stays when P8 is fixed.
  - `test_a_crashing_mutant_is_reported_under_the_backlog_key`: `CRASH_SEED` is a one-program
    directory whose loop body is `(let* ((x (+ state.i 1))) (done state.i))`; the `graft` of the
    binding's value by the `done` form is P8's crash (probed). Its report has one record, whose
    key is the new row's in T0's `KNOWN`. It is deleted with that row.
  - `test_the_fixture_sample_has_no_crash`: `compile_report` on the fixture at `cap` 3, number
    0, has no crash record, at least one mutant per operator, and counts that add up. The
    fixture is in no readout, so a crash on it is unrecorded by definition and fails. If the
    fixed sample does crash when this task is done, the implementer stops and reports; the
    sample is not tuned.
  - `test_the_known_list_has_the_shape_this_module_reads`: every value of T0's `KNOWN` starts
    with a kind this module knows, so a change of shape cannot empty the set of known keys
    unnoticed.
  - `test_command_exits_0_without_a_crash`: the command on the fixture with `--operators rounds`.
- Run: the module (expected: about 20 s: at most 18 fixture mutants and two command runs).
- Reviewer: that no test can pass by producing no mutants; that nothing is written under the
  seed directory; that `check.py` imports no `tests/test_*` module.

### Task T3: Reuse figures (5 h)

Files: `check.py`, the test module.

- [ ] `reuse_report(seed_dir, program, standin, scenario, mutants)`. `standin` is
      `{"inputs": {...}, "files": {...}, "answers": {program: {scenario: [...]}}}`: the run's
      inputs (the check sets `repo` to the workspace), the workspace's files (the token
      `{python}` in a file's text becomes `sys.executable` when the world is built, so no
      interpreter path is stored), and the fake `claude`'s answers in call order. It builds a
      world in a temporary directory removed in `finally` (`src/` a copy of the seed directory,
      `repo/` the workspace, `bin/claude` the fake), runs the seed once to completion with
      `python -m orchestrator run` on `closed_path` (P11), then for each mutant that compiles
      writes it to `src/`, calls `plan_outcome(run_root, repo)`, and restores the source.
- [ ] `plan_outcome`, one rule. `plan_resume` returns: `("plan", kept, cancelled,
      calls_cancelled)`, `calls_cancelled` being `len(plan.costs)` (the cancelled provider-class
      commits). `plan_resume` raises a `ValueError` whose `code` attribute is a string
      (`PlanRefusal`; the resume preflight's refusal, a private class caught by its base;
      `EvaluatedValueError`, a `ValueError` through `PureExprEvaluationError`):
      `("no_plan", code)`. Anything else propagates and fails the check: a `ValueError` without
      a `code` (`WorkflowSignatureError`), `FileNotFoundError`. An uncoded failure is never a
      share of zero. A mutant whose digest is the seed's is `("same_program",)` and is not sent
      to `plan_resume`.
- [ ] Per operator, program and scenario in the readout: mutants measured; plans; the minimum,
      median and maximum of steps kept over steps committed, and of provider calls kept over
      the run's provider calls (the fake's request log has one line per call); each `no_plan`
      code with its count, reported as a count and not averaged in. `--standin FILE.json
      [--scenarios a,b]` on the command adds the section.
- Tests, failing first because `check.reuse_report` does not exist; one stand-in run of the
  fixture serves the first five:
  - `test_a_reviewer_effort_mutant_keeps_the_steps_before_the_first_review`: steps kept equals
    the steps the run committed before its first reviewer step; provider calls kept likewise.
  - `test_a_rounds_mutant_keeps_every_step`.
  - `test_a_layout_only_edit_is_the_same_program`.
  - `test_no_mutant_is_ever_run`: after `reuse_report` the fake's request log holds exactly the
    seed run's calls, and the run directory's files are byte-identical to before.
  - `test_the_seed_source_is_restored_and_the_world_removed`.
  - `test_a_coded_refusal_is_no_plan_with_its_code`, two cases, one per raising class that a
    fixture reaches: a second fixture whose coder is an `agent`, under an `effort` mutant
    (`PlanRefusal`, `invalidate_coordinator_committed`); the first fixture's run with its
    inputs file edited (the preflight's refusal, `resume_inputs_changed`). `EvaluatedValueError`
    is caught by the same clause and has no fixture here.
  - `test_an_uncoded_failure_propagates`: with the run's inputs file removed, `plan_outcome`
    raises `FileNotFoundError`.
- Run: the module (expected: two stand-in runs of a small fixture, 5 to 10 s each on a
  loaded machine; under `--dist=worksteal` a module-scoped run is made once in each worker that
  draws one of its tests).
- Reviewer: that no test reaches a real provider; that a `no_plan` is never counted as a share.

### Task T4: The `conversation` operator (deferred; 3 h when selected)

Not built now (coordinator's ruling on O6). When the conversation dimension is searched:
`continue` wraps a workflow's body in one `agent` binding for a role whose `provider-result`
forms agree in `:model` and `:effort` text, and `fresh` is its inverse, both on one line. P10
already gives the reuse of the hand-made edit.

### Task T5: First readout and hand-off (2 h)

- [ ] Export the seeds and write the stand-in files at run time (they are not committed here):

      ```bash
      mkdir -m 700 /tmp/r3x
      git archive spike/long-horizon-seed experiments/long_horizon_seed | tar -x -C /tmp/r3x
      git archive feat/seed-set-prep experiments/seed_set/programs | tar -x -C /tmp/r3x
      python -m experiments.mutants.check /tmp/r3x/experiments/long_horizon_seed \
          --programs milestones,staged,roles --standin /tmp/r3x/long_horizon.json \
          --scenarios clean,review-rejects-once --out experiments/mutants/readout.json
      python -m experiments.mutants.check /tmp/r3x/experiments/seed_set/programs \
          --programs direct,implement_check_repair,implement_review_revise,retry_until_check \
          --out /tmp/r3x/seed_set.json
      ```

      `/tmp/r3x/long_horizon.json` is written by a ten-line snippet from the `clean` and
      `review-rejects-once` answers of the seed's `demo.py`, with `{python}` where `demo.py`
      has `sys.executable`. The seed-set programs get the compile check only (no stand-in
      scenario exists for them). Expected: about 540 mutants of the long-horizon seeds, ten to
      fifteen minutes on a loaded machine for both invocations; exit 1 while P8's defect is open.
- [ ] Commit `experiments/mutants/readout.json` (it holds no interpreter path and no absolute
      path of the scratch directory: names and sources only).
- [ ] This plan's ledger: the sample; per operator the mutants and outcomes, with "`graft`: N
      of M build" beside "every other mutant compiles or is refused", so the gate is not read
      as coverage; distinct digests; the reuse figures per operator, seed and scenario, in
      steps and in provider calls.
- [ ] The hand-off of [the next section](#what-the-crash-report-feeds).
- No new test. The readout is provisional until T6 repeats it on the frozen seeds.

### Task T6: The frozen seeds (2 h; after the seed's merge to `main`)

- [ ] The command's default seed directory and programs are the merged seed's. The stand-in
      file sits beside the seeds, with the `{python}` token and both scenarios.
- [ ] `test_a_seed_crash_must_be_recorded`, at `cap` 2 (about 36 mutants): for every crash
      record of the suite's sample, its key is one of the crash or traceback keys of T0's
      `KNOWN`, **and** each of its `(operator, program)` pairs is in the `pairs` of that key in
      the committed `experiments/mutants/readout.json`. A key that is not known fails; a known
      key reached by an operator or on a seed the last readout did not record for it fails too.
      The failure message carries the record with its smallest source. The remedy is a new
      readout and the decision of the next section, never an edit of the test.
- [ ] One reuse test on `milestones` (a reviewer `effort` mutant keeps 5 of 11 steps and 4 of 8
      provider calls).
- [ ] Repeat T5's readout on the frozen seeds and commit it; the roadmap's R3 row gets its
      result (the coordinator's edit).
- Suite cost after this task: about 36 seed mutants at 0.06 to 0.6 s and one `milestones`
  stand-in run (4 s quiet, 19 s loaded).

### Task T7: Sites of the role idiom (3 h; only if the revised seed replaces the frozen one)

The spike's spelling is frozen for the first space (coordinator's ruling on O4). If a seed that
binds roles with `bind-proc` replaces it, `effort` and `model` also take the operand of
`:effort` or `:model` of a `(bind-proc (proc-ref ask) :who providers.R ...)` form as a site. They
still write a literal there and never edit an input's default. Test: on the revised seed, an
`effort` mutant builds and its plan keeps the steps before the role's first call.

## What The Crash Report Feeds

The backlog's rule is that a dropped defect returns when a mutant or a real workflow hits it
([Prevention](2026-11-13-compiler-and-runtime-defect-backlog-plan.md#prevention)). For mutants:

- **The rule reads a readout, never a prototype.** It is applied to the readout of T5, and
  again to every new readout. A readout is new whenever its sample changes: the cap, the
  number, the seeds, the operators, or the tree it compiled. P8's numbers are a prototype's and
  decide nothing by this rule; P8's key returns by the coordinator's ruling on O3, on its
  merits (an author can write the form, and a refusal is the specified outcome).
- **Every readout lists every key**, with its mutants, operators, pairs, cause and smallest
  mutant, whether or not it meets a threshold. A key below the threshold appears in each
  readout with its counts; nothing is carried as "known" without being shown.
- **The default.** A key hit by at least one mutant of `effort`, `model`, `rounds`, `drop_step`
  or `prompt` returns its defect: a search over the declared dimensions meets it. A key hit by
  `graft` only returns when mutants of at least two programs hit it, or at least three mutants
  of one program.
- **Who decides.** The coordinator, from the readout. The coordinator may return a key below
  the threshold, or hold one above it, with the reason. Returned work that together exceeds 10
  hours goes to the owner, whose cut it was.
- **Where it is recorded.** The backlog plan's ledger: one row per readout, naming the readout's
  commit, each key with its counts and the backlog row it matches, and the decision. Whether a
  key "matches" a row is judged by the row's cause and program, not by key equality.
- **A key with no row** becomes a new row in the backlog's table and in T0's `KNOWN` and
  `KNOWN_AT_T0`, with the smallest mutant's minimal form as its reproduction.
- Classes A and C of the backlog are not ordered by this: a mutant that spends wrongly does not
  crash.

The default suite does not find crashes. At a cap of 3 on the fixture, or 2 on the seeds, among
about 1,500 `graft` pairs with a crash rate near 4 in 750, its sample guards the harness (the
operators still apply, outcomes are still classified, a recorded combination has not spread).
Finding crashes is the readout's work.

## Review Focus

For a second reading, after this revision:

- That the closed-set tests fail on a widened tuple (try adding a model to `MODELS`).
- That `test_a_seed_crash_must_be_recorded` and the readout's `pairs` together cannot let a new
  defect behind a known key pass, as far as an operator and seed pair can tell two defects
  apart; and that the limit is stated (two defects with one key, one operator and one seed are
  told apart only by the record's cause and smallest source, which a person reads).
- That `plan_outcome`'s rule matches what `plan_resume` raises today.
- The coverage table against the seed-set plan's dimension table.

## Size

23 hours in six tasks, with T4 (3 hours) deferred and not counted: T1 (7) can start now; T2, T3
and T5 (11) follow the backlog's T0; T6 (2) waits for the seed's merge; T7 (3) is done only if
the revised seed replaces the frozen one. The coordinator's figure after deferring T4 was 22;
T2 is one hour larger than first planned because it now carries the crash records, the injected
crash test and the two rows of the backlog. With reviews, about 36 agent-hours.

Suite cost, on the review's measurements: T1 under 5 s; T2 about 20 s; T3 two fixture
stand-in runs of 5 to 10 s, each made once in every worker that draws one of its tests; T6 about
15 s of seed mutants and one `milestones` run. About one and a half minutes of worker time
before T6 and two after.

## What This Makes Harder

- **A point of the first space is a program.** 27 points are 27 sources and 27 digests; a
  readout that joins by program digest sees 27 programs, and the join is by name.
- **Site rules follow today's spelling.** A seed in the role idiom has no `:effort` on its
  calls until T7; a new call form (phased delivery, a library wrapper) needs a new site rule.
- **Two test-support modules become dependencies of an experiment.** A rename of
  `crash_signature`, `build_outcome`, `FAKE_CLAUDE` or `closed_path` breaks the command, loudly,
  at import.
- **A committed readout that must be renewed.** A crash reached by a new operator or seed fails
  the suite until a new readout is made and decided; that is the intent, and it is one more
  thing to do after a change to an operator or a seed.
- **`graft` mostly tests the typechecker.** 5 percent of its mutants build, so the stages after
  typecheck see few of them; raising that needs a donor chosen by scope, which is not planned.
- **Steps and calls, not dollars.** The reuse figures count steps and provider calls of one
  recorded path per scenario; they are not priced, and a run that takes another path has other
  figures.
- **The fake's observation is the real one.** The stand-in run goes through the plain command
  line, so a seed with Agent Sessions starts a tmux session for the run's length (P11: none is
  left behind after a completed run; a killed run could leave one).

## Not Verified While Planning

- No operator was written as planned: P8 used a throwaway prototype without `conversation` and
  without the name-position rule of `graft`, with `swap` (dropped) and a wider `prompt`. Its
  counts are indicative, and the review did not regenerate them.
- The key "as T0 defines it after its review": the helper list was not final when this was
  written. The probes used the innermost package function.
- The reuse figures on the seed-set programs (no stand-in scenario exists for them) and on
  scenarios other than `clean` and, for three rows, `review-rejects-once`.
- T7: no tree has both the role idiom and a stand-in run.
- P9 and "E1 does not close it" were probed on `588faf29`; the branch has moved to `c2bb56a6`.
- The round trip on a real file with non-ASCII text: none is tracked.
- That a plain-command-line run of a sessions seed leaves no tmux server when it fails midway.
- The hours: read from the prototype's size, not from a trial.
- The sampled suite and the whole suite were not run for this change, which is one document.

## Rulings

Coordinator's rulings on the review (2026-11-13):

| # | Ruling |
| --- | --- |
| O1, M4 | `check.py` imports no test module. `_signature` and `_build_outcome` move to `tests/workflow_lisp_closed_program_helpers.py` as `crash_signature` and `build_outcome` in T0's fix round; only `tests/experiments/test_mutants.py` reads `KNOWN` |
| O2, M2, M3 | The "hits" rule is accepted as revised: a key is a location and never makes a crash known; the rule reads T5's readout and each later one; keys below the threshold are listed in every readout; the coordinator decides from the readout and records it in the backlog plan's ledger |
| O3 | The new crash is recorded (roadmap, tenth batch); the right outcome is a refusal (specification §13.1) |
| O4 | The spike's spelling of the seed is frozen for the first space; T7 only if the revised seed replaces it |
| O5 | The two reuse findings go to the owner through the coordinator, in the wording of the probe section |
| O6 | `conversation` is not built now; T4 is deferred |
| O7 | The coordinator adds the rows in `docs/index.md` and the roadmap on acceptance |
| M1 | The closed sets live in `operators.py` only and are pinned literally by a test |
| M5 | One rule for "no plan": a coded refusal is `no_plan` with its code; an uncoded exception fails the check |
| M6 | The reuse result is worded as measured; T5 adds `review-rejects-once` and reports provider calls beside steps |
| M7 | The coverage table |
| M8 | In the first space a point is a program, not a binding |

Planner's rulings, with the cost if wrong:

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | A mutation is a character splice at a reader span, on decoded and line-normalised text | P5: no printer exists, the slices round-trip, comments survive. The driver design's warning is about byte offsets, which are not used | A printer is written (about a day) and the operators return forms |
| 2 | `effort` and `model` write a literal at the role's calls and never touch inputs or defaults | P10; the entry signature is frozen in every search condition; M8 | An input-binding mode is added; it gets no plan until `resume` accepts changed inputs |
| 3 | The check compiles in process and classifies with T0's two functions | P7: the key needs the traceback, and two classifiers would drift | T2 waits for T0; if T0 slips, the two functions are copied and removed again when it merges |
| 4 | `graft` is in, although it is no declared value | It is the only operator that found a crash, and its build rate is reported, not hidden | It is removed from `OPERATORS`; the readout loses its only crash-finding operator (the default suite's sample finds none either way) |
| 5 | The default suite mutates a fixture, not the seeds, until T6, and a crash on the fixture always fails | The seeds are not on `main`; the fixture is in no readout | A fixture crash blocks the suite until the defect is fixed or the coordinator rules |
| 6 | Nothing is imported from the October search or the toy | Prior art, above | A few helper lines are duplicated |
| 7 | No `swap` operator, no two-mutation mutants, no skeleton count | Not declared, not asked; composition is free by applying operators again | Added when a search asks |
| 8 | The stand-in run goes through the plain command line | P11: it works for all three seeds, and it removes the last import of a test module | A leaked tmux session after a failed sessions run; the fake observation is then moved into `tests/agent_session_shims.py` |
| 9 | The readout is one committed file, `experiments/mutants/readout.json` | M2 asks for the record of pairs to be stored with the readout and not in the test; the test must read it from the tree | A fourth file; it moves to the ledger if the coordinator prefers, and the test then cannot check pairs |

## Open Decisions For The Coordinator

All seven decisions of the first version are ruled (above). Two are new in this revision:

| # | Decision | Planner's recommendation |
| --- | --- | --- |
| N1 | The size is 23 hours, not the ruled 22: T2 grew by one hour (crash records, the injected crash test, the backlog rows) | Accept 23; the alternative is to move the two backlog rows to T0's fix round and keep 22 |
| N2 | Ruling 9: the readout is a committed file that the T6 test reads | Accept; M2's record needs a place in the tree |

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Plan written as proposed, against `main` at `b399076b` (`8a61b143` merged afterwards: nothing under `orchestrator/`). Ten probes, all zero spend, stand-in providers on a closed `PATH`, no provider or model call. The long-horizon seeds (`aa7ae4a0`) build and run on `main` as written and the seed-set programs (`5449db80`) build; only the staged-authoring spelling is refused. Reader with character spans, no printer. 1,527 prototype mutants: one crash key, new, `graft`-only, on three programs; `graft` built 38 of 750. Reuse on `milestones`, `clean`: 0, 3 and 5 of 11 steps for a planner, coder and reviewer edit. No code change |
| 2026-11-13 | Revised after the independent review (accept after fixes; no blocker, 8 majors, 12 minors; every probe it re-ran holds) and the coordinator's rulings, on `main` at `a9f9e410` merged into the branch. Changes: the closed sets pinned literally and narrowed only; a crash key is a location, with a record per key and a suite test on recorded operator and seed pairs; the "hits" rule reads readouts and lists every key; `check.py` imports no test module (one more probe, P11: the stand-in run works through the plain command line); one rule for "no plan"; the reuse result worded as measured, with the review's table, a second scenario and provider calls; the coverage table; the ruling that a point of the first space is a program, with the sentences other documents must change; `conversation` deferred. Size 23 hours. The review's second crash is listed for the backlog. No code change, no spend |
| 2026-11-13 | Plan accepted by the coordinator | The review's eight majors and twelve minors are applied in the revision (`b7b6d165`). Rulings on the revision's open decisions: N1, the two new backlog rows are entered by the backlog's Task T0 in its fix round, so T2 is 3 hours and the plan 22; N2, `experiments/mutants/readout.json` is accepted as the fourth file (data, written by the command). T1 starts now; T2 waits for the backlog's T0 on `main`. The sentences of other documents that ruling M8 makes untrue (a point of the first space is a program, effort per role is a literal at each call site) are corrected by the coordinator in one pass with the checkpoint design's findings. |
| 2026-11-13 | T1 built on `feat/mutants-t1` and revised after its independent review (accept after fixes: no blocker, one major, seven minors). Task T1's text above is corrected to ruling M8: the fixture's entry has no effort parameter and holds a literal `:effort` at each call, so `effort` has 12 mutations on it and 6 for three levels. Rulings of the fix round, which the code and its tests carry: a `replace_prompt` mutation is named `name.` and twelve hexadecimal digits of the SHA-256 of the raw text; `graft` also passes over the binder pairs of the two map forms and a `loop-state` field declaration; a source that already holds a `:model` or `:effort` string literal outside the closed sets is refused by every operator and by `sample` (`undeclared_literals` is the one check), while a model or effort that arrives as a name is an input and is left alone; `sample` refuses a negative cap; `levels` and `models` are read once and refuse a duplicate; `operators.py` splices a source as given, so the caller (T2) normalises line ends before it compares digests. Run time of the module: 5 to 14 seconds with `-n 8` at load average 76 to 90 during the review, against "under 5 s" in Task T1 and in the suite-cost arithmetic of "Size"; the machine's load is the cause, and the figure is not changed. No provider or model call. |
| 2026-11-13 | T2 built on `feat/mutants-t2`: `experiments/mutants/check.py` (`outcome`, `compile_report`, the command) and eight tests in `tests/experiments/test_mutants.py`. Rulings of the coordinator that the code carries: `check.py` imports `build_outcome` (which keys a crash with `crash_signature`) from the helper module and no test module, and reads no known list; a crash key has no kind, so a raw traceback and the `compiler_defect` it becomes under the backlog's TP1 share one key (tested by injecting one failure in `closed/build.py` with and without its defect boundary, not through a live defect); line ends are normalised before the sample and every digest; the check compiles only (a test replaces `subprocess.Popen` and the command still exits 0). The cause's first line is read from the exception as it leaves the build, by a context manager that keeps it and lets it go on, so no second `except` is written. A refusal is counted under its codes joined by a space. Rows D21 and D22 were entered by the backlog's T0 fix round, so none is added here. The fixture, by hand, at cap 100 and number 0 (`graft` 100 of 143): `effort` 12 of 12 compile, `model` 6 of 6, `rounds` 3 of 3, `drop_step` 1 of 3 (2 `name_unknown`), `prompt` 5 of 12 (7 `prompt_placeholder_missing`), `graft` 4 of 100 (96 refused under 11 codes); 31 distinct digests, none equal to the seed, no crash, exit 0. `CRASH_SEED`'s `graft` mutants crash under D21's key only. Module: 100 tests, 10 s with `-n 8`. No provider or model call. |
| 2026-11-13 | T2 fix round 1 after the independent review (accept after fixes: no blocker, one major, seven minors; the review's 1,014 mutants of the eight real seeds agree mutant by mutant with the command line, and no fixture outcome or digest changes with `PYTHONHASHSEED`). Rulings of the coordinator, which the code and its tests carry: exit 1 means a mutant crashed and nothing else; every input problem exits 2 with one line, no traceback and no readout, before any mutant compiles (a missing seed directory or program file, an unreadable one, no program, an unknown operator, a negative cap, an empty sample, a literal outside the closed sets, a missing or unwritable `--out` directory), and a seed that does not build exits 2 after its own compile; `--out` is checked before any compile; a crash record's `cause` is its smallest mutant's and `causes` counts every distinct cause under the key; a refusal holding a code that is or starts with `compiler_defect`, alone or beside other codes, is a crash for R3's gate, keyed by its cause's crash key or else by the code (in `check.py`; `build_outcome` is unchanged); a test that `check.py` loads none of the dispatch entry points `orchestrator.cli.commands.run`, `orchestrator.cli.commands.resume`, `orchestrator.workflow.evaluated.runtime` and `orchestrator.workflow.evaluated.effect_execution` (`plan_resume`'s module, which T3 imports, loads none of them); the readout's fields are documented in `check.py`'s docstring and one test reads its top-level keys from there; tests for `distinct_digests`, `equal_to_seed`, `lines_50_or_more` and the choice of `smallest`, each failing under a deliberate mutation of the code (`len(built)`, `!=`, a wrong threshold, the largest kept). Not as ruled: "refuse to overwrite a tracked file" is applied as "refuse an existing file of a git working tree other than `experiments/mutants/readout.json`", because asking git would start a process, which the check never does, and T5 and T6 must overwrite the committed readout. Module: 117 tests; with the backlog module 241 passed in 27 s with `-n 8`. The fixture by hand gives the figures of T2's row above, exit 0. No provider or model call. |
| 2026-11-13 | T3 built on `feat/mutants-t3`: `recorded_run`, `plan_outcome`, `measure` and `reuse_report` in `experiments/mutants/check.py`, `--standin FILE.json [--scenarios a,b]` on the command, and ten tests in `tests/experiments/test_mutants.py`. As built: the seed's stand-in run is `python -m orchestrator run` with the fake `claude` on `closed_path` in a temporary world; a run that does not exit 0 or leaves answers unused is an input problem (exit 2, no readout), and every stand-in run is made before any mutant compiles; each mutant is compiled again in the world to tell `compiles` and `same_program` (digest equal to the seed's) before `plan_resume`; the readout's `reuse` is one section per program and scenario with `steps`, `provider_calls`, `priced_usd` (null for every stand-in run: its calls report no usage, so no share of priced tokens is given) and, per operator and per site, `measured`, `same_program`, `plans`, `steps_kept` and `calls_kept` (min, median, max) and `no_plan` counts by code; an uncoded exception of the planner ends the command with exit 1 and a traceback. Tests: the fake answered exactly the seed's three calls and none while 15 mutants were planned; the workspace with the run root and the request log, and the fake's call counter, are byte-identical before and after planning; the reviewer `effort` mutant keeps the 3 steps and 2 calls before the first review (read from the run's journal); `rounds` keeps 4 of 4; a layout edit is `same_program`; `resume_inputs_changed` for the edited inputs file; `invalidate_coordinator_committed` for the coder `effort` mutants of a fixture whose coder is an `agent`; `FileNotFoundError` propagates for a removed inputs file. Fixture by hand (cap 100, number 0, `fixture` and the `agent` fixture, `clean` and `review-rejects-once`): readouts identical under `PYTHONHASHSEED` 1 and 2; `clean` planner, coder, reviewer edits keep 0, 1, 3 of 4 steps and 0, 1, 2 of 3 calls. Long-horizon seeds (`spike/long-horizon-seed` at `c93a6954`; `staged`, `designed`, `milestones`, `roles`; stand-in answers of its `demo.py`), cap 100, number 0, 861 s: `milestones` `clean` planner, coder, reviewer `effort` keep 0, 3, 5 of 11 steps and 0, 3, 4 of 8 calls (P10's figures), `rounds` 11 of 11, and on `review-rejects-once` the outer loop's bound 2 to 1 keeps 9 of 14; `staged` 0, 3, 5 of 6 steps; `designed` planner, reviewer, coder 0, 3, 5 of 8; `roles` no plan, `invalidate_coordinator_committed`, for every `effort`, `prompt`, `drop_step` and `graft` mutant, a plan keeping every step only for `rounds` and for the `model` mutant that writes the run's own bound model; exit 1 for one `graft` mutant of `milestones` under D21's key. Module 127 tests; with the backlog module 251 passed in 37 s with `-n 8`. No provider or model call. |
| 2026-11-13 | T3 fix round 1 after the independent review (accept after fixes: no blocker, one major, eleven minors; 88 mutants compared one by one with `resume` on the command line, no disagreement). Correction (M1): a `model` mutant that writes the model the run already used keeps every step only where the role is an `agent` declaration (`roles`, the coder of the `agents` fixture); for a `provider-result` call it cuts at that role like any other edit (`staged` coder 3 of 6, fixture coder 1 of 4, `milestones` reviewer 5 of 14 on `review-rejects-once`). The previous row's sentence on `roles` is right as scoped. Rulings of the coordinator, which the code and its tests carry: a stand-in run that times out, an `answers` that is not an object of objects, a run that fails (the line gives the last `[code]` line of its stderr, else its last line, not the run's path), unused answers and no scenario each exit 2 with one line; the recorded run is refused (exit 2) unless its request-log lines equal its committed provider-class effects (`provider`, `provider_phased`, `agent_turn`), and the module docstring states how a provider call is counted; `steps` is the committed rows of the run's journal; `priced_reason` stands beside a null `priced_usd`; the second compile is gone: `measure` takes the compile check's per-mutant results and the seed's digest, and the one compile left per planned mutant is the one inside `plan_resume`; the docstring says the module loads no dispatch entry point at import, and that planning loads the `run` command, the evaluated runtime and the effect dispatcher without calling them (the test of the fake's unchanged call count and byte-identical run stands); `_standin_runs` (split with `_read_standin`) and `measure` (split with `_planned`) are at 11 and 7 or below by a strict count (branches, loops, comprehension clauses, boolean operands, `with`, `except`). New tests: the exit 1 of the command on a `RuntimeError` injected into `plan_resume` in the command's own process, exit 2 for a failed run (its cause `[provider_exit_nonzero]`), unused answers, a timeout (limit 1 s, the fake sleeping), no scenario and `answers` not an object. By hand: the fixture command 34 s (82 s before), the long-horizon command 400 s (861 s before; load 36 to 44 against 50 to 58, so not all of the gain is the removed compile), every per-site figure identical to the first round, exit 1 for D21's `graft` crash only. Suite cost as found by the review (m5, left as it is): the module-scoped stand-in run is made in every xdist worker that draws one of its tests, about four runs of 14 to 24 s with `-n 8`, plus the `agents` run of about 15 to 19 s. Module 133 tests. No provider or model call. |
| 2026-11-14 | T5, first readout, on `feat/mutants-t5` (`main` at `9bb55dda`, with E1 and the call-site fix). Seeds read with `git show`: the four long-horizon seeds (`staged`, `designed`, `milestones`, `roles`, with `common.orc` and the two manifests) from `spike/long-horizon-seed` at `c93a6954`, and the four seed-set programs from `feat/seed-set-prep` at `5449db80`. Stand-in file written from the seed's `demo.py` answers (`clean` and `review-rejects-once`; for `designed` `clean` and `acceptance-refused-once`, its refusal scenario), `{python}` in `dev-check.json`'s argv. Sample: cap 100, number 0, every operator, Python 3.13.9. The long-horizon readout is the committed `experiments/mutants/readout.json` (`b2b72895`); the seed-set readout (compile only, no stand-in scenario exists) was written to the scratch directory as Task T5 says and is not committed. Both readouts are byte-identical under `PYTHONHASHSEED` 1 and 2 and hold no absolute path or user name. Long-horizon, 681 mutants: `effort` 48 of 48 compile, `model` 24 of 24, `rounds` 18 of 18, `drop_step` 10 of 44 (30 `name_unknown`, 4 `provider_result_provider_invalid`), `prompt` 97 of 147 (50 `prompt_placeholder_missing`), `graft`: 26 of 400 build, 373 refused under 17 codes, 1 crash; 223 distinct digests, none equal to its seed; 292 mutants of 50 lines or more, among them every `effort` and `model` mutant of `milestones` and `roles`, whose seeds are 50 lines already. Seed-set, 333 mutants: `effort` 25 of 25, `model` 10 of 10, `rounds` 6 of 6, `drop_step` 1 of 10 (9 `name_unknown`), `prompt` 21 of 35 (14 `prompt_placeholder_missing`), `graft`: 27 of 247 build, 219 refused under 15 codes, 1 crash; 90 distinct digests. Every mutant of the other five operators compiles or is refused with a code. Crash key `TypeError workflow_lisp/wcc/elaborate.py:_replace_halts_with_jump` (D21), `graft` only: `milestones/graft/21<-33` (a `let*` binding's value replaced by `(done (variant Outcome DONE …))`, cause `… WccLoopDone`) and `retry_until_check/graft/4<-10` (the same with `(continue …)`, cause `… WccLoopContinue`); no other key. Both commands exit 1. E1 and the call-site fix change nothing here: compiled against `main` at `dc024e69` (T3 merged, before both), all 1,014 mutants give the same outcome kind, the same refusal codes and the same digests. R3's gate is not met: 2 mutants, both `graft`, end in `compiler_defect`. Reuse, steps and provider calls kept of the run's total (per site; a property of these seeds and scenarios: `resume` keeps the steps before the first changed call, so an edit to a role that runs first keeps nothing): `effort` and `model` by role in the order the roles first run, `milestones` 0, 3, 5 of 11 steps and 0, 3, 4 of 8 calls (`clean`) and 0, 3, 5 of 14 and 0, 3, 4 of 10 (`review-rejects-once`); `staged` 0, 3, 5 of 6 and 0, 3, 4 of 5, and of 9 and of 7; `designed` (planner, reviewer, coder) 0, 3, 5 of 8 and 0, 3, 5 of 7, and of 11 and of 9; `roles`, an Agent Sessions seed, no plan (`invalidate_coordinator_committed`) for every `effort` mutant, and for a `model` mutant except the one that writes the model the run already used, which keeps every step (that holds only for `agent` declarations); `rounds` keeps every step on `clean` (the run never reaches a bound) and 9 of 14 (`milestones`, outer loop 2 to 1), 6 of 9 (`staged`) and 8 of 11 (`designed`) at the lowest bound after a refusal, with one `roles` bound of `review-rejects-once` getting no plan; `prompt` keeps the steps before the prompt's first use, from 0 (`guides`) to every step (`designed` `revise`, unused on `clean`); `roles` gets no plan for every `prompt`, `drop_step` and `graft` mutant. Run time: 500 and 504 s for the two long-horizon runs side by side, 28 and 21 s for the seed-set runs (load average 33 to 41). The only processes started were the 16 stand-in runs of the seeds (8 per hash seed), with the fake `claude` on `closed_path`; no mutant was run and no tmux server was left. No provider or model call. |
