# PRD: 소프트웨어 시험 절차 스케줄링 서비스

## Context

소프트웨어 시험 절차를 장소/버전별로 관리하고, 캘린더 형태로 스케줄링하는 웹 서비스. 드래그앤드롭으로 수동 배치하며, JSON 파일 기반 데이터 저장소를 사용한다.

## 기술 스택

- **Backend:** Flask + Jinja2
- **Frontend:** Bootstrap 5 + 바닐라 JavaScript (10개 모듈)
- **데이터 저장:** JSON 파일 (DB 없음, portalocker 파일 잠금)
- **포트:** 5001
- **테스트:** pytest (157개)

---

## 1. 데이터 계층

```
문서명 (doc_name)                    ← 최상단 그룹
  └─ 시험식별자 (identifiers[].id)     ← N개, 각각 예상시간 보유
       └─ 작성자 (identifiers[].owners) ← N개, 해당 식별자를 작성한 인원
```

- **시험 담당자** (assignee_names) = 테스트를 수행하는 사람 (이름 기반)
- **작성자** (owners) = 시험식별자를 작성/개발한 사람 (자유 텍스트)
- 두 그룹은 겹치지 않음 (작성한 사람과 테스트하는 사람은 별개)

---

## 2. 핵심 기능

### 2.1 시험 항목(Task) 관리

속성:
- `doc_id` (int) — 문서 ID
- `doc_name` — 문서명 (최상단 표시명)
- `version_id` — 소프트웨어 버전
- `assignee_names` — 시험 담당자 이름 배열 (복수)
- `location_id` — 시험 장소
- `identifiers` — 시험 식별자 배열:
  ```json
  [{"id": "TC-001", "name": "시험항목", "estimated_minutes": 60, "owners": ["김민수"]}]
  ```
- `estimated_minutes` — 식별자 시간 합 (불변, 리사이즈로 바뀌지 않음)
- `remaining_minutes` — 잔여 시간
- `status` — waiting / in_progress / completed
- `memo`
- `is_simple` — 단순 블록 여부 (시험 준비, 회의 등)

필터링: 상태, 담당자(이름), 장소, 문서명, 날짜

### 2.2 스케줄 블록 관리

속성:
- `task_id` — 연결된 시험항목 (단순 블록은 null)
- `assignee_names` — 담당자 이름 배열
- `location_id`
- `date`, `start_time`, `end_time`
- `is_locked` — 잠금 (이동/리사이즈 불가)
- `block_status` — pending / in_progress / completed / cancelled
- `identifier_ids` — 이 블록에 할당된 식별자 (null = 전체)
- `title` — 단순 블록용 제목
- `is_simple` — 단순 블록 여부
- `overflow_minutes` — 초과 시간 (다음날 넘김 시)
- `memo`

### 2.3 캘린더 뷰

| 뷰 | URL | 특징 |
|----|-----|------|
| 일간 | `/schedule/` | 장소별 컬럼, 5분 그리드, 리사이즈/이동 |
| 주간 | `/schedule/week` | 평일 5일 × 장소별 서브컬럼, 초기 진입 페이지 |
| 월간 | `/schedule/month` | 평일만 달력, 항목 수에 따라 셀 높이 자동 확장 |

공통: 장소 필터 (복수 선택, 컬럼 단위 숨김, localStorage 유지)

### 2.4 드래그앤드롭

- **큐→시간표**: 항목 드래그하여 시간대에 배치, 고스트 그리드 스냅 + 휴식 시간 높이 반영
- **블록 이동**: 같은날/다른날/큐복귀, 종료시간 초과 시 다음 근무일 자동 넘김
- **블록 리사이즈**: 상/하 핸들
- **다중 선택**: Ctrl+클릭 토글, Shift+클릭 범위 선택, Esc 해제
- **큐 다중 드래그**: Shift+클릭 범위 선택 후 드래그 → 순차 배치
- **블록 다중 이동**: 선택 후 드래그 → 순차 배치, 종료시간 초과 시 다음날 자동 전환

### 2.5 분할 배치

