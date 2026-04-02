# Frontend 아키텍처 문서

## 1. 개요

서버 사이드 렌더링(Jinja2) + 바닐라 JavaScript 구성.

> **왜 React/Vue 같은 프레임워크를 쓰지 않는가?**
> 이 프로젝트는 빌드 도구 없이 간단하게 동작하는 것을 목표로 한다.
> HTML은 서버(Jinja2)에서 완성하여 보내고, JS는 드래그앤드롭·리사이즈 등
> 인터랙션에만 사용한다. npm/webpack 없이 `<script>` 태그 하나로 동작한다.

```
구성 파일:
├── templates/
│   ├── base.html                  ← 공통 레이아웃 (네비게이션, 모드 토글, 내보내기)
│   ├── schedule/
│   │   ├── day.html               ← 일간 캘린더 뷰 (장소별 컬럼)
│   │   ├── week.html              ← 주간 캘린더 뷰
│   │   ├── month.html             ← 월간 캘린더 뷰
│   │   ├── _task_queue.html       ← 업무 큐 사이드바 (include)
│   │   ├── _version_selector.html ← 버전 선택 드롭다운 (include)
│   │   └── _location_filter.html  ← 장소 필터 바 (include)
│   ├── tasks/
│   │   ├── list.html              ← 시험 항목 목록
│   │   ├── form.html              ← 시험 항목 생성/수정 폼
│   │   └── detail.html            ← 시험 항목 상세
│   └── admin/
│       ├── settings.html          ← 시스템 설정
│       ├── users.html             ← 사용자 관리
│       ├── user_form.html         ← 사용자 생성/수정 폼
│       ├── locations.html         ← 장소 관리
│       ├── location_form.html     ← 장소 생성/수정 폼
│       ├── versions.html          ← 버전 관리
│       └── version_form.html      ← 버전 생성/수정 폼
├── static/
│   ├── css/style.css              ← 전체 스타일
│   └── js/drag_drop.js            ← UI 이벤트 엔진
```

---

## 2. 서버에서 넘어오는 데이터

템플릿에서 사용하는 주요 변수들은 서버(routes.py)에서 `render_template()`으로 전달된다.

### 서버 → JS 전역 변수

| 변수 | 출처 | 설명 |
|------|------|------|
| `window.SCHEDULE_BREAKS` | day/week/month 템플릿의 `<script>` 블록 | 점심시간 + 추가 휴식시간 배열 `[{start, end}]`. 고스트 높이 계산(`workMinutes`)에 사용 |

### 공통 변수 (Jinja2 전역)

| 변수 | 출처 | 설명 |
|------|------|------|
| `cache_bust` | `create_app()`에서 서버 기동 시 타임스탬프로 설정 | `<script src="drag_drop.js?v={{ cache_bust }}">`처럼 사용하여 브라우저 캐시 무효화 |
| `enumerate` | Python 내장 함수를 Jinja2에 등록 | 템플릿에서 `{% for i, item in enumerate(list) %}` 사용 가능 |

### 일간/주간/월간 뷰 변수

| 변수 | 타입 | 설명 |
|------|------|------|
| `blocks` | list[dict] | enriched 블록 리스트 (procedure_id, assignee_name, location_name, color 등 포함) |
| `time_slots` | list[str] | `["08:00", "08:15", "08:30", ...]` 근무시간 타임슬롯 |
| `break_slots` | set[str] | `{"09:45", "12:00", "12:15", ...}` 휴식 시간대 |
| `queue_tasks` | list[dict] | 미배치 잔여시간이 있는 시험 항목 리스트 |
| `settings` | dict | 시스템 설정 |
| `locations` | list[dict] | 장소 목록 (일간 뷰 컬럼용) |
| `prev_date` / `next_date` | date | 이전/다음 날짜 (네비게이션용) |
| `current_date` | date | 현재 표시 중인 날짜 |
| `current_version_id` | str | 현재 선택된 버전 ID |
| `blocks_by_location` | dict | 장소 ID → 블록 리스트 (일간 뷰용) |

### `settings` 객체 구조

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

