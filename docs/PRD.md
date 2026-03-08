# PRD: 팀 업무 스케줄링 서비스

## Context
팀원들의 업무를 공유 캘린더 형태로 관리하고, 우선순위 기반 자동 스케줄링 기능을 제공하는 웹 서비스를 새로 구축한다. MVP 수준으로 빠르게 시작하기 위해 JSON 파일 기반 데이터 저장소를 사용하고, 인증 없이 팀원 이름 선택만으로 사용할 수 있도록 한다.

## 기술 스택
- **Backend:** Flask + Jinja2
- **Frontend:** Bootstrap 5 + SortableJS (드래그앤드랍)
- **데이터 저장:** JSON 파일 (DB 없음)
- **포트:** 5001

---

## 1. 핵심 기능

### 1.1 업무(Task) 관리
- 업무 CRUD (생성/조회/수정/삭제)
- 업무 속성:
  - 제목, 설명
  - 담당자 (팀원)
  - 우선순위 (높음/중간/낮음)
  - 예상 소요시간 (시간 단위)
  - 남은 시간 (`remaining_hours`) — 스케줄 블록 배치 시 자동 차감
  - 마감일 (deadline)
  - 카테고리
  - 상태 (대기/진행중/완료)
- 업무 목록 필터링/정렬
- **Task:ScheduleBlock = 1:N 관계** — 예상 소요시간이 하루 가용 시간을 초과하면 여러 날짜의 블록으로 분할 배치

### 1.2 캘린더 뷰
- **일간 뷰:** 시간대별 타임라인에 업무 블록 표시
- **주간 뷰:** 7일 × 시간대 그리드
- **월간 뷰:** 날짜별 업무 요약 표시
- 뷰 간 자유로운 전환
- 날짜 네비게이션 (이전/다음, 오늘로 이동)
- **색상 표시 옵션:** 블록 색상을 담당자 색상 또는 카테고리 색상 중 선택 가능 (설정에서 변경)

### 1.3 드래그앤드랍
- 캘린더 위에서 업무 블록을 드래그하여 시간/날짜 변경
- SortableJS 라이브러리 활용
- 드래그 시 시각적 피드백
- **Grid Snap:** 30분 단위로 스냅 — 드롭 위치 좌표를 계산하여 `start_time`을 30분 단위로 보정
- **HTML 데이터 속성:** 캘린더 셀에 `data-date`, `data-time` 속성을 부여하여 뷰 형태(일간/주간)에 관계없이 일관된 드롭 처리

### 1.4 자동 스케줄링
- 미배치 업무들을 우선순위/마감일 기반으로 자동 배치
- `remaining_hours`가 남아있는 업무만 대상으로 블록 생성
- 스케줄링 규칙:
  - 마감일이 임박한 업무 우선
  - 같은 마감일이면 우선순위 높은 것 우선
  - 업무 시간(예: 09:00~18:00) 내에만 배치
  - 점심시간(12:00~13:00) 자동 skip
  - 담당자별로 시간 겹침 없이 배치
  - **잠금된 블록(`is_locked`)은 이동하지 않음** — 수동 배치 블록 보호
- **초안/확정 워크플로우:**
  - 자동 스케줄링 결과를 "초안"으로 먼저 표시
  - 사용자가 확인/수정 후 "확정" 처리
  - 초안 폐기 가능
- **오버플로우 처리:**
  - 가용 시간 부족으로 배치되지 못한 업무는 별도 "미배치 업무" 리스트로 표시
  - 에러 없이 가능한 만큼만 배치하고 나머지를 알림

### 1.5 사용자/설정 관리
- 로그인 없이 사용 (팀원 이름 선택 방식)
- 관리자 페이지:
  - 팀원 관리 (이름, 역할 등록)
  - 카테고리 관리
  - 업무 시간 설정 (시작/종료, 점심시간)
  - 블록 색상 기준 설정 (담당자 / 카테고리)

---

## 2. 데이터 모델 (JSON 파일 기반)

### ID 생성 전략
- `uuid4` 사용 (예: `"t_a1b2c3d4"`)
- `json_store.py`에 `generate_id(prefix)` 유틸리티 함수 정의
- 접두사로 엔티티 구분: `u_` (user), `c_` (category), `t_` (task), `sb_` (schedule_block)

### `data/users.json`
```json
[
  { "id": "u_a1b2c3d4", "name": "홍길동", "role": "개발자", "color": "#4A90D9" }
]
```

### `data/categories.json`
```json
[
  { "id": "c_a1b2c3d4", "name": "개발", "color": "#28a745" }
]
```

### `data/tasks.json`
```json
[
  {
    "id": "t_a1b2c3d4",
    "title": "API 설계",
    "description": "REST API 엔드포인트 설계",
    "assignee_id": "u_a1b2c3d4",
    "category_id": "c_a1b2c3d4",
    "priority": "high",
    "estimated_hours": 8,
    "remaining_hours": 5,
    "deadline": "2026-03-10",
    "status": "in_progress",
    "created_at": "2026-03-08T10:00:00"
  }
]
```

