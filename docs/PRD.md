# PRD: 소프트웨어 시험 절차 스케줄링 서비스

## Context

소프트웨어 시험 절차를 장소/버전별로 관리하고, 캘린더 형태로 스케줄링하는 웹 서비스. 드래그앤드롭으로 수동 배치하며, JSON 파일 기반 데이터 저장소를 사용한다.

## 기술 스택

- **Backend:** Flask + Jinja2
- **Frontend:** Bootstrap 5 + 바닐라 JavaScript (10개 모듈)
- **데이터 저장:** JSON 파일 (DB 없음, portalocker 파일 잠금)
- **포트:** 5001
- **테스트:** pytest (149개)

---

## 1. 데이터 계층

```
장절명 (section_name)           ← 최상단 그룹
  └─ 시험식별자 (test_list[].id)    ← N개, 각각 예상시간 보유
       └─ 작성자 (test_list[].owners) ← N개, 해당 식별자를 작성한 인원
```

- **시험 담당자** (assignee_ids) = 테스트를 수행하는 사람 (등록된 팀원 목록에서 선택)
- **작성자** (owners) = 시험식별자를 작성/개발한 사람 (자유 텍스트)
- 두 그룹은 겹치지 않음 (작성한 사람과 테스트하는 사람은 별개)

---

## 2. 핵심 기능

### 2.1 시험 항목(Task) 관리

속성:
- `section_name` — 장절명 (최상단 표시명)
- `procedure_id` — 내부 식별자 (UI에서 미노출, 자동 생성)
- `version_id` — 소프트웨어 버전
- `assignee_ids` — 시험 담당자 (복수)
- `location_id` — 시험 장소
- `test_list` — 시험 식별자 배열:
  ```json
  [{"id": "TC-001", "estimated_hours": 1.0, "owners": ["김민수", "이지은"]}]
  ```
- `estimated_hours` — 식별자 시간 합 (불변, 리사이즈로 바뀌지 않음)
- `remaining_hours` — 잔여 시간
- `status` — waiting / in_progress / completed
- `memo`
- `is_simple` — 단순 블록 여부 (시험 준비, 회의 등)

필터링: 버전, 상태, 담당자, 장소, 날짜

### 2.2 스케줄 블록 관리

속성:
- `task_id` — 연결된 시험항목 (단순 블록은 null)
- `assignee_ids`, `location_id`, `version_id`
- `date`, `start_time`, `end_time`
- `is_locked` — 잠금 (이동/리사이즈 불가)
- `block_status` — pending / in_progress / completed / cancelled
- `identifier_ids` — 이 블록에 할당된 식별자 (null = 전체)
- `title` — 단순 블록용 제목
- `is_simple` — 단순 블록 여부
- `memo`

### 2.3 캘린더 뷰

| 뷰 | URL | 특징 |
|----|-----|------|
| 일간 | `/schedule/` | 장소별 컬럼, 리사이즈/이동 |
| 주간 | `/schedule/week` | 7일 그리드, 초기 진입 페이지 |
| 월간 | `/schedule/month` | 달력, 장소 필터 없음 |

공통: 버전 필터, 장소 필터 (복수 선택), 주말 토글

### 2.4 드래그앤드롭

- **큐→시간표**: 항목을 드래그하여 시간대에 배치
- **블록 이동**: 같은날/다른날/큐복귀
- **블록 리사이즈**: 상/하 핸들, 시간 축소 시 경고 모달
- **월간→월간**: 날짜 변경

### 2.5 분할 배치

- 하나의 장절에 여러 식별자가 있을 때, 일부만 선택하여 배치 가능
- 큐에서 드래그 시 식별자 선택 피커 표시
- 이미 배치된 식별자는 비활성 표시 + "배치됨" 뱃지
- 배치된 식별자를 다시 선택하면 기존 블록에서 자동 제거
- 우클릭 → "분리"로 배치된 블록을 식별자 단위로 분리 가능
- 분할 블록에는 `2/5` 형태의 분할 뱃지 표시

### 2.6 시간 관리 규칙

