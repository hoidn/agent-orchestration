"""Build `request_allowlist.json`, the passthrough's allowlist of the CLI's request shape, from the recorded
request fixtures (`fixtures/requests/*.json`, cut by `cut_fixture.py requests`).

Only the CLI's own model requests count: shapes of `POST /v1/messages?beta=true` that declare no provider-side
tool (the allowlist probe's GET and the web-search request are not the shape the passthrough lets through).
From them: header names, the values of the headers the cutter keeps (`anthropic-beta` as a set of flags, the
user agent's product token), the top-level body keys (the cutter's named fields and every other recorded
field), the efforts, the largest `max_tokens`, the `stream` values, and the client-side tool names.
Tool keys are not in today's fixtures (they keep tool names only); until a fixture records them (a shape field
`tool_keys`), the client-side tool fields of the Messages API are used, and `tool_keys_recorded` says so.
`x-api-key` and `cookie` are never allowed (key mode is not the ladder's; decision 18).

Usage: python -I make_allowlist.py           (writes request_allowlist.json beside this file)
       python -I make_allowlist.py --check   (exit 1 if the committed file differs from what the fixtures give)
"""

import glob
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "request_allowlist.json"
MESSAGES = ("POST", "/v1/messages?beta=true")
NEVER_HEADERS = {"x-api-key", "cookie"}
VALUE_HEADERS = ("anthropic-version", "content-type", "x-app")
UNRECORDED_TOOL_KEYS = ["cache_control", "description", "input_schema", "name"]


def _named_params():
    spec = importlib.util.spec_from_file_location("lh_cut_fixture", HERE / "cut_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NAMED_PARAMS


def shapes(directory=HERE / "fixtures" / "requests"):
    files = sorted(glob.glob(f"{directory}/*.json"))
    found = [s for path in files for s in json.loads(Path(path).read_text())["shapes"]]
    return [s for s in found if (s.get("method"), s.get("path")) == MESSAGES and not s.get("server_tools")]


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
        "top_level": sorted({"messages", "system", "tools", *_named_params()} |
                            {k for s in kept for k in s.get("other_params") or []}),
        "effort": _values(kept, "effort"),
        "max_tokens_max": max(s["max_tokens"] for s in kept if s.get("max_tokens")),
        "stream": _values(kept, "stream"),
    }


def _tools(kept):
    keys = sorted({k for s in kept for k in s.get("tool_keys") or []})
    return {"tool_names": sorted({name for s in kept for name in s.get("tools") or []}),
            "tool_keys": keys or UNRECORDED_TOOL_KEYS, "tool_keys_recorded": bool(keys)}


def build(kept):
    source = "make_allowlist.py over fixtures/requests (CLI 2.1.311 recordings); regenerate when fixtures change"
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