> **`work_start/end` vs `actual_work_start/end`:**
> `work_start/end`는 캘린더 **표시 범위** (08:00~17:00).
> `actual_work_start/end`는 자동 스케줄링의 **실제 배치 범위** (08:30~16:30).

---

## 3. 템플릿 구조

### 3.1 `base.html` — 공통 레이아웃

**구성:**
- Bootstrap 5.3.0 CDN + Bootstrap Icons
- 네비게이션: 일간/주간/월간 뷰 링크, 시험 항목, 관리자(사용자/장소/버전/설정) 드롭다운
- 편집/읽기 모드 토글 버튼 (localStorage 저장)
- 내보내기 드롭다운 (날짜 범위 + 포맷 선택 → `GET /schedule/api/export`)
- Flash 메시지 표시 영역
- `{% block content %}` — 자식 템플릿 콘텐츠 삽입 위치
- `{% block main_class %}` — 자식 템플릿에서 컨테이너 클래스 오버라이드 가능

### 3.2 일간 뷰 (`schedule/day.html`)

```
┌──────────────────────────────────────────────────────────────────┐
│ [◀ 이전일] [오늘] [다음일 ▶]  2026-03-15 (월)    [버전 선택 ▼]  │
├────────────┬────────┬──────────┬──────────┬──────────────────────┤
│            │        │ 장소 A   │ 장소 B   │ 장소 C              │
│  업무 큐    │ 시간   │ (컬럼)   │ (컬럼)   │ (컬럼)              │
│  사이드바   │ gutter │          │          │                     │
│            │ 08:00  │          │          │                     │
│  (드래그    │ 08:15  │┌────────┐│          │                     │
│   가능)    │ 08:30  ││ 블록 A ││          │                     │
│            │ 08:45  ││        ││┌────────┐│                     │
│            │ 09:00  │└────────┘││ 블록 B ││                     │
│            │ 09:15  │          │└────────┘│                     │
│            │ 09:30  │          │          │                     │
│            │ 09:45  │░░ 휴식 ░░│░░ 휴식 ░░│░░ 휴식 ░░           │
│            │ 10:00  │          │          │                     │
└────────────┴────────┴──────────┴──────────┴──────────────────────┘
```

**일간 뷰의 핵심 구조:**
- `day-columns-layout` (flex row):
  - `time-gutter` — 시간 라벨 컬럼 (좌측)
    - `time-gutter-header` — 장소 헤더와 높이를 맞추는 빈 공간
    - `time-gutter-label` × N — 각 시간 슬롯 라벨
  - `day-loc-col` × N — 각 장소별 컬럼
    - `day-loc-header` — 장소 이름 + 색상 dot (sticky)
    - `day-loc-body` — 시간 슬롯 + 블록들 (position: relative)

**블록 위치 계산 (Jinja2 서버사이드):**
```python
top = (start_min - work_start_min) / grid_interval * SLOT_HEIGHT  # px
height = (end_min - start_min) / grid_interval * SLOT_HEIGHT      # px
width = 100% / col_total                                          # 겹침 시 분할
left = col_index * width                                          # 겹침 시 오프셋
```

> **`col_index`와 `col_total`이란?**
> 같은 시간대에 여러 블록이 겹칠 때, 서버에서 각 블록에 열 번호(`col_index`)와
> 총 열 수(`col_total`)를 계산하여 전달한다. 프론트엔드는 이 값으로 블록의 너비와 위치를 결정한다.

**블록 HTML 구조 (실제 코드):**
```html
<div class="schedule-block draft block-status-pending"
     data-block-id="sb_xxx"
     data-task-id="t_xxx"
     data-block-status="pending"
     data-start-time="09:00"
     data-end-time="12:00"
     data-memo="메모 내용"
     data-procedure-id="STP-001"
     data-section-name="통신 시험"
     data-assignee-name="홍길동"
     data-location-name="시험실 A"
     style="top:0px; height:288px; width:100%; left:0%;
            background-color:#4A90D9;">
  <div class="resize-handle resize-handle-top"></div>
  <div class="block-title">
    STP-001
    <span class="block-section">통신 시험</span>
    <span class="block-status-badge badge-status-in_progress">진행</span>
  </div>
  <div class="block-meta">
    <span class="block-assignee">홍길동</span>
  </div>
  <div class="block-info">
    <span class="block-time">09:00–12:00</span>
  </div>
  <span class="memo-icon" title="메모 내용"><i class="bi bi-sticky-fill"></i></span>
  <span class="lock-icon"><i class="bi bi-lock-fill"></i></span>
  <button class="btn-to-queue" data-block-id="sb_xxx">
    <i class="bi bi-arrow-left-square"></i>
  </button>
  <div class="block-break-overlay" style="top:...px; height:...px;"></div>
  <div class="resize-handle resize-handle-bottom"></div>
</div>
```

