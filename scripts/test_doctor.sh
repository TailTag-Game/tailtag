#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
doctor_script="$repository_root/scripts/doctor.sh"
temporary_directory="$(mktemp -d)"

cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local output="$1"
  local expected="$2"

  [[ "$output" == *"$expected"* ]] || fail "expected output to contain: $expected"
}

assert_not_contains() {
  local output="$1"
  local unexpected="$2"

  [[ "$output" != *"$unexpected"* ]] || fail "did not expect output to contain: $unexpected"
}

assert_line() {
  local output="$1"
  local prefix="$2"
  local fragment="$3"
  local line

  while IFS= read -r line; do
    if [[ "$line" == "$prefix"* && "$line" == *"$fragment"* ]]; then
      return 0
    fi
  done <<<"$output"

  printf '%s\n' "$output" >&2
  fail "expected a line starting with '$prefix' containing: $fragment"
}

find_line() {
  local output="$1"
  local prefix="$2"
  local fragment="$3"
  local line

  while IFS= read -r line; do
    if [[ "$line" == "$prefix"* && "$line" == *"$fragment"* ]]; then
      printf '%s\n' "$line"
      return 0
    fi
  done <<<"$output"

  printf '%s\n' "$output" >&2
  fail "expected a line starting with '$prefix' containing: $fragment"
}

assert_no_line() {
  local output="$1"
  local prefix="$2"
  local fragment="$3"
  local line

  while IFS= read -r line; do
    if [[ "$line" == "$prefix"* && "$line" == *"$fragment"* ]]; then
      printf '%s\n' "$output" >&2
      fail "did not expect a line starting with '$prefix' containing: $fragment"
    fi
  done <<<"$output"
}

create_repository_fixture() {
  local fixture="$1"

  mkdir -p "$fixture/.git" "$fixture/.devcontainer" "$fixture/services/api"
  touch "$fixture/services/api/Dockerfile" \
    "$fixture/services/api/compose.yaml" \
    "$fixture/services/api/pyproject.toml" \
    "$fixture/services/api/uv.lock" \
    "$fixture/services/api/.env.example" \
    "$fixture/.devcontainer/devcontainer.json" \
    "$fixture/.devcontainer/compose.devcontainer.yaml" \
    "$fixture/scripts-doctor-placeholder"
  mkdir -p "$fixture/scripts"
  cp "$doctor_script" "$fixture/scripts/doctor.sh"
  printf 'help:\n\t@:\n' >"$fixture/Makefile"
  printf '[project]\nrequires-python = ">=3.13,<3.14"\n' >"$fixture/services/api/pyproject.toml"
}

create_fake_tools() {
  local tools_directory="$1"
  mkdir -p "$tools_directory"

cat >"$tools_directory/git" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "remote" ]]; then
  printf '%s\n' "${FAKE_REMOTE_URL:-git@github.com:TailTag-Game/tailtag.git}"
elif [[ "$1" == "branch" ]]; then
  printf '%s\n' 'chore/test'
elif [[ "$1" == "rev-parse" ]]; then
  pwd
fi
EOF
  cat >"$tools_directory/docker" <<'EOF'
#!/usr/bin/env bash
case "$1 ${2:-}" in
  "info ") exit "${FAKE_DOCKER_INFO_STATUS:-0}" ;;
  "compose version") exit "${FAKE_DOCKER_COMPOSE_STATUS:-0}" ;;
  *) exit 0 ;;
esac
EOF
  cat >"$tools_directory/gh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
  cat >"$tools_directory/devcontainer" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat >"$tools_directory/python" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-c" && "${2:-}" == *"sys.version_info"* ]]; then
  printf '%s\n' "${FAKE_PYTHON_VERSION:-3.13}"
fi
exit 0
EOF
cat >"$tools_directory/uv" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  printf '%s\n' 'uv 0.9.17'
  exit 0
fi
if [[ "$*" == *"config.compose_database_url"* ]]; then
  printf '%s\n' 'postgresql://test:password@db:5432/test'
  exit "${FAKE_COMPOSE_URL_STATUS:-0}"
fi
if [[ "$*" == *"import django; import psycopg"* ]]; then
  exit "${FAKE_DEPENDENCY_STATUS:-0}"
