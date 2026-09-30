"""Verbosity census over the Workflow Lisp corpus.

Run from the orc-shared-repairs worktree root:
  PYTHONPATH=$PWD PYTHONDONTWRITEBYTECODE=1 python experiments/orc_repetition_census/census.py [--sites]

Parses every corpus file with orchestrator.workflow_lisp.reader.read_sexpr_text
and counts by form (not by text search).
"""
import collections
import json
import pathlib
import re
import sys

from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom, SymbolAtom

ROOT = pathlib.Path.cwd()


def corpus():
    files = sorted(ROOT.glob("workflows/examples/**/*.orc"))
    files += sorted(p for p in ROOT.glob("workflows/library/**/*.orc") if "lisp_frontend_design_delta" not in p.parts)
    files += sorted(ROOT.glob("experiments/orc_vs_single_call/workflows/**/*.orc"))
    files += sorted(ROOT.glob("orchestrator/workflow_lisp/stdlib_modules/**/*.orc"))
    return [p.relative_to(ROOT).as_posix() for p in files]


def hd(e):
    if isinstance(e, ListExpr) and e.items and isinstance(e.items[0], SymbolAtom):
        return e.items[0].value
    return None


def sym(e):
    return e.value if isinstance(e, (SymbolAtom, KeywordAtom)) else None


def kwargs(items):
    """Map :keyword -> following item for a flat keyword/value tail."""
    out, i = {}, 0
    while i < len(items):
        if isinstance(items[i], KeywordAtom) and i + 1 < len(items):
            out[items[i].value] = items[i + 1]
            i += 2
        else:
            i += 1
    return out


def code_lines(text):
    return {n for n, line in enumerate(text.splitlines(), 1) if line.strip() and not line.strip().startswith(";")}


def base(t):
    return t.split("[", 1)[0].rsplit("/", 1)[-1]


def is_typevar(t, tvars):
    return base(t) in tvars


# ---------------------------------------------------------------- parse corpus
FILES = {}
for f in corpus():
    text = (ROOT / f).read_text()
    root = read_sexpr_text(text, source_path=f)
    wl = root.items[0]
    FILES[f] = dict(text=text, forms=list(wl.items[1:]), lines=code_lines(text))

# Global declaration tables (keyed by bare name; collisions recorded).
RECORDS, UNIONS, PROCS, MACROS, MODULE_OF = {}, {}, {}, {}, {}
for f, d in FILES.items():
    mod = None
    for form in d["forms"]:
        h = hd(form)
        if h == "defmodule":
            mod = sym(form.items[1])
            MODULE_OF[f] = mod
        elif h == "defrecord":
            RECORDS.setdefault(sym(form.items[1]), []).append(
                dict(file=f, module=mod, fields={sym(x.items[0]): sym(x.items[1]) for x in form.items[2:] if isinstance(x, ListExpr)}))
        elif h == "defunion":
            tvars, rest = [], form.items[2:]
            if rest and sym(rest[0]) == ":forall":
                tvars = [sym(x) for x in rest[1].items]
                rest = rest[2:]
            variants = {}
            for v in rest:
                if isinstance(v, ListExpr):
                    variants[sym(v.items[0])] = [(sym(x.items[0]), sym(x.items[1])) for x in v.items[1:]]
            UNIONS.setdefault(sym(form.items[1]), []).append(
                dict(file=f, module=mod, tvars=tvars, variants=variants, line=form.span.start.line))
        elif h in ("defproc", "defworkflow", "defun"):
            items = form.items[2:]
            tvars, params = [], None
            for i, it in enumerate(items):
                if sym(it) == ":forall":
                    tvars = [sym(x) for x in items[i + 1].items]
                if isinstance(it, ListExpr) and params is None and (i == 0 or sym(items[i - 1]) != ":forall"):
                    params = [(sym(p.items[0]), sym(p.items[1])) for p in it.items]
            PROCS.setdefault(sym(form.items[1]), []).append(dict(file=f, module=mod, tvars=tvars, params=params))
        elif h == "defmacro":
            MACROS[sym(form.items[1])] = f


