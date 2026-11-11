#!/usr/bin/env python3
"""The on-call console: what the person who gets paged actually sees.

    python3 scripts/console.py            writes artifacts/console.html from every run on disk

One card per run, the ones that need a person first: an approval request
(the exact steps that would run, what the facility's check found, the model's
own words, the evidence, how to answer), an interrupted recovery, an
escalation (why nothing was done, and what to do next), or the record. Every
value on the page is read from the run directory and the runtime's pending
request; the page refreshes itself, so it can sit open beside the terminal.
Self-contained: no network, no scripts.
"""
import fcntl
import html
from datetime import datetime
from pathlib import Path

from show_run import ROLES, Run

OUT = Path("artifacts") / "console.html"
E = html.escape


def local(stamp, fmt="%H:%M:%S"):
    if stamp is None:
        return ""
    when = datetime.fromtimestamp(stamp) if isinstance(stamp, (int, float)) else datetime.fromisoformat(stamp)
    return when.astimezone().strftime(fmt)


def values(run):
    """binding name -> committed value of its latest step."""
    return {name: step.get("value") or {} for name, _identity, step in run.steps()}


def pending_request(run):
    try:
        from orchestrator.host_input import pending
        return pending(run.dir)
    except Exception:   # not suspended, or no host input in this runtime: no request to show
        return None


def live(run):
    """Is a process still writing this run? Probe its writer lock without waiting."""
    with (run.dir / "run.lock").open() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
        return False


def interrupted(run):
    """The must-not-repeat effect that started and never reported, if any."""
    latest = {}
    for record in run.memo():
        if "identity" in record:
            latest[record["identity"]] = record
    for identity, record in latest.items():
        effect = run.performs.get(Run.site(identity), {})
        if record["record"] == "started" and effect.get("repeat") == "never":
            return record
    return None


def classify(run):
    outputs = run.state.get("workflow_outputs") or {}
    if run.state.get("status") == "suspended":
        return "waiting"
    if outputs.get("variant") == "ESCALATED":
        return "escalated"
    if outputs.get("variant") in ("DRY_RUN", "RECOVERED"):
        return "recovered"
    if live(run):
        return "running"
    if interrupted(run):
        return "interrupted"
    return "failed"


BADGE = {"waiting": "Waiting for your approval", "interrupted": "Interrupted during the recovery",
         "escalated": "Escalated to you: nothing was done", "running": "Running",
         "recovered": "Playbook run (dry run)", "failed": "Stopped"}
ORDER = ["waiting", "interrupted", "escalated", "running", "failed", "recovered"]


def link(path, label):
    return f'<a href="../{E(str(path))}">{E(label)}</a>' if path and Path(path).exists() else ""


def prompt_path(run):
    for record in run.memo():
        if record.get("record") == "committed" and run.name(record["identity"]) == "claude":
            return run.dir / Path(record["result_path"]).parent / "prompt.txt"
    return None


def quoted_lines(evidence, limit=6):
    path = Path(evidence) if evidence else None
    if not path or not path.exists():
        return []
    return [line[2:] for line in path.read_text().splitlines() if line.startswith("> ")][:limit]


def evidence_block(verdict):
    lines = quoted_lines(verdict.get("evidence"))
    if not lines:
        return ""
    rows = "".join(f"<li><span class=ok>✓</span> {E(line)}</li>" for line in lines)
    return (f'<h3>Evidence the model cited <span class=dim>(each line found in the log bundle)</span></h3>'
            f'<ul class="quotes">{rows}</ul>')


def words(verdict, model):
    text = verdict.get("fix") or verdict.get("suggestion")
    if not text:
        return ""
    return (f'<p class="words"><span class=dim>The model ({E(model)}), in its own words:</span> “{E(text)}”'
            '<br><span class=dim>Advice only: nothing executes it.</span></p>')


def timeline(run):
    """fetched ✓ · proposed ✓ · checked ✓ · approved ⏸ · acted · : the staircase, as far as it got."""
    done = {name: step.get("status") for name, _identity, step in run.steps()}
    items = []
    for name, role in ROLES.items():
        mark = {"completed": "✓", "failed": "✗", "running": "…", "suspended": "⏸"}.get(done.get(name, ""), "·")
        items.append(f'<span class="t {E(done.get(name) or "pending")}">{mark} {E(role)}</span>')
    return '<div class="timeline">' + "".join(items) + "</div>"