> **휴식시간 빗금 오버레이(`block-break-overlay`)란?**
> 블록이 점심/휴식시간에 걸쳐 있을 때, 해당 구간에 대각선 빗금을 표시한다.
> 서버(Jinja2)에서 블록의 start/end와 각 break의 겹침을 계산하여 오버레이의
> `top`(블록 내 상대 위치)과 `height`(겹침 구간 높이)를 결정한다.

### 3.3 주간 뷰 (`schedule/week.html`)

일간 뷰와 유사한 타임라인 구조를 **7개 열(월~일)**로 확장한다.

| 차이점 | 일간 뷰 | 주간 뷰 |
|--------|---------|---------|
| 레이아웃 | 시간 거터 + 장소별 컬럼 | 시간 거터 + 7개 일별 컬럼 |
| CSS 클래스 | `.day-columns-layout` | `.week-grid`, `.week-day-col` |
| 블록 클래스 | `.schedule-block` | `.schedule-block.week-block` |
| 폰트 크기 | 기본 | 축소 (0.65rem) |
| 날짜 헤더 | 장소 이름 | 요일+날짜, 오늘은 `.today` 강조 |
| 장소 필터 | 컬럼으로 분리 | `_location_filter.html` 바 (버전 선택과 같이) |

### 3.4 월간 뷰 (`schedule/month.html`)

테이블 기반 달력. 각 셀에 최대 3개 블록 표시, 초과 시 "+N개 더" 표시.

```html
<td class="month-day-cell today-cell" data-date="2026-03-15">
  <a class="day-number" href="/schedule/?date=2026-03-15">15</a>
  <div class="month-block-item draft"
       data-block-id="sb_xxx"
       data-task-id="t_xxx"
       data-block-status="pending"
       style="background-color:#4A90D9;">
    STP-001
  </div>
  <div class="month-more-count">+2개 더</div>
</td>
```

### 3.5 업무 큐 사이드바 (`schedule/_task_queue.html`)

일간/주간/월간 뷰에 `{% include %}`로 포함.

```html
<div class="queue-task-item"
     data-task-id="t_xxx"
     data-assignee-ids='["u_xxx1"]'
     data-remaining-hours="5.5"
     data-location-id="loc_xxx"
     data-queue-color="#4A90D9"
     data-title="STP-001"
     style="border-left: 4px solid #4A90D9;">
  <div class="queue-task-title">STP-001</div>
  <span>통신 시험</span>
  <span>5.5h</span>
  <span>홍길동</span>
</div>
```

> **큐 색상 결정:** `settings.block_color_by` 값에 따라 좌측 보더 색상이 결정된다.
> `"assignee"` → 담당자의 `color`, `"location"` → 장소의 `color`.

검색 입력 필드 + 정렬 버튼 4개: 마감일, 이름, 시간, 우선순위.

### 3.6 시험 항목 목록 (`tasks/list.html`)

필터링(버전, 상태, 장소, 담당자, 절차서 검색) + 필터 칩 표시.

테이블 컬럼: 절차서 ID, 장절명, 담당자, 장소, 시간, 상태, **배치**.

**배치 상태 컬럼:**
서버에서 `schedule_status_map`을 전달하며, 각 태스크가 시간표에 블록이 있으면 "배치됨"(파란색), 없으면 "큐"(회색)로 표시된다.

```html
<span class="task-sched-chip sched-scheduled"><i class="bi bi-calendar-check"></i> 배치됨</span>
<span class="task-sched-chip sched-queue"><i class="bi bi-inbox"></i> 큐</span>
```

---

## 4. CSS 구조 (`style.css`)

### 주요 클래스

