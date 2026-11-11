#!/usr/bin/env bash
# Five moments, one workflow, one terminal, one on-call console. ~12 minutes.
# Run 412 from the page to the recovery (1-4), then the next page, run 431 (5).
#
#   AO_REPO=/path/to/agent-orchestration ./demo.sh                   # replayed model (rehearsal)
#   AO_REPO=... PROVIDER=real ./demo.sh                               # the real `claude`, confined
#   AO_REPO=... PROVIDER=real MODEL=claude-sonnet-5-5 ./demo.sh       # another model under test
#   DEMO_NOPAUSE=1 ./demo.sh                                          # no "press enter" stops, no browser
#
# Requirements: Linux or macOS, python3 >= 3.11 with jsonschema and PyYAML importable, a checkout
# of agent-orchestration at $AO_REPO with the Python frontend and durable host input (on macOS:
# the fix/py-frontend-macos fixes), and for PROVIDER=real a working `claude` CLI.
set -u
cd "$(dirname "$0")"
KIT="$PWD"
: "${AO_REPO:=$KIT/../agent-orchestration}"
: "${PROVIDER:=fake}"
export PYTHONPATH="$AO_REPO${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1   # streamed actuator output reaches the screen as it arrives
python3 -c "from orchestrator.py import ask" 2>/dev/null || {
  echo "cannot import orchestrator.py with durable host input (ask) from AO_REPO=$AO_REPO"; exit 1; }
if [ "$PROVIDER" = fake ]; then export PATH="$KIT/bin:$PATH"
else command -v claude >/dev/null || { echo "PROVIDER=real needs claude on PATH"; exit 1; }
     export PATH="$KIT/confine:$PATH"; fi   # the model step runs under Claude Code permission rules

WF=workflows/daq_diagnosis.py
ENTRY=diagnose_and_recover
FLAGS=(--entry-workflow "$ENTRY" --provider-externs-file inputs/providers.json --command-boundaries-file inputs/commands.json)
RUNFLAGS=("${FLAGS[@]}")
[ -n "${MODEL:-}" ] && RUNFLAGS+=(--input "model=$MODEL")   # else the model named in inputs/*.json
ORC=(python3 -m orchestrator)
PLAYBOOKS=scripts/playbooks.py

bold()   { printf '\n\033[1m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }
quo()    { echo; printf 'status quo: %s\n' "$*" | fold -s -w 100 | sed $'s/^/  \033[35m/; s/$/\033[0m/'; }
cmd()    { printf '\033[36m$ %s\033[0m\n' "$*"; }
show()   { cmd "$*"; "$@"; }
indent() { sed 's/^/  /'; }
rule()   { printf '  \033[2m── %s ──\033[0m\n' "$*"; }
levels() { sed -e $'s/.*<E>.*/\033[31m&\033[0m/' -e $'s/.*<W>.*/\033[33m&\033[0m/'; }
tidy() {  # drop the logger's timestamp prefix and shorten digests; make the runtime's [codes] and refusals stand out
  local line re='^[0-9-]+ [0-9:,]+ - [A-Za-z_.]+ - [A-Z]+ - (.*)$'
  while IFS= read -r line; do
    [[ $line =~ $re ]] && line="${BASH_REMATCH[1]}"
    line=$(sed -E 's/(sha256:[0-9a-f]{12})[0-9a-f]{52}/\1…/g' <<<"$line")
    case "$line" in
      "["*"]"*|*shown_evidence_changed*) printf '\033[1;31m%s\033[0m\n' "$line" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done
}
orc_run() {  # orc_run <input file>: build the Python workflow and run it; its output only if it fails
  cmd "python3 -m orchestrator py run $WF --input-file $1 …"
  local log; log=$(mktemp)
  "${ORC[@]}" py run "$WF" "${RUNFLAGS[@]}" --input-file "$1" >"$log" 2>&1 || tidy <"$log"
  rm -f "$log"
}
orc_resume() { cmd "python3 -m orchestrator resume $1"; "${ORC[@]}" resume "$1" --stream-output 2>&1 | tidy; }
request_id() { "${ORC[@]}" input get "$1" 2>/dev/null | python3 -c 'import json, sys; print(json.load(sys.stdin)["request_id"])'; }
answer() {   # answer <run> <APPROVED|DENIED> <who>: what the console's Approve button would do
  local id; id=$(request_id "$1")
  cmd "python3 -m orchestrator input answer $1 ${id:0:19}… --value '\"$2\"' --by $3"
  "${ORC[@]}" input answer "$1" "$id" --value "\"$2\"" --by "$3" 2>&1 | tidy
}
runs_now()   { ls .orchestrate/runs 2>/dev/null; }
new_run()    { runs_now | grep -vxF -e "$1" | tail -1; }   # new_run "<runs before>"
memo()       { python3 scripts/show_run.py memo "$1"; }
verdict()    { python3 scripts/show_run.py verdict "$@"; }
pause() { if [ -z "${DEMO_NOPAUSE:-}" ]; then printf '\n\033[2m[enter]\033[0m'; read -r _ </dev/tty; fi; echo; }
OPENED=
console() {  # console "<what to look at>": refresh the on-call page; open it the first time
  python3 scripts/console.py >/dev/null
  if [ -z "$OPENED" ] && [ -z "${DEMO_NOPAUSE:-}" ] && [ "${DEMO_BROWSER:-1}" = 1 ]; then
    open artifacts/console.html 2>/dev/null || xdg-open artifacts/console.html >/dev/null 2>&1
    OPENED=1
  fi
  printf '\033[1;34m  ▸ console (artifacts/console.html): %s\033[0m\n' "$*"
}
model_reply() {  # model_reply <run> <replay dir>: the first lines of what the model said, and where it came from
  local step; step=$(dirname "$(ls .orchestrate/runs/$1/effects/*/attempt-1/prompt.txt)")
  if [ "$PROVIDER" = fake ]; then
    dim "the model's reply (stdout.txt; replayed from $(grep -o 'orchestrator run [0-9TZ]*-[a-z0-9]*' "$2/SOURCE"), claude-opus-5-5)."
  else
    dim "the model's reply (stdout.txt; live)."
  fi
  dim "Nothing in the workflow reads it; only the typed result routes:"
  fold -s -w 96 "$step/stdout.txt" | grep -v '^[[:space:]]*$' | head -n 6 | indent
  echo "  …"
}

