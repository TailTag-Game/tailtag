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
    "Taskfile.yml"
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

  if command -v task >/dev/null 2>&1 && task --list-all >/dev/null 2>&1; then
    pass "Canonical backend task commands are available"
  else
    fail "Canonical backend task commands are unavailable; verify go-task is installed and the root Taskfile.yml parses"
  fi
}

pinned_flutter_version() {
  sed -nE 's/.*"flutter"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' apps/mobile/.fvmrc 2>/dev/null | head -n 1
}

# Only the `versions` array counts; entries under `projects` do not.
fvm_sdk_installed() {
  fvm api list --compress 2>/dev/null | tr -d ' \t\r\n' | \
    sed -e 's/.*"versions":\[//' -e 's/\],"projects".*//' | \
    grep -Fq "\"name\":\"$1\""
}

# Prints ok, warn, or bad for the named `fvm flutter doctor` section.
flutter_doctor_state() {
  local doctor_output="$1"
  local section="$2"
  local line

  while IFS= read -r line; do
    case "$line" in
      "[✓] $section"*) printf 'ok'; return 0 ;;
      "[!] $section"*) printf 'warn'; return 0 ;;
      "[✗] $section"*) printf 'bad'; return 0 ;;
    esac
  done <<<"$doctor_output"

  printf 'bad'
}

check_mobile_toolchains() {
  local doctor_output
  local android_state
  local ios_state=""
  local android_hint="set ANDROID_HOME or run: fvm flutter config --android-sdk <path>, then see: fvm flutter doctor -v"
  local ios_hint="install Xcode and run: sudo xcodebuild -runFirstLaunch, then see: fvm flutter doctor -v"

  doctor_output="$(cd apps/mobile && fvm flutter doctor 2>&1 || true)"
  android_state="$(flutter_doctor_state "$doctor_output" 'Android toolchain')"

  if [[ "$(uname -s)" == "Darwin" ]]; then
    ios_state="$(flutter_doctor_state "$doctor_output" 'Xcode')"
  fi

  if [[ "$android_state" == "bad" && ( -z "$ios_state" || "$ios_state" == "bad" ) ]]; then
    if [[ -z "$ios_state" ]]; then
      fail "The Android toolchain is not usable ($android_hint); iOS is not applicable on this host"
    else
      fail "Neither the Android toolchain nor Xcode is usable; Android: $android_hint; iOS: $ios_hint"
    fi
    return
  fi

  case "$android_state" in
    ok) pass "Android toolchain is usable" ;;
    warn) warn "Android toolchain is usable with warnings; see: fvm flutter doctor -v" ;;
    bad) warn "Android toolchain is not usable (optional while iOS works): $android_hint" ;;
  esac

  case "$ios_state" in
    "") pass "iOS is not applicable on this host (Xcode requires macOS)" ;;
    ok) pass "Xcode (iOS) toolchain is usable" ;;
    warn) warn "Xcode (iOS) toolchain is usable with warnings; see: fvm flutter doctor -v" ;;
    bad) warn "Xcode (iOS) toolchain is not usable (optional while Android works): $ios_hint" ;;
  esac
}

check_mobile_devices() {
  if (cd apps/mobile && fvm flutter devices --machine 2>/dev/null) | tr -d ' \t\r\n' | \
    grep -Eq '"targetPlatform":"(android[^"]*|ios)"'; then
    pass "An Android or iOS device or emulator is available"
  else
    warn "No Android or iOS device or emulator is available; start one with: fvm flutter emulators --launch <emulator-id>"
  fi
}

check_mobile_configuration() {
  local config_path="apps/mobile/config/development.json"
  local check_output
  local check_errors
  local check_errors_file
  local check_status
  local origin
  local problem

  if [[ ! -f "$config_path" ]]; then
    warn "Mobile configuration is missing; run: cp apps/mobile/config/development.example.json apps/mobile/config/development.json"
    return
  fi

  # The tool prints the validated origin on stdout and problems on stderr; keep
  # them apart so incidental tool output never becomes the probed origin.
  check_errors_file="$(mktemp)"
  check_output="$(cd apps/mobile && fvm dart run tool/check_config.dart config/development.json 2>"$check_errors_file")"
  check_status=$?
  check_errors="$(cat "$check_errors_file")"
  rm -f "$check_errors_file"

  if (( check_status == 2 )); then
    warn "Mobile configuration is missing; run: cp apps/mobile/config/development.example.json apps/mobile/config/development.json"
    return
  elif (( check_status != 0 )); then
    fail "Mobile configuration is invalid"
    while IFS= read -r problem; do
      printf '      %s\n' "$problem"
    done <<<"$check_errors"
    return
  fi

  pass "Mobile configuration is valid"
  # The tool prints the validated origin as its final line.
  origin="${check_output##*$'\n'}"

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl is not installed; skipped the API reachability check for $origin (host reachability does not prove device reachability)"
  elif curl -fsS --max-time 5 "$origin/health/live" >/dev/null 2>&1; then
    pass "API at $origin answered /health/live from this host (host reachability does not prove device reachability)"
  else
    warn "API at $origin did not answer /health/live from this host; start it or check the URL (host reachability does not prove device reachability)"
  fi
}

check_mobile_environment() {
  local pinned_version

  if [[ "${TAILTAG_DEVCONTAINER:-}" == "1" ]]; then
    fail "Mobile checks run on the host, not in the TailTag devcontainer"
    return
  fi

  if ! command -v fvm >/dev/null 2>&1; then
    fail "FVM is not installed; install it: https://fvm.app/documentation/getting-started/installation"
    warn "Flutter SDK, toolchain, device, and configuration checks skipped until FVM is installed"
    return
  fi

  pass "FVM is installed"
  pinned_version="$(pinned_flutter_version)"

  if [[ -z "$pinned_version" ]]; then
    fail "Could not determine the pinned Flutter version from apps/mobile/.fvmrc"
    warn "Flutter SDK, toolchain, device, and configuration checks skipped"
    return
  fi

  if fvm_sdk_installed "$pinned_version"; then
    pass "Flutter $pinned_version (pinned in apps/mobile/.fvmrc) is installed"
  else
    fail "Flutter $pinned_version (pinned in apps/mobile/.fvmrc) is not installed; run: (cd apps/mobile && fvm install)"
    warn "Toolchain, device, and configuration checks skipped until the pinned Flutter SDK is installed"
    return
  fi

  check_mobile_toolchains
  check_mobile_devices
  check_mobile_configuration
}

usage() {
  printf 'usage: ./scripts/doctor.sh [--mobile]\n'
}

mobile_mode=0

for argument in "$@"; do
  case "$argument" in
    --mobile) mobile_mode=1 ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

printf 'TailTag contributor environment check\n\n'
printf 'Repository\n'
check_repository
check_github_cli
check_foundation_structure

if (( mobile_mode )); then
  printf '\nMobile environment (host)\n'
  check_mobile_environment
elif [[ "${TAILTAG_DEVCONTAINER:-}" == "1" ]]; then
  printf '\nBackend environment (TailTag devcontainer)\n'
  check_devcontainer_environment
  printf 'Mobile checks: run ./scripts/doctor.sh --mobile on the host.\n'
else
  printf '\nHost prerequisites\n'
  check_host_prerequisites
  printf 'Mobile checks: run ./scripts/doctor.sh --mobile on the host.\n'
fi

printf '\n'

if (( failures > 0 )); then
  printf '%d required check(s) failed.\n' "$failures"
  exit 1
fi

printf 'Required checks passed.\n'
