"""Task P1 of the staged-workflow authoring plan: a prompt application is a value of type `Prompt[T]`.

Design: `docs/design/workflow_lisp_staged_workflow_authoring.md` §4.1 (prompt values, the head rule, where
`Prompt[...]` may be written) and §4.4 (a provider is a value only as an argument). Nothing consumes a prompt
value yet, so every position outside `:prompt` refuses with `prompt_value_escape`, a call included.

Each program is workflow `run` of module `m` at target 2.40, built in process through the public build with a
provider externs file naming `providers.a` and `providers.b`. Digests named "recorded by the base build" were
read from builds of these sources on an export of `main` at `497853b3` (`git archive`), never on a tree with
this change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_lisp_closed_program_helpers import build_outcome

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule m) (export run)
  (defrecord Pair (a Int))
  (defrecord Note (text String))
  (defprompt ask (:fills (q :text)) -> Pair "Answer {q}.")
  (defprompt jot (:fills (q :text)) -> Note "Note {q}.")
  DEFINITIONS
  (defworkflow run ((n Int) (model String)) -> RESULT BODY))
'''
ASK = '(ask :q "x")'
CALL = '(provider-result providers.a :model model :prompt {})'


def build(root: Path, body: str, *definitions: str, result: str = "Int"):
    """The public build of `run`; returns the build result, or raises the build's error."""
    source = SOURCE.replace("DEFINITIONS", "\n  ".join(definitions)).replace("RESULT", result).replace("BODY", body)
    (root / "m.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.a": "codex", "providers.b": "codex"}))
    return build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        provider_externs_path=root / "providers.json", workspace_root=root))


def outcome(root: Path, body: str, *definitions: str, result: str = "Int") -> tuple:
    """`("builds", digest)`, `("refused", codes...)` or the crash of a `compiler_defect`."""
    built = []
    seen = build_outcome(lambda: built.append(build(root, body, *definitions, result=result)))
    return ("builds", built[0].program.digest) if built else seen


def refusal(root: Path, body: str, *definitions: str, result: str = "Int") -> str:
    """The message of the one diagnostic a refused build gives."""
    with pytest.raises(LispFrontendCompileError) as stopped:
        build(root, body, *definitions, result=result)
    (diagnostic,) = stopped.value.diagnostics
    return diagnostic.message


# ---------------------------------------------------------------------------------------------
# The head rule keeps the meaning of every program that compiles today (design §4.1, §11).

SHARED_NAME = {
    "a let* binding named like the prompt, used in :prompt": (
        "Pair", f"(let* ((ask 1)) {CALL.format(ASK)})", (),
        "sha256:fad5c355321570ddb5a18f0f22e06a4ab5c081ba0193d0779118b85fc8dc4548"),
    "the binding's value a provider call": (
        "Pair", f'(let* ((ask {CALL.format(ASK)})) {CALL.format("(ask :q " + chr(34) + "y" + chr(34) + ")")})', (),
        "sha256:bb0893ed9c696affabc5307ac40f92f09b459f6946df9fb3f50536fab11c738f"),
    "a procedure named like the prompt, both used": (
        "Int", f'(let* ((r {CALL.format(ASK)})) (ask "z"))', ("(defproc ask ((q String)) -> Int 1)",),
        "sha256:2270fdc18a5143e29250140b6b3a8898518566069fd13ef1bc8aaaa60ec7ea1c"),
    "a prompt without slots": (
        "Pair", CALL.format("(nil0)"), ('(defprompt nil0 (:fills) -> Pair "Say nothing.")',),
        "sha256:2aed33a00046f31a227fb1ac4796101d860016e214236bd9d219b6c68f2421cf"),
    "a prompt without slots named like a procedure, both used": (
        "Int", f'(let* ((p {CALL.format("(nil0)")})) (nil0))',
        ('(defprompt nil0 (:fills) -> Pair "Say nothing.")', "(defproc nil0 () -> Int 7)"),
        "sha256:7f9618c4c4a6e44bb45c60a6459148aed5f34a876226719433274b2276a5ad51"),
    "a prompt named like a form (record), both used": (
        "Pair", f'(let* ((r (record Pair :a 1))) {CALL.format("(record :q " + chr(34) + "x" + chr(34) + ")")})',
        ('(defprompt record (:fills (q :text)) -> Pair "R {q}.")',),
        "sha256:31c6131c49f643bc1ac82a6ffeb5b73e096490921b0e72aea32c52cc797d349a"),
    "a prompt named like an operator (list/length), both used": (
        "Int", f'(let* ((r {CALL.format("(list/length :q " + chr(34) + "x" + chr(34) + ")")})) (list/length (list 1 2)))',
        ('(defprompt list/length (:fills (q :text)) -> Pair "R {q}.")',),
        "sha256:b05d44585f47ae0f9db433f1e55c1da3a32f08a77c2ce6ecfaade2d78c05788f"),
}


