"""Tests of the mechanical mutation operators (Phase 6 readiness R3, Task T1).

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md. No test compiles or runs anything:
a mutant is a string, re-read here with the package's reader. `SEED` is the only source the
default suite mutates until T6. It is spelled the way the frozen seed will be (ruling M8): effort
per role is a string literal at each call site, model per role is an entry input.

The sample relies on `random.Random(seed).random()` only, the one method whose sequence the
Python documentation fixes across versions. Written and run under Python 3.13.9.
"""

import os
import subprocess
import sys
from collections import Counter

import pytest

from experiments.mutants import operators
from experiments.mutants.operators import Mutation
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom

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
