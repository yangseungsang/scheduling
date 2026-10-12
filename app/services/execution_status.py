"""Shared status aggregation for scheduled test items."""


def aggregate_status(statuses):
    """Reflect active, paused, completed and untouched work consistently."""
    statuses = list(statuses)
    if statuses and all(status == 'completed' for status in statuses):
        return 'completed'
    if 'in_progress' in statuses:
        return 'in_progress'
    if 'paused' in statuses:
        return 'paused'
    if 'completed' in statuses:
        return 'in_progress'
    return 'pending'


def block_execution_status(block, runs):
    """Test blocks follow execution records; simple events use manual state."""
    if block.kind == 'simple':
        return block.manual_status or 'pending'
    status = aggregate_status(runs[(block.procedure_id, iid)].status
                            if (block.procedure_id, iid) in runs else 'pending'
                            for iid in block.test_item_ids)
    # A placement can be unavailable before execution begins. Actual work takes precedence.
    if status == 'pending' and block.manual_status == 'cancelled':
        return 'cancelled'
    return status
