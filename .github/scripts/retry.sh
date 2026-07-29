#!/usr/bin/env bash
# Retry wrapper for CI steps that reach the network.
#
# Every external dependency this project builds against fails
# intermittently: raw.githubusercontent.com, PyPI, npm, the GitHub API
# behind `gh`, the git clones assemble.py and ESPHome perform, and the font
# and toolchain downloads inside a compile. Nightly run 30435668438 is the
# canonical case — one ConnectionResetError fetching a webfont failed a
# device that had compiled cleanly the day before, and the report job then
# went to file a [broken] issue for it.
#
# Usage:
#   source .github/scripts/retry.sh
#   retry <command> [args...]
#
# All diagnostics go to stderr, so `VAR=$(retry curl ...)` captures only the
# command's own output.
#
# Defaults to 4 attempts with 5s/15s/45s backoff. Override per step with
# RETRY_ATTEMPTS / RETRY_INITIAL_DELAY — expensive commands (a full device
# compile) are worth fewer attempts than a one-second fetch.

retry() {
  local max_attempts="${RETRY_ATTEMPTS:-4}"
  local delay="${RETRY_INITIAL_DELAY:-5}"
  local attempt=1
  local status

  while true; do
    # Running the command as an `if` condition keeps a failed attempt from
    # tripping `set -e` in the calling step (GitHub runs steps as `bash -e`).
    # The status has to be read inside the `else` — an `if` whose condition
    # fails and which has no else branch is itself a *success*, so reading
    # $? after the `fi` would report 0 for every failed attempt.
    if "$@"; then
      if [ "$attempt" -gt 1 ]; then
        echo "retry: '$1' succeeded on attempt $attempt" >&2
      fi
      return 0
    else
      status=$?
    fi

    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "retry: '$1' failed after $attempt attempt(s), last exit $status" >&2
      return "$status"
    fi

    echo "retry: '$1' failed (exit $status) — attempt $attempt/$max_attempts," \
      "retrying in ${delay}s" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 3))
  done
}

# Sourced by workflow steps; executed directly only to self-test.
if [ "${BASH_SOURCE[0]}" = "$0" ] && [ "${1:-}" = "--self-test" ]; then
  set -u
  _st_failures=0

  _st_check() {
    if [ "$2" = "$3" ]; then
      echo "  ok: $1"
    else
      echo "  FAIL: $1 (expected '$3', got '$2')" >&2
      _st_failures=$((_st_failures + 1))
    fi
  }

  echo "retry.sh self-test"

  # A command that succeeds first time runs exactly once.
  _st_calls=0
  _st_always_ok() { _st_calls=$((_st_calls + 1)); return 0; }
  RETRY_INITIAL_DELAY=0 retry _st_always_ok
  _st_check "success runs once" "$_st_calls" "1"

  # A command that recovers is retried until it does, and reports success.
  _st_calls=0
  _st_flaky() { _st_calls=$((_st_calls + 1)); [ "$_st_calls" -ge 3 ]; }
  RETRY_INITIAL_DELAY=0 retry _st_flaky
  _st_check "flaky command retried to success" "$_st_calls" "3"

  # Exhausting the attempts propagates the command's own exit status, so a
  # step still fails (and `|| true` fallbacks still fire) after the retries.
  _st_calls=0
  _st_always_fails() { _st_calls=$((_st_calls + 1)); return 7; }
  RETRY_INITIAL_DELAY=0 RETRY_ATTEMPTS=2 retry _st_always_fails
  _st_check "exhausted retries propagate exit status" "$?" "7"
  _st_check "attempt cap honoured" "$_st_calls" "2"

  # Arguments reach the command untouched, including ones with spaces.
  _st_seen=""
  _st_echo_args() { _st_seen="$*"; return 0; }
  RETRY_INITIAL_DELAY=0 retry _st_echo_args --flag "two words"
  _st_check "arguments passed through" "$_st_seen" "--flag two words"

  if [ "$_st_failures" -ne 0 ]; then
    echo "retry.sh self-test FAILED ($_st_failures)" >&2
    exit 1
  fi
  echo "retry.sh self-test passed"
fi
