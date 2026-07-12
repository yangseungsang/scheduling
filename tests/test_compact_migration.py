import json
from pathlib import Path

from app.domain.ids import stable_id
from app.services.compact_migration import build_compact_snapshot
from app.services.read_models import (
    build_execution_list_items,
    build_schedule_export_rows,
    build_unscheduled_attempts,
)
from app.services.compact_snapshot_files import build_snapshot_from_files


def _legacy_payload():
    tasks = [
        {
            'id': 't_alpha',
            'doc_id': 10,
            'version_id': 'V1',
            'exam_no': 1,
            'doc_name': '절차 A',
            'assignee_names': ['홍길동'],
            'location_id': 'loc_1',
            'identifiers': [
                {
                    'id': 'TC-001',
                    'name': '부팅',
                    'estimated_minutes': 30,
                    'owners': ['김작성'],
                    'total_count': 5,
                },
                {
                    'id': 'TC-002',
                    'name': '종료',
                    'estimated_minutes': 20,
                    'owners': ['김작성'],
                    'pf_num': 3,
                },
            ],
            'memo': '메모',
        },
        {
            'id': 't_retry',
            'doc_id': 10,
            'version_id': 'V1',
            'exam_no': 2,
            'doc_name': '절차 A',
            'assignee_names': ['홍길동'],
            'location_id': 'loc_2',
            'identifiers': [
                {
                    'id': 'TC-001',
                    'name': '부팅',
                    'estimated_minutes': 35,
                    'owners': ['김작성'],
                    'total_count': 6,
                },
            ],
        },
    ]
    blocks = [
        {
            'id': 'sb_all',
            'task_id': 't_alpha',
            'date': '2026-05-13',
            'start_time': '09:00',
            'end_time': '10:00',
            'location_id': 'loc_1',
            'assignee_names': ['홍길동'],
            'identifier_ids': None,
            'block_status': 'pending',
        },
        {
            'id': 'sb_one',
            'task_id': 't_retry',
            'date': '2026-05-14',
            'start_time': '11:00',
            'end_time': '12:00',
            'location_id': 'loc_2',
            'assignee_names': ['홍길동'],
            'identifier_ids': ['TC-001'],
            'block_status': 'cancelled',
        },
        {
            'id': 'sb_simple',
            'task_id': None,
            'date': '2026-05-15',
            'start_time': '13:00',
            'end_time': '14:00',
            'location_id': 'loc_1',
            'assignee_names': [],
            'title': '회의',
            'is_simple': True,
        },
    ]
    executions = [
        {
            'id': 'ex_1',
            'identifier_id': 'TC-001',
            'task_id': 't_alpha',
            'exam_no': 1,
            'status': 'completed',
            'segments': [{'start': '2026-05-13T09:00:00', 'end': '2026-05-13T09:10:00'}],
            'total_count': 5,
            'fail_count': 1,
            'block_count': 1,
            'pass_count': 3,
            'comment': '완료',
            'performer': '홍길동',
            'created_at': '2026-05-13T09:00:00',
            'completed_at': '2026-05-13T09:10:00',
            'elapsed_seconds': 600,
            'elapsed_mins': 10,
        },
        {
            'id': 'ex_orphan',
            'identifier_id': 'TC-999',
            'task_id': 'missing',
            'status': 'pending',
        },
    ]
    return tasks, blocks, executions


def test_stable_id_is_deterministic():
    assert stable_id('ea_', 'ti_1', 2) == stable_id('ea_', 'ti_1', 2)
    assert stable_id('ea_', 'ti_1', 2) != stable_id('ea_', 'ti_1', 3)


