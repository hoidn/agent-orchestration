"""The documentation link checker resolves heading and HTML anchors and reports the rest."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_doc_links.py"


def _checker():
    spec = importlib.util.spec_from_file_location("check_doc_links", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_heading_and_html_anchors_resolve_and_a_missing_one_is_reported(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text(
        '# Title\n\n## A Heading\n\n<a id="kept-id"></a>\n<a name="kept-name"></a>\n', encoding="utf-8"
    )
    source = tmp_path / "source.md"
    source.write_text(
        "[h](target.md#a-heading) [i](target.md#kept-id) [n](target.md#kept-name) [m](target.md#absent)\n",
        encoding="utf-8",
    )

    assert _checker().problems(source) == [f"{source}: missing anchor target.md#absent"]


def _problems_for(tmp_path: Path, target_text: str, fragment: str) -> list[str]:
    (tmp_path / "target.md").write_text(target_text, encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text(f"[x](target.md#{fragment})\n", encoding="utf-8")
    return _checker().problems(source)


def test_single_quoted_id_after_another_attribute_in_an_uppercase_tag_resolves(tmp_path: Path) -> None:
    assert _problems_for(tmp_path, "<A class='x' ID='late-id'></A>\n", "late-id") == []


def test_mixed_case_id_resolves_from_a_mixed_case_fragment(tmp_path: Path) -> None:
    assert _problems_for(tmp_path, '<a id="MixedCase"></a>\n', "MixedCase") == []


def test_anchor_inside_inline_code_does_not_count(tmp_path: Path) -> None:
    assert _problems_for(tmp_path, 'Write `<a id="shown"></a>` to add one.\n', "shown") != []


def test_anchor_inside_a_fence_does_not_count(tmp_path: Path) -> None:
    assert _problems_for(tmp_path, '```html\n<a id="fenced"></a>\n```\n', "fenced") != []


def test_duplicate_anchor_id_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "dup.md"
    source.write_text('<a id="twice"></a>\n<a name="TWICE"></a>\n', encoding="utf-8")
    assert _checker().problems(source) == [f"{source}: duplicate anchor id twice"]