fi
if [[ "$*" == *"connection.ensure_connection"* ]]; then
  [[ "${DJANGO_SETTINGS_MODULE:-}" == "config.settings.local" ]] || exit 1
  [[ "${DATABASE_URL:-}" == "postgresql://test:password@db:5432/test" ]] || exit 1
  exit "${FAKE_DATABASE_STATUS:-0}"
fi
exit 0
EOF
  chmod +x "$tools_directory"/*
}

run_doctor() {
  local fixture="$1"
  shift
  local output
  local status

  set +e
  output="$(cd "$fixture" && PATH="$fixture/tools:/usr/bin:/bin" "$@" bash ./scripts/doctor.sh ${DOCTOR_ARGS:-} 2>&1)"
  status=$?
  set -e
  printf '%s\n%s\n' "$status" "$output"
}

host_fixture="$temporary_directory/host"
create_repository_fixture "$host_fixture"
create_fake_tools "$host_fixture/tools"
host_result="$(run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
host_status="${host_result%%$'\n'*}"
host_output="${host_result#*$'\n'}"
if [[ "$host_status" != "0" ]]; then
  printf '%s\n' "$host_output" >&2
  fail "expected host diagnostics to pass, got $host_status"
fi
assert_contains "$host_output" 'PASS  Docker is installed'
assert_contains "$host_output" 'PASS  Docker daemon is reachable'
assert_contains "$host_output" 'PASS  Docker Compose is available'
assert_contains "$host_output" 'PASS  Dev Container CLI is available'
assert_not_contains "$host_output" 'Python is'
assert_not_contains "$host_output" 'uv is'
assert_not_contains "$host_output" 'PostgreSQL is'
assert_contains "$host_output" 'Mobile checks: run ./scripts/doctor.sh --mobile on the host.'
assert_not_contains "$host_output" 'FVM'

rm "$host_fixture/services/api/Dockerfile"
mkdir "$host_fixture/services/api/Dockerfile"
wrong_artifact_type_result="$(run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
wrong_artifact_type_status="${wrong_artifact_type_result%%$'\n'*}"
wrong_artifact_type_output="${wrong_artifact_type_result#*$'\n'}"
[[ "$wrong_artifact_type_status" == "1" ]] || fail 'expected a required file replaced by a directory to fail'
assert_contains "$wrong_artifact_type_output" 'FAIL  Required foundation artifact is not a regular file: services/api/Dockerfile'
rmdir "$host_fixture/services/api/Dockerfile"
touch "$host_fixture/services/api/Dockerfile"

remote_warning_result="$(FAKE_REMOTE_URL='https://private-token@github.com/example/fork.git' run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
remote_warning_output="${remote_warning_result#*$'\n'}"
assert_contains "$remote_warning_output" 'WARN  Origin points to an unexpected repository: https://github.com/example/fork.git'
assert_not_contains "$remote_warning_output" 'private-token'

daemon_failure_result="$(FAKE_DOCKER_INFO_STATUS=1 run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
daemon_failure_status="${daemon_failure_result%%$'\n'*}"
daemon_failure_output="${daemon_failure_result#*$'\n'}"
[[ "$daemon_failure_status" == "1" ]] || fail 'expected an unreachable Docker daemon to fail'
assert_contains "$daemon_failure_output" 'FAIL  Docker daemon is unavailable; start Docker and try again'

rm "$host_fixture/tools/devcontainer"
launcher_warning_result="$(run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
launcher_warning_status="${launcher_warning_result%%$'\n'*}"
launcher_warning_output="${launcher_warning_result#*$'\n'}"
[[ "$launcher_warning_status" == "0" ]] || fail 'expected missing launcher warning to exit zero'
assert_contains "$launcher_warning_output" 'WARN  No Dev Container CLI was detected'

compose_failure_result="$(FAKE_DOCKER_COMPOSE_STATUS=1 run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
compose_failure_status="${compose_failure_result%%$'\n'*}"
compose_failure_output="${compose_failure_result#*$'\n'}"
[[ "$compose_failure_status" == "1" ]] || fail 'expected unavailable Docker Compose support to fail'
assert_contains "$compose_failure_output" 'FAIL  Docker Compose is unavailable; install Docker with the Compose plugin'

rm "$host_fixture/tools/docker"
missing_docker_result="$(run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
missing_docker_status="${missing_docker_result%%$'\n'*}"
missing_docker_output="${missing_docker_result#*$'\n'}"
[[ "$missing_docker_status" == "1" ]] || fail 'expected missing Docker to fail'
assert_contains "$missing_docker_output" 'FAIL  Docker is not installed; install Docker with the Compose plugin'

missing_override_result="$(rm "$host_fixture/.devcontainer/compose.devcontainer.yaml"; run_doctor "$host_fixture" env -u TAILTAG_DEVCONTAINER)"
missing_override_status="${missing_override_result%%$'\n'*}"
missing_override_output="${missing_override_result#*$'\n'}"
[[ "$missing_override_status" == "1" ]] || fail 'expected a missing devcontainer Compose override to fail'
assert_contains "$missing_override_output" 'FAIL  Required foundation artifact is missing: .devcontainer/compose.devcontainer.yaml'

container_fixture="$temporary_directory/container"
create_repository_fixture "$container_fixture"
create_fake_tools "$container_fixture/tools"
container_result="$(run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
container_status="${container_result%%$'\n'*}"
container_output="${container_result#*$'\n'}"
[[ "$container_status" == "0" ]] || fail "expected devcontainer diagnostics to pass, got $container_status"
assert_contains "$container_output" 'PASS  Python 3.13 matches the required version 3.13'
assert_contains "$container_output" 'PASS  uv is available'
assert_contains "$container_output" 'PASS  Locked backend dependencies are usable'
assert_contains "$container_output" 'PASS  PostgreSQL is reachable from the backend environment'
assert_contains "$container_output" 'PASS  Canonical backend Make commands are available'
assert_not_contains "$container_output" 'Docker daemon'
assert_contains "$container_output" 'Mobile checks: run ./scripts/doctor.sh --mobile on the host.'

wrong_python_result="$(FAKE_PYTHON_VERSION=3.12 run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
wrong_python_status="${wrong_python_result%%$'\n'*}"
wrong_python_output="${wrong_python_result#*$'\n'}"
[[ "$wrong_python_status" == "1" ]] || fail 'expected an unsupported Python version to fail'
assert_contains "$wrong_python_output" 'FAIL  Python 3.12 does not match the required version 3.13'

dependency_failure_result="$(FAKE_DEPENDENCY_STATUS=1 run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
dependency_failure_status="${dependency_failure_result%%$'\n'*}"
dependency_failure_output="${dependency_failure_result#*$'\n'}"
[[ "$dependency_failure_status" == "1" ]] || fail 'expected unusable locked dependencies to fail'
assert_contains "$dependency_failure_output" 'FAIL  Locked backend dependencies are unusable'

compose_url_failure_result="$(FAKE_COMPOSE_URL_STATUS=1 run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
compose_url_failure_status="${compose_url_failure_result%%$'\n'*}"
compose_url_failure_output="${compose_url_failure_result#*$'\n'}"
[[ "$compose_url_failure_status" == "1" ]] || fail 'expected an unusable Compose database configuration to fail'
assert_contains "$compose_url_failure_output" 'FAIL  PostgreSQL is not reachable from the backend environment'
assert_not_contains "$compose_url_failure_output" 'postgresql://test:password@db:5432/test'

database_failure_result="$(FAKE_DATABASE_STATUS=1 run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
database_failure_status="${database_failure_result%%$'\n'*}"
database_failure_output="${database_failure_result#*$'\n'}"
[[ "$database_failure_status" == "1" ]] || fail 'expected an unreachable database to fail'
assert_contains "$database_failure_output" 'FAIL  PostgreSQL is not reachable from the backend environment'
assert_not_contains "$database_failure_output" 'postgresql://'
assert_not_contains "$database_failure_output" 'tailtag-local-password'

rm "$container_fixture/tools/uv"
missing_uv_result="$(run_doctor "$container_fixture" env TAILTAG_DEVCONTAINER=1)"
missing_uv_status="${missing_uv_result%%$'\n'*}"
missing_uv_output="${missing_uv_result#*$'\n'}"
[[ "$missing_uv_status" == "1" ]] || fail 'expected missing uv to fail'
assert_contains "$missing_uv_output" 'FAIL  uv is not installed in the TailTag devcontainer'

# --- doctor.sh --mobile -------------------------------------------------------

create_fake_mobile_tools() {
  local tools_directory="$1"

  cat >"$tools_directory/fvm" <<'EOF'
#!/usr/bin/env bash
tools_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf 'fvm %s\n' "$*" >>"$tools_directory/calls.log"

require_project_directory() {
  if [[ "$PWD" != */apps/mobile ]]; then
    printf 'FAKE_FVM: expected to run from apps/mobile, ran from %s\n' "$PWD" >&2
    exit 97
  fi
}