| 클래스 | 역할 |
|--------|------|
| `.schedule-layout` | flexbox 레이아웃 (큐 + 메인) |
| `.task-queue` | 220px 사이드바, `.collapsed` → 40px |
| `.day-columns-layout` | 일간 뷰 — 시간 거터 + 장소 컬럼 flex row |
| `.day-loc-col` | 일간 뷰 장소 컬럼 (flex column) |
| `.day-loc-header` | 장소 이름 헤더 (sticky top, 컬러 하단 보더) |
| `.day-loc-body` | 시간 슬롯 + 블록 컨테이너 (position: relative) |
| `.time-gutter` | 시간 라벨 컬럼 (70px) |
| `.time-gutter-header` | 장소 헤더와 높이를 맞추는 빈 공간 |
| `.time-slot` | 높이 24px, 15분 단위 셀 |
| `.break-slot` | 휴식 시간 시각적 구분 (연한 배경) |
| `.schedule-block` | 절대 위치 블록, `cursor: grab`, z-index: 10 |
| `.draft` | 점선 테두리 (초안 표시) |
| `.resize-handle` | 상/하단 리사이즈 핸들, z-index: 20 |
| `.drag-over` | 드래그 중 드롭 대상 강조 (점선 아웃라인) |
| `.block-break-overlay` | 대각선 빗금 (블록 내 휴식 시간 표시), z-index: 15 |
| `.task-linked-hover` | 동일 업무 호버 하이라이트 (아웃라인 + 밝기) |
| `.readonly-mode` | 읽기 모드: 드래그 비활성, 핸들/버튼 숨김 |
| `.block-detail-overlay` | 블록 상세 팝업 배경 오버레이 |
| `.block-status-badge` | 상태 배지 (pending은 숨김, 나머지 표시) |
| `.block-status-completed` | 완료 블록 투명도 0.5 |
| `.block-status-cancelled` | 불가 블록 투명도 0.4 |
| `.week-grid`, `.week-day-col` | 주간 뷰 전용 레이아웃 |
| `.resizing` | 리사이즈 중 블록 스타일, z-index: 30 |
| `.task-sched-chip` | 배치 상태 칩 (배치됨/큐) |
| `.sched-scheduled` | 배치됨 칩 (파란색) |
| `.sched-queue` | 큐 칩 (회색) |

### z-index 계층 구조

| z-index | 요소 | 설명 |
|---------|------|------|
| 5 | `.day-loc-header` | 장소 헤더 (sticky) |
| 10 | `.schedule-block` | 일반 블록 |
| 15 | `.block-break-overlay` | 블록 내 휴식 빗금 |
| 18 | `.btn-to-queue` | 큐 복귀 버튼 |
| 20 | `.resize-handle` | 리사이즈 핸들 |
| 30 | `.resizing` | 리사이즈 중인 블록 |
| 1100 | Toast container | 알림 메시지 |
| 1200 | Context menu | 우클릭 메뉴 |
| 1300 | Memo modal | 메모 모달 |
| 9999 | Ghost element | 드래그 미리보기 |

### 블록 크기 계산

```
SLOT_HEIGHT = 24px (15분 = 1칸)
1시간 블록 = 4칸 = 96px
3시간 블록 = 12칸 = 288px
```

---

## 5. JavaScript UI 이벤트 엔진 (`drag_drop.js`)

### 5.0 전체 구조

즉시실행함수(IIFE)로 전역 스코프 오염을 방지한다.

```javascript
(function () {
  'use strict';

  var GRID_MINUTES = 15;   // 시간 그리드 단위
  var SLOT_HEIGHT  = 24;   // 1칸(15분)의 픽셀 높이

  // ... 유틸리티, 이벤트 핸들러 함수들 ...

  document.addEventListener('DOMContentLoaded', function () {
    initBlockMove();       // 1. 블록 드래그 이동
    initMonthBlockMove();  // 2. 월간 블록 이동
    initQueueDrag();       // 3. 큐 → 캘린더 드래그
    initResize();          // 4. 블록 리사이즈
    initContextMenu();     // 5. 우클릭 컨텍스트 메뉴
    initReturnToQueue();   // 6. 큐로 되돌리기 버튼
    initDraftControls();   // 7. 초안 제어 버튼
    initQueueSearch();     // 8. 큐 검색
    initQueueToggle();     // 9. 큐 접기/펼치기
    initTaskHoverLink();   // 10. 동일 업무 호버 하이라이트
    initBlockDetail();     // 11. 블록 상세 팝업 (더블클릭)
  });
})();
```

