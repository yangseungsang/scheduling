"""절차(procedure) 조회 서비스 모듈.

절차 ID로 절차 정보(장절명, 작성자, 시험 목록)를 조회하는 기능을 제공한다.
현재는 로컬 JSON 파일에서 읽어오며, 향후 외부 API 연동으로 교체 가능하다.
"""

from app.features.schedule.store import read_json

FILENAME = 'procedures.json'


def lookup(procedure_id):
    """절차 ID로 절차 정보를 조회한다.

    procedures.json 파일에서 해당 절차 ID와 일치하는 항목을 찾아
    장절명, 작성자, 시험 목록 정보를 반환한다.

    Args:
        procedure_id: 조회할 절차 ID 문자열.

    Returns:
        dict 또는 None: 일치하는 절차가 있으면
            {'section_name': str, 'procedure_owner': str, 'test_list': list},
            없으면 None.
    """
    procedures = read_json(FILENAME)
    for p in procedures:
        if p['procedure_id'] == procedure_id:
            return {
                'section_name': p['section_name'],
                'procedure_owner': p['procedure_owner'],
                'test_list': p['test_list'],
            }
    return None
