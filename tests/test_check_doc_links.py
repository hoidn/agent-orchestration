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