**초기화 순서:** 11개의 `init*` 함수는 서로 독립적이며 순서가 바뀌어도 동작에 영향 없다.

**상태 관리:** SPA가 아니므로 클라이언트 상태를 유지하지 않는다.
모든 API 호출 성공 시 `location.reload()`로 전체 페이지를 새로고침하여
서버가 항상 진실의 원천(source of truth)이 된다.

### 5.1 공통 유틸리티

```javascript
// Toast 알림 — Bootstrap 스타일 알림을 화면 우하단에 표시, 4초 후 자동 제거
showToast(msg, type)

// API 호출 — fetch 래퍼, JSON 요청/응답
api(method, url, data) → Promise<json>

// 시간 변환
timeToMin("09:30")  → 570        // HH:MM → 분
minToTime(570)      → "09:30"    // 분 → HH:MM
snapMin(573)        → 570        // 15분 단위 반올림

// 쉬는시간 제외 실제 작업 분 계산
workMinutes(startMin, endMin) → number
// window.SCHEDULE_BREAKS (서버에서 전달)의 점심/휴식시간을 제외한 순수 작업 분 반환
// 예: workMinutes(660, 840) → 120 (11:00~14:00, 점심 1시간 제외 = 2시간)

// 읽기전용 모드 체크
isReadonly() → body에 'readonly-mode' 클래스가 있으면 true
```

### 5.2 드래그 시스템 핵심 원리

#### 5.2.1 공통 드래그 헬퍼: `startDrag()`

블록 이동, 큐 드래그, 월간 블록 이동이 **모두 이 함수를 공유**한다.
HTML5 Drag API를 사용하지 않고, **mousedown/mousemove/mouseup 이벤트**로 직접 구현한다.

**`startDrag(e, opts)` 파라미터:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `opts.sourceEl` | Element (선택) | 드래그 시작 시 투명도 30%로 변하는 원본 요소 |
| `opts.ghostText` | string | 커서를 따라다니는 미리보기의 텍스트 |
| `opts.ghostColor` | string | 미리보기의 배경색 |
| `opts.ghostWidth` | number | 미리보기의 너비 (px) |
| `opts.ghostHeight` | number | 미리보기의 높이 (px). 블록 이동 시 `workMinutes()` 기반으로 쉬는시간 제외한 실제 작업시간 높이 |
| `opts.onDrop` | function(target) | 드롭 시 실행할 콜백 |

**전체 흐름:**

```
[mousedown] → 5px 이상 이동 → [드래그 시작]
  → ghost 생성, hideAllBlocks(), 원본 투명도 30%
  → [mousemove] ghost 위치 업데이트, findTarget()으로 하이라이트
  → [mouseup] findTarget()으로 드롭 대상 결정, opts.onDrop(target) 콜백
```

#### 5.2.2 `hideAllBlocks()` — 왜 블록을 숨기는가?

`document.elementFromPoint(x, y)`는 최상위 DOM 요소만 반환한다.
블록이 타임 슬롯 위에 겹쳐져 있으면 슬롯을 감지할 수 없다.
드래그 시작 시 모든 블록의 `pointerEvents`를 `'none'`으로 설정하여 투과시킨다.

#### 5.2.3 `findTarget()` — 드롭 대상 판별

| type | 뷰 | date | time | 용도 |
|------|-----|------|------|------|
| `'slot'` | 일간/주간 | O | O | 블록 이동/생성 (정확한 시간) |
| `'month'` | 월간 | O | X | 날짜만 변경 |
| `'queue'` | 모든 뷰 | X | X | 블록을 큐로 반환 |

일간 뷰에서는 `slot`에 `data-location-id`도 포함되어 장소 이동이 가능하다.

---

### 5.3 블록 드래그 이동 (`initBlockMove`)

**대상:** `.schedule-block[data-block-id]` — 일간/주간 뷰의 스케줄 블록

