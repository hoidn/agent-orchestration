"""Usage: python scripts/check_doc_links.py FILE.md... -- check relative links and GitHub `#anchor` slugs.

Prints each problem and exits 1 if any. Links with a URL scheme are skipped; anchors are checked in .md targets."""
from functools import cache
from pathlib import Path
import re
import sys
from urllib.parse import unquote

FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
LINK = re.compile(r"\]\(<?(?![a-z][a-z0-9+.-]*:)([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)", re.I)
HTML_ID = re.compile(r"<a\s[^>]*?\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.I)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def html_ids(text: str) -> list[str]:
    """Lower-cased `<a id>`/`<a name>` anchors outside inline code (fences are removed by the caller)."""
    return [name.lower() for name in HTML_ID.findall(INLINE_CODE.sub("", text))]


@cache
def anchors(path: Path) -> frozenset[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    names, seen = set(html_ids(text)), {}
    for title in re.findall(r"^#{1,6}\s+(.+?)(?:\s+#+)?\s*$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title).lower()).replace(" ", "-")
        names.add(f"{slug}-{seen[slug]}" if slug in seen else slug)  # GitHub suffixes repeated headings
        seen[slug] = seen.get(slug, 0) + 1
    return frozenset(names)


def problems(source: Path) -> list[str]:
    unfenced = FENCE.sub("", source.read_text(encoding="utf-8"))
    ids = html_ids(unfenced)
    found = [f"{source}: duplicate anchor id {name}" for name in sorted({n for n in ids if ids.count(n) > 1})]
    text = INLINE_CODE.sub("", unfenced)
    for target in LINK.findall(text):
        ref, _, fragment = target.partition("#")
        destination = source.parent / unquote(ref) if ref else source
        if not destination.exists():
            found.append(f"{source}: missing target {target}")
        elif fragment and destination.suffix == ".md" and unquote(fragment).lower() not in anchors(destination.resolve()):
            found.append(f"{source}: missing anchor {target}")
    return found


if __name__ == "__main__":
    report = [line for name in sys.argv[1:] for line in problems(Path(name))]
    print("\n".join(report) or "ok")
    sys.exit(1 if report else 0)
