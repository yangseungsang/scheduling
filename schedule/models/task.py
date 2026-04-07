from datetime import datetime

from schedule.models.base import BaseRepository


class TaskRepository(BaseRepository):
    FILENAME = 'tasks.json'
    ID_PREFIX = 't_'

    @classmethod
    def get_by_version(cls, version_id):
        return [t for t in cls.get_all() if t.get('version_id') == version_id]

    @classmethod
    def validate_unique_identifiers(cls, test_list, exclude_task_id=None):
        """Check that identifier IDs in test_list are globally unique across all tasks.

        Returns list of duplicate IDs, or empty list if all unique.
        """
        new_ids = [item['id'] for item in test_list if isinstance(item, dict)]
        if not new_ids:
            return []

        from schedule.store import read_json
        existing_ids = set()
        for t in read_json(cls.FILENAME):
            if exclude_task_id and t['id'] == exclude_task_id:
                continue
            for item in t.get('test_list', []):
                if isinstance(item, dict):
                    existing_ids.add(item['id'])
                else:
                    existing_ids.add(item)
        return [i for i in new_ids if i in existing_ids]

    @staticmethod
    def compute_estimated_minutes(test_list):
        """Sum estimated_minutes from test_list identifiers."""
        total = 0
        for item in (test_list or []):
            if isinstance(item, dict):
                total += item.get('estimated_minutes', 0)
        return total

    @classmethod
    def create(cls, procedure_id, version_id, assignee_ids, location_id,
               section_name, procedure_owner, test_list,
               estimated_minutes, memo='', source='local', external_key=''):
        data = {
            'procedure_id': procedure_id,
            'version_id': version_id,
            'assignee_ids': assignee_ids or [],
            'location_id': location_id,
            'section_name': section_name,
            'procedure_owner': procedure_owner,
            'test_list': test_list or [],
            'estimated_minutes': estimated_minutes,
            'remaining_minutes': estimated_minutes,
            'status': 'waiting',
            'memo': memo,
            'source': source,
            'external_key': external_key,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        return super().create(data)

    @classmethod
    def update(cls, task_id, procedure_id, version_id, assignee_ids, location_id,
               section_name, procedure_owner, test_list,
               estimated_minutes, remaining_minutes, status, memo=''):
        return cls.patch(
            task_id,
            procedure_id=procedure_id,
            version_id=version_id,
            assignee_ids=assignee_ids or [],
            location_id=location_id,
            section_name=section_name,
            procedure_owner=procedure_owner,
            test_list=test_list or [],
            estimated_minutes=estimated_minutes,
            remaining_minutes=remaining_minutes,
            status=status,
            memo=memo,
        )


    @classmethod
    def get_by_external_key(cls, key):
        for t in cls.get_all():
            if t.get('external_key') == key:
                return t
        return None


# Backward-compatible module-level aliases
get_all = TaskRepository.get_all
get_by_id = TaskRepository.get_by_id
get_by_version = TaskRepository.get_by_version
create = TaskRepository.create
update = TaskRepository.update
patch = TaskRepository.patch
delete = TaskRepository.delete
validate_unique_identifiers = TaskRepository.validate_unique_identifiers
compute_estimated_minutes = TaskRepository.compute_estimated_minutes
get_by_external_key = TaskRepository.get_by_external_key
