"""Generated programs and their classification for `tests/test_workflow_lisp_totality_matrix.py`.

One program per cell: form, position, helper locality (calls only), and target.
Original names retain target 2.33; `t234:` aliases select 2.34. `inline:` and
`imported:` vary the selected outer helper, preserving its effects and value.
Contract: docs/design/workflow_lisp_core_calculus_middle_end.md section 9
(elaboration totality: a program that passes typecheck elaborates, normalizes
and defunctionalizes; any restriction is a typecheck diagnostic that names it).
Case letters refer to docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
section 2.1.

Every effect is a command-backed procedure. All commands run one probe script,
which appends `<command> <arg>` to `probe.log`, so a test can assert the ordered
command log of the whole run.

Each form has one type. The calls that the brief's cases a and c are about
return unions, so they can be `match` subjects; the command-backed calls and
the pure `match` return a record, so that they reach cases b and d.

Each known-defect cell records how it fails (`KNOWN_DEFECTS`): exit code,
diagnostic code or exception type, and stage (`STAGES`). The test asserts it
before the cell counts as its defect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from tests import workflow_lisp_totality_matrix_extensions as regressions
from tests import workflow_lisp_totality_matrix_locality as locality

HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.33")\n'

PROBE = """import json, os, sys
from pathlib import Path
command, raw = sys.argv[1:3]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(f"{command} {raw}\\n")
if command == "step":
    payload = {"flag": True, "note": raw}
elif command in ("bump", "tick"):
    payload = int(raw) + (command == "bump")
else:
    n = int(raw)
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

COMMANDS = ("fetch", "find", "gate", "check", "bump", "tick", "step")

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
    read: str  # an Int read out of `held.v`, a value of the type