### `data/schedule_blocks.json`
```json
[
  {
    "id": "sb_a1b2c3d4",
    "task_id": "t_a1b2c3d4",
    "assignee_id": "u_a1b2c3d4",
    "date": "2026-03-09",
    "start_time": "09:00",
    "end_time": "12:00",
    "is_draft": true,
    "is_locked": false,
    "origin": "auto"
  }
]
```
- `is_locked`: `true`이면 자동 스케줄링 시 이동/삭제 불가
- `origin`: `"auto"` (자동 스케줄링 생성) 또는 `"manual"` (수동 배치)

### `data/settings.json`
```json
{
  "work_start": "09:00",
  "work_end": "18:00",
  "lunch_start": "12:00",
  "lunch_end": "13:00",
  "max_schedule_days": 14,
  "block_color_by": "assignee"
}
```
- `block_color_by`: `"assignee"` (담당자 색상) 또는 `"category"` (카테고리 색상)

---

## 3. URL 구조

| URL | 설명 |
|-----|------|
| `/` | → `/schedule/` 리다이렉트 |
| `/schedule/` | 일간 뷰 |
| `/schedule/week` | 주간 뷰 |
| `/schedule/month` | 월간 뷰 |
| `/tasks/` | 업무 목록 |
| `/tasks/new` | 업무 생성 |
| `/tasks/<id>` | 업무 상세 |
| `/tasks/<id>/edit` | 업무 수정 |
| `/admin/settings` | 설정 관리 |
| `/admin/users` | 팀원 관리 |
| `/admin/categories` | 카테고리 관리 |

### API 엔드포인트
| Method | URL | 설명 |
|--------|-----|------|
| POST | `/schedule/api/blocks` | 스케줄 블록 생성 |
| PUT | `/schedule/api/blocks/<id>` | 블록 수정 (드래그앤드랍) |
| DELETE | `/schedule/api/blocks/<id>` | 블록 삭제 |
| PUT | `/schedule/api/blocks/<id>/lock` | 블록 잠금/해제 토글 |
| POST | `/schedule/api/draft/generate` | 자동 스케줄링 초안 생성 |
| POST | `/schedule/api/draft/approve` | 초안 확정 |
| POST | `/schedule/api/draft/discard` | 초안 폐기 |

---

## 4. 프로젝트 구조

```
scheduling/
├── run.py
├── config.py
├── data/                    # JSON 데이터 파일
│   ├── users.json
│   ├── categories.json
│   ├── tasks.json
│   ├── schedule_blocks.json
│   └── settings.json
├── app/
│   ├── __init__.py          # create_app
│   ├── json_store.py        # JSON 읽기/쓰기 + generate_id() + 파일 잠금 + .bak 백업
│   ├── blueprints/
│   │   ├── tasks/routes.py
│   │   ├── schedule/routes.py
│   │   └── admin/routes.py
│   ├── repositories/        # 데이터 접근 계층
│   │   ├── user_repo.py
│   │   ├── category_repo.py
│   │   ├── task_repo.py
│   │   ├── schedule_repo.py
│   │   └── settings_repo.py
│   ├── services/
│   │   └── scheduler.py     # 자동 스케줄링 로직 (분할 배치, 오버플로우 처리)
│   ├── templates/
│   │   ├── base.html
│   │   ├── schedule/day.html, week.html, month.html
│   │   ├── tasks/list.html, detail.html, form.html
│   │   └── admin/settings.html, users.html, categories.html
│   └── static/
│       ├── css/style.css
│       └── js/drag_drop.js  # SortableJS + grid snap (30분 단위) + data-date/data-time 처리
└── tests/
    └── test_app.py
```

---

## 5. UI 일관성 요구사항

모든 사용자 액션(생성/수정/삭제/드래그 등) 후 UI가 반드시 최신 상태를 반영해야 한다.
- API 호출 후 성공 응답을 받으면 관련 DOM을 즉시 갱신 (새로고침 없이)
- 실패 시 UI를 이전 상태로 롤백하고 에러 피드백 표시
- 모든 상태 변경 경로에서 빠짐없이 UI 업데이트 처리

---

## 6. 비기능 요구사항
- **파일 잠금:** `portalocker` 라이브러리로 JSON 동시 접근 시 데이터 무결성 보장
- **백업:** 매 쓰기 작업 전 `.bak` 파일 자동 생성 (json_store.py에서 처리)
- Bootstrap 5 반응형 레이아웃
- CDN으로 Bootstrap/SortableJS 로드

---

## 7. 구현 순서

1. **Phase 1 - 기반:** 프로젝트 구조 + json_store.py (ID 생성, 파일 잠금, 백업) + 설정/유저/카테고리 관리
2. **Phase 2 - 업무:** Task CRUD (remaining_hours 포함) + 목록/상세/폼
3. **Phase 3 - 캘린더:** 일간/주간/월간 뷰 + 네비게이션 + 색상 옵션
4. **Phase 4 - 스케줄링:** 자동 스케줄링 엔진 (분할 배치, is_locked 보호, 오버플로우 처리) + 초안/확정 워크플로우
5. **Phase 5 - 인터랙션:** 드래그앤드랍 (grid snap 30분, data-date/data-time) + UI 즉시 갱신
6. **Phase 6 - 마감:** 테스트 + 버그 수정 + UI 다듬기
