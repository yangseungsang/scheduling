from schedule.store import read_json, write_json, generate_id

FILENAME = 'schedule_blocks.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(block_id):
    for b in read_json(FILENAME):
        if b['id'] == block_id:
            return b
    return None


def get_by_date(date_str):
    return [b for b in read_json(FILENAME) if b['date'] == date_str]


def get_by_date_range(start_date, end_date):
    return [
        b for b in read_json(FILENAME)
        if start_date <= b['date'] <= end_date
    ]


def get_by_version(version_id):
    return [b for b in read_json(FILENAME) if b.get('version_id') == version_id]


def get_by_assignee(assignee_id):
    return [b for b in read_json(FILENAME) if assignee_id in b.get('assignee_ids', [])]


def get_by_location_and_date(location_id, date_str):
    return [
        b for b in read_json(FILENAME)
        if b.get('location_id') == location_id and b['date'] == date_str
    ]


def create(task_id, assignee_ids, location_id, version_id,
           date, start_time, end_time,
           is_draft=False, is_locked=False, origin='manual',
           block_status='pending'):
    blocks = read_json(FILENAME)
    block = {
        'id': generate_id('sb_'),
        'task_id': task_id,
        'assignee_ids': assignee_ids or [],
        'location_id': location_id,
        'version_id': version_id,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'is_draft': is_draft,
        'is_locked': is_locked,
        'origin': origin,
        'block_status': block_status,
        'memo': '',
    }
    blocks.append(block)
    write_json(FILENAME, blocks)
    return block


ALLOWED_FIELDS = {
    'date', 'start_time', 'end_time', 'is_draft', 'is_locked',
    'block_status', 'task_id', 'assignee_ids', 'location_id',
    'version_id', 'origin', 'memo',
}


def update(block_id, **kwargs):
    blocks = read_json(FILENAME)
    for b in blocks:
        if b['id'] == block_id:
            for key, value in kwargs.items():
                if key in ALLOWED_FIELDS:
                    b[key] = value
            write_json(FILENAME, blocks)
            return b
    return None


def delete(block_id):
    blocks = read_json(FILENAME)
    blocks = [b for b in blocks if b['id'] != block_id]
    write_json(FILENAME, blocks)


def delete_drafts():
    blocks = read_json(FILENAME)
    blocks = [b for b in blocks if not b.get('is_draft')]
    write_json(FILENAME, blocks)


def approve_drafts():
    blocks = read_json(FILENAME)
    for b in blocks:
        if b.get('is_draft'):
            b['is_draft'] = False
    write_json(FILENAME, blocks)
