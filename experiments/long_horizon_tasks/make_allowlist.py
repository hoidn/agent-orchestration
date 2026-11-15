"""Build `request_allowlist.json`, the passthrough's allowlist of the CLI's request shape, from the request
fixtures of Task 2a's recordings, the ladder's configuration (`fixtures/requests/t2a-*.json`, cut by
`cut_fixture.py requests`).

Only the CLI's own model requests in token mode count: shapes of `POST /v1/messages?beta=true` that declare no
provider-side tool and carry no `x-api-key` (the relay probe's GET and the key-mode contrast are not the shape
the passthrough lets through). From them: header names, the values of the headers the cutter keeps
(`anthropic-beta` as a set of flags, the user agent's product token), the recorded top-level body keys, the
efforts, the largest `max_tokens`, the `stream` values, and per tool name the recorded keys of its definition and
of its `input_schema`. Nothing is assumed: a kept shape without a recorded key set stops the build.
`x-api-key` and `cookie` are never allowed (key mode is not the ladder's; decision 18).

Usage: python -I make_allowlist.py           (writes request_allowlist.json beside this file)
       python -I make_allowlist.py --check   (exit 1 if the committed file differs from what the fixtures give)
"""

import collections
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "request_allowlist.json"
MESSAGES = ("POST", "/v1/messages?beta=true")
NEVER_HEADERS = {"x-api-key", "cookie"}
VALUE_HEADERS = ("anthropic-version", "content-type", "x-app")


def shapes(directory=HERE / "fixtures" / "requests"):
    files = sorted(glob.glob(f"{directory}/t2a-*.json"))
    found = [s for path in files for s in json.loads(Path(path).read_text())["shapes"]]
    return [s for s in found if (s.get("method"), s.get("path")) == MESSAGES and not s.get("server_tools")
            and "x-api-key" not in s["headers"]]


def _recorded(shape, field, length=None):
    value = shape.get(field)
    if value is None or None in value or (length is not None and len(value) != length):
        sys.exit(f"make_allowlist: a request shape (tools {shape.get('tools')}) has no recorded {field}; "
                 "re-cut its fixture with cut_fixture.py requests")
    return value


def _values(kept, key):
    seen = {s.get(key) for s in kept}
    return sorted(v for v in seen if v is not None) + ([None] if None in seen else [])


def _headers(kept):
    headers = [s["headers"] for s in kept]
    return {
        "headers": sorted({name for h in headers for name in h} - NEVER_HEADERS),
        "header_values": {name: sorted({h[name] for h in headers if h.get(name)}) for name in VALUE_HEADERS},
        "anthropic_beta": sorted({flag for h in headers if h.get("anthropic-beta")
                                  for flag in h["anthropic-beta"].split(",")}),
        "user_agent": sorted({h["user-agent"] for h in headers if h.get("user-agent")}),
    }


def _body(kept):
    return {
        "top_level": sorted({k for s in kept for k in _recorded(s, "body_keys")}),
        "effort": _values(kept, "effort"),
        "max_tokens_max": max(s["max_tokens"] for s in kept if s.get("max_tokens")),
        "stream": _values(kept, "stream"),
    }


def _tools(kept):
    keys, schema = collections.defaultdict(set), collections.defaultdict(set)
    for s in kept:
        tools = s.get("tools") or []
        for name, own, its in zip(tools, _recorded(s, "tool_keys", len(tools)),
                                  _recorded(s, "input_schema_keys", len(tools))):
            keys[name].update(own)
            schema[name].update(its)
    return {"tool_keys": {name: sorted(found) for name, found in sorted(keys.items())},
            "input_schema_keys": {name: sorted(found) for name, found in sorted(schema.items())}}


def build(kept):
    source = "make_allowlist.py over fixtures/requests/t2a-*.json (CLI 2.1.311, Task 2a); regenerate when they change"
    return {"source": source, "method": MESSAGES[0], "path": MESSAGES[1], **_headers(kept), **_body(kept),
            **_tools(kept)}


def render(allowlist):
    return json.dumps(allowlist, indent=1) + "\n"


def main(argv):
    text = render(build(shapes()))
    if argv[1:] == ["--check"]:
        return 0 if OUT.read_text() == text else 1
    OUT.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
