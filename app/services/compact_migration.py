"""Build compact JSON snapshots from the current legacy JSON data."""

from copy import deepcopy

from app.domain.ids import stable_id

SCHEMA_VERSION = '1.0'


def _total_count(identifier):
    for key in ('total_count', 'pf_num', 'test_count', 'case_count', 'count'):
        value = identifier.get(key)
        if value in (None, ''):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _identifier_id(identifier):
    if isinstance(identifier, dict):
        return identifier.get('id', '')
    return str(identifier)


def _identifier_name(identifier):
    return identifier.get('name', '') if isinstance(identifier, dict) else ''


def _identifier_minutes(identifier):
    if not isinstance(identifier, dict):
        return 0
    try:
        return int(identifier.get('estimated_minutes') or 0)
    except (TypeError, ValueError):
        return 0


def _identifier_owners(identifier):
    if not isinstance(identifier, dict):
        return []
    owners = identifier.get('owners') or []
    return list(owners) if isinstance(owners, list) else [str(owners)]


def build_compact_snapshot(
    *,
    tasks=None,
    schedule_blocks=None,
    executions=None,
    users=None,
    locations=None,
    versions=None,
    settings=None,
    provider_cache=None,
):
    """Convert legacy in-memory data into compact JSON document payloads."""
    tasks = tasks or []
    schedule_blocks = schedule_blocks or []
    executions = executions or []
    users = users or []
    locations = locations or []
    versions = versions or []
    settings = settings or {}
    provider_cache = provider_cache or {}

    catalog, attempt_lookup, task_identifier_lookup = _build_catalog(tasks, provider_cache)
    schedule = _build_schedule(schedule_blocks, task_identifier_lookup)
    execution_payload = _build_executions(executions, attempt_lookup)

    return {
        'catalog': catalog,
        'schedule': schedule,
        'executions': execution_payload,
        'resources': {
            'schema_version': SCHEMA_VERSION,
            'users': deepcopy(users),
            'locations': deepcopy(locations),
            'versions': deepcopy(versions),
        },
        'settings': _build_settings(settings, provider_cache),
    }


def _build_catalog(tasks, provider_cache):
    documents_by_key = {}
    test_items_by_key = {}
    exam_attempts = []
    attempt_lookup = {}
    task_identifier_lookup = {}
    warnings = []

    for legacy_task in tasks:
        legacy_task_id = legacy_task.get('id', '')
        external_doc_id = _external_doc_id(legacy_task.get('doc_id'))
        doc_key = (legacy_task.get('version_id', ''), external_doc_id)
        document_id = stable_id('doc_', *doc_key)
        document = documents_by_key.get(doc_key)
        if document is None:
            document = {
                'id': document_id,
                'legacy_task_ids': [],
                'external_doc_id': external_doc_id,
                'version_id': legacy_task.get('version_id', ''),
                'doc_name': legacy_task.get('doc_name', ''),
                'is_active': legacy_task.get('status') != 'cancelled',
            }
            documents_by_key[doc_key] = document
        if legacy_task_id and legacy_task_id not in document['legacy_task_ids']:
            document['legacy_task_ids'].append(legacy_task_id)

        identifiers = legacy_task.get('identifiers', [])
        if not identifiers:
            warnings.append(f'{legacy_task_id}: identifiers가 비어 있음')

        for identifier in identifiers:
            external_test_id = _identifier_id(identifier)
            if not external_test_id:
                warnings.append(f'{legacy_task_id}: id 없는 identifier 건너뜀')
                continue

            test_key = (document_id, external_test_id)
            test_item = test_items_by_key.get(test_key)
            if test_item is None:
                test_item_id = stable_id('ti_', document_id, external_test_id)
                test_item = {
                    'id': test_item_id,
                    'document_id': document_id,
                    'external_test_id': external_test_id,
                    'name': _identifier_name(identifier),
                    'estimated_minutes': _identifier_minutes(identifier),
                    'total_count': _total_count(identifier) if isinstance(identifier, dict) else 0,
                    'owner_names': _identifier_owners(identifier),
                    'is_active': True,
                }
                test_items_by_key[test_key] = test_item
            else:
                # Keep the richest available fields when duplicated across exam attempts.
                if not test_item.get('name'):
                    test_item['name'] = _identifier_name(identifier)
                if not test_item.get('owner_names'):
                    test_item['owner_names'] = _identifier_owners(identifier)
                if not test_item.get('total_count'):
                    test_item['total_count'] = _total_count(identifier) if isinstance(identifier, dict) else 0
                if not test_item.get('estimated_minutes'):
                    test_item['estimated_minutes'] = _identifier_minutes(identifier)

            exam_no = legacy_task.get('exam_no')
            attempt_id = stable_id('ea_', test_item['id'], exam_no)
            attempt = {
                'id': attempt_id,
                'test_item_id': test_item['id'],
                'exam_no': exam_no,
                'legacy_task_id': legacy_task_id,
                'legacy_identifier_id': external_test_id,
                'default_location_id': legacy_task.get('location_id', ''),
                'default_assignee_names': list(legacy_task.get('assignee_names', [])),
                'memo': legacy_task.get('memo', ''),
                'state': 'cancelled' if legacy_task.get('status') == 'cancelled' else 'active',
            }
            exam_attempts.append(attempt)
            attempt_lookup[(legacy_task_id, external_test_id)] = attempt_id
            task_identifier_lookup.setdefault(legacy_task_id, []).append((external_test_id, attempt_id))

    return (
        {
            'schema_version': SCHEMA_VERSION,
            'documents': list(documents_by_key.values()),
            'test_items': list(test_items_by_key.values()),
            'exam_attempts': exam_attempts,
            'sync': {
                'provider': provider_cache.get('provider', ''),
                'updated_at': provider_cache.get('updated_at', ''),
                'data_hash': provider_cache.get('data_hash', ''),
            },
            'migration': {'warnings': warnings},
        },
        attempt_lookup,
        task_identifier_lookup,
    )


