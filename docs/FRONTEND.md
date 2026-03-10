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
│   ├── base.html              ← 공통 레이아웃 (네비게이션, 모드 토글, 내보내기)
│   ├── schedule/
│   │   ├── day.html           ← 일간 캘린더 뷰
│   │   ├── week.html          ← 주간 캘린더 뷰
│   │   ├── month.html         ← 월간 캘린더 뷰
│   │   └── _task_queue.html   ← 업무 큐 사이드바 (include)
│   ├── tasks/
│   │   ├── list.html          ← 업무 목록
│   │   ├── form.html          ← 업무 생성/수정 폼
│   │   └── detail.html        ← 업무 상세
│   └── admin/
│       ├── settings.html      ← 시스템 설정
│       ├── users.html         ← 사용자 관리
│       └── categories.html    ← 카테고리 관리
├── static/
│   ├── css/style.css          ← 전체 스타일
│   └── js/drag_drop.js        ← UI 이벤트 엔진 (666줄)
```

---

## 2. 서버에서 넘어오는 데이터

템플릿에서 사용하는 주요 변수들은 서버(routes.py)에서 `render_template()`으로 전달된다.

### 공통 변수 (Jinja2 전역)

| 변수 | 출처 | 설명 |
|------|------|------|
| `cache_bust` | `create_app()`에서 서버 기동 시 타임스탬프로 설정 | `<script src="drag_drop.js?v={{ cache_bust }}">`처럼 사용하여 브라우저 캐시 무효화 |
| `enumerate` | Python 내장 함수를 Jinja2에 등록 | 템플릿에서 `{% for i, item in enumerate(list) %}` 사용 가능 |

### 일간/주간/월간 뷰 변수

| 변수 | 타입 | 설명 |
|------|------|------|
| `blocks` | list[dict] | enriched 블록 리스트 (task_title, assignee_name, color 등 포함) |
| `time_slots` | list[str] | `["09:00", "09:15", "09:30", ...]` 근무시간 타임슬롯 |
| `break_slots` | set[str] | `{"09:45", "12:00", "12:15", ...}` 휴식 시간대 |
| `queue_tasks` | list[dict] | 미배치 잔여시간이 있는 업무 리스트 |
| `settings` | dict | `{work_start, work_end, lunch_start, lunch_end, breaks, block_color_by, ...}` |
| `users` | list[dict] | 사용자 목록 |
| `prev_date` / `next_date` | str | 이전/다음 날짜 (네비게이션용) |
| `current_date` | str | 현재 표시 중인 날짜 |

### `settings` 객체 구조 (프론트에서 자주 참조)

```json
{
  "work_start": "09:00",           // 근무 시작
  "work_end": "18:00",             // 근무 종료
  "lunch_start": "12:00",          // 점심 시작
  "lunch_end": "13:00",            // 점심 종료
  "breaks": [                      // 추가 휴식
    { "start": "09:45", "end": "10:00" },
    { "start": "14:45", "end": "15:00" }
  ],
  "grid_interval_minutes": 15,     // 시간 그리드 단위
  "max_schedule_days": 14,         // 자동 스케줄링 최대 일수
  "block_color_by": "assignee"     // "assignee" | "category"
}
```

---

## 3. 템플릿 구조

### 3.1 `base.html` — 공통 레이아웃

**구성:**
- Bootstrap 5.3.0 CDN + Bootstrap Icons
- 네비게이션: 일간/주간/월간 뷰 링크, 업무, 관리자(사용자/카테고리/설정) 드롭다운
- 편집/읽기 모드 토글 버튼 (localStorage 저장)
- 내보내기 드롭다운 (날짜 범위 + 포맷 선택 → `GET /schedule/api/export`)
- Flash 메시지 표시 영역
- `{% block content %}` — 자식 템플릿 콘텐츠 삽입 위치
- `{% block main_class %}` — 자식 템플릿에서 컨테이너 클래스 오버라이드 가능 (기본: `container mt-3`, 일간 뷰에서 `container-fluid p-0`으로 변경)

**인라인 스크립트:**
1. **모드 토글:** `localStorage.getItem('scheduleMode')`로 상태 관리, `body`에 `readonly-mode` 클래스 토글
2. **내보내기:** 날짜 기본값 설정 (현재 주), 유효성 검증, API URL(`/schedule/api/export?start_date=...&end_date=...&format=...`) 생성 후 다운로드

### 3.2 일간 뷰 (`schedule/day.html`)

```
┌──────────────────────────────────────────────────┐
│ [◀ 이전일] [오늘] [다음일 ▶]  2026-03-15 (월)    │
├────────────┬─────────────────────────────────────┤
│            │                                     │
│  업무 큐    │   시간 그리드 (15분 단위)            │
│  사이드바   │                                     │
│            │  09:00 ┌──────────────────┐         │
│  (드래그    │       │  블록 A          │         │
│   가능)    │  09:15 │  (절대 위치)      │         │
│            │       └──────────────────┘         │
│            │  09:30                              │
│            │  09:45 ░░░░░ 휴식시간 ░░░░░         │
│            │  10:00                              │
│            │                                     │
└────────────┴─────────────────────────────────────┘
```

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
> ```
> 예: 09:00~10:00에 블록 2개가 겹침
> 블록A: col_index=0, col_total=2 → width=50%, left=0%
> 블록B: col_index=1, col_total=2 → width=50%, left=50%
> ```

**블록 HTML 구조 (실제 코드):**
```html
<div class="schedule-block draft"
     data-block-id="sb_xxx"
     data-task-id="t_xxx"
     data-block-status="pending"
     data-start-time="09:00"
     data-end-time="12:00"
     data-memo="메모 내용"
     style="top:0px; height:288px; width:100%; left:0%;
            background-color:#4A90D9;">
  <div class="resize-handle resize-handle-top"></div>
  <div class="block-content">
    <span class="block-title">업무 이름</span>
    <span class="block-meta">09:00-12:00</span>
    <span class="block-info">
      <span class="block-priority priority-high">●</span>
      담당자 · 카테고리
    </span>
    <span class="badge block-status-badge badge-status-in_progress">진행 중</span>
  </div>
  <span class="memo-icon" title="메모 내용"><i class="bi bi-sticky-fill"></i></span>
  <span class="lock-icon"><i class="bi bi-lock-fill"></i></span>
  <button class="btn-to-queue" data-block-id="sb_xxx">
    <i class="bi bi-arrow-left-square"></i>
  </button>
  <!-- 블록 내 휴식시간 빗금 오버레이 (서버에서 계산) -->
  <div class="block-break-overlay"
       style="top:...px; height:...px;"></div>
  <div class="resize-handle resize-handle-bottom"></div>