def card(run):
    kind = classify(run)
    found = values(run)
    inputs = run.header["bound_inputs"]
    model = str(inputs.get("model", ""))
    verdict, check = found.get("claude", {}), found.get("check_playbook", {})
    links = " · ".join(filter(None, [link(prompt_path(run), "the prompt it received"),
                                     link(verdict.get("evidence"), "evidence.md"),
                                     link(run.dir / "memo.jsonl", "the full record")]))
    head = (f'<header><span class="badge {kind}">{E(BADGE[kind])}</span>'
            f'<span class="where">{E(str(inputs.get("hutch", "")))} run {E(str(inputs.get("run_number", "")))}'
            f' · {E(local(run.state.get("updated_at")))}</span><span class="id">{E(run.id)}</span></header>')
    body = []

    if kind == "waiting":
        request = pending_request(run) or {}
        steps = "".join(f"<li>{E(step)}</li>" for step in check.get("steps", []))
        checks = "".join(f"<li><span class=ok>✓</span> {E(part.strip())}</li>" for part in check.get("detail", "").split(";"))
        question = request.get("question", "").split("\n\n## Answer Contract")[0]
        answer = (f'python3 -m orchestrator input answer {run.id} {request.get("request_id", "<request id>")} '
                  f"--value '\"APPROVED\"' --by <you>")
        body += [f'<h2>{E(question) or "Run the playbook?"}</h2>',
                 f'<ol class="steps">{steps}</ol>',
                 f'<h3>Checked by the facility, not the model</h3><ul class="checks">{checks}</ul>',
                 words(verdict, model), evidence_block(verdict),
                 '<h3>Your call: is the diagnosis right?</h3>'
                 f'<pre class="answer"><span class=yes>approve</span>  {E(answer)}\n'
                 f'<span class=no>deny</span>     {E(answer.replace("APPROVED", "DENIED"))}</pre>'
                 f'<p class=dim>The steps and the evidence above are frozen with the request: if either '
                 f'changes, the answer is refused. Unanswered, it expires at {E(local(request.get("deadline")))}.</p>']
    elif kind == "interrupted":
        log = next(iter(sorted(Path(verdict.get("evidence", "x")).parent.glob("recovery.log"))), None)
        done = log.read_text().splitlines() if log else []
        body += ['<h2>The recovery started and never reported. The runtime will not run it again.</h2>',
                 '<p>It is declared must-not-repeat: half a recovery is a state only a person can judge.</p>',
                 '<h3>Logged before the interruption</h3><ul class="checks">'
                 + "".join(f"<li>{E(line)}</li>" for line in done) + "</ul>",
                 '<h3>What you can do</h3><ul class="next">'
                 + "".join(f"<li>Read back by hand: <code>{E(step)}</code></li>"
                           for step in check.get("steps", []) if "expect" in step)
                 + '<li>If the stall is gone, record that in the elog and close the incident.</li>'
                 '<li>If not, start a new run: it diagnoses the current state, not this one.</li></ul>']
    elif kind == "escalated":
        reason = run.state["workflow_outputs"].get("reason", "")
        if verdict.get("variant") == "UNLISTED":
            body += ['<h2>No playbook covers what the model found.</h2>',
                     f'<p class="why">{E(verdict.get("summary", ""))}</p>', words(verdict, model),
                     evidence_block(verdict),
                     '<h3>What you can do</h3><ul class="next">'
                     '<li>Decide on the model’s suggestion and act by hand: nothing will run on its own.</li>'
                     '<li>If this will happen again, add a playbook and a cause for it in '
                     '<code>scripts/playbooks.py</code>, with preconditions the check can read.</li></ul>']
        elif check.get("variant") == "BLOCKED":
            body += [f'<h2>The model said {E(verdict.get("cause", ""))} on {E(verdict.get("target", ""))}. '
                     'The check blocked it.</h2>',
                     f'<p class="why">{E(check.get("detail", ""))}</p>', words(verdict, model), evidence_block(verdict)]
        elif verdict.get("variant") == "INCONCLUSIVE":
            body += ['<h2>The model could not determine a cause.</h2>',
                     f'<p>Checked: {E(", ".join(verdict.get("checked", [])))}</p>',
                     f'<p>Missing: {E(", ".join(verdict.get("missing", [])))}</p>']
        else:
            body += [f'<h2>{E(reason)}</h2>']
    elif kind == "recovered":
        outputs = run.state["workflow_outputs"]
        answer = found.get("ask_daq_oncall", {})
        body += [f'<h2>{E(outputs.get("summary", ""))}</h2>',
                 f'<p>Approved by <b>{E(answer.get("by", ""))}</b>; proposed by {E(model)}; '
                 f'checked by scripts/check_playbook.py ({E(check.get("detail", ""))}).</p>']
    elif kind == "running":
        body += ['<h2>Working…</h2>']
    else:
        error = run.state.get("error") or {}
        body += [f'<h2>{E(error.get("code", "stopped"))}</h2><p>{E(error.get("message", ""))}</p>']

    return kind, (f'<article class="{kind}">{head}{"".join(body)}{timeline(run)}'
                  f'<footer>{links}</footer></article>')


