"""Tests of the mechanical mutation operators, the compile check and the reuse figures (Phase 6 readiness R3,
Tasks T1, T2, T3).

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md. The operators' tests compile nothing:
a mutant is a string, re-read here with the package's reader. The compile check's tests build
mutants in process and run no workflow. The reuse tests run a seed, never a mutant, with the fake
`claude` on `closed_path`. `SEED` is the only source the
default suite mutates until T6. It is spelled the way the frozen seed will be (ruling M8): effort
per role is a string literal at each call site, model per role is an entry input.

The sample relies on `random.Random(seed).random()` only, the one method whose sequence the
Python documentation fixes across versions. Written and run under Python 3.13.9.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import nullcontext
from dataclasses import replace

import pytest

from experiments.mutants import check, operators
from experiments.mutants.operators import Mutation
from orchestrator.workflow_lisp.closed import artifact, build
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from tests.agent_session_shims import shim_requests
from tests.test_workflow_lisp_defect_backlog import KNOWN
from tests.workflow_lisp_closed_program_helpers import crash_signature

# The closed sets, written out: `operators.py` may not hold a Fable model, a model above the
# Sonnet ceiling or an undeclared effort (AGENTS.md, experiment rules).
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")

SEED = r"""(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule fixture) (export run)
  (defrecord Change (summary String)) (defrecord CheckReport (passed Bool) (excerpt String))
  (defunion Verdict (MET (evidence String)) (NOT_MET (reason String)))
  (defunion Outcome (DONE (summary String)) (BLOCKED (reason String)))
  (defprompt plan (:fills (task :text) (repo :text)) -> Change
    "Work in {repo}. Plan the task below. Write no code.\n\nTask: {task}")
  (defprompt work (:fills (repo :text) (plan :value Change) (note :text)) -> Change
    "Work in {repo}. Carry out this plan: {plan}. The last review said \"{note}\".")
  (defprompt review (:fills (repo :text) (report :value CheckReport)) -> Verdict
    "Review {repo}. The check reported: {report}. MET if the goal is reached.")
  (defworkflow run ((task String) (repo String) (planner String) (coder String) (reviewer String)) -> Outcome
    (let* ((plan (provider-result providers.planner :model planner :effort "medium" :timeout-sec 1200
                   :prompt (plan :task task :repo repo))))
      (loop/recur :max 2 :state (loop-state (note String ""))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((change (provider-result providers.coder :model coder :effort "medium" :timeout-sec 3600
                           :prompt (work :repo repo :plan plan :note state.note)))
                 (report (command-result dev-check :returns CheckReport)))
            (match (provider-result providers.reviewer :model reviewer :effort "medium" :timeout-sec 1200
                     :prompt (review :repo repo :report report))
              ((MET met) (done (variant Outcome DONE :summary met.evidence)))
              ((NOT_MET gap) (continue (loop-state :like state :note gap.reason))))))))))
"""


def read(text: str) -> ListExpr:
    return read_sexpr_text(text, source_path="<test>")


def shape(node):
    """A form without its spans, so that two readings compare equal."""
    if isinstance(node, ListExpr):
        return tuple(shape(item) for item in node.items)
    return type(node).__name__, node.value


def lists(node):
    """Every list at or under `node`, in document order."""
    if isinstance(node, ListExpr):
        yield node
        for item in node.items:
            yield from lists(item)


def headed(text: str, head: str) -> list[ListExpr]:
    return [form for form in lists(read(text)) if form.items and getattr(form.items[0], "value", None) == head]


def operand(form: ListExpr, key: str):
    """The item after the keyword `key` among the form's own items, or None."""
    for item, after in zip(form.items, form.items[1:]):
        if isinstance(item, KeywordAtom) and item.value == key:
            return after
    return None


def test_the_closed_sets_are_the_declared_ones():
    assert (operators.MODELS, operators.EFFORTS) == (MODELS, EFFORTS)


def test_apply_splices_disjoint_edits_given_in_any_order():
    mutation = Mutation("graft", "0<-1", ((4, 6, "Z"), (0, 2, "long")))
    assert operators.apply("abcdef", mutation) == "longcdZ"


@pytest.mark.parametrize("edits", [((0, 3, "X"), (2, 4, "Y")), ((2, 4, "Y"), (0, 3, "X")), ((4, 9, "X"),)])
def test_apply_refuses_overlapping_edits(edits):
    with pytest.raises(ValueError):
        operators.apply("abcdef", Mutation("graft", "0<-1", edits))


# The number of mutations each operator has on `SEED`.
COUNTS = {
    "effort": 12,  # 3 roles times 5 levels, less the level each role already has
    "model": 6,  # 3 roles times 2 models; the seed's models are inputs, so none is an identity
    "rounds": 3,  # one loop with bound 2: 1, 3 and 4
    "drop_step": 3,  # one binding in the outer `let*`, two in the inner
    "prompt": 12,  # 3 prompts of 3 sentences: a drop of each, and the append
    "graft": 143,  # 14 expression forms: 196 pairs, less the 53 whose donor is or contains the target
}

# Every name position holds a list headed like an expression: the entry's parameter `and`, the
# binding `record`, the map binder `not`, the loop binder `if`, the arm's pattern `(done x)`, the
# loop-state field `or`, the parameter list `(call)`. One expression occurs twice, side by side.
NAMES = """(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule names)
  (defworkflow run ((and List[Int])) -> Int
    (let* ((record (list/map ((not and)) (+ (+ not 1) (+ not 1)))))
      (loop/recur ((if 0)) :max 2 :on-exhausted 0
        (match (variant Step ON)
          ((done x) (loop/recur :max 2 :state (loop-state (or Int (list/length and))) :on-exhausted 0
                      (fn (call) (done (list/length record))))))))))
"""
NAME_POSITIONS = ["(and List[Int])", "(record (list/map ((not and)) (+ (+ not 1) (+ not 1))))", "(not and)", "(if 0)",
                  "(done x)", "(or Int (list/length and))", "(call)"]