</div>
```

> **휴식시간 빗금 오버레이(`block-break-overlay`)란?**
> 블록이 점심/휴식시간에 걸쳐 있을 때, 해당 구간에 대각선 빗금을 표시한다.
> 서버(Jinja2)에서 블록의 start/end와 각 break의 겹침을 계산하여 오버레이의
> `top`(블록 내 상대 위치)과 `height`(겹침 구간 높이)를 결정한다.
> CSS에서 `repeating-linear-gradient`로 빗금 패턴을 그린다.

**타임 슬롯 HTML:**
```html
<div class="time-slot break-slot"
     data-date="2026-03-15"
     data-time="09:45">
</div>
```

### 3.3 주간 뷰 (`schedule/week.html`)

일간 뷰와 동일한 타임라인 구조를 **7개 열(월~일)**로 확장한다.

| 차이점 | 일간 뷰 | 주간 뷰 |
|--------|---------|---------|
| 레이아웃 | 단일 열 | 시간 거터(좌측) + 7개 일별 열 |
| CSS 클래스 | `.timeline` | `.week-grid`, `.week-day-col` |
| 블록 클래스 | `.schedule-block` | `.schedule-block.week-block` |
| 폰트 크기 | 기본 | 축소 (0.65rem) |
| 날짜 헤더 | 없음 | 각 열 상단에 요일+날짜, 오늘은 `.today` 강조 |

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
    업무 이름
  </div>
  <div class="month-more-count">+2개 더</div>
</td>
```

### 3.5 업무 큐 사이드바 (`schedule/_task_queue.html`)

일간/주간/월간 뷰에 `{% include %}`로 포함.

```html
<div class="queue-task-item"
     data-task-id="t_xxx"
     data-assignee-id="u_xxx"
     data-remaining-hours="5.5"
     data-priority="high"
     data-title="업무 이름"
     data-deadline="2026-03-15"
     style="border-left: 4px solid #4A90D9;">
  <div class="queue-task-title">업무 이름</div>
  <span class="badge">high</span>
  <span>카테고리</span>
  <span>5.5h</span>
  <span>담당자</span>
  <span>~03/15</span>
</div>
```

> **큐 색상 결정:** `settings.block_color_by` 값에 따라 좌측 보더 색상이 결정된다.
> `"assignee"` → 담당자의 `color`, `"category"` → 카테고리의 `color`.

> **`data-remaining-hours`의 값:** 서버에서 `remaining_unscheduled_hours` (= 전체 remaining - 이미 배치된 블록 시간)을 계산하여 전달한다. 업무의 `remaining_hours`가 아닌, 아직 캘린더에 배치되지 않은 잔여 시간이다.

정렬 버튼 4개: 마감일, 이름, 시간, 우선순위.

---

## 4. CSS 구조 (`style.css`)

### 주요 클래스

| 클래스 | 역할 |
|--------|------|
| `.schedule-layout` | flexbox 레이아웃 (큐 + 메인) |
| `.task-queue` | 220px 사이드바, `.collapsed` → 40px |
| `.timeline` | 시간 거터 + 콘텐츠 영역 flexbox |
| `.time-slot` | 높이 24px, 15분 단위 셀 |
| `.break-slot` | 휴식 시간 시각적 구분 (연한 배경) |
| `.schedule-block` | 절대 위치 블록, `cursor: grab`, z-index: 10 |
| `.draft` | 점선 테두리 (초안 표시) |
| `.resize-handle` | 상/하단 리사이즈 핸들, z-index: 20 |
| `.drag-over` | 드래그 중 드롭 대상 강조 (점선 아웃라인) |
| `.block-break-overlay` | 대각선 빗금 (블록 내 휴식 시간 표시), z-index: 15 |
| `.task-linked-hover` | 동일 업무 호버 하이라이트 (아웃라인 + 밝기) |
| `.readonly-mode` | 읽기 모드: 드래그 비활성, 핸들/버튼 숨김 |
| `.memo-modal-backdrop` | 메모 모달 배경 오버레이, z-index: 1300 |
| `.block-status-badge` | 상태 배지 (pending은 숨김, 나머지 표시) |
| `.block-status-completed` | 완료 블록 투명도 0.5 |
| `.block-status-cancelled` | 불가 블록 투명도 0.4 |
| `.week-grid`, `.week-day-col` | 주간 뷰 전용 레이아웃 |
| `.resizing` | 리사이즈 중 블록 스타일, z-index: 30 |

