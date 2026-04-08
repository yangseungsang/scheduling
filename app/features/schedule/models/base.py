"""
기본 레포지토리 모듈.

JSON 파일 기반 CRUD 연산을 제공하는 BaseRepository 클래스를 정의한다.
모든 도메인별 레포지토리(Task, User, Location 등)는 이 클래스를 상속받는다.
"""

from app.features.schedule.store import read_json, write_json, generate_id


class BaseRepository:
    """JSON 파일 기반 레포지토리의 기본 클래스.

    하위 클래스에서 FILENAME, ID_PREFIX를 지정하면
    해당 JSON 파일에 대한 CRUD 기능을 자동으로 제공한다.

    Attributes:
        FILENAME: 데이터가 저장되는 JSON 파일명 (예: 'tasks.json')
        ID_PREFIX: 자동 생성 ID의 접두사 (예: 't_')
        ALLOWED_FIELDS: patch 시 수정 허용 필드 집합. None이면 모든 필드 허용.
    """

    FILENAME = ''
    ID_PREFIX = ''
    ALLOWED_FIELDS = None  # None이면 patch 시 모든 필드 수정 허용

    @classmethod
    def get_all(cls):
        """모든 항목을 조회한다.

        Returns:
            list[dict]: JSON 파일에 저장된 전체 항목 리스트
        """
        return read_json(cls.FILENAME)

    @classmethod
    def get_by_id(cls, item_id):
        """ID로 단일 항목을 조회한다.

        Args:
            item_id: 조회할 항목의 ID

        Returns:
            dict 또는 None: 일치하는 항목, 없으면 None
        """
        for item in read_json(cls.FILENAME):
            if item['id'] == item_id:
                return item
        return None

    @classmethod
    def create(cls, data):
        """새 항목을 생성한다.

        data에 'id'가 없거나 빈 값이면 ID_PREFIX를 사용해 자동 생성한다.

        Args:
            data: 생성할 항목 데이터 (dict)

        Returns:
            dict: ID가 포함된 생성된 항목 데이터
        """
        items = read_json(cls.FILENAME)
        if 'id' not in data or not data['id']:
            # ID가 없으면 접두사 기반으로 고유 ID 자동 생성
            data['id'] = generate_id(cls.ID_PREFIX)
        items.append(data)
        write_json(cls.FILENAME, items)
        return data

    @classmethod
    def patch(cls, item_id, **kwargs):
        """기존 항목의 허용된 필드를 부분 수정한다.

        ALLOWED_FIELDS가 설정되어 있으면 해당 필드만 수정 가능하고,
        None이면 전달된 모든 필드를 수정한다.

        Args:
            item_id: 수정할 항목의 ID
            **kwargs: 수정할 필드와 값 (예: name='새이름', color='#FF0000')

        Returns:
            dict 또는 None: 수정된 항목, 해당 ID가 없으면 None
        """
        items = read_json(cls.FILENAME)
        for item in items:
            if item['id'] == item_id:
                for key, value in kwargs.items():
                    # ALLOWED_FIELDS가 None이면 모든 필드 허용, 아니면 허용 목록 검사
                    if cls.ALLOWED_FIELDS is None or key in cls.ALLOWED_FIELDS:
                        item[key] = value
                write_json(cls.FILENAME, items)
                return item
        return None

    @classmethod
    def delete(cls, item_id):
        """ID에 해당하는 항목을 삭제한다.

        Args:
            item_id: 삭제할 항목의 ID
        """
        items = read_json(cls.FILENAME)
        # 해당 ID를 제외한 나머지 항목만 유지
        items = [item for item in items if item['id'] != item_id]
        write_json(cls.FILENAME, items)

    @classmethod
    def filter_by(cls, **kwargs):
        """주어진 조건에 맞는 항목들을 필터링하여 반환한다.

        모든 필드=값 조건이 동시에 만족하는 항목만 반환한다(AND 조건).

        Args:
            **kwargs: 필터 조건 (예: status='waiting', location_id='loc_abc')

        Returns:
            list[dict]: 조건에 맞는 항목 리스트
        """
        results = []
        for item in read_json(cls.FILENAME):
            # 전달된 모든 키-값 쌍이 항목과 일치하는지 확인
            if all(item.get(k) == v for k, v in kwargs.items()):
                results.append(item)
        return results