default_list='{"size":"1 GB","versions":[{"name":"3.47.1","type":"release","isSetup":true},{"name":"3.47.2","type":"release","isSetup":true}],"projects":[],"unreferencedVersions":[]}'
default_doctor='Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2 25G83 darwin-arm64, locale en-US)
[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)
[✓] Xcode - develop for iOS and macOS (Xcode 27.0)
[✓] Chrome - develop for the web
[✓] Connected device (3 available)

• No issues found!'
default_devices='[
  {
    "name": "Pixel 8",
    "id": "emulator-5554",
    "isSupported": true,
    "targetPlatform": "android-arm64",
    "emulator": true
  },
  {
    "name": "macOS",
    "id": "macos",
    "isSupported": true,
    "targetPlatform": "darwin",
    "emulator": false
  }
]'

case "$*" in
  "api list --compress"*)
    printf '%s\n' "${FAKE_FVM_LIST:-$default_list}"
    ;;
  "api context"*)
    printf 'LEAKED_ENV_CANARY=1\n'
    ;;
  "flutter doctor"*)
    require_project_directory
    printf '%s\n' "${FAKE_FLUTTER_DOCTOR:-$default_doctor}"
    ;;
  "flutter devices --machine"*)
    require_project_directory
    printf '%s\n' "${FAKE_DEVICES:-$default_devices}"
    ;;
  "dart run tool/check_config.dart "*)
    require_project_directory
    config_path="${*:4}"
    if [[ ! -f "$config_path" && ! -f "$PWD/../../$config_path" ]]; then
      printf 'missing: %s\n' "$config_path" >&2
      exit 2
    fi
    printf '%s' "${FAKE_CHECK_STDOUT-http://127.0.0.1:8000
}"
    [[ -z "${FAKE_CHECK_STDERR:-}" ]] || printf '%s\n' "$FAKE_CHECK_STDERR" >&2
    exit "${FAKE_CHECK_STATUS:-0}"
    ;;
  *)
    printf 'UNEXPECTED fvm %s\n' "$*" >>"$tools_directory/calls.log"
    exit 99
    ;;