### z-index 계층 구조

UI 요소가 겹칠 때 어떤 것이 위에 표시되는지 결정한다:

| z-index | 요소 | 설명 |
|---------|------|------|
| 10 | `.schedule-block` | 일반 블록 |
| 15 | `.block-break-overlay` | 블록 내 휴식 빗금 |
| 18 | `.btn-to-queue` | 큐 복귀 버튼 |
| 20 | `.resize-handle` | 리사이즈 핸들 |
| 30 | `.resizing` | 리사이즈 중인 블록 |
| 1100 | Toast container | 알림 메시지 |
| 1200 | Context menu | 우클릭 메뉴 |
| 1300 | Memo modal | 메모 모달 |
| 9999 | Ghost element | 드래그 미리보기 |

### 리사이즈 핸들의 특수 동작

```css
.resize-handle { pointer-events: none; }           /* 기본: 클릭 불가 */
.schedule-block:hover .resize-handle { pointer-events: auto; }  /* 호버 시: 클릭 가능 */
```
블록 위에 마우스를 올려야만 리사이즈 핸들이 활성화된다.
기본 상태에서 `pointer-events: none`이므로 핸들 영역을 클릭해도 아래의 블록이 이벤트를 받는다.

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

> **IIFE란?** `(function() { ... })()` 형태로, 함수를 선언과 동시에 실행한다.
> 내부의 변수/함수가 전역(`window`)에 노출되지 않는다.
> 이 프로젝트는 ES Module(`import/export`)을 쓰지 않으므로,
> IIFE가 모듈 스코프 역할을 대신한다.

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
    initQueueSort();       // 8. 큐 정렬
    initQueueToggle();     // 9. 큐 접기/펼치기
    initTaskHoverLink();   // 10. 동일 업무 호버 하이라이트
  });
})();
```

**초기화 순서:** 10개의 `init*` 함수는 서로 독립적이며 순서가 바뀌어도 동작에 영향 없다.
각 함수는 자기가 관리하는 DOM 요소에만 이벤트를 등록한다.

**상태 관리:** SPA가 아니므로 클라이언트 상태를 유지하지 않는다.
모든 API 호출 성공 시 `location.reload()`로 전체 페이지를 새로고침하여
서버가 항상 진실의 원천(source of truth)이 된다.

### 5.1 공통 유틸리티

```javascript
// Toast 알림 — Bootstrap 스타일 알림을 화면 우하단에 표시, 4초 후 자동 제거
showToast(msg, type)

// API 호출 — fetch 래퍼, JSON 요청/응답
// r.ok가 false면 응답 JSON의 error 필드를 추출하여 throw new Error()
// 호출부에서 .catch()로 에러를 잡아 showToast로 표시
api(method, url, data) → Promise<json>

// 시간 변환
pad(n)              → "01", "09"  // 한 자리 숫자를 두 자리로 패딩
timeToMin("09:30")  → 570        // HH:MM → 분
minToTime(570)      → "09:30"    // 분 → HH:MM
snapMin(573)        → 570        // Math.round(573/15)*15 = 570 (15분 단위 반올림)

// 읽기전용 모드 체크
isReadonly() → body에 'readonly-mode' 클래스가 있으면 true
```

### 5.2 드래그 시스템 핵심 원리

#### 5.2.1 공통 드래그 헬퍼: `startDrag()`

블록 이동, 큐 드래그, 월간 블록 이동이 **모두 이 함수를 공유**한다.
HTML5 Drag API를 사용하지 않고, **mousedown/mousemove/mouseup 이벤트**로 직접 구현한다.

> **왜 HTML5 Drag API를 안 쓰는가?**
> HTML5 Drag API는 드래그 이미지 커스터마이즈가 제한적이고,
> `elementFromPoint()`로 정확한 드롭 위치를 감지하기 어렵다.
> 마우스 이벤트 직접 처리가 더 세밀한 제어를 제공한다.

> **터치 디바이스 미지원:** `mousedown/mousemove/mouseup`만 사용하므로
> 모바일/태블릿 터치 이벤트(`touchstart/touchmove/touchend`)에는 반응하지 않는다.

**`startDrag(e, opts)` 파라미터:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `opts.sourceEl` | Element (선택) | 드래그 시작 시 투명도 30%로 변하는 원본 요소 |
| `opts.ghostText` | string | 커서를 따라다니는 미리보기의 텍스트 |
| `opts.ghostColor` | string | 미리보기의 배경색 |
| `opts.ghostWidth` | number | 미리보기의 너비 (px) |
| `opts.onDrop` | function(target) | 드롭 시 실행할 콜백. target은 `findTarget()` 반환값 |

**전체 흐름:**

```
[mousedown 발생]
    │
    ├── button !== 0 (좌클릭 아님) → 무시
    │   (우클릭은 컨텍스트 메뉴가 처리하므로 드래그 시작 방지)
    ├── isReadonly() → 무시
    │
    ├── document에 mousemove, mouseup 리스너 등록
    │   startX, startY 기록
    │
    ▼
