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
import re

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_lisp_closed_program_helpers import build_outcome

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule m)IMPORTS (export run)
  (defrecord Pair (a Int))
  (defrecord Note (text String))
  (defprompt ask (:fills (q :text)) -> Pair "Answer {q}.")
  (defprompt jot (:fills (q :text)) -> Note "Note {q}.")
  DEFINITIONS
  (defworkflow run ((n Int) (model String)) -> RESULT BODY))
'''
ASK = '(ask :q "x")'
CALL = '(provider-result providers.a :model model :prompt {})'


def build(root: Path, body: str, *definitions: str, result: str = "Int", lib: str | None = None):
    """The public build of `run`; returns the build result, or raises the build's error.

    `lib` is the definitions of a module `lib` beside `m`, exporting each name it defines; `m` imports them."""
    source = SOURCE.replace("DEFINITIONS", "\n  ".join(definitions)).replace("RESULT", result).replace("BODY", body)
    source = source.replace("IMPORTS", "" if lib is None else f" (import lib :as lib :only ({' '.join(_defined(lib))}))")
    if lib is not None:
        (root / "lib.orc").write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule lib) '
                                      f"(export {' '.join(_defined(lib))})\n  {lib})\n", encoding="utf-8")
    (root / "m.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.a": "codex", "providers.b": "codex"}))
    return build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        provider_externs_path=root / "providers.json", workspace_root=root))


def _defined(definitions: str) -> list[str]:
    return re.findall(r"\((?:defrecord|defunion|defproc) ([^\s)]+)", definitions)


def outcome(root: Path, body: str, *definitions: str, result: str = "Int", lib: str | None = None) -> tuple:
    """`("builds", digest)`, `("refused", codes...)` or the crash of a `compiler_defect`."""
    built = []
    seen = build_outcome(lambda: built.append(build(root, body, *definitions, result=result, lib=lib)))
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


# The provider stands alone on its line; the refusal is located at that line, in the file that holds it.
PROVIDER_PLACES = {
    "directly in the workflow": ("m.orc", "(let* ((p\n      providers.a)) n)", (), None),
    "in a procedure the workflow calls": ("m.orc", "(f n)", ("(defproc f ((k Int)) -> Int\n    (let* ((p\n      providers.b)) k))",), None),
    "in a procedure of an imported module": ("lib.orc", "(g n)", (), "(defproc g ((k Int)) -> Int\n    (let* ((p\n      providers.a)) k))"),
}


def _provider_line(path: Path) -> int:
    (line,) = [number for number, text in enumerate(path.read_text().splitlines(), 1) if text.strip().startswith("providers.")]
    return line


@pytest.mark.parametrize("place", sorted(PROVIDER_PLACES))
def test_provider_used_as_a_value_is_refused_at_its_own_line(tmp_path, place):
    file_name, body, definitions, lib = PROVIDER_PLACES[place]
    with pytest.raises(LispFrontendCompileError) as stopped:
        build(tmp_path, body, *definitions, lib=lib)
    (diagnostic,) = stopped.value.diagnostics

    assert (Path(diagnostic.span.start.path).name, diagnostic.span.start.line) == (file_name, _provider_line(tmp_path / file_name))


def _with_binder_named_like_a_provider(source: str) -> str:
    renamed = re.sub(r"(?<![\w.\-])u(?![\w\-])", "providers.a", source)
    if renamed == source:
        raise ValueError("the defect record's row no longer binds `u`")
    return renamed


@pytest.mark.parametrize("row", ["D7", "D7-hoisted"])
def test_a_compiler_defect_on_a_binder_named_like_a_provider_stays_a_compiler_defect(tmp_path, row):
    """The defect record's row (a loop binder out of scope) with that binder spelled `providers.a`, the extern
    declared: no provider is used as a value, so the base's crash stands (recorded by the base build)."""
    from tests.test_workflow_lisp_defect_backlog import ROWS, _install

    path = _install(tmp_path, {"m.orc": _with_binder_named_like_a_provider(ROWS[row].source)})
    (tmp_path / "providers.json").write_text(json.dumps({"providers.a": "codex"}))
    seen = build_outcome(lambda: build_closed_program_bundle(FrontendBuildRequest(
        source_path=path, source_roots=(tmp_path,), entry_workflow="m::run", workspace_root=tmp_path,
        command_boundaries_path=tmp_path / "commands.json", provider_externs_path=tmp_path / "providers.json")))

    assert seen == ("crash", "KeyError", "workflow_lisp/wcc/elaborate.py:_infer_expr_type")


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


TAKE_PROVIDER = "(defproc take ((w Provider) (k Int)) -> Int k)"
BIND = "(bind-proc (proc-ref take) :w providers.a)"
UNCALLED_BIND_PROC = {
    "a let* binding": (f"(let* ((f {BIND})) n)", (TAKE_PROVIDER,), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "an alias of it": (f"(let* ((f {BIND}) (g f)) n)", (TAKE_PROVIDER,), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "inside a reached procedure": ("(f n)", (TAKE_PROVIDER, f"(defproc f ((k Int)) -> Int (let* ((g {BIND})) k))"), None,
                                   "sha256:f3e85f5e4f834968add31aff4dc577724846a0e4b8ffef6ddaea1d6d8f0566f8"),
    "an if branch": (f"(if (> n 0) (let* ((f {BIND})) n) 0)", (TAKE_PROVIDER,), None, "sha256:fc359258b0fe46e139218ef99484a503c775fc1b0dd60fb31b114fb1eb0c2213"),
    "a map body": (f"(list/length (list/map ((x (list 1 2))) (let* ((f {BIND})) x)))", (TAKE_PROVIDER,), None, "sha256:dadf68606c17a1152f3e1bce42ce8315f85af9e748b72ad9783db10247c5a670"),
    "a loop body": (f"(loop/recur ((s 0)) :max 1 :on-exhausted n (let* ((f {BIND})) (done s)))", (TAKE_PROVIDER,), None,
                    "sha256:69e24e7b37cc2c08f31d9678a7bde00bd057fcae516ee9964f1443de6ce42836"),
    "over a let-proc local": ("(let-proc ((h ((w Provider) (k Int)) -> Int k)) "
                              "(let* ((g (bind-proc (proc-ref h) :w providers.a))) n))", (), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "beside a proc-ref": (f"(let* ((g {BIND}) (r (proc-ref take))) n)", (TAKE_PROVIDER,), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a macro expansion": ("(mk n)", (TAKE_PROVIDER, f"(defmacro mk (x) (let* ((f {BIND})) x))"), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "over an imported procedure": ("(let* ((f (bind-proc (proc-ref lib.take) :w providers.a))) n)", (), TAKE_PROVIDER,
                                   "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a provider chosen by if inside the argument": (
        "(let* ((f (bind-proc (proc-ref take) :w (if (> n 0) providers.a providers.b)))) n)", (TAKE_PROVIDER,), None,
        "sha256:b1a55001d85fe2f7b0dcba0c7d39f45302f98a712836589209bfab32c7764b31"),
    "a provider in a record inside the argument": (
        "(let* ((f (bind-proc (proc-ref tk) :h (record H :p providers.a)))) n)",
        ("(defrecord H (p Provider))", "(defproc tk ((h H) (k Int)) -> Int k)"), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a procedure returning a provider as the argument": (
        "(let* ((f (bind-proc (proc-ref take) :w (pick)))) n)",
        (TAKE_PROVIDER, "(defproc pick () -> Provider providers.a)"), None, "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
}


@pytest.mark.parametrize("position", sorted(UNCALLED_BIND_PROC))
def test_bind_proc_over_a_provider_that_is_not_called_keeps_its_digest(tmp_path, position):
    """A `bind-proc` argument is not a refused position (design §4.4); recorded by the base build."""
    body, definitions, lib, recorded = UNCALLED_BIND_PROC[position]

    assert outcome(tmp_path, body, *definitions, lib=lib) == ("builds", recorded)


# A type the author declares, or imports, under the name `Prompt` or `Provider` keeps its meaning.
USER_PROMPT = "(defunion Prompt :forall (T) (SOME (value T)) (NONE (none Int)))"
OPEN = "(match p ((SOME s) s.value) ((NONE x) 0))"
DECLARED_PROMPT = {
    "a record field": ("n", (USER_PROMPT, "(defrecord H (p Prompt[Int]))"), "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a let* value": (f"(let* ((p (variant Prompt[Int] SOME :value n))) {OPEN})", (USER_PROMPT,), "sha256:014728386301059deac8f4e74a60d6ac3c21d6ca0474c589661d6da6a7371104"),
    "a result type": ("(match (f n) ((SOME s) s.value) ((NONE x) 0))",
                      (USER_PROMPT, "(defproc f ((k Int)) -> Prompt[Int] (variant Prompt[Int] SOME :value k))"),
                      "sha256:c18f857cad03539c2ca9a8f5826c4c118c07c7797fd550b68b918e3d3080e599"),
    "a workflow parameter": ("n", (USER_PROMPT, "(defworkflow w ((p Prompt[Int])) -> Int 1)"), "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a procedure parameter it uses": ("(f (variant Prompt[Int] SOME :value n))",
                                      (USER_PROMPT, f"(defproc f ((p Prompt[Int])) -> Int {OPEN})"), "sha256:a6aad26bc7d7a421f7ad3b38bc444531102839b5872e6fd393e3b2225662334b"),
    "a list item": ("n", (USER_PROMPT, "(defrecord H (ps List[Prompt[Int]]))"), "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
}


def test_a_type_parameter_named_prompt_keeps_the_base_refusal(tmp_path):
    """Under `:forall (Prompt)` the name is the type parameter, which takes no argument, as on the base."""
    definition = "(defproc f :forall (Prompt) ((x Prompt) (p Prompt[Pair])) -> Int 1)"

    assert outcome(tmp_path, "n", definition) == ("refused", "generic_union_not_generic")


@pytest.mark.parametrize("position", sorted(DECLARED_PROMPT))
def test_a_union_declared_as_prompt_keeps_its_digest(tmp_path, position):
    """`Prompt[...]` is the built-in type only where no declared or imported type has the name (recorded by the
    base build)."""
    body, definitions, recorded = DECLARED_PROMPT[position]

    assert outcome(tmp_path, body, *definitions) == ("builds", recorded)


IMPORTED_PROMPT = {
    "a record field": ("n", ("(defrecord H (p Prompt[Int]))",)),
    "a procedure parameter it uses": ("(f (variant Prompt[Int] SOME :value n))",
                                      (f"(defproc f ((p Prompt[Int])) -> Int {OPEN})",)),
    "a procedure parameter it does not use": ("n", ("(defproc f ((p Prompt[Int])) -> Int 1)",)),
}


@pytest.mark.parametrize("position", sorted(IMPORTED_PROMPT))
def test_an_imported_union_named_prompt_keeps_the_base_refusal(tmp_path, position):
    """The prelude's `Prompt` shadows an imported one, so the base refuses these with `generic_union_not_generic`;
    the built-in `Prompt[...]` does not take them over."""
    body, definitions = IMPORTED_PROMPT[position]

    assert outcome(tmp_path, body, *definitions, lib=USER_PROMPT) == ("refused", "generic_union_not_generic")


USER_PROVIDER = {
    "a record field": ("n", ("(defrecord Provider (a Int))", "(defrecord H (p Provider))"), "sha256:4c5fbebc34adead3e9e5abdfc4ff7f0b6e4700aba45a5604fecae6c4e235e738"),
    "a record as parameter and result": ("(let* ((r (f (record Provider :a n)))) r.a)",
                                         ("(defrecord Provider (a Int))", "(defproc f ((w Provider)) -> Provider w)"),
                                         "sha256:a14bdac276aea1f7decd3d19845a9df61f8079b664245af4e8c88e1720ab97d0"),
    "a union as parameter and result": ("(match (f (variant Provider ONE :a n)) ((ONE o) o.a) ((TWO t) t.b))",
                                        ("(defunion Provider (ONE (a Int)) (TWO (b Int)))",
                                         "(defproc f ((w Provider)) -> Provider w)"), "sha256:2df6ebd3b8cf077f81690b1e17387c97fb36763a05cf8133509377fe62d107e0"),
}


@pytest.mark.parametrize("position", sorted(USER_PROVIDER))
def test_a_type_declared_as_provider_keeps_its_digest(tmp_path, position):
    """Recorded by the base build; the provider check reads extern names, not the type name."""
    body, definitions, recorded = USER_PROVIDER[position]

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