# The fixture with its loop-state field named like a head; it compiles (checked once, outside the suite).
FIELD = (SEED.replace('(loop-state (note String ""))', '(loop-state (not String ""))')
         .replace("state.note", "state.not").replace(":like state :note", ":like state :not"))


def mutants(name: str, text: str = SEED) -> list[tuple[Mutation, str]]:
    return [(mutation, operators.apply(text, mutation)) for mutation in operators.OPERATORS[name](text)]


def frozen(text: str) -> list:
    """The surfaces no operator may change, as forms."""
    cuts = {"defprompt": slice(1, -1), "defworkflow": slice(2, 3)}  # all but the body; the parameter list
    return [form[cuts.get(form[0][1], slice(None))] for form in shape(read(text).items[0])]


@pytest.mark.parametrize("name,allowed", [("effort", EFFORTS), ("model", MODELS)])
def test_effort_and_model_write_only_declared_literals(name, allowed):
    written = {replacement for mutation, _ in mutants(name) for _, _, replacement in mutation.edits}
    assert written and written <= {f'"{value}"' for value in allowed}


def test_a_value_outside_the_sets_is_refused():
    with pytest.raises(ValueError):
        operators.effort(SEED, levels=("turbo",))
    with pytest.raises(ValueError):
        operators.model(SEED, models=("claude-fable-5-2",))
    # The first space: 3 roles times 3 levels on the spike's spelling (a name as the operand); the
    # frozen spelling already holds one of the three levels at every role.
    spike = SEED.replace(':effort "medium"', ":effort effort")
    assert len(list(operators.effort(spike, levels=("low", "medium", "high")))) == 9
    assert len(list(operators.effort(SEED, levels=("low", "medium", "high")))) == 6


@pytest.mark.parametrize("name,values", [("effort", ("low", "high")), ("model", MODELS)])
def test_levels_and_models_are_read_once_and_hold_no_duplicate(name, values):
    operator = getattr(operators, name)
    assert len(list(operator(SEED, iter(values)))) == 6
    with pytest.raises(ValueError):
        operator(SEED, (*values, values[0]))


@pytest.mark.parametrize("name", ["effort", "model"])
def test_a_call_whose_first_operand_is_no_role_is_no_site(name):
    source = '(defworkflow run () -> Change (provider-result runner :model m :effort "low" :prompt (plan)))'
    assert list(operators.OPERATORS[name](source)) == []


def position(text: str, literal: str) -> tuple[int, int]:
    """The line and column, from one, of the first occurrence of `literal`."""
    before = text[:text.index(literal)]
    return before.count("\n") + 1, len(before) - before.rfind("\n")


OUTSIDE = [(":model", "claude-fable-5-2", SEED.replace(":model reviewer", ':model "claude-fable-5-2"')),
           (":effort", "turbo", SEED.replace(':effort "medium" :timeout-sec 3600', ':effort "turbo" :timeout-sec 3600'))]


@pytest.mark.parametrize("key,value,seed", OUTSIDE, ids=["model", "effort"])
def test_a_literal_outside_the_sets_is_found_with_its_position(key, value, seed):
    assert operators.undeclared_literals(seed) == [(key, value, *position(seed, f'"{value}"'))]


@pytest.mark.parametrize("key,value,seed", OUTSIDE, ids=["model", "effort"])
@pytest.mark.parametrize("name", [*COUNTS, "replace_prompt", "sample"])
def test_a_seed_with_a_literal_outside_the_sets_is_refused(name, key, value, seed):
    produce = {**operators.OPERATORS, "replace_prompt": lambda text: [operators.replace_prompt(text, "work", "{repo}")],
               "sample": lambda text: operators.sample({"fixture": SEED, "seed": text}, 2, 1)}[name]
    with pytest.raises(ValueError):
        list(produce(seed))


def test_a_literal_outside_the_sets_is_found_in_a_form_that_is_no_call_form():
    source = '(defworkflow run () -> Int (call helper :effort "turbo"))'
    assert operators.undeclared_literals(source) == [(":effort", "turbo", *position(source, '"turbo"'))]


def test_sample_names_the_program_that_holds_the_literal():
    with pytest.raises(ValueError, match="offender"):
        operators.sample({"fixture": SEED, "offender": OUTSIDE[0][2]}, 2, 1, operators=())


def test_a_model_or_effort_that_arrives_as_a_name_is_left_alone():
    # `fable` and `turbo` are names here: inputs, bound at launch, which only the launcher can pin.
    named = SEED.replace(':effort "medium"', ":effort turbo").replace(":model reviewer", ":model fable")
    assert operators.undeclared_literals(named) == []
    assert Counter(mutation.operator for _, mutation in operators.sample({"seed": named}, 1, 1)) == dict.fromkeys(COUNTS, 1)


@pytest.mark.parametrize("name", COUNTS)
def test_each_operator_yields_mutations_of_the_fixture(name):
    assert len(mutants(name)) == COUNTS[name]


def test_mutation_names_are_unique_per_operator():
    names = [(mutation.operator, mutation.params) for name in COUNTS for mutation, _ in mutants(name)]
    assert len(set(names)) == len(names) == sum(COUNTS.values())


@pytest.mark.parametrize("key,name,value", [(":effort", "effort", "low"), (":model", "model", "claude-haiku-5-5")])
def test_effort_edits_every_call_of_one_role_and_nothing_else(key, name, value):
    # Two reviewer calls, so that "every call of the role" is more than one site.
    source = SEED.replace("providers.coder", "providers.reviewer")
    mutation = next(m for m in operators.OPERATORS[name](source) if m.params == f"reviewer={value}")
    mutant = operators.apply(source, mutation)
    calls = zip(headed(source, "provider-result"), headed(mutant, "provider-result"), strict=True)
    operands = [(shape(before.items[1])[1], shape(operand(before, key)), shape(operand(after, key)))
                for before, after in calls]
    assert operands == [(role, old, ("StringAtom", value) if role == "providers.reviewer" else old)
                        for role, old, _ in operands]
    assert [role for role, _, _ in operands].count("providers.reviewer") == len(mutation.edits) == 2
    assert [shape(f) for f in read(mutant).items[0].items[:-1]] == [shape(f) for f in read(source).items[0].items[:-1]]


