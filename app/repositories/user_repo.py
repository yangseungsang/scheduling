from app.json_store import read_json, write_json, generate_id

FILENAME = 'users.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(user_id):
    for u in read_json(FILENAME):
        if u['id'] == user_id:
            return u
    return None


def create(name, role, color):
    users = read_json(FILENAME)
    user = {
        'id': generate_id('u_'),
        'name': name,
        'role': role,
        'color': color,
    }
    users.append(user)
    write_json(FILENAME, users)
    return user


def update(user_id, name, role, color):
    users = read_json(FILENAME)
    for u in users:
        if u['id'] == user_id:
            u['name'] = name
            u['role'] = role
            u['color'] = color
            write_json(FILENAME, users)
            return u
    return None


def delete(user_id):
    users = read_json(FILENAME)
    users = [u for u in users if u['id'] != user_id]
    write_json(FILENAME, users)
