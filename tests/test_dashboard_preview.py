"""Tests for safe dashboard file previews."""

from __future__ import annotations

from pathlib import Path

from orchestrator.dashboard.preview import PreviewRenderer


def test_preview_escapes_html_and_decodes_with_replacement(tmp_path: Path):
    path = tmp_path / "payload.txt"
    path.write_bytes(b"<script>x</script>\xff")

    preview = PreviewRenderer(max_bytes=100).preview(path)

    assert preview.status == "ok"
    assert preview.display_text == "&lt;script&gt;x&lt;/script&gt;\ufffd"
    assert preview.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in preview.headers["Content-Security-Policy"]


def test_preview_pretty_prints_json_as_escaped_text(tmp_path: Path):
    path = tmp_path / "payload.json"
    path.write_text('{"html":"<b>bold</b>","n":1}', encoding="utf-8")

    preview = PreviewRenderer(max_bytes=100).preview(path)

    assert preview.status == "ok"
    assert '"n": 1' in preview.display_text
    assert "&lt;b&gt;bold&lt;/b&gt;" in preview.display_text


def test_preview_caps_large_text_files(tmp_path: Path):
    path = tmp_path / "large.log"
    path.write_text("abcdef", encoding="utf-8")

    preview = PreviewRenderer(max_bytes=3).preview(path)

    assert preview.status == "ok"
    assert preview.truncated is True
    assert preview.display_text == "abc"


def test_preview_classifies_binary_and_missing_files(tmp_path: Path):
    binary = tmp_path / "blob.bin"
    missing = tmp_path / "missing.txt"
    binary.write_bytes(b"abc\x00def")
    renderer = PreviewRenderer(max_bytes=100)

    assert renderer.preview(binary).status == "binary"
    assert renderer.preview(missing).status == "missing"


def test_raw_download_headers_keep_scriptable_payloads_inert(tmp_path: Path):
    path = tmp_path / "payload.svg"
    path.write_text("<svg><script>alert(1)</script></svg>", encoding="utf-8")

    raw = PreviewRenderer(max_bytes=100).raw(path)

    assert raw.status == "ok"
    assert raw.headers["X-Content-Type-Options"] == "nosniff"
    assert raw.headers["Content-Disposition"].startswith("attachment;")
    assert raw.headers["Content-Type"] == "text/plain; charset=utf-8"
