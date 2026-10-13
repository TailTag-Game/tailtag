#!/usr/bin/env bash
# Runs the TailTag mobile app on one explicitly chosen Android or iOS target.
# Usage: DEVICE=<id> ./scripts/mobile_run.sh   (or: make mobile-run DEVICE=<id>)

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mobile_directory="$repository_root/apps/mobile"
config_file="config/development.json"
device="${DEVICE:-}"

die() {
  printf '%s\n' "$1" >&2
  exit 1
}

if [[ "${TAILTAG_DEVCONTAINER:-}" == "1" ]]; then
  die 'Mobile commands run on the host, not in the TailTag devcontainer.'
fi

command -v fvm >/dev/null 2>&1 || \
  die 'FVM is not installed; install it: https://fvm.app/documentation/getting-started/installation'

# --- Resolve the device (never boots or chooses one) ---------------------------

device_platform() {
  local machine entry id

  [[ "$device" =~ ^[A-Za-z0-9._:-]+$ ]] || return 0
  machine="$(cd "$mobile_directory" && fvm flutter devices --machine 2>/dev/null | tr -d ' \t\r\n' || true)"

  while IFS= read -r entry; do
    id="${entry#\"id\":\"}"
    id="${id%%\"*}"

    if [[ "$id" == "$device" ]]; then
      entry="${entry##*\"targetPlatform\":\"}"
      printf '%s\n' "${entry%\"}"
      return 0
    fi
  done < <(printf '%s' "$machine" | grep -oE '"id":"[^"]*"[^}]*"targetPlatform":"[^"]*"' || true)
}

platform="$(device_platform)"

if [[ -z "$platform" ]]; then
  if [[ -z "$device" ]]; then
    printf '%s\n' 'DEVICE is required: choose one connected target.' >&2
  else
    printf '%s\n' 'DEVICE is not a connected device id.' >&2
  fi

  (cd "$mobile_directory" && fvm flutter devices) || true
  printf '\n%s\n' 'Start one with: fvm flutter emulators --launch <emulator-id>'
  printf '%s\n' 'Then run: make mobile-run DEVICE=<id>'
  exit 1
fi

case "$platform" in
  android*|ios) ;;
  *) die "TailTag supports Android and iOS targets; $device is a $platform target." ;;
esac

# --- Validate configuration before launching -----------------------------------

# The tool prints the validated origin on stdout and problems on stderr; keep
# them apart so incidental tool output never becomes part of the origin.
check_errors_file="$(mktemp)"
set +e
check_output="$(cd "$mobile_directory" && fvm dart run tool/check_config.dart "$config_file" 2>"$check_errors_file")"
check_status=$?
set -e
check_errors="$(cat "$check_errors_file")"
rm -f "$check_errors_file"

if (( check_status == 2 )); then
  printf '%s\n' 'Mobile configuration is missing: apps/mobile/config/development.json' >&2
  printf '%s\n' 'Copy the template: cp apps/mobile/config/development.example.json apps/mobile/config/development.json' >&2
  printf '%s\n' 'Then set CLERK_PUBLISHABLE_KEY to the Clerk Development publishable key.' >&2
  exit 1
elif (( check_status != 0 )); then
  printf '%s\n' 'Mobile configuration is invalid (apps/mobile/config/development.json):' >&2
  printf '%s\n' "$check_errors" >&2
  printf '%s\n' 'Fix the listed values, or start again from the template: cp apps/mobile/config/development.example.json apps/mobile/config/development.json' >&2
  exit 1
fi

# --- Android Local needs the device to reach the host loopback API -------------

origin="${check_output##*$'\n'}"

if [[ "$origin" == http://* && "$platform" == android* ]]; then
  command -v adb >/dev/null 2>&1 || \
    die 'adb is not on PATH; install Android platform-tools (or set ANDROID_HOME and add platform-tools to PATH) so Local API access can be forwarded.'

  authority="${origin#http://}"
  port="${authority##*:}"
  [[ "$authority" == *:* ]] || port=80

  adb -s "$device" reverse "tcp:$port" "tcp:$port" || \
    die "adb reverse failed for $device; check that the device is online (adb devices)."
fi

cd "$mobile_directory"
exec fvm flutter run -d "$device" "--dart-define-from-file=$config_file"
