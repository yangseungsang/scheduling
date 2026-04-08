"""
장소 레포지토리 모듈.

시험이 수행되는 장소(location)의 생성, 수정, 조회 기능을 제공한다.
각 장소는 이름, 색상, 설명 정보를 갖는다.
"""

from app.features.schedule.models.base import BaseRepository


class LocationRepository(BaseRepository):
    """장소 데이터를 관리하는 레포지토리.

    JSON 파일(locations.json)에 장소 정보를 저장하고 관리한다.

    Attributes:
        FILENAME: 데이터 파일명 ('locations.json')
        ID_PREFIX: 장소 ID 접두사 ('loc_')
    """

    FILENAME = 'locations.json'
    ID_PREFIX = 'loc_'

    @classmethod
    def create(cls, name, color, description=''):
        """새 장소를 생성한다.

        Args:
            name: 장소 이름 (예: 'A동 시험실')
            color: 시간표에서 사용할 표시 색상 (예: '#FF5733')
            description: 장소 설명 (기본값: 빈 문자열)

        Returns:
            dict: 생성된 장소 데이터 (자동 생성된 ID 포함)
        """
        data = {'name': name, 'color': color, 'description': description}
        return super().create(data)

    @classmethod
    def update(cls, loc_id, name, color, description=''):
        """기존 장소 정보를 수정한다.

        Args:
            loc_id: 수정할 장소 ID
            name: 장소 이름
            color: 표시 색상
            description: 장소 설명 (기본값: 빈 문자열)

        Returns:
            dict 또는 None: 수정된 장소, 해당 ID가 없으면 None
        """
        return cls.patch(loc_id, name=name, color=color, description=description)


# 하위 호환성을 위한 모듈 수준 별칭
get_all = LocationRepository.get_all
get_by_id = LocationRepository.get_by_id
create = LocationRepository.create
update = LocationRepository.update
delete = LocationRepository.delete
