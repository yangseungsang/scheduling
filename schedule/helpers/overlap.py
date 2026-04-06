from schedule.helpers.time_utils import time_to_minutes
from schedule.models import schedule_block


def check_overlap(assignee_ids, location_id, date_str, start_time, end_time,
                   exclude_block_id=None, exclude_task_id=None):
    """Check location overlap only. Same assignees at the same time are allowed."""
    if not location_id:
        return None
    s1 = time_to_minutes(start_time)
    e1 = time_to_minutes(end_time)
    for b in schedule_block.get_by_date(date_str):
        if exclude_block_id and b['id'] == exclude_block_id:
            continue
        if exclude_task_id and b.get('task_id') == exclude_task_id:
            continue
        if b.get('location_id') != location_id:
            continue
        s2 = time_to_minutes(b['start_time'])
        e2 = time_to_minutes(b['end_time'])
        if s1 < e2 and s2 < e1:
            return b
    return None


def compute_overlap_layout(blocks):
    if not blocks:
        return blocks
    sorted_blocks = sorted(
        blocks,
        key=lambda b: (time_to_minutes(b['start_time']),
                       -time_to_minutes(b['end_time'])),
    )
    columns = []
    block_col = {}
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        placed = False
        for ci, (col_end, indices) in enumerate(columns):
            if col_end <= s:
                columns[ci] = (time_to_minutes(b['end_time']), indices + [i])
                block_col[i] = ci
                placed = True
                break
        if not placed:
            block_col[i] = len(columns)
            columns.append((time_to_minutes(b['end_time']), [i]))
    for i, b in enumerate(sorted_blocks):
        s = time_to_minutes(b['start_time'])
        e = time_to_minutes(b['end_time'])
        max_col = block_col[i] + 1
        for j, b2 in enumerate(sorted_blocks):
            if i == j:
                continue
            s2 = time_to_minutes(b2['start_time'])
            e2 = time_to_minutes(b2['end_time'])
            if s < e2 and s2 < e:
                max_col = max(max_col, block_col[j] + 1)
        b['col_index'] = block_col[i]
        b['col_total'] = max_col
    return sorted_blocks