[mousemove 발생]
    │
    ├── |dx| + |dy| < 5px → 무시 (클릭과 드래그 구분, 5px 임계값)
    │
    ├── 최초 5px 초과 시 (드래그 시작):
    │   ├── ghost 요소 생성 (커서를 따라다니는 미리보기)
    │   ├── hideAllBlocks() 호출 ★ (아래 5.2.2에서 상세 설명)
    │   ├── 원본 요소 투명도 30%로 (어디서 드래그했는지 시각적 표시)
    │   ├── document.body.style.userSelect = 'none' (드래그 중 텍스트 선택 방지)
    │   └── cursor를 'grabbing'으로 변경
    │
    ├── ghost 위치 업데이트 (clientX + 12, clientY + 12)
    │
    └── findTarget(x, y) 호출 → 드롭 대상 하이라이트
        │
        ▼
[mouseup 발생]
    │
    ├── findTarget()으로 최종 드롭 대상 결정
    ├── 정리: ghost 제거, 블록 복원, 하이라이트 해제,
    │         userSelect 복원, cursor 복원
    │
    ├── 드래그 안 했으면 (5px 미만 이동) → 아무것도 안 함
    │
    └── 드래그 했으면:
        └── opts.onDrop(target) 콜백 실행
```

> **드래그 중 자동 스크롤:** 현재 구현되어 있지 않다. 화면 끝으로 드래그해도 자동으로 스크롤되지 않으므로, 긴 타임라인에서는 미리 스크롤한 뒤 드래그해야 한다.

#### 5.2.2 `hideAllBlocks()` — 왜 블록을 숨기는가?

```javascript
function hideAllBlocks() {
  document.querySelectorAll('.schedule-block, .month-block-item').forEach(function (b) {
    b.style.pointerEvents = 'none';
  });
}
```

**핵심 문제:** `document.elementFromPoint(x, y)`는 해당 좌표의 **최상위 DOM 요소**만 반환한다.
스케줄 블록(`.schedule-block`)이 타임 슬롯(`.time-slot`) 위에 `position: absolute`로 겹쳐져 있으므로,
커서 아래의 타임 슬롯을 감지할 수 없다.

**해결:** 드래그 시작 시 모든 블록의 `pointerEvents`를 `'none'`으로 설정하면,
브라우저가 해당 요소를 "없는 것처럼" 취급하여 `elementFromPoint()`가 블록을 "투과"하여
그 아래의 `.time-slot` 요소를 반환한다.

```
드래그 전:                    드래그 중 (hideAllBlocks 후):

┌─ 블록 (z-index:10) ┐       ┌─ 블록 (pointerEvents: none) ─┐
│  elementFromPoint    │       │  ← 브라우저가 이 요소를 무시   │
│  = 블록 반환 ✗      │       │                               │
├─ 타임슬롯 ──────────┤       ├─ 타임슬롯 ──────────────────┤
│  감지 불가           │       │  elementFromPoint = 이것 반환 ✓│
└─────────────────────┘       └────────────────────────────────┘
```

드래그 종료 시 `showAllBlocks()`로 `pointerEvents`를 빈 문자열(`''`)로 복원한다.

#### 5.2.3 `findTarget()` — 드롭 대상 판별

```javascript
function findTarget(x, y) {
  var el = document.elementFromPoint(x, y);  // 커서 아래 DOM 요소
  if (!el) return null;

  // 1순위: .time-slot (일간/주간 뷰의 시간 칸)
  var slot = el.closest('.time-slot');
  if (slot && slot.dataset.date && slot.dataset.time) {
    return { type: 'slot', date: '2026-03-15', time: '09:00', el: slot };
  }

  // 2순위: .month-day-cell (월간 뷰의 날짜 셀)
  var cell = el.closest('.month-day-cell[data-date]');
  if (cell) {
    return { type: 'month', date: '2026-03-15', el: cell };
  }

  // 3순위: #task-queue (업무 큐 영역)
  var queue = el.closest('#task-queue');
  if (queue) {
    return { type: 'queue', el: queue };
  }

  return null;  // 유효한 드롭 대상 아님
}
```

> **`el.closest(selector)`란?** 해당 요소부터 DOM 트리를 위로 올라가며
> 셀렉터에 맞는 첫 번째 부모를 반환한다. 커서가 타임 슬롯 내부의 텍스트 위에 있어도
> `.time-slot`까지 올라가서 감지할 수 있다.

**반환 객체:**

| type | 뷰 | date | time | 용도 |
|------|-----|------|------|------|
| `'slot'` | 일간/주간 | O | O | 블록 이동/생성 (정확한 시간) |
| `'month'` | 월간 | O | X | 날짜만 변경 |
| `'queue'` | 모든 뷰 | X | X | 블록을 큐로 반환 |

#### 5.2.4 Ghost 요소 — 드래그 미리보기

```javascript
function createGhost(text, color, w) {
  var g = document.createElement('div');
  g.textContent = text;         // 업무 이름
  g.style.cssText =
    'position:fixed;'           // 뷰포트 기준 위치 (스크롤과 무관)
    + 'z-index:9999;'           // 최상위 표시
    + 'pointer-events:none;'    // 마우스 이벤트 통과 (findTarget 방해 안 함)
    + 'opacity:0.85;'           // 약간 투명
    + 'background:' + color;    // 블록/업무 색상
  document.body.appendChild(g);
  return g;
}
```

**`pointer-events: none`이 여기서도 사용되는 이유:**
Ghost 자체가 `elementFromPoint()`의 결과를 가로채면 안 되기 때문이다.
Ghost가 커서 바로 옆에 있으므로, `pointer-events: none`이 없으면
`findTarget()`이 Ghost 요소를 반환하여 실제 드롭 대상을 찾을 수 없다.

이동 중:
```javascript
ghost.style.left = ev.clientX + 12 + 'px';  // 커서 우측 12px
ghost.style.top  = ev.clientY + 12 + 'px';  // 커서 하단 12px
```
12px 오프셋으로 Ghost가 커서 바로 위를 가리지 않게 한다.

#### 5.2.5 드롭 대상 하이라이트

```javascript
var highlighted = null;

