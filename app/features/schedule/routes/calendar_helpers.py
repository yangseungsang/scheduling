from app.features.schedule.helpers.time_utils import (
    adjust_end_for_breaks,
    minutes_to_time,
    time_to_minutes,
    work_minutes_in_range,
)
from app.features.schedule.models import schedule_block, settings, task

DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']

VALID_BLOCK_STATUSES = {'pending', 'in_progress', 'completed', 'cancelled'}


def remove_identifiers_from_other_blocks(task_id, exclude_block_id,
                                         moved_ids, sttngs):
    """Remove moved_ids from other blocks of the same task.

    If a block loses all its identifiers, delete it.
    If it loses some, shrink its duration proportionally.
    """
    t = task.get_by_id(task_id)
    if not t:
        return
    test_list = t.get('test_list', [])
    # Build minutes lookup: identifier_id → estimated_minutes
    id_minutes = {}
    for item in test_list:
        if isinstance(item, dict):
            id_minutes[item['id']] = item.get('estimated_minutes', 0)

    moved_set = set(moved_ids)
    all_blocks = schedule_block.get_all()
    for b in all_blocks:
        if b.get('task_id') != task_id:
            continue
        if b['id'] == exclude_block_id:
            continue
        block_ids = b.get('identifier_ids')
        if not block_ids:
            # Block covers all identifiers — remove the moved ones
            all_task_ids = [item['id'] if isinstance(item, dict) else item
                           for item in test_list]
            block_ids = all_task_ids

        overlap = [i for i in block_ids if i in moved_set]
        if not overlap:
            continue

        remaining_ids = [i for i in block_ids if i not in moved_set]
        if not remaining_ids:
            # Block lost all identifiers → delete it
            schedule_block.delete(b['id'])
        else:
            # Shrink block duration to match remaining identifiers
            remaining_min = max(sum(id_minutes.get(i, 0) for i in remaining_ids), 15)
            new_end_min = time_to_minutes(b['start_time']) + remaining_min
            new_end = minutes_to_time(new_end_min)
            adjusted_end = adjust_end_for_breaks(b['start_time'], new_end, sttngs)
            schedule_block.update(b['id'],
                                 identifier_ids=remaining_ids,
                                 end_time=adjusted_end)


def sync_task_remaining_minutes(task_id):
    if not task_id:
        return
    t = task.get_by_id(task_id)
    if not t:
        return

    # estimated_minutes = sum of test_list identifier minutes, or task value for simple blocks
    test_list = t.get('test_list', [])
    tl_sum = sum(
        item.get('estimated_minutes', 0) for item in test_list
        if isinstance(item, dict)
    )
    est = tl_sum if tl_sum > 0 else t.get('estimated_minutes', 0)

    sttngs = settings.get()
    total_min = sum(
        work_minutes_in_range(b['start_time'], b['end_time'], sttngs)
        + b.get('overflow_minutes', 0)
        for b in schedule_block.get_all()
        if b.get('task_id') == task_id
    )
    new_remaining = max(est - total_min, 0)

    patches = {}
    if t.get('estimated_minutes', 0) != est:
        patches['estimated_minutes'] = est
    if t.get('remaining_minutes', 0) != new_remaining:
        patches['remaining_minutes'] = new_remaining
    if patches:
        task.patch(task_id, **patches)


def sync_task_status(task_id):
    """Update task status based on its schedule blocks' statuses."""
    from app.features.schedule.models import task as task_model
    t = task_model.get_by_id(task_id)
    if not t:
        return
    blocks = [b for b in schedule_block.get_all()
              if b.get('task_id') == task_id]
    if not blocks:
        return
    statuses = [b.get('block_status', 'pending') for b in blocks]
    if all(s == 'completed' for s in statuses):
        new_status = 'completed'
    elif any(s == 'in_progress' for s in statuses):
        new_status = 'in_progress'
    elif any(s == 'completed' for s in statuses):
        new_status = 'in_progress'
    else:
        new_status = t['status']
    if new_status != t['status']:
        task_model.patch(task_id, status=new_status)