```
onDrop(target):
  ├── target.type === 'queue' → DELETE /api/blocks/{id}
  ├── target.type === 'slot'  → PUT /api/blocks/{id} { date, start_time, end_time, location_id }
  └── target.type === 'month' → PUT /api/blocks/{id} { date }
```

### 5.4 큐 → 캘린더 드래그 (`initQueueDrag`)

**대상:** `.queue-task-item[data-task-id]` — 업무 큐의 아이템

```
블록 크기 결정: min(remaining * 60, 240분) → max(15분) → 15분 스냅

onDrop(target):
  ├── target.type === 'slot'  → POST /api/blocks { task_id, assignee_ids, location_id, ... }
  └── target.type === 'month' → POST /api/blocks { ..., start_time: actual_work_start }
```

### 5.5 월간 블록 이동 (`initMonthBlockMove`)

큐로 보내기 또는 다른 날짜 셀로 이동만 가능. 시간 조정 불가.

### 5.6 블록 리사이즈 (`initResize`)

**대상:** `.resize-handle` — 블록 상단/하단의 핸들 영역

```
[mousedown on .resize-handle]
  → [mousemove] 24px(=15분) 단위로 스냅하여 블록 크기 조절
  → [mouseup] PUT /api/blocks/{id} { start_time, end_time, resize: true }
     → resize: true가 서버에서 task의 estimated_hours 재계산을 트리거
```

### 5.7 컨텍스트 메뉴 (`initContextMenu`)

**트리거:** 스케줄 블록에서 우클릭

```
메뉴 항목:
┌─────────────────────────┐
│ 상태 변경               │
│  ○ 시작 전 (pending)    │
│  ● 진행 중 (active)     │
│  ○ 완료 (completed)     │
│  ○ 불가 (cancelled)     │
├─────────────────────────┤
│  메모                   │ → openMemoModal()
│  큐로 보내기            │ → DELETE /api/blocks/{id}
│  잠금 토글              │ → PUT /api/blocks/{id}/lock
│  삭제                   │ → confirm() → DELETE /api/blocks/{id}
└─────────────────────────┘
```

### 5.8 메모 모달 (`openMemoModal`)

컨텍스트 메뉴에서 "메모" 클릭 시 모달 팝업.
`PUT /api/blocks/{id}/memo`로 저장.

### 5.9 초안 제어 (`initDraftControls`)

`.schedule-nav` 툴바에 동적 추가되는 3개 버튼:
- **자동 스케줄링** → 설정 팝업 표시 (알고리즘 설명 + 날짜 범위 입력) → `POST /api/draft/generate`
- **초안 확정** → `POST /api/draft/approve`
- **초안 폐기** → `POST /api/draft/discard`

자동 스케줄링 팝업에는 배치 규칙 설명이 포함되어 있다:
- 절차서 번호 순서대로 가장 빠른 빈 시간에 배치
- 장소 미지정 항목은 가장 여유 있는 장소에 자동 배정
- 장소/시간 충돌 방지, 점심/휴식시간 건너뜀
- 결과는 초안으로 생성

초안 블록(`.schedule-block.draft`)이 DOM에 있을 때만 확정/폐기 버튼 표시.

### 5.10 큐로 되돌리기 (`initReturnToQueue`)

블록의 `←` 버튼 클릭 → `DELETE /api/blocks/{id}`.
`e.stopPropagation()`으로 블록 드래그와 충돌 방지.

### 5.11 큐 검색 (`initQueueSearch`)

큐 상단의 검색 입력 필드에서 절차서 ID/섹션명으로 필터링.

### 5.12 큐 접기/펼치기 (`initQueueToggle`)

```javascript
btn.onclick = function () { q.classList.toggle('collapsed'); };
```

### 5.13 동일 업무 호버 하이라이트 (`initTaskHoverLink`)

같은 `data-task-id`를 가진 모든 요소에 `task-linked-hover` 클래스를 토글.
스케줄 블록, 월간 블록, 큐 아이템이 동시에 강조된다.

### 5.14 블록 상세 팝업 (`initBlockDetail`)

**트리거:** 스케줄 블록 또는 큐 아이템에서 더블클릭