if [ "$PROVIDER" = fake ]; then WHO="replayed recordings of claude-opus-5-5 (rehearsal/replay/*/SOURCE); PROVIDER=real runs one live"
else WHO="live ${MODEL:-claude-opus-5-5}, confined by confine/claude"; fi
dim "Reset: removing previous runs and artifacts (builds are kept). Model: $WHO"
rm -rf .orchestrate/runs artifacts
CHECK_LOG=$(mktemp)
"${ORC[@]}" py check "$WF" "${FLAGS[@]}" >/dev/null 2>"$CHECK_LOG" || {
  cat "$CHECK_LOG"; rm -f "$CHECK_LOG"
  echo "py check failed. On macOS the Python frontend needs the fix/py-frontend-macos branch of agent-orchestration."
  exit 1; }
rm -f "$CHECK_LOG"

# ---------------------------------------------------------------------------
bold "02:13 at TMO. Run 412 stalls."
dim  "What DAQ on-call is paged with: the elog, the XPM's readout group 0, the control log."
tail -n 2 fixtures/stall-412/shift.log | indent
grep -E "^DAQ:.*(L0AccRate|DeadFrac) " fixtures/stall-412/xpm.txt | indent
tail -n 3 fixtures/stall-412/control.log | levels | indent
echo
dim  "Two questions: why, and who may change the DAQ to fix it? The agent that answers is one Python"
dim  "file, one prompt, and the on-call playbooks it may propose (scripts/playbooks.py)."
dim  "(Commands are shown without their binding-file flags; demo.sh has them in full.)"
pause

# ---------------------------------------------------------------------------
bold "1 · How is it built, and what will it touch?   (before anything runs)"
dim  "Typed Python. Effects are calls; every branch is a match over a typed result, and each arm"
dim  "nests the next effect. A person's answer is one of them. Nothing routes on the model's prose."
sed -n '/^@proc/,$p' $WF | sed -E \
  -e $'s/(daq_logs|claude|check_playbook|ask_daq_oncall|daq_recover|ask)\\(/\033[1;36m\\1\033[0m(/g' \
  -e $'s/([A-Z]{5,})=lambda/\033[1;33m\\1\033[0m=lambda/g' | indent
pause
dim  "py build traces that into ordinary Workflow Lisp and compiles it. The compiler's own site table:"
cmd "python3 scripts/check_effects.py $WF"
python3 scripts/check_effects.py $WF $ENTRY "${FLAGS[@]:2}"
echo
dim  "The model's own tools are bounded separately, by Claude Code's permission rules (confine/claude):"
sed -n '/^policy = /,/result.json)"\]/p' confine/claude | grep -v '^ *#' | indent
dim  "recorded in rehearsal (rehearsal/refused.txt): a model reaching for a shell, and the rule refusing it:"
indent < rehearsal/refused.txt
quo "a SKILL.md says in prose what the agent should do; its harness hands it a shell, and nothing lists what it can touch before it runs."
pause

