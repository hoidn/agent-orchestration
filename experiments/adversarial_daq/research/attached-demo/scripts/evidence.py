"""The evidence contract: every line the model quotes ("> ...") is copied from one line of the bundle.

A quote may be a whole line or a contiguous part of one (a dropped trailing comma, a
trimmed timestamp), with runs of spaces counted as one (a table row re-spaced), but
not a line rewritten from memory, one joined across lines, the model's own reasoning
behind the marker, or a fragment too short to mean anything.
"""

SHORTEST = 16   # characters; "phase 2" is not evidence


def quotes(evidence_text):
    return [line[2:].strip() for line in evidence_text.splitlines() if line.startswith("> ")]


def _spaced(text):
    return " ".join(text.split())


def not_in_bundle(quoted, bundle_text):
    lines = [_spaced(line) for line in bundle_text.splitlines()]
    return [q for q in quoted if len(q) < SHORTEST or not any(_spaced(q) in line for line in lines)]
