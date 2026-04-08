"""JSON 파일 기반 데이터 프로바이더 모듈.

로컬 JSON 파일(versions.json, procedures.json)에서 버전 및 시험 데이터를
읽어오는 기본 프로바이더 구현. 외부 API 없이 독립적으로 동작하며,
기존 데이터 구조와의 하위 호환성을 유지한다.
"""

from app.features.schedule.providers.base import BaseProvider
from app.features.schedule.store import read_json


class JsonFileProvider(BaseProvider):
    """로컬 JSON 파일에서 데이터를 읽어오는 프로바이더.

    data/ 디렉토리의 versions.json과 procedures.json 파일을 사용한다.
    별도의 외부 연동 없이 동작하는 기본(default) 프로바이더이다.
    """

    def get_versions(self):
        """versions.json에서 버전 목록을 읽어온다.

        Returns:
            list: [{'id': str, 'name': str, 'description': str}, ...] 형태의 버전 목록.
        """
        return [
            {'id': v['id'], 'name': v['name'], 'description': v.get('description', '')}
            for v in read_json('versions.json')
        ]

    def get_test_data(self, version_id):
        """특정 버전 ID에 해당하는 시험 데이터만 필터링하여 반환한다.

        Args:
            version_id: 조회할 버전 ID.

        Returns:
            list: 해당 버전의 시험 데이터 딕셔너리 목록.
        """
        return [
            item for item in self._read_procedures()
            if item['version_id'] == version_id
        ]

    def get_test_data_all(self):
        """모든 버전의 시험 데이터를 반환한다.

        Returns:
            list: 전체 시험 데이터 딕셔너리 목록.
        """
        return self._read_procedures()

    def _read_procedures(self):
        """procedures.json 파일을 읽어 표준 형식으로 변환한다.

        JSON 파일의 'test_list' 키도 'identifiers'로 인식하여
        하위 호환성을 유지한다.

        Returns:
            list: [{'section_name': str, 'version_id': str,
                    'identifiers': list}, ...] 형태의 시험 데이터 목록.
        """
        raw = read_json('procedures.json')
        result = []
        for p in raw:
            result.append({
                'section_name': p.get('section_name', ''),
                'version_id': p.get('version_id', ''),
                # 'identifiers' 키 우선, 없으면 'test_list' 키로 폴백 (하위 호환)
                'identifiers': p.get('identifiers', p.get('test_list', [])),
            })
        return result