- `estimated_hours` = 식별자 시간 합 (불변)
- **리사이즈** = 실제 시간 변경 (remaining 변경 안 됨, 큐 미노출)
- **큐 복귀** (블록 삭제) = remaining 재계산
- 분할 안 된 블록이 있으면 해당 task는 큐에서 제거
- 분할된 블록만 있으면 미배치 식별자의 시간만 큐에 표시

### 2.7 추가 기능

- **간단 블록**: 시험 외 일정 (시험 준비, 회의 등), 제목+시간만으로 큐에 추가
- **일정 밀기/당기기**: 특정 날짜 이후 블록을 +1/-1일 이동, 주말 건너뛰기
- **내보내기**: CSV/Excel, 날짜 범위 지정

---

## 3. 설정

```json
{
  "work_start": "08:00",
  "work_end": "17:00",
  "actual_work_start": "08:30",
  "actual_work_end": "16:30",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [{"start": "10:00", "end": "10:00"}],
  "grid_interval_minutes": 10,
  "max_schedule_days": 14,
  "block_color_by": "location"
}
```

---

## 4. URL 구조

### 페이지
- `/` → 리다이렉트 → `/schedule/week`
- `/schedule/`, `/schedule/week`, `/schedule/month`
- `/tasks/`, `/tasks/new`, `/tasks/<id>`, `/tasks/<id>/edit`
- `/admin/settings`, `/admin/users`, `/admin/locations`, `/admin/versions`

### API
- `POST/PUT/DELETE /schedule/api/blocks`, `/schedule/api/blocks/<id>/lock|status|memo`
- `POST /schedule/api/simple-blocks` — 간단 블록 생성
- `GET /schedule/api/blocks/by-task/<task_id>`
- `POST /schedule/api/blocks/shift` — 일정 이동
- `POST /schedule/api/blocks/<id>/split` — 블록 분리
- `GET /schedule/api/export`
- `GET /schedule/api/day|week|month` — 뷰 데이터
- `GET/POST/PUT/DELETE /tasks/api/*` — 시험항목 CRUD
- `GET /tasks/api/check-identifier` — 식별자 중복 검사
- `GET/PUT /admin/api/settings`
- `GET/POST/PUT/DELETE /admin/api/users|locations|versions`

---

## 5. 프로젝트 구조

```
scheduling/
├── run.py                          # 서버 실행
├── config.py
├── migrate_data.py                 # 데이터 마이그레이션
├── data/                           # JSON 데이터
│   ├── tasks.json, schedule_blocks.json, settings.json
│   ├── users.json, locations.json, versions.json, procedures.json
├── schedule/
│   ├── __init__.py                 # create_app()
│   ├── store.py                    # JSON I/O + 파일 잠금
│   ├── models/
│   │   ├── base.py                 # BaseRepository 공통 클래스
│   │   ├── task.py, schedule_block.py, user.py, location.py, version.py, settings.py
│   ├── routes/
│   │   ├── calendar_views.py       # 일간/주간/월간 뷰
│   │   ├── calendar_api.py         # 블록 CRUD API
│   │   ├── calendar_helpers.py     # 공통 헬퍼 함수
│   │   ├── tasks.py, admin.py
│   ├── helpers/
│   │   ├── enrichment.py           # 블록/큐 데이터 가공
│   │   ├── overlap.py, time_utils.py
│   ├── services/
│   │   ├── export.py, procedure.py
│   ├── static/
│   │   ├── css/style.css           # CSS 변수 기반
│   │   ├── js/                     # 10개 모듈
│   │       ├── utils.js, modals.js, drag-core.js
│   │       ├── block-move.js, block-resize.js, queue-drag.js
│   │       ├── context-menu.js, block-detail.js
│   │       ├── schedule-features.js, schedule-app.js
│   ├── templates/
│       ├── base.html
│       ├── schedule/ (day, week, month, _task_queue, _version_selector, _location_filter)
│       ├── tasks/ (list, form, detail)
│       ├── admin/ (settings, users, locations, versions + forms)
├── tests/                          # 149개 테스트
│   ├── conftest.py
│   ├── test_models.py, test_helpers.py, test_services.py
│   ├── test_routes_calendar.py, test_routes_tasks.py, test_routes_admin.py
│   ├── test_calendar_api.py, test_enrichment.py, test_integration.py
```
