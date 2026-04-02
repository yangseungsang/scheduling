# PRD: 소프트웨어 시험 절차 스케줄링 서비스

## Context

소프트웨어 시험 절차를 장소·버전별로 관리하고, 캘린더 형태로 스케줄링하는 웹 서비스. 자동 스케줄링 기능을 제공하며, JSON 파일 기반 데이터 저장소를 사용한다. 인증 없이 팀원 이름 선택만으로 사용할 수 있다.

## 기술 스택

- **Backend:** Flask + Jinja2
- **Frontend:** Bootstrap 5 + 바닐라 JavaScript
- **데이터 저장:** JSON 파일 (DB 없음)
- **포트:** 5001

---

## 1. 핵심 기능

### 1.1 시험 항목(Task) 관리

- 시험 항목 CRUD (생성/조회/수정/삭제)
- 시험 항목 속성:
  - 절차서 식별자 (`procedure_id`)
  - 소프트웨어 버전 (`version_id`)
  - 시험 담당자 (`assignee_ids`) — 복수 배정 가능
  - 시험 장소 (`location_id`)
  - 섹션명 (`section_name`)
  - 절차서 담당자 (`procedure_owner`)
  - 시험 목록 (`test_list`) — 개별 테스트 항목 배열
  - 예상 소요시간 (`estimated_hours`)
  - 남은 시간 (`remaining_hours`) — 스케줄 블록 배치 시 차감
  - 상태 (`status`: waiting / in_progress / completed / cancelled)
  - 메모 (`memo`)
- 시험 항목 목록 필터링 (상태, 버전, 장소, 담당자, 절차서 검색)
- **배치 상태 표시:** 시험 항목 목록에서 각 항목이 시간표에 배치됨/큐 상태인지 표시
- 절차서 외부 조회 API 연동 (현재 mock)

### 1.2 캘린더 뷰

- **일간 뷰:** 장소별 컬럼 레이아웃으로 시간대별 블록 표시
- **주간 뷰:** 7일 × 시간대 그리드 (장소 필터 바)
- **월간 뷰:** 날짜별 업무 요약 표시
- 뷰 간 자유로운 전환
- 날짜 네비게이션 (이전/다음, 오늘로 이동)
- **소프트웨어 버전 선택:** 버전별로 캘린더 필터링
- **색상 표시 옵션:** 블록 색상을 담당자 색상 또는 장소 색상 중 선택 가능

### 1.3 드래그앤드랍

- 캘린더 위에서 업무 블록을 드래그하여 시간/날짜/장소 변경
- mousedown/mousemove/mouseup 기반 커스텀 드래그 시스템
- 드래그 시 시각적 피드백 (ghost 요소, 하이라이트)
- **Ghost 크기:** 쉬는시간을 제외한 실제 작업시간 기준 높이로 표시
- **Grid Snap:** 15분 단위로 스냅
- **장소 이동:** 일간 뷰에서 장소 간 드래그 이동 지원

### 1.4 자동 스케줄링

- 미배치 업무들을 절차서ID 순으로 자동 배치
- `remaining_hours`가 남아있는 업무만 대상으로 블록 생성
- **장소 자동 배정:** 장소가 미지정인 태스크는 등록된 장소 중 가장 빈 장소에 자동 배정. 장소가 지정된 태스크는 해당 장소 우선 사용
- 스케줄링 규칙:
  - 업무시간 내에만 배치 (actual_work_start~actual_work_end: 08:30~16:30)
  - 점심시간/쉬는시간 자동 skip
  - **장소 충돌 방지:** 같은 장소+시간에 2개 시험 불가
  - **당일 완료 제약:** 시험은 한번 시작하면 같은 날 끝나야 함
  - **잠금된 블록(`is_locked`)은 이동하지 않음**
- **초안/확정 워크플로우:**
  - 자동 스케줄링 결과를 "초안"으로 먼저 표시 (점선 테두리)
  - 사용자가 확인/수정 후 "확정" 처리
  - 초안 폐기 가능
- **오버플로우 처리:** 배치 못한 업무는 "미배치 업무" 리스트로 표시

### 1.5 블록 상태 → 시험 항목 연동

- 블록 상태(`block_status`)를 변경하면 해당 태스크의 상태(`status`)가 자동 연동
  - 모든 블록 `completed` → 태스크 `completed`
  - 일부 블록 `in_progress` 또는 일부만 `completed` → 태스크 `in_progress`

### 1.6 블록 상세 팝업

- 스케줄 블록 또는 큐 아이템 더블클릭 시 상세 정보 팝업
- 소요시간 및 메모 인라인 편집
- 소요시간 변경 시 task의 estimated_hours와 블록의 end_time 동시 업데이트

### 1.7 사용자/설정 관리

