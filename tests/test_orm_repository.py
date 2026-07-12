from app.db.models import SourceDocument
from app.db.repository import CompactSnapshotOrmRepository
from app.repositories.compact_snapshot import compact_snapshot_repository_from_config
from app.services.compact_consistency import (
    check_orm_storage_consistency,
    compare_snapshots,
)
from app.services.compact_migration import build_compact_snapshot
from app.services.compact_schedule_commands import CompactScheduleCommandService
from app.services.read_models import build_execution_list_items, build_schedule_export_rows
from app.features.schedule.providers.base import BaseProvider
from app.features.schedule.services.sync import SyncService
from tests.test_compact_migration import _legacy_payload


def _snapshot():
    tasks, blocks, executions = _legacy_payload()
    return build_compact_snapshot(
        tasks=tasks,
        schedule_blocks=blocks,
        executions=executions,
        users=[{'id': 'u_1', 'name': '홍길동'}],
        locations=[
            {'id': 'loc_1', 'name': '1시험실'},
            {'id': 'loc_2', 'name': '2시험실'},
        ],
        versions=[{'id': 'V1', 'name': '버전'}],
        settings={'work_start': '08:00'},
        provider_cache={'provider': 'dyn_ready', 'updated_at': 'u1', 'data_hash': 'h1'},
    )


