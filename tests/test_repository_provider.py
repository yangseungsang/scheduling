import pytest
from flask import Flask

from app.repositories import get_repository, init_repository


def _app(data_dir):
    app = Flask(__name__)
    app.config['DOMAIN_DATA_DIR'] = str(data_dir)
    return app


def test_provider_returns_the_repository_bound_to_each_app(tmp_path):
    first_app = _app(tmp_path / 'first')
    second_app = _app(tmp_path / 'second')

    first_repository = init_repository(first_app)
    second_repository = init_repository(second_app)

    with first_app.app_context():
        assert get_repository() is first_repository

    with second_app.app_context():
        assert get_repository() is second_repository


def test_provider_fails_clearly_when_repository_is_not_initialized(tmp_path):
    app = _app(tmp_path / 'missing')

    with app.app_context(), pytest.raises(
        RuntimeError,
        match='JsonDomainRepository가 초기화되지 않았습니다.',
    ):
        get_repository()
