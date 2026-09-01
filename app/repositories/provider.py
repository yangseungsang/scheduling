"""Flask app-scoped access to the shared JSON domain repository."""

from flask import Flask, current_app

from app.repositories.json_domain import JsonDomainRepository


_REPOSITORY_KEY = 'scheduling.domain_repository'


def init_repository(app: Flask, *, reset: bool = False) -> JsonDomainRepository:
    """Create, initialize, and bind one repository to a Flask application."""
    repository = JsonDomainRepository(app.config['DOMAIN_DATA_DIR'])
    repository.initialize(reset=reset)
    app.extensions[_REPOSITORY_KEY] = repository
    return repository


def get_repository() -> JsonDomainRepository:
    """Return the repository belonging to the active Flask application."""
    repository = current_app.extensions.get(_REPOSITORY_KEY)
    if not isinstance(repository, JsonDomainRepository):
        raise RuntimeError('JsonDomainRepository가 초기화되지 않았습니다.')
    return repository
