"""Utilities for deduplicating calendar rows."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


def dedupe_by_key(
    rows: Iterable[dict],
    keys: Sequence[str],
) -> List[dict]:
    """Deduplicate rows by the composite key given by `keys`."""
    seen: set[Tuple] = set()
    unique_rows: List[dict] = []
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