TYPES = {
    "Int": ValueType("0", None, "held.v"),
    "Float": ValueType("0.0", None, "held.v"),
    "Box": ValueType("(record Box :n 0)", None, "held.v.n"),
    "Pick": ValueType(
        "(variant Pick MISS :n 0)", "((HIT h) h.n) ((MISS m) m.n)", "(match held.v ((HIT h) h.n) ((MISS m) m.n))"
    ),
    "Maybe[Box]": ValueType(
        "(variant Maybe[Box] NONE :n 0)",
        "((SOME s) s.value.n) ((NONE z) z.n)",
        "(match held.v ((SOME s) s.value.n) ((NONE z) z.n))",
    ),
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
    # The same call with a non-literal argument: in a `loop/recur` body a literal argument
    # has no producing step, and that, not the position, fails `command-call/loop-state-field`.
    "command-call-field": Form(
        "Box", "(fetch src.n)", {"n": 7}, (BOX, FETCH), ("fetch 7",), prelude="(src (record Box :n 7))"
    ),
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


CARRY = "  (defunion Carry (HOLD (v {type})) (DROP (n Int)))\n"

# `record-field` reads the field back, so the workflow returns the form's type as
# `workflow-tail` does. `variant-field` reads the field back too and returns an Int
# taken from it. The variant is bound first and then passed through a `match` over a
# command result: that gives it a producing step, which a `match` subject needs
# (a variant that no step produced is the defect subject-producer). Returning the
# variant instead would measure the workflow return boundary, which rejects a union
# inside a returned variant (`RETURN_BOUNDARY_RULES`).
POSITIONS = {
    "let-binding": Position("(let* ((v {expr})) v)"),
    "match-subject": Position("(match {expr} {arms})", returns="Int"),
    "record-field": Position("(let* ((w (record Wrap :v {expr}))) w.v)", decls=("  (defrecord Wrap (v {type}))\n",)),
    "variant-field": Position("""(let* ((door (gate 1))
             (c (variant Carry HOLD :v {expr}))
             (k (match door ((OPEN o) c) ((SHUT s) (variant Carry DROP :n 0)))))
      (match k ((HOLD held) {read}) ((DROP d) d.n)))""", "Int", (CARRY, GATE), ("gate 1",)),
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

# Not a matrix position: the workflow returns the variant, so the workflow return
# boundary checks a union inside it. Measured by its own test.
RETURN_BOUNDARY = Position("(variant Carry HOLD :v {expr})", "Carry", (CARRY,))


# Cells where the form's type cannot occupy the position. They are not generated.
SKIPPED = {
    ("literal", "match-subject"): "Int is not a union",
    ("record", "match-subject"): "Box is a record, not a union",
    ("field-access", "match-subject"): "the field is an Int, not a union",
    ("command-call", "match-subject"): "the command returns a record, not a union",
    ("command-call-field", "match-subject"): "the command returns a record, not a union",
    ("pure-match", "match-subject"): "the arms build a record, not a union",
}

# Where a failure comes from. The test finds the frames where the failure started: the
# traceback of the exception that reached the run entry; for a diagnostic, the traceback
# of the exception being handled when it was created, or else the stack that created it.
# From the innermost frame outward, the first frame that contains a fragment names the
# stage; within one frame the first matching fragment wins.
STAGES = (
    ("/workflow_lisp/typecheck", "typecheck"),
    ("/workflow_lisp/workflows.py:build_workflow_catalog", "workflow signature"),  # before any body is typechecked
    ("/workflow_lisp/procedure_specialization.py:", "specialization"),
    ("/workflow_lisp/wcc/elaborate.py:", "elaboration"),
    ("/workflow_lisp/wcc/defunctionalize.py:", "defunctionalization"),
    # the lowered workflow fails shared validation, which lowering remaps to a diagnostic
    ("/workflow_lisp/lowering/origins.py:_remapped_shared_validation_diagnostic", "shared validation"),
    ("/workflow_lisp/lowering/", "lowering"),
    ("/workflow/pure_result_replay.py:", "replay index at run start"),  # `--dry-run` builds it too
    ("/workflow/steps/pure_projection.py:", "runtime pure projection"),
)

# Codes that the typechecker reports for a restriction, with the place that raises each one.
# A rule cell must also fail in the typecheck stage: some of these codes are raised later too.
RESTRICTION_CODES = frozenset({
    "effect_not_permitted",  # typecheck_dispatch._typecheck: record and variant fields must be pure
    "loop_recur_contract_invalid",  # typecheck_loop_recur: the `:on-exhausted` value must be pure
})

# Typecheck rejects the cell: (form, position) -> code. Each form here has a real effect:
# the same command written inline with `command-result`, without a procedure call, is
# rejected with the same code in the same position.
RULES = {
    ("command-call", "record-field"): "effect_not_permitted",
    ("command-call", "variant-field"): "effect_not_permitted",
    ("command-call", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("command-call-field", "record-field"): "effect_not_permitted",
    ("command-call-field", "variant-field"): "effect_not_permitted",
    ("command-call-field", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("imported-wrapper-call", "record-field"): "effect_not_permitted",
    ("imported-wrapper-call", "variant-field"): "effect_not_permitted",
    ("imported-wrapper-call", "on-exhausted-value"): "loop_recur_contract_invalid",
    ("generic-hook-call", "record-field"): "effect_not_permitted",
    ("generic-hook-call", "variant-field"): "effect_not_permitted",
    ("generic-hook-call", "on-exhausted-value"): "loop_recur_contract_invalid",
}

# The workflow return boundary rejects a union inside a returned variant, whatever the body:
# form -> (code, stage), for the program `program(form, "return-boundary", probe)`.
RETURN_BOUNDARY_RULES = {
    "plain-variant": ("workflow_boundary_type_invalid", "workflow signature"),
    "generic-variant": ("workflow_boundary_type_invalid", "workflow signature"),
}

# Each known defect: a fragment of the logged failure that identifies it, and what it is.
# Kinds: producer rule (decision brief section 3, consequence 1), pure projection
# (consequence 2 at compile time, in the older loop lowerer), pure-result replay
# (consequence 2 at run start), position not claimed by the repairs, and typecheck
# restriction wrongly applied.
DEFECTS = {
    "subject-producer": ("WCC M3 lowering requires case subjects", "producer rule: a union that no step "
        "produced is a `match` subject. A variant built without effects: workflow_return_not_exportable; a pure "
        "call: wcc_lowering_route_unsupported (wcc/defunctionalize.py `_defunctionalize_case`)"),
    "loop-call-argument": ("Stage 3 lowering requires same-file call bindings to resolve to workflow inputs",
        "producer rule: in a `loop/recur` body a command-backed procedure is lowered as a private-workflow call "
        "whose scalar arguments must be refs; a literal, or a field of a record literal bound by `let*`, has none "
        "(lowering/workflow_calls.py `_render_call_binding_leaf_ref`)"),
    "done-call": ("unsupported WCC elaboration node: ProcedureCallExpr", "position not claimed: an effectful call "
        "as a `done` value (wcc/elaborate.py `_elaborate_expr_to_value`, from the `DoneExpr` branch)"),
    "done-match": ("unsupported WCC elaboration node: MatchExpr", "position not claimed: a `match` as a `done` "
        "value (wcc/elaborate.py, as done-call)"),
    "continue-typed-state": ("does not match `ProcRef", "position not claimed: the `continue` typecheck handler "
        "keeps the authored state, so specialization discovery sees the unspecialized generic call and reports "
        "proc_ref_signature_invalid (procedure_refs.py `validate_proc_ref_value`); case c's cause at a second site"),
    "loop-state-union": ("unsupported pure projection expression: dict", "pure projection: a union-typed "
        "`loop-state` field, however it was produced (lowering/pure_projection.py `_payload_resolved_local_value`)"),
    "loop-state-match": ("unsupported pure projection expression: MatchExpr", "pure projection: a `match` in a "
        "`loop-state` field (lowering/pure_projection.py `_payload_expr`)"),
    "on-exhausted-match": ("could not project `result__n` from `MatchExpr`", "pure projection: a `match` as the "
        "`:on-exhausted` value (lowering/control_loops.py `_loop_projection_materialize_values`)"),
    "nested-union-result": ("cannot appear inside a collection-valued structured result", "a union inside a "
        "variant: the result contract of the step that carries the variant cannot hold it, and the message wrongly "
        "speaks of a collection (contracts.py `_structured_result_field_definition`, from lowering/control_match.py). "
        "No route reads such a field back today: returned, the workflow boundary rejects it "
        "(RETURN_BOUNDARY_RULES); matched with no producing step, subject-producer"),
    "replay-union-argument": ("pure replay union binding must have a literal variant", "pure-result replay: a "
        "union procedure argument, literal or produced by a step (workflow/pure_result_replay.py)"),
    "replay-frame-scope": ("pure replay binding crosses the indexed frame scope", "pure-result replay: a pure "
        "call in a `match` arm (workflow/pure_result_replay.py `_resolve_replay_ref`)"),
    "d": ("pure replay binding references an unknown result member", "pure-result replay, case d: a pure "
        "`match` whose arms build a record, as a variant field or procedure argument "
        "(workflow/pure_result_replay.py `_validate_result_member`)"),
    "on-exhausted-call-edge": ("`loop/recur` exhaustion projection must be pure", "typecheck restriction wrongly "
        "applied: the `:on-exhausted` check compares the whole effect summary, procedure-call edges included, "
        "with the empty summary, so a call to a `defproc` declared `:effects ()` is rejected; the variant it "
        "returns, written directly, compiles (typecheck_loop_recur.py `typecheck_loop_recur_expr`)"),
}


@dataclass(frozen=True)
class Defect:
    """How a known-defect cell fails today; the test asserts all of it before it counts the cell."""

    label: str  # a key of DEFECTS
    exit_code: int
    kind: str  # the first diagnostic code logged, or else the type of the exception that reached the run entry
    stage: str  # a stage of STAGES


# The cell typechecks, or is wrongly rejected by typecheck, and then fails: (form, position)
# -> the first defect it reaches. A comment names the defect found under it, where one was
# found by running the `let*`-bound form of the cell. Deleting a line declares the cell working.
# An internal exception after typecheck is reported as exit 2 with code `compiler_defect`.
KNOWN_DEFECTS = {
    ("plain-variant", "match-subject"): Defect("subject-producer", 2, "workflow_return_not_exportable", "defunctionalization"),
    ("plain-variant", "variant-field"): Defect("nested-union-result", 2, "collection_element_type_unsupported", "lowering"),
    ("plain-variant", "loop-state-field"): Defect("loop-state-union", 2, "compiler_defect", "lowering"),
    ("plain-variant", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("generic-variant", "match-subject"): Defect("subject-producer", 2, "workflow_return_not_exportable", "defunctionalization"),
    ("generic-variant", "variant-field"): Defect("nested-union-result", 2, "collection_element_type_unsupported", "lowering"),
    ("generic-variant", "loop-state-field"): Defect("loop-state-union", 2, "compiler_defect", "lowering"),
    ("generic-variant", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("defun-call", "match-subject"): Defect("subject-producer", 2, "wcc_lowering_route_unsupported", "defunctionalization"),
    ("defun-call", "variant-field"): Defect("nested-union-result", 2, "collection_element_type_unsupported", "lowering"),
    ("defun-call", "loop-state-field"): Defect("loop-state-union", 2, "compiler_defect", "lowering"),
    ("defun-call", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("defun-call", "match-arm-result"): Defect("replay-frame-scope", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("pure-proc-call", "match-subject"): Defect("subject-producer", 2, "wcc_lowering_route_unsupported", "defunctionalization"),
    ("pure-proc-call", "variant-field"): Defect("nested-union-result", 2, "collection_element_type_unsupported", "lowering"),
    ("pure-proc-call", "loop-state-field"): Defect("loop-state-union", 2, "compiler_defect", "lowering"),
    ("pure-proc-call", "on-exhausted-value"): Defect("on-exhausted-call-edge", 2, "loop_recur_contract_invalid", "typecheck"),
    ("pure-proc-call", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("pure-proc-call", "match-arm-result"): Defect("replay-frame-scope", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("command-call", "loop-state-field"): Defect("loop-call-argument", 2, "workflow_signature_mismatch", "lowering"),
    ("command-call", "done-value"): Defect("done-call", 2, "compiler_defect", "elaboration"),  # then loop-call-argument
    ("command-call-field", "loop-state-field"): Defect("loop-call-argument", 2, "workflow_signature_mismatch", "lowering"),
    ("command-call-field", "done-value"): Defect("done-call", 2, "compiler_defect", "elaboration"),
    ("imported-wrapper-call", "loop-state-field"): Defect("loop-state-union", 2, "compiler_defect", "lowering"),  # then loop-call-argument
    ("imported-wrapper-call", "done-value"): Defect("done-call", 2, "compiler_defect", "elaboration"),  # then loop-call-argument
    ("imported-wrapper-call", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("generic-hook-call", "loop-state-field"): Defect("continue-typed-state", 2, "proc_ref_signature_invalid", "specialization"),  # then loop-state-union
    ("generic-hook-call", "done-value"): Defect("done-call", 2, "compiler_defect", "elaboration"),  # then output resolution fails at run time
    ("generic-hook-call", "procedure-argument"): Defect("replay-union-argument", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("pure-match", "variant-field"): Defect("d", 2, "pure_result_replay_unavailable", "replay index at run start"),
    ("pure-match", "loop-state-field"): Defect("loop-state-match", 2, "compiler_defect", "lowering"),
    ("pure-match", "done-value"): Defect("done-match", 2, "compiler_defect", "elaboration"),  # then on-exhausted-match
    ("pure-match", "on-exhausted-value"): Defect("on-exhausted-match", 2, "workflow_return_not_exportable", "lowering"),
    ("pure-match", "procedure-argument"): Defect("d", 2, "pure_result_replay_unavailable", "replay index at run start"),
}


def cells() -> list[tuple[str, str]]:
    return locality.expanded_cells(FORMS, POSITIONS) + locality.regression_cells(regressions.cells())


def program(form_name: str, position_name: str, probe: str) -> dict[str, str]:
    """The sources of one cell, keyed by path under the source root.

    `position_name` is a key of POSITIONS, or "return-boundary" for RETURN_BOUNDARY.
    """

    target, _, base = locality.axes(form_name)
    if base.startswith("repro:"):
        return locality.regression_sources(form_name, probe, regressions.program)
    form = locality.form_value(form_name, FORMS, probe)
    position = RETURN_BOUNDARY if position_name == "return-boundary" else POSITIONS[position_name]
    if form.type == "Float" and position_name == "variant-field":
        position = replace(position, returns="Float", body=position.body.replace("((DROP d) d.n)", "((DROP d) 0.0)"))
    value_type = TYPES[form.type]
    fill = {
        "expr": form.expr, "type": form.type, "seed": value_type.seed, "arms": value_type.arms,
        "read": value_type.read, "probe": probe,
    }
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
    sources.update(locality.additional_sources(form_name, FORMS, HEADER, probe))
    return locality.retarget(sources, target)


def expected(form_name: str, position_name: str) -> tuple[dict[str, object], list[str]]:
    """The workflow outputs and the ordered command log of a working cell."""

    _, _, base = locality.axes(form_name)
    if base.startswith("repro:"):
        return regressions.expected(base)
    form, position = locality.form_value(form_name, FORMS, "probe.py"), POSITIONS[position_name]
    value = form.value if form.type == "Float" else 7 if position_name in ("match-subject", "variant-field") else form.value
    outputs = _flatten("return", value) if isinstance(value, dict) else {"__result__": value}
    return outputs, [*form.prelude_calls, *position.calls, *form.calls]


def _flatten(prefix: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {prefix: value}
    flat: dict[str, object] = {}
    for key, item in value.items():
        flat.update(_flatten(f"{prefix}__{key}", item))
    return flat


DEFECTS.update(locality.DEFECT_DETAILS)
locality.add_classifications(cells(), RULES, KNOWN_DEFECTS, SKIPPED, Defect)