esac
EOF
  cat >"$tools_directory/curl" <<'EOF'
#!/usr/bin/env bash
tools_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf 'curl %s\n' "$*" >>"$tools_directory/calls.log"
exit "${FAKE_CURL_STATUS:-0}"
EOF
  cat >"$tools_directory/uname" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-s" ]]; then
  printf '%s\n' "${FAKE_UNAME:-Darwin}"
else
  exec /usr/bin/uname "$@"
fi
EOF
  chmod +x "$tools_directory"/*
}

# Creates a host fixture with a pinned SDK, a config file, and the fake tools.
new_mobile_fixture() {
  mobile_fixture="$temporary_directory/mobile-$1"
  create_repository_fixture "$mobile_fixture"
  create_fake_tools "$mobile_fixture/tools"
  create_fake_mobile_tools "$mobile_fixture/tools"
  mkdir -p "$mobile_fixture/apps/mobile/config"
  printf '{\n  "flutter": "3.47.2"\n}\n' >"$mobile_fixture/apps/mobile/.fvmrc"
  printf '{}\n' >"$mobile_fixture/apps/mobile/config/development.json"
}

# Runs `doctor.sh --mobile` on the host fixture; sets mobile_status and mobile_output.
run_mobile() {
  local result

  result="$(DOCTOR_ARGS=--mobile run_doctor "$mobile_fixture" env -u TAILTAG_DEVCONTAINER)"
  mobile_status="${result%%$'\n'*}"
  mobile_output="${result#*$'\n'}"
  mobile_calls="$(cat "$mobile_fixture/tools/calls.log" 2>/dev/null || true)"
}

expect_status() {
  [[ "$mobile_status" == "$1" ]] || {
    printf '%s\n' "$mobile_output" >&2
    fail "$2 (expected exit $1, got $mobile_status)"
  }
}

# Healthy host: every check passes, backend host checks are not run.
new_mobile_fixture healthy
run_mobile
expect_status 0 'expected a healthy mobile host to pass'
assert_contains "$mobile_output" 'Mobile environment (host)'
assert_contains "$mobile_output" 'Required foundation artifact exists: services/api/Dockerfile'
assert_not_contains "$mobile_output" 'Docker is installed'
assert_no_line "$mobile_output" 'FAIL' ''
assert_no_line "$mobile_output" 'WARN' 'configuration'
assert_no_line "$mobile_output" 'WARN' 'emulators'
assert_not_contains "$mobile_output" 'LEAKED_ENV_CANARY'
assert_not_contains "$mobile_calls" 'api context'
assert_not_contains "$mobile_calls" 'UNEXPECTED'
assert_contains "$mobile_calls" 'curl -fsS --max-time 5 http://127.0.0.1:8000/health/live'

# AC14: the reachability result names the origin and says host reachability
# does not prove device reachability.
assert_contains "$(find_line "$mobile_output" 'PASS' 'http://127.0.0.1:8000')" 'device'

# Devcontainer: FAIL immediately and skip every toolchain check.
new_mobile_fixture devcontainer
mobile_result="$(DOCTOR_ARGS=--mobile run_doctor "$mobile_fixture" env TAILTAG_DEVCONTAINER=1)"
mobile_status="${mobile_result%%$'\n'*}"
mobile_output="${mobile_result#*$'\n'}"
expect_status 1 'expected --mobile inside the devcontainer to fail'
assert_contains "$mobile_output" 'FAIL  Mobile checks run on the host, not in the TailTag devcontainer'
assert_not_contains "$mobile_output" 'Docker daemon'
[[ ! -s "$mobile_fixture/tools/calls.log" ]] || fail 'expected no mobile tool to run inside the devcontainer'

# FVM missing: FAIL with install guidance; SDK-dependent checks are skipped, not run.
new_mobile_fixture no-fvm
rm "$mobile_fixture/tools/fvm"
run_mobile
expect_status 1 'expected missing FVM to fail'
assert_line "$mobile_output" 'FAIL' 'FVM is not installed'
assert_line "$mobile_output" 'WARN' 'skipped'
assert_not_contains "$mobile_calls" 'curl'

# Pinned SDK missing. The pinned version appears only as a different release
# (3.47.20) and under `projects`, neither of which means it is installed.
new_mobile_fixture no-sdk
FAKE_FVM_LIST='{"size":"1 GB","versions":[{"name":"3.47.1","isSetup":true},{"name":"3.47.20","isSetup":true}],"projects":[{"name":"3.47.2","pinnedVersion":"3.47.2"}],"unreferencedVersions":[]}' run_mobile
expect_status 1 'expected a missing pinned SDK to fail'
assert_contains "$mobile_output" 'FAIL  Flutter 3.47.2 (pinned in apps/mobile/.fvmrc) is not installed; run: (cd apps/mobile && fvm install)'

# Toolchains: neither usable (absent Xcode counts as unusable) fails.
new_mobile_fixture no-toolchain
FAKE_FLUTTER_DOCTOR='Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2 25G83 darwin-arm64, locale en-US)
[✗] Android toolchain - develop for Android devices
    ✗ cmdline-tools component is missing.
[✓] Chrome - develop for the web' run_mobile
expect_status 1 'expected no usable platform toolchain to fail'
assert_line "$mobile_output" 'FAIL' 'ANDROID_HOME'
assert_line "$mobile_output" 'FAIL' 'xcodebuild -runFirstLaunch'

# Toolchains: exactly one unusable warns and does not fail.
new_mobile_fixture one-toolchain
FAKE_FLUTTER_DOCTOR='Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2 25G83 darwin-arm64, locale en-US)
[✗] Android toolchain - develop for Android devices
    ✗ cmdline-tools component is missing.
[✓] Xcode - develop for iOS and macOS (Xcode 27.0)
[✓] Chrome - develop for the web' run_mobile
expect_status 0 'expected one usable platform toolchain to pass'
assert_line "$mobile_output" 'WARN' 'ANDROID_HOME'
assert_no_line "$mobile_output" 'FAIL' ''

# Toolchains: a [!] entry is usable, with a pointer to the verbose doctor.
# Both entries are [!], so treating [!] as unusable would FAIL this case.
new_mobile_fixture usable-with-warnings
FAKE_FLUTTER_DOCTOR='Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on macOS 26.6.2 25G83 darwin-arm64, locale en-US)
[!] Android toolchain - develop for Android devices (Android SDK version 36.0.0)
    ! Some Android licenses not accepted.
[!] Xcode - develop for iOS and macOS (Xcode 27.0)
    ! CocoaPods not installed.
[✓] Chrome - develop for the web' run_mobile
expect_status 0 'expected toolchains with warnings to remain usable'
assert_line "$mobile_output" 'WARN' 'usable with warnings'
assert_no_line "$mobile_output" 'FAIL' ''

# iOS is not applicable off macOS: informational, not a WARN.
new_mobile_fixture linux
FAKE_UNAME=Linux FAKE_FLUTTER_DOCTOR='Doctor summary (to see all details, run flutter doctor -v):
[✓] Flutter (Channel stable, 3.47.2, on Ubuntu 24.04, locale en-US)
[✓] Android toolchain - develop for Android devices (Android SDK version 36.0.0)
[✓] Chrome - develop for the web' run_mobile
expect_status 0 'expected a Linux host with Android to pass'
assert_contains "$mobile_output" 'iOS is not applicable'
assert_no_line "$mobile_output" 'WARN' 'iOS'
assert_no_line "$mobile_output" 'WARN' 'Xcode'
assert_no_line "$mobile_output" 'FAIL' ''

# Devices: none usable warns with the emulator hint.
new_mobile_fixture no-device
FAKE_DEVICES='[
  {
    "name": "macOS",
    "id": "macos",
    "targetPlatform": "darwin"
  },
  {
    "name": "Chrome",
    "id": "chrome",
    "targetPlatform": "web-javascript"
  }
]' run_mobile
expect_status 0 'expected a missing device to warn, not fail'
assert_line "$mobile_output" 'WARN' 'fvm flutter emulators --launch'

# Devices: an iOS device alone is enough.
new_mobile_fixture ios-device
FAKE_DEVICES='[
  {
    "name": "iPhone 17",
    "id": "ABCD-1234",
    "targetPlatform": "ios"
  }
]' run_mobile
expect_status 0 'expected an iOS device to pass'
assert_no_line "$mobile_output" 'WARN' 'emulators --launch'

# Configuration missing: WARN with the copy command; no probe is attempted.
new_mobile_fixture no-config
rm "$mobile_fixture/apps/mobile/config/development.json"
run_mobile
expect_status 0 'expected missing configuration to warn, not fail'
assert_contains "$mobile_output" 'WARN  Mobile configuration is missing; run: cp apps/mobile/config/development.example.json apps/mobile/config/development.json'
assert_not_contains "$mobile_calls" 'curl'

# Configuration invalid: FAIL, the validator's problems are shown, no probe is attempted.
new_mobile_fixture bad-config
FAKE_CHECK_STDOUT='' FAKE_CHECK_STDERR='CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key' FAKE_CHECK_STATUS=1 run_mobile
expect_status 1 'expected invalid configuration to fail'
assert_contains "$mobile_output" 'FAIL  Mobile configuration is invalid'
assert_contains "$mobile_output" 'CLERK_PUBLISHABLE_KEY: must be a Clerk test publishable key'
assert_not_contains "$mobile_calls" 'curl'

# API unreachable: WARN naming the origin; does not fail.
new_mobile_fixture api-down
FAKE_CURL_STATUS=22 run_mobile
expect_status 0 'expected an unreachable API to warn, not fail'
assert_contains "$(find_line "$mobile_output" 'WARN' 'http://127.0.0.1:8000')" 'device'
assert_no_line "$mobile_output" 'PASS' 'http://127.0.0.1:8000'

# Unknown arguments are rejected before any check runs.
new_mobile_fixture bad-arg
mobile_result="$(DOCTOR_ARGS=--bogus run_doctor "$mobile_fixture" env -u TAILTAG_DEVCONTAINER)"
mobile_status="${mobile_result%%$'\n'*}"
mobile_output="${mobile_result#*$'\n'}"
expect_status 2 'expected an unknown argument to exit 2'
assert_contains "$mobile_output" '--mobile'
assert_not_contains "$mobile_output" 'PASS'

grep -Fq '"TAILTAG_DEVCONTAINER": "1"' "$repository_root/.devcontainer/devcontainer.json" || \
  fail 'expected the repository devcontainer configuration to define the TailTag marker'

printf 'PASS: doctor diagnostics tests\n'
