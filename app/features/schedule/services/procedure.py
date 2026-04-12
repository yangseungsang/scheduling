"""문서(document) 조회 서비스 모듈.

문서 ID로 문서 정보(문서명, 식별자 목록)를 조회하는 기능을 제공한다.
현재는 로컬 JSON 파일에서 읽어오며, 향후 외부 API 연동으로 교체 가능하다.
"""

from app.features.schedule.store import read_json

FILENAME = 'procedures.json'


def lookup(doc_id):
    """문서 ID로 문서 정보를 조회한다.

    procedures.json 파일에서 해당 doc_id와 일치하는 항목을 찾아
    문서명과 식별자 목록을 반환한다.

    Args:
        doc_id: 조회할 문서 ID (정수 또는 문자열).

    Returns:
        dict 또는 None: 일치하는 문서가 있으면
            {'doc_id': int, 'doc_name': str, 'version_id': str, 'identifiers': list},
            없으면 None.
    """
    try:
        target = int(doc_id)
    except (TypeError, ValueError):
        return None
    for p in read_json(FILENAME):
        if p.get('doc_id') == target:
            return {
                'doc_id': p['doc_id'],
                'doc_name': p.get('doc_name', ''),
                'version_id': p.get('version_id', ''),
                'identifiers': p.get('identifiers', []),
            }
    return None