@pytest.mark.parametrize("case", sorted(SHARED_NAME))
def test_programs_whose_prompt_shares_a_name_keep_their_digests(tmp_path, case):
    result, body, definitions, recorded = SHARED_NAME[case]

    assert outcome(tmp_path, body, *definitions, result=result) == ("builds", recorded)


# ---------------------------------------------------------------------------------------------
# The type of a prompt application, and the positions where a prompt value refuses.

@pytest.mark.parametrize(("application", "type_name"), [(ASK, "Prompt[Pair]"), ('(jot :q "x")', "Prompt[Note]")])
def test_prompt_application_has_type_prompt_of_its_result(tmp_path, application, type_name):
    """The refusal names the type of the value it refuses."""
    assert f"`{type_name}`" in refusal(tmp_path, f"(let* ((p {application})) n)")


def test_prompt_application_types_its_fills_before_it_refuses(tmp_path):
    assert outcome(tmp_path, "(let* ((p (ask :q n))) n)") == ("refused", "prompt_slot_type_mismatch")


TAKE = "(defproc take ((p Prompt[Pair]) (k Int)) -> Int k)"
VALUE_POSITIONS = {
    "a let* binding": (f"(let* ((p {ASK})) n)", ()),
    "a bind-proc argument": (f"(let* ((f (bind-proc (proc-ref add) :k {ASK}))) (f n))",
                             ("(defproc add ((k Int) (m Int)) -> Int (+ k m))",)),
    "a record field": (f"(let* ((r (record Pair :a {ASK}))) n)", ()),
    "a list element": (f"(list/length (list {ASK}))", ()),
    "loop state": (f"(loop/recur ((s {ASK})) :max 1 :on-exhausted n (done n))", ()),
    "an if value": (f"(let* ((p (if (> n 0) {ASK} {ASK}))) n)", ()),
    "a match value": (f"(let* ((p (match (variant V A :k 1) ((A a) {ASK}) ((B b) {ASK})))) n)",
                      ("(defunion V (A (k Int)) (B (j Int)))",)),
    "a procedure result": ("(f n)", (f"(defproc f ((k Int)) -> Int {ASK})",)),
    "a procedure argument": (f"(take {ASK} n)", (TAKE,)),
    "a defun argument": (f"(g {ASK})", ("(defun g ((x Int)) -> Int x)",)),
    "a defun body": ("(g n)", (f"(defun g ((x Int)) -> Int (let* ((p {ASK})) x))",)),
    "a workflow input": (f"(call inner :x {ASK})", ("(defworkflow inner ((x Int)) -> Int x)",)),
    "a workflow result": (ASK, ()),
    "a procedure parameter used as a value": ("n", ("(defproc f ((p Prompt[Pair])) -> Int (let* ((q p)) 1))",)),
}


@pytest.mark.parametrize("position", sorted(VALUE_POSITIONS))
def test_prompt_value_positions_refuse(tmp_path, position):
    body, definitions = VALUE_POSITIONS[position]
    result = "Pair" if position == "a workflow result" else "Int"

    assert outcome(tmp_path, body, *definitions, result=result) == ("refused", "prompt_value_escape")


TYPE_POSITIONS = {
    "a record field": "(defrecord H (p Prompt[Pair]))",
    "a union field": "(defunion U (A (p Prompt[Pair])) (B (k Int)))",
    "List[Prompt[X]]": "(defproc f ((ps List[Prompt[Pair]])) -> Int 1)",
    "Optional[Prompt[X]]": "(defproc f ((p Optional[Prompt[Pair]])) -> Int 1)",
    "a workflow parameter": "(defworkflow w ((p Prompt[Pair])) -> Int 1)",
    "a defun parameter": "(defun g ((p Prompt[Pair])) -> Int 1)",
    "a result type": "(defproc f ((k Int)) -> Prompt[Pair] 1)",
    "inside ProcRef[...]": "(defproc f ((g ProcRef[Prompt[Pair] -> Int])) -> Int 1)",
}


@pytest.mark.parametrize("position", sorted(TYPE_POSITIONS))
def test_prompt_type_is_a_parameter_type_only(tmp_path, position):
    assert outcome(tmp_path, "n", TYPE_POSITIONS[position]) == ("refused", "prompt_value_escape")


