# 소프트웨어 시험 절차 스케줄링 시스템 재설계

> 기존 팀 업무 스케줄링 → 소프트웨어 시험 절차 스케줄링으로 전환

## 1. 핵심 변경 요약

| 기존 | 변경 |
|------|------|
| 카테고리 (기획/개발/QA) | **시험장소** (A, B, C...) |
| 업무 (task) | **시험 항목** (test item) |
| 담당자 1명 (`assignee_id`) | **시험 담당자 복수** (`assignee_ids`) |
| 단일 캘린더 | **소프트웨어 버전별 캘린더** |
| 여러 날에 걸쳐 배치 가능 | **한번 시작하면 당일 완료 필수** |
| 업무시간 08:00-23:30 | **표시 08:00-17:00, 실제 업무 08:30-16:30** |

## 2. 데이터 모델

### 2.1 소프트웨어 버전 (Version) - 신규

파일: `data/versions.json`

```json
[
  {
    "id": "v_a1b2c3d4",
    "name": "v1.2.0",
    "description": "2차 통합시험",
    "is_active": true,
    "created_at": "2026-03-30T09:00:00"
  }
]
```

- `id`: `v_` 접두사 + 8자리 hex
- `name`: 소프트웨어 버전명
- `description`: 버전 설명 (선택)
- `is_active`: 활성 버전 여부. 드롭다운에서 비활성 버전은 별도 표시
- 캘린더의 모든 데이터(시험 항목, 스케줄 블록)는 반드시 하나의 버전에 소속

### 2.2 시험장소 (Location) - 기존 Category 대체

파일: `data/locations.json` (기존 `categories.json` 대체)

```json
[
  {
    "id": "loc_a1b2c3d4",
    "name": "A",
    "color": "#28a745",
    "description": "1층 시험실"
  }
]
```

- `id`: `loc_` 접두사
- `name`: 장소 식별 (A, B, C 등)
- `color`: UI 표시 색상
- `description`: 장소 상세 설명 (선택)

### 2.3 시험 항목 (Task) - 필드 확장

파일: `data/tasks.json`

```json
[
  {
    "id": "t_a1b2c3d4",
    "procedure_id": "ABC-001",
    "version_id": "v_a1b2c3d4",
    "assignee_ids": ["u_a1b2c3d4", "u_e5f6g7h8"],
    "location_id": "loc_a1b2c3d4",
    "section_name": "3.2 통신 기능",
    "procedure_owner": "홍길동",
    "test_list": ["TC-001", "TC-002", "TC-003"],
    "estimated_hours": 4.0,
    "remaining_hours": 4.0,
    "deadline": "2026-04-15",
    "status": "waiting",
    "memo": "특이사항 기록",
    "created_at": "2026-03-30T09:00:00"
  }
]
```

변경사항:
- `title`, `description`, `priority` 제거
- `category_id` → `location_id`로 교체
- `assignee_id` (단일) → `assignee_ids` (배열)로 변경
- `procedure_id` 추가: `{영문3자}-{숫자}` 형식 (예: `ABC-001`, `SYS-042`)
- `version_id` 추가: 소속 버전 참조
- `section_name` 추가: 장절명 (절차서 식별자에서 파생)
- `procedure_owner` 추가: 절차서 담당자 (절차서 식별자에서 파생)
- `test_list` 추가: 시험목록 배열 (절차서 식별자에서 파생)
- `memo` 유지: 향후 DB 연동 시 마이그레이션 대상

### 2.4 스케줄 블록 (Schedule Block) - 필드 확장

파일: `data/schedule_blocks.json`

```json
[
  {
    "id": "sb_a1b2c3d4",
    "task_id": "t_a1b2c3d4",
    "assignee_ids": ["u_a1b2c3d4", "u_e5f6g7h8"],
    "location_id": "loc_a1b2c3d4",
    "version_id": "v_a1b2c3d4",
    "date": "2026-04-01",
    "start_time": "08:30",
    "end_time": "12:00",
    "is_draft": false,
    "is_locked": false,
    "origin": "manual",
    "block_status": "pending",
    "memo": ""
  }
]
```

