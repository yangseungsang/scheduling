import pytest
from playwright.sync_api import Page, expect

BASE_URL = 'http://localhost:5001'


def test_home_redirects(page: Page):
    page.goto(BASE_URL + '/')
    expect(page).to_have_url(f'{BASE_URL}/schedule/')


def test_day_view_loads(page: Page):
    page.goto(BASE_URL + '/schedule/')
    expect(page.get_by_text('미배치 업무', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='초안 생성').first).to_be_visible()


def test_week_view_loads(page: Page):
    page.goto(BASE_URL + '/schedule/week')
    expect(page.locator('table')).to_be_visible()


def test_month_view_loads(page: Page):
    page.goto(BASE_URL + '/schedule/month')
    expect(page.locator('table')).to_be_visible()


def test_admin_settings_loads(page: Page):
    page.goto(BASE_URL + '/admin/settings')
    expect(page.locator('input[name="work_start"]')).to_be_visible()
    expect(page.locator('input[name="lunch_start"]')).to_be_visible()


def test_admin_settings_save(page: Page):
    page.goto(BASE_URL + '/admin/settings')
    page.fill('input[name="work_start"]', '09:00')
    page.fill('input[name="work_end"]', '18:00')
    page.fill('input[name="lunch_start"]', '12:00')
    page.fill('input[name="lunch_end"]', '13:00')
    page.click('button[type="submit"]')
    expect(page.locator('.alert-success')).to_be_visible()


def test_create_category(page: Page):
    page.goto(BASE_URL + '/admin/categories/new')
    page.fill('input[name="name"]', '테스트카테고리')
    page.click('input[type="color"]')
    page.click('button[type="submit"]')
    expect(page.locator('text=테스트카테고리').first).to_be_visible()


def test_create_task(page: Page):
    page.goto(BASE_URL + '/tasks/new')
    page.fill('input[name="title"]', '테스트 업무')
    page.fill('input[name="estimated_minutes"]', '90')
    page.click('button[type="submit"]')
    expect(page.locator('text=테스트 업무')).to_be_visible()


def test_task_list_filter(page: Page):
    page.goto(BASE_URL + '/tasks')
    page.select_option('select[name="status"]', 'pending')
    expect(page.locator('table')).to_be_visible()


def test_task_status_update(page: Page):
    page.goto(BASE_URL + '/tasks')
    first_select = page.locator('select[name="status"]').first
    if first_select.count() > 0:
        first_select.select_option('in_progress')
        page.wait_for_load_state('networkidle')
        expect(page.locator('table')).to_be_visible()


def test_add_task_note(page: Page):
    page.goto(BASE_URL + '/tasks')
    first_link = page.locator('a.fw-semibold').first
    if first_link.count() > 0:
        first_link.click()
        page.fill('textarea[name="content"]', '테스트 메모입니다.')
        page.click('button:has-text("추가")')
        expect(page.locator('text=테스트 메모입니다.')).to_be_visible()


def test_schedule_draft_modal(page: Page):
    page.goto(BASE_URL + '/schedule/')
    page.click('button:has-text("초안 생성")')
    expect(page.locator('#draftModal')).to_be_visible()
    # 모달 닫기
    page.click('#draftModal .btn-close')
