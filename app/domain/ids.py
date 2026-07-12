"""Stable internal ID helpers for redesigned data models."""

import hashlib


def stable_id(prefix, *parts):
    """Return a deterministic internal ID for legacy data parts."""
    raw = '\x1f'.join('' if part is None else str(part) for part in parts)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]
    return f'{prefix}{digest}'
