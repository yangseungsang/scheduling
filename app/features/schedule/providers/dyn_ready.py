"""dyn_ready 프로바이더 — 자체 /dyn_ready/std-list/grouped 엔드포인트에서 데이터를 가져온다.

updated_at을 로컬 캐시와 비교하여 변경이 없으면 NoChangesError를 발생시킨다.
identifiers의 exam_no를 기준으로 (doc_id, exam_no) 조합별로 묶어 반환한다.
"""

import json
import os

import requests

from app.features.schedule.providers.base import BaseProvider, NoChangesError

_ENDPOINT = '/dyn_ready/std-list/grouped'
_META_FILE = 'dyn_ready_meta.json'


def _meta_path():
    from flask import current_app
    return os.path.join(current_app.config['DATA_DIR'], _META_FILE)


def _load_meta():
    path = _meta_path()
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _save_meta(meta):
    with open(_meta_path(), 'w') as f:
        json.dump(meta, f)


class DynReadyProvider(BaseProvider):

    def __init__(self):
        self.base_url = os.environ.get('DYN_READY_URL', 'http://127.0.0.1:5000').rstrip('/')

    def get_versions(self):
        return []

    def get_test_data(self, version_id):
        return self.get_test_data_all()

    def get_test_data_all(self, force=False):
        """grouped 엔드포인트에서 데이터를 가져와 (doc_id, exam_no) 단위 리스트로 반환한다.

        updated_at이 캐시와 동일하면 NoChangesError를 발생시킨다.
        force=True이면 updated_at 비교 없이 항상 동기화한다.
        """
        resp = requests.get(f'{self.base_url}{_ENDPOINT}', timeout=10)
        resp.raise_for_status()
        payload = resp.json()

        new_ts = str(payload.get('updated_at', ''))
        meta = _load_meta()

        if not force and new_ts and new_ts == meta.get('updated_at', ''):
            raise NoChangesError(new_ts)

        meta['updated_at'] = new_ts
        _save_meta(meta)

        return _transform(payload)


def _transform(payload):
    """API 응답을 SyncService가 소비할 수 있는 형태로 변환한다.

    반환 항목마다 'exam_no' 키가 포함되어 있어
    SyncService가 std_list 캐시 없이 바로 사용할 수 있다.
    """
    items = []
    for doc in payload.get('data', []):
        doc_id = doc.get('doc_id')
        doc_name = doc.get('doc_name', '')

        by_exam: dict = {}
        for ident in doc.get('identifiers', []):
            exam_no = ident.get('exam_no')
            normalized = {
                'id': ident.get('test_id', ''),
                'name': ident.get('func_name', ''),
                'estimated_minutes': ident.get('estimated_minutes', 0),
                'owners': [ident['owner']] if ident.get('owner') else [],
            }
            by_exam.setdefault(exam_no, []).append(normalized)

        for exam_no, idents in by_exam.items():
            items.append({
                'doc_id': doc_id,
                'doc_name': doc_name,
                'exam_no': exam_no,
                'identifiers': idents,
            })

    return items
