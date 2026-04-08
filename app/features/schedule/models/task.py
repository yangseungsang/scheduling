"""
태스크(시험 절차) 레포지토리 모듈.

시험 절차(task)의 생성, 수정, 조회 기능을 제공한다.
각 태스크는 장절명(section_name), 시험 식별자 목록(test_list),
담당자(assignee_ids), 장소(location_id) 등의 정보를 포함한다.
"""

from datetime import datetime

from app.features.schedule.models.base import BaseRepository


class TaskRepository(BaseRepository):
    """시험 절차 데이터를 관리하는 레포지토리.

    JSON 파일(tasks.json)에 태스크 정보를 저장하고 관리한다.

    Attributes:
        FILENAME: 데이터 파일명 ('tasks.json')
        ID_PREFIX: 태스크 ID 접두사 ('t_')
    """

    FILENAME = 'tasks.json'
    ID_PREFIX = 't_'

    @classmethod
    def validate_unique_identifiers(cls, test_list, exclude_task_id=None):
        """식별자 ID의 전역 고유성을 검증한다.

        새로 추가하려는 test_list의 식별자 ID가
        다른 태스크에 이미 존재하는지 확인한다.

        Args:
            test_list: 검증할 식별자 목록 (dict 리스트, 각 dict에 'id' 키 포함)
            exclude_task_id: 검증에서 제외할 태스크 ID
                (태스크 수정 시 자기 자신의 식별자는 제외해야 함)

        Returns:
            list[str]: 중복된 식별자 ID 리스트. 중복이 없으면 빈 리스트.
        """
        # test_list에서 dict 형태인 항목의 ID만 추출
        new_ids = [item['id'] for item in test_list if isinstance(item, dict)]
        if not new_ids:
            return []

        from app.features.schedule.store import read_json
        existing_ids = set()
        for t in read_json(cls.FILENAME):
            # 수정 중인 태스크 자신은 중복 검사에서 제외
            if exclude_task_id and t['id'] == exclude_task_id:
                continue
            for item in t.get('test_list', []):
                # test_list 항목이 dict이면 'id' 키로, 문자열이면 그 자체가 ID
                if isinstance(item, dict):
                    existing_ids.add(item['id'])
                else:
                    existing_ids.add(item)
        return [i for i in new_ids if i in existing_ids]

    @staticmethod
    def compute_estimated_minutes(test_list):
        """식별자 목록에서 총 예상 시간(분)을 계산한다.

        각 식별자의 estimated_minutes 값을 합산한다.

        Args:
            test_list: 식별자 목록 (dict 리스트, 각 dict에 'estimated_minutes' 키 포함)

        Returns:
            int: 총 예상 소요 시간(분 단위)
        """
        total = 0
        for item in (test_list or []):
            if isinstance(item, dict):
                total += item.get('estimated_minutes', 0)
        return total

    @classmethod
    def create(cls, procedure_id, assignee_ids, location_id,
               section_name, procedure_owner, test_list,
               estimated_minutes, memo='', source='local', external_key='',
               **kwargs):
        """새 태스크를 생성한다.

        Args:
            procedure_id: 절차서 ID
            assignee_ids: 시험 담당자 ID 리스트
            location_id: 시험 장소 ID
            section_name: 장절명 (예: '3.1 기능시험')
            procedure_owner: 절차서 작성자
            test_list: 시험 식별자 목록 (dict 리스트)
            estimated_minutes: 총 예상 소요 시간(분)
            memo: 메모 (기본값: 빈 문자열)
            source: 데이터 출처 (기본값: 'local', 외부 동기화 시 다른 값)
            external_key: 외부 시스템 연동 키 (기본값: 빈 문자열)
            **kwargs: 추가 인자 (무시됨)

        Returns:
            dict: 생성된 태스크 데이터 (자동 생성된 ID 포함)
        """
        data = {
            'procedure_id': procedure_id,
            'assignee_ids': assignee_ids or [],
            'location_id': location_id,
            'section_name': section_name,
            'procedure_owner': procedure_owner,
            'test_list': test_list or [],
            'estimated_minutes': estimated_minutes,
            # remaining_minutes: 아직 배치되지 않은 잔여 시간 (초기값 = 예상 시간)
            'remaining_minutes': estimated_minutes,
            'status': 'waiting',
            'memo': memo,
            'source': source,
            'external_key': external_key,
            'created_at': datetime.now().isoformat(timespec='seconds'),
        }
        return super().create(data)

    @classmethod
    def update(cls, task_id, procedure_id, assignee_ids, location_id,
               section_name, procedure_owner, test_list,
               estimated_minutes, remaining_minutes, status, memo=''):
        """기존 태스크를 수정한다.

        Args:
            task_id: 수정할 태스크 ID
            procedure_id: 절차서 ID
            assignee_ids: 시험 담당자 ID 리스트
            location_id: 시험 장소 ID
            section_name: 장절명
            procedure_owner: 절차서 작성자
            test_list: 시험 식별자 목록
            estimated_minutes: 총 예상 소요 시간(분)
            remaining_minutes: 잔여 시간(분)
            status: 태스크 상태 ('waiting', 'scheduled', 'done' 등)
            memo: 메모 (기본값: 빈 문자열)

        Returns:
            dict 또는 None: 수정된 태스크, 해당 ID가 없으면 None
        """
        return cls.patch(
            task_id,
            procedure_id=procedure_id,
            assignee_ids=assignee_ids or [],
            location_id=location_id,
            section_name=section_name,
            procedure_owner=procedure_owner,
            test_list=test_list or [],
            estimated_minutes=estimated_minutes,
            remaining_minutes=remaining_minutes,
            status=status,
            memo=memo,
        )


    @classmethod
    def get_by_external_key(cls, key):
        """외부 시스템 연동 키로 태스크를 조회한다.

        Args:
            key: 외부 시스템에서 부여한 고유 키

        Returns:
            dict 또는 None: 일치하는 태스크, 없으면 None
        """
        for t in cls.get_all():
            if t.get('external_key') == key:
                return t
        return None


# 하위 호환성을 위한 모듈 수준 별칭
get_all = TaskRepository.get_all
get_by_id = TaskRepository.get_by_id
create = TaskRepository.create
update = TaskRepository.update
patch = TaskRepository.patch
delete = TaskRepository.delete
validate_unique_identifiers = TaskRepository.validate_unique_identifiers
compute_estimated_minutes = TaskRepository.compute_estimated_minutes
get_by_external_key = TaskRepository.get_by_external_key
