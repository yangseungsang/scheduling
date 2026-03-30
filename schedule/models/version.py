from datetime import datetime

from schedule.store import read_json, write_json, generate_id

FILENAME = 'versions.json'


def get_all():
    return read_json(FILENAME)


def get_active():
    return [v for v in read_json(FILENAME) if v.get('is_active', True)]


def get_by_id(version_id):
    for v in read_json(FILENAME):
        if v['id'] == version_id:
            return v
    return None


def create(name, description=''):
    versions = read_json(FILENAME)
    version = {
        'id': generate_id('v_'),
        'name': name,
        'description': description,
        'is_active': True,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    versions.append(version)
    write_json(FILENAME, versions)
    return version


def update(version_id, name, description, is_active=True):
    versions = read_json(FILENAME)
    for v in versions:
        if v['id'] == version_id:
            v['name'] = name
            v['description'] = description
            v['is_active'] = is_active
            write_json(FILENAME, versions)
            return v
    return None


def delete(version_id):
    versions = read_json(FILENAME)
    versions = [v for v in versions if v['id'] != version_id]
    write_json(FILENAME, versions)
