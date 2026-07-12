"""Transitional ORM storage for legacy file-shaped payloads."""

from copy import deepcopy

from app.db import Base, create_session_factory, session_scope
from app.db.models import StoragePayload


class OrmFileStorage:
    """Store legacy JSON-file-shaped payloads in an ORM table."""

    def __init__(self, database_url, area):
        self.database_url = database_url
        self.area = area
        self.session_factory, self.engine = create_session_factory(database_url)
        Base.metadata.create_all(self.engine)

    def get_payload(self, filename, default):
        with self.session_factory() as session:
            row = session.get(StoragePayload, (self.area, filename))
            if row is None:
                return deepcopy(default)
            return deepcopy(row.payload)

    def save_payload(self, filename, payload):
        with session_scope(self.session_factory) as session:
            row = session.get(StoragePayload, (self.area, filename))
            if row is None:
                row = StoragePayload(
                    area=self.area,
                    filename=filename,
                    payload=deepcopy(payload),
                )
                session.add(row)
            else:
                row.payload = deepcopy(payload)
