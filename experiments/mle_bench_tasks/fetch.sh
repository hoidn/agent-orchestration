#!/usr/bin/env bash
# Download and prepare MLE-bench competitions with the owner's Kaggle token (family plan M10; Task 10a). The one
# command of this line that reads the token, and it never reads it itself: it gives the benchmark's tool the
# token's directory and nothing else.
#
#   KAGGLE_CONFIG_DIR=<token dir> fetch.sh <slug>...
#
# For each slug it runs `~/lh-cache/mle/venv/bin/python -I -m mlebench.cli prepare -c <slug> --data-dir
# ~/mle-cache/prepared` (the benchmark's own environment, never a program found on PATH) and prints one fixed line,
# `<slug>: done`, `<slug>: rules not accepted or download failed` or `<slug>: no room` (the lower free space of the
# data directory and the token directory unreadable or under the ladder's 20 GB floor; the tool is not started).
# Exit 0 when every slug is done, 1 otherwise.
#
# The tool runs with every KAGGLE_* variable unset but KAGGLE_CONFIG_DIR (so the client reads kaggle.json from the
# token directory and nothing else steers it), in a new session with standard input from /dev/null (no terminal
# to read or write, so the rules question gets end of file), with its working and temporary directories inside the
# token directory, no core dumps, and its standard output and error in <token dir>/fetch-<slug>.log, made afresh
# with mode 600. The pane sees only the fixed lines. INT, TERM or HUP stops the tool's process group with fetch.sh
# (TERM, then KILL after 3 seconds; exit 130).
#
# Refuses (exit 2, one line on stderr, nothing started): KAGGLE_CONFIG_DIR unset, empty or relative, or not the
# token directory's own path (a link anywhere in it, `.` or `..`); a token directory that is not a directory of
# mode 700 or lies inside a git repository (or git cannot tell); a kaggle.json that is not a regular file of mode
# 600 (a link included); a tmp in the token directory that is a link; no benchmark python; no slug, or a name that
# is not a slug. The checks run inside the token directory, on the paths then used.
set -u
umask 077
ulimit -c 0

refuse() { echo "fetch.sh: $1" >&2; exit 2; }

dir=${KAGGLE_CONFIG_DIR:-}
dir=${dir%/}
[[ $dir == /* ]] || refuse "KAGGLE_CONFIG_DIR is not set to an absolute path"
cd -P -- "$dir" 2>/dev/null || refuse "cannot enter the token directory"
[ "$(pwd -P)" = "$dir" ] || refuse "KAGGLE_CONFIG_DIR is not the token directory's own path (a link, . or ..)"
[ "$(stat -c '%a %F' -- .)" = "700 directory" ] || refuse "the token directory is not a directory of mode 700"
[ "$(stat -c '%a %F' -- kaggle.json 2>/dev/null)" = "600 regular file" ] || refuse "kaggle.json is not a regular file of mode 600"
git rev-parse >/dev/null 2>&1; [ $? -eq 128 ] || refuse "the token directory is inside a git repository, or git cannot tell"
[ ! -L tmp ] || refuse "tmp in the token directory is a link"
python=$HOME/lh-cache/mle/venv/bin/python
[ -f "$python" ] && [ -x "$python" ] || refuse "the benchmark's python (~/lh-cache/mle/venv/bin/python) is missing"
[ $# -gt 0 ] || refuse "no competition named"
for slug; do
  [[ $slug =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || refuse "a name that is not a competition slug"
done

data=$HOME/mle-cache/prepared
mkdir -p -- "$data" tmp 2>/dev/null || refuse "cannot create the data or temporary directory"
unset "${!KAGGLE_@}"
export KAGGLE_CONFIG_DIR=$dir TMPDIR=$dir/tmp

floor=20000000000  # the ladder's free-disk floor, 20 GB (family plan M9)
pid=
stop() {
  if [ -n "$pid" ]; then
    kill -TERM -- "-$pid" 2>/dev/null
    sleep 3
    kill -KILL -- "-$pid" 2>/dev/null
  fi
  exit 130
}
trap stop INT TERM HUP
status=0
for slug; do
  free=$(df --output=avail -B1 -- "$data" "$dir" 2>/dev/null | tail -n +2 | sort -n | head -n 1)
  if ! [[ $free =~ ^[0-9]+$ ]] || [ "$free" -lt "$floor" ]; then
    echo "$slug: no room"; status=1; continue
  fi
  log=fetch-$slug.log
  rm -f -- "$log"  # a link or an open file left in its place receives nothing
  # setsid: the tool leads its own session and process group, with no controlling terminal; $! is its pid.
  setsid "$python" -I -m mlebench.cli prepare -c "$slug" --data-dir "$data" </dev/null >"$log" 2>&1 &
  pid=$!
  if wait "$pid" 2>/dev/null; then echo "$slug: done"; else echo "$slug: rules not accepted or download failed"; status=1; fi
  pid=
done
exit "$status"
