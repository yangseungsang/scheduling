# Frontend 아키텍처 문서

## 1. 개요

Jinja2 SSR + Bootstrap 5 + 바닐라 JavaScript. 모듈 번들러 없이 `window.ScheduleApp` 네임스페이스로 10개 JS 모듈 관리.

---

## 2. JS 모듈 구조

`schedule/static/js/` 디렉토리, 로드 순서 중요:

```
{% block scripts %}     ← 뷰별 설정 (SCHEDULE_BREAKS, GRID_INTERVAL)
utils.js                ← 상수, API, 시간 헬퍼, showToast, isReadonly
modals.js               ← showConfirmModal, openMemoModal
drag-core.js            ← startDrag, findTarget, ghost, highlight, 장소 가이드
block-move.js           ← initBlockMove, initMonthBlockMove
block-resize.js         ← initResize (축소 경고 모달)
queue-drag.js           ← initQueueDrag, showIdentifierPicker
context-menu.js         ← initContextMenu, showSplitPicker (우클릭 메뉴)
block-detail.js         ← showTaskDetailPopup, initBlockDetail (더블클릭 팝업)
schedule-features.js    ← 주말토글, 일정이동, 블록추가, 큐검색, 큐토글, hover링크, 큐복귀
schedule-app.js         ← DOMContentLoaded 진입점
```

### 네임스페이스
```javascript
window.ScheduleApp = window.ScheduleApp || {};
(function(App) {
  // 함수 정의 후 App에 등록
  App.initBlockMove = initBlockMove;
})(window.ScheduleApp);
```

### 전역 설정 (뷰 템플릿에서 주입)
```javascript
window.SCHEDULE_BREAKS = [{start: '12:00', end: '13:00'}, ...];
window.GRID_INTERVAL = 10;  // settings.grid_interval_minutes
```

`{% block scripts %}`가 JS 모듈들보다 **먼저** 로드됨 → `utils.js`에서 `App.GRID_MINUTES = window.GRID_INTERVAL || 15` 올바르게 설정.

---

## 3. 드래그앤드롭 흐름

### 큐→시간표 (queue-drag.js)
1. `.queue-task-item` mousedown → `startDrag()`
2. 식별자 2개 이상이면 `/schedule/api/blocks/by-task/` 조회
3. `showIdentifierPicker()` — 배치됨 식별자 비활성, 선택
4. `POST /schedule/api/blocks` (identifier_ids 포함)
5. 기존 블록에서 겹치는 식별자 자동 제거 (백엔드)
6. `location.reload()`

### 블록 이동 (block-move.js)
1. `.schedule-block` mousedown → `startDrag()`
2. 고스트: `block.offsetHeight` (리사이즈 후 실제 크기 반영)
3. 드롭: 큐(DELETE ?restore=1) / 슬롯(PUT) / 월간(PUT date only)

### 블록 리사이즈 (block-resize.js)
1. `.resize-handle` mousedown → 드래그
2. `SLOT_HEIGHT` 단위 스냅
3. 축소 시 `showConfirmModal()` — 현재 크기와 비교
4. `PUT /schedule/api/blocks/<id>` resize:true
5. remaining 변경 없음 (리사이즈 = 실제 시간 변경)

### 우클릭 메뉴 (context-menu.js)
- 상태 변경 (pending/in_progress/completed/cancelled)
- 메모 편집
- 분리 (`showSplitPicker` — 체크 유지=남김, 해제=큐로)
- 큐로 보내기, 잠금 토글, 삭제

### 상세 팝업 (block-detail.js)
- 더블클릭 → `showTaskDetailPopup()`
- 식별자 테이블: ID, 시간, 작성자, 배치일
- 합계 시간 + 기준 시간(식별자 합) 표시
- 메모 편집 + 저장

---

## 4. 장소 필터 (_location_filter.html)

- 복수 선택 가능 (토글 방식)
- "전체" 버튼: 개별 모두 해제, 전체만 활성
- 개별 클릭: 전체 해제, 해당 장소 토글
- 모두 해제 → 자동으로 전체 모드
- 상태 localStorage에 저장 (드래그 후 리로드에도 유지)
- 활성: 장소 고유 색상 배경 (pill 형태), 비활성: 회색+취소선
- 드래그 시 필터된 장소만 가이드에 표시

---

## 5. 큐 (_task_queue.html)

카드 표시:
- 왼쪽 색상 띠: 장소 색상 (간단 블록은 회색)
- 장절명 (메인 타이틀)
- 남은: X분 / 전체: Y분
- 간단 블록은 "준비" 뱃지

버튼:
- "시험 추가" → `/tasks/new` 폼 이동
- "블록 추가" → 간단 블록 팝업 (제목+시간 → 큐에 추가)

---

## 6. 시간표 블록 표시

- 배경색: 장소 색상
- 제목: 장절명
- 분할 블록: `2/5` 뱃지 표시
- 시간: `09:00–10:00`
- 상태 뱃지: 진행/완료/불가
- 메모/잠금 아이콘

---

## 7. 시험항목 목록 (tasks/list.html)

테이블 열: 장절명, 담당자, 장소, 시간, 상태, 배치
- 배치 칩 클릭 → 블록 상세 드롭다운 (날짜/시간/장소/식별자)
- 분할 시 "분할 (N건)" 주황색 뱃지

---

## 8. 시험항목 상세 (tasks/detail.html)

- 장절명 (타이틀)
- 식별자 테이블: ID, 시간, 작성자, 배치일 (링크)
- 예상 시간 (잔여)
- 시험장소, 시험 담당자, 버전, 상태, 메모

---

## 9. 시험항목 폼 (tasks/form.html)

필드 순서:
1. 장절명 (필수)
2. 절차서 담당자 (hidden)
3. 식별자 동적 테이블 (ID, 작성자, 예상시간 + 합계)
4. 버전, 장소
5. 시험 담당자 (복수 선택 + 칩)
6. 잔여시간, 상태 (수정 시)
7. 메모

---

## 10. CSS (style.css)

`:root` CSS 변수로 디자인 토큰 관리:
```css
:root {
  --color-text: #1e293b;
  --color-text-muted: #64748b;
  --color-text-light: #94a3b8;
  --color-bg: #f5f6f8;
  --color-bg-light: #f8f9fa;
  --color-border: #e2e8f0;
  --color-primary: #0d6efd;
  --color-success: #28a745;
  --color-danger: #dc3545;
}
```

---

## 11. 템플릿 구조

```
base.html
├── schedule/day.html, week.html, month.html
│   └── _task_queue.html, _version_selector.html, _location_filter.html
├── tasks/list.html, form.html, detail.html
└── admin/settings.html, users.html, locations.html, versions.html + forms
```

스크립트 로드 순서:
1. bootstrap.bundle.min.js
2. `{% block scripts %}` — 뷰별 SCHEDULE_BREAKS, GRID_INTERVAL 설정
3. utils.js → modals.js → drag-core.js → ... → schedule-app.js
