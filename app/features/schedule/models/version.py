"""
버전 레포지토리 모듈.

스케줄 버전(version)의 생성, 수정, 조회 기능을 제공한다.
버전은 스케줄의 스냅샷 또는 관리 단위를 나타내며,
활성/비활성 상태를 가진다.
"""

from datetime import datetime

from app.features.schedule.models.base import BaseRepository


class VersionRepository(BaseRepository):
    """버전 데이터를 관리하는 레포지토리.

    JSON 파일(versions.json)에 버전 정보를 저장하고 관리한다.

    Attributes:
        FILENAME: 데이터 파일명 ('versions.json')
        ID_PREFIX: 버전 ID 접두사 ('v_')
    """

    FILENAME = 'versions.json'
    ID_PREFIX = 'v_'

    @classmethod
    def get_active(cls):
        """활성 상태인 버전만 조회한다.

        is_active 필드가 True이거나 명시되지 않은 버전을 반환한다.

        Returns:
            list[dict]: 활성 버전 리스트
        """
        # is_active가 명시되지 않은 경우 기본적으로 활성으로 간주
        return [v for v in cls.get_all() if v.get('is_active', True)]

    @classmethod
    def create(cls, name, description='', id=None):
        """새 버전을 생성한다.

        Args:
            name: 버전 이름 (예: 'v1.0', '2026년 4월 1주차')
            description: 버전 설명 (기본값: 빈 문자열)
            id: 지정할 ID (기본값: None이면 자동 생성)

        Returns:
            dict: 생성된 버전 데이터 (ID 포함)
        """
        data = {
            'name': name,
            'description': description,
            'is_active': True,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        # 외부에서 ID를 직접 지정하는 경우 (예: 동기화 시)
        if id:
            data['id'] = id
        return super().create(data)

    @classmethod
    def update(cls, version_id, name, description, is_active=True):
        """기존 버전 정보를 수정한다.

        Args:
            version_id: 수정할 버전 ID
            name: 버전 이름
            description: 버전 설명
            is_active: 활성 상태 (기본값: True)

        Returns:
            dict 또는 None: 수정된 버전, 해당 ID가 없으면 None
        """
        return cls.patch(version_id, name=name, description=description,
                         is_active=is_active)


# 하위 호환성을 위한 모듈 수준 별칭
get_all = VersionRepository.get_all
get_active = VersionRepository.get_active
get_by_id = VersionRepository.get_by_id
create = VersionRepository.create
update = VersionRepository.update
patch = VersionRepository.patch
delete = VersionRepository.delete
