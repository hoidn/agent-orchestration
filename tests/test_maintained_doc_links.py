"""Relative links and ``#fragment`` anchors in maintained docs resolve.

Inputs: the maintained Markdown set below, read from the working tree.
Fenced code blocks and inline code spans are not prose, so links inside them
are ignored; scheme URLs (``https:``, ``mailto:``) are not checked.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
MAINTAINED_DOCS = sorted(
    {
        *REPO_ROOT.glob("README.md"),
        *REPO_ROOT.glob("MIND_MAP.md"),
        *REPO_ROOT.glob("docs/*.md"),
        *REPO_ROOT.glob("docs/design/*.md"),
        *REPO_ROOT.glob("docs/templates/*.md"),
        *REPO_ROOT.glob("specs/*.md"),
        *REPO_ROOT.glob("workflows/README.md"),
        *REPO_ROOT.glob("prompts/README.md"),
        *REPO_ROOT.glob("experiments/*/README.md"),
    }
)
FENCE = re.compile(r"^(```|~~~)")
CODE_SPAN = re.compile(r"(`+).+?\1")
# Link text may wrap across lines; the target may not.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
ANCHOR_TAG = re.compile(r"<a\s+(?:id|name)=\"([^\"]+)\"")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
HEADING_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _prose_lines(path: Path) -> list[str]:
    """Return the file's lines with fenced-code lines blanked (numbering kept)."""
    lines = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            lines.append("")
        else:
            lines.append("" if in_fence else line)
    return lines


@lru_cache(maxsize=None)
def _anchors(path: Path) -> frozenset[str]:
    """GitHub-style heading slugs plus explicit ``<a id/name>`` anchors."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _prose_lines(path):
        anchors.update(ANCHOR_TAG.findall(line))
        heading = HEADING.match(line)
        if heading is None:
            continue
        text = HEADING_LINK.sub(r"\1", heading.group(1)).lower()
        slug = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(anchors)


def _broken_links(doc: Path) -> list[str]:
    text = "\n".join(CODE_SPAN.sub("", line) for line in _prose_lines(doc))
    broken = []
    for match in LINK.finditer(text):
        target = match.group(1)
        if SCHEME.match(target):
            continue
        line_number = text.count("\n", 0, match.start(1)) + 1
        path_part, _, fragment = target.partition("#")
        dest = (doc.parent / path_part).resolve() if path_part else doc
        if not dest.exists():
            broken.append(f"line {line_number}: {target} (no such path)")
        elif fragment and dest.suffix == ".md" and fragment not in _anchors(dest):
            broken.append(f"line {line_number}: {target} (no such anchor)")
    return broken


@pytest.mark.parametrize(
    "doc",
    MAINTAINED_DOCS,
    ids=lambda path: path.relative_to(REPO_ROOT).as_posix(),
)
def test_relative_links_and_fragments_resolve(doc: Path) -> None:
    assert _broken_links(doc) == []


def test_link_scan_ignores_code_and_checks_wrapped_links(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text(
        "# Target Heading\n\n## Repeat\n\n## Repeat\n\n<a id=\"explicit\"></a>\n",
        encoding="utf-8",
    )
    doc = tmp_path / "doc.md"
    doc.write_text(
        "`call f[spec](atoms)` and [ok](target.md#target-heading)\n"
        "[wrapped\ntext](target.md#repeat-1) [anchor](target.md#explicit)\n"
        "```\n[fenced](missing.md)\n```\n"
        "[web](https://example.com/missing) [bad](target.md#repeat-2)\n"
        "[gone](missing.md)\n",
        encoding="utf-8",
    )

    assert _broken_links(doc) == [
        "line 7: target.md#repeat-2 (no such anchor)",
        "line 8: missing.md (no such path)",
    ]