function setHighlight(target) {
  clearHighlight();
  if (target && target.el) {
    target.el.classList.add('drag-over');  // CSS: 점선 아웃라인 + 배경색
    highlighted = target.el;
  }
}

function clearHighlight() {
  if (highlighted) highlighted.classList.remove('drag-over');
  highlighted = null;
}
```

`mousemove`마다 이전 하이라이트를 제거하고 새 대상에 추가한다.
`highlighted` 변수로 현재 하이라이트된 요소를 추적하여, 매번 모든 요소를 순회하지 않는다.

---

### 5.3 블록 드래그 이동 (`initBlockMove`)

**대상:** `.schedule-block[data-block-id]` — 일간/주간 뷰의 스케줄 블록

```
사용자가 블록을 mousedown
    │
    ├── e.target이 .resize-handle 내부면 → 무시 (리사이즈가 처리)
    ├── e.target이 .btn-to-queue면 → stopPropagation으로 이미 차단됨 (5.8 참조)
    │
    ├── 블록 정보 추출: blockId, title, color, duration
    │
    └── startDrag() 호출 (onDrop 콜백 전달)
         │
         └── onDrop(target):
              │
              ├── target.type === 'queue'
              │   → DELETE /api/blocks/{id}
              │   → 블록 삭제 + remaining_hours 재계산
              │
              ├── target.type === 'slot'
              │   → PUT /api/blocks/{id}
              │     { date, start_time: snapMin(time), end_time: start + duration }
              │   → 기존 duration 유지한 채 새 위치로 이동
              │
              └── target.type === 'month'
                  → PUT /api/blocks/{id} { date: target.date }
                  → 날짜만 변경 (시간은 유지)
```

**duration 보존 원리:**
```javascript
var durationMin = timeToMin(endTime) - timeToMin(startTime);
// 드래그 전 블록이 09:00~12:00이면 durationMin = 180

// 드롭 시 새 위치의 시작 시간에 duration을 더함:
var t = snapMin(timeToMin(target.time));  // 예: 14:00 = 840분
// end_time = minToTime(840 + 180) = "17:00"

// 서버에서는 실제 근무시간(휴식 제외)을 기준으로 end_time을 재조정한다.
// 프론트에서 보낸 end_time과 서버가 저장하는 end_time이 다를 수 있다.
```

### 5.4 큐 → 캘린더 드래그 (`initQueueDrag`)

**대상:** `.queue-task-item[data-task-id]` — 업무 큐의 아이템

```
사용자가 큐 아이템을 mousedown
    │
    ├── 업무 정보 추출: taskId, assigneeId, remainingHours, title
    │
    └── startDrag() 호출 (onDrop 콜백 전달)
         │
         └── onDrop(target):
              │
              ├── 블록 시간 계산:
              │   blockMin = min(remaining * 60, 240)  // 최대 4시간
              │   blockMin = max(blockMin, 15)          // 최소 15분
              │   blockMin = round(blockMin / 15) * 15  // 15분 단위 스냅
              │
              ├── target.type === 'slot'
              │   → POST /api/blocks
              │     { task_id, assignee_id, date, start_time, end_time, origin:'manual' }
              │   → 새 블록 생성
              │
              └── target.type === 'month'
                  → POST /api/blocks
                    { ..., start_time:'09:00', end_time: 09:00+blockMin }
                  → 09:00 시작으로 블록 생성
```

> **참고:** 큐 드래그의 ghost 색상은 항상 `#0d6efd`(Bootstrap 기본 파랑)으로 하드코딩되어 있다. 블록 드래그는 원본 블록의 `backgroundColor`를 사용하는 것과 다르다.

**블록 크기 결정 로직:**
```
remaining_hours = 5.5 → 5.5 * 60 = 330 → min(330, 240) = 240분 (최대 4시간 제한)
remaining_hours = 0.3 → 0.3 * 60 = 18 → max(18, 15) = 18 → snap → 15분
remaining_hours = 1.0 → 1.0 * 60 = 60분
```

### 5.5 월간 블록 이동 (`initMonthBlockMove`)

**대상:** `.month-block-item[data-block-id]`

큐로 보내기 또는 다른 날짜 셀로 이동만 가능. 시간 조정 불가.

```
onDrop(target):
  ├── target.type === 'queue' → DELETE (큐 복귀)
  └── target.type === 'month' → PUT { date: target.date } (날짜 이동)
```

