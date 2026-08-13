"""Create representative local data for scheduling and execution screens."""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_VERSION_ID = 'TEST-CYCLE-2026-08'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.domain.execution import ExecutionRun, Executions
from app.domain.scheduling import Schedule, ScheduleBlock
from app.domain.settings import AppSettings
from app.domain.test_procedures import TestItem, TestProcedure
from app.repositories import JsonDomainRepository


def build_seed_data(start_date):
    """Return a connected set of procedures, schedule blocks, runs, and settings."""
    day = date.fromisoformat(start_date)
    next_day = _next_workday(day)
    third_day = _next_workday(next_day)
    now = datetime.now().replace(microsecond=0)

    procedures = (
        TestProcedure(
            id='tp_payment_release', document_id='DOC-1001',
            document_name='결제 서비스 정기 배포', test_round=1,
            test_items=(
                TestItem('PAY-LOGIN', '로그인 및 결제 진입', 90, 24, ('김민지',)),
                TestItem('PAY-REFUND', '취소 및 환불', 120, 18, ('이준호',)),
            ),
            estimated_minutes=210, assignee_names=('김민지', '이준호'),
            location_name='QA Lab A', memo='배포 전 핵심 회귀 시험',
        ),
        TestProcedure(
            id='tp_mobile_release', document_id='DOC-1002',
            document_name='모바일 앱 릴리스', test_round=1,
            test_items=(
                TestItem('APP-ANDROID', 'Android 주요 시나리오', 120, 32, ('박서연',)),
                TestItem('APP-IOS', 'iOS 주요 시나리오', 120, 30, ('박서연', '최현우')),
            ),
            estimated_minutes=240, assignee_names=('박서연', '최현우'),
            location_name='Mobile Lab', memo='스토어 심사 제출 전 확인',
        ),
        TestProcedure(
            id='tp_security_check', document_id='DOC-1003',
            document_name='권한 관리 보안 점검', test_round=2,
            test_items=(
                TestItem('SEC-AUTH', '인증 정책', 90, 20, ('김민지',)),
                TestItem('SEC-PERM', '역할별 접근 권한', 90, 22, ('정다은',)),
            ),
            estimated_minutes=180, assignee_names=('김민지', '정다은'),
            location_name='Security Lab', memo='관리자 권한 변경 포함',
        ),
        TestProcedure(
            id='tp_network_regression', document_id='DOC-1004',
            document_name='네트워크 장애 복구 시험', test_round=1,
            test_items=(
                TestItem('NET-FAILOVER', '회선 절체', 120, 16, ('최현우',)),
                TestItem('NET-RECOVERY', '서비스 자동 복구', 90, 14, ('최현우',)),
            ),
            estimated_minutes=210, assignee_names=('최현우',),
            location_name='Integration Lab', memo='아직 일정이 배정되지 않은 작업',
        ),
    )

    blocks = (
        ScheduleBlock(
            id='blk_payment_login', procedure_id='tp_payment_release',
            test_item_ids=('PAY-LOGIN',), date=day.isoformat(),
            start_time='09:00', end_time='10:30', location_name='QA Lab A',
            assignee_names=('김민지',), is_locked=True,
        ),
        ScheduleBlock(
            id='blk_payment_refund', procedure_id='tp_payment_release',
            test_item_ids=('PAY-REFUND',), date=next_day.isoformat(),
            start_time='09:00', end_time='11:00', location_name='QA Lab A',
            assignee_names=('이준호',),
        ),
        ScheduleBlock(
            id='blk_mobile_android', procedure_id='tp_mobile_release',
            test_item_ids=('APP-ANDROID',), date=day.isoformat(),
            start_time='13:00', end_time='15:00', location_name='Mobile Lab',
            assignee_names=('박서연',), manual_status='in_progress',
        ),
        ScheduleBlock(
            id='blk_mobile_ios', procedure_id='tp_mobile_release',
            test_item_ids=('APP-IOS',), date=next_day.isoformat(),
            start_time='13:00', end_time='15:00', location_name='Mobile Lab',
            assignee_names=('박서연', '최현우'),
        ),
        ScheduleBlock(
            id='blk_security_auth', procedure_id='tp_security_check',
            test_item_ids=('SEC-AUTH',), date=next_day.isoformat(),
            start_time='09:30', end_time='11:00', location_name='Security Lab',
            assignee_names=('김민지',), manual_status='paused',
        ),
        ScheduleBlock(
            id='blk_security_permission', procedure_id='tp_security_check',
            test_item_ids=('SEC-PERM',), date=third_day.isoformat(),
            start_time='09:30', end_time='11:00', location_name='Security Lab',
            assignee_names=('정다은',),
        ),
        ScheduleBlock(
            id='blk_team_sync', date=day.isoformat(), start_time='16:00',
            end_time='16:30', location_name='회의실 2',
            assignee_names=('김민지', '박서연', '최현우'), kind='simple',
            title='시험 진행 상황 공유', memo='이슈와 다음 일정 확인',
        ),
    )

    completed_start = now - timedelta(hours=3)
    completed_end = completed_start + timedelta(minutes=82)
    progress_start = now - timedelta(minutes=35)
    paused_start = now - timedelta(hours=2)
    paused_end = paused_start + timedelta(minutes=47)
    runs = Executions(runs=(
        ExecutionRun(
            procedure_id='tp_payment_release',
            test_item_id='PAY-LOGIN', status='completed',
            started_at=_iso(completed_start), ended_at=_iso(completed_end),
            actual_seconds=82 * 60,
            total_count=24, fail_count=1, block_count=1, pass_count=22,
            comment='환불 권한 관련 이슈 1건 등록', performer_name='김민지',
        ),
        ExecutionRun(
            procedure_id='tp_mobile_release',
            test_item_id='APP-ANDROID', status='in_progress',
            started_at=_iso(progress_start), active_started_at=_iso(progress_start),
            total_count=32,
            performer_name='박서연',
        ),
        ExecutionRun(
            procedure_id='tp_security_check',
            test_item_id='SEC-AUTH', status='paused',
            started_at=_iso(paused_start), actual_seconds=47 * 60,
            total_count=20, fail_count=0, block_count=2, pass_count=9,
            comment='테스트 계정 권한 확인 대기', performer_name='김민지',
        ),
    ))

    settings = AppSettings(
        work_start='08:00', work_end='17:00',
        actual_work_start='08:30', actual_work_end='16:30',
        lunch_start='12:00', lunch_end='13:00',
        breaks=(
            {'start': '09:45', 'end': '10:00'},
            {'start': '14:45', 'end': '15:00'},
        ),
        grid_interval_minutes=15, max_schedule_days=14,
        block_color_by='status',
    )
    return procedures, Schedule(blocks=blocks), runs, settings


def seed(data_dir, start_date, force=False):
    repository = JsonDomainRepository(data_dir)
    repository.initialize()
    current = repository.load_operations()
    if not force and (current.test_procedures or current.schedule_blocks or current.execution_runs):
        raise RuntimeError('기존 데이터가 있습니다. 덮어쓰려면 --force를 사용하세요.')
    procedures, schedule, executions, settings = build_seed_data(start_date)
    repository.replace_all(
        test_procedures=procedures,
        schedule=schedule,
        executions=executions,
        settings=settings,
        version_id=SEED_VERSION_ID,
    )


def _next_workday(value):
    value += timedelta(days=1)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _iso(value):
    return value.isoformat(timespec='seconds')


def main():
    parser = argparse.ArgumentParser(description='로컬 테스트 데이터를 생성합니다.')
    parser.add_argument(
        '--data-dir',
        default=os.path.join(PROJECT_ROOT, 'app', 'data'),
    )
    parser.add_argument('--start-date', default=date.today().isoformat())
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    seed(args.data_dir, args.start_date, args.force)
    print(f'테스트 데이터를 생성했습니다: {os.path.abspath(args.data_dir)}')


if __name__ == '__main__':
    main()
