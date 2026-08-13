"""Load grouped test data from the DynReady API."""

import os

import requests

_ENDPOINT = '/dyn_ready/std-list/grouped'


class DynReadyClient:

    def __init__(self):
        self.base_url = os.environ.get('DYN_READY_URL', 'http://127.0.0.1:5000').rstrip('/')

    def get_test_data_all(self):
        """Return the current API data grouped by document and exam number."""
        resp = requests.get(f'{self.base_url}{_ENDPOINT}', timeout=10)
        resp.raise_for_status()
        payload = resp.json()

        return _transform(payload)


def _transform(payload):
    """API 응답을 SyncService가 소비할 수 있는 형태로 변환한다.

    반환 항목마다 'test_round' 키가 포함되어 있어
    SyncService가 추가 조회 없이 바로 사용할 수 있다.
    """
    items = []
    for doc in payload.get('data', []):
        document_id = doc.get('doc_id')
        document_name = doc.get('doc_name', '')

        by_round: dict = {}
        for ident in doc.get('identifiers', []):
            # DynReady의 외부 필드명을 내부 도메인 명칭으로 변환한다.
            test_round = ident.get('exam_no')
            normalized = {
                'id': ident.get('test_id', ''),
                'name': ident.get('func_name', ''),
                'estimated_minutes': ident.get('estimated_minutes', 0),
                'total_count': ident.get('pf_num', 0),
                'owners': [ident['owner']] if ident.get('owner') else [],
            }
            by_round.setdefault(test_round, []).append(normalized)

        for test_round, idents in by_round.items():
            items.append({
                'document_id': document_id,
                'document_name': document_name,
                'test_round': test_round,
                'test_items': idents,
            })

    return items
