"""Tests of the mechanical mutation operators (Phase 6 readiness R3, Task T1).

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md. No test compiles or runs anything:
a mutant is a string, re-read here with the package's reader. `SEED` is the only source the
default suite mutates until T6. It is spelled the way the frozen seed will be (ruling M8): effort
per role is a string literal at each call site, model per role is an entry input.

The sample relies on `random.Random(seed).random()` only, the one method whose sequence the
Python documentation fixes across versions. Written and run under Python 3.13.9.
"""

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

# Name positions: a binding named `record`, a map binder named `not`, a parameter list `(call)`.
NAMES = """(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule names)
  (defworkflow run ((xs List[Int])) -> Int
    (let* ((record (list/map ((not xs)) (+ not 1))))
      (loop/recur :max 2 :state (loop-state (n Int 0)) :on-exhausted 0
        (fn (call) (done (list/length record)))))))
"""


def mutants(name: str, text: str = SEED) -> list[tuple[Mutation, str]]:
    return [(mutation, operators.apply(text, mutation)) for mutation in operators.OPERATORS[name](text)]


def frozen(text: str) -> list:
    """The surfaces no operator may change, as forms."""
    module = read(text).items[0].items
    surfaces = [shape(form) for form in module if not shape(form)[0][1].startswith(("defprompt", "defworkflow"))]
    surfaces += [shape(prompt)[1:-1] for prompt in headed(text, "defprompt")]
    return surfaces + [shape(headed(text, "defworkflow")[-1].items[2])]


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


def own_raw(name: str) -> str:
    """The source text between the quotes of a prompt's body."""
    span = next(p for p in headed(SEED, "defprompt") if p.items[1].value == name).items[-1].span
    return SEED[span.start.offset + 1:span.end.offset - 1]


@pytest.mark.parametrize("name,raw", [
    ("work", own_raw("work")),  # an identity
    ("work", 'a bare " quote'),
    ("work", "a line\nend"),
    ("work", "a backslash at the end\\"),
    ("work", ""),
    ("absent", "a prompt the module does not have"),
])
def test_replace_prompt_refuses_an_identity_and_text_that_is_no_string_body(name, raw):
    with pytest.raises(ValueError):
        operators.replace_prompt(SEED, name, raw)


def test_graft_puts_another_expression_of_the_module_in_place_of_one():
    # No expression of the seed occurs twice, so a donor that held its target would show as text.
    for mutation, _ in mutants("graft"):
        (start, end, donor), = mutation.edits
        assert donor in SEED and SEED[start:end] not in donor
        assert shape(read(donor).items[0])[0][1] in operators.EXPRESSION_HEADS


def test_graft_skips_name_positions():
    names = ["(record (list/map ((not xs)) (+ not 1)))", "(not xs)", "(call)"]
    spans = [(NAMES.index(name), NAMES.index(name) + len(name)) for name in names]
    grafts = list(operators.graft(NAMES))
    taken = [m.params for m in grafts for start, end, donor in m.edits if (start, end) in spans or donor in names]
    assert grafts and not taken
