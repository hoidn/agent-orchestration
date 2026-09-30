"""Target and helper-locality axes, keeping the matrix's two-string cell API.

Locality moves or substitutes the selected outer helper. For `lookup` and
`attempt`, its underlying `find`/`check` effect procedure stays the same.
Classifications below were measured through the public run entry at both targets.
"""

from dataclasses import replace


CALL_FORMS = (
    "defun-call", "pure-proc-call", "command-call", "command-call-field",
    "imported-wrapper-call", "generic-hook-call",
)
NUMERIC_FORMS = ("decimal-literal", "float-operator")
REGRESSION_HELPERS = {
    "repro:nested-effectful-argument": "bump",
    "repro:pure-helper-exhaustion": "result",
    "repro:pure-helper-exhaustion-top-level": "result",
    "repro:scalar-call-loop-state": "tick",
}
EXPORTS = {
    "defun-call": ("Pick", "hit"),
    "pure-proc-call": ("Pick", "make-hit"),
    "command-call": ("Box", "fetch"),
    "command-call-field": ("Box", "fetch"),
    "imported-wrapper-call": ("lookup",),
    "generic-hook-call": ("Box", "Maybe", "check", "attempt"),
}

DEFECT_DETAILS = {
    "done-command": ("unsupported WCC elaboration node: CommandResultExpr",
                     "a command result as a done value is not elaborated"),
    "nested-call-argument": ("unsupported WCC elaboration node: ProcedureCallExpr",
                             "an effectful procedure argument is not elaborated"),
    "nested-command-argument": ("unsupported WCC elaboration node: CommandResultExpr",
                                "an inline command argument is not elaborated"),
    "on-exhausted-float": ("could not project `result` from `PureOpExpr`",
                           "a Float operator as the exhaustion value is not projected"),
    "record-if-runtime": ("binding node references unknown binding",
                          "a record if bound in a procedure in a loop produces an invalid runtime payload"),
    "list-if-binding": ("Stage 3 lowering does not support let* binding `IfExpr`",
                        "a list if bound in an inline procedure is not lowered"),
    "nested-loop": ("structured repeat_until is only supported on top-level steps",
                    "a loop inside an if branch fails shared validation"),
    "scalar-private-workflow": ("AssertionError",
                                "a scalar-returning procedure in loop state hits the private-workflow assertion"),
}

REPRO_FAILURES = {
    "repro:if-record-loop": ("record-if-runtime", 1, "pure_expr_payload_invalid", "runtime pure projection"),
    "repro:if-list-loop": ("list-if-binding", 2, "workflow_return_not_exportable", "lowering"),
    "repro:nested-effectful-argument": ("nested-call-argument", 2, "compiler_defect", "elaboration"),
    "repro:pure-helper-exhaustion": ("nested-loop", 2, "workflow_boundary_type_invalid", "shared validation"),
    "repro:call-result-in-if": ("replay-frame-scope", 2, "pure_result_replay_unavailable", "replay index at run start"),
    "repro:scalar-call-loop-state": ("scalar-private-workflow", 1, "AssertionError", "lowering"),
}


def axes(name: str) -> tuple[str, str, str]:
    target = "2.34" if name.startswith("t234:") else "2.33"
    name = name.removeprefix("t234:")
    locality, separator, base = name.partition(":")
    if separator and locality in ("inline", "imported"):
        return target, locality, base
    return target, "same-module", name


def expanded_cells(forms, positions) -> list[tuple[str, str]]:
    base = [(form, position) for form in forms for position in positions]
    localized = [(f"{locality}:{form}", position) for form in CALL_FORMS
                 for locality in ("inline", "imported") for position in positions]
    return [*base, *localized,
            *(("t234:" + form, position) for form, position in [*base, *localized]),
            *(("t234:" + form, position) for form in NUMERIC_FORMS for position in positions)]


def form_value(name, forms, probe):
    _, locality, base = axes(name)
    if base in NUMERIC_FORMS:
        expr = "7.5" if base == "decimal-literal" else "(+ 3.0 4.5)"
        return replace(forms["literal"], type="Float", expr=expr, value=7.5)
    form = forms[base]
    if locality == "same-module":
        return form
    if locality == "imported":
        imports = ("  (import grt/helper :only (" + " ".join(EXPORTS[base]) + "))\n",)
        if base == "imported-wrapper-call":
            imports = (form.decls[0], *imports)
        return replace(form, decls=imports)
    if base in ("defun-call", "pure-proc-call"):
        return replace(form, expr="(variant Pick HIT :n 7)", decls=form.decls[:1])
    if base in ("command-call", "command-call-field"):
        arg = "7" if base == "command-call" else "src.n"
        expr = f'(command-result fetch :argv ("python" "{probe}" "fetch" {arg}) :returns Box)'
        return replace(form, expr=expr, decls=form.decls[:1])
    if base == "imported-wrapper-call":
        return replace(form, expr="(find 7)", decls=form.decls[:1])
    return replace(form, expr="(check (record Box :n 7))",
                   decls=(*form.decls[:2], form.decls[2].split("  (defproc attempt", 1)[0]))


