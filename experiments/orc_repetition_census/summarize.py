"""Render census.json (written by census.py) as markdown tables."""
import pathlib
import collections
import json

d = json.load(open(pathlib.Path(__file__).with_name("census.json")))
short = lambda f: f.replace("workflows/examples/", "ex/").replace("workflows/library/", "lib/").replace(
    "experiments/orc_vs_single_call/workflows/", "exp/").replace("orchestrator/workflow_lisp/stdlib_modules/", "")
CATS = ["header/imports", "defrecord", "defunion", "defpath", "defenum", "defprompt", "defun", "defproc", "defworkflow", "other"]

print("## 1. Files and lines by top-level form\n")
print("| File | Target | Code lines | " + " | ".join(CATS) + " |")
print("|---|---|--:|" + "--:|" * len(CATS))
tot = collections.Counter()
for r in d["rows"]:
    print(f"| {short(r['file'])} | {r['target']} | {r['code']} | " + " | ".join(str(r[c]) for c in CATS) + " |")
    tot["code"] += r["code"]
    for c in CATS:
        tot[c] += r[c]
print(f"| **Total ({len(d['rows'])} files)** | | **{tot['code']}** | " + " | ".join(f"**{tot[c]}**" for c in CATS) + " |")
print("| Share of code lines | | | " + " | ".join(f"{100*tot[c]/tot['code']:.1f}%" for c in CATS) + " |")

S = d["sites"]
print("\n## 2. Constructor sites by position\n")
order = ["tail", "done", "on-exhausted", "let* binding", "call argument", "constructor field"]
def cat(s):
    k = s["kind"]
    if s["arm"] and k in ("tail", "done", "on-exhausted"):
        return f"match/if arm in {k}"
    if s["arm"]:
        return f"{k} (through match/if arm)"
    return k
c = collections.Counter(cat(s) for s in S)
cf = collections.Counter(cat(s) for s in S if s["fixed"])
crt = collections.Counter(cat(s) for s in S if s["reach"] is True)
cru = collections.Counter(cat(s) for s in S if s["reach"] is None)
cr = collections.Counter(cat(s) for s in S if s["ctor"] == "record")
cv = collections.Counter(cat(s) for s in S if s["ctor"] == "variant")
print("| Position | Sites | record | variant | Expected type fixed by a declaration | Expected type reaches the site in today's typechecker |")
print("|---|--:|--:|--:|--:|--:|")
for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
    print(f"| {k} | {v} | {cr[k]} | {cv[k]} | {cf[k]} | {crt[k]}{' (' + str(cru[k]) + ' not checked)' if cru[k] else ''} |")
print(f"| **Total** | **{len(S)}** | **{sum(cr.values())}** | **{sum(cv.values())}** | **{sum(cf.values())}** | **{sum(crt.values())}** ({sum(cru.values())} not checked) |")

print("\nPer file:\n")
print("| File | Sites | record | variant | Fixed by declaration | Not fixed |")
print("|---|--:|--:|--:|--:|--:|")
byf = collections.defaultdict(list)
for s in S:
    byf[s["file"]].append(s)
for r in d["rows"]:
    ss = byf.get(r["file"], [])
    if not ss:
        continue
    fx = sum(s["fixed"] for s in ss)
    print(f"| {short(r['file'])} | {len(ss)} | {sum(s['ctor']=='record' for s in ss)} | {sum(s['ctor']=='variant' for s in ss)} | {fx} | {len(ss)-fx} |")
nf = [s for s in S if not s["fixed"]]
print("\nSites whose expected type is not fixed by a declaration:\n")
print("| File:line | Constructor | Position | Why |")
print("|---|---|---|---|")
for s in nf:
    print(f"| {short(s['file'])}:{s['line']} | `{s['ctor']} {s['type']}{' '+s['variant'] if s['variant'] else ''}` | {cat(s)} | {s['via'] or ''} |")

print("\n## 3. Type names written in constructors\n")
names = [s["type"] for s in S]
bases = {n.split("[")[0].rsplit("/", 1)[-1] for n in names}
qual = [n for n in names if "/" in n]
targs = [n for n in names if "[" in n]
print(f"- Occurrences: {len(names)} ({sum(s['ctor']=='record' for s in S)} record, {sum(s['ctor']=='variant' for s in S)} variant)")
print(f"- Distinct spellings: {len(set(names))}; distinct base names (qualifier and type arguments stripped): {len(bases)}")
print(f"- Characters in the type atom: {sum(len(n) for n in names)} (mean {sum(len(n) for n in names)/len(names):.1f})")
print(f"- Module-qualified spellings: {len(qual)} occurrences, {sum(len(n) for n in qual)} characters, of which qualifier prefixes {sum(len(n.rsplit('/',1)[0])+1 for n in qual)}")
print(f"- Spellings with type arguments: {len(targs)} occurrences, {sum(len(n) for n in targs)} characters ({', '.join(sorted(set(targs)))})")
vs = [s for s in S if s["ctor"] == "variant"]
print(f"- Variant constructors also write a variant tag: {len(vs)} tags, {sum(len(s['variant']) for s in vs)} characters")
print("\n| Type spelling | Occurrences | Characters |")
print("|---|--:|--:|")
for n, k in collections.Counter(names).most_common():
    print(f"| `{n}` | {k} | {k*len(n)} |")

