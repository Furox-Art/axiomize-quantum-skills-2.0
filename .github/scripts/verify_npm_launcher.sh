#!/usr/bin/env bash
# Manual verification of the npm launcher. Mirrors what the `npm-contract` CI
# job runs, so a contributor can reproduce the gate locally.
#
# Run from anywhere: the repository root is resolved with git, not with $0, so
# a Windows-style absolute path handed in by a shell does not confuse the cd.
set -u

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT" || exit 1

# Honour an explicit interpreter so a virtualenv is not shadowed by PATH order.
export AXIOMIZE_PYTHON="${AXIOMIZE_PYTHON:-python3}"

rc=0
report() {
  local label="$1" code="$2"
  echo "$label -> $code"
  [ "$code" -ne 0 ] && rc=1
  return 0
}

node --check index.js >/dev/null 2>&1
report "node --check index.js" $?

node --check bin/axiomize-quantum.js >/dev/null 2>&1
report "node --check bin/axiomize-quantum.js" $?

node index.js --help >/dev/null 2>&1
report "node index.js --help" $?

node bin/axiomize-quantum.js --help >/dev/null 2>&1
report "node bin/axiomize-quantum.js --help" $?

exit $rc
