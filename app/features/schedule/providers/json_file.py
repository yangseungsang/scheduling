from app.features.schedule.providers.base import BaseProvider
from app.features.schedule.store import read_json


class JsonFileProvider(BaseProvider):
    """Provider that reads from local JSON files (default, backward-compatible)."""

    def get_versions(self):
        return [
            {'id': v['id'], 'name': v['name'], 'description': v.get('description', '')}
            for v in read_json('versions.json')
        ]

    def get_test_data(self, version_id):
        return [
            item for item in self._read_procedures()
            if item['version_id'] == version_id
        ]

    def get_test_data_all(self):
        return self._read_procedures()

    def _read_procedures(self):
        raw = read_json('procedures.json')
        result = []
        for p in raw:
            result.append({
                'section_name': p.get('section_name', ''),
                'version_id': p.get('version_id', ''),
                'identifiers': p.get('identifiers', p.get('test_list', [])),
            })
        return result
