"""Count type declarations whose name is declared in more than one corpus file.

Dependencies: none beyond the standard library. Reads `.orc` files under the
repository root given as the first argument (default: current directory).
Prints, per declaration kind, the number of declarations, the number that
repeat a name declared in another file, how many of those have identical
text, and the lines they occupy.
"""
import collections
import glob
import pathlib
import re
import sys

KINDS = ("defrecord", "defunion", "defpath", "defenum")


def corpus(root: pathlib.Path) -> list[pathlib.Path]:
    patterns = (
        "workflows/examples/**/*.orc",
        "workflows/library/**/*.orc",
        "experiments/orc_vs_single_call/workflows/*.orc",
        "orchestrator/workflow_lisp/stdlib_modules/**/*.orc",
    )
    found = [pathlib.Path(p) for pattern in patterns for p in glob.glob(str(root / pattern), recursive=True)]
    return sorted(p for p in found if "lisp_frontend_design_delta" not in p.parts)


def declarations(text: str) -> list[tuple[str, str, str, int]]:
    """Return (kind, name, normalized text, line count) for each declaration."""
    out = []
    for match in re.finditer(r"^  \((def(?:record|union|path|enum))\s+([^\s()]+)", text, re.M):
        start, depth, index = match.start() + 2, 0, match.start() + 2
        while index < len(text):
            char = text[index]
            if char == '"':
                index += 1
                while index < len(text) and text[index] != '"':
                    index += 2 if text[index] == "\\" else 1
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        source = text[start:index + 1]
        normalized = re.sub(r"\s+", " ", re.sub(r";.*", "", source))
        out.append((match.group(1), match.group(2), normalized, source.count("\n") + 1))
    return out


def main() -> None:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    by_name = collections.defaultdict(list)
    files = corpus(root)
    for path in files:
        for kind, name, text, lines in declarations(path.read_text()):
            by_name[(kind, name)].append((path, text, lines))
    print(f"files {len(files)}")
    for kind in KINDS:
        groups = [group for (k, _), group in by_name.items() if k == kind]
        total = sum(len(group) for group in groups)
        repeats = sum(len(group) - 1 for group in groups if len(group) > 1)
        identical = sum(len(group) - 1 for group in groups if len(group) > 1 and len({t for _, t, _ in group}) == 1)
        lines = sum(sum(n for _, _, n in group[1:]) for group in groups if len(group) > 1)
        print(f"{kind:10s} declarations={total:3d} repeats={repeats:3d} identical={identical:3d} lines_in_repeats={lines:3d}")
    for (kind, name), group in sorted(by_name.items(), key=lambda item: -len(item[1])):
        if len(group) > 1:
            same = len({t for _, t, _ in group}) == 1
            print(f"  {kind} {name}: {len(group)} files, identical={same}")


if __name__ == "__main__":
    main()