변경사항:
- `assignee_id` → `assignee_ids` (배열)
- `location_id` 추가 (시험장소)
- `version_id` 추가 (버전 소속)

### 2.5 설정 (Settings)

파일: `data/settings.json`

```json
{
  "work_start": "08:00",
  "work_end": "17:00",
  "actual_work_start": "08:30",
  "actual_work_end": "16:30",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [
    {"start": "09:45", "end": "10:00"},
    {"start": "14:45", "end": "15:00"}
  ],
  "grid_interval_minutes": 15,
  "max_schedule_days": 14,
  "block_color_by": "assignee"
}
```

변경사항:
- `work_start`/`work_end`: 캘린더 표시 범위 (08:00-17:00)
- `actual_work_start`/`actual_work_end` 추가: 실제 업무 배치 가능 범위 (08:30-16:30)

### 2.6 사용자 (User) - 변경 없음

기존 구조 유지.

## 3. 스케줄러 로직 변경

### 3.1 당일 완료 제약

- 시험 항목은 한번 시작하면 당일 완료해야 하므로, 하루 가용시간 내에 들어가는 항목만 배치
- 하루 가용시간 = `actual_work_end - actual_work_start - 점심시간 - 휴식시간`
- `estimated_hours`가 하루 가용시간을 초과하면 자동 배치 불가 → `unplaced`에 경고와 함께 반환

### 3.2 시험장소 충돌 방지

- 같은 날, 같은 시험장소에서 시간이 겹치는 블록 배치 불가
- 자동 스케줄링 시 장소별 가용 슬롯도 함께 계산

### 3.3 담당자 충돌 방지

- `assignee_ids` 중 한 명이라도 같은 시간에 다른 블록에 배치되어 있으면 충돌
- 복수 담당자 전원의 가용 시간 교집합에서 슬롯 탐색

### 3.4 버전 필터

- `generate_draft_schedule(version_id)`: 특정 버전의 항목만 대상
- 다른 버전의 블록은 충돌 검사에서 제외

### 3.5 정렬 기준 변경

- 기존: 마감일 → 우선순위
- 변경: 마감일 → 절차서 식별자 순 (알파벳+숫자 정렬)

## 4. API 변경

### 4.1 버전 관리 API (신규)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin/versions` | 버전 목록 페이지 |
| GET | `/admin/versions/new` | 버전 생성 폼 |
| POST | `/admin/versions/new` | 버전 생성 |
| GET | `/admin/versions/<id>/edit` | 버전 편집 폼 |
| POST | `/admin/versions/<id>/edit` | 버전 수정 |
| POST | `/admin/versions/<id>/delete` | 버전 삭제 |
| GET | `/admin/api/versions` | 버전 목록 JSON |
| POST | `/admin/api/versions` | 버전 생성 JSON |
| PUT | `/admin/api/versions/<id>` | 버전 수정 JSON |
| DELETE | `/admin/api/versions/<id>` | 버전 삭제 JSON |

### 4.2 장소 관리 API (기존 카테고리 대체)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin/locations` | 장소 목록 |
| POST | `/admin/locations/new` | 장소 생성 |
| ... | (기존 카테고리와 동일 패턴) | |

### 4.3 절차서 조회 API (신규)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/procedure/<procedure_id>` | 절차서 정보 반환 |

- 현재: 목업 데이터 또는 수동 입력 허용
- 향후: 외부 시스템 API 호출로 교체
- 반환값: `{ "section_name": "...", "procedure_owner": "...", "test_list": [...] }`

### 4.4 기존 API 변경

- 모든 스케줄 API에 `version_id` 쿼리 파라미터 추가
- 블록 생성/수정 시 `assignee_ids` (배열), `location_id` 수용
- 업무 생성/수정 시 `procedure_id`, `assignee_ids`, `version_id` 등 새 필드 수용

## 5. UI 변경

### 5.1 버전 선택기

- 상단 네비게이션 바에 버전 드롭다운 추가
- 선택한 버전이 모든 뷰(일간/주간/월간, 업무 목록)에 적용
- URL 파라미터로 버전 유지: `?version=v_xxx`
- 비활성 버전은 드롭다운에서 구분 표시 (회색 등)