```
[더블클릭 on .schedule-block 또는 .queue-task-item]
    │
    ├── showTaskDetailPopup(taskId, { blockId, startTime, endTime, ... })
    │   → GET /tasks/api/{taskId} 로 task 상세 조회
    │
    ├── 팝업 표시:
    │   ┌──────────────────────────────┐
    │   │ STP-001  [대기]              │
    │   │ 통신 시험                     │
    │   ├──────────────────────────────┤
    │   │ 장소:     시험실 A           │
    │   │ 시간:     09:00 – 12:00     │
    │   │ 소요:     [120▼] 분 (잔여 90분) │  ← 편집 가능
    │   │ 시험 담당: 홍길동             │
    │   │ 절차서 담당: 김철수           │
    │   │ 버전:     v2.1.0             │
    │   │ 상태:     대기                │
    │   │ 시험목록: TC-001, TC-002     │
    │   │ 메모:     [___________]      │  ← 편집 가능
    │   ├──────────────────────────────┤
    │   │ 수정 페이지 →    [저장]      │
    │   └──────────────────────────────┘
    │
    └── [저장] 클릭:
        1. PUT /tasks/api/{taskId}/update — task의 estimated_hours, memo 업데이트
        2. (소요시간 변경 + blockId 있으면) PUT /schedule/api/blocks/{blockId}
           { duration_minutes: newEstMin } — 블록의 end_time 재계산
        3. 성공 시 페이지 새로고침
```

> **소요시간 변경 시 블록도 함께 업데이트:**
> 팝업에서 소요시간을 변경하면 task의 `estimated_hours`뿐 아니라
> schedule block의 `end_time`도 `duration_minutes` 파라미터를 통해 서버에서 재계산된다.
> 서버는 `start_time` + `duration_minutes`로 새 end_time을 계산하며, 휴식시간을 건너뛴다.

---

## 6. 이벤트 간 상호작용 방지

| 충돌 | 해결 방법 |
|------|----------|
| 리사이즈 vs 드래그 | `initBlockMove`에서 `.resize-handle` 체크 + `initResize`에서 `stopPropagation()` |
| 큐 복귀 버튼 vs 블록 드래그 | `mousedown`과 `click` 모두에 `stopPropagation` |
| 클릭 vs 드래그 | 5px 미만 이동은 클릭으로 간주 |
| 우클릭 vs 드래그 | `e.button !== 0`이면 무시 |
| 더블클릭 vs 드래그 | `dblclick`은 별도 이벤트, `mousedown`의 5px 임계값으로 자연 분리 |

---

## 7. 서버-클라이언트 통신 패턴

```
[사용자 조작]
    │
    ├── 드래그 이동 → PUT /api/blocks/{id}
    ├── 큐에서 드래그 → POST /api/blocks
    ├── 리사이즈 → PUT /api/blocks/{id} (resize: true)
    ├── 상태 변경 → PUT /api/blocks/{id}/status
    ├── 메모 저장 → PUT /api/blocks/{id}/memo
    ├── 잠금 토글 → PUT /api/blocks/{id}/lock
    ├── 큐 복귀 → DELETE /api/blocks/{id}
    ├── 블록 삭제 → DELETE /api/blocks/{id}
    ├── 초안 관리 → POST /api/draft/{generate|approve|discard}
    ├── 상세 팝업 저장 → PUT /tasks/api/{id}/update + PUT /api/blocks/{id} (duration_minutes)
    └── 내보내기 → GET /api/export?start_date=...&end_date=...&format=...
    │
    ▼
[api() 함수] → fetch → 성공: .then() / 실패: .catch() → showToast
    │
    ▼
[성공 후] → location.reload()
```

---

## 8. 읽기 전용 모드

`base.html`에서 `localStorage.getItem('scheduleMode')`를 확인하여
`body`에 `readonly-mode` 클래스를 추가/제거한다.

**CSS 효과:**
```css
.readonly-mode .schedule-block { cursor: default; }
.readonly-mode .resize-handle { display: none; }
.readonly-mode .btn-to-queue { display: none; }
```

**JS 효과:** `isReadonly()` 함수가 true를 반환하면 모든 드래그/리사이즈를 차단.
