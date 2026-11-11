"""Gunicorn configuration, read from `./gunicorn.conf.py` in its working directory.

Gunicorn configures logging in the master before Django loads, so the JSON logging
setup is applied here to give `gunicorn.error` the same formatter as the application.
"""

from __future__ import annotations

from observability.logging import build_logging_config

logconfig_dict = build_logging_config()

# Sync workers hold one database connection each. A value here overrides the
# `WEB_CONCURRENCY=1` that Render sets on the `0.5c-512mb` plan (#448).
workers = 3
worker_class = "sync"
