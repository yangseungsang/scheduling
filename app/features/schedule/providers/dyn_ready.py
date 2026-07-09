"""dyn_ready 프로바이더 — 자체 /dyn_ready/std-list/grouped 엔드포인트에서 데이터를 가져온다.

updated_at을 로컬 캐시와 비교하여 변경이 없으면 NoChangesError를 발생시킨다.
identifiers의 exam_no를 기준으로 (doc_id, exam_no) 조합별로 묶어 반환한다.
"""

import hashlib
import json
import os

import requests

from app.features.schedule.providers.base import BaseProvider, NoChangesError

_ENDPOINT = '/dyn_ready/std-list/grouped'
_META_FILE = 'dyn_ready_meta.json'
_TOTAL_COUNT_KEYS = (
    'total_count',
    'test_count',
    'case_count',
    'count',
    'total_tests',
    'total_cases',
    'test_case_count',
    'testcase_count',
    'tc_count',
)


def _meta_path():
    from flask import current_app
    return os.path.join(current_app.config['DATA_DIR'], _META_FILE)


def _load_meta():
    path = _meta_path()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_meta(meta):
    with open(_meta_path(), 'w', encoding='utf-8') as f:
        json.dump(meta, f)


def _data_hash(payload):
    """응답 데이터의 안정적인 지문을 계산한다.

    updated_at이 데이터 삭제를 반영하지 않는 경우에도 실제 응답 내용의
    변화를 감지할 수 있도록 메타데이터와 함께 저장한다.
    """
    serialized = json.dumps(
        payload.get('data', []),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _first_count(ident):
    for key in _TOTAL_COUNT_KEYS:
        value = ident.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


class DynReadyProvider(BaseProvider):

    def __init__(self):
        self.base_url = os.environ.get('DYN_READY_URL', 'http://127.0.0.1:5000').rstrip('/')

    def get_versions(self):
        return []

    def get_test_data(self, version_id):
        return self.get_test_data_all()

    def get_test_data_all(self, force=False):
        """grouped 엔드포인트에서 데이터를 가져와 (doc_id, exam_no) 단위 리스트로 반환한다.

        updated_at과 응답 데이터가 모두 캐시와 동일하면 NoChangesError를
        발생시킨다. 삭제처럼 updated_at에 드러나지 않는 변경은 데이터
        지문 비교로 감지한다.
        force=True이면 updated_at 비교 없이 항상 동기화한다.
        """
        resp = requests.get(f'{self.base_url}{_ENDPOINT}', timeout=10)
        resp.raise_for_status()
        payload = resp.json()

        new_ts = str(payload.get('updated_at', ''))
        new_hash = _data_hash(payload)
        meta = _load_meta()

        if (not force
                and new_ts
                and new_ts == meta.get('updated_at', '')
                and new_hash == meta.get('data_hash', '')):
            raise NoChangesError(new_ts)

        meta['updated_at'] = new_ts
        meta['data_hash'] = new_hash
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
            total_count = _first_count(ident)
            if total_count is not None:
                normalized['total_count'] = total_count
            by_exam.setdefault(exam_no, []).append(normalized)

        for exam_no, idents in by_exam.items():
            items.append({
                'doc_id': doc_id,
                'doc_name': doc_name,
                'exam_no': exam_no,
                'identifiers': idents,
            })

    return items
