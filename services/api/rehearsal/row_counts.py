"""Count every row of every public table for the Render Staging PITR drill (#410).

The row-count job and the restore counter both use these two functions. So
both sides of the AC13 comparison count and hash in exactly the same way.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg import Cursor

# One static statement counts every table. PostgreSQL quotes each table name
# with format('%I'), and the single statement reads one consistent snapshot.
_COUNT_EVERY_TABLE = """
SELECT t.tablename, (xpath('/row/n/text()', query_to_xml(
    format('SELECT count(*) AS n FROM %I.%I', t.schemaname, t.tablename),
    false, true, ''
)))[1]::text::bigint
FROM pg_catalog.pg_tables AS t
WHERE t.schemaname = 'public'
ORDER BY t.tablename
"""


def count_rows(cursor: Cursor[Any]) -> dict[str, int]:
    """Return the exact row count of each table in `public`, by table name."""
    cursor.execute(_COUNT_EVERY_TABLE)
    counts: dict[str, int] = {}
    for name, count in cursor.fetchall():
        if not isinstance(name, str) or type(count) is not int:
            raise TypeError("row count invalid")
        counts[name] = count
    return counts


def digest(counts: dict[str, int]) -> str:
    """Return the SHA-256 of the counts in one canonical JSON form."""
    canonical = json.dumps(counts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
