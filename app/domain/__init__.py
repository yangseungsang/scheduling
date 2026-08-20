"""Domain utilities shared across feature boundaries."""

from app.domain.common import SCHEMA_VERSION
from app.domain.common.identity import stable_id

__all__ = ['SCHEMA_VERSION', 'stable_id']
