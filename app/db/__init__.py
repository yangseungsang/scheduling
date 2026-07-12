"""Database primitives for the compact domain model."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def create_session_factory(database_url, **engine_kwargs):
    """Create a SQLAlchemy session factory for the configured database URL."""
    connect_args = engine_kwargs.pop('connect_args', None)
    if connect_args is None and database_url.startswith('sqlite:'):
        connect_args = {'check_same_thread': False}
    engine = create_engine(database_url, connect_args=connect_args or {}, **engine_kwargs)
    return sessionmaker(bind=engine, expire_on_commit=False), engine


@contextmanager
def session_scope(session_factory):
    """Provide a transactional session scope."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
