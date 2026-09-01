import json
from dataclasses import replace

from app.repositories import JsonDomainRepository, init_repository
from app.features.execution.domain import Executions
from app.features.schedule.domain import AppSettings, Schedule, TestProcedure
from app.features.schedule.services._block_commands import ScheduleCommandService
from app.services.read_models import build_execution_list_items, build_schedule_export_rows
from app.features.schedule.services.sync import SyncService


def _domain_sections():
    procedures = tuple(TestProcedure.from_dict(item) for item in [
            {
                'id': 't_alpha', 'document_id': '10',
                'document_name': '절차 A', 'test_round': 1,
                'location_name': 'loc_1', 'assignee_names': ['홍길동'],
                'estimated_minutes': 55,
                'test_items': [
                    {
                        'id': 'TC-001', 'name': '부팅',
                        'estimated_minutes': 35, 'total_count': 6,
                        'owner_names': ['김작성'],
                    },
                    {
                        'id': 'TC-002', 'name': '종료',
                        'estimated_minutes': 20, 'total_count': 3,
                        'owner_names': ['김작성'],
                    },
                ],
            },
            {
                'id': 't_retry', 'document_id': '10',
                'document_name': '절차 A', 'test_round': 2,
                'location_name': 'loc_2', 'assignee_names': ['홍길동'],
                'estimated_minutes': 35,
                'test_items': [{
                    'id': 'TC-001', 'name': '부팅',
                    'estimated_minutes': 35, 'total_count': 6,
                    'owner_names': ['김작성'],
                }],
            },
        ])
    schedule = Schedule.from_dict({
        'blocks': [
            {
                'id': 'blk_1', 'date': '2026-05-13', 'start_time': '09:00',
                'end_time': '10:00', 'location_name': 'STE1',
                'assignee_names': ['홍길동'], 'procedure_id': 't_alpha',
                'test_item_ids': ['TC-001', 'TC-002'],
            },
            {
                'id': 'blk_2', 'date': '2026-05-14', 'start_time': '11:00',
                'end_time': '12:00', 'location_name': 'STE2',
                'assignee_names': ['홍길동'], 'manual_status': 'cancelled',
                'procedure_id': 't_retry', 'test_item_ids': ['TC-001'],
            },
            {
                'id': 'blk_3', 'date': '2026-05-15', 'start_time': '13:00',
                'end_time': '14:00', 'location_name': 'STE1',
                'title': '회의',
            },
        ],
    })
    executions = Executions.from_dict({
        'runs': [{
            'procedure_id': 't_alpha', 'test_item_id': 'TC-001',
            'status': 'completed',
            'started_at': '2026-05-13T09:00:00',
            'ended_at': '2026-05-13T09:10:00', 'actual_seconds': 600,
            'total_count': 5, 'fail_count': 1, 'block_count': 1, 'pass_count': 3,
            'performer_name': '홍길동', 'elapsed_seconds': 600, 'elapsed_minutes': 10,
        }],
    })
    settings = AppSettings.from_dict({
        'work_start': '08:00',
    })
    return procedures, schedule, executions, settings


def _empty_sections():
    return (), Schedule(), Executions(), AppSettings()


def _replace_domain_data(repository, sections=None):
    procedures, schedule, executions, settings = sections or _domain_sections()
    repository.replace_all(
        test_procedures=procedures,
        schedule=schedule,
        executions=executions,
        settings=settings,
    )


def _loaded_domain_data(repository):
    return {
        'test_procedures': [item.to_dict() for item in repository.load_test_procedures()],
        'schedule': repository.load_schedule().to_dict(),
        'executions': repository.load_executions().to_dict(),
        'settings': repository.load_settings().to_dict(),
    }


def _domain_payload(sections):
    procedures, schedule, executions, settings = sections
    return {
        'test_procedures': [item.to_dict() for item in procedures],
        'schedule': schedule.to_dict(),
        'executions': executions.to_dict(),
        'settings': settings.to_dict(),
    }


