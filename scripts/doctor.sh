#!/usr/bin/env bash

set -uo pipefail

failures=0

pass() {
  printf 'PASS  %s\n' "$1"
}

warn() {
  printf 'WARN  %s\n' "$1"
}

fail() {
  printf 'FAIL  %s\n' "$1"
  failures=$((failures + 1))
}

check_command() {
  local command_name="$1"
  local display_name="$2"

  if command -v "$command_name" >/dev/null 2>&1; then
    pass "$display_name is installed"
  else
    fail "$display_name is not installed"
  fi
}

printf 'TailTag contributor environment check\n\n'

check_command git "Git"

if command -v gh >/dev/null 2>&1; then
  pass "GitHub CLI is installed"

  if gh auth status >/dev/null 2>&1; then
    pass "GitHub CLI is authenticated"
  else
    warn "GitHub CLI is installed but not authenticated; run: gh auth login"
  fi
else
  warn "GitHub CLI is not installed; it is recommended but not currently required"
fi

if [[ -d .git ]]; then
  pass "Current directory is a Git repository"
else
  fail "Run this script from the root of the cloned TailTag repository"
fi

remote_url="$(git remote get-url origin 2>/dev/null || true)"

if [[ "$remote_url" == *"TailTag-Game/tailtag"* ]]; then
  pass "Origin points to TailTag-Game/tailtag"
elif [[ -n "$remote_url" ]]; then
  warn "Origin points to an unexpected repository: $remote_url"
else
  fail "No origin remote is configured"
fi

current_branch="$(git branch --show-current 2>/dev/null || true)"

if [[ "$current_branch" == "main" ]]; then
  warn "You are on main; create a feature branch before making changes"
elif [[ -n "$current_branch" ]]; then
  pass "Current branch is $current_branch"
fi

if git diff --quiet && git diff --cached --quiet; then
  pass "Working tree has no uncommitted changes"
else
  warn "Working tree contains uncommitted changes"
fi

printf '\n'

if (( failures > 0 )); then
  printf '%d required check(s) failed.\n' "$failures"
  exit 1
fi

printf 'Required checks passed.\n'
