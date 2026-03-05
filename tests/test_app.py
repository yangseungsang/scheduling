import pytest
from playwright.sync_api import Page, expect

BASE_URL = 'http://localhost:5001'


# ============================================================
# 기존 테스트
# ============================================================

def test_home_redirects(page: Page):
    page.goto(BASE_URL + '/')
    expect(page).to_have_url(f'{BASE_URL}/schedule/')


def test_day_view_loads(page: Page):
    page.goto(BASE_URL + '/schedule/')
    expect(page.get_by_text('미배치 업무', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='초안 생성').first).to_be_visible()


def test_week_view_loads(page: Page):
    page.goto(BASE_URL + '/schedule/week')
    expect(page.locator('#week-timeline-scroll')).to_be_visible()


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
    # 필터 폼의 status select (카드 내 첫 번째 form)
    page.locator('.card-body form select[name="status"]').select_option('pending')
    page.wait_for_load_state('networkidle')
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
        expect(page.locator('text=테스트 메모입니다.').first).to_be_visible()


def test_schedule_draft_modal(page: Page):
    page.goto(BASE_URL + '/schedule/')
    page.click('button:has-text("초안 생성")')
    expect(page.locator('#draftModal')).to_be_visible()
    # 모달 닫기
    page.click('#draftModal .btn-close')


# ============================================================
# 엣지 케이스 테스트 - 날짜 경계
# ============================================================

def test_month_year_boundary_dec(page: Page):
    """12월→1월 연도 경계 월간 뷰 이동."""
    page.goto(BASE_URL + '/schedule/month?year=2025&month=12')
    expect(page.locator('text=2025년 12월')).to_be_visible()
    # 다음달(2026년 1월)로 이동
    next_link = page.locator('a.btn-outline-secondary.btn-sm >> nth=1')
    next_link.click()
    expect(page.locator('text=2026년 1월')).to_be_visible()


def test_month_year_boundary_jan(page: Page):
    """1월→12월 연도 경계 역방향 이동."""
    page.goto(BASE_URL + '/schedule/month?year=2026&month=1')
    expect(page.locator('text=2026년 1월')).to_be_visible()
    # 이전달(2025년 12월)로 이동
    prev_link = page.locator('a.btn-outline-secondary.btn-sm >> nth=0')
    prev_link.click()
    expect(page.locator('text=2025년 12월')).to_be_visible()


def test_day_view_date_navigation(page: Page):
    """일간 뷰에서 이전/다음 날짜 이동."""
    page.goto(BASE_URL + '/schedule/?date=2025-12-31')
    expect(page.locator('text=2025-12-31')).to_be_visible()
    # 다음날(2026-01-01)로 이동
    page.locator('a.btn-outline-secondary.btn-sm >> nth=1').click()
    expect(page.locator('text=2026-01-01')).to_be_visible()


def test_month_view_invalid_params(page: Page):
    """유효하지 않은 month 파라미터가 기본값으로 처리되는지."""
    page.goto(BASE_URL + '/schedule/month?year=2025&month=13')
    # month=13은 유효하지 않으므로 현재 달로 fallback
    expect(page.locator('table')).to_be_visible()


# ============================================================
# 엣지 케이스 테스트 - API 경계 조건
# ============================================================

def test_api_create_block_missing_fields(page: Page):
    """필수 필드 누락 시 블록 생성 실패."""
    resp = page.request.post(BASE_URL + '/schedule/api/blocks',
                             data={'task_id': 1})
    assert resp.status == 400
    body = resp.json()
    assert body['success'] is False


def test_api_create_block_invalid_time(page: Page):
    """end_time이 start_time보다 이른 경우 거부."""
    resp = page.request.post(BASE_URL + '/schedule/api/blocks',
                             data={
                                 'task_id': 1,
                                 'assigned_date': '2025-06-01',
                                 'start_time': '14:00',
                                 'end_time': '10:00',
                             })
    assert resp.status == 400
    body = resp.json()
    assert 'start_time must be before end_time' in body['error']


def test_api_create_block_equal_times(page: Page):
    """start_time == end_time인 경우 거부."""
    resp = page.request.post(BASE_URL + '/schedule/api/blocks',
                             data={
                                 'task_id': 1,
                                 'assigned_date': '2025-06-01',
                                 'start_time': '10:00',
                                 'end_time': '10:00',
                             })
    assert resp.status == 400


def test_api_create_block_invalid_date_format(page: Page):
    """잘못된 날짜 형식 거부."""
    resp = page.request.post(BASE_URL + '/schedule/api/blocks',
                             data={
                                 'task_id': 1,
                                 'assigned_date': '2025/06/01',
                                 'start_time': '09:00',
                                 'end_time': '10:00',
                             })
    assert resp.status == 400


def test_api_create_block_invalid_time_format(page: Page):
    """잘못된 시간 형식 거부."""
    resp = page.request.post(BASE_URL + '/schedule/api/blocks',
                             data={
                                 'task_id': 1,
                                 'assigned_date': '2025-06-01',
                                 'start_time': '9:00',
                                 'end_time': '10:00',
                             })
    assert resp.status == 400


def test_api_update_block_invalid_time(page: Page):
    """블록 수정 시 end_time < start_time 거부."""
    resp = page.request.put(BASE_URL + '/schedule/api/blocks/9999',
                            data={
                                'assigned_date': '2025-06-01',
                                'start_time': '15:00',
                                'end_time': '10:00',
                            })
    assert resp.status == 400


