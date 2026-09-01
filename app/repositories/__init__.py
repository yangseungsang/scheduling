"""Persistent repositories shared by application features."""

from app.repositories.json_domain import JsonDomainRepository
from app.repositories.provider import get_repository, init_repository

__all__ = ['JsonDomainRepository', 'get_repository', 'init_repository']
