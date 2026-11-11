#!/usr/bin/env bash
# Rehearsal check: run the whole demo with the replayed model and assert each moment's payoff,
# then run the uninterrupted path (approve, resume, playbook completes) on its own.
#
#   AO_REPO=/path/to/agent-orchestration tests/smoke.sh
set -u
cd "$(dirname "$0")/.."
: "${AO_REPO:=$PWD/../agent-orchestration}"
FILES=(scripts/playbooks.py workflows/daq_diagnosis.py workflows/prompts/diagnose.md)
before=$(cksum "${FILES[@]}")
out=$(DEMO_NOPAUSE=1 PROVIDER=fake AO_REPO="$AO_REPO" ./demo.sh 2>&1 | sed $'s/\x1b\\[[0-9;]*m//g')
fail=0
expect() {
  if grep -qF -- "$2" <<<"$out"; then printf 'ok    %s\n' "$1"
  else printf 'FAIL  %s: missing %q\n' "$1" "$2"; fail=1; fi
}
in_order() {  # in_order <what> <first> <second>: both appear, first before second
  local a b; a=$(grep -nF -- "$2" <<<"$out" | head -1 | cut -d: -f1); b=$(grep -nF -- "$3" <<<"$out" | head -1 | cut -d: -f1)
  if [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; then printf 'ok    %s\n' "$1"
  else printf 'FAIL  %s: %q not before %q\n' "$1" "$2" "$3"; fail=1; fi
}

expect "0: the stall"                              "Run 412 stalls."
expect "0: the replay is labelled"                 "Model: replayed recordings of claude-opus-5-5"
expect "1: a person's answer is an effect"         "ask_daq_oncall  DIAGNOSED → APPLICABLE"
expect "1: the proof path"                         "reachable only through DIAGNOSED → APPLICABLE → ANSWERED → APPROVED"
expect "1: the model step is confined"             '"--permission-mode", "dontAsk"'
expect "1: a recorded refusal"                     "No such tool available: Bash"
expect "2: the run waits for a person"             "waiting for a person"
expect "2: the reply says where it came from"      "replayed from orchestrator run"
expect "2: the request shows frozen files"         "attached, frozen: artifacts/daq/412/"
expect "2: the check read the link PVs"            "link 4 to drp-srcf-cmp026 is the o"
expect "3: evidence edit refuses the answer"       "shown_evidence_changed"
expect "3: playbook edit refuses the resume"       "[effect_input_diverged]"
expect "4: the answer is recorded with who"        '"by": "tmo-daq-oncall", "value": "APPROVED"'
expect "4: the actuator got part way"              "step 2/4"
expect "4: the interrupted actuator is not rerun"  "[lexical_restore_pending_effect_unsafe]"
expect "5: a cause outside the playbooks"          "UNLISTED"
expect "5: escalated, nothing ran"                 'ESCALATED reason="no playbook covers the cause the model found"'
expect "console written"                           "console (artifacts/console.html)"
in_order "412 runs to the end before the next page" "4 · DAQ on-call says yes" "5 · The next page."
for card in "Interrupted during the recovery" "Escalated to you"; do
  grep -q "$card" artifacts/console.html 2>/dev/null && echo "ok    console: $card" \
    || { echo "FAIL  console: $card"; fail=1; }
done
[ "$(cksum "${FILES[@]}")" = "$before" ] || { echo "FAIL  a demo edit was left behind"; fail=1; }

# the uninterrupted path: approve, resume, the playbook runs to the end
export PYTHONPATH="$AO_REPO" PATH="$PWD/bin:$PATH"
F=(--entry-workflow diagnose_and_recover --provider-externs-file inputs/providers.json --command-boundaries-file inputs/commands.json)
seen=$(ls .orchestrate/runs)
python3 -m orchestrator py run workflows/daq_diagnosis.py "${F[@]}" --input-file inputs/run_412.json >/dev/null 2>&1
run=$(ls .orchestrate/runs | grep -vxF -e "$seen" | tail -1)
id=$(python3 -m orchestrator input get "$run" | python3 -c 'import json, sys; print(json.load(sys.stdin)["request_id"])')
python3 -m orchestrator input answer "$run" "$id" --value '"APPROVED"' --by smoke >/dev/null 2>&1
python3 -m orchestrator resume "$run" >/dev/null 2>&1
outcome=$(python3 -c "import json; print(json.load(open('.orchestrate/runs/$run/state.json')).get('workflow_outputs'))")
case "$outcome" in
  *DRY_RUN*) echo "ok    approved run completes: $outcome" ;;
  *) echo "FAIL  approved run completes: $outcome"; fail=1 ;;
esac
python3 scripts/console.py >/dev/null && grep -q "Playbook run (dry run)" artifacts/console.html \
  && echo "ok    console: Playbook run (dry run)" || { echo "FAIL  console: Playbook run (dry run)"; fail=1; }

[ $fail = 0 ] || { echo; echo "full output:"; echo "$out" | tail -60; }
exit $fail