def test_api_delete_nonexistent_block(page: Page):
    """존재하지 않는 블록 삭제 시 에러 없이 처리."""
    resp = page.request.delete(BASE_URL + '/schedule/api/blocks/99999')
    assert resp.status == 200


def test_api_draft_generate_no_tasks(page: Page):
    """미배치 업무 없는 카테고리로 초안 생성 시 빈 결과."""
    resp = page.request.post(BASE_URL + '/schedule/api/draft/generate',
                             data={'category_id': 99999})
    assert resp.status == 200
    body = resp.json()
    assert body['success'] is True
    assert body['count'] == 0


def test_api_draft_discard(page: Page):
    """초안 폐기 API 정상 동작."""
    resp = page.request.post(
        BASE_URL + '/schedule/api/draft/discard',
        headers={'Content-Type': 'application/json'},
        data='{}')
    assert resp.status == 200
    assert resp.json()['success'] is True


def test_api_draft_approve_empty(page: Page):
    """초안 블록 없는 상태에서 승인 시 에러 없이 처리."""
    # 먼저 초안 폐기
    page.request.post(
        BASE_URL + '/schedule/api/draft/discard',
        headers={'Content-Type': 'application/json'},
        data='{}')
    resp = page.request.post(
        BASE_URL + '/schedule/api/draft/approve',
        headers={'Content-Type': 'application/json'},
        data='{}')
    assert resp.status == 200
    assert resp.json()['success'] is True


# ============================================================
# 엣지 케이스 테스트 - 업무 관리
# ============================================================

def test_create_task_title_only(page: Page):
    """최소 필수 정보(제목만)로 업무 생성."""
    page.goto(BASE_URL + '/tasks/new')
    page.fill('input[name="title"]', 'QA최소정보업무')
    page.click('button[type="submit"]')
    expect(page.locator('text=QA최소정보업무')).to_be_visible()


def test_create_task_empty_title(page: Page):
    """빈 제목으로 업무 생성 시 HTML required 검증."""
    page.goto(BASE_URL + '/tasks/new')
    # title 필드를 비워둔 채 submit 시도 - HTML5 required 속성이 차단
    title_input = page.locator('input[name="title"]')
    expect(title_input).to_have_attribute('required', '')


def test_task_detail_404(page: Page):
    """존재하지 않는 업무 상세 페이지 접근 시 404."""
    resp = page.goto(BASE_URL + '/tasks/999999')
    assert resp.status == 404


def test_task_edit_404(page: Page):
    """존재하지 않는 업무 수정 페이지 접근 시 404."""
    resp = page.goto(BASE_URL + '/tasks/999999/edit')
    assert resp.status == 404


def test_task_status_invalid(page: Page):
    """유효하지 않은 상태값으로 API 상태 변경 거부."""
    resp = page.request.post(BASE_URL + '/tasks/1/status',
                             data={'status': 'invalid_status'})
    assert resp.status == 400


# ============================================================
# 엣지 케이스 테스트 - 사용자 관리 CRUD
# ============================================================

def test_admin_user_create(page: Page):
    """사용자 추가."""
    import time
    unique_email = f'qatest_{int(time.time())}@test.com'
    page.goto(BASE_URL + '/admin/users/new')
    page.fill('input[name="name"]', 'QA테스트유저신규')
    page.fill('input[name="email"]', unique_email)
    page.click('button[type="submit"]')
    expect(page.locator('.alert-success')).to_be_visible()


def test_admin_user_edit(page: Page):
    """사용자 수정 (마지막 사용자 수정)."""
    page.goto(BASE_URL + '/admin/users')
    edit_links = page.locator('a:has-text("수정")')
    if edit_links.count() > 0:
        edit_links.last.click()
        page.fill('input[name="name"]', 'QA수정완료')
        page.click('button[type="submit"]')
        expect(page.locator('.alert-success')).to_be_visible()


# ============================================================
# 엣지 케이스 테스트 - 빈 상태
# ============================================================

def test_week_view_with_date_param(page: Page):
    """특정 날짜의 주간 뷰 로드."""
    page.goto(BASE_URL + '/schedule/week?date=2025-01-06')
    expect(page.locator('#week-timeline-scroll')).to_be_visible()


def test_day_view_invalid_date(page: Page):
    """유효하지 않은 날짜 파라미터가 기본값으로 처리."""
    page.goto(BASE_URL + '/schedule/?date=invalid-date')
    # 유효하지 않은 날짜는 오늘로 fallback
    expect(page.get_by_text('미배치 업무', exact=True)).to_be_visible()


def test_task_list_pagination(page: Page):
    """업무 목록 페이지네이션 범위 초과 시 에러 없이 표시."""
    resp = page.goto(BASE_URL + '/tasks?page=9999')
    assert resp.status == 200
    # 페이지 범위를 벗어나도 에러 없이 로드됨
    expect(page.locator('h1')).to_be_visible()


def test_admin_categories_list(page: Page):
    """카테고리 목록 페이지 로드."""
    page.goto(BASE_URL + '/admin/categories')
    expect(page).to_have_url(BASE_URL + '/admin/categories')


def test_admin_redirect(page: Page):
    """관리자 루트 접근 시 설정 페이지로 리다이렉트."""
    page.goto(BASE_URL + '/admin/')
    expect(page).to_have_url(BASE_URL + '/admin/settings')
