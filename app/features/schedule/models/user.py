"""
사용자 레포지토리 모듈.

시험 담당자(user)의 생성, 수정, 조회 기능을 제공한다.
각 사용자는 이름, 역할, 색상 정보를 갖는다.
"""

from app.features.schedule.models.base import BaseRepository


class UserRepository(BaseRepository):
    """사용자 데이터를 관리하는 레포지토리.

    JSON 파일(users.json)에 사용자 정보를 저장하고 관리한다.

    Attributes:
        FILENAME: 데이터 파일명 ('users.json')
        ID_PREFIX: 사용자 ID 접두사 ('u_')
    """

    FILENAME = 'users.json'
    ID_PREFIX = 'u_'

    @classmethod
    def create(cls, name, role, color):
        """새 사용자를 생성한다.

        Args:
            name: 사용자 이름
            role: 역할 (예: 'tester', 'manager')
            color: 시간표에서 사용할 표시 색상 (예: '#3498DB')

        Returns:
            dict: 생성된 사용자 데이터 (자동 생성된 ID 포함)
        """
        data = {'name': name, 'role': role, 'color': color}
        return super().create(data)

    @classmethod
    def update(cls, user_id, name, role, color):
        """기존 사용자 정보를 수정한다.

        Args:
            user_id: 수정할 사용자 ID
            name: 사용자 이름
            role: 역할
            color: 표시 색상

        Returns:
            dict 또는 None: 수정된 사용자, 해당 ID가 없으면 None
        """
        return cls.patch(user_id, name=name, role=role, color=color)


# 하위 호환성을 위한 모듈 수준 별칭
get_all = UserRepository.get_all
get_by_id = UserRepository.get_by_id
create = UserRepository.create
update = UserRepository.update
delete = UserRepository.delete