def decl_sig(form):
    """Split a defproc/defworkflow/defun into header keyword map and body."""
    items = form.items[2:]
    header, i = {}, 0
    while i < len(items) - 1:
        it = items[i]
        if isinstance(it, KeywordAtom):
            header[it.value] = items[i + 1]
            i += 2
        elif sym(it) == "->":
            header["->"] = items[i + 1]
            i += 2
        else:
            i += 1
    return header, items[-1]


def pick(decls, f, tname):
    """Prefer the declaration in the same file, then the module named by a qualifier."""
    if not decls:
        return None
    mod = tname.split("[", 1)[0].rsplit("/", 1)[0] if "/" in tname.split("[", 1)[0] else None
    for d in decls:
        if d["file"] == f:
            return d
    for d in decls:
        if mod and d["module"] == mod:
            return d
    return decls[0]


def field_type(tname, field, variant=None, f=None):
    b = base(tname)
    if variant is None:
        d = pick(RECORDS.get(b), f, tname)
        return (d["fields"].get(field) if d else None), ()
    d = pick(UNIONS.get(b), f, tname)
    if not d:
        return None, ()
    return dict(d["variants"].get(variant, [])).get(field), tuple(d["tvars"])


# ---------------------------------------------------------------- constructor sites
SITES = []


IN_MACRO = [False]


def P(kind, fixed, via=None, arm=False, loop=None, expected=None, reach=None):
    """reach: does today's typechecker pass an expected type into this position?
    True/False per the typecheck_dispatch/procedure_typecheck reading; None = not checked."""
    return dict(kind=kind, fixed=fixed, via=via, arm=arm, loop=loop, expected=expected, reach=reach)


def site(e, pos, f):
    h = hd(e)
    tname = sym(e.items[1])
    SITES.append(dict(file=f, line=e.span.start.line, ctor=h, type=tname,
                      variant=sym(e.items[2]) if h == "variant" else None,
                      kind=pos["kind"], fixed=pos["fixed"], via=pos["via"], arm=pos["arm"], reach=pos["reach"],
                      in_macro=IN_MACRO[0], chars=len(tname)))
    rest = e.items[3:] if h == "variant" else e.items[2:]
    vname = sym(e.items[2]) if h == "variant" else None
    for k, v in kwargs(rest).items():
        ft, tvars = field_type(tname, k[1:], vname, f)
        fixed = ft is not None and not is_typevar(ft, tvars)
        visit(v, P("constructor field", fixed, via=f"field {k} : {ft}", expected=ft, reach=True), f)