def test_json_repository_round_trips_domain_sections(tmp_path):
    data_dir = tmp_path / 'domain-data'
    sections = _domain_sections()
    expected = _domain_payload(sections)
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository, sections)

    loaded = _loaded_domain_data(repository)

    assert isinstance(repository.load_test_procedures(), tuple)
    assert isinstance(repository.load_schedule(), Schedule)
    assert isinstance(repository.load_executions(), Executions)
    assert isinstance(repository.load_settings(), AppSettings)
    assert not (data_dir / 'catalog.json').exists()
    assert not (data_dir / 'versions.json').exists()
    assert not (data_dir / 'users.json').exists()
    assert not (data_dir / 'locations.json').exists()
    assert not (data_dir / 'procedures.json').exists()
    assert not (data_dir / 'schedule.json').exists()
    assert not (data_dir / 'executions.json').exists()
    assert (data_dir / 'test_plan.json').exists()
    assert (data_dir / 'test_executions.json').exists()
    assert repository.load_operations().version_id == ''

    assert loaded['test_procedures'] == expected['test_procedures']
    assert len(loaded['test_procedures']) == 2
    assert len(loaded['test_procedures'][0]['test_items']) == 2
    assert len(loaded['schedule']['blocks']) == 3
    assert len(loaded['executions']['runs']) == 1
    assert loaded['settings']['work_start'] == '08:00'

    execution_items = build_execution_list_items(*sections[:3])
    assert len(execution_items) == 3
    completed = next(item for item in execution_items if item['execution_status'] == 'completed')
    assert completed['performer_name'] == '홍길동'
    assert completed['elapsed_seconds'] == 600

    export_rows = build_schedule_export_rows(*sections[:3], '2026-05-13', '2026-05-14')
    assert [row['execution_status'] for row in export_rows] == ['in_progress', 'cancelled']


def test_loads_specific_procedure_information_from_json(tmp_path):
    """로드한 domain 객체에서 원하는 procedure의 일부 정보만 선택한다."""
    # 실제 app/data 대신 테스트 전용 임시 디렉터리를 사용한다.
    repository = JsonDomainRepository(tmp_path / 'domain-data')
    repository.initialize(reset=True)
    _replace_domain_data(repository)

    # JSON 전체를 직접 열지 않고 repository를 통해 domain 객체를 로드한다.
    procedures = repository.load_test_procedures()

    # 로드된 목록에서 필요한 ID의 procedure 하나만 찾는다.
    procedure = next(
        (item for item in procedures if item.id == 't_alpha'),
        None,
    )

    # 찾은 객체에서 필요한 필드만 속성으로 조회한다.
    assert procedure is not None
    assert procedure.document_name == '절차 A'
    assert not hasattr(procedure, 'location_name')
    assert 'location_name' not in procedure.to_dict()


def test_updates_specific_procedure_information_in_json(tmp_path):
    """특정 procedure만 변경하고 JSON에 저장된 결과를 다시 확인한다."""
    # 실제 app/data를 건드리지 않도록 테스트 전용 저장소를 준비한다.
    repository = JsonDomainRepository(tmp_path / 'domain-data')
    repository.initialize(reset=True)
    _replace_domain_data(repository)

    # TestProcedure는 불변 객체이므로 replace()로 변경된 복사본을 만든다.
    # update_test_procedures()는 변경 결과를 잠금 안에서 JSON에 저장한다.
    repository.update_test_procedures(lambda procedures: tuple(
        replace(item, memo='수정됨')
        if item.id == 't_alpha'
        else item
        for item in procedures
    ))

    # 저장소에서 다시 로드하여 변경 내용이 실제로 반영됐는지 확인한다.
    procedures = repository.load_test_procedures()
    updated = next(item for item in procedures if item.id == 't_alpha')
    unchanged = next(item for item in procedures if item.id == 't_retry')

    # 대상 procedure만 수정되고 나머지 데이터는 유지되어야 한다.
    assert updated.memo == '수정됨'
    assert unchanged.memo == ''


def test_concurrent_operations_preserve_unrelated_procedure_changes(tmp_path):
    repository = JsonDomainRepository(tmp_path / 'domain-data')
    repository.initialize(reset=True)
    repository.set_version_id('cycle-1')
    barrier = Barrier(2)

    def append_procedure(procedure_id):
        barrier.wait()
        procedure = TestProcedure.from_dict({
            'id': procedure_id,
            'document_name': procedure_id,
            'test_items': [{'id': f'{procedure_id}-test_item'}],
        })

        def update(procedures):
            time.sleep(0.03)
            return procedures + (procedure,)

        repository.update_test_procedures(update)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(append_procedure, ('procedure-a', 'procedure-b')))

    operations = repository.load_operations()
    assert {procedure.id for procedure in operations.test_procedures} == {'procedure-a', 'procedure-b'}
    assert operations.version_id == 'cycle-1'