def test_prompt_type_of_a_let_proc_local_parameter_refuses(tmp_path):
    body = "(let-proc ((h ((p Prompt[Pair])) -> Int 1)) (h n))"

    assert outcome(tmp_path, body) == ("refused", "prompt_value_escape")


def test_prompt_type_of_a_procedure_parameter_builds_the_program_without_it(tmp_path):
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()

    assert outcome(tmp_path / "with", "n", TAKE) == outcome(tmp_path / "without", "n")


# ---------------------------------------------------------------------------------------------
# A provider is a value only as the provider of a call (design §4.4, defect D7).

PROVIDER_VALUES = {
    "a let* binding": ("(let* ((p providers.a)) n)", ()),
    "a record field": ("(let* ((h (record H :p providers.a))) n)", ("(defrecord H (p Provider))",)),
    "an if value": ("(let* ((p (if (> n 0) providers.a providers.b))) n)", ()),
    "a procedure result": ("(let* ((p (f))) n)", ("(defproc f () -> Provider providers.a)",)),
    "a procedure argument": ("(f providers.a)", ("(defproc f ((w Provider)) -> Int 1)",)),
}


@pytest.mark.parametrize("position", sorted(PROVIDER_VALUES))
def test_provider_used_as_a_value_refuses_with_one_diagnostic(tmp_path, position):
    """In reached code. The base build gives `compiler_defect` for each (`KeyError` in
    `wcc/elaborate.py:_infer_expr_type`)."""
    body, definitions = PROVIDER_VALUES[position]

    assert outcome(tmp_path, body, *definitions) == ("refused", "prompt_value_escape")


SHADOWS_PROVIDER = {
    "a let* binding": ("(let* ((providers.a 1)) providers.a)", (), "sha256:061d33e31ce4586cc32b2f5d22001309f8e77417707c859cf897c374a091e54f"),
    "a let* binding in a procedure": ("(f 1)", ("(defproc f ((k Int)) -> Int (let* ((providers.a k)) providers.a))",),
                                      "sha256:a72a552c03e37b2cc75dacfe6a96b98d324bb2e7b2252118000e5bc2ad956944"),
}


@pytest.mark.parametrize("position", sorted(SHADOWS_PROVIDER))
def test_binding_named_like_a_provider_keeps_its_digest(tmp_path, position):
    """A name bound over a provider extern's name is that binding, not the provider (recorded by the base build)."""
    body, definitions, recorded = SHADOWS_PROVIDER[position]

    assert outcome(tmp_path, body, *definitions) == ("builds", recorded)


UNREACHED_PROVIDER = "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"
NAMES_PROVIDER = {
    "a record field": "(defrecord H (p Provider))",
    "a list item": "(defrecord H (ps List[Provider]))",
    "a defun parameter": "(defun g ((p Provider)) -> Int 1)",
    "a result type": "(defproc f ((k Int)) -> Provider providers.a)",
    "a ProcRef type": "(defproc f ((g ProcRef[Provider -> Int])) -> Int 1)",
    "a defproc parameter": "(defproc f ((p Provider)) -> Int 1)",
    "a provider bound by let* in an unreached procedure": "(defproc f () -> Int (let* ((p providers.a)) 1))",
}


@pytest.mark.parametrize("position", sorted(NAMES_PROVIDER))
def test_unreached_definition_that_names_provider_keeps_its_digest(tmp_path, position):
    assert outcome(tmp_path, "n", NAMES_PROVIDER[position]) == ("builds", UNREACHED_PROVIDER)


# ---------------------------------------------------------------------------------------------
# What stays refused: a partial application, a prompt named as a value, a reference to a prompt.

STAYS_REFUSED = {
    "a partial application": ("(let* ((p (ask))) n)", "Int", "prompt_slot_undischarged"),
    "a partial application in :prompt": (CALL.format("(ask)"), "Pair", "prompt_slot_undischarged"),
    "a bare prompt name in :prompt": (CALL.format("ask"), "Pair", "prompt_partial_application_unsupported"),
    "a bare prompt name as a value": ("(let* ((p ask)) n)", "Int", "name_unknown"),
    "proc-ref of a prompt": ("(let* ((r (proc-ref ask))) n)", "Int", "proc_ref_unknown"),
    "bind-proc over a prompt": ('(let* ((r (bind-proc (proc-ref ask) :q "x"))) n)', "Int", "proc_ref_unknown"),
}


@pytest.mark.parametrize("case", sorted(STAYS_REFUSED))
def test_partial_application_and_proc_ref_of_a_prompt_stay_refused(tmp_path, case):
    body, result, code = STAYS_REFUSED[case]

    assert outcome(tmp_path, body, result=result) == ("refused", code)
