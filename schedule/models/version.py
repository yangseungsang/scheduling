from datetime import datetime

from schedule.models.base import BaseRepository


class VersionRepository(BaseRepository):
    FILENAME = 'versions.json'
    ID_PREFIX = 'v_'

    @classmethod
    def get_active(cls):
        return [v for v in cls.get_all() if v.get('is_active', True)]

    @classmethod
    def create(cls, name, description='', id=None):
        data = {
            'name': name,
            'description': description,
            'is_active': True,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        if id:
            data['id'] = id
        return super().create(data)

    @classmethod
    def update(cls, version_id, name, description, is_active=True):
        return cls.patch(version_id, name=name, description=description,
                         is_active=is_active)


# Backward-compatible module-level aliases
get_all = VersionRepository.get_all
get_active = VersionRepository.get_active
get_by_id = VersionRepository.get_by_id
create = VersionRepository.create
update = VersionRepository.update
delete = VersionRepository.delete
