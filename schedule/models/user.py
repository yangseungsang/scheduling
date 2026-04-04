from schedule.models.base import BaseRepository


class UserRepository(BaseRepository):
    FILENAME = 'users.json'
    ID_PREFIX = 'u_'

    @classmethod
    def create(cls, name, role, color):
        data = {'name': name, 'role': role, 'color': color}
        return super().create(data)

    @classmethod
    def update(cls, user_id, name, role, color):
        return cls.patch(user_id, name=name, role=role, color=color)


# Backward-compatible module-level aliases
get_all = UserRepository.get_all
get_by_id = UserRepository.get_by_id
create = UserRepository.create
update = UserRepository.update
delete = UserRepository.delete