def test_plan_and_execution_updates_write_only_their_own_file(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    plan_path = data_dir / 'test_plan.json'
    executions_path = data_dir / 'test_executions.json'

    executions_before = executions_path.read_bytes()
    repository.update_test_procedures(lambda procedures: procedures + (TestProcedure.from_dict({
        'id': 't_new', 'document_name': '추가 작업',
    }),))
    assert executions_path.read_bytes() == executions_before

    plan_before = plan_path.read_bytes()
    repository.update_executions(lambda executions: Executions(
        runs=executions.runs[:-1],
    ))
    assert plan_path.read_bytes() == plan_before


def test_json_repository_replaces_previous_domain_data(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)

    _replace_domain_data(
        repository,
        _empty_sections(),
    )
    loaded = _loaded_domain_data(repository)
    assert loaded['test_procedures'] == []
    assert loaded['schedule']['blocks'] == []


def test_domain_json_files_contain_only_their_owned_data(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    repository.replace_all(
        test_procedures=(TestProcedure.from_dict({
            'id': 't_minimal', 'document_id': '1', 'document_name': '최소 작업',
        }),),
        schedule=Schedule.from_dict({'blocks': [{
            'id': 'blk_minimal', 'procedure_id': 't_minimal',
            'date': '2026-08-10', 'start_time': '09:00', 'end_time': '10:00',
        }]}),
        executions=Executions.from_dict({'runs': [{
            'procedure_id': 't_minimal',
            'test_item_id': 'TC-1', 'status': 'pending',
        }]}),
        settings=AppSettings(),
        version_id='CYCLE-1',
    )

    with open(data_dir / 'test_plan.json', encoding='utf-8') as file:
        plan_data = json.load(file)
    with open(data_dir / 'test_executions.json', encoding='utf-8') as file:
        execution_data = json.load(file)

    assert set(plan_data) == {'version_id', 'test_procedures', 'schedule_blocks'}
    assert set(execution_data) == {'execution_runs'}
    assert 'version_id' not in plan_data['test_procedures'][0]
    assert 'state' not in plan_data['test_procedures'][0]
    assert 'is_locked' not in plan_data['schedule_blocks'][0]
    assert 'id' not in execution_data['execution_runs'][0]
    assert 'segments' not in execution_data['execution_runs'][0]
    assert 'kind' not in plan_data['schedule_blocks'][0]

def test_json_repository_can_replace_settings(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    repository.replace_settings({'schema_version': '1.0', 'work_start': '07:30'})

    loaded = _loaded_domain_data(repository)

    assert loaded['settings']['work_start'] == '07:30'


def test_schedule_command_writes_typed_json(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    service = ScheduleCommandService(repository)
    block = service.create_block(
        block_id='blk_direct_1',
        date='2026-06-01',
        start_time='10:00',
        end_time='10:30',
        location_name='loc_1',
        assignee_names=['홍길동'],
        procedure_id='t_alpha',
        test_item_ids=['TC-001'],
    )

    loaded = _loaded_domain_data(repository)
    created = next(item for item in loaded['schedule']['blocks'] if item['id'] == block['id'])
    assert created['id'] == 'blk_direct_1'
    assert created['procedure_id'] == 't_alpha'
    assert created['test_item_ids'] == ['TC-001']

    updated = service.update_block(block['id'], date='2026-06-02', memo='변경')
    assert updated['date'] == '2026-06-02'
    assert updated['memo'] == '변경'

    service.replace_test_items(block['id'], [])
    loaded = _loaded_domain_data(repository)
    created = next(item for item in loaded['schedule']['blocks'] if item['id'] == block['id'])
    assert created.get('test_item_ids', []) == []

    assert service.delete_block(block['id']) is True
    loaded = _loaded_domain_data(repository)
    assert all(item['id'] != block['id'] for item in loaded['schedule']['blocks'])


def test_json_schedule_command_rejects_missing_test_item(tmp_path):
    data_dir = tmp_path / 'domain-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)

    service = ScheduleCommandService(repository)

    try:
        service.create_block(
            date='2026-06-01',
            start_time='10:00',
            end_time='10:30',
            procedure_id='t_alpha',
            test_item_ids=['TC-MISSING'],
        )
    except ValueError as exc:
        assert 'TC-MISSING' in str(exc)
    else:
        raise AssertionError('missing test_item should fail')


def test_domain_json_schedule_block_api_crud(app, client, tmp_path):
    data_dir = tmp_path / 'api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    create_response = client.post('/schedule/api/blocks', json={
        'procedure_id': 't_alpha',
        'date': '2026-06-03',
        'start_time': '09:00',
        'end_time': '09:30',
            'location_name': 'STE1',
        'assignee_names': ['홍길동'],
        'test_item_ids': ['TC-001'],
    })
    assert create_response.status_code == 201
    block = create_response.get_json()
    assert block['procedure_id'] == 't_alpha'
    assert block['test_item_ids'] == ['TC-001']

    loaded = _loaded_domain_data(repository)
    assert any(item['id'] == block['id'] for item in loaded['schedule']['blocks'])

    update_response = client.put(f'/schedule/api/blocks/{block["id"]}', json={
        'date': '2026-06-04',
        'block_status': 'cancelled',
        'test_item_ids': ['TC-002'],
    })
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated['date'] == '2026-06-04'
    assert updated['block_status'] == 'cancelled'
    assert updated['test_item_ids'] == ['TC-002']

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

    loaded = _loaded_domain_data(repository)
    persisted = next(item for item in loaded['schedule']['blocks'] if item['id'] == block['id'])
    assert persisted['is_locked'] is True
    assert persisted['manual_status'] == 'completed'
    assert persisted['memo'] == '현장 확인'

    delete_response = client.delete(f'/schedule/api/blocks/{block["id"]}')
    assert delete_response.status_code == 200
    assert delete_response.get_json() == {'success': True}

    loaded = _loaded_domain_data(repository)
    assert all(item['id'] != block['id'] for item in loaded['schedule']['blocks'])


def test_domain_json_schedule_block_api_rejects_empty_test_block(app, client, tmp_path):
    data_dir = tmp_path / 'api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    response = client.post('/schedule/api/blocks', json={
        'procedure_id': 't_alpha',
        'date': '2026-06-03',
        'start_time': '09:00',
        'end_time': '09:30',
        'test_item_ids': [],
    })

    assert response.status_code == 400
    assert response.get_json()['error'] == '연결할 시험 항목를 찾을 수 없습니다.'


