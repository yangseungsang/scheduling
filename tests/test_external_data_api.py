import json
import os


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def _seed_external_api_data(app):
    data_dir = app.config['DATA_DIR']
    execution_dir = app.config['EXECUTION_DATA_DIR']
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
                    'total_count': 5,
                },
                {
                    'id': 'TC-002',
                    'name': '종료',
                    'estimated_minutes': 20,
                    'total_count': 3,
                },
            ],
        },
        {
            'id': 't_beta',
            'doc_id': 11,
            'version_id': 'V1',
            'exam_no': 1,
            'doc_name': '절차 B',
            'assignee_names': ['김개발'],
            'location_id': 'loc_2',
            'identifiers': [
                {
                    'id': 'TC-003',
                    'name': '확인',
                    'estimated_minutes': 15,
                    'total_count': 2,
                },
            ],
        },
    ]
    blocks = [
        {
            'id': 'sb_alpha',
            'task_id': 't_alpha',
            'date': '2026-05-13',
            'start_time': '09:00',
            'end_time': '10:00',
            'location_id': 'loc_1',
            'assignee_names': ['홍길동'],
            'identifier_ids': ['TC-001'],
        },
        {
            'id': 'sb_beta',
            'task_id': 't_beta',
            'date': '2026-05-15',
            'start_time': '11:00',
            'end_time': '12:00',
            'location_id': 'loc_2',
            'assignee_names': ['김개발'],
        },
    ]
    executions = [
        {
            'id': 'ex_1',
            'identifier_id': 'TC-001',
            'task_id': 't_alpha',
            'status': 'completed',
            'segments': [
                {'start': '2026-05-13T09:00:00', 'end': '2026-05-13T09:10:00'},
            ],
            'total_count': 5,
            'fail_count': 1,
            'block_count': 1,
            'pass_count': 3,
            'performer': '홍길동',
            'comment': '완료',
        },
    ]

    _write_json(os.path.join(data_dir, 'tasks.json'), tasks)
    _write_json(os.path.join(data_dir, 'schedule_blocks.json'), blocks)
    _write_json(os.path.join(data_dir, 'locations.json'), [
        {'id': 'loc_1', 'name': '1시험실'},
        {'id': 'loc_2', 'name': '2시험실'},
    ])
    _write_json(os.path.join(data_dir, 'users.json'), [
        {'id': 'u_1', 'name': '홍길동'},
    ])
    _write_json(os.path.join(data_dir, 'versions.json'), [
        {'id': 'V1', 'name': '버전 1'},
    ])
    _write_json(os.path.join(data_dir, 'dyn_ready_meta.json'), {
        'updated_at': '2026-05-13T08:00:00',
        'data_hash': 'hash-1',
    })
    _write_json(os.path.join(execution_dir, 'executions.json'), executions)


def test_external_snapshot_and_metadata(app, client):
    _seed_external_api_data(app)

    snapshot_response = client.get('/api/external/v1/snapshot')
    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.get_json()
    assert snapshot['schema_version'] == '1.0'
    assert len(snapshot['catalog']['documents']) == 2
    assert len(snapshot['schedule']['block_items']) == 2
    assert snapshot['catalog']['sync']['data_hash'] == 'hash-1'

    metadata_response = client.get('/api/external/v1/metadata')
    assert metadata_response.status_code == 200
    metadata = metadata_response.get_json()
    assert metadata['counts']['documents'] == 2
    assert metadata['counts']['execution_runs'] == 1
    assert metadata['sync']['updated_at'] == '2026-05-13T08:00:00'


def test_external_schedule_and_execution_read_models(app, client):
    _seed_external_api_data(app)

    schedule_response = client.get(
        '/api/external/v1/schedule?start_date=2026-05-13&end_date=2026-05-13'
    )
    assert schedule_response.status_code == 200
    schedule = schedule_response.get_json()['schedule']
    assert len(schedule['blocks']) == 1
    assert len(schedule['block_items']) == 1
    assert len(schedule['rows']) == 1
    assert schedule['rows'][0]['doc_name'] == '절차 A'
    assert schedule['rows'][0]['external_test_ids'] == ['TC-001']

    execution_response = client.get('/api/external/v1/executions?date=2026-05-13&location=loc_1')
    assert execution_response.status_code == 200
    executions = execution_response.get_json()['executions']['items']
    assert len(executions) == 1
    assert executions[0]['external_test_id'] == 'TC-001'
    assert executions[0]['execution_status'] == 'completed'
    assert executions[0]['elapsed_seconds'] == 600
