from datetime import datetime

from app.json_store import read_json, write_json, generate_id

FILENAME = 'tasks.json'


def get_all():
    return read_json(FILENAME)


def get_by_id(task_id):
    for t in read_json(FILENAME):
        if t['id'] == task_id:
            return t
    return None


def create(title, description, assignee_id, category_id, priority,
           estimated_hours, deadline):
    tasks = read_json(FILENAME)
    task = {
        'id': generate_id('t_'),
        'title': title,
        'description': description,
        'assignee_id': assignee_id,
        'category_id': category_id,
        'priority': priority,
        'estimated_hours': estimated_hours,
        'remaining_hours': estimated_hours,
        'deadline': deadline,
        'status': 'waiting',
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    tasks.append(task)
    write_json(FILENAME, tasks)
    return task


def update(task_id, title, description, assignee_id, category_id, priority,
           estimated_hours, remaining_hours, deadline, status):
    tasks = read_json(FILENAME)
    for t in tasks:
        if t['id'] == task_id:
            t['title'] = title
            t['description'] = description
            t['assignee_id'] = assignee_id
            t['category_id'] = category_id
            t['priority'] = priority
            t['estimated_hours'] = estimated_hours
            t['remaining_hours'] = remaining_hours
            t['deadline'] = deadline
            t['status'] = status
            write_json(FILENAME, tasks)
            return t
    return None


def delete(task_id):
    tasks = read_json(FILENAME)
    tasks = [t for t in tasks if t['id'] != task_id]
    write_json(FILENAME, tasks)
