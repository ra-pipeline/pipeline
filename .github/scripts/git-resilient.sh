#!/usr/bin/env bash
#
# git-resilient.sh
# Network resilience wrapper for Git operations against on-prem remotes.
#
# NOTE: Uses in-memory `git -c` parameters for each command invocation so it
# NEVER modifies your ~/.gitconfig or local repository .git/config files.
# Safe to source and run on local workstations and CI runners alike.
#
# Usage:
#   1. Sourced in a shell script:
#      source .github/scripts/git-resilient.sh
#      retry_cmd git fetch bitbucket
#
#   2. Executed directly as a wrapper:
#      .github/scripts/git-resilient.sh git fetch bitbucket
#

retry_cmd() {
  local retries="${MAX_RETRIES:-4}"
  local delay="${INITIAL_DELAY:-5}"
  local low_speed_time="${GIT_TIMEOUT:-30}"

  # Inject in-memory network resilience flags if first argument is git
  if [ "$1" = "git" ]; then
    set -- git \
      -c http.lowSpeedLimit=1000 \
      -c "http.lowSpeedTime=$low_speed_time" \
      -c http.postBuffer=524288000 \
      "${@:2}"
  fi

  for ((i = 1; i <= retries; i++)); do
    "$@" && return 0

    if [ "$i" -lt "$retries" ]; then
      echo "Command failed ($*). Retrying in ${delay}s (attempt $i/$retries)..." >&2
      sleep "$delay"
      delay=$((delay * 2))
    fi
  done

  echo "::error::Command failed after $retries attempts: $*" >&2
  return 1
}

# If executed directly with arguments, run retry_cmd with those arguments
if [[ "${BASH_SOURCE[0]}" == "${0}" ]] && [ "$#" -gt 0 ]; then
  retry_cmd "$@"
fi
