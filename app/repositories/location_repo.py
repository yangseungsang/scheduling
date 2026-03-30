from app.json_store import read_json, write_json, generate_id

FILENAME = 'locations.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(loc_id):
    for loc in read_json(FILENAME):
        if loc['id'] == loc_id:
            return loc
    return None


def create(name, color, description=''):
    locations = read_json(FILENAME)
    loc = {
        'id': generate_id('loc_'),
        'name': name,
        'color': color,
        'description': description,
    }
    locations.append(loc)
    write_json(FILENAME, locations)
    return loc


def update(loc_id, name, color, description=''):
    locations = read_json(FILENAME)
    for loc in locations:
        if loc['id'] == loc_id:
            loc['name'] = name
            loc['color'] = color
            loc['description'] = description
            write_json(FILENAME, locations)
            return loc
    return None


def delete(loc_id):
    locations = read_json(FILENAME)
    locations = [loc for loc in locations if loc['id'] != loc_id]
    write_json(FILENAME, locations)
