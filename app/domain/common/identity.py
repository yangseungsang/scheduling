"""Deterministic identities for externally synchronized domain records."""

import hashlib


def stable_id(prefix, *parts):
    """Return the same internal ID for the same external business keys."""
    raw = '\x1f'.join('' if part is None else str(part) for part in parts)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]
    return f'{prefix}{digest}'