- 로그인 없이 사용
- 관리자 페이지:
  - 팀원 관리 (이름, 역할, 색상)
  - 시험 장소 관리 (이름, 색상, 설명)
  - 소프트웨어 버전 관리 (이름, 설명, 활성 상태)
  - 업무 시간 설정 (표시 범위, 실제 배치 범위, 점심/쉬는시간)
  - 블록 색상 기준 설정 (담당자 / 장소)

### 1.8 내보내기

- 날짜 범위 + 포맷(CSV/Excel) 선택하여 스케줄 데이터 다운로드

---

## 2. 데이터 모델 (JSON 파일 기반)

### ID 생성 전략

- `uuid4` 사용 (예: `"t_a1b2c3d4"`)
- `store.py`에 `generate_id(prefix)` 유틸리티 함수 정의
- 접두사로 엔티티 구분: `u_` (user), `loc_` (location), `v_` (version), `t_` (task), `sb_` (schedule_block)

### `data/users.json`

```json
[{ "id": "u_a1b2c3d4", "name": "홍길동", "role": "시험원", "color": "#4A90D9" }]
```

### `data/locations.json`

```json
[{ "id": "loc_00000001", "name": "시험실 A", "color": "#E74C3C", "description": "1층 좌측" }]
```

### `data/versions.json`

```json
[{ "id": "v_00000001", "name": "v2.1.0", "description": "2차 통합 시험", "is_active": true, "created_at": "2026-03-28T09:00:00" }]
```

### `data/tasks.json`

```json
[
  {
    "id": "t_a1b2c3d4",
    "procedure_id": "STP-001",
    "version_id": "v_00000001",
    "assignee_ids": ["u_a1b2c3d4"],
    "location_id": "loc_00000001",
    "section_name": "통신 시험",
    "procedure_owner": "김철수",
    "test_list": ["TC-001", "TC-002"],
    "estimated_hours": 2.0,
    "remaining_hours": 1.5,
    "status": "waiting",
    "memo": "",
    "created_at": "2026-03-28T09:50:00"
  }
]
```

### `data/schedule_blocks.json`

```json
[
  {
    "id": "sb_a1b2c3d4",
    "task_id": "t_a1b2c3d4",
    "assignee_ids": ["u_a1b2c3d4"],
    "location_id": "loc_00000001",
    "version_id": "v_00000001",
    "date": "2026-03-09",
    "start_time": "09:00",
    "end_time": "12:00",
    "is_draft": false,
    "is_locked": false,
    "origin": "manual",
    "block_status": "pending",
    "memo": ""
  }
]
```

### `data/settings.json`

```json
{
  "work_start": "08:00",
  "work_end": "17:00",
  "actual_work_start": "08:30",
  "actual_work_end": "16:30",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "breaks": [
    { "start": "09:45", "end": "10:00" },
    { "start": "14:45", "end": "15:00" }
  ],
  "grid_interval_minutes": 15,
  "max_schedule_days": 14,
  "block_color_by": "assignee"
}
```

### `data/procedures.json`

```json
[
  { "procedure_id": "STP-001", "section_name": "통신 시험", "procedure_owner": "김철수", "test_list": ["TC-001", "TC-002"] }
]
```

---

## 3. URL 구조

| URL | 설명 |
| --- | --- |
| `/` | → `/schedule/` 리다이렉트 |
| `/schedule/` | 일간 뷰 (장소별 컬럼) |
| `/schedule/week` | 주간 뷰 |
| `/schedule/month` | 월간 뷰 |
| `/tasks/` | 시험 항목 목록 |
| `/tasks/new` | 시험 항목 생성 |
| `/tasks/<id>` | 시험 항목 상세 |
| `/tasks/<id>/edit` | 시험 항목 수정 |
| `/admin/settings` | 설정 관리 |
| `/admin/users` | 팀원 관리 |
| `/admin/locations` | 장소 관리 |
| `/admin/versions` | 버전 관리 |

### API 엔드포인트

| Method | URL | 설명 |
| ------ | --- | --- |
| POST | `/schedule/api/blocks` | 스케줄 블록 생성 |
| PUT | `/schedule/api/blocks/<id>` | 블록 수정 (드래그/리사이즈/소요시간 변경) |
| DELETE | `/schedule/api/blocks/<id>` | 블록 삭제 |
| PUT | `/schedule/api/blocks/<id>/lock` | 블록 잠금/해제 토글 |
| PUT | `/schedule/api/blocks/<id>/status` | 블록 상태 변경 |
| PUT | `/schedule/api/blocks/<id>/memo` | 블록 메모 수정 |
| POST | `/schedule/api/draft/generate` | 자동 스케줄링 초안 생성 |
| POST | `/schedule/api/draft/approve` | 초안 확정 |
| POST | `/schedule/api/draft/discard` | 초안 폐기 |
| GET | `/schedule/api/export` | CSV/Excel 내보내기 |
| GET | `/tasks/api/list` | 시험 항목 목록 |
| GET | `/tasks/api/<id>` | 시험 항목 상세 |
| POST | `/tasks/api/create` | 시험 항목 생성 |
| PUT | `/tasks/api/<id>/update` | 시험 항목 수정 |
| DELETE | `/tasks/api/<id>/delete` | 시험 항목 삭제 |
| GET | `/tasks/api/procedure/<id>` | 절차서 정보 조회 |