def test_domain_json_schedule_block_item_api_flow(app, client, tmp_path):
    data_dir = tmp_path / 'items-api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    repository.replace_schedule(Schedule())
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    create_response = client.post('/schedule/api/blocks', json={
        'procedure_id': 't_alpha',
        'date': '2026-06-05',
        'start_time': '09:00',
        'end_time': '10:00',
            'location_name': 'STE1',
        'assignee_names': ['홍길동'],
    })
    assert create_response.status_code == 201
    block = create_response.get_json()
    assert block['test_item_ids'] == ['TC-001', 'TC-002']

    split_response = client.post(f'/schedule/api/blocks/{block["id"]}/split', json={
        'keep_test_item_ids': ['TC-001'],
    })
    assert split_response.status_code == 200
    new_block = split_response.get_json()['new_block']
    assert new_block['test_item_ids'] == ['TC-002']

    by_procedure_response = client.get('/schedule/api/blocks/by-procedure/t_alpha')
    assert by_procedure_response.status_code == 200
    procedure_blocks = by_procedure_response.get_json()['blocks']
    created_blocks = [item for item in procedure_blocks if item['date'] == '2026-06-05']
    assert len(created_blocks) == 2
    original = next(item for item in created_blocks if item['id'] == block['id'])
    assert original['test_item_ids'] == ['TC-001']
    assert original['end_time'] == '09:35'

    shift_response = client.post('/schedule/api/blocks/shift', json={
        'from_date': '2026-06-05',
        'direction': 1,
    })
    assert shift_response.status_code == 200
    assert shift_response.get_json()['shifted_count'] == 2

    shifted_blocks = client.get('/schedule/api/blocks/by-procedure/t_alpha').get_json()['blocks']
    assert {item['date'] for item in shifted_blocks if item['id'] in {block['id'], new_block['id']}} == {
        '2026-06-08',
    }

    return_response = client.post(
        f'/schedule/api/blocks/{new_block["id"]}/return-test_items',
        json={'keep_test_item_ids': []},
    )
    assert return_response.status_code == 200
    assert return_response.get_json() == {'success': True}

    loaded = _loaded_domain_data(repository)
    assert all(item['id'] != new_block['id'] for item in loaded['schedule']['blocks'])


