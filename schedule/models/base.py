from schedule.store import read_json, write_json, generate_id


class BaseRepository:
    """Base class for JSON-file-backed repositories."""

    FILENAME = ''
    ID_PREFIX = ''
    ALLOWED_FIELDS = None  # None means allow all fields in patch

    @classmethod
    def get_all(cls):
        return read_json(cls.FILENAME)

    @classmethod
    def get_by_id(cls, item_id):
        for item in read_json(cls.FILENAME):
            if item['id'] == item_id:
                return item
        return None

    @classmethod
    def create(cls, data):
        """Create a new item. *data* is a dict; 'id' is added automatically unless already present."""
        items = read_json(cls.FILENAME)
        if 'id' not in data or not data['id']:
            data['id'] = generate_id(cls.ID_PREFIX)
        items.append(data)
        write_json(cls.FILENAME, items)
        return data

    @classmethod
    def patch(cls, item_id, **kwargs):
        """Update allowed fields on an existing item."""
        items = read_json(cls.FILENAME)
        for item in items:
            if item['id'] == item_id:
                for key, value in kwargs.items():
                    if cls.ALLOWED_FIELDS is None or key in cls.ALLOWED_FIELDS:
                        item[key] = value
                write_json(cls.FILENAME, items)
                return item
        return None

    @classmethod
    def delete(cls, item_id):
        items = read_json(cls.FILENAME)
        items = [item for item in items if item['id'] != item_id]
        write_json(cls.FILENAME, items)

    @classmethod
    def filter_by(cls, **kwargs):
        """Return items where all given field=value pairs match."""
        results = []
        for item in read_json(cls.FILENAME):
            if all(item.get(k) == v for k, v in kwargs.items()):
                results.append(item)
        return results