def test_orm_repository_round_trips_compact_snapshot(tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    snapshot = _snapshot()
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(snapshot)

    loaded = repository.load_snapshot()

    assert loaded['catalog']['sync'] == snapshot['catalog']['sync']
    assert len(loaded['catalog']['documents']) == 1
    assert len(loaded['catalog']['test_items']) == 2
    assert len(loaded['catalog']['exam_attempts']) == 3
    assert len(loaded['schedule']['blocks']) == 3
    assert len(loaded['schedule']['block_items']) == 3
    assert len(loaded['executions']['runs']) == 1
    assert loaded['resources']['locations'][0]['name'] == '1시험실'
    assert loaded['settings']['provider_cache']['dyn_ready']['data_hash'] == 'h1'

    execution_items = build_execution_list_items(loaded)
    assert len(execution_items) == 3
    completed = next(item for item in execution_items if item['execution_status'] == 'completed')
    assert completed['performer_name'] == '홍길동'
    assert completed['elapsed_seconds'] == 600

    export_rows = build_schedule_export_rows(loaded, '2026-05-13', '2026-05-14')
    assert [row['execution_status'] for row in export_rows] == ['in_progress', 'cancelled']


def test_orm_repository_replaces_previous_snapshot(tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())

    empty_snapshot = build_compact_snapshot(tasks=[], schedule_blocks=[], executions=[])
    repository.replace_snapshot(empty_snapshot)

    with repository.session_factory() as session:
        assert session.query(SourceDocument).count() == 0
    loaded = repository.load_snapshot()
    assert loaded['catalog']['documents'] == []
    assert loaded['schedule']['blocks'] == []


def test_external_api_can_read_from_orm_source(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['EXTERNAL_DATA_SOURCE'] = 'orm'

    metadata_response = client.get('/api/external/v1/metadata')
    assert metadata_response.status_code == 200
    metadata = metadata_response.get_json()
    assert metadata['counts']['documents'] == 1
    assert metadata['counts']['execution_runs'] == 1
    assert metadata['sync']['data_hash'] == 'h1'

    schedule_response = client.get(
        '/api/external/v1/schedule?start_date=2026-05-13&end_date=2026-05-13'
    )
    assert schedule_response.status_code == 200
    assert schedule_response.get_json()['schedule']['rows'][0]['doc_name'] == '절차 A'


def test_compact_snapshot_repository_factory_selects_backends(app, tmp_path):
    json_repository = compact_snapshot_repository_from_config(app.config)
    json_snapshot = json_repository.load_snapshot()
    assert json_snapshot['catalog']['documents'] == []

    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    orm_repository = CompactSnapshotOrmRepository(database_url)
    orm_repository.create_schema(drop_existing=True)
    orm_repository.replace_snapshot(_snapshot())

    app.config['DATABASE_URL'] = database_url
    app.config['EXTERNAL_DATA_SOURCE'] = 'orm'
    selected = compact_snapshot_repository_from_config(app.config)
    orm_snapshot = selected.load_snapshot()
    assert len(orm_snapshot['catalog']['documents']) == 1


def test_orm_storage_writes_refresh_compact_snapshot(app, client, tmp_path):
    app.config['DATABASE_URL'] = f'sqlite:///{tmp_path / "storage-sync.db"}'
    app.config['SCHEDULE_STORAGE'] = 'orm'
    app.config['EXECUTION_STORAGE'] = 'orm'
    app.config['EXTERNAL_DATA_SOURCE'] = 'orm'
    app.config['SYNC_COMPACT_ON_ORM_STORAGE_WRITE'] = True

    with app.app_context():
        from app.features.execution.models.execution import ExecutionRepository
        from app.features.schedule.models import location, schedule_block, task

        loc = location.create('1시험실', '#111111')
        created = task.create(
            doc_id=100,
            version_id='V1',
            assignee_names=['홍길동'],
            location_id=loc['id'],
            doc_name='ORM 문서',
            identifiers=[
                {
                    'id': 'TC-ORM',
                    'name': 'ORM 시험',
                    'estimated_minutes': 30,
                    'total_count': 4,
                },
            ],
            estimated_minutes=30,
        )
        schedule_block.create(
            task_id=created['id'],
            assignee_names=['홍길동'],
            location_id=loc['id'],
            date='2026-07-11',
            start_time='09:00',
            end_time='09:30',
            identifier_ids=['TC-ORM'],
        )
        ex = ExecutionRepository.start('TC-ORM', created['id'], total_count=4)
        ExecutionRepository.complete(ex['id'], fail_count=1, block_count=0)

    metadata = client.get('/api/external/v1/metadata').get_json()
    assert metadata['counts']['documents'] == 1
    assert metadata['counts']['execution_runs'] == 1

    executions = client.get('/api/external/v1/executions?date=2026-07-11').get_json()
    item = executions['executions']['items'][0]
    assert item['doc_name'] == 'ORM 문서'
    assert item['external_test_id'] == 'TC-ORM'
    assert item['execution_status'] == 'completed'
    assert item['fail_count'] == 1

    report = check_orm_storage_consistency(app.config['DATABASE_URL'])
    assert report['ok'] is True
    assert report['mismatches'] == []


def test_compact_consistency_reports_mismatched_sections():
    expected = _snapshot()
    actual = build_compact_snapshot(tasks=[], schedule_blocks=[], executions=[])

    report = compare_snapshots(expected, actual)

    assert report['ok'] is False
    assert 'catalog' in report['mismatches']
    assert 'schedule' in report['mismatches']
    assert report['counts']['expected']['documents'] == 1
    assert report['counts']['actual']['documents'] == 0


def test_compact_orm_repository_can_replace_resources_and_settings(tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_resources('locations', [
        {'id': 'loc_1', 'name': '1시험실'},
    ])
    repository.replace_settings({'schema_version': '1.0', 'work_start': '07:30'})

    snapshot = repository.load_snapshot()

    assert snapshot['resources']['locations'] == [{'id': 'loc_1', 'name': '1시험실'}]
    assert snapshot['settings']['work_start'] == '07:30'


def test_compact_schedule_command_writes_blocks_directly(tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    attempt_id = repository.load_snapshot()['catalog']['exam_attempts'][0]['id']

    service = CompactScheduleCommandService(database_url)
    block = service.create_block(
        legacy_block_id='direct_1',
        date='2026-06-01',
        start_time='10:00',
        end_time='10:30',
        location_id='loc_1',
        assignee_names=['홍길동'],
        exam_attempt_ids=[attempt_id],
    )

    loaded = repository.load_snapshot()
    created = next(item for item in loaded['schedule']['blocks'] if item['id'] == block['id'])
    assert created['legacy_block_id'] == 'direct_1'
    assert any(
        item['block_id'] == block['id'] and item['exam_attempt_id'] == attempt_id
        for item in loaded['schedule']['block_items']
    )

    updated = service.update_block(block['id'], date='2026-06-02', memo='변경')
    assert updated['date'] == '2026-06-02'
    assert updated['memo'] == '변경'

    service.replace_block_items(block['id'], [])
    loaded = repository.load_snapshot()
    assert all(item['block_id'] != block['id'] for item in loaded['schedule']['block_items'])

    assert service.delete_block(block['id']) is True
    loaded = repository.load_snapshot()
    assert all(item['id'] != block['id'] for item in loaded['schedule']['blocks'])


def test_compact_schedule_command_rejects_missing_attempt(tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())

    service = CompactScheduleCommandService(database_url)

    try:
        service.create_block(
            date='2026-06-01',
            start_time='10:00',
            end_time='10:30',
            exam_attempt_ids=['ea_missing'],
        )
    except ValueError as exc:
        assert 'ea_missing' in str(exc)
    else:
        raise AssertionError('missing attempt should fail')


def test_compact_orm_schedule_block_api_crud(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'
    app.config['EXTERNAL_DATA_SOURCE'] = 'orm'

    create_response = client.post('/schedule/api/blocks', json={
        'task_id': 't_alpha',
        'date': '2026-06-03',
        'start_time': '09:00',
        'end_time': '09:30',
        'location_id': 'loc_1',
        'assignee_names': ['홍길동'],
        'identifier_ids': ['TC-001'],
    })
    assert create_response.status_code == 201
    block = create_response.get_json()
    assert block['task_id'] == 't_alpha'
    assert block['identifier_ids'] == ['TC-001']

    loaded = repository.load_snapshot()
    assert any(item['id'] == block['id'] for item in loaded['schedule']['blocks'])
    assert any(item['block_id'] == block['id'] for item in loaded['schedule']['block_items'])

    update_response = client.put(f'/schedule/api/blocks/{block["id"]}', json={
        'date': '2026-06-04',
        'block_status': 'cancelled',
        'identifier_ids': ['TC-002'],
    })
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated['date'] == '2026-06-04'
    assert updated['block_status'] == 'cancelled'
    assert updated['identifier_ids'] == ['TC-002']

    lock_response = client.put(f'/schedule/api/blocks/{block["id"]}/lock')
    assert lock_response.status_code == 200
    assert lock_response.get_json()['is_locked'] is True

    status_response = client.put(
        f'/schedule/api/blocks/{block["id"]}/status',
        json={'block_status': 'completed'},
    )
    assert status_response.status_code == 200
    assert status_response.get_json()['block_status'] == 'completed'

    memo_response = client.put(
        f'/schedule/api/blocks/{block["id"]}/memo',
        json={'memo': '현장 확인'},
    )
    assert memo_response.status_code == 200
    assert memo_response.get_json()['memo'] == '현장 확인'

    loaded = repository.load_snapshot()
    persisted = next(item for item in loaded['schedule']['blocks'] if item['id'] == block['id'])
    assert persisted['is_locked'] is True
    assert persisted['manual_status'] == 'completed'
    assert persisted['memo'] == '현장 확인'

    delete_response = client.delete(f'/schedule/api/blocks/{block["id"]}')
    assert delete_response.status_code == 200
    assert delete_response.get_json() == {'success': True}

    loaded = repository.load_snapshot()
    assert all(item['id'] != block['id'] for item in loaded['schedule']['blocks'])
    assert all(item['block_id'] != block['id'] for item in loaded['schedule']['block_items'])


def test_compact_orm_schedule_block_api_rejects_empty_test_block(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    response = client.post('/schedule/api/blocks', json={
        'task_id': 't_alpha',
        'date': '2026-06-03',
        'start_time': '09:00',
        'end_time': '09:30',
        'identifier_ids': [],
    })

    assert response.status_code == 400
    assert response.get_json()['error'] == '연결할 시험 항목을 찾을 수 없습니다.'


def test_compact_orm_schedule_block_item_api_flow(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-items-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    create_response = client.post('/schedule/api/blocks', json={
        'task_id': 't_alpha',
        'date': '2026-06-05',
        'start_time': '09:00',
        'end_time': '10:00',
        'location_id': 'loc_1',
        'assignee_names': ['홍길동'],
    })
    assert create_response.status_code == 201
    block = create_response.get_json()
    assert block['identifier_ids'] == ['TC-001', 'TC-002']

    split_response = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
        'keep_identifier_ids': ['TC-001'],
    })
    assert split_response.status_code == 200
    new_block = split_response.get_json()['new_block']
    assert new_block['identifier_ids'] == ['TC-002']

    by_task_response = client.get('/schedule/api/blocks/by-task/t_alpha')
    assert by_task_response.status_code == 200
    task_blocks = by_task_response.get_json()['blocks']
    created_blocks = [item for item in task_blocks if item['date'] == '2026-06-05']
    assert len(created_blocks) == 2
    original = next(item for item in created_blocks if item['id'] == block['id'])
    assert original['identifier_ids'] == ['TC-001']
    assert original['end_time'] == '09:30'

    shift_response = client.post('/schedule/api/blocks/shift', json={
        'from_date': '2026-06-05',
        'direction': 1,
    })
    assert shift_response.status_code == 200
    assert shift_response.get_json()['shifted_count'] == 2

    shifted_blocks = client.get('/schedule/api/blocks/by-task/t_alpha').get_json()['blocks']
    assert {item['date'] for item in shifted_blocks if item['id'] in {block['id'], new_block['id']}} == {
        '2026-06-08',
    }

    return_response = client.post(
        f'/schedule/api/blocks/{new_block["id"]}/return-identifiers',
        json={'keep_identifier_ids': []},
    )
    assert return_response.status_code == 200
    assert return_response.get_json() == {'success': True}

    loaded = repository.load_snapshot()
    assert all(item['id'] != new_block['id'] for item in loaded['schedule']['blocks'])
    assert all(item['block_id'] != new_block['id'] for item in loaded['schedule']['block_items'])


def test_compact_orm_schedule_day_api_and_export(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-read-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    day_response = client.get('/schedule/api/day?date=2026-05-13')
    assert day_response.status_code == 200
    day_data = day_response.get_json()
    assert day_data['current_date'] == '2026-05-13'
    assert day_data['blocks'][0]['task_title'] == '절차 A'
    assert day_data['blocks'][0]['identifier_ids'] == ['TC-001', 'TC-002']
    assert 'queue_tasks' in day_data

    csv_response = client.get(
        '/schedule/api/export?start_date=2026-05-13&end_date=2026-05-13&format=csv'
    )
    assert csv_response.status_code == 200
    assert 'text/csv' in csv_response.content_type
    body = csv_response.data.decode('utf-8-sig')
    assert '절차 A' in body
    assert '2026-05-13' in body


def test_compact_orm_schedule_week_month_apis_and_views(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-view-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    week_response = client.get('/schedule/api/week?date=2026-05-13')
    assert week_response.status_code == 200
    week_data = week_response.get_json()
    assert week_data['week_start'] == '2026-05-11'
    assert week_data['blocks_by_date']['2026-05-13'][0]['task_title'] == '절차 A'

    month_response = client.get('/schedule/api/month?date=2026-05-13')
    assert month_response.status_code == 200
    month_data = month_response.get_json()
    may_13 = [
        day
        for week in month_data['weeks']
        for day in week
        if day and day['date'] == '2026-05-13'
    ][0]
    assert may_13['blocks'][0]['task_title'] == '절차 A'

    assert client.get('/schedule/?date=2026-05-13').status_code == 200
    assert client.get('/schedule/week?date=2026-05-13').status_code == 200
    assert client.get('/schedule/month?date=2026-05-13').status_code == 200


def test_compact_orm_execution_list_detail_and_start(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-execution-api.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    assert client.get('/execution/').status_code == 200

    list_response = client.get('/execution/api/list?date=2026-05-13')
    assert list_response.status_code == 200
    items = list_response.get_json()
    item = next(
        row
        for row in items
        if row['identifier_id'] == 'TC-001' and row['task_id'] == 't_alpha'
    )
    assert item['execution_status'] == 'completed'
    assert item['result_counts']['total_count'] == 5

    detail_response = client.get('/execution/api/item/TC-001?task_id=t_alpha')
    assert detail_response.status_code == 200
    assert detail_response.get_json()['execution']['status'] == 'completed'

    total_response = client.get('/execution/api/total-count/TC-001?task_id=t_alpha')
    assert total_response.status_code == 200
    assert total_response.get_json()['total_count'] == 5

    start_response = client.post('/execution/api/start', json={
        'identifier_id': 'TC-002',
        'task_id': 't_alpha',
    })
    assert start_response.status_code == 201
    assert start_response.get_json()['exam_no'] == 1


def test_compact_orm_execution_storage_writes_runs_directly(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-execution-storage.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'
    app.config['EXECUTION_STORAGE'] = 'compact_orm'

    start_response = client.post('/execution/api/start', json={
        'identifier_id': 'TC-002',
        'task_id': 't_alpha',
    })
    assert start_response.status_code == 201
    execution = start_response.get_json()
    assert execution['total_count'] == 3

    pause_response = client.post('/execution/api/pause', json={
        'execution_id': execution['id'],
    })
    assert pause_response.status_code == 200
    assert pause_response.get_json()['status'] == 'paused'

    complete_response = client.post('/execution/api/complete', json={
        'execution_id': execution['id'],
        'fail_count': 1,
        'block_count': 0,
    })
    assert complete_response.status_code == 200
    assert complete_response.get_json()['status'] == 'completed'

    loaded = repository.load_snapshot()
    runs = {
        item['id']: item
        for item in loaded['executions']['runs']
    }
    assert runs[execution['id']]['status'] == 'completed'
    assert runs[execution['id']]['fail_count'] == 1

    detail_response = client.get('/execution/api/item/TC-002?task_id=t_alpha')
    assert detail_response.status_code == 200
    assert detail_response.get_json()['execution_status'] == 'completed'


def test_compact_orm_admin_resources_and_settings(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-admin.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    settings_response = client.put('/admin/api/settings', json={'block_color_by': 'location'})
    assert settings_response.status_code == 200
    assert settings_response.get_json()['block_color_by'] == 'location'

    user_response = client.post('/admin/api/users', json={
        'name': '김검증',
        'role': 'tester',
        'color': '#123456',
    })
    assert user_response.status_code == 201

    location_response = client.post('/admin/api/locations', json={
        'name': '3시험실',
        'color': '#654321',
        'description': 'compact',
    })
    assert location_response.status_code == 201

    version_response = client.post('/admin/api/versions', json={
        'name': 'V2',
        'description': 'compact version',
    })
    assert version_response.status_code == 201

    loaded = repository.load_snapshot()
    assert loaded['settings']['block_color_by'] == 'location'
    assert any(item['name'] == '김검증' for item in loaded['resources']['users'])
    assert any(item['name'] == '3시험실' for item in loaded['resources']['locations'])
    assert any(item['name'] == 'V2' for item in loaded['resources']['versions'])


def test_compact_orm_task_read_views_and_api(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-tasks.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'
    app.config['EXECUTION_STORAGE'] = 'compact_orm'

    list_response = client.get('/tasks/')
    assert list_response.status_code == 200

    detail_response = client.get('/tasks/t_alpha')
    assert detail_response.status_code == 200

    api_response = client.get('/tasks/api/t_alpha')
    assert api_response.status_code == 200
    task_data = api_response.get_json()['task']
    assert task_data['doc_name'] == '절차 A'
    assert [item['id'] for item in task_data['identifiers']] == ['TC-001', 'TC-002']


def test_compact_orm_task_api_writes_catalog(app, client, tmp_path):
    database_url = f'sqlite:///{tmp_path / "compact-task-write.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(_snapshot())
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    create_response = client.post('/tasks/api/create', json={
        'doc_id': 77,
        'version_id': 'V2',
        'doc_name': '신규 절차',
        'exam_no': 1,
        'assignee_names': ['김검증'],
        'location_id': 'loc_1',
        'identifiers': [
            {'id': 'TC-NEW-1', 'name': '신규 1', 'estimated_minutes': 11, 'total_count': 2},
            {'id': 'TC-NEW-2', 'name': '신규 2', 'estimated_minutes': 13, 'total_count': 3},
        ],
        'memo': 'compact task',
    })
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created['doc_name'] == '신규 절차'
    assert created['estimated_minutes'] == 24

    update_response = client.put(f'/tasks/api/{created["id"]}/update', json={
        'doc_id': 77,
        'version_id': 'V2',
        'doc_name': '수정 절차',
        'assignee_names': ['김검증'],
        'location_id': 'loc_2',
        'identifiers': [
            {'id': 'TC-NEW-1', 'name': '수정 1', 'estimated_minutes': 15, 'total_count': 4},
        ],
        'memo': 'updated',
    })
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated['doc_name'] == '수정 절차'
    assert updated['identifiers'][0]['estimated_minutes'] == 15

    loaded = repository.load_snapshot()
    attempts = [
        item
        for item in loaded['catalog']['exam_attempts']
        if item['legacy_task_id'] == created['id']
    ]
    assert [item['legacy_identifier_id'] for item in attempts] == ['TC-NEW-1']

    delete_response = client.delete(f'/tasks/api/{created["id"]}/delete')
    assert delete_response.status_code == 200
    loaded = repository.load_snapshot()
    assert all(
        item['legacy_task_id'] != created['id']
        for item in loaded['catalog']['exam_attempts']
    )


def test_compact_orm_sync_test_data_writes_catalog(app, tmp_path):
    class Provider(BaseProvider):
        def get_versions(self):
            return []

        def get_test_data(self, version_id):
            return self.get_test_data_all()

        def get_test_data_all(self):
            return [
                {
                    'doc_id': 88,
                    'doc_name': '동기화 절차',
                    'version_id': 'VSYNC',
                    'exam_no': 1,
                    'identifiers': [
                        {'id': 'TC-SYNC-1', 'name': '동기화 1', 'estimated_minutes': 20},
                    ],
                },
            ]

    database_url = f'sqlite:///{tmp_path / "compact-sync.db"}'
    repository = CompactSnapshotOrmRepository(database_url)
    repository.create_schema(drop_existing=True)
    repository.replace_snapshot(build_compact_snapshot(tasks=[], schedule_blocks=[], executions=[]))
    app.config['DATABASE_URL'] = database_url
    app.config['SCHEDULE_STORAGE'] = 'compact_orm'

    with app.app_context():
        result = SyncService.sync_test_data(Provider())

    assert result['added'] == 1
    loaded = repository.load_snapshot()
    assert loaded['catalog']['documents'][0]['doc_name'] == '동기화 절차'
    assert loaded['catalog']['test_items'][0]['external_test_id'] == 'TC-SYNC-1'

    class EmptyProvider(Provider):
        def get_test_data_all(self):
            return []

    with app.app_context():
        result = SyncService.sync_test_data(EmptyProvider())

    assert result['deleted'] == 1
    assert repository.load_snapshot()['catalog']['exam_attempts'] == []
