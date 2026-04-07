from app.features.schedule.models.base import BaseRepository
from app.features.schedule.store import read_json, write_json


class ScheduleBlockRepository(BaseRepository):
    FILENAME = 'schedule_blocks.json'
    ID_PREFIX = 'sb_'
    ALLOWED_FIELDS = {
        'date', 'start_time', 'end_time', 'is_locked',
        'block_status', 'task_id', 'assignee_ids', 'location_id',
        'version_id', 'memo', 'identifier_ids', 'title', 'is_simple',
        'overflow_minutes',
    }

    @classmethod
    def get_by_date(cls, date_str):
        return [b for b in cls.get_all() if b['date'] == date_str]

    @classmethod
    def get_by_date_range(cls, start_date, end_date):
        return [
            b for b in cls.get_all()
            if start_date <= b['date'] <= end_date
        ]

    @classmethod
    def get_by_version(cls, version_id):
        return [b for b in cls.get_all() if b.get('version_id') == version_id]

    @classmethod
    def get_by_assignee(cls, assignee_id):
        return [b for b in cls.get_all()
                if assignee_id in b.get('assignee_ids', [])]

    @classmethod
    def get_by_location_and_date(cls, location_id, date_str):
        return [
            b for b in cls.get_all()
            if b.get('location_id') == location_id and b['date'] == date_str
        ]

    @classmethod
    def create(cls, task_id, assignee_ids, location_id, version_id,
               date, start_time, end_time,
               is_locked=False,
               block_status='pending', identifier_ids=None,
               title='', is_simple=False, overflow_minutes=0):
        data = {
            'task_id': task_id,
            'assignee_ids': assignee_ids or [],
            'location_id': location_id,
            'version_id': version_id,
            'date': date,
            'start_time': start_time,
            'end_time': end_time,
            'is_locked': is_locked,
            'block_status': block_status,
            'memo': '',
            'identifier_ids': identifier_ids,
            'title': title,
            'is_simple': is_simple,
            'overflow_minutes': overflow_minutes,
        }
        return super().create(data)

    @classmethod
    def update(cls, block_id, **kwargs):
        return cls.patch(block_id, **kwargs)



# Backward-compatible module-level aliases
get_all = ScheduleBlockRepository.get_all
get_by_id = ScheduleBlockRepository.get_by_id
get_by_date = ScheduleBlockRepository.get_by_date
get_by_date_range = ScheduleBlockRepository.get_by_date_range
get_by_version = ScheduleBlockRepository.get_by_version
get_by_assignee = ScheduleBlockRepository.get_by_assignee
get_by_location_and_date = ScheduleBlockRepository.get_by_location_and_date
create = ScheduleBlockRepository.create
update = ScheduleBlockRepository.update
delete = ScheduleBlockRepository.delete