def additional_sources(name, forms, header, probe):
    _, locality, base = axes(name)
    if locality != "imported":
        return {}
    decls = forms[base].decls
    imports = "".join(decl for decl in decls if decl.startswith("  (import"))
    definitions = "".join(decl for decl in decls if not decl.startswith("  (import"))
    source = (header + "  (defmodule grt/helper)\n" + imports
              + "  (export " + " ".join(EXPORTS[base]) + ")\n" + definitions + ")\n")
    return {"grt/helper.orc": source.format(probe=probe)}


def retarget(sources, target):
    return {path: text.replace('(:target-dsl "2.33")', f'(:target-dsl "{target}")')
            for path, text in sources.items()}


def regression_cells(original):
    localized = [(f"{locality}:{form}", position) for form, position in original
                 if form in REGRESSION_HELPERS for locality in ("inline", "imported")]
    return [*original, *localized,
            *(("t234:" + form, position) for form, position in [*original, *localized])]


def regression_sources(name, probe, render):
    target, locality, base = axes(name)
    sources = render(base, probe)
    if locality == "same-module":
        return retarget(sources, target)
    source = sources["grt/entry.orc"]
    helper = REGRESSION_HELPERS[base]
    start = source.index("  (defun result" if helper == "result" else f"  (defproc {helper}")
    end = source.index("  (defproc fetch" if helper == "bump" else "  (defworkflow run", start)
    definition = source[start:end]
    source = source[:start] + source[end:]
    if locality == "inline":
        if helper == "result":
            for status in ("loop_bound_exhausted", "done"):
                source = source.replace(f'(result state "{status}")',
                                        f'(record Result :turn state.turn :status "{status}")')
        else:
            arg = "26" if helper == "bump" else "1"
            source = source.replace(f"({helper} {arg})",
                f'(command-result {helper} :argv ("python" "{probe}" "{helper}" {arg}) :returns Int)')
    else:
        exports = helper
        if helper == "result":
            start = source.index("  (defrecord State")
            end = source.index("  (defworkflow run", start)
            definition = source[start:end] + definition
            source = source[:start] + source[end:]
            exports = "State Result result"
        header = source.split("  (defmodule grt/entry)", 1)[0]
        sources["grt/helper.orc"] = header + "  (defmodule grt/helper)\n  (export " + exports + ")\n" + definition + ")\n"
        source = source.replace("  (export run)", f"  (import grt/helper :only ({exports}))\n  (export run)")
    sources["grt/entry.orc"] = source
    return retarget(sources, target)


def _reproducer_failure(base, locality, defect_type):
    if base not in REPRO_FAILURES or (base == "repro:scalar-call-loop-state" and locality == "inline"):
        return None
    defect = defect_type(*REPRO_FAILURES[base])
    if base == "repro:nested-effectful-argument" and locality == "inline":
        defect = replace(defect, label="nested-command-argument")
    return defect


def _localized_failure(base, position, locality, original, defect_type):
    source = "plain-variant" if locality == "inline" and base in ("defun-call", "pure-proc-call") else base
    if locality == "inline" and base in ("command-call", "command-call-field"):
        return defect_type("done-command", 2, "compiler_defect", "elaboration") if position == "done-value" else None
    if locality == "inline" and base == "generic-hook-call" and position == "loop-state-field":
        return original["plain-variant", "loop-state-field"]
    return original.get((source, position))


def add_classifications(cells, rules, defects, skipped, defect_type):
    """Expand the measured equalities; keep exceptions explicit and failures strict."""
    original_rules, original_defects, original_skipped = dict(rules), dict(defects), dict(skipped)
    for form, position in cells:
        _, locality, base = axes(form)
        key = (base, position)
        if base in NUMERIC_FORMS:
            if position == "match-subject":
                skipped[form, position] = "Float is not a union"
            if base == "float-operator" and position == "on-exhausted-value":
                defects[form, position] = defect_type("on-exhausted-float", 2, "workflow_return_not_exportable", "lowering")
            continue
        if base.startswith("repro:"):
            failure = _reproducer_failure(base, locality, defect_type)
            if failure is not None:
                defects[form, position] = failure
            continue
        if key in original_skipped:
            skipped[form, position] = original_skipped[key]
        if key in original_rules:
            rules[form, position] = original_rules[key]
        failure = _localized_failure(base, position, locality, original_defects, defect_type)
        if failure is not None:
            defects[form, position] = failure