> **제한사항:** 월간 뷰에서 타임 슬롯(`target.type === 'slot'`)은 존재하지 않으므로,
> 월간 블록을 일간/주간 뷰로 드래그할 수 없다 (같은 페이지에 공존하지 않으므로).

---

### 5.6 블록 리사이즈 (`initResize`)

**대상:** `.resize-handle` — 블록 상단/하단의 핸들 영역

> **핸들은 블록에 호버해야만 클릭 가능하다.** CSS에서 `.resize-handle`의 `pointer-events`가 기본 `none`이고, `.schedule-block:hover` 시에만 `auto`로 변경된다. (4절 CSS 참조)

**HTML5 Drag API를 사용하지 않고 mousedown/mousemove/mouseup으로 직접 구현.**

```
[mousedown on .resize-handle]
    │
    ├── e.stopPropagation() ← 블록 드래그와 겹치지 않게 이벤트 전파 중단
    │
    ├── 초기값 기록:
    │   isTop = handle이 resize-handle-top인지 여부
    │   origTop = block.style.top (px)
    │   origHeight = block.style.height (px)
    │   startY = e.clientY
    │
    ▼
[mousemove]
    │
    ├── delta = ev.clientY - startY (마우스 이동량, px)
    ├── snapped = round(delta / SLOT_HEIGHT) * SLOT_HEIGHT
    │             ↑ 24px(=15분) 단위로 스냅
    │
    ├── 상단 핸들 (isTop):
    │   newTop = origTop + snapped      ← 시작 시간 변경
    │   newHeight = origHeight - snapped ← 높이는 반대로 변화
    │   제약: newHeight >= 24px (최소 15분), newTop >= 0
    │
    └── 하단 핸들 (!isTop):
        newHeight = origHeight + snapped ← 종료 시간 변경
        제약: newHeight >= 24px (최소 15분)
    │
    ▼
[mouseup]
    │
    ├── 최종 위치에서 시간 역산:
    │   firstSlot = DOM에서 첫 번째 .time-slot의 data-time (예: "09:00")
    │   wsMin = timeToMin(firstSlot) → 540 (= 09:00, 근무 시작 분)
    │   newStartMin = wsMin + (finalTop / SLOT_HEIGHT) * GRID_MINUTES
    │   durationMin = (finalHeight / SLOT_HEIGHT) * GRID_MINUTES
    │   newStart = minToTime(newStartMin)
    │   newEnd = minToTime(newStartMin + durationMin)
    │
    ├── 시간이 변경되었으면:
    │   → PUT /api/blocks/{id} { start_time, end_time, resize: true }
    │   → resize: true 플래그가 서버에서 remaining_hours 재계산을 트리거
    │     (일반 이동에서는 근무시간이 보존되므로 재계산 불필요)
    │
    └── API 실패 시: origTop, origHeight로 블록 크기 롤백
```

**픽셀 ↔ 시간 변환 원리:**

```
SLOT_HEIGHT = 24px = 15분 (GRID_MINUTES)

시간 → 픽셀 (서버에서 계산, 블록 렌더링 시):
  09:00에 시작하는 블록의 top = (540 - 540) / 15 * 24 = 0px
  09:30에 시작하는 블록의 top = (570 - 540) / 15 * 24 = 48px
  1시간 블록의 height = 60 / 15 * 24 = 96px

픽셀 → 시간 (JS에서 계산, 리사이즈 완료 시):
  top 48px → 48 / 24 * 15 = 30분 오프셋 → 09:00 + 30분 = 09:30
  height 96px → 96 / 24 * 15 = 60분 = 1시간
```

**상단 vs 하단 리사이즈 차이:**

```
상단 핸들 드래그 (시작 시간 조절):

  원래:                  위로 드래그 (확장):       아래로 드래그 (축소):
  ┌──────────┐          ┌──────────┐              ┊
  │          │          │ 추가 영역 │              ┊ (사라진 영역)
  │ 블록     │    →     │──────────│        →     ┌──────────┐
  │          │          │ 블록     │              │ 블록     │
  └──────────┘          └──────────┘              └──────────┘

하단 핸들 드래그 (종료 시간 조절):

  원래:                  아래로 드래그 (확장):      위로 드래그 (축소):
  ┌──────────┐          ┌──────────┐              ┌──────────┐
  │ 블록     │    →     │ 블록     │        →     │ 블록     │
  │          │          │          │              └──────────┘
  └──────────┘          │ 추가 영역 │              ┊ (사라진 영역)
                        └──────────┘              ┊
```

---

### 5.7 컨텍스트 메뉴 (`initContextMenu`)

**트리거:** 스케줄 블록에서 우클릭 (`contextmenu` 이벤트)

> **월간 뷰에서는 컨텍스트 메뉴가 동작하지 않는다.**
> 대상이 `.schedule-block[data-block-id]`이므로, `.month-block-item`에는 반응하지 않는다.

