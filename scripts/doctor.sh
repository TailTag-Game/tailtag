#!/bin/sh
# POSIX wrapper for the contributor environment check. The checks live in
# scripts/doctor.py; `task doctor` runs the same script on every OS.

cd "$(dirname "$0")/.." || exit 1

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project python scripts/doctor.py "$@"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/doctor.py "$@"
fi

printf '%s\n' 'Install uv (https://docs.astral.sh/uv/) or Python 3 to run doctor.'
exit 1