print("\n## 4. Annotations\n")
E = d["effects"]
print(f"- `:effects` clauses: {len(E)} (all on defproc); lines occupied: {sum(e['nlines'] for e in E)}; empty `()`: {sum(e['empty'] for e in E)}; effect entries: {sum(e['entries'] for e in E)}")
print("- `:lowering`: " + ", ".join(f"`{k}` {v}" for k, v in d["lowering"].items()) + f" ({sum(d['lowering'].values())} lines; none written as `private-workflow`)")
print(f"- `:where` clauses: {len(d['where'])}, constraint entries: {sum(sum(w['kinds'].values()) for w in d['where'])}")
kinds = collections.Counter()
for w in d["where"]:
    kinds.update(w["kinds"])
print("  - by kind: " + ", ".join(f"`{k}` {v}" for k, v in kinds.items()))
print(f"- `:forall` clauses: {len(d['forall'])} (" + ", ".join(f"{k} {v}" for k, v in collections.Counter(x['form'] for x in d['forall']).items()) + ")")
print("\n| File | `:effects` (= defproc count) | empty | effect lines | `:lowering inline` | `:lowering auto` | `:where` | `:forall` |")
print("|---|--:|--:|--:|--:|--:|--:|--:|")
for r in d["rows"]:
    f = r["file"]
    e = [x for x in E if x["file"] == f]
    w = [x for x in d["where"] if x["file"] == f]
    fa = [x for x in d["forall"] if x["file"] == f]
    if not (e or w or fa):
        continue
    lw = [x["value"] for x in d["lowering_sites"] if x["file"] == f]
    print(f"| {short(f)} | {len(e)} | {sum(x['empty'] for x in e)} | {sum(x['nlines'] for x in e)} | {lw.count('inline')} | {lw.count('auto')} | {len(w)} | {len(fa)} |")

print("\n## 5. let* candidates\n")
print("| File:line | Binding | Value form | Single use in next form |")
print("|---|---|---|---|")
for x in d["letstar"]:
    print(f"| {short(x['file'])}:{x['line']} | `{x['name']}` | `{x['value_head'] or 'symbol'}` | {x['use']} (`{x['next_head']}`) |")

print("\n## 6. Provider call options\n")
OPTS = [":model", ":effort", ":timeout-sec", ":delivery"]
print("| File | provider-result calls | " + " | ".join(f"`{o}` set" for o in OPTS) + " | Same value on every call |")
print("|---|--:|" + "--:|" * len(OPTS) + "---|")
allcalls = 0
setc = collections.Counter()
repeat_files = collections.defaultdict(list)
for r in d["rows"]:
    cs = d["provider_calls"].get(r["file"], [])
    if not cs:
        continue
    allcalls += len(cs)
    same = []
    for o in OPTS:
        n = sum(o in c for c in cs)
        setc[o] += n
        vals = {str(c.get(o)) for c in cs}
        if len(cs) >= 2 and n == len(cs) and len(vals) == 1:
            same.append(f"`{o} {vals.pop()}`")
            repeat_files[o].append(short(r["file"]))
    print(f"| {short(r['file'])} | {len(cs)} | " + " | ".join(str(sum(o in c for c in cs)) for o in OPTS) + f" | {', '.join(same) or '-'} |")
print(f"| **Total** | **{allcalls}** | " + " | ".join(f"**{setc[o]}**" for o in OPTS) + " | |")
print("\nFiles repeating one value on every call (>= 2 calls): " + "; ".join(f"`{o}`: {len(v)} ({', '.join(v)})" for o, v in repeat_files.items()))

print("\n## 7. Review-like unions\n")
print("| Union | File:line | Params | Variants and fields |")
print("|---|---|---|---|")
for u in d["review_unions"]:
    desc = "; ".join(f"{v}(" + ", ".join(f"{a} {b}" for a, b in fs) + ")" for v, fs in u["variants"].items())
    print(f"| `{u['name']}` | {short(u['file'])}:{u['line']} | {' '.join(u['tvars']) or '-'} | {desc} |")

print("\n## 8. Variant names shared by unions visible in one module\n")
print("| File | Variant | Unions |")
print("|---|---|---|")
for c in d["collisions"]:
    print(f"| {short(c['file'])} | {c['variant']} | {', '.join(c['unions'])} |")
amb = collections.defaultdict(set)
for c in d["collisions"]:
    amb[c["file"]].add(c["variant"])
hit = [s for s in S if s["ctor"] == "variant" and s["variant"] in amb.get(s["file"], ())]
print(f"\nVariant constructor sites whose tag is shared by >1 visible union in its module: {len(hit)} of {len(vs)}")
for s in hit:
    print(f"- {short(s['file'])}:{s['line']} `{s['type']} {s['variant']}`")
