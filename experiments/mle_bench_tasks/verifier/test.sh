#!/usr/bin/env bash
# The verifier's entry point (Harbor runs /tests/test.sh in the verifier container). It needs only bash and the
# image's python3; grade_submission.py, beside it, writes /logs/verifier/reward.json and ctrf.json, or nothing and a
# non-zero exit when the grader itself fails. Paths: see IN_IMAGE in grade_submission.py.
set -euo pipefail
here=${BASH_SOURCE[0]%/*}
[[ $here == "${BASH_SOURCE[0]}" ]] && here=.
exec python3 -I "$here/grade_submission.py"
