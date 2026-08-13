"""Tests for the remaining admin settings routes."""


def test_admin_settings_page(client):
    assert client.get('/admin/settings').status_code == 200


def test_update_settings_form(client):
    response = client.post('/admin/settings', data={
        'work_start': '09:07',
        'work_end': '17:00',
        'actual_work_start': '08:30',
        'actual_work_end': '16:30',
        'lunch_start': '12:03',
        'lunch_end': '13:00',
        'grid_interval_minutes': '15',
        'max_schedule_days': '7',
        'block_color_by': 'location',
    }, follow_redirects=True)

    assert response.status_code == 200
    settings = client.get('/admin/api/settings').get_json()
    assert settings['work_start'] == '09:00'
    assert settings['lunch_start'] == '12:00'
    assert settings['max_schedule_days'] == 7


def test_update_settings_api(client):
    response = client.put('/admin/api/settings', json={'work_start': '08:30'})
    assert response.status_code == 200
    assert response.get_json()['work_start'] == '08:30'