### 5.2 시험 항목 폼 (기존 업무 폼 대체)

- **절차서 식별자**: `AAA-000` 형식 입력 필드 + 패턴 검증
  - 입력 후 blur/엔터 시 자동으로 장절명, 절차서 담당자, 시험목록 조회 표시
  - 외부 연동 실패 시 수동 입력 가능
- **시험 담당자**: 멀티셀렉트 드롭다운 → 선택 시 칩(chip) 표시, X로 제거
- **시험장소**: 단일 셀렉트 드롭다운
- **소프트웨어 버전**: 현재 선택된 버전 자동 설정 (변경 가능)
- **예상 소요시간**: 숫자 입력
- **마감일**: 날짜 피커
- **메모**: 텍스트에어리어

### 5.3 필터링 UI

업무 목록과 캘린더 뷰에 필터 바 추가:

- **시험 담당자**: 멀티셀렉트 → 칩 표시 (여러 명 필터 가능)
- **시험장소**: 멀티셀렉트 → 칩 표시
- **절차서 식별자**: 텍스트 검색 (부분 매칭)
- **상태**: 멀티셀렉트 (waiting, completed 등)
- 칩 클릭 시 해당 필터 제거
- "초기화" 버튼으로 전체 필터 리셋

### 5.4 캘린더 블록 표시

- 블록에 절차서 식별자 + 장절명 표시
- 블록 색상: 담당자별 또는 장소별 (설정에 따라)
- 복수 담당자는 이니셜 또는 이름 나열

### 5.5 관리 메뉴 변경

- 카테고리 관리 → **시험장소 관리**
- **버전 관리** 메뉴 추가
- 사용자 관리는 그대로 유지

## 6. 파일 구조 변경

### 신규 파일
```
data/versions.json
data/locations.json
app/repositories/version_repo.py
app/repositories/location_repo.py
app/templates/admin/versions.html
app/templates/admin/version_form.html
app/templates/admin/locations.html        (categories.html 기반)
app/templates/admin/location_form.html    (category_form.html 기반)
```

### 삭제 파일
```
data/categories.json
app/repositories/category_repo.py
app/templates/admin/categories.html
app/templates/admin/category_form.html
```

### 수정 파일
```
data/tasks.json                          (필드 구조 변경)
data/schedule_blocks.json                (필드 구조 변경)
data/settings.json                       (시간 변경)
app/repositories/task_repo.py            (새 필드 지원)
app/repositories/schedule_repo.py        (새 필드 지원)
app/repositories/settings_repo.py        (actual_work_start/end 지원)
app/services/scheduler.py               (당일완료, 장소충돌, 버전필터)
app/blueprints/schedule/routes.py        (버전 필터, 새 필드)
app/blueprints/tasks/routes.py           (새 폼 필드, 절차서 조회)
app/blueprints/admin/routes.py           (장소, 버전 관리)
app/templates/base.html                  (버전 선택기, 메뉴 변경)
app/templates/schedule/day.html          (블록 표시, 필터 UI)
app/templates/schedule/week.html         (동일)
app/templates/schedule/month.html        (동일)
app/templates/schedule/_task_queue.html   (필터 칩 UI)
app/templates/tasks/*.html               (새 폼 필드)
app/static/css/style.css                 (칩, 필터 스타일)
app/static/js/drag_drop.js              (새 필드 반영)
tests/test_app.py                        (전면 수정)
```

## 7. 외부 연동 전략

- 절차서 정보 조회용 서비스 레이어: `app/services/procedure_service.py`
- 현재: `data/procedures.json` 목업 파일에서 조회 또는 수동 입력 허용
- 향후: 환경변수 `PROCEDURE_API_URL`로 외부 API 연동 전환
- 메모 데이터: JSON 파일에 저장하되, 추후 DB 마이그레이션 시 `json_store.py`를 DB 어댑터로 교체하는 구조 유지

## 8. 마이그레이션

- 기존 `categories.json` 데이터 → `locations.json`으로 변환 스크립트 불필요 (신규 데이터로 시작)
- 기존 `tasks.json`, `schedule_blocks.json` → 구조 변경이 크므로 빈 파일로 초기화
- 기존 사용자 데이터는 유지
