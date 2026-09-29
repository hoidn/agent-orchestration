"""Generated programs and their classification for `tests/test_workflow_lisp_totality_matrix.py`.

One program per cell: one value form written in one position, at target 2.33.
Contract: docs/design/workflow_lisp_core_calculus_middle_end.md section 9
(elaboration totality: a program that passes typecheck elaborates, normalizes
and defunctionalizes; any restriction is a typecheck diagnostic that names it).
Case letters refer to docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
section 2.1.

Every effect is a command-backed procedure. All commands run one probe script,
which appends `<command> <arg>` to `probe.log`, so a test can assert the ordered
command log of the whole run.

Each form has one type. The calls that the brief's cases a and c are about
return unions, so they can be `match` subjects; the command-backed call and
the pure `match` return a record, so that they reach cases b and d.
"""

from __future__ import annotations

from dataclasses import dataclass


HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.33")\n'

PROBE = """import json, os, sys
from pathlib import Path
command, n = sys.argv[1], int(sys.argv[2])
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(f"{command} {n}\\n")
payload = {
    "fetch": {"n": n},
    "find": {"variant": "HIT", "n": n},
    "gate": {"variant": "OPEN", "n": n},
    "check": {"variant": "SOME", "value": {"n": n}},
}[command]
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""

COMMANDS = ("fetch", "find", "gate", "check")

# Declarations. In a program, `{probe}` becomes the probe path and `{type}` the form's type.
BOX = "  (defrecord Box (n Int))\n"
PICK = "  (defunion Pick (HIT (n Int)) (MISS (n Int)))\n"
MAYBE = "  (defunion Maybe :forall (T) (SOME (value T)) (NONE (n Int)))\n"
GATE = """  (defunion Gate (OPEN (n Int)) (SHUT (n Int)))
  (defproc gate ((n Int)) -> Gate
    :effects ((uses-command gate))
    :lowering inline
    (command-result gate :argv ("python" "{probe}" "gate" n) :returns Gate))
"""
FETCH = """  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "{probe}" "fetch" n) :returns Box))
"""
FIND = """  (defproc find ((n Int)) -> Pick
    :effects ((uses-command find))
    :lowering inline
    (command-result find :argv ("python" "{probe}" "find" n) :returns Pick))
"""
IMPORT_FIND = "  (import grt/lib :only (Pick find))\n"
LOOKUP = """  (defproc lookup ((n Int)) -> Pick
    :effects ((uses-command find))
    :lowering inline
    (find n))
"""
ATTEMPT = """  (defproc check ((b Box)) -> Maybe[Box]
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "{probe}" "check" b.n) :returns Maybe[Box]))
  (defproc attempt :forall (S) ((subject S) (hook ProcRef[(S) -> Maybe[S]]))
    :where ((S is-record))
    -> Maybe[S]
    :effects ()
    :lowering inline
    (hook subject))
