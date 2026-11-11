#!/usr/bin/env python3
"""Moment 1: what will this workflow touch, before anything runs.

Builds the Python workflow (py build: trace it, generate ordinary Workflow
Lisp, compile it) and lists every effect in the checked closed program: the
variant arms that must match before it can run (its proof path, which is
part of its identity), its binding, and the typed result it must return;
then the model's contract in full. Nothing here is inferred from prose; it
is the compiler's own site table.

usage: check_effects.py <workflow.py> <entry> [py build flags...]
"""
import json
import subprocess
import sys
from pathlib import Path

BOLD, DIM, OFF = "\033[1m", "\033[2m", "\033[0m"


def compile_entry(source, entry, flags):
    """py build the workflow; return (build result, closed program)."""
    proc = subprocess.run(
        [sys.executable, "-m", "orchestrator", "py", "build", source, "--entry-workflow", entry, *flags],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(proc.returncode)
    built = json.loads(proc.stdout[proc.stdout.index("{"):])
    program = json.loads(Path(built["artifact_paths"]["closed_program"]).read_text())
    return built, program


def performs(node):
    if isinstance(node, dict):
        if node.get("k") == "perform":
            yield node
        for value in node.values():
            yield from performs(value)
    elif isinstance(node, list):
        for value in node:
            yield from performs(value)


def nodes(node, kind):
    if isinstance(node, dict):
        if node.get("k") == kind:
            yield node
        for value in node.values():
            yield from nodes(value, kind)
    elif isinstance(node, list):
        for value in node:
            yield from nodes(value, kind)


def effects_in_site_order(program):
    """Every effect, including those inside called procedures (a person's answer is one),
    with `site` set to its full path from the entry: the call frame, then the procedure's site."""
    effects = list(performs(program["body"]))
    for call in nodes(program["body"], "call"):
        for effect in performs(program["definitions"].get(call["callee"], {})):
            effects.append({**effect, "site": f"{call['frame']} / {effect['site']}",
                            "procedure": call["callee"].split("::")[-1]})
    order = {tuple(site): i for i, site in enumerate(program["sites"])}
    return sorted(effects, key=lambda p: (len(guards(p["site"])), order.get((program["entry"], p["site"]), 99)))


BRANCH = {}   # "then"/"else" of a `when`, named after the literal it compares with, e.g. APPROVED


def name_branches(program):
    tests = [lit["v"] for op in nodes(program["body"], "op") for lit in op.get("args", [])
             if lit.get("k") == "lit" and lit.get("type", {}).get("kind") == "enum"]
    if len(tests) == 1:
        BRANCH.update({"then": tests[0], "else": f"not {tests[0]}"})


def guards(site):
    """The arms on an effect's path. Generated sites read `_e7 / body / DIAGNOSED / _e2`:
    each match arm or when branch follows a `body` segment."""
    parts = site.split(" / ")
    return [BRANCH.get(parts[i], parts[i]) for i in range(1, len(parts) - 1) if parts[i - 1] == "body"]


def provider_names(externs_file):
    """binding -> extern name, from a providers.json such as {"providers.claude": "claude_..."}."""
    externs = json.loads(Path(externs_file).read_text()) if externs_file else {}
    return {binding: name.split(".")[-1] for name, binding in externs.items()}


def effect_name(perform, names):
    if perform["class"] == "provider":
        return names.get(perform["provider"], perform["provider"])
    if perform["class"] == "request_input":
        return perform.get("procedure", "request")
    return perform.get("boundary") or perform["site"].split(" / ")[-1]


def type_text(t):
    kind = t.get("kind")
    if kind == "primitive":
        return t["name"]
    if kind == "enum":
        return "one of " + " | ".join(t["allowed"])
    if kind == "path":
        return f"a path under {t['under']}" + (" that must exist" if t.get("must_exist_target") else "")
    if kind == "list":
        return "List[" + type_text(t["item"] if "item" in t else t.get("element", {})) + "]"
    if kind == "record":
        return t["name"].split("::")[-1]
    if kind == "union":
        return " | ".join(v["name"] for v in t["variants"])
    return kind or "?"


def binding_text(p):
    if p["class"] == "provider":
        return "model call"
    if p["class"] == "request_input":
        return "a person: input answer"
    command = p["command"]
    return " ".join(command[1:] if command[0].startswith("python") else command)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    source, entry, *flags = sys.argv[1:]
    built, program = compile_entry(source, entry, flags)
    name_branches(program)
    externs = flags[flags.index("--provider-externs-file") + 1] if "--provider-externs-file" in flags else None
    names = provider_names(externs)
    rows = effects_in_site_order(program)
    generated = Path(built["source_path"])
    shown = generated.relative_to(Path.cwd()) if generated.is_relative_to(Path.cwd()) else generated
    snapshot = shown.parts[2] if len(shown.parts) > 2 and shown.parts[:2] == (".orchestrate", "python") else None
    if snapshot:   # .orchestrate/python/<64-hex snapshot>/generated/...: keep the path, shorten the key
        shown = Path(*shown.parts[:2], snapshot[:8] + "…", *shown.parts[3:])

    print(f"{BOLD}{program['entry']}{OFF}   {len(rows)} effects   program {built['program_digest'][:19]}…")
    print(f"{DIM}generated Workflow Lisp: {shown} ({len(generated.read_text().splitlines())} lines){OFF}\n")
    for p in rows:   # two lines per effect: the path that reaches it, then what it is bound to and returns
        path = " → ".join(guards(p["site"])) or "always"
        print(f"  {BOLD}{effect_name(p, names):<16}{OFF}{path}")
        print(f"  {'':<16}{DIM}{binding_text(p)}  →  {type_text(p['result'])}{OFF}")

    for p in rows:
        if p["class"] != "provider":
            continue
        model = p.get("policy", {}).get("model", {})
        model = model["v"] if "v" in model else f"input `{model.get('n', '?')}`"
        fills = ", ".join(f"{f['name']} ({f['kind']})" for f in p["prompt"]["fills"])
        print(f"\n  {BOLD}{effect_name(p, names)}{OFF} is the only model call")
        print(f"  {DIM}provider{OFF} {p['provider']}")
        print(f"  {DIM}model{OFF}    {model}")
        print(f"  {DIM}reads{OFF}    {fills}")
        print(f"  {DIM}returns{OFF}")
        for variant in p["result"]["variants"]:
            for i, field in enumerate(variant["fields"]):
                label = variant["name"] if i == 0 else ""
                print(f"    {label:<14}{field['name']:<12}{type_text(field['type'])}")

    for p in rows:
        if p["class"] != "request_input":
            continue
        timeout = p.get("timeout_sec", {}).get("v")
        print(f"\n  {BOLD}{effect_name(p, names)}{OFF} is the only question to a person: the run suspends until "
              f"`orchestrator input answer`" + (f", and the request expires after {timeout} s" if timeout else ""))
        print(f"  {DIM}shows{OFF}    {len(p.get('show', []))} frozen files (an answer is refused if they change)")
        print(f"  {DIM}returns{OFF}  {type_text(p['result'])}")

    deepest = max(rows, key=lambda p: len(guards(p["site"])))
    if guards(deepest["site"]):
        print(f"\nNothing else runs. `{effect_name(deepest, names)}` is reachable only through "
              f"{' → '.join(guards(deepest['site']))}:\nthat is its identity in the compiled program, "
              "not a comment.")


if __name__ == "__main__":
    main()
