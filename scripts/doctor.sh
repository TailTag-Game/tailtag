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
    return 0
  fi

  fail "$display_name is not installed"
  return 1
}

check_required_path() {
  local path="$1"
  local expected_type="$2"

  if [[ "$expected_type" == "directory" && -d "$path" ]] || \
    [[ "$expected_type" == "regular file" && -f "$path" ]]; then
    pass "Required foundation artifact exists: $path"
  elif [[ -e "$path" ]]; then
    fail "Required foundation artifact is not a $expected_type: $path"
  else
    fail "Required foundation artifact is missing: $path"
  fi
}

expected_python_version() {
  sed -nE \
    's/^[[:space:]]*requires-python[[:space:]]*=[[:space:]]*"[>=[:space:]]*([0-9]+\.[0-9]+).*/\1/p' \
    services/api/pyproject.toml | head -n 1
}

sanitized_remote_url() {
  sed -E 's#(https?://)[^/@]*@#\1#' <<<"$1"
}

check_repository() {
  local git_available=0
  local repository_root=""
  local remote_url=""
  local current_branch=""

  if check_command git "Git"; then
    git_available=1
  fi

  if (( git_available )) && repository_root="$(git rev-parse --show-toplevel 2>/dev/null)" && [[ "$repository_root" == "$PWD" ]]; then
    pass "Current directory is the TailTag repository root"
  else
    fail "Run this script from the root of the cloned TailTag repository"
  fi

  if (( git_available )); then
    remote_url="$(git remote get-url origin 2>/dev/null || true)"

    if [[ "$remote_url" == *"TailTag-Game/tailtag"* ]]; then
      pass "Origin points to TailTag-Game/tailtag"
    elif [[ -n "$remote_url" ]]; then
      warn "Origin points to an unexpected repository: $(sanitized_remote_url "$remote_url")"
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
  fi
}

check_github_cli() {
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
}

check_foundation_structure() {
  local required_files=(
    "services/api/Dockerfile"
    "services/api/compose.yaml"
    "services/api/pyproject.toml"
    "services/api/uv.lock"
    "services/api/.env.example"
    ".devcontainer/devcontainer.json"
    ".devcontainer/compose.devcontainer.yaml"
    "Makefile"
    "scripts/doctor.sh"
  )
  local path

  check_required_path "services/api" "directory"

  for path in "${required_files[@]}"; do
    check_required_path "$path" "regular file"
  done
}

check_host_prerequisites() {
  if command -v docker >/dev/null 2>&1; then
    pass "Docker is installed"

    if docker info >/dev/null 2>&1; then
      pass "Docker daemon is reachable"
    else
      fail "Docker daemon is unavailable; start Docker and try again"
    fi

    if docker compose version >/dev/null 2>&1; then
      pass "Docker Compose is available"
    else
      fail "Docker Compose is unavailable; install Docker with the Compose plugin"
    fi
  else
    fail "Docker is not installed; install Docker with the Compose plugin"
  fi

  if command -v devcontainer >/dev/null 2>&1; then
    pass "Dev Container CLI is available"
  else
    warn "No Dev Container CLI was detected; use a devcontainer-capable editor or install a compatible Dev Container CLI"
  fi
}

check_devcontainer_environment() {
  local expected_version=""
  local detected_version=""
  local database_url=""

  if ! command -v python >/dev/null 2>&1; then
    fail "Python is not installed in the TailTag devcontainer"
  else
    expected_version="$(expected_python_version)"
    detected_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"

    if [[ -z "$expected_version" ]]; then
      fail "Could not determine the required Python version from services/api/pyproject.toml"
    elif [[ "$detected_version" == "$expected_version" ]]; then
      pass "Python $detected_version matches the required version $expected_version"
    else
      fail "Python ${detected_version:-unknown} does not match the required version $expected_version"
    fi
  fi

  if command -v uv >/dev/null 2>&1; then
    pass "uv is available"

    if uv --directory services/api run --locked --no-sync python -c 'import django; import psycopg' >/dev/null 2>&1; then
      pass "Locked backend dependencies are usable"
    else
      fail "Locked backend dependencies are unusable; run the established backend setup flow"
    fi

    if database_url="$(uv --directory services/api run --locked --no-sync python -m config.compose_database_url 2>/dev/null)" && \
      DJANGO_SETTINGS_MODULE=config.settings.local DATABASE_URL="$database_url" \
        uv --directory services/api run --locked --no-sync python -c '
from django import setup
from django.db import connection

setup()
connection.ensure_connection()
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
' >/dev/null 2>&1; then
      pass "PostgreSQL is reachable from the backend environment"
    else
      fail "PostgreSQL is not reachable from the backend environment; verify the local database service is running and healthy"
    fi
  else
    fail "uv is not installed in the TailTag devcontainer"
  fi

  if command -v make >/dev/null 2>&1 && make -n help >/dev/null 2>&1; then
    pass "Canonical backend Make commands are available"
  else
    fail "Canonical backend Make commands are unavailable; verify the root Makefile"
  fi
}

printf 'TailTag contributor environment check\n\n'
printf 'Repository\n'
check_repository
check_github_cli
check_foundation_structure

if [[ "${TAILTAG_DEVCONTAINER:-}" == "1" ]]; then
  printf '\nBackend environment (TailTag devcontainer)\n'
  check_devcontainer_environment
else
  printf '\nHost prerequisites\n'
  check_host_prerequisites
fi

printf '\n'

if (( failures > 0 )); then
  printf '%d required check(s) failed.\n' "$failures"
  exit 1
fi

printf 'Required checks passed.\n'
