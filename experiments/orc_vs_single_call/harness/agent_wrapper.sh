#!/bin/bash
# Transparent wrapper around the real claude CLI: same arguments, same prompt.
# Records the prompt, the output, and every candidate repository's patch after the call.
REAL=/home/ollie/.local/bin/claude
mkdir -p "$TRIAL_ROOT/.shim/calls"
n=$(( $(ls "$TRIAL_ROOT/.shim/calls" | wc -l) + 1 ))
dir="$TRIAL_ROOT/.shim/calls/$n"
mkdir -p "$dir"
cat > "$dir/prompt.txt"
# The runtime names the result file relative to the run workspace and does not clear it between
# calls. Give the agent an absolute path and remove any earlier result, so a call that delivers
# nothing cannot be read as a repeat of the previous one.
if [ -n "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH" ]; then
  relative_bundle="$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
  case "$relative_bundle" in /*) ;; *) export ORCHESTRATOR_OUTPUT_BUNDLE_PATH="$PWD/$relative_bundle";; esac
  rm -f "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
fi
start=$(date +%s)
"$REAL" "$@" < "$dir/prompt.txt" > "$dir/stdout.txt" 2> "$dir/stderr.txt"
status=$?
cat "$dir/stdout.txt"
for repo in "$TRIAL_ROOT"/cand*; do
  [ -e "$repo/.git" ] || continue
  ( cd "$repo" && git add -A -N . >/dev/null 2>&1; git diff --binary "$(cat "$TRIAL_ROOT/baseline")" > "$dir/patch-$(basename "$repo").diff"; git reset -q >/dev/null 2>&1 )
done
echo "status=$status seconds=$(( $(date +%s) - start ))" > "$dir/meta"
exit $status
