from datetime import datetime

from app.features.execution.store import read_json, write_json, generate_id

FILENAME = 'executions.json'
ID_PREFIX = 'ex_'


class ExecutionRepository:

    @classmethod
    def get_all(cls):
        return read_json(FILENAME)

    @classmethod
    def get_by_id(cls, execution_id):
        for item in read_json(FILENAME):
            if item['id'] == execution_id:
                return item
        return None

    @classmethod
    def get_by_identifier(cls, identifier_id):
        for item in read_json(FILENAME):
            if item['identifier_id'] == identifier_id:
                return item
        return None

    @staticmethod
    def compute_elapsed_seconds(segments):
        total = 0
        now = datetime.now()
        for seg in segments:
            start = datetime.fromisoformat(seg['start'])
            end = datetime.fromisoformat(seg['end']) if seg['end'] else now
            total += int((end - start).total_seconds())
        return max(0, total)

    @classmethod
    def _patch(cls, execution_id, **kwargs):
        items = read_json(FILENAME)
        for item in items:
            if item['id'] == execution_id:
                item.update(kwargs)
                write_json(FILENAME, items)
                return item
        return None

    @classmethod
    def start(cls, identifier_id, task_id, total_count=10):
        now = datetime.now().isoformat(timespec='seconds')
        existing = cls.get_by_identifier(identifier_id)
        if existing:
            return cls._patch(
                existing['id'],
                status='in_progress',
                segments=[{'start': now, 'end': None}],
                fail_count=0,
                pass_count=0,
                total_count=total_count,
                completed_at=None,
            )
        data = {
            'id': generate_id(ID_PREFIX),
            'identifier_id': identifier_id,
            'task_id': task_id,
            'status': 'in_progress',
            'segments': [{'start': now, 'end': None}],
            'total_count': total_count,
            'fail_count': 0,
            'pass_count': 0,
            'comment': '',
            'created_at': now,
            'completed_at': None,
        }
        items = read_json(FILENAME)
        items.append(data)
        write_json(FILENAME, items)
        return data

    @classmethod
    def pause(cls, execution_id):
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'in_progress':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = list(ex['segments'])
        if segments:
            segments[-1] = {**segments[-1], 'end': now}
        return cls._patch(execution_id, status='paused', segments=segments)

    @classmethod
    def resume(cls, execution_id):
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'paused':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = ex['segments'] + [{'start': now, 'end': None}]
        return cls._patch(execution_id, status='in_progress', segments=segments)

    @classmethod
    def complete(cls, execution_id, fail_count):
        ex = cls.get_by_id(execution_id)
        if not ex:
            return None
        if ex['status'] not in ('in_progress', 'paused'):
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = list(ex['segments'])
        if segments:
            segments[-1] = {**segments[-1], 'end': now}
        total_count = ex.get('total_count', 0)
        pass_count = max(0, total_count - int(fail_count))
        return cls._patch(
            execution_id,
            status='completed',
            segments=segments,
            fail_count=int(fail_count),
            pass_count=pass_count,
            completed_at=now,
        )

    @classmethod
    def update_comment(cls, execution_id, comment):
        return cls._patch(execution_id, comment=comment)

    @classmethod
    def reset(cls, execution_id):
        return cls._patch(
            execution_id,
            status='pending',
            segments=[],
            fail_count=0,
            pass_count=0,
            comment='',
            completed_at=None,
        )