def visit(e, pos, f):
    if not isinstance(e, ListExpr) or not e.items:
        return
    h = hd(e)
    items = e.items
    other = lambda tag: P(f"other: {tag}", False)
    if h in ("record", "variant") and len(items) >= 2 and isinstance(items[1], SymbolAtom):
        site(e, pos, f)
        return
    if h == "let*":
        for b in items[1].items:
            visit(b.items[1], P("let* binding", False, via="no annotation on let* bindings", reach=False), f)
        for x in items[2:]:
            visit(x, dict(pos, reach=False), f)  # let* body drops expected_type (typecheck_dispatch.py:914-921)
        return
    if h == "match":
        visit(items[1], other("match subject"), f)
        for arm in items[2:]:
            for x in arm.items[1:]:
                visit(x, dict(pos, arm=True), f)
        return
    if h in ("if",):
        visit(items[1], other("if condition"), f)
        for x in items[2:]:
            visit(x, dict(pos, arm=True), f)
        return
    if h == "cond":
        for clause in items[1:]:
            visit(clause.items[0], other("cond test"), f)
            for x in clause.items[1:]:
                visit(x, dict(pos, arm=True), f)
        return
    if h in ("with-phase", "__with-phase__"):
        visit(items[-1], dict(pos, reach=False), f)  # typecheck_dispatch.py:1077
        return
    if h == "loop/recur":
        kw = kwargs(items[1:])
        loop = dict(fixed=pos["fixed"], kind=pos["kind"], state=kw.get(":state"))
        if ":on-exhausted" in kw:
            visit(kw[":on-exhausted"], P("on-exhausted", pos["fixed"], via=f"loop in {pos['kind']}", arm=False, reach=False), f)
        st = kw.get(":state")
        if st is not None:
            if hd(st) == "loop-state":
                for decl in st.items[1:]:
                    if isinstance(decl, ListExpr):
                        visit(decl.items[-1], P("other: loop-state init", True, via=f"declared {sym(decl.items[1])}", reach=True), f)
            else:
                visit(st, dict(other("loop :state initial value"), reach=False), f)
        fn = items[-1]
        if hd(fn) == "fn":
            for x in fn.items[2:]:
                visit(x, dict(pos, loop=loop), f)
        return
    if h == "fn":
        for x in items[2:]:
            visit(x, pos, f)
        return
    if h == "done":
        loop = pos.get("loop") or {}
        visit(items[1], P("done", loop.get("fixed", False), via=f"loop in {loop.get('kind')}", reach=False), f)
        return
    if h == "continue":
        loop = pos.get("loop") or {}
        st = loop.get("state")
        declared = st is not None and hd(st) == "loop-state"
        visit(items[1], P("other: continue value", declared,
                          via="loop-state declared types" if declared else "type set by :state constructor, not a declaration", reach=False), f)
        return
    if h == "loop-state":
        # (loop-state :like state :field v)
        for k, v in kwargs(items[1:]).items():
            if k != ":like":
                visit(v, P("other: loop-state field update", True, via="loop-state declaration", reach=True), f)
        return
    if h == "list":
        exp = pos.get("expected")
        m = re.match(r"^List\[(.+)\]$", exp or "")
        for x in items[1:]:
            visit(x, P("other: list element", bool(m), via=f"element of {exp}"), f)
        return
    if h == "resource-transition":
        for k, v in kwargs(items[1:]).items():
            visit(v, P(f"other: resource-transition {k}", k == ":request", via="deftransition :request-type" if k == ":request" else None), f)
        return
    if h == "materialize-view":
        for k, v in kwargs(items[2:]).items():
            visit(v, other(f"materialize-view {k}"), f)
        return
    if h == "call":
        callee = pick(PROCS.get(base(sym(items[1]))), f, sym(items[1]))
        params = dict(callee["params"]) if callee else {}
        tvars = callee["tvars"] if callee else []
        for k, v in kwargs(items[2:]).items():
            t = params.get(k[1:])
            visit(v, P("call argument", t is not None and not is_typevar(t, tvars), via=f"param {k} : {t}", expected=t, reach=True), f)
        return
    if h in ("provider-result", "command-result"):
        for x in items[1:]:
            visit(x, other(h), f)
        return
    if h is not None and base(h) in PROCS:
        callee = pick(PROCS[base(h)], f, h)
        for i, x in enumerate(items[1:]):
            t = callee["params"][i][1] if callee["params"] and i < len(callee["params"]) else None
            visit(x, P("call argument", t is not None and not is_typevar(t, callee["tvars"]), via=f"param #{i} : {t}", expected=t,
                       reach=not callee["tvars"]), f)  # generic calls type args first (procedure_typecheck.py:700)
        return
    if h is not None and base(h) in MACROS:
        for x in items[1:]:
            visit(x, other(f"macro argument ({h})"), f)
        return
    for x in items[1:]:
        visit(x, other(h or "list"), f)