---

## 4. 프로젝트 구조

```
scheduling/
├── run.py
├── requirements.txt
├── data/                          # JSON 데이터 파일
│   ├── users.json
│   ├── locations.json
│   ├── versions.json
│   ├── tasks.json
│   ├── schedule_blocks.json
│   ├── settings.json
│   └── procedures.json
├── schedule/
│   ├── __init__.py                # create_app (인라인 config 포함)
│   ├── store.py                   # JSON 읽기/쓰기 + generate_id() + 파일 잠금 + .bak 백업
│   ├── models/                    # 데이터 접근 계층
│   │   ├── user.py
│   │   ├── location.py
│   │   ├── version.py
│   │   ├── task.py
│   │   ├── schedule_block.py
│   │   └── settings.py
│   ├── routes/                    # Blueprint 라우팅
│   │   ├── calendar.py            # 캘린더 뷰 + 블록 CRUD API
│   │   ├── tasks.py               # 시험 항목 CRUD
│   │   └── admin.py               # 설정/사용자/장소/버전 관리
│   ├── helpers/                   # 헬퍼 유틸리티
│   │   ├── enrichment.py          # 블록 enrichment, 큐 계산, 날짜 유틸
│   │   ├── overlap.py             # 겹침 감지 + 컬럼 레이아웃 계산
│   │   └── time_utils.py          # 시간 변환, 휴식시간 조정, 근무시간 계산
│   ├── services/                  # 비즈니스 로직
│   │   ├── scheduler.py           # 자동 스케줄링 엔진
│   │   ├── procedure.py           # 절차서 조회 서비스
│   │   └── export.py              # CSV/Excel 내보내기
│   ├── templates/
│   │   ├── base.html
│   │   ├── schedule/              # day.html, week.html, month.html, _task_queue.html, ...
│   │   ├── tasks/                 # list.html, detail.html, form.html
│   │   └── admin/                 # settings.html, users.html, locations.html, versions.html, ...
│   └── static/
│       ├── css/style.css
│       └── js/drag_drop.js        # 바닐라 JS 이벤트 엔진 (드래그, 리사이즈, 상세 팝업 등)
└── tests/
    ├── conftest.py
    ├── test_helpers.py
    ├── test_models.py
    ├── test_routes_admin.py
    ├── test_routes_calendar.py
    ├── test_routes_tasks.py
    └── test_services.py
```

---

## 5. UI 일관성 요구사항

모든 사용자 액션(생성/수정/삭제/드래그 등) 후 UI가 반드시 최신 상태를 반영해야 한다.

- API 호출 후 성공 응답을 받으면 전체 페이지를 새로고침하여 서버 상태와 동기화
- 실패 시 Toast 알림으로 에러 피드백 표시
- 서버가 항상 진실의 원천(source of truth)

---

## 6. 비기능 요구사항

- **파일 잠금:** `portalocker` 라이브러리로 JSON 동시 접근 시 데이터 무결성 보장
- **백업:** 매 쓰기 작업 전 `.bak` 파일 자동 생성 (store.py에서 처리)
- Bootstrap 5 반응형 레이아웃
- CDN으로 Bootstrap/Bootstrap Icons 로드

---

## 7. 구현 순서

1. **Phase 1 - 기반:** 프로젝트 구조 + store.py (ID 생성, 파일 잠금, 백업) + 설정/유저/장소/버전 관리
2. **Phase 2 - 시험 항목:** Task CRUD (remaining_hours 포함) + 절차서 조회 연동
3. **Phase 3 - 캘린더:** 일간(장소별 컬럼)/주간/월간 뷰 + 버전 선택 + 장소 필터
4. **Phase 4 - 스케줄링:** 자동 스케줄링 엔진 (당일 완료, 장소 충돌 방지) + 초안/확정 워크플로우
5. **Phase 5 - 인터랙션:** 드래그앤드랍 (15분 그리드 스냅) + 리사이즈 + 컨텍스트 메뉴 + 상세 팝업
6. **Phase 6 - 마감:** 테스트 + 내보내기 + 버그 수정 + UI 다듬기
