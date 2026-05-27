"""
시험실행(Execution) 핵심 데이터 레포지토리.

각 식별자(identifier)에 대한 시험 실행 상태를 JSON 파일로 관리한다.
DB 없이 store.py의 read_json/write_json을 통해 영속성을 유지한다.

상태 흐름:
    pending → in_progress → paused ↔ in_progress → completed

핵심 개념 — segments:
    segments는 {start, end} 딕셔너리의 리스트로, 실제로 타이머가 동작한
    시간 구간들을 기록한다. end=None이면 현재 진행 중인 구간이다.
    일시정지/재개를 반복하면 segments에 구간이 누적되며,
    compute_elapsed_seconds()는 모든 구간의 합을 계산한다.

    예:
        [
            {"start": "2026-05-13T09:00:00", "end": "2026-05-13T09:30:00"},  # 30분 진행
            {"start": "2026-05-13T10:00:00", "end": None},                   # 현재 진행 중
        ]
"""

from datetime import datetime

from app.features.execution.store import read_json, write_json, generate_id

FILENAME = 'executions.json'
ID_PREFIX = 'ex_'


class ExecutionRepository:
    """시험실행 레코드에 대한 CRUD 및 상태 전이 메서드를 제공하는 클래스 레포지토리."""

    @classmethod
    def get_all(cls):
        """전체 실행 레코드 목록을 반환한다."""
        return read_json(FILENAME)

    @classmethod
    def get_by_id(cls, execution_id):
        """execution_id로 단일 실행 레코드를 조회한다. 없으면 None."""
        for item in read_json(FILENAME):
            if item['id'] == execution_id:
                return item
        return None

    @classmethod
    def get_by_identifier(cls, identifier_id):
        """identifier_id로 실행 레코드를 조회한다.

        식별자(identifier)와 실행 레코드는 1:1 관계이므로 최대 1개만 존재한다.
        없으면 None을 반환한다.
        """
        for item in read_json(FILENAME):
            if item['identifier_id'] == identifier_id:
                return item
        return None

    @classmethod
    def get_by_identifier_and_task(cls, identifier_id: str, task_id: str):
        """(identifier_id, task_id) 조합으로 실행 레코드를 조회한다."""
        for item in read_json(FILENAME):
            if (item['identifier_id'] == identifier_id
                    and item.get('task_id') == task_id):
                return item
        return None

    @staticmethod
    def compute_elapsed_seconds(segments):
        """segments 리스트를 기반으로 실제 경과 시간(초)을 계산한다.

        닫힌 구간(end 있음): end - start 합산
        열린 구간(end=None): 현재 시각까지의 시간을 실시간으로 포함

        일시정지 상태에서도 마지막 구간이 닫혀 있으므로 현재 시각은 포함되지 않는다.
        결과가 음수가 될 수 없도록 max(0, ...) 처리한다.
        """
        total = 0
        now = datetime.now()
        for seg in segments:
            start = datetime.fromisoformat(seg['start'])
            # end가 None이면 아직 진행 중인 구간 → 현재 시각을 종료 시점으로 사용
            end = datetime.fromisoformat(seg['end']) if seg['end'] else now
            total += int((end - start).total_seconds())
        return max(0, total)

    @classmethod
    def _patch(cls, execution_id, **kwargs):
        """특정 실행 레코드의 필드를 부분 갱신하고 저장한다.

        전체 파일을 읽어 해당 레코드만 업데이트한 뒤 다시 쓰는 방식으로 동작한다.
        파일 I/O가 한 번 발생하므로 여러 필드를 한 번에 변경할 때 사용한다.
        """
        items = read_json(FILENAME)
        for item in items:
            if item['id'] == execution_id:
                item.update(kwargs)
                write_json(FILENAME, items)
                return item
        return None

    @classmethod
    def start(cls, identifier_id, task_id, total_count=10):
        """시험 실행을 시작(또는 재시작)한다.

        식별자에 이미 실행 레코드가 있으면 타이머를 초기화하고 재시작한다.
        (버그 #103 이전에는 중복 생성 문제가 있었으나, 재시작 시 기존 레코드를 patch로 덮어쓴다.)

        재시작 시:
            - segments를 새 단일 구간으로 초기화 (이전 측정 기록 폐기)
            - fail_count, pass_count를 0으로 리셋
            - completed_at을 None으로 초기화

        Args:
            identifier_id: 시험 대상 식별자 ID
            task_id: 상위 태스크 ID (외부 API 소요시간 전송 시 version_id 조회에 사용)
            total_count: 전체 시험 케이스 수
        """
        now = datetime.now().isoformat(timespec='seconds')
        existing = cls.get_by_identifier_and_task(identifier_id, task_id)
        if existing:
            # 이미 레코드가 있으면 새 레코드를 만들지 않고 기존 레코드를 초기화하여 재사용
            return cls._patch(
                existing['id'],
                status='in_progress',
                segments=[{'start': now, 'end': None}],
                fail_count=0,
                pass_count=0,
                total_count=total_count,
                completed_at=None,
            )
        data = {
            'id': generate_id(ID_PREFIX),
            'identifier_id': identifier_id,
            'task_id': task_id,
            'status': 'in_progress',
            'segments': [{'start': now, 'end': None}],  # 첫 번째 구간 시작
            'total_count': total_count,
            'fail_count': 0,
            'block_count': 0,
            'pass_count': 0,
            'comment': '',
            'performer': '',
            'created_at': now,
            'completed_at': None,
        }
        items = read_json(FILENAME)
        items.append(data)
        write_json(FILENAME, items)
        return data

    @classmethod
    def pause(cls, execution_id):
        """진행 중인 시험을 일시정지한다.

        열린 마지막 구간의 end를 현재 시각으로 닫아 타이머를 멈춘다.
        elapsed_seconds를 스냅샷으로 저장해 두어, 재개 전에도 UI에서
        경과 시간을 정확히 표시할 수 있게 한다.

        in_progress 상태가 아니면 None을 반환한다.
        """
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'in_progress':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = list(ex['segments'])
        if segments:
            # 마지막 구간의 end를 현재 시각으로 닫아 타이머 정지
            segments[-1] = {**segments[-1], 'end': now}
        elapsed_seconds = cls.compute_elapsed_seconds(segments)
        return cls._patch(execution_id, status='paused', segments=segments, elapsed_seconds=elapsed_seconds)

    @classmethod
    def resume(cls, execution_id):
        """일시정지된 시험을 재개한다.

        새 구간 {start: 현재시각, end: None}을 segments 끝에 추가하여
        타이머를 다시 시작한다. paused 상태가 아니면 None을 반환한다.
        """
        ex = cls.get_by_id(execution_id)
        if not ex or ex['status'] != 'paused':
            return None
        now = datetime.now().isoformat(timespec='seconds')
        # 기존 segments에 새 구간을 추가 (일시정지 중의 공백 시간은 포함되지 않음)
        segments = ex['segments'] + [{'start': now, 'end': None}]
        return cls._patch(execution_id, status='in_progress', segments=segments)

    @classmethod
    def complete(cls, execution_id, fail_count, block_count=0):
        """시험을 완료 처리한다.

        핵심 설계: 열린 구간(end=None)만 닫는다.
        일시정지(paused) 상태로 완료하면 마지막 구간이 이미 닫혀 있으므로
        segments를 건드리지 않는다. 이를 처리하지 않으면 end=None인 구간 없이도
        완료가 가능해야 한다는 점을 놓쳐 segments 마지막이 잘못 덮어씌워지는
        버그(#103)가 발생할 수 있다.

        pass_count는 total - fail - block으로 자동 계산된다.
        in_progress와 paused 둘 다 완료 가능한 상태로 허용한다.
        """
        ex = cls.get_by_id(execution_id)
        if not ex:
            return None
        if ex['status'] not in ('in_progress', 'paused'):
            return None
        now = datetime.now().isoformat(timespec='seconds')
        segments = list(ex['segments'])
        # 열린 구간만 닫는다 — paused 상태면 이미 닫혀 있어 이 블록을 건너뜀
        if segments and segments[-1]['end'] is None:
            segments[-1] = {**segments[-1], 'end': now}
        total_count = ex.get('total_count', 0)
        fail_count = int(fail_count)
        block_count = int(block_count)
        # pass = 전체 - 실패 - 블락 (음수 방지)
        pass_count = max(0, total_count - fail_count - block_count)
        elapsed_seconds = cls.compute_elapsed_seconds(segments)
        return cls._patch(
            execution_id,
            status='completed',
            segments=segments,
            fail_count=fail_count,
            block_count=block_count,
            pass_count=pass_count,
            completed_at=now,
            elapsed_seconds=elapsed_seconds,
        )

    @classmethod
    def update_comment(cls, execution_id, comment):
        """실행 레코드의 코멘트를 갱신한다."""
        return cls._patch(execution_id, comment=comment)

    @classmethod
    def update_performer(cls, execution_id, performer):
        """시험 수행자(performer) 이름을 갱신한다."""
        return cls._patch(execution_id, performer=performer)

    @classmethod
    def save_pre_comment(cls, identifier_id, task_id, comment):
        """시험 시작 전 코멘트를 pending 상태 실행 레코드로 저장한다.

        시험이 아직 시작되지 않은 식별자에 대해 코멘트를 미리 저장할 때 사용한다.
        UI에서 '코멘트 저장' 버튼을 누르면 이 메서드가 호출된다.

        - 레코드가 없으면: pending 상태의 새 레코드를 생성
        - pending 상태의 레코드가 있으면: 코멘트만 갱신
        - 이미 진행 중이거나 완료된 레코드면: 덮어쓰지 않고 기존 레코드 반환
          (진행 중 코멘트 변경은 /comment 엔드포인트를 사용해야 함)

        task_id로 정확히 조회하여 재시험(동일 identifier, 다른 task)과 혼용되지 않게 한다.
        """
        existing = cls.get_by_identifier_and_task(identifier_id, task_id)
        if existing:
            if existing['status'] == 'pending':
                return cls._patch(existing['id'], comment=comment)
            return existing  # 이미 진행 중 — 덮어쓰지 않음
        now = datetime.now().isoformat(timespec='seconds')
        data = {
            'id': generate_id(ID_PREFIX),
            'identifier_id': identifier_id,
            'task_id': task_id,
            'status': 'pending',
            'segments': [],          # 아직 시작 전이므로 구간 없음
            'total_count': 0,
            'fail_count': 0,
            'block_count': 0,
            'pass_count': 0,
            'comment': comment,
            'performer': '',
            'created_at': now,
            'completed_at': None,
            'elapsed_seconds': 0,
        }
        items = read_json(FILENAME)
        items.append(data)
        write_json(FILENAME, items)
        return data

    @classmethod
    def reset(cls, execution_id):
        """실행 레코드를 pending(초기) 상태로 되돌린다.

        모든 측정 기록(segments, 카운트, 코멘트, 수행자)을 초기화한다.
        재시험이 필요하거나 잘못 시작된 경우에 사용한다.
        """
        return cls._patch(
            execution_id,
            status='pending',
            segments=[],
            fail_count=0,
            block_count=0,
            pass_count=0,
            comment='',
            performer='',
            completed_at=None,
            elapsed_seconds=0,
        )
