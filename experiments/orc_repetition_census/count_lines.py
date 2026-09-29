"""Count non-blank, non-comment lines of .orc files by top-level form category.

usage: python count.py label=path [label=path ...]
"""
import re
import sys
from collections import Counter

CATS = {
    "workflow-lisp": "header", ":language": "header", ":target-dsl": "header",
    "defmodule": "header", "import": "header", "export": "header",
    "defrecord": "types", "defunion": "types", "defpath": "types", "defenum": "types",
    "defprompt": "prompts", "defproc": "procs", "defworkflow": "procs",
}
ANNOT = (":effects", ":lowering", ":where", ":forall")


def code_lines(text):
    """Yield (code, depth_at_start, heads_opened) per line; strips ; comments outside strings."""
    depth, in_str, esc = 0, False, False
    for raw in text.split("\n"):
        code, start_depth, opened = [], depth, []
        i = 0
        while i < len(raw):
            ch = raw[i]
            if in_str:
                code.append(ch)
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == ";":
                break
            else:
                code.append(ch)
                if ch == '"':
                    in_str = True
                elif ch == "(":
                    m = re.match(r"\(([^\s()]+)", raw[i:])
                    opened.append((depth, m.group(1) if m else ""))
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        yield "".join(code), start_depth, opened


def count(path):
    text = open(path).read()
    totals, sub = Counter(), Counter()
    current = "header"
    for code, start_depth, opened in code_lines(text):
        if start_depth == 1:
            top = [h for d, h in opened if d == 1]
            current = CATS.get(top[0], "other") if top else "header"
        if start_depth == 0:
            current = "header"
        if not code.strip():
            continue
        totals[current] += 1
        totals["total"] += 1
        if current == "procs":
            s = code.strip()
            if s.startswith(ANNOT):
                sub["annotation lines"] += 1
            sub["constructor type names"] += len(re.findall(r"\((?:variant|record)\s+[A-Z]", code))
    return totals, sub


if __name__ == "__main__":
    rows = []
    for arg in sys.argv[1:]:
        label, path = arg.split("=", 1)
        rows.append((label, *count(path)))
    cols = ["header", "types", "prompts", "procs", "other", "total"]
    print("label".ljust(12) + "".join(c.rjust(9) for c in cols) + "  annot  ctor-types")
    for label, t, s in rows:
        print(label.ljust(12) + "".join(str(t[c]).rjust(9) for c in cols)
              + str(s["annotation lines"]).rjust(7) + str(s["constructor type names"]).rjust(12))