"""

LIB = HEADER + "  (defmodule grt/lib)\n  (export Pick find)\n" + PICK + FIND.rstrip() + ")\n"


@dataclass(frozen=True)
class ValueType:
    seed: str  # another value of the type, written without effects
    arms: str | None  # `match` arms that read `n` out of the union; None: not a union


TYPES = {
    "Int": ValueType("0", None),
    "Box": ValueType("(record Box :n 0)", None),
    "Pick": ValueType("(variant Pick MISS :n 0)", "((HIT h) h.n) ((MISS m) m.n)"),
    "Maybe[Box]": ValueType("(variant Maybe[Box] NONE :n 0)", "((SOME s) s.value.n) ((NONE z) z.n)"),
}


@dataclass(frozen=True)
class Form:
    type: str
    expr: str
    value: object  # the value of `expr`, nested as the workflow outputs flatten it
    decls: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()  # command log of evaluating `expr` once
    prelude: str = ""  # a `let*` binding wrapped around the workflow body
    prelude_calls: tuple[str, ...] = ()
    lib: bool = False  # the program also has module `grt/lib`


HIT = {"variant": "HIT", "n": 7}
SOME = {"variant": "SOME", "value": {"n": 7}}

FORMS = {
    "literal": Form("Int", "7", 7),
    "record": Form("Box", "(record Box :n 7)", {"n": 7}, (BOX,)),
    "plain-variant": Form("Pick", "(variant Pick HIT :n 7)", HIT, (PICK,)),
    "generic-variant": Form("Maybe[Box]", "(variant Maybe[Box] SOME :value (record Box :n 7))", SOME, (BOX, MAYBE)),
    "field-access": Form("Int", "src.n", 7, (BOX,), prelude="(src (record Box :n 7))"),
    "defun-call": Form("Pick", "(hit 7)", HIT, (PICK, "  (defun hit ((n Int)) -> Pick (variant Pick HIT :n n))\n")),
    "pure-proc-call": Form(
        "Pick", "(make-hit 7)", HIT,
        (PICK, "  (defproc make-hit ((n Int)) -> Pick :effects () :lowering inline (variant Pick HIT :n n))\n"),
    ),
    "command-call": Form("Box", "(fetch 7)", {"n": 7}, (BOX, FETCH), ("fetch 7",)),
    "imported-wrapper-call": Form("Pick", "(lookup 7)", HIT, (IMPORT_FIND, LOOKUP), ("find 7",), lib=True),
    "generic-hook-call": Form(
        "Maybe[Box]", "(attempt (record Box :n 7) (proc-ref check))", SOME, (BOX, MAYBE, ATTEMPT), ("check 7",)
    ),
    "pure-match": Form(
        "Box", "(match g ((OPEN o) (record Box :n o.n)) ((SHUT c) (record Box :n c.n)))", {"n": 7},
        (BOX, GATE), prelude="(g (gate 7))", prelude_calls=("gate 7",),
    ),
}


@dataclass(frozen=True)
class Position:
    body: str  # workflow body: {expr} is the form, {type} its type, {seed} its seed, {arms} its match arms
    returns: str = "{type}"
    decls: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()  # commands the position runs before the form


# `record-field` reads the field back, so the workflow returns the form's type as
# `workflow-tail` does. `variant-field` returns the variant: a variant built
# without effects cannot be read back with `match` (plain-variant @ match-subject).
POSITIONS = {
    "let-binding": Position("(let* ((v {expr})) v)"),
    "match-subject": Position("(match {expr} {arms})", returns="Int"),
    "record-field": Position("(let* ((w (record Wrap :v {expr}))) w.v)", decls=("  (defrecord Wrap (v {type}))\n",)),
    "variant-field": Position("(variant Carry HOLD :v {expr})", "Carry", ("  (defunion Carry (HOLD (v {type})))\n",)),
    "loop-state-field": Position("""(loop/recur :max 2
      :state (loop-state (v {type} {seed}) (turn Int 0))
      :on-exhausted {seed}
      (fn (state)
        (if (= state.turn 0)
          (continue (loop-state :like state :v {expr} :turn 1))
          (done state.v))))"""),
    "done-value": Position("""(loop/recur :max 1
      :state (loop-state (turn Int 0))
      :on-exhausted {seed}
      (fn (state) (done {expr})))"""),
    "on-exhausted-value": Position("""(loop/recur :max 1
      :state (loop-state (turn Int 0))
      :on-exhausted {expr}
      (fn (state)
        (if (= state.turn 1)
          (done {seed})
          (continue (loop-state :like state :turn 1)))))"""),
    "procedure-argument": Position(
        "(pass {expr})", decls=("  (defproc pass ((v {type})) -> {type} :effects () :lowering inline v)\n",)
    ),
    "match-arm-result": Position("""(let* ((door (gate 1)))
      (match door
        ((OPEN opened) {expr})
        ((SHUT shut) {seed})))""", decls=(GATE,), calls=("gate 1",)),
    "workflow-tail": Position("{expr}"),
}


# Cells where the form's type cannot occupy the position. They are not generated.
SKIPPED = {
    ("literal", "match-subject"): "Int is not a union",
    ("record", "match-subject"): "Box is a record, not a union",
    ("field-access", "match-subject"): "the field is an Int, not a union",
    ("command-call", "match-subject"): "the command returns a record, not a union",
    ("pure-match", "match-subject"): "the arms build a record, not a union",
}

# Codes that the typechecker reports for a restriction, with the place that raises
# each one (found by recording where each diagnostic of the matrix is created).
# Not listed, because they are raised after typecheck: `proc_ref_signature_invalid`
# (specialization discovery), `workflow_return_not_exportable` and
# `wcc_lowering_route_unsupported` (WCC defunctionalization, loop lowering) and
# `workflow_signature_mismatch` (call lowering).
RESTRICTION_CODES = frozenset({
    "effect_not_permitted",  # typecheck_dispatch._typecheck: record and variant fields must be pure
    "loop_recur_contract_invalid",  # typecheck_loop_recur: `:on-exhausted` must have an empty effect
    # summary, procedure-call edges included, so a call to an effect-free `defproc` is rejected too
    "workflow_boundary_type_invalid",  # workflows.build_workflow_catalog checks the declared
    # return type before any body is typechecked: no union inside a returned variant
})

# Typecheck rejects the cell: (form, position) -> code.
RULES = {
    ("plain-variant", "variant-field"): "workflow_boundary_type_invalid",
    ("generic-variant", "variant-field"): "workflow_boundary_type_invalid",
    ("defun-call", "variant-field"): "workflow_boundary_type_invalid",
    ("pure-proc-call", "variant-field"): "workflow_boundary_type_invalid",
    ("pure-proc-call", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("command-call", "record-field"): "effect_not_permitted",
    ("command-call", "variant-field"): "effect_not_permitted",
    ("command-call", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("imported-wrapper-call", "record-field"): "effect_not_permitted",
    ("imported-wrapper-call", "variant-field"): "workflow_boundary_type_invalid",
    ("imported-wrapper-call", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("generic-hook-call", "record-field"): "effect_not_permitted",
    ("generic-hook-call", "variant-field"): "workflow_boundary_type_invalid",
    ("generic-hook-call", "on-exhausted-value"): "loop_recur_contract_invalid",
}

# What each known defect is after the shared defect repairs (Tasks 2 to 9 merged):
# its kind, the symptom and where it is raised. Kinds: producer rule (decision brief
# section 3, consequence 1), pure projection (consequence 2 at compile time, in the
# older loop lowerer), pure-result replay (consequence 2 at run start; also reported
# by `--dry-run`), and position not claimed by the repairs.
DEFECTS = {
    "subject-producer": "producer rule: a union that no step produced is a `match` subject. A variant built "
    "without effects: workflow_return_not_exportable `requires case subjects to resolve to structured match "
    "bindings`; a pure call: wcc_lowering_route_unsupported `requires case subjects with stable producer step "
    "identities` (wcc/defunctionalize.py `_defunctionalize_case`)",
    "loop-call-argument": "producer rule: in a `loop/recur` body a command-backed procedure is lowered as a "
    "private-workflow call whose scalar arguments must be refs, and a literal argument has none: "
    "workflow_signature_mismatch (lowering/procedures.py `_lower_procedure_call`); the `let*`-bound form fails "
    "the same way",
    "done-call": "position not claimed: an effectful call as a `done` value: `TypeError: unsupported WCC "
    "elaboration node: ProcedureCallExpr` (wcc/elaborate.py `_elaborate_expr_to_value`, from the `DoneExpr` "
    "branch of `_elaborate_expr_to_body`)",
    "done-match": "position not claimed: a `match` as a `done` value: `TypeError: unsupported WCC elaboration "
    "node: MatchExpr` (wcc/elaborate.py, as done-call)",
    "continue-typed-state": "position not claimed: the `continue` typecheck handler keeps the authored state, "
    "so specialization discovery sees the unspecialized generic call and reports proc_ref_signature_invalid "
    "(procedure_refs.py `validate_proc_ref_value`); case c's cause at a second site",
    "loop-state-union": "pure projection: a union-typed `loop-state` field, however it was produced: "
    "`TypeError: unsupported pure projection expression: dict` (lowering/pure_projection.py "
    "`_payload_resolved_local_value`)",
    "loop-state-match": "pure projection: a `match` in a `loop-state` field: `TypeError: unsupported pure "
    "projection expression: MatchExpr` (lowering/pure_projection.py `_payload_expr`)",
    "on-exhausted-match": "pure projection: a `match` as the `:on-exhausted` value: workflow_return_not_exportable "
    "`could not project result__n from MatchExpr` (lowering/control_loops.py `_loop_projection_materialize_values`)",
    "replay-union-argument": "pure-result replay: a union procedure argument, literal or produced by a step: "
    "`pure replay union binding must have a literal variant` (workflow/pure_result_replay.py "
    "`_walk_typed_binding_value`)",
    "replay-frame-scope": "pure-result replay: a pure call in a `match` arm: `pure replay binding crosses the "
    "indexed frame scope` (workflow/pure_result_replay.py `_resolve_replay_ref`)",
    "d": "pure-result replay, case d: a pure `match` whose arms build a record, as a variant field or procedure "
    "argument: `pure replay binding references an unknown result member` (workflow/pure_result_replay.py "
    "`_validate_result_member`)",
}

# The cell typechecks and then fails: (form, position) -> a key of DEFECTS, the first
# defect the cell reaches. A comment names the defect found under it, where one was found
# by running the `let*`-bound form of the cell. Deleting a line here declares the cell working.
KNOWN_DEFECTS = {
    ("plain-variant", "match-subject"): "subject-producer",
    ("plain-variant", "loop-state-field"): "loop-state-union",
    ("plain-variant", "procedure-argument"): "replay-union-argument",
    ("generic-variant", "match-subject"): "subject-producer",
    ("generic-variant", "loop-state-field"): "loop-state-union",
    ("generic-variant", "procedure-argument"): "replay-union-argument",
    ("defun-call", "match-subject"): "subject-producer",
    ("defun-call", "loop-state-field"): "loop-state-union",
    ("defun-call", "procedure-argument"): "replay-union-argument",
    ("defun-call", "match-arm-result"): "replay-frame-scope",
    ("pure-proc-call", "match-subject"): "subject-producer",
    ("pure-proc-call", "loop-state-field"): "loop-state-union",
    ("pure-proc-call", "procedure-argument"): "replay-union-argument",
    ("pure-proc-call", "match-arm-result"): "replay-frame-scope",
    ("command-call", "loop-state-field"): "loop-call-argument",  # the case b repair itself holds for this shape
    ("command-call", "done-value"): "done-call",  # then loop-call-argument
    ("imported-wrapper-call", "loop-state-field"): "loop-state-union",  # then loop-call-argument
    ("imported-wrapper-call", "done-value"): "done-call",  # then loop-call-argument
    ("imported-wrapper-call", "procedure-argument"): "replay-union-argument",
    ("generic-hook-call", "loop-state-field"): "continue-typed-state",  # then loop-state-union
    ("generic-hook-call", "done-value"): "done-call",  # then the loop's output resolution fails at run time
    ("generic-hook-call", "procedure-argument"): "replay-union-argument",
    ("pure-match", "variant-field"): "d",
    ("pure-match", "loop-state-field"): "loop-state-match",
    ("pure-match", "done-value"): "done-match",  # then on-exhausted-match's projection failure
    ("pure-match", "on-exhausted-value"): "on-exhausted-match",
    ("pure-match", "procedure-argument"): "d",
}


def cells() -> list[tuple[str, str]]:
    return [(form, position) for form in FORMS for position in POSITIONS]


def program(form_name: str, position_name: str, probe: str) -> dict[str, str]:
    """The sources of one cell, keyed by path under the source root."""

    form, position = FORMS[form_name], POSITIONS[position_name]
    value_type = TYPES[form.type]
    fill = {"expr": form.expr, "type": form.type, "seed": value_type.seed, "arms": value_type.arms, "probe": probe}
    body = position.body.format(**fill)
    if form.prelude:
        body = f"(let* ({form.prelude})\n      " + body.replace("\n", "\n  ") + ")"
    decls = list(dict.fromkeys(decl.format(**fill) for decl in form.decls + position.decls))
    imports = [decl for decl in decls if decl.startswith("  (import")]
    entry = (
        HEADER
        + "  (defmodule grt/entry)\n"
        + "".join(imports)
        + "  (export run)\n"
        + "".join(decl for decl in decls if decl not in imports)
        + f"  (defworkflow run () -> {position.returns.format(**fill)}\n    {body}))\n"
    )
    sources = {"grt/entry.orc": entry}
    if form.lib:
        sources["grt/lib.orc"] = LIB.format(probe=probe)
    return sources


def expected(form_name: str, position_name: str) -> tuple[dict[str, object], list[str]]:
    """The workflow outputs and the ordered command log of a working cell."""

    form, position = FORMS[form_name], POSITIONS[position_name]
    value = {
        "match-subject": 7,
        "variant-field": {"variant": "HOLD", "v": form.value},
    }.get(position_name, form.value)
    outputs = _flatten("return", value) if isinstance(value, dict) else {"__result__": value}
    return outputs, [*form.prelude_calls, *position.calls, *form.calls]


def _flatten(prefix: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {prefix: value}
    flat: dict[str, object] = {}
    for key, item in value.items():
        flat.update(_flatten(f"{prefix}__{key}", item))
    return flat
