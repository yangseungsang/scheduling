"""
시험실행(Execution) 핵심 데이터 레포지토리.

각 시험 항목(test_item)에 대한 시험 실행 상태를 storage adapter로 관리한다.
실행 데이터는 typed JSON storage를 통해 관리하며 repository는 파일 구조를 알지 않는다.

상태 흐름:
    pending → in_progress → paused ↔ in_progress → completed

일시정지 이력은 저장하지 않는다. 최초 시작, 최종 종료, 실제 수행 시간과
현재 진행 구간의 시작 시각만 관리한다.
"""

from datetime import datetime

from app.features.execution.storage import get_execution_storage

class ExecutionRepository:
    """시험실행 레코드에 대한 CRUD 및 상태 전이 메서드를 제공하는 클래스 레포지토리."""

    @classmethod
    def _storage(cls):
        return get_execution_storage()

    @classmethod
    def get_all(cls):
        """전체 실행 레코드 목록을 반환한다."""
        return cls._storage().get_all()

    @classmethod
    def get_by_test_item(cls, test_item_id):
        """test_item_id로 실행 레코드를 조회한다.

        시험 항목(test_item)와 실행 레코드는 1:1 관계이므로 최대 1개만 존재한다.
        없으면 None을 반환한다.
        """
        for item in cls.get_all():
            if item['test_item_id'] == test_item_id:
                return item
        return None

    @classmethod
    def get_by_test_item_and_procedure(cls, test_item_id: str, procedure_id: str):
        """(test_item_id, procedure_id) 조합으로 실행 레코드를 조회한다."""
        for item in cls.get_all():
            if (item['test_item_id'] == test_item_id
                    and item.get('procedure_id') == procedure_id):
                return item
        return None

    @classmethod
    def _patch(cls, procedure_id, test_item_id, **kwargs):
        """특정 실행 레코드의 필드를 부분 갱신하고 저장한다.

        storage에서 전체 레코드를 읽어 해당 레코드만 업데이트한 뒤 다시 저장한다.
        여러 필드를 한 번에 변경할 때 사용한다.
        """
        storage = cls._storage()
        updated = []
        def patch(items):
            for item in items:
                if (item.get('procedure_id') == procedure_id
                        and item.get('test_item_id') == test_item_id):
                    item.update(kwargs)
                    updated.append(dict(item))
                    break
            return items
        storage.update_all(patch)
        return cls.get_by_test_item_and_procedure(test_item_id, procedure_id) if updated else None

    @classmethod
    def start(cls, test_item_id, procedure_id, total_count=10):
        """시험 실행을 시작(또는 재시작)한다.

        시험 항목에 이미 실행 레코드가 있으면 타이머를 초기화하고 재시작한다.
        (버그 #103 이전에는 중복 생성 문제가 있었으나, 재시작 시 기존 레코드를 patch로 덮어쓴다.)

        재시작 시:
            - 실제 수행 시간을 0으로 초기화
            - fail_count, pass_count를 0으로 리셋
            - 최종 종료 시각을 None으로 초기화

        Args:
            test_item_id: 시험 대상 시험 항목 ID
            procedure_id: 상위 시험 절차서 ID
            total_count: 전체 시험 케이스 수
        """
        now = datetime.now().isoformat(timespec='seconds')
        data = {
            'test_item_id': test_item_id,
            'procedure_id': procedure_id,
            'status': 'in_progress',
            'started_at': now,
            'ended_at': None,
            'active_started_at': now,
            'actual_seconds': 0,
            'total_count': total_count,
            'fail_count': 0,
            'block_count': 0,
            'pass_count': 0,
            'comment': '',
            'performer': '',
        }
        saved = []
        def start(items):
            existing = next((
                item for item in items
                if item['test_item_id'] == test_item_id
                and item.get('procedure_id') == procedure_id
            ), None)
            if existing:
                existing.update({
                    'status': 'in_progress',
                    'started_at': now,
                    'ended_at': None,
                    'active_started_at': now,
                    'actual_seconds': 0,
                    'fail_count': 0,
                    'pass_count': 0,
                    'total_count': total_count,
                })
                saved.append(dict(existing))
            else:
                items.append(data)
                saved.append(dict(data))
            return items
        cls._storage().update_all(start)
        return saved[0]

    @classmethod
    def pause(cls, procedure_id, test_item_id):
        """진행 중인 시험을 일시정지한다.

        현재 진행 구간의 시간을 실제 수행 시간에 더하고 진행 시각을 비운다.

        in_progress 상태가 아니면 None을 반환한다.
        """
        ex = cls.get_by_test_item_and_procedure(test_item_id, procedure_id)
        if not ex or ex['status'] != 'in_progress':
            return None
        return cls._patch(
            procedure_id, test_item_id,
            status='paused',
            actual_seconds=ex.get('elapsed_seconds', 0),
            active_started_at=None,
        )

    @classmethod
    def resume(cls, procedure_id, test_item_id):
        """일시정지된 시험을 재개한다.

        현재 진행 구간의 시작 시각만 기록한다.
        """
        ex = cls.get_by_test_item_and_procedure(test_item_id, procedure_id)
        if not ex or ex['status'] != 'paused':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        return cls._patch(
            procedure_id, test_item_id, status='in_progress', active_started_at=now,
        )

    @classmethod
    def complete(cls, procedure_id, test_item_id, fail_count, block_count=0):
        """시험을 완료 처리한다.

        pass_count는 total - fail - block으로 자동 계산된다.
        in_progress와 paused 둘 다 완료 가능한 상태로 허용한다.
        """
        ex = cls.get_by_test_item_and_procedure(test_item_id, procedure_id)
        if not ex:
            return None
        if ex['status'] not in ('in_progress', 'paused'):
            return None
        now = datetime.now().isoformat(timespec='seconds')
        total_count = ex.get('total_count', 0)
        fail_count = int(fail_count)
        block_count = int(block_count)
        # pass = 전체 - 실패 - 블락 (음수 방지)
        pass_count = max(0, total_count - fail_count - block_count)
        elapsed_seconds = ex.get('elapsed_seconds', 0)
        return cls._patch(
            procedure_id, test_item_id,
            status='completed',
            ended_at=now,
            active_started_at=None,
            actual_seconds=elapsed_seconds,
            fail_count=fail_count,
            block_count=block_count,
            pass_count=pass_count,
        )

    @classmethod
    def update_comment(cls, procedure_id, test_item_id, comment):
        """실행 레코드의 코멘트를 갱신한다."""
        return cls._patch(procedure_id, test_item_id, comment=comment)

    @classmethod
    def update_performer(cls, procedure_id, test_item_id, performer):
        """시험 수행자(performer) 이름을 갱신한다."""
        return cls._patch(procedure_id, test_item_id, performer=performer)

    @classmethod
    def save_pre_comment(cls, test_item_id, procedure_id, comment):
        """시험 시작 전 코멘트를 pending 상태 실행 레코드로 저장한다.

        시험이 아직 시작되지 않은 시험 항목에 대해 코멘트를 미리 저장할 때 사용한다.
        UI에서 '코멘트 저장' 버튼을 누르면 이 메서드가 호출된다.

        - 레코드가 없으면: pending 상태의 새 레코드를 생성
        - pending 상태의 레코드가 있으면: 코멘트만 갱신
        - 이미 진행 중이거나 완료된 레코드면: 덮어쓰지 않고 기존 레코드 반환
          (진행 중 코멘트 변경은 /comment 엔드포인트를 사용해야 함)

        procedure_id로 정확히 조회하여 재시험(동일 test_item, 다른 procedure)과 혼용되지 않게 한다.
        """
        existing = cls.get_by_test_item_and_procedure(test_item_id, procedure_id)
        if existing:
            if existing['status'] == 'pending':
                return cls._patch(procedure_id, test_item_id, comment=comment)
            return existing  # 이미 진행 중 — 덮어쓰지 않음
        data = {
            'test_item_id': test_item_id,
            'procedure_id': procedure_id,
            'status': 'pending',
            'started_at': None,
            'ended_at': None,
            'active_started_at': None,
            'actual_seconds': 0,
            'total_count': 0,
            'fail_count': 0,
            'block_count': 0,
            'pass_count': 0,
            'comment': comment,
            'performer': '',
        }
        saved = []
        def save(items):
            existing = next((
                item for item in items
                if item['test_item_id'] == test_item_id
                and item.get('procedure_id') == procedure_id
            ), None)
            if existing:
                if existing['status'] == 'pending':
                    existing['comment'] = comment
                saved.append(dict(existing))
            else:
                items.append(data)
                saved.append(dict(data))
            return items
        cls._storage().update_all(save)
        return saved[0]

    @classmethod
    def update_action_status(cls, procedure_id, test_item_id, action_status):
        """실행 레코드의 액션 상태를 갱신한다."""
        return cls._patch(procedure_id, test_item_id, action_status=action_status)

    @classmethod
    def update_action_input(cls, procedure_id, test_item_id, action_input):
        """실행 레코드의 액션 입력을 갱신한다."""
        return cls._patch(procedure_id, test_item_id, action_input=action_input)

    @classmethod
    def reset(cls, procedure_id, test_item_id):
        """실행 레코드를 pending(초기) 상태로 되돌린다.

        모든 측정 기록과 카운트, 코멘트, 수행자를 초기화한다.
        재시험이 필요하거나 잘못 시작된 경우에 사용한다.
        """
        return cls._patch(
            procedure_id, test_item_id,
            status='pending',
            started_at=None,
            ended_at=None,
            active_started_at=None,
            actual_seconds=0,
            fail_count=0,
            block_count=0,
            pass_count=0,
            comment='',
            performer='',
        )