@pytest.mark.parametrize("name", COUNTS)
def test_frozen_surfaces_survive(name):
    assert all(frozen(mutant) == frozen(SEED) for _, mutant in mutants(name))


@pytest.mark.parametrize("name", COUNTS)
def test_only_graft_adds_a_line(name):
    assert any(mutant.count("\n") > SEED.count("\n") for _, mutant in mutants(name)) is (name == "graft")


def literals(text: str) -> set[str]:
    """The string literals in `:model` and `:effort` position anywhere in the source."""
    found = (operand(form, key) for form in lists(read(text)) for key in (":model", ":effort"))
    return {item.value for item in found if isinstance(item, StringAtom)}


@pytest.mark.parametrize("name", ["rounds", "drop_step", "prompt", "graft"])
def test_no_other_operator_introduces_a_model_or_effort(name):
    assert all(literals(mutant) <= literals(SEED) for _, mutant in mutants(name))


def test_rounds_rewrites_the_bound_of_one_loop():
    bounds = {m.params: shape(operand(headed(mutant, "loop/recur")[0], ":max")) for m, mutant in mutants("rounds")}
    assert bounds == {"loop0=1": ("IntAtom", 1), "loop0=3": ("IntAtom", 3), "loop0=4": ("IntAtom", 4)}


def test_rounds_leaves_a_map_cap_and_a_named_bound():
    source = "(defworkflow run () -> Int (loop/recur :max limit (list/map-effect ((m xs)) :max 8 (call f :m m))))"
    assert list(operators.rounds(source)) == []


def test_drop_step_deletes_one_whole_pair():
    def bindings(text):
        return [[shape(pair)[0][1] for pair in form.items[1].items] for form in headed(text, "let*")]

    assert {m.params: bindings(mutant) for m, mutant in mutants("drop_step")} == {
        "let0.0": [[], ["change", "report"]],
        "let1.0": [["plan"], ["report"]],
        "let1.1": [["plan"], ["change"]],
    }


@pytest.mark.parametrize("source,params,mutant", ids=["space", "comment after", "last pair"], argvalues=[
    # The white space after the pair goes with it; a comment stays.
    ("(defworkflow run () -> Int (let* ((a 1) (b 2)) b))", "let0.0", "(defworkflow run () -> Int (let* ((b 2)) b))"),
    ("(defworkflow run () -> Int (let* ((a 1) ; one\n  (b 2)) b))", "let0.0",
     "(defworkflow run () -> Int (let* (; one\n  (b 2)) b))"),
    ("(defworkflow run () -> Int (let* ((a 1) ; one\n  (b 2)) b))", "let0.1",
     "(defworkflow run () -> Int (let* ((a 1) ; one\n  ) b))"),
])
def test_drop_step_takes_the_white_space_after_the_pair_and_no_comment(source, params, mutant):
    mutation = next(m for m in operators.drop_step(source) if m.params == params)
    assert operators.apply(source, mutation) == mutant


def test_drop_step_leaves_a_let_outside_a_definition():
    source = "(defmacro twice (x) (let* ((y x)) y)) (defproc run () -> Int (let* ((a 1)) a))"
    assert [operators.apply(source, mutation) for mutation in operators.drop_step(source)] == [
        "(defmacro twice (x) (let* ((y x)) y)) (defproc run () -> Int (let* () a))"]


def bodies(text: str) -> dict[str, str]:
    """The decoded body of each prompt, by name."""
    return {prompt.items[1].value: prompt.items[-1].value for prompt in headed(text, "defprompt")}


def test_prompt_edit_keeps_escapes():
    # Decoded bodies: a mutant whose escapes were re-encoded would not read back to these.
    seed = bodies(SEED)
    expected = {f"{name}.append": {**seed, name: body + operators.APPENDED} for name, body in seed.items()}
    for name, body in seed.items():
        pieces = body.split(". ")
        expected |= {f"{name}.drop{k}": {**seed, name: ". ".join(pieces[:k] + pieces[k + 1:])}
                     for k in range(len(pieces))}
    assert {m.params: bodies(mutant) for m, mutant in mutants("prompt")} == expected


def test_replace_prompt_puts_the_raw_text_in_one_body():
    mutation = operators.replace_prompt(SEED, "work", r"Say \"go\" in {repo}.\n{plan} {note}")
    assert bodies(operators.apply(SEED, mutation)) == {**bodies(SEED), "work": 'Say "go" in {repo}.\n{plan} {note}'}


def test_prompt_of_one_sentence_is_only_appended_to():
    source = '(defprompt one (:fills (repo :text)) -> Change "Work in {repo}")'
    assert [mutation.params for mutation in operators.prompt(source)] == ["one.append"]


def test_replace_prompt_names_each_proposal():
    names = [operators.replace_prompt(SEED, "work", raw).params for raw in ("A {repo}", "B {repo}", "A {repo}")]
    assert names[0] == names[2] != names[1] and all(name.startswith("work.") for name in names)


def test_replace_prompt_name_is_the_same_in_another_process():
    code = ("import sys; from experiments.mutants import operators; "
            "print(operators.replace_prompt(sys.stdin.read(), 'work', 'A {repo}').params)")
    # The other process imports what this one does and hashes strings with another seed.
    other = subprocess.run([sys.executable, "-c", code], input=SEED, capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, sys.path)),
                                "PYTHONHASHSEED": "20261113"})
    assert other.stdout.strip() == operators.replace_prompt(SEED, "work", "A {repo}").params


def test_prompt_names_are_the_generator_s_own():
    assert not {mutation.params for mutation, _ in mutants("prompt")} & {
        operators.replace_prompt(SEED, name, raw).params for name in bodies(SEED) for raw in ("A {repo}", "B {repo}")}


def own_raw(name: str) -> str:
    """The source text between the quotes of a prompt's body."""
    span = next(p for p in headed(SEED, "defprompt") if p.items[1].value == name).items[-1].span
    return SEED[span.start.offset + 1:span.end.offset - 1]