def _build_schedule(blocks, task_identifier_lookup):
    compact_blocks = []
    block_items = []
    warnings = []

    for legacy_block in blocks:
        legacy_block_id = legacy_block.get('id', '')
        block_id = stable_id('blk_', legacy_block_id)
        is_simple = bool(legacy_block.get('is_simple')) or not legacy_block.get('task_id')
        compact_blocks.append({
            'id': block_id,
            'legacy_block_id': legacy_block_id,
            'date': legacy_block.get('date', ''),
            'start_time': legacy_block.get('start_time', ''),
            'end_time': legacy_block.get('end_time', ''),
            'location_id': legacy_block.get('location_id', ''),
            'assignee_names': list(legacy_block.get('assignee_names', [])),
            'kind': 'simple' if is_simple else 'test',
            'title': legacy_block.get('title', ''),
            'memo': legacy_block.get('memo', ''),
            'is_locked': bool(legacy_block.get('is_locked', False)),
            'manual_status': 'cancelled' if legacy_block.get('block_status') == 'cancelled' else '',
            'overflow_minutes': int(legacy_block.get('overflow_minutes') or 0),
        })

        if is_simple:
            continue

        task_id = legacy_block.get('task_id', '')
        known_attempts = task_identifier_lookup.get(task_id, [])
        if not known_attempts:
            warnings.append(f'{legacy_block_id}: 연결 task를 찾지 못함: {task_id}')
            continue

        identifier_ids = legacy_block.get('identifier_ids')
        if identifier_ids is None:
            selected_attempts = known_attempts
        else:
            selected = set(identifier_ids)
            selected_attempts = [(iid, aid) for iid, aid in known_attempts if iid in selected]
            missing = selected - {iid for iid, _ in selected_attempts}
            for identifier_id in sorted(missing):
                warnings.append(f'{legacy_block_id}: attempt를 찾지 못함: {task_id}/{identifier_id}')

        for sort_order, (_identifier_id, attempt_id) in enumerate(selected_attempts):
            block_items.append({
                'id': stable_id('bi_', block_id, attempt_id),
                'block_id': block_id,
                'exam_attempt_id': attempt_id,
                'sort_order': sort_order,
            })

    return {
        'schema_version': SCHEMA_VERSION,
        'blocks': compact_blocks,
        'block_items': block_items,
        'migration': {'warnings': warnings},
    }


def _external_doc_id(value):
    if value is None:
        return ''
    return str(value)


def _build_executions(executions, attempt_lookup):
    runs = []
    warnings = []

    for legacy_execution in executions:
        legacy_execution_id = legacy_execution.get('id', '')
        task_id = legacy_execution.get('task_id', '')
        identifier_id = legacy_execution.get('identifier_id', '')
        attempt_id = attempt_lookup.get((task_id, identifier_id))
        if not attempt_id:
            warnings.append(f'{legacy_execution_id}: attempt를 찾지 못함: {task_id}/{identifier_id}')
            continue

        runs.append({
            'id': stable_id('run_', legacy_execution_id),
            'legacy_execution_id': legacy_execution_id,
            'exam_attempt_id': attempt_id,
            'status': legacy_execution.get('status', 'pending'),
            'segments': deepcopy(legacy_execution.get('segments', [])),
            'total_count': int(legacy_execution.get('total_count') or 0),
            'fail_count': int(legacy_execution.get('fail_count') or 0),
            'block_count': int(legacy_execution.get('block_count') or 0),
            'pass_count': int(legacy_execution.get('pass_count') or 0),
            'comment': legacy_execution.get('comment', ''),
            'performer_name': legacy_execution.get('performer', ''),
            'created_at': legacy_execution.get('created_at'),
            'completed_at': legacy_execution.get('completed_at'),
            'elapsed_seconds_snapshot': int(legacy_execution.get('elapsed_seconds') or 0),
            'elapsed_mins_snapshot': int(legacy_execution.get('elapsed_mins') or 0),
        })

    return {
        'schema_version': SCHEMA_VERSION,
        'runs': runs,
        'migration': {'warnings': warnings},
    }


def _build_settings(settings, provider_cache):
    compact_settings = deepcopy(settings)
    compact_settings['schema_version'] = SCHEMA_VERSION
    compact_settings.setdefault('provider_cache', {})
    if provider_cache:
        provider_name = provider_cache.get('provider') or 'default'
        compact_settings['provider_cache'][provider_name] = {
            'updated_at': provider_cache.get('updated_at', ''),
            'data_hash': provider_cache.get('data_hash', ''),
        }
    return compact_settings
