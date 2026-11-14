"""Existing runtime limits shared with published run evidence."""

from typing import Final

MAX_RESPONSE_BYTES = 65536  # a page of presigned image URLs is tens of KB
REQUEST_TIMEOUT_SECONDS = 10.0
LEASE_TTL_SECONDS: Final = 1800
LAUNCHER_TIMEOUT_SECONDS: Final = 180
RETENTION_CAP: Final = 5
# The request-limit scenario closes its review window this long after provision.
REVIEW_DEADLINE_OFFSET_SECONDS: Final = 1200