for f, d in FILES.items():
    for form in d["forms"]:
        h = hd(form)
        if h in ("defproc", "defworkflow", "defun"):
            header, body = decl_sig(form)
            visit(body, P("tail", True, via=f"declared -> {sym(header.get('->'))}", reach=True), f)
        elif h == "defmacro":
            IN_MACRO[0] = True
            visit(form.items[-1], P("other: macro template", False), f)
            IN_MACRO[0] = False
        elif h == "deftransition":
            kw = kwargs(form.items[2:])
            for k in (":result", ":audit"):
                if k in kw:
                    visit(kw[k], P(f"other: deftransition {k}", k == ":result",
                                   via="deftransition :result-type" if k == ":result" else "no audit type declared"), f)


# ---------------------------------------------------------------- per-file metrics
CATS = ["header/imports", "defrecord", "defunion", "defpath", "defenum", "defprompt", "defun", "defproc", "defworkflow", "other"]


def form_cat(h):
    if h in (":language", ":target-dsl", "defmodule", "import", "export"):
        return "header/imports"
    return h if h in CATS else "other"


def lines_of(e, code):
    return {n for n in range(e.span.start.line, e.span.end.line + 1)} & code


rows = []
effects, lowering, where, forall, lowering_sites = [], collections.Counter(), [], [], []
provider_calls = collections.defaultdict(list)
for f, d in FILES.items():
    code = d["lines"]
    per = collections.Counter()
    covered = set()
    target = None
    for form in d["forms"]:
        h = hd(form) or sym(form.items[0])
        if h == ":target-dsl":
            target = form.items[1].value
        ls = lines_of(form, code) - covered
        covered |= ls
        per[form_cat(h)] += len(ls)
        if h in ("defproc", "defworkflow", "defun", "defunion"):
            items = form.items
            for i, it in enumerate(items):
                if not isinstance(it, KeywordAtom):
                    continue
                if it.value == ":effects":
                    val = items[i + 1]
                    effects.append(dict(file=f, line=it.span.start.line, form=h, name=sym(items[1]),
                                        nlines=val.span.end.line - it.span.start.line + 1, empty=not val.items,
                                        entries=len(val.items)))
                elif it.value == ":lowering":
                    lowering[sym(items[i + 1])] += 1
                    lowering_sites.append(dict(file=f, line=it.span.start.line, name=sym(items[1]), value=sym(items[i + 1])))
                elif it.value == ":where":
                    where.append(dict(file=f, line=it.span.start.line, name=sym(items[1]),
                                      clauses=[" ".join(sym(x) or "(..)" for x in c.items[1:2]) for c in items[i + 1].items],
                                      kinds=collections.Counter(sym(c.items[1]) for c in items[i + 1].items)))
                elif it.value == ":forall":
                    forall.append(dict(file=f, line=it.span.start.line, form=h, name=sym(items[1]),
                                       vars=[sym(x) for x in items[i + 1].items]))
    per["header/imports"] += len(code - covered)  # wrapper line and closing parens
    rows.append(dict(file=f, target=target, code=len(code), **{c: per[c] for c in CATS}))

    def pr(e):
        if isinstance(e, ListExpr):
            if hd(e) == "provider-result":
                kw = kwargs(e.items[2:])
                provider_calls[f].append(dict(line=e.span.start.line, provider=sym(e.items[1]), **{
                    k: (v.value if isinstance(v, (SymbolAtom, StringAtom, KeywordAtom)) else getattr(v, "value", "(..)"))
                    for k, v in kw.items() if k in (":model", ":effort", ":timeout-sec", ":delivery")}))
            for x in e.items:
                pr(x)
    for form in d["forms"]:
        pr(form)


# ---------------------------------------------------------------- let* candidates
def uses(e, name):
    """Count references to name (bare symbol or dotted name.field) inside e."""
    if isinstance(e, SymbolAtom):
        return int(e.value == name or e.value.startswith(name + "."))
    if isinstance(e, ListExpr):
        return sum(uses(x, name) for x in e.items)
    return 0


