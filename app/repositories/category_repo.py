from app.json_store import read_json, write_json, generate_id

FILENAME = 'categories.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(cat_id):
    for c in read_json(FILENAME):
        if c['id'] == cat_id:
            return c
    return None


def create(name, color):
    categories = read_json(FILENAME)
    cat = {
        'id': generate_id('c_'),
        'name': name,
        'color': color,
    }
    categories.append(cat)
    write_json(FILENAME, categories)
    return cat


def update(cat_id, name, color):
    categories = read_json(FILENAME)
    for c in categories:
        if c['id'] == cat_id:
            c['name'] = name
            c['color'] = color
            write_json(FILENAME, categories)
            return c
    return None


def delete(cat_id):
    categories = read_json(FILENAME)
    categories = [c for c in categories if c['id'] != cat_id]
    write_json(FILENAME, categories)