def test_build_compact_snapshot_maps_catalog_schedule_and_executions():
    tasks, blocks, executions = _legacy_payload()

    snapshot = build_compact_snapshot(
        tasks=tasks,
        schedule_blocks=blocks,
        executions=executions,
        users=[{'id': 'u_1', 'name': '홍길동'}],
        locations=[{'id': 'loc_1', 'name': '시험실'}],
        versions=[{'id': 'V1', 'name': '버전'}],
        settings={'work_start': '08:00'},
        provider_cache={'provider': 'dyn_ready', 'updated_at': 'u1', 'data_hash': 'h1'},
    )

    catalog = snapshot['catalog']
    assert catalog['schema_version'] == '1.0'
    assert len(catalog['documents']) == 1
    assert len(catalog['test_items']) == 2
    assert len(catalog['exam_attempts']) == 3
    assert catalog['sync'] == {'provider': 'dyn_ready', 'updated_at': 'u1', 'data_hash': 'h1'}

    tc002 = next(item for item in catalog['test_items'] if item['external_test_id'] == 'TC-002')
    assert tc002['total_count'] == 3

    schedule = snapshot['schedule']
    assert len(schedule['blocks']) == 3
    assert len(schedule['block_items']) == 3
    cancelled = next(block for block in schedule['blocks'] if block['legacy_block_id'] == 'sb_one')
    assert cancelled['manual_status'] == 'cancelled'
    simple = next(block for block in schedule['blocks'] if block['legacy_block_id'] == 'sb_simple')
    assert simple['kind'] == 'simple'
    assert all(item['block_id'] != simple['id'] for item in schedule['block_items'])

    compact_executions = snapshot['executions']
    assert len(compact_executions['runs']) == 1
    run = compact_executions['runs'][0]
    assert run['legacy_execution_id'] == 'ex_1'
    assert run['performer_name'] == '홍길동'
    assert run['elapsed_seconds_snapshot'] == 600
    assert compact_executions['migration']['warnings'] == [
        'ex_orphan: attempt를 찾지 못함: missing/TC-999'
    ]

    assert snapshot['resources']['users'][0]['name'] == '홍길동'
    assert snapshot['settings']['schema_version'] == '1.0'
    assert snapshot['settings']['provider_cache']['dyn_ready']['data_hash'] == 'h1'


def test_read_models_from_compact_snapshot():
    tasks, blocks, executions = _legacy_payload()
    snapshot = build_compact_snapshot(
        tasks=tasks,
        schedule_blocks=blocks,
        executions=executions,
        locations=[
            {'id': 'loc_1', 'name': '1시험실'},
            {'id': 'loc_2', 'name': '2시험실'},
        ],
    )

    execution_items = build_execution_list_items(snapshot)
    assert len(execution_items) == 3
    completed = next(item for item in execution_items if item['external_test_id'] == 'TC-001' and item['exam_no'] == 1)
    assert completed['execution_status'] == 'completed'
    assert completed['location_name'] == '1시험실'
    assert completed['pass_count'] == 3
    assert completed['elapsed_seconds'] == 600

    filtered = build_execution_list_items(snapshot, date_filter='2026-05-14', location_filter='loc_2')
    assert [item['exam_no'] for item in filtered] == [2]

    queue_items = build_unscheduled_attempts(snapshot)
    assert queue_items == []

    export_rows = build_schedule_export_rows(snapshot, '2026-05-13', '2026-05-14')
    assert len(export_rows) == 2
    first = export_rows[0]
    assert first['doc_name'] == '절차 A'
    assert first['external_test_ids'] == ['TC-001', 'TC-002']
    assert first['execution_status'] == 'in_progress'
    second = export_rows[1]
    assert second['split_label'] == '1/3'
    assert second['execution_status'] == 'cancelled'


def test_build_from_files_reads_legacy_dirs(tmp_path):
    tasks, blocks, executions = _legacy_payload()
    schedule_dir = tmp_path / 'schedule'
    execution_dir = tmp_path / 'execution'
    schedule_dir.mkdir()
    execution_dir.mkdir()

    files = {
        schedule_dir / 'tasks.json': tasks,
        schedule_dir / 'schedule_blocks.json': blocks,
        schedule_dir / 'users.json': [],
        schedule_dir / 'locations.json': [],
        schedule_dir / 'versions.json': [],
        schedule_dir / 'settings.json': {'work_start': '08:00'},
        schedule_dir / 'dyn_ready_meta.json': {'updated_at': 'u2', 'data_hash': 'h2'},
        execution_dir / 'executions.json': executions,
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    snapshot = build_snapshot_from_files(Path(schedule_dir), Path(execution_dir))

    assert snapshot['catalog']['sync'] == {
        'provider': 'dyn_ready',
        'updated_at': 'u2',
        'data_hash': 'h2',
    }
    assert len(snapshot['schedule']['block_items']) == 3