@pytest.mark.parametrize("name,raw", [
    ("work", own_raw("work")),  # an identity
    ("work", 'a bare " quote'),
    ("work", "a line\nend"),
    ("work", "a backslash at the end\\"),
    ("work", "an escape the reader refuses: \\q"),
    ("work", "a carriage\rreturn"),
    ("work", ""),
    ("absent", "a prompt the module does not have"),
])
def test_replace_prompt_refuses_an_identity_and_text_that_is_no_string_body(name, raw):
    with pytest.raises(ValueError):
        operators.replace_prompt(SEED, name, raw)


@pytest.mark.parametrize("source", [SEED, NAMES], ids=["seed", "names"])
def test_graft_puts_another_expression_of_the_module_in_place_of_one(source):
    # A donor that is its target, holds it or reads the same would hold the target's text: the
    # one expression that occurs twice (in `NAMES`) has its two copies side by side in one form.
    for mutation in operators.graft(source):
        (start, end, donor), = mutation.edits
        assert donor in source and source[start:end] not in donor
        assert shape(read(donor).items[0])[0][1] in operators.EXPRESSION_HEADS


def graft_targets(source: str) -> list[str]:
    """The text of every form some graft replaces, in document order."""
    spans = sorted({(start, end) for mutation in operators.graft(source) for start, end, _ in mutation.edits})
    return [source[start:end] for start, end in spans]


def test_graft_skips_name_positions():
    targets, donors = graft_targets(NAMES), {donor for m in operators.graft(NAMES) for _, _, donor in m.edits}
    assert not [name for name in NAME_POSITIONS if name in targets or name in donors]
    # What a name position binds is still an expression: every form below, and no other.
    assert [shape(read(target).items[0])[0][1] for target in targets] == [
        "let*", "list/map", "+", "+", "+", "loop/recur", "match", "variant", "loop/recur", "loop-state",
        "list/length", "done", "list/length"]


def test_graft_skips_a_loop_state_field_of_a_legal_program():
    assert '(not String "")' not in graft_targets(FIELD)
    assert len(list(operators.graft(FIELD))) == COUNTS["graft"]


def test_graft_takes_the_operand_of_a_loop_state_keyword_for_an_expression():
    source = "(defworkflow run () -> Int (continue (loop-state :like state :n (list/length xs) :m (list/length ys))))"
    assert graft_targets(source)[2:] == ["(list/length xs)", "(list/length ys)"]


SOURCES = {"seed": SEED, "names": NAMES}


def every(sources: dict[str, str]) -> list[tuple[str, Mutation]]:
    """All mutations, programs in name order, operators in `OPERATORS` order, each in document order."""
    return [(program, mutation) for program in sorted(sources) for name in operators.OPERATORS
            for mutation in operators.OPERATORS[name](sources[program])]


def test_sample_is_deterministic_and_capped():
    first = operators.sample(SOURCES, 3, 1)
    assert operators.sample(SOURCES, 3, 1) == first
    assert operators.sample(SOURCES, 3, 2) != first
    assert max(Counter((program, mutation.operator) for program, mutation in first).values()) == 3


def test_sample_keeps_document_order_and_unique_names():
    drawn, mutations = operators.sample(SOURCES, 3, 1), every(SOURCES)
    positions = [mutations.index(pair) for pair in drawn]
    assert positions == sorted(set(positions))
    assert len({(program, mutation.operator, mutation.params) for program, mutation in drawn}) == len(drawn)


def test_sample_takes_every_mutation_at_or_under_the_cap():
    assert operators.sample({"seed": SEED}, COUNTS["graft"], 5) == every({"seed": SEED})


def test_sample_of_number_one_is_these_mutants():
    # The plan's rule worked out by hand once: a change of the generator or of the rule shows here.
    drawn = operators.sample({"seed": SEED}, 2, 1)
    assert [f"{program}/{mutation.operator}/{mutation.params}" for program, mutation in drawn] == [
        "seed/effort/coder=max", "seed/effort/reviewer=high",
        "seed/model/planner=claude-sonnet-5-5", "seed/model/coder=claude-sonnet-5-5",
        "seed/rounds/loop0=3", "seed/rounds/loop0=4",
        "seed/drop_step/let1.0", "seed/drop_step/let1.1",
        "seed/prompt/plan.append", "seed/prompt/work.drop2",
        "seed/graft/1<-4", "seed/graft/7<-10",
    ]


def test_sample_draws_from_the_named_operators_only():
    drawn = operators.sample(SOURCES, 2, 1, operators=("graft", "rounds"))
    assert [(program, mutation.operator) for program, mutation in drawn] == [
        ("names", "rounds"), ("names", "rounds"), ("names", "graft"), ("names", "graft"),
        ("seed", "rounds"), ("seed", "rounds"), ("seed", "graft"), ("seed", "graft")]


def test_sample_refuses_an_operator_it_does_not_have():
    with pytest.raises(ValueError):
        operators.sample(SOURCES, 2, 1, operators=("swap",))


def test_sample_refuses_a_negative_cap():
    with pytest.raises(ValueError):
        operators.sample(SOURCES, -1, 1)


# ---------------------------------------------------------------------------------------------
# The compile check (Task T2). A seed directory holds `NAME.orc` per program, entry `NAME::run`,
# and the two manifests. Only this module reads the backlog's `KNOWN`; `check.py` reads no known list.

PROVIDERS = {f"providers.{role}": "claude_unrestricted_workspace" for role in ("planner", "coder", "reviewer")}
COMMANDS = {"dev-check": {"stable_command": ["python", "dev_check.py"], "closure": ["dev_check.py"]}}
# The kinds of the backlog's signatures; the mutants' crash keys are those of the first two.
KINDS = ("crash", "traceback", "refused", "builds", "value", "digests", "ran")


def seed_dir(root, sources: dict[str, str]):
    root.mkdir()
    for program, text in sources.items():
        (root / f"{program}.orc").write_text(text, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps(PROVIDERS), encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(COMMANDS), encoding="utf-8")
    return root