# ---------------------------------------------------------------------------
bold "2 · What did the model see, and what is DAQ on-call asked?"
dim  "Run it on run 412. It stops where a person has to decide."
[ "$PROVIDER" = real ] && dim "(the model is reading the bundle: a minute or two, live)"
BEFORE=$(runs_now); orc_run inputs/run_412.json; RUN_A=$(new_run "$BEFORE")
dim "(exit 0: the run is suspended, waiting for a person; it has not failed)"
PROMPT=$(ls .orchestrate/runs/$RUN_A/effects/*/attempt-1/prompt.txt)
BUNDLE_DIR=$(dirname "$(verdict "$RUN_A" evidence)")
echo
dim "the composed prompt, on disk at .orchestrate/runs/$RUN_A/effects/…/prompt.txt ($(wc -l <"$PROMPT" | tr -d ' ') lines)"
rule "injected by the runtime: the log bundle the first effect fetched ($(grep -c '^==== [^ ]* ====$' "$BUNDLE_DIR/bundle.txt") sources)"
sed -n '3,5p' "$PROMPT" | indent
echo "  …"
rule "authored: workflows/prompts/diagnose.md, fills substituted (excerpt)"
sed -n '/^Decide what is stalling/,/^what you checked/p' "$PROMPT" | indent
echo "  …"
rule "appended by the runtime, from the declared types (excerpt)"
python3 scripts/show_run.py contract "$PROMPT" | sed -E $'/"cause"|"target"|must_exist|"variant"/s/.*/\033[33m&\033[0m/' | indent
echo
model_reply "$RUN_A" rehearsal/replay/412
echo
dim "what came back, and what the runtime did with it (the memo of run $RUN_A):"
memo "$RUN_A"
echo
dim "the check does not judge the diagnosis. It confirmed every quoted line is in the bundle, and that the"
dim "proposed playbook's preconditions hold on its target, read from the XPM's own link PVs."
echo
dim "the request DAQ on-call sees (python3 -m orchestrator input get $RUN_A):"
"${ORC[@]}" input get "$RUN_A" | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("  " + r["question"].split("\n\n## Answer Contract")[0])
for s in r["show"]:
    print("  attached, frozen: " + s["path"])'
console "run 412 waits for DAQ on-call: the steps, what was checked, the model's words, the evidence"
quo "the output format is a paragraph in a SKILL.md, and approval is a thumbs-up on the agent's summary, not on the steps that will run."
pause

# ---------------------------------------------------------------------------
bold "3 · Change it under the pending approval."
dim  "Run 412 is waiting for DAQ on-call. Two things change while it waits."
EVIDENCE=$(verdict "$RUN_A" evidence)
EVIDENCE_COPY=$(mktemp); cp "$EVIDENCE" "$EVIDENCE_COPY"
PLAYBOOKS_COPY=$(mktemp); cp $PLAYBOOKS "$PLAYBOOKS_COPY"
restore() { cp "$EVIDENCE_COPY" "$KIT/$EVIDENCE"; cp "$PLAYBOOKS_COPY" "$KIT/$PLAYBOOKS"; }
trap restore EXIT                              # never leave an edit behind, even on ^C
trap 'restore; exit 130' INT TERM HUP
echo
dim "1. Someone adds a line to the model's evidence file:"
cmd "echo '> link 4 checked by hand, all good' >> $EVIDENCE"
echo '> link 4 checked by hand, all good' >> "$EVIDENCE"
answer "$RUN_A" APPROVED tmo-daq-oncall
dim "refused: DAQ on-call would be approving a request they were not shown. (restored)"
cp "$EVIDENCE_COPY" "$EVIDENCE"
echo
dim "2. Someone edits the deadtime_link playbook, swapping the KCU timing reset for a node power cycle:"
python3 - "$PLAYBOOKS" <<'EOF'
import sys; p = sys.argv[1]; s = open(p).read()
old = 'TxPhyPllReset on the KCU1500 timing link (devGui); if LinkRxReady stays 0, "\n        "switch timing to xpmmini and back to LCLS2'
assert s.count(old) == 1, "playbook text moved; update demo.sh"
open(p, "w").write(s.replace(old, 'power-cycle the node (psipmi power cycle)', 1))
EOF
printf '  \033[31m- %s\033[0m\n  \033[32m+ %s\033[0m\n' \
  "{host}: TxPhyPllReset on the KCU1500 timing link (devGui); if LinkRxReady stays 0, ..." \
  "{host}: power-cycle the node (psipmi power cycle)"
orc_resume "$RUN_A"
dim "refused: the check that produced the steps being approved ran against the old playbook. (reverted)"
cp "$PLAYBOOKS_COPY" $PLAYBOOKS
quo "an approval in a chat thread is not tied to what it approved: change the evidence or the playbook after the request, and the old yes runs the new steps."
pause

# ---------------------------------------------------------------------------
bold "4 · DAQ on-call says yes. Then the power goes out."
dim  "DAQ on-call reads the request in the console, judges the diagnosis, and answers:"
answer "$RUN_A" APPROVED tmo-daq-oncall
echo
dim "Resume: the playbook runs one step at a time (dry run). Mid-way, the machine running it loses power:"
cmd "python3 -m orchestrator resume $RUN_A"
RECOVERY_LOG=$BUNDLE_DIR/recovery.log
RESUME_LOG=$(mktemp)
# own process group, so one kill takes the run and everything it started (portable: no setsid needed)
DEMO_STEP_SECONDS=3 python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
  "${ORC[@]}" resume "$RUN_A" --stream-output >"$RESUME_LOG" 2>&1 &
BG=$!
disown $BG
for _ in $(seq 1 150); do grep -q "step 2/" "$RECOVERY_LOG" 2>/dev/null && break; sleep 0.2; done
sleep 1
kill -9 -- -$BG
sleep 1
cmd "kill -9 (the resume, during step 2)"
dim "what the actuator had logged when it died:"
indent < "$RECOVERY_LOG"
echo
orc_resume "$RUN_A"
dim "refused: daq_recover is declared must-not-repeat. Half a recovery is a state only a person can judge."
echo
memo "$RUN_A"
echo
dim "the record: who proposed, what checked it, who approved, what acted and how far it got"
python3 scripts/show_run.py audit "$RUN_A"
console "run 412: interrupted during the recovery; what was logged, what to check by hand, what to do next"
quo "after a restart the agent retries its last command, or nobody knows how far it got."
pause

# ---------------------------------------------------------------------------
bold "5 · The next page."
dim  "03:40, same night. The elog since run 412:"
sed -n '3,$p' fixtures/stall-431/shift.log | indent
dim  "Same symptom as run 412. The reflex is to rerun what fixed it."
[ "$PROVIDER" = real ] && dim "(the model is reading the bundle: a minute or two, live)"
BEFORE=$(runs_now); orc_run inputs/run_431.json; RUN_Q=$(new_run "$BEFORE")
echo
memo "$RUN_Q"
echo
case "$(verdict "$RUN_Q")" in
  UNLISTED)
    dim "No playbook covers what the model found, and it said so instead of forcing a label:"
    printf '%s\n' "$(verdict "$RUN_Q" summary)" | fold -s -w 94 | indent
    dim "its suggestion, for a person:"
    printf '%s\n' "$(verdict "$RUN_Q" suggestion)" | fold -s -w 94 | indent
    dim "Escalated; nothing ran. (In rehearsal every model answered UNLISTED here: rehearsal/TRIALS.md.)" ;;
  DIAGNOSED)
    dim "It proposed $(verdict "$RUN_Q" cause) on $(verdict "$RUN_Q" target); the check read the target's own state and blocked it." ;;
  *)
    dim "It could not decide, and said what it checked and what it would need. Escalated." ;;
esac
console "run 431 is escalated: what the model found, what it suggests, what DAQ on-call can do"
quo "the agent that holds the tools reruns last night's fix because the symptom matches, or acts on its own suggestion, on an HSD this partition no longer owns."

bold "Done. What you saw:"
echo "  1  every effect, a person's answer among them, known from typed Python before anything ran;"
echo "     the model's own tools bounded by permission rules, and a recorded refusal"
echo "  2  the model's prompt and typed contract on disk, and a request DAQ on-call can actually judge"
echo "  3  an answer refused when the evidence changed, a resume refused when the playbook did"
echo "  4  an approval by a named person, and a half-run recovery that is never repeated on its own"
echo "  5  a fault outside the playbooks: the model said so, and it went to a person, not to a label"
echo
dim "Runs on disk: $(runs_now | tr '\n' ' ')"