def test_domain_json_schedule_day_api_and_export(app, client, tmp_path):
    data_dir = tmp_path / 'read-api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    day_response = client.get('/schedule/api/day?date=2026-05-13')
    assert day_response.status_code == 200
    day_data = day_response.get_json()
    assert day_data['current_date'] == '2026-05-13'
    assert day_data['blocks'][0]['procedure_title'] == '절차 A'
    assert day_data['blocks'][0]['test_item_ids'] == ['TC-001', 'TC-002']
    assert 'queue_procedures' in day_data

    csv_response = client.get(
        '/schedule/api/export?start_date=2026-05-13&end_date=2026-05-13&format=csv'
    )
    assert csv_response.status_code == 200
    assert 'text/csv' in csv_response.content_type
    body = csv_response.data.decode('utf-8-sig')
    assert '절차 A' in body
    assert '2026-05-13' in body


def test_domain_json_schedule_week_month_apis_and_views(app, client, tmp_path):
    data_dir = tmp_path / 'view-api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    week_response = client.get('/schedule/api/week?date=2026-05-13')
    assert week_response.status_code == 200
    week_data = week_response.get_json()
    assert week_data['week_start'] == '2026-05-11'
    assert week_data['blocks_by_date']['2026-05-13'][0]['procedure_title'] == '절차 A'

    month_response = client.get('/schedule/api/month?date=2026-05-13')
    assert month_response.status_code == 200
    month_data = month_response.get_json()
    may_13 = [
        day
        for week in month_data['weeks']
        for day in week
        if day and day['date'] == '2026-05-13'
    ][0]
    assert may_13['blocks'][0]['procedure_title'] == '절차 A'

    assert client.get('/schedule/?date=2026-05-13').status_code == 200
    assert client.get('/schedule/week?date=2026-05-13').status_code == 200
    assert client.get('/schedule/month?date=2026-05-13').status_code == 200


def test_domain_json_execution_list_detail_and_start(app, client, tmp_path):
    data_dir = tmp_path / 'execution-api-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    assert client.get('/execution/').status_code == 200

    list_response = client.get('/execution/api/list?date=2026-05-13')
    assert list_response.status_code == 200
    items = list_response.get_json()
    item = next(
        row
        for row in items
        if row['test_item_id'] == 'TC-001' and row['procedure_id'] == 't_alpha'
    )
    assert item['execution_status'] == 'completed'
    assert item['result_counts']['total_count'] == 5

    detail_response = client.get('/execution/api/item/TC-001?procedure_id=t_alpha')
    assert detail_response.status_code == 200
    assert detail_response.get_json()['execution']['status'] == 'completed'

    total_response = client.get('/execution/api/total-count/TC-001?procedure_id=t_alpha')
    assert total_response.status_code == 200
    assert total_response.get_json()['total_count'] == 5

    start_response = client.post('/execution/api/start', json={
        'test_item_id': 'TC-002',
        'procedure_id': 't_alpha',
    })
    assert start_response.status_code == 201
    assert 'test_round' not in start_response.get_json()


def test_domain_json_execution_storage_writes_runs_directly(app, client, tmp_path):
    data_dir = tmp_path / 'execution-storage-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    start_response = client.post('/execution/api/start', json={
        'test_item_id': 'TC-002',
        'procedure_id': 't_alpha',
    })
    assert start_response.status_code == 201
    execution = start_response.get_json()
    assert execution['total_count'] == 3

    pause_response = client.post('/execution/api/pause', json={
        'procedure_id': 't_alpha', 'test_item_id': 'TC-002',
    })
    assert pause_response.status_code == 200
    assert pause_response.get_json()['status'] == 'paused'

    complete_response = client.post('/execution/api/complete', json={
        'procedure_id': 't_alpha', 'test_item_id': 'TC-002',
        'fail_count': 1,
        'block_count': 0,
    })
    assert complete_response.status_code == 200
    assert complete_response.get_json()['status'] == 'completed'

    loaded = _loaded_domain_data(repository)
    run = loaded['executions']['runs'][0]
    assert run['status'] == 'completed'
    assert run['fail_count'] == 1

    detail_response = client.get('/execution/api/item/TC-002?procedure_id=t_alpha')
    assert detail_response.status_code == 200
    assert detail_response.get_json()['execution_status'] == 'completed'