- 하나의 문서에 여러 식별자가 있을 때, 일부만 선택하여 배치 가능
- 큐에서 드래그 시 식별자 선택 피커 표시 (전체 선택/해제 버튼)
- 이미 배치된 식별자는 비활성 표시 + "배치됨" 뱃지
- 배치된 식별자를 다시 선택하면 기존 블록에서 자동 제거
- 우클릭 → "분리" / "일부 큐로 보내기"로 식별자 단위 관리
- 분할 뱃지: `2/5` — 부분 배치(나머지 큐)는 빨간색, 전체 배치는 기본색
- 상세 팝업에서 체크박스로 식별자 선택 + 분리/큐 복귀 버튼
- 행별 큐 복귀 버튼 (배치 열 옆)
- 같은 task 항목 호버 시 빨간 내부 테두리로 관련 블록 강조

### 2.6 시간 관리 규칙

- `estimated_minutes` = 식별자 시간 합 (불변)
- **리사이즈** = 실제 시간 변경 (remaining 변경 안 됨, 큐 미노출)
- **큐 복귀** (블록 삭제) = remaining 재계산
- 분할 안 된 블록이 있으면 해당 task는 큐에서 제거
- 분할된 블록만 있으면 미배치 식별자의 시간만 큐에 표시
- **종료시간 초과**: actual_work_end 기준 자동 감지 → 다음 근무일 자동 넘김
- 넘김 실패(겹침) 시 초과분은 줄어듦

### 2.7 추가 기능

- **간단 블록**: 시험 외 일정 (시험 준비, 회의 등), 제목+시간만으로 큐에 추가
- **일정 밀기/당기기**: 특정 날짜 이후 블록을 +1/-1일 이동, 주말 건너뛰기
- **내보내기**: CSV/Excel, 날짜 범위 지정, 버전 정보 포함, 분리 블록 (N/M) 표시
- **점심/휴식 표시**: 시간표 슬롯에 빗금 배경, 블록 오버레이
- **큐 그룹화**: 담당자별 그룹 토글 버튼

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
  "breaks": [{"start": "10:00", "end": "10:15"}],
  "grid_interval_minutes": 15,
  "max_schedule_days": 21,
  "block_color_by": "location"
}
```

- 일간 뷰는 5분 그리드 고정 (주간은 grid_interval_minutes 사용)
- actual_work_start/actual_work_end로 그리드 시작/종료 시간 결정

---

## 4. URL 구조

### 페이지
- `/` → 리다이렉트 → `/schedule/week`
- `/schedule/`, `/schedule/week`, `/schedule/month`
- `/tasks/`, `/tasks/new`, `/tasks/<id>`, `/tasks/<id>/edit`
- `/admin/settings`, `/admin/users`, `/admin/locations`

### API
- `POST/PUT/DELETE /schedule/api/blocks`, `/schedule/api/blocks/<id>/lock|status|memo`
- `POST /schedule/api/simple-blocks`
- `GET /schedule/api/blocks/by-task/<task_id>`
- `POST /schedule/api/blocks/shift`
- `POST /schedule/api/blocks/<id>/split`
- `POST /schedule/api/blocks/<id>/return-identifiers`
- `GET /schedule/api/export`
- `GET /schedule/api/day|week|month`
- `GET/POST/PUT/DELETE /tasks/api/*`
- `GET /tasks/api/check-identifier`
- `GET /tasks/api/procedure/<int:doc_id>`
- `GET/PUT /admin/api/settings`
- `GET/POST/PUT/DELETE /admin/api/users|locations|versions`
- `POST /api/sync/versions|test-data|reset-and-sync`
- `GET /api/sync/status`

---

## 5. 프로젝트 구조

```
scheduling/
├── run.py
├── scripts/csv_to_json.py              # CSV → JSON 변환
├── app/
│   ├── __init__.py                      # create_app()
│   ├── features/
│   │   ├── schedule/                    # 관리자 시간표
│   │   │   ├── store.py                 # JSON I/O + 파일 잠금
│   │   │   ├── data/                    # JSON 데이터 파일
│   │   │   ├── models/                  # BaseRepository + 도메인 모델
│   │   │   ├── routes/                  # 뷰 + API + 헬퍼
│   │   │   ├── helpers/                 # enrichment, overlap, time_utils
│   │   │   ├── services/               # export, procedure, sync
│   │   │   └── providers/              # 외부 데이터 프로바이더
│   │   └── execution/                   # 시험 실행 (설계 완료, 미구현)
│   ├── templates/
│   │   ├── schedule/                    # 시간표 템플릿
│   │   └── execution/                   # 실행 페이지 템플릿 (예정)
│   └── static/
│       └── schedule/
│           ├── css/style.css
│           └── js/ (10개 모듈)
├── tests/ (157개)
└── docs/
```
