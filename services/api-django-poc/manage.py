#!/usr/bin/env python
"""Django management entry point."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run Django management commands with local settings by default."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