```
[우클릭 on .schedule-block]
    │
    ├── e.preventDefault() ← 브라우저 기본 메뉴 차단
    ├── 기존 메뉴 제거
    │
    ├── Bootstrap 드롭다운 스타일의 메뉴를 동적 생성
    │   position: fixed, 클릭 좌표에 배치
    │
    │   메뉴 항목:
    │   ┌─────────────────────────┐
    │   │ 상태 변경               │
    │   │  ○ 시작 전 (pending)    │ ← 아직 시작하지 않은 상태
    │   │  ● 진행 중 (active)     │ ← 현재 상태에 active 표시
    │   │  ○ 완료 (completed)     │ ← 작업 완료
    │   │  ○ 불가 (cancelled)     │ ← 해당 시간 작업 불가능
    │   ├─────────────────────────┤
    │   │  메모                   │ → openMemoModal()
    │   │  큐로 보내기            │ → DELETE /api/blocks/{id}
    │   │  잠금 토글              │ → PUT /api/blocks/{id}/lock
    │   │  삭제                   │ → confirm() → DELETE /api/blocks/{id}
    │   └─────────────────────────┘
    │
    └── 메뉴 외부 클릭 시 메뉴 제거
```

**메뉴 외부 클릭 닫기 구현:**
```javascript
setTimeout(function () {
  document.addEventListener('click', function h() {
    menu.remove();
    document.removeEventListener('click', h);
  }, { once: true });
}, 0);
```

> **왜 `setTimeout(fn, 0)`인가?**
> 우클릭 이벤트가 처리된 직후, 같은 이벤트 루프에서 `click` 리스너를 등록하면
> 현재 이벤트가 리스너를 즉시 트리거하여 메뉴가 열리자마자 닫힌다.
> `setTimeout(fn, 0)`으로 다음 이벤트 루프까지 지연시키면,
> 현재 우클릭 이벤트는 무시되고 **이후의** 클릭만 메뉴를 닫는다.

---

### 5.8 메모 모달 (`openMemoModal`)

```
[컨텍스트 메뉴에서 "메모" 클릭]
    │
    ├── 기존 모달 있으면 제거
    │
    ├── DOM 동적 생성:
    │   ┌─── backdrop (반투명 검정 오버레이) ───┐
    │   │                                       │
    │   │   ┌─── modal card ───────────────┐   │
    │   │   │  메모                         │   │
    │   │   │  ┌─── textarea ────────────┐ │   │
    │   │   │  │ (현재 메모 내용)         │ │   │
    │   │   │  └─────────────────────────┘ │   │
    │   │   │         [취소]  [저장]        │   │
    │   │   └──────────────────────────────┘   │
    │   │                                       │
    │   └───────────────────────────────────────┘
    │
    ├── 취소: backdrop 제거
    ├── backdrop 클릭: backdrop 제거
    ├── 저장:
    │   → PUT /api/blocks/{id}/memo { memo: textarea.value }
    │   → 성공 시 모달 제거 + 페이지 새로고침
    │
    └── HTML 이스케이프: currentMemo의 '<' → '&lt;'로 변환
        (textarea 안에 들어가므로 직접적 XSS 위험은 낮지만, 최소한의 보호)
```

---

### 5.9 초안 제어 (`initDraftControls`)

```
[DOMContentLoaded]
    │
    ├── .schedule-nav 툴바에 버튼 3개 동적 추가:
    │   [자동 스케줄링]  [초안 확정]  [초안 폐기]
    │
    ├── .schedule-block.draft 요소가 DOM에 있으면:
    │   → [초안 확정], [초안 폐기] 버튼을 보이게 표시
    │     (초안이 없으면 이 두 버튼은 숨겨짐)
    │
    ├── [자동 스케줄링] 클릭:
    │   → POST /api/draft/generate
    │   → 응답: { placed_count: 5, unplaced: [...] }
    │   → showToast("5개 블록 배치 (미배치 2개)")
    │   → 0.5초 후 새로고침 (Toast 메시지를 보여주기 위한 지연)
    │
    ├── [초안 확정] 클릭:
    │   → POST /api/draft/approve
    │   → 초안 → 확정, remaining_hours 차감
    │   → 0.5초 후 새로고침
    │
    └── [초안 폐기] 클릭:
        → confirm("초안을 모두 폐기하시겠습니까?")
        → POST /api/draft/discard
        → 모든 초안 삭제
        → 0.5초 후 새로고침
```

> **왜 0.5초 지연?** 다른 API 호출은 성공 즉시 `location.reload()`하지만,
> 초안 제어는 Toast 메시지를 먼저 보여주고 0.5초 후 새로고침한다.
> 사용자에게 결과(배치 수, 미배치 수)를 확인할 시간을 주기 위한 것이다.

### 5.10 큐로 되돌리기 (`initReturnToQueue`)

```
[click on .btn-to-queue]
    │
    ├── e.stopPropagation() ← 블록의 mousedown(드래그)이 발동하지 않게
    │   (mousedown과 click 모두에 stopPropagation 적용)
    │
    └── DELETE /api/blocks/{id}
        → 블록 삭제 + remaining_hours 재계산
        → showToast + 새로고침
```

### 5.11 큐 정렬 (`initQueueSort`)

```
[click on .queue-sort-btn]
    │
    ├── 같은 버튼 재클릭: 오름차순 ↔ 내림차순 토글
    ├── 다른 버튼 클릭: 해당 기준으로 오름차순 정렬
    │
    ├── 정렬 기준:
    │   ├── deadline: dataset.deadline 문자열 비교
    │   ├── name: dataset.title 로케일 비교 (localeCompare)
    │   ├── hours: dataset.remainingHours 숫자 비교
    │   └── priority: { high:0, medium:1, low:2 } 매핑 비교
    │
    └── DOM 재배치:
        items.sort(compareFn)
        items.forEach(item => body.appendChild(item))
        ↑ appendChild는 기존 위치에서 제거 후 끝에 추가
          (서버 요청 없이 클라이언트에서만 DOM 순서 변경)
          (새로고침하면 원래 순서로 돌아감)
```