def snapshot(root) -> dict:
    return {path.relative_to(root): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def mutant_of(name: str, params: str) -> str:
    return operators.apply(SEED, next(m for m in operators.OPERATORS[name](SEED) if m.params == params))


def raising_after_first(original, error=lambda *args, **kwargs: RuntimeError("injected\nsecond line")):
    """`original` for the first call (the seed's own build), then `error(*args, **kwargs)` raised."""
    calls = []

    def stand_in(*args, **kwargs):
        calls.append(None)
        if len(calls) == 1:
            return original(*args, **kwargs)
        raise error(*args, **kwargs)

    return stand_in


def test_outcome_kinds(tmp_path):
    work = seed_dir(tmp_path / "work", {"fixture": SEED})
    seed = check.outcome(work, "fixture")
    found = {}
    for name, params in (("rounds", "loop0=3"), ("drop_step", "let0.0"), ("prompt", "work.drop0")):
        (work / "fixture.orc").write_text(mutant_of(name, params), encoding="utf-8")
        found[name] = check.outcome(work, "fixture")
    assert seed[0] == found["rounds"][0] == "compiles" and seed[1] != found["rounds"][1]
    assert found["drop_step"] == ("refused", "name_unknown")
    assert found["prompt"] == ("refused", "prompt_placeholder_missing")


def test_an_escaped_exception_is_a_crash_record_and_exit_1(tmp_path, monkeypatch):
    seed, original = seed_dir(tmp_path / "seed", {"fixture": SEED}), artifact.build_closed_program
    monkeypatch.setattr(artifact, "build_closed_program", raising_after_first(original))
    report = check.compile_report(seed, ["fixture"], 3, 0, operators=("rounds",))
    (record,) = report["crashes"]
    assert (record["key"][0], record["mutants"], record["pairs"]) == ("RuntimeError", COUNTS["rounds"],
                                                                      [["rounds", "fixture"]])
    assert record["cause"] == "injected"
    read(record["smallest"]["source"])
    monkeypatch.setattr(artifact, "build_closed_program", raising_after_first(original))
    assert check.main([str(seed), "--programs", "fixture", "--operators", "rounds",
                       "--out", str(tmp_path / "readout.json")]) == 1


@pytest.mark.parametrize("kind", ["crash", "traceback"])
def test_a_coded_crash_and_its_traceback_have_one_key(kind, tmp_path, monkeypatch):
    # A raw traceback that a later fix turns into `compiler_defect` keeps its key: the key has no kind.
    monkeypatch.setattr(build, "_build_with_builder", raising_after_first(build._build_with_builder))
    if kind == "traceback":
        monkeypatch.setattr(build, "compiler_defect_boundary", nullcontext)
    report = check.compile_report(seed_dir(tmp_path / "seed", {"fixture": SEED}), ["fixture"], 3, 0,
                                  operators=("rounds",))
    assert [(record["key"], record["kinds"], record["mutants"]) for record in report["crashes"]] == [
        (["RuntimeError", "workflow_lisp/closed/build.py:build_closed_program"], [kind], COUNTS["rounds"])]


def test_the_fixture_sample_has_no_crash(tmp_path):
    seed = seed_dir(tmp_path / "seed", {"fixture": SEED})
    before = snapshot(seed)
    report = check.compile_report(seed, ["fixture"], 3, 0)
    assert report["crashes"] == [], json.dumps(report["crashes"], indent=2)
    counts = report["operators"]
    assert list(counts) == list(operators.OPERATORS) and all(row["mutants"] >= 1 for row in counts.values())
    assert all(row["compiles"] + sum(row["refused"].values()) + sum(row["crash_keys"].values()) == row["mutants"]
               for row in counts.values())
    assert sum(row["mutants"] for row in counts.values()) == report["sample"]["mutants"]
    assert snapshot(seed) == before


def test_the_known_list_has_the_shape_this_module_reads():
    assert {signature[0] for signature in KNOWN.values()} <= set(KINDS)
    assert any(signature[0] in KINDS[:2] for signature in KNOWN.values())


def test_the_check_starts_no_process(tmp_path, monkeypatch):
    # It compiles and nothing else: no workflow runs, no provider or command is started. This sees a
    # launch through `subprocess` only; the next test is the structural guarantee.
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: started.append(args) or pytest.fail("a process"))
    assert check.main([str(seed_dir(tmp_path / "seed", {"fixture": SEED})), "--programs", "fixture", "--cap", "1",
                       "--out", str(tmp_path / "readout.json")]) == 0
    assert started == []


def test_command_exits_0_without_a_crash(tmp_path):
    seed, out = seed_dir(tmp_path / "seed", {"fixture": SEED}), tmp_path / "readout.json"
    done = subprocess.run([sys.executable, "-m", "experiments.mutants.check", str(seed), "--programs", "fixture",
                           "--operators", "rounds", "--out", str(out)], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, sys.path))})
    assert done.returncode == 0, done.stderr
    readout = json.loads(out.read_text(encoding="utf-8"))
    assert (readout["operators"]["rounds"]["mutants"], readout["crashes"]) == (COUNTS["rounds"], [])


# The runtime's dispatch entry points: the `run` and `resume` commands (`run_workflow`, `resume`), the
# evaluated runtime (`execute_pure_run`, `execute_pure_resume`) and the effect dispatcher
# (`perform_external`). `plan_resume`'s module, which Task T3 imports, loads none of them at import; a call of
# `plan_resume` loads them and calls nothing in them (`test_no_mutant_is_ever_run`).
DISPATCH = ("orchestrator.cli.commands.run", "orchestrator.cli.commands.resume",
            "orchestrator.workflow.evaluated.runtime", "orchestrator.workflow.evaluated.effect_execution")


def test_the_check_imports_no_dispatch_entry_point():
    code = "import sys, experiments.mutants.check; print('\\n'.join(sys.modules))"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                          env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, sys.path))})
    loaded = set(done.stdout.split())
    assert all(importlib.util.find_spec(name) for name in DISPATCH)
    assert "experiments.mutants.check" in loaded and not loaded & set(DISPATCH)


