"""
스케줄 블록 레포지토리 모듈.

시간표에 배치되는 스케줄 블록의 생성, 수정, 조회 기능을 제공한다.
각 블록은 특정 날짜/시간대에 장소와 담당자가 지정된 시험 일정을 나타낸다.
"""

from app.features.schedule.models.base import BaseRepository
from app.features.schedule.store import read_json, write_json


class ScheduleBlockRepository(BaseRepository):
    """스케줄 블록 데이터를 관리하는 레포지토리.

    JSON 파일(schedule_blocks.json)에 블록 정보를 저장하고 관리한다.
    블록은 시간표 UI에서 드래그/리사이즈/분리 등의 조작이 가능하다.

    Attributes:
        FILENAME: 데이터 파일명 ('schedule_blocks.json')
        ID_PREFIX: 블록 ID 접두사 ('sb_')
        ALLOWED_FIELDS: patch 시 수정 가능한 필드 집합
    """

    FILENAME = 'schedule_blocks.json'
    ID_PREFIX = 'sb_'
    # patch로 수정 가능한 필드를 명시적으로 제한 (보안 및 무결성 보호)
    ALLOWED_FIELDS = {
        'date', 'start_time', 'end_time', 'is_locked',
        'block_status', 'task_id', 'assignee_ids', 'location_id',
        'memo', 'identifier_ids', 'title', 'is_simple',
        'overflow_minutes',
    }

    @classmethod
    def get_by_date(cls, date_str):
        """특정 날짜의 모든 블록을 조회한다.

        Args:
            date_str: 조회할 날짜 문자열 (예: '2026-04-07')

        Returns:
            list[dict]: 해당 날짜의 블록 리스트
        """
        return [b for b in cls.get_all() if b['date'] == date_str]

    @classmethod
    def get_by_date_range(cls, start_date, end_date):
        """날짜 범위 내의 모든 블록을 조회한다.

        Args:
            start_date: 시작 날짜 문자열 (포함)
            end_date: 종료 날짜 문자열 (포함)

        Returns:
            list[dict]: 범위 내 블록 리스트
        """
        return [
            b for b in cls.get_all()
            if start_date <= b['date'] <= end_date
        ]

    @classmethod
    def get_by_assignee(cls, assignee_id):
        """특정 담당자가 포함된 모든 블록을 조회한다.

        Args:
            assignee_id: 담당자 ID

        Returns:
            list[dict]: 해당 담당자가 배정된 블록 리스트
        """
        return [b for b in cls.get_all()
                if assignee_id in b.get('assignee_ids', [])]

    @classmethod
    def get_by_location_and_date(cls, location_id, date_str):
        """특정 장소 + 특정 날짜의 블록을 조회한다.

        Args:
            location_id: 장소 ID
            date_str: 날짜 문자열

        Returns:
            list[dict]: 조건에 맞는 블록 리스트
        """
        return [
            b for b in cls.get_all()
            if b.get('location_id') == location_id and b['date'] == date_str
        ]

    @classmethod
    def create(cls, task_id, assignee_ids, location_id,
               date, start_time, end_time,
               is_locked=False,
               block_status='pending', identifier_ids=None,
               title='', is_simple=False, overflow_minutes=0, **kwargs):
        """새 스케줄 블록을 생성한다.

        Args:
            task_id: 연결된 태스크 ID (간단 블록이면 None 가능)
            assignee_ids: 시험 담당자 ID 리스트
            location_id: 시험 장소 ID
            date: 배치 날짜 (예: '2026-04-07')
            start_time: 시작 시간 (예: '09:00')
            end_time: 종료 시간 (예: '10:30')
            is_locked: 잠금 여부 (잠긴 블록은 이동/리사이즈 불가)
            block_status: 블록 상태 (기본값: 'pending')
            identifier_ids: 이 블록에 배정된 식별자 ID 리스트
                (태스크 분할 시 일부 식별자만 포함 가능)
            title: 간단 블록용 제목 (is_simple=True일 때 사용)
            is_simple: 간단 블록 여부 (태스크 없이 제목만으로 생성)
            overflow_minutes: 초과 시간(분) (블록 시간이 식별자 합계를 초과할 때)
            **kwargs: 추가 인자 (무시됨)

        Returns:
            dict: 생성된 블록 데이터 (자동 생성된 ID 포함)
        """
        data = {
            'task_id': task_id,
            'assignee_ids': assignee_ids or [],
            'location_id': location_id,
            'date': date,
            'start_time': start_time,
            'end_time': end_time,
            'is_locked': is_locked,
            'block_status': block_status,
            'memo': '',
            'identifier_ids': identifier_ids,
            'title': title,
            'is_simple': is_simple,
            'overflow_minutes': overflow_minutes,
        }
        return super().create(data)

    @classmethod
    def update(cls, block_id, **kwargs):
        """기존 스케줄 블록을 수정한다.

        ALLOWED_FIELDS에 포함된 필드만 수정 가능하다.

        Args:
            block_id: 수정할 블록 ID
            **kwargs: 수정할 필드와 값

        Returns:
            dict 또는 None: 수정된 블록, 해당 ID가 없으면 None
        """
        return cls.patch(block_id, **kwargs)



# 하위 호환성을 위한 모듈 수준 별칭
get_all = ScheduleBlockRepository.get_all
get_by_id = ScheduleBlockRepository.get_by_id
get_by_date = ScheduleBlockRepository.get_by_date
get_by_date_range = ScheduleBlockRepository.get_by_date_range
get_by_assignee = ScheduleBlockRepository.get_by_assignee
get_by_location_and_date = ScheduleBlockRepository.get_by_location_and_date
create = ScheduleBlockRepository.create
update = ScheduleBlockRepository.update
delete = ScheduleBlockRepository.delete
