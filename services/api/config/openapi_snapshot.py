"""Write or check the committed OpenAPI schema snapshot.

The snapshot (`openapi/schema.yaml`) is the authoritative contract input to the
mobile client. It is exactly the `manage.py spectacular --validate` output and
needs no database. Run through the Taskfile: `task api-schema` writes it and
`task api-schema-check` fails when the committed file is stale.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi" / "schema.yaml"
REGENERATE_COMMAND = "task api-schema"


def render_schema() -> bytes:
    """Return Django's current validated schema as LF-terminated bytes."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    # Imported here so the settings module is chosen before Django loads.
    import django
    from django.core.management import call_command

    django.setup()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "schema.yaml"
        call_command("spectacular", validate=True, file=str(output))
        return output.read_bytes()


def main(arguments: list[str]) -> int:
    """Write the snapshot with `--write`; compare it with Django with `--check`."""
    if arguments not in (["--write"], ["--check"]):
        print(
            "usage: python -m config.openapi_snapshot --write|--check", file=sys.stderr
        )
        return 2
    rendered = render_schema()
    if arguments == ["--write"]:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_bytes(rendered)
        print(f"Wrote {SNAPSHOT.parent.name}/{SNAPSHOT.name}.")
        return 0
    committed = SNAPSHOT.read_bytes() if SNAPSHOT.exists() else b""
    if committed.replace(b"\r\n", b"\n") != rendered:
        print(
            f"The committed OpenAPI schema snapshot (services/api/openapi/schema.yaml) "
            f"is stale; regenerate it with: {REGENERATE_COMMAND}",
            file=sys.stderr,
        )
        return 1
    print("The OpenAPI schema snapshot is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