def test_the_readout_keys_are_the_documented_ones(tmp_path):
    documented = re.findall(r"^- `(\w+)`:", check.__doc__, re.MULTILINE)
    report = check.compile_report(seed_dir(tmp_path / "seed", {"fixture": SEED}), ["fixture"], 1, 0,
                                  operators=("rounds",))
    assert list(report) == documented


def test_the_committed_readout_has_the_documented_keys():
    # The readout of Task T5 is made with `--standin`, so it also holds `reuse`.
    documented = re.findall(r"^- `(\w+)`:", check.__doc__, re.MULTILINE)
    readout = json.loads(check.READOUT.read_text(encoding="utf-8"))
    assert list(readout) == [*documented, "reuse"]


def test_digests_and_long_mutants_are_counted(tmp_path, monkeypatch):
    # Three layout-only mutants compile to the seed's digest; two copies of one bound share a digest.
    bound = next(mutation for mutation in operators.rounds(SEED) if mutation.params == "loop0=3")
    drawn = [("fixture", Mutation("rounds", "newline", ((0, 0, "\n"),))),
             ("fixture", Mutation("rounds", "space", ((0, 0, " "),))),
             ("fixture", Mutation("rounds", "long", ((0, 0, "\n" * check.LONG),))),
             ("fixture", bound), ("fixture", replace(bound, params="again"))]
    monkeypatch.setattr(check, "sample", lambda *args, **kwargs: drawn)
    report = check.compile_report(seed_dir(tmp_path / "seed", {"fixture": SEED}), ["fixture"], 4, 0)
    row = report["operators"]["rounds"]
    figures = (row["compiles"], report["distinct_digests"], report["equal_to_seed"], row["lines_50_or_more"])
    assert figures == (5, 2, 3, 1)


def test_the_smallest_crashing_mutant_and_its_cause_are_recorded(tmp_path, monkeypatch):
    # Each crash's message names the length of its mutant, so the record's cause must be the smallest's.
    monkeypatch.setattr(artifact, "compile_typed_program_with_result", raising_after_first(
        artifact.compile_typed_program_with_result,
        lambda path, **kwargs: RuntimeError(f"length {len(path.read_text(encoding='utf-8'))}")))
    report = check.compile_report(seed_dir(tmp_path / "seed", {"fixture": SEED}), ["fixture"], 100, 0,
                                  operators=("drop_step", "prompt"))
    lengths = Counter(f"length {len(mutant)}" for name in ("drop_step", "prompt") for _, mutant in mutants(name))
    shortest = min(len(mutant) for name in ("drop_step", "prompt") for _, mutant in mutants(name))
    (record,) = report["crashes"]
    assert len(lengths) > 1 and record["mutants"] == sum(lengths.values())
    assert (len(record["smallest"]["source"]), record["cause"], record["causes"]) == (
        shortest, f"length {shortest}", dict(lengths))


def diagnostic(code: str, cause: BaseException | None) -> LispFrontendDiagnostic:
    start = SourcePosition(path="fixture.orc", line=1, column=1, offset=0)
    return LispFrontendDiagnostic(code=code, message=f"{code}\ndetail", span=SourceSpan(start=start, end=start),
                                  cause=cause)


@pytest.mark.parametrize("codes", [("type_mismatch", "compiler_defect_constructor_type_dropped"),
                                   ("compiler_defect", "name_unknown")], ids=["prefixed code", "beside another"])
def test_a_refusal_holding_a_compiler_defect_code_is_a_crash(codes, tmp_path, monkeypatch):
    # A `compiler_defect` diagnostic with its cause is keyed by the cause; one without, by its code.
    with pytest.raises(TypeError) as raised:
        artifact.canonical_json_bytes(object())  # an exception raised in the package
    cause = raised.value if codes[0] == "compiler_defect" else None
    diagnostics = tuple(diagnostic(code, cause if code.startswith("compiler_defect") else None) for code in codes)
    monkeypatch.setattr(artifact, "compile_typed_program_with_result", raising_after_first(
        artifact.compile_typed_program_with_result, lambda *args, **kwargs: LispFrontendCompileError(diagnostics)))
    out = tmp_path / "readout.json"
    assert check.main([str(seed_dir(tmp_path / "seed", {"fixture": SEED})), "--programs", "fixture",
                       "--operators", "rounds", "--out", str(out)]) == 1
    key = list(crash_signature(cause)) if cause else [codes[1]]
    assert [record["key"] for record in json.loads(out.read_text(encoding="utf-8"))["crashes"]] == [key]


def usage_case(name: str, tmp_path) -> list[str]:
    """The command line of one input problem; the seed is the fixture unless the case says otherwise."""
    seed, out = seed_dir(tmp_path / "seed", {"fixture": SEED}), tmp_path / "readout.json"
    line = {"programs": "fixture", "out": str(out)}
    if name == "missing directory":
        seed = tmp_path / "nodir"
    elif name == "literal outside the sets":
        seed = seed_dir(tmp_path / "outside", {"fixture": OUTSIDE[0][2]})
    elif name == "out in a git working tree":
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        (tmp_path / "repo" / "tracked.json").write_text("{}", encoding="utf-8")
        line["out"] = str(tmp_path / "repo" / "tracked.json")
    line |= {"missing file": {"programs": "nosuch"}, "no program": {"programs": ""}, "a comma only": {"programs": ","},
             "unknown operator": {"operators": "swap"}, "negative cap": {"cap": "-1"}, "empty sample": {"cap": "0"},
             "out directory missing": {"out": str(tmp_path / "nodir" / "readout.json")}}.get(name, {})
    return [str(seed), *(item for flag, value in line.items() for item in (f"--{flag}", value))]


USAGE = ["missing file", "missing directory", "no program", "a comma only", "unknown operator", "negative cap",
         "empty sample", "literal outside the sets", "out directory missing", "out in a git working tree"]