CSS = """
:root{--bg:#12161C;--panel:#1B2029;--line:#2C3440;--text:#F3F1EA;--soft:#B8C0CC;--orange:#E8833A;
--amber:#E8C547;--blue:#6FA8E8;--red:#E86A5A;--mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}.summary{color:var(--soft);margin:0 0 24px}
article{background:var(--panel);border:1px solid var(--line);border-left:6px solid var(--line);
border-radius:10px;padding:18px 20px;margin:0 0 16px}
article.waiting{border-left-color:var(--amber)}article.escalated{border-left-color:var(--orange)}
article.interrupted{border-left-color:var(--red)}article.recovered{border-left-color:var(--blue)}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:baseline}
.badge{font-weight:700;text-transform:uppercase;letter-spacing:.06em;font-size:13px;padding:3px 10px;
border-radius:999px;background:var(--line)}
.badge.waiting{background:var(--amber);color:var(--bg)}.badge.escalated{background:var(--orange);color:var(--bg)}
.badge.interrupted{background:var(--red);color:var(--bg)}.badge.recovered{background:var(--blue);color:var(--bg)}
.where{color:var(--soft)}.id{margin-left:auto;font:13px var(--mono);color:var(--soft)}
h2{font-size:20px;margin:14px 0 8px}h3{font-size:14px;text-transform:uppercase;letter-spacing:.05em;
color:var(--soft);margin:16px 0 6px}
ol.steps{margin:0;padding-left:24px;font-size:17px}ul{margin:0;padding-left:0;list-style:none}
ul.next{padding-left:18px;list-style:disc}
.quotes li,.checks li{font:13px/1.6 var(--mono);color:var(--soft);overflow-wrap:anywhere}
.ok{color:var(--blue)}.dim{color:var(--soft);font-weight:400;text-transform:none;letter-spacing:0}
.why{color:var(--orange);font-weight:600}.words{border-left:3px solid var(--line);padding-left:12px}
pre.answer{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;
font:13px/1.7 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere}
.yes{color:var(--blue);font-weight:700}.no{color:var(--orange);font-weight:700}
.timeline{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:14px;font:13px var(--mono);color:var(--soft)}
.t.completed{color:var(--text)}.t.failed,.t.running,.t.suspended{color:var(--amber)}
footer{margin-top:10px;font-size:14px;color:var(--soft)}a{color:var(--blue)}
code{font:14px var(--mono)}
"""


def main():
    root = Path(".orchestrate") / "runs"
    runs = sorted((p.name for p in root.iterdir() if (p / "state.json").exists()), reverse=True) if root.exists() else []
    cards = [card(Run(run_id)) for run_id in runs]
    cards.sort(key=lambda item: ORDER.index(item[0]))
    counts = {kind: sum(1 for k, _ in cards if k == kind) for kind in ORDER}
    summary = " · ".join(f"{n} {BADGE[k].split(':')[0].lower()}" for k, n in counts.items() if n) or "no runs yet"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="2">
<title>TMO DAQ agent · on-call</title><style>{CSS}</style></head><body><main>
<h1>TMO DAQ agent · on-call</h1><p class="summary">{E(summary)} · updated {E(datetime.now().strftime("%H:%M:%S"))}</p>
{"".join(html_ for _, html_ in cards)}
</main></body></html>
""")
    print(f"console: {OUT} ({summary})")


if __name__ == "__main__":
    main()