def test_domain_json_admin_settings(app, client, tmp_path):
    data_dir = tmp_path / 'admin-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    settings_response = client.put('/admin/api/settings', json={'block_color_by': 'location'})
    assert settings_response.status_code == 200
    assert settings_response.get_json()['block_color_by'] == 'location'

    loaded = _loaded_domain_data(repository)
    assert loaded['settings']['block_color_by'] == 'location'


def test_domain_json_procedure_read_views_and_api(app, client, tmp_path):
    data_dir = tmp_path / 'procedures-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    list_response = client.get('/procedures/')
    assert list_response.status_code == 200

    detail_response = client.get('/procedures/t_alpha')
    assert detail_response.status_code == 200

    api_response = client.get('/procedures/api/t_alpha')
    assert api_response.status_code == 200
    procedure_data = api_response.get_json()['procedure']
    assert procedure_data['document_name'] == '절차 A'
    assert [item['id'] for item in procedure_data['test_items']] == ['TC-001', 'TC-002']


def test_domain_json_procedure_api_writes_catalog(app, client, tmp_path):
    data_dir = tmp_path / 'procedure-write-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(repository)
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    create_response = client.post('/procedures/api/create', json={
        'document_id': 77,
        'document_name': '신규 절차',
        'test_round': 1,
        'assignee_names': ['김검증'],
        'location_name': 'loc_1',
        'test_items': [
            {'id': 'TC-NEW-1', 'name': '신규 1', 'estimated_minutes': 11, 'total_count': 2},
            {'id': 'TC-NEW-2', 'name': '신규 2', 'estimated_minutes': 13, 'total_count': 3},
        ],
        'memo': 'domain procedure',
    })
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created['document_name'] == '신규 절차'
    assert created['estimated_minutes'] == 24

    update_response = client.put(f'/procedures/api/{created["id"]}/update', json={
        'document_id': 77,
        'document_name': '수정 절차',
        'assignee_names': ['김검증'],
        'location_name': 'loc_2',
        'test_items': [
            {'id': 'TC-NEW-1', 'name': '수정 1', 'estimated_minutes': 15, 'total_count': 4},
        ],
        'memo': 'updated',
    })
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated['document_name'] == '수정 절차'
    assert updated['test_items'][0]['estimated_minutes'] == 15

    loaded = _loaded_domain_data(repository)
    saved_procedure = next(item for item in loaded['test_procedures'] if item['id'] == created['id'])
    assert [item['id'] for item in saved_procedure['test_items']] == ['TC-NEW-1']

    delete_response = client.delete(f'/procedures/api/{created["id"]}/delete')
    assert delete_response.status_code == 200
    loaded = _loaded_domain_data(repository)
    assert all(item['id'] != created['id'] for item in loaded['test_procedures'])


def test_domain_json_sync_test_data_writes_procedures(app, tmp_path):
    class Provider:
        def get_test_data_all(self):
            return [
                {
                    'document_id': 88,
                    'document_name': '동기화 절차',
                    'test_round': 1,
                    'test_items': [
                        {'id': 'TC-SYNC-1', 'name': '동기화 1', 'estimated_minutes': 20},
                    ],
                },
            ]

    data_dir = tmp_path / 'sync-data'
    repository = JsonDomainRepository(data_dir)
    repository.initialize(reset=True)
    _replace_domain_data(
        repository,
        _empty_sections(),
    )
    app.config['DOMAIN_DATA_DIR'] = data_dir
    init_repository(app)

    with app.app_context():
        result = SyncService.sync_test_data(Provider())

    assert result['added'] == 1
    loaded = _loaded_domain_data(repository)
    assert loaded['test_procedures'][0]['document_name'] == '동기화 절차'
    assert loaded['test_procedures'][0]['test_items'][0]['id'] == 'TC-SYNC-1'

    class EmptyProvider(Provider):
        def get_test_data_all(self):
            return []

    with app.app_context():
        result = SyncService.sync_test_data(EmptyProvider())

    assert result['deleted'] == 1
    assert _loaded_domain_data(repository)['test_procedures'] == []
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time
