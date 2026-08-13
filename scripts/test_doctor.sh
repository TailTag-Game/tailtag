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
  output="$(cd "$fixture" && PATH="$fixture/tools:/usr/bin:/bin" "$@" bash ./scripts/doctor.sh 2>&1)"
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

grep -Fq '"TAILTAG_DEVCONTAINER": "1"' "$repository_root/.devcontainer/devcontainer.json" || \
  fail 'expected the repository devcontainer configuration to define the TailTag marker'

printf 'PASS: doctor diagnostics tests\n'