@pytest.mark.parametrize("name", USAGE)
def test_an_input_problem_exits_2_before_any_compile(name, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check, "prepare_closed_program_bundle", lambda *args, **kwargs: pytest.fail("a compile"))
    argv = usage_case(name, tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    assert check.main(argv) == 2
    error = capsys.readouterr().err
    assert len(error.splitlines()) == 1 and "Traceback" not in error, error
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


def test_a_seed_that_does_not_build_exits_2(tmp_path, capsys):
    seed = seed_dir(tmp_path / "seed", {"fixture": SEED.replace(") -> Outcome", ") -> Change")})
    assert check.main([str(seed), "--programs", "fixture", "--out", str(tmp_path / "readout.json")]) == 2
    assert len(capsys.readouterr().err.splitlines()) == 1 and not (tmp_path / "readout.json").exists()


# ---------------------------------------------------------------------------------------------
# Reuse figures (Task T3). One stand-in run of the fixture (the fake `claude` on `closed_path`)
# serves the module fixture's tests; `AGENTS_SEED` is the fixture with its coder an `agent`.

CHANGE, MET = {"result": {"summary": "s"}}, {"result": {"variant": "MET", "evidence": "e"}}
CHECK_SCRIPT = ('import json, os\nopen(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w")'
                '.write(json.dumps({"passed": True, "excerpt": ""}))\n')
STANDIN = {"inputs": {"task": "t", **dict.fromkeys(("planner", "coder", "reviewer"), "claude-haiku-5-5")},
           "files": {"dev_check.py": CHECK_SCRIPT},
           "answers": {"fixture": {"clean": [CHANGE, CHANGE, MET]}, "agents": {"clean": [CHANGE, CHANGE, MET]}}}
AGENTS_SEED = (SEED.replace("(defmodule fixture)", "(defmodule agents)")
               .replace(":prompt (plan :task task :repo repo))))",
                        ':prompt (plan :task task :repo repo)))\n         (coding (agent providers.coder :model coder :effort "medium")))')
               .replace('(provider-result providers.coder :model coder :effort "medium" :timeout-sec 3600',
                        "(provider-result coding :timeout-sec 3600"))
LAYOUT = Mutation("rounds", "layout", ((0, 0, "\n"),))


def raised(call) -> BaseException | None:
    """The exception `call()` raises, or None."""
    try:
        call()
    except Exception as error:  # the test asserts its type
        return error
    return None


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """The fixture's `clean` run, measured under its `effort` and `rounds` mutants and a layout-only edit, then its
    inputs file edited and removed; what each test reads is kept, and the world is removed before the tests run."""
    root = tmp_path_factory.mktemp("reuse")
    seed, scratch = seed_dir(root / "seed", {"fixture": SEED}), root / "scratch"
    scratch.mkdir()
    mutants = [("fixture", mutation) for name in ("effort", "rounds") for mutation in operators.OPERATORS[name](SEED)]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tempfile, "tempdir", str(scratch))
        results, seeds = check.compiled(seed, {"fixture": SEED}, [*mutants, ("fixture", LAYOUT)])
        layout = [result for result in results if result["params"] == "layout"]
        with check.recorded_run(seed, "fixture", STANDIN, "clean") as run:
            source, workspace, inputs = run["world"] / "src" / "fixture.orc", run["workspace"], run["world"] / "inputs.json"
            seen = {"source": source.read_bytes(), "workspace": snapshot(workspace),
                    "calls": (run["world"] / "bin" / ".claude.calls").read_text(encoding="utf-8")}
            commits = [json.loads(line) for line in (run["run_root"] / "memo.jsonl").read_text().splitlines()]
            commits = [row for row in commits if row["record"] == "committed"]
            first_review = next(index for index, row in enumerate(commits) if "variant" in row["value"])
            data = {"run": {key: run[key] for key in ("steps", "calls", "priced_usd", "priced_reason")},
                    "before_review": (first_review, sum(row["effect_class"] == "provider" for row in commits[:first_review])),
                    "section": check.measure(run, [result for result in results if result not in layout], seeds["fixture"]),
                    "layout": check.measure(run, layout, seeds["fixture"])}
            data["after"] = {"source": source.read_bytes(), "workspace": snapshot(workspace),
                             "calls": (run["world"] / "bin" / ".claude.calls").read_text(encoding="utf-8")}
            data["before"], data["requests"] = seen, shim_requests(workspace)
            inputs.write_text(json.dumps({**json.loads(inputs.read_text()), "task": "another"}), encoding="utf-8")
            data["inputs_changed"] = check.plan_outcome(run["run_root"], workspace)
            inputs.unlink()
            data["inputs_removed"] = raised(lambda: check.plan_outcome(run["run_root"], workspace))
        data["left"] = list(scratch.iterdir())
    return data


def test_a_reviewer_effort_mutant_keeps_the_steps_before_the_first_review(recorded):
    reviewer = recorded["section"]["operators"]["effort"]["sites"]["reviewer"]
    steps, calls = recorded["before_review"]
    assert (reviewer["measured"], reviewer["plans"]) == (4, 4) and (steps, calls) == (3, 2)
    assert (reviewer["steps_kept"], reviewer["calls_kept"]) == (dict.fromkeys(("min", "median", "max"), steps),
                                                               dict.fromkeys(("min", "median", "max"), calls))


def test_a_rounds_mutant_keeps_every_step(recorded):
    rounds, run = recorded["section"]["operators"]["rounds"], recorded["run"]
    assert (rounds["plans"], rounds["steps_kept"]["min"], rounds["calls_kept"]["min"]) == (3, run["steps"], run["calls"])
    assert (run["steps"], run["calls"], run["priced_usd"], run["priced_reason"] is None) == (4, 3, None, False)


def test_a_layout_only_edit_is_the_same_program(recorded):
    row = recorded["layout"]["operators"]["rounds"]
    assert (row["measured"], row["same_program"], row["plans"], row["steps_kept"], row["no_plan"]) == (1, 1, 0, None, {})


def test_no_mutant_is_ever_run(recorded):
    # The fake answered the seed's three calls; planning 15 mutants added no call and changed no byte of the run.
    assert len(recorded["requests"]) == len(STANDIN["answers"]["fixture"]["clean"]) == len(recorded["before"]["calls"])
    assert recorded["section"]["operators"]["effort"]["measured"] + recorded["section"]["operators"]["rounds"]["measured"] == 15
    assert recorded["after"]["calls"] == recorded["before"]["calls"]
    assert recorded["after"]["workspace"] == recorded["before"]["workspace"]


