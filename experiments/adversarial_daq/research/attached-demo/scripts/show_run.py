#!/usr/bin/env python3
"""Presenter views of a run, read straight from .orchestrate/runs/<run_id>/.

  show_run.py memo <run_id>              one line per effect attempt, in memo order
  show_run.py audit <run_id>             what was fetched, proposed, checked, approved and done
  show_run.py verdict <run_id> [field]   a field of the model's committed result (default: variant)
  show_run.py contract <prompt.txt>      the result shape the runtime appended: first variant in full

Nothing here is computed for the demo: every value shown is a field the
runtime wrote to memo.jsonl, state.json or run.json. Effects are named by
their binding (daq_logs, claude, ...) and indented by the variant arms
above them; the compiled identities use generated names (_e0, _e7 / body).
"""
import json
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from check_effects import effect_name, effects_in_site_order, guards, provider_names

GREEN, RED, YELLOW, BOLD, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[2m", "\033[0m"
WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 110)
ROLES = {"daq_logs": "fetched", "claude": "proposed", "check_playbook": "checked",
         "ask_daq_oncall": "approved", "daq_recover": "acted"}


class Run:
    """One run directory, with each compiled site resolved to its binding name."""

    def __init__(self, run_id):
        self.id = run_id
        self.dir = Path(".orchestrate") / "runs" / run_id
        self.state = json.loads((self.dir / "state.json").read_text())
        self.header = json.loads((self.dir / "run.json").read_text())
        program = json.loads((self.dir / "closed_program.json").read_text())
        names = provider_names(self.header["resume_request"].get("provider_externs_path"))
        self.performs = {p["site"]: p for p in effects_in_site_order(program)}
        self.names = {site: effect_name(p, names) for site, p in self.performs.items()}

    @staticmethod
    def site(identity):
        return identity.split(" / ", 1)[-1]

    def name(self, identity):
        return self.names.get(self.site(identity), self.site(identity))

    def depth(self, identity):
        return len(guards(self.site(identity)))

    def steps(self):
        return [(self.name(identity), identity, step) for identity, step in self.state["steps"].items()]

    def memo(self):
        return [json.loads(raw) for raw in (self.dir / "memo.jsonl").open()]


def value_text(value, compact=False):
    """DIAGNOSED cause=deadtime_link target=... : the variant first, then its fields.
    compact: long text cut to 72 characters, lists counted, for the memo on a projector."""
    if not isinstance(value, dict):
        return json.dumps(value)
    parts = [value["variant"]] if "variant" in value else []
    for key, field in value.items():
        if key == "variant":
            continue
        if isinstance(field, list) and all(isinstance(item, str) for item in field):
            parts.append(f"{key}=[{len(field)} items]" if compact else f"{key}=[{' · '.join(field)}]")
            continue
        text = field if isinstance(field, str) else json.dumps(field)
        if compact:   # artifacts/daq/412/20261023T...-xxxxxx/evidence.md -> artifacts/daq/412/…/evidence.md
            text = re.sub(r"/\d{8}T\d{6}Z-[a-z0-9]{6}/", "/…/", text)
        if compact and len(text) > 72:
            text = text[:71] + "…"
        parts.append(f"{key}={json.dumps(text, ensure_ascii=False) if ' ' in text else text}")
    return " ".join(parts)


def wrapped(head, text, indent):
    """Print head + text, wrapping text under itself at column `indent`."""
    body = textwrap.wrap(text, WIDTH - indent) or [""]
    print(head + body[0])
    for more in body[1:]:
        print(" " * indent + more)


def line(mark, color, label, text):
    wrapped(f"  {color}{mark}{OFF} {label:<24}", text, 28)


def memo(run_id):
    run = Run(run_id)
    entries, latest = [], {}
    for record in run.memo():
        if record["record"] == "terminal" or "identity" not in record:   # terminal, invalidated, ...
            entries.append(record)
            continue
        key = (record["identity"], record.get("attempt"))
        if key not in latest:
            entries.append(key)
        latest[key] = record

    for entry in entries:
        if isinstance(entry, dict):
            if entry["record"] != "terminal":
                print(f"  {DIM}■ {entry['record']}{OFF}")
            elif "value" in entry:
                print(f"  {BOLD}■ finished{OFF}  {value_text(entry['value'])}")
            else:
                print(f"  {DIM}■ stopped here: {entry.get('code') or entry.get('outcome')}{OFF}")
            continue
        record = latest[entry]
        label = "  " * run.depth(record["identity"]) + f"{run.name(record['identity'])} #{record.get('attempt')}"
        kind = record["record"]
        effect = run.performs.get(Run.site(record["identity"]), {})
        if kind == "committed":
            line("✓", GREEN, label, value_text(record.get("value"), compact=True))
        elif kind == "failed":
            line("✗", RED, label, record.get("code", "failed"))
        elif kind in ("started", "suspended") and effect.get("class") == "request_input":
            line("⏸", YELLOW, label, "waiting for a person (orchestrator input answer)")
        elif kind == "started" and effect.get("repeat") == "never":
            line("…", RED, label, "started, no result: must not repeat, so resume will not run it again")
        elif kind == "started":
            line("…", YELLOW, label, "started, no result")
        else:
            line("·", DIM, label, kind)


def local_time(stamp):
    return datetime.fromisoformat(stamp).astimezone().strftime("%H:%M:%S") if stamp else ""


def audit(run_id):
    run = Run(run_id)
    print(f"  run {run_id}: {BOLD}{run.state['status']}{OFF}, inputs "
          + " ".join(f"{k}={v}" for k, v in run.header["bound_inputs"].items()))
    last = None
    for name, identity, step in run.steps():
        perform = run.performs.get(Run.site(identity), {})
        value = step.get("value") or {}
        if perform.get("class") == "provider":
            who = run.header["bound_inputs"].get("model", name)
        elif "by" in value:
            who = value["by"]
        else:
            who = " ".join(perform.get("command", [])[1:2]) or name
        attempt = f", on attempt {step['attempt']}" if step.get("attempt", 1) > 1 else ""
        when = local_time(step.get("completed_at") or step.get("started_at")) or "--:--:--"
        if not value and step.get("status") == "running" and perform.get("repeat") == "never":
            value = {"variant": "STARTED", "result": "never reported; must not repeat"}
        print(f"  {DIM}{when}{OFF}  {BOLD}{ROLES.get(name, name):<9}{OFF} by {who}{DIM}{attempt}{OFF}")
        wrapped(" " * 12, value_text(value, compact=True) if value else step.get("status", ""), 12)
        last = value
    outputs = run.state.get("workflow_outputs")
    if outputs and outputs != last:   # ESCALATED and friends; a RECOVERED outcome is the last step
        wrapped(f"  {BOLD}{'outcome':<20}{OFF}", value_text(outputs), 22)


def verdict(run_id, field="variant"):
    run = Run(run_id)
    for _name, identity, step in run.steps():
        if run.performs.get(Run.site(identity), {}).get("class") == "provider" and field in (step.get("value") or {}):
            value = step["value"][field]
            print(value if isinstance(value, str) else json.dumps(value))
            return
    raise SystemExit(f"run {run_id} has no committed model result with {field!r}")


def contract(prompt_path):
    shape = Path(prompt_path).read_text().split("## Output Contract\n", 1)[1]
    first, *rest = shape[shape.index("(\n"):].split("\n|\n")
    print(first)
    print("|  " + "  |  ".join('{ "variant": "%s", … }' % re.search(r'"variant": "(\w+)"', alt).group(1)
                             for alt in rest) + "\n)")


if __name__ == "__main__":
    views = {"memo": memo, "audit": audit, "verdict": verdict, "contract": contract}
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in views:
        raise SystemExit(__doc__)
    views[sys.argv[1]](*sys.argv[2:])