def use_kind(e, name, in_loop_state=False):
    """Return set of contexts in which name is used within e."""
    out = set()
    if isinstance(e, ListExpr):
        h = hd(e)
        if h == "match" and len(e.items) > 1 and isinstance(e.items[1], SymbolAtom) and e.items[1].value == name:
            out.add("match subject")
        for x in e.items:
            if isinstance(x, SymbolAtom) and (x.value == name or x.value.startswith(name + ".")):
                if in_loop_state or h == "loop-state":
                    out.add("loop-state")
                elif not (h == "match" and x is e.items[1]):
                    out.add("other")
            out |= use_kind(x, name, in_loop_state or h == "loop-state")
    return out


LETSTAR = []


def scan_let(e, f):
    if not isinstance(e, ListExpr):
        return
    if hd(e) == "let*":
        binds = list(e.items[1].items)
        body = list(e.items[2:])
        for i, b in enumerate(binds):
            name = sym(b.items[0])
            later = [bb.items[1] for bb in binds[i + 1:]] + body
            nxt = later[0]
            total = sum(uses(x, name) for x in later)
            if total == 1 and uses(nxt, name) == 1:
                kinds = use_kind(nxt, name)
                if kinds and kinds <= {"match subject", "loop-state"}:
                    LETSTAR.append(dict(file=f, line=b.span.start.line, name=name, use=sorted(kinds)[0],
                                        value_head=hd(b.items[1]), next_head=hd(nxt)))
    for x in e.items:
        scan_let(x, f)


for f, d in FILES.items():
    for form in d["forms"]:
        scan_let(form, f)


# ---------------------------------------------------------------- unions and variant collisions
APPROVAL = {"APPROVE", "APPROVED", "ACCEPT", "ACCEPTED", "PASS", "PASSED", "OK", "READY"}
CHANGES = {"REVISE", "REQUEST_CHANGES", "CHANGES_REQUESTED", "BLOCKED", "BLOCK", "REJECT", "REJECTED", "FIX", "NEEDS_REVISION", "WRONG_APPROACH"}
review_unions = []
for name, decls in UNIONS.items():
    for u in decls:
        vs = set(u["variants"])
        if vs & APPROVAL and vs & CHANGES:
            review_unions.append(dict(name=name, **u))

collisions = []
for f, d in FILES.items():
    visible = {}
    for form in d["forms"]:
        h = hd(form)
        if h == "defunion":
            visible[sym(form.items[1])] = "local"
        elif h == "import":
            mod = sym(form.items[1])
            kw = kwargs(form.items[2:])
            names = [sym(x) for x in kw[":only"].items] if ":only" in kw else None
            for uname, decls in UNIONS.items():
                for u in decls:
                    if u["module"] == mod and (names is None or uname in names):
                        visible[uname] = f"import {mod}"
    owners = collections.defaultdict(list)
    for uname, src in visible.items():
        mod = MODULE_OF[f] if src == "local" else src.split(" ", 1)[1]
        u = next(x for x in UNIONS[uname] if x["module"] == mod)
        for v in u["variants"]:
            owners[v].append(f"{uname} ({src})")
    for v, us in owners.items():
        if len(us) > 1:
            collisions.append(dict(file=f, variant=v, unions=us))


# ---------------------------------------------------------------- output
out = dict(lowering_sites=lowering_sites, rows=rows, sites=SITES, effects=effects, lowering=dict(lowering), where=[
    dict(w, kinds=dict(w["kinds"])) for w in where], forall=forall,
    provider_calls=provider_calls, letstar=LETSTAR,
    review_unions=[dict(name=u["name"], file=u["file"], line=u["line"], tvars=u["tvars"], variants=u["variants"]) for u in review_unions],
    collisions=collisions)
pathlib.Path(__file__).with_name("census.json").write_text(json.dumps(out, indent=1, default=str))
print(f"{len(FILES)} files, {len(SITES)} constructor sites, {len(effects)} :effects, {len(LETSTAR)} let* candidates")