def test_the_seed_source_is_restored_and_the_world_removed(recorded):
    assert recorded["after"]["source"] == recorded["before"]["source"] == SEED.encode("utf-8")
    assert recorded["left"] == []


NO_REPO_SEED = (SEED.replace("(defmodule fixture)", "(defmodule norepo)").replace(" (repo String)", "")
                .replace("(repo :text) ", "").replace(" (repo :text)", "").replace("{repo}", "here")
                .replace(":repo repo ", "").replace(" :repo repo", ""))


@pytest.mark.parametrize("program", ["fixture", "norepo"])
def test_a_stand_in_run_binds_repo_only_when_the_entry_declares_it(program, tmp_path):
    seed = seed_dir(tmp_path / "seed", {program: {"fixture": SEED, "norepo": NO_REPO_SEED}[program]})
    standin = {**STANDIN, "answers": {program: {"clean": [CHANGE, CHANGE, MET]}}}
    with check.recorded_run(seed, program, standin, "clean") as run:
        bound = json.loads((run["world"] / "inputs.json").read_text(encoding="utf-8"))
        assert (run["steps"], run["calls"], "repo" in bound) == (4, 3, program == "fixture")


def test_a_coded_refusal_is_no_plan_with_its_code(recorded, tmp_path, monkeypatch):
    # The preflight's refusal: the run's inputs file edited.
    assert recorded["inputs_changed"] == ("no_plan", "resume_inputs_changed")
    # `PlanRefusal`: an edited `agent` declaration under its committed turn, through the command.
    seed, standin, out = seed_dir(tmp_path / "seed", {"agents": AGENTS_SEED}), tmp_path / "standin.json", tmp_path / "out.json"
    standin.write_text(json.dumps(STANDIN), encoding="utf-8")
    assert check.main([str(seed), "--programs", "agents", "--operators", "effort", "--standin", str(standin),
                       "--out", str(out)]) == 0
    (section,) = json.loads(out.read_text(encoding="utf-8"))["reuse"]
    coder = section["operators"]["effort"]["sites"]["coder"]
    assert (coder["plans"], coder["no_plan"], coder["steps_kept"]) == (0, {"invalidate_coordinator_committed": 4}, None)


def test_an_uncoded_failure_propagates(recorded):
    assert isinstance(recorded["inputs_removed"], FileNotFoundError)


NO_RUN = {"scenarios without standin": None, "standin without a key": {"inputs": {}, "answers": {}},
          "scenario no program has": STANDIN, "no scenario": {**STANDIN, "answers": {"other": {"clean": []}}},
          "answers not an object": {**STANDIN, "answers": ["clean"]}}


@pytest.mark.parametrize("case", list(NO_RUN))
def test_a_standin_problem_exits_2_before_any_run(case, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("a run"))
    standin = tmp_path / "standin.json"
    standin.write_text(json.dumps(NO_RUN[case]), encoding="utf-8")
    extra = {"scenarios without standin": ["--scenarios", "clean"],
             "scenario no program has": ["--standin", str(standin), "--scenarios", "clean,nosuch"]}
    argv = [str(seed_dir(tmp_path / "seed", {"fixture": SEED})), "--programs", "fixture",
            "--out", str(tmp_path / "readout.json"), *extra.get(case, ["--standin", str(standin)])]
    assert check.main(argv) == 2
    assert len(capsys.readouterr().err.splitlines()) == 1 and not (tmp_path / "readout.json").exists()


SLEEPS = {"mode": "timeout", "result": {"summary": "s"}}  # the fake sleeps 30 s before it answers
FAILED_RUNS = {"run fails": [CHANGE, CHANGE], "answers left unused": [CHANGE, CHANGE, MET, CHANGE],
               "run times out": [SLEEPS, CHANGE, MET]}


@pytest.mark.parametrize("case", list(FAILED_RUNS))
def test_a_failed_standin_run_exits_2_with_its_cause(case, tmp_path, monkeypatch, capsys):
    # The run is made and removed; no mutant compiles, and the one line names the cause, not the run.
    scratch, standin = tmp_path / "scratch", tmp_path / "standin.json"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.setattr(check, "STANDIN_TIMEOUT", 1 if case == "run times out" else check.STANDIN_TIMEOUT)
    monkeypatch.setattr(check, "prepare_closed_program_bundle", lambda *args, **kwargs: pytest.fail("a compile"))
    standin.write_text(json.dumps({**STANDIN, "answers": {"fixture": {"clean": FAILED_RUNS[case]}}}), encoding="utf-8")
    argv = [str(seed_dir(tmp_path / "seed", {"fixture": SEED})), "--programs", "fixture", "--standin", str(standin),
            "--out", str(tmp_path / "readout.json")]
    assert check.main(argv) == 2
    (line,) = capsys.readouterr().err.splitlines()
    assert "/runs/" not in line and not (tmp_path / "readout.json").exists()
    if case == "run fails":
        assert "[provider_exit_nonzero]" in line
    assert not [path for path in scratch.iterdir() if path.name.startswith("mutants-reuse-")]


def test_an_uncoded_planner_exception_ends_the_command_with_exit_1(tmp_path):
    # Injected in the command's own process: a `RuntimeError` from `plan_resume` is not a share and not a refusal.
    standin, out = tmp_path / "standin.json", tmp_path / "readout.json"
    standin.write_text(json.dumps(STANDIN), encoding="utf-8")
    code = ("import sys\nfrom experiments.mutants import check\n"
            "def planner(*args, **kwargs):\n    raise RuntimeError('injected')\n"
            "check.plan_resume = planner\nsys.exit(check.main(sys.argv[1:]))\n")
    done = subprocess.run([sys.executable, "-c", code, str(seed_dir(tmp_path / "seed", {"fixture": SEED})),
                           "--programs", "fixture", "--operators", "rounds", "--standin", str(standin),
                           "--out", str(out)], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, sys.path))})
    assert done.returncode == 1 and "RuntimeError: injected" in done.stderr and not out.exists()
