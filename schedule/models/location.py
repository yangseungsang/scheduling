from schedule.models.base import BaseRepository


class LocationRepository(BaseRepository):
    FILENAME = 'locations.json'
    ID_PREFIX = 'loc_'

    @classmethod
    def create(cls, name, color, description=''):
        data = {'name': name, 'color': color, 'description': description}
        return super().create(data)

    @classmethod
    def update(cls, loc_id, name, color, description=''):
        return cls.patch(loc_id, name=name, color=color, description=description)


# Backward-compatible module-level aliases
get_all = LocationRepository.get_all
get_by_id = LocationRepository.get_by_id
create = LocationRepository.create
update = LocationRepository.update
delete = LocationRepository.delete