### 5.12 큐 접기/펼치기 (`initQueueToggle`)

```javascript
btn.onclick = function () { q.classList.toggle('collapsed'); };
// CSS: .task-queue.collapsed { width: 40px; overflow: hidden; }
```

### 5.13 동일 업무 호버 하이라이트 (`initTaskHoverLink`)

```
[mouseenter on [data-task-id] 요소]
    │
    ├── data-task-id 값 추출 (예: "t_abc123")
    │
    └── 같은 task-id를 가진 모든 요소에 'task-linked-hover' 클래스 추가
        → CSS: outline + brightness 필터로 강조
        → 스케줄 블록, 월간 블록, 큐 아이템 모두 동시 하이라이트

[mouseleave]
    └── 모든 'task-linked-hover' 클래스 제거
```

**사용 시나리오:**
큐의 "로그인 구현" 업무에 마우스를 올리면,
캘린더에 배치된 같은 업무의 모든 블록이 동시에 강조된다.
역으로, 캘린더의 블록에 마우스를 올리면 큐의 해당 업무 아이템도 강조된다.

---

## 6. 이벤트 간 상호작용 방지

하나의 DOM 요소에 여러 이벤트 핸들러가 걸려 있을 때, 원치 않는 동시 실행을 방지하는 메커니즘:

### 6.1 리사이즈 vs 드래그

```javascript
// initBlockMove에서:
block.addEventListener('mousedown', function (e) {
  if (e.target.closest('.resize-handle')) return;  // 리사이즈 핸들이면 무시
  // ... 드래그 시작
});

// initResize에서:
handle.addEventListener('mousedown', function (e) {
  e.stopPropagation();  // 블록의 mousedown으로 전파 방지
  // ... 리사이즈 시작
});
```

> **이중 보호:** 리사이즈 핸들에서 mousedown이 발생하면
> (1) `initBlockMove`가 `.resize-handle` 체크로 무시하고,
> (2) `initResize`가 `stopPropagation()`으로 이벤트 전파를 차단한다.

### 6.2 큐 복귀 버튼 vs 블록 드래그

```javascript
// initReturnToQueue에서:
btn.addEventListener('mousedown', function (e) {
  e.stopPropagation();  // 블록 드래그 방지
});
btn.addEventListener('click', function (e) {
  e.stopPropagation();
  e.preventDefault();
  // ... API 호출
});
```

### 6.3 클릭 vs 드래그 구분

```javascript
// startDrag에서:
if (!dragging && Math.abs(dx) + Math.abs(dy) < 5) return;
// 5px 미만 이동은 클릭으로 간주, 드래그 시작 안 함
```

### 6.4 우클릭 vs 드래그

```javascript
// startDrag에서:
if (e.button !== 0) return;  // 좌클릭(0)이 아니면 무시
// 우클릭(2)은 initContextMenu에서 처리
```

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
    └── 내보내기 → GET /api/export?start_date=...&end_date=...&format=...
    │
    ▼
[api() 함수]
    │
    ├── fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON })
    │
    ├── 응답 처리:
    │   ├── r.ok === true:
    │   │   └── r.json() → Promise 반환 (호출부에서 .then()으로 처리)
    │   │
    │   └── r.ok === false:
    │       └── r.json() → j.error 추출 → throw new Error(j.error)
    │           → 호출부의 .catch()에서 showToast(err.message, 'danger')
    │
    ▼
[성공 후 처리]
    │
    ├── 대부분: location.reload() (즉시 새로고침)
    └── 초안 제어: showToast → setTimeout(500) → location.reload()
```

**새로고침 방식의 장점:**
- 클라이언트 상태 관리 불필요
- 서버와 항상 동기화
- 겹침 감지, remaining_hours 재계산 등 복잡한 로직을 서버에서만 처리

**단점:**
- 매 조작마다 전체 페이지 로드 (네트워크 비용)
- 스크롤 위치, 큐 정렬 상태 등 UI 상태 초기화

---

## 8. 읽기 전용 모드

`base.html`에서 `localStorage.getItem('scheduleMode')`를 확인하여
`body`에 `readonly-mode` 클래스를 추가/제거한다.

**CSS 효과:**
```css
.readonly-mode .schedule-block { cursor: default; }           /* 드래그 커서 제거 */
.readonly-mode .resize-handle { display: none; }               /* 리사이즈 핸들 숨김 */
.readonly-mode .btn-to-queue { display: none; }                /* 큐 복귀 버튼 숨김 */
.readonly-mode .queue-task-item { cursor: default; }           /* 큐 드래그 비활성 */
.readonly-mode .month-block-item { cursor: default; }          /* 월간 블록 커서 */
.readonly-mode .schedule-nav .ms-auto { display: none !important; }  /* 초안 제어 버튼 전체 숨김 */
```

**JS 효과:** `isReadonly()` 체크로 드래그/리사이즈/컨텍스트 메뉴/큐 복귀를 조기 반환:
```javascript
function isReadonly() {
  return document.body.classList.contains('readonly-mode');
}
// startDrag, initResize, initContextMenu, initReturnToQueue에서 사용
```
