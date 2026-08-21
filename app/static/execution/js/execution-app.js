'use strict';

/**
 * execution-app.js — 시험 실행 목록 화면 컨트롤러
 *
 * 역할:
 *   - 전체 시험 항목 목록을 테이블로 표시하고 필터·정렬·검색을 제공한다.
 *   - 열 가시성을 localStorage에 저장해 사용자별 맞춤 설정을 유지한다.
 *   - 바코드 스캐너 입력으로 특정 시험 항목 상세 페이지로 바로 이동한다.
 *
 * 의존성:
 *   - Bootstrap 5 (Tooltip)
 *   - Bootstrap Icons
 *   - 전역 변수 BARCODE_PREFIX (Jinja2 템플릿이 인라인으로 주입, 없을 수 있음)
 *
 * 데이터 흐름:
 *   loadList() → apiFetch('/api/list') → _allItems 저장
 *     → renderStatusSummary()      (상태 요약 바 갱신)
 *     → applyAndRender()           (필터·정렬 적용)
 *       → refreshTableHeader()     (정렬 아이콘 포함 헤더 재생성)
 *       → renderTable(items)       (tbody 행 재생성)
 */

// ── 전역 상태 ─────────────────────────────────────────────────────────────────

/** 서버에서 받아온 전체 시험 항목 배열. 필터·정렬의 원본 데이터. */
let _allItems = [];

/**
 * 현재 정렬 중인 열 키. null이면 정렬 없음.
 * 가능한 값: 'location' | 'scheduled_time' | 'actual_time' | 'status'
 */
let _sortCol = null;

/** 정렬 방향. 'asc' 또는 'desc'. */
let _sortDir = 'asc';

/**
 * 상태 정렬 순서 정의.
 * 상태(status) → 한글 레이블 매핑.
 * 정렬 순서는 서버가 내려주는 status_order를 사용한다.
 */
const STATUS_CFG = {
  pending: '대기',
  in_progress: '진행 중',
  paused: '일시정지',
  completed: '완료',
};

const FILTER_CFG = {
  doc: {
    label: '문서',
    values: item => [{ value: item.procedure_id, label: item.display_name || item.document_name || item.procedure_id }],
  },
  test_item: {
    label: '시험 식별자',
    values: item => [{ value: item.test_item_id, label: item.test_item_id }],
  },
  name: {
    label: '시험 항목',
    values: item => [{ value: item.test_item_name, label: item.test_item_name || '-' }],
  },
  assignee: {
    label: '작성자',
    values: item => (item.owners || []).map(name => ({ value: name, label: name })),
  },
  location: {
    label: '장소',
    values: item => [{ value: item.location_name || '-', label: item.location_name || '-' }],
  },
  date: {
    label: '날짜',
    values: item => {
      const values = [];
      if (item.scheduled_date) values.push({ value: item.scheduled_date, label: item.scheduled_date });
      const actualDate = actualStartDate(item);
      if (actualDate) values.push({ value: actualDate, label: actualDate });
      return values;
    },
  },
  performer: {
    label: '수행자',
    values: item => [{ value: item.performer_name || '-', label: item.performer_name || '-' }],
  },
  status: {
    label: '상태',
    values: item => {
      const status = item.execution_status || 'pending';
      return [{ value: status, label: STATUS_CFG[status] || status }];
    },
  },
};

const _columnFilters = Object.keys(FILTER_CFG).reduce((acc, key) => {
  acc[key] = [];
  return acc;
}, {});

// ── 열 정의 및 가시성 ─────────────────────────────────────────────────────────

/**
 * 테이블 열 정의 배열.
 *
 * 이 배열이 열 순서·레이블·가시성 토글 메뉴의 단일 소스다.
 * buildTableHeader()와 buildRow()는 이 배열을 순서대로 순회하며
 * colVisible(key)가 true인 열만 포함한다.
 *
 * sortable 여부는 buildTableHeader() 내부에서 하드코딩으로 처리하며,
 * 현재 location·scheduled_time·actual_time·status 열의 정렬을 지원한다.
 */
const COL_DEFS = [
  { key: 'doc',        label: '문서' },
  { key: 'test_item', label: '시험 항목' },
  { key: 'name',       label: '시험항목' },
  { key: 'assignee',   label: '작성자' },
  { key: 'location',   label: '장소' },
  { key: 'scheduled_time', label: '예정 날짜(시간)' },
  { key: 'actual_time',    label: '실제 수행 날짜(시간)' },
  { key: 'estimated',  label: '예상시간' },
  { key: 'performer',  label: '수행자' },
  { key: 'result',     label: '결과' },
  { key: 'status',     label: '상태' },
];

/**
 * localStorage에서 열 가시성 맵을 불러온다.
 * 저장된 값이 없거나 파싱 실패 시 빈 객체를 반환한다.
 * 키가 없는 열은 기본적으로 보이는 것으로 간주한다(colVisible 참고).
 */
function loadColVis() {
  try { return JSON.parse(localStorage.getItem('execColVis') || 'null') || {}; }
  catch { return {}; }
}

/** 열 가시성 맵을 localStorage('execColVis')에 저장한다. */
function saveColVis(vis) { localStorage.setItem('execColVis', JSON.stringify(vis)); }

/**
 * 특정 열이 현재 보이는 상태인지 반환한다.
 * vis[key]가 명시적으로 false일 때만 숨김 처리하고, 그 외(undefined 포함)는 true.
 */
function colVisible(key) { return loadColVis()[key] !== false; }

// ── 유틸 ──────────────────────────────────────────────────────────────────────

/** 초를 HH:MM:SS 문자열로 변환한다. */
function formatElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

/** 분(mins)을 "N분" 형태로 반환한다. 값이 없으면 '-'. */
function formatMinutes(mins) {
  if (!mins) return '-';
  return `${mins}분`;
}

/** 날짜와 시간 구간을 두 줄로 표시한다. */
function renderDateTimeCell(date, time) {
  if (!date) return '-';
  return `<span class="datetime-date">${escHtml(date)}</span>` +
    (time ? `<span class="datetime-time">${escHtml(time)}</span>` : '');
}

/** 일정 블록의 예정 날짜와 시작·종료 시각을 표시한다. */
function renderScheduledPeriod(item) {
  const start = item.scheduled_start_time || '';
  const end = item.scheduled_end_time ? `–${item.scheduled_end_time}` : '';
  return renderDateTimeCell(item.scheduled_date, `${start}${end}`);
}

/** 실제 실행 구간의 최초 시작과 최종 종료 시각을 표시한다. */
function renderActualPeriod(item) {
  if (!item.actual_start_at) return '-';
  const start = String(item.actual_start_at).replace('T', ' ');
  const startDate = start.slice(0, 10);
  const startTime = start.slice(11, 16);
  if (!item.actual_end_at) {
    const suffix = item.execution_status === 'in_progress' ? '–진행 중' : '';
    return renderDateTimeCell(startDate, `${startTime}${suffix}`);
  }
  const end = String(item.actual_end_at).replace('T', ' ');
  const endTime = end.slice(0, 10) === startDate
    ? end.slice(11, 16)
    : `${end.slice(0, 10)} ${end.slice(11, 16)}`;
  return renderDateTimeCell(startDate, `${startTime}–${endTime}`);
}

function actualStartDate(item) {
  return item.actual_start_at ? String(item.actual_start_at).replace('T', ' ').slice(0, 10) : '';
}

/** HTML 특수문자를 엔티티로 이스케이프한다. XSS 방지용. */
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** JSON API 요청 공통 래퍼. 오류 시 Error를 throw한다. */
async function apiFetch(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}


// ── 열 토글 메뉴 ──────────────────────────────────────────────────────────────

/**
 * 드롭다운 열 토글 메뉴를 렌더링한다.
 *
 * COL_DEFS를 순회하며 체크박스 항목을 생성한다.
 * 현재 가시성 상태를 checked 속성에 반영하고,
 * 변경 시 toggleCol()을 호출한다.
 */
function renderColMenu() {
  const menu = document.getElementById('col-toggle-menu');
  if (!menu) return;
  const vis = loadColVis();
  menu.innerHTML = COL_DEFS.map(col => {
    const checked = vis[col.key] !== false ? 'checked' : '';
    return `<li><label class="dropdown-item d-flex gap-2 align-items-center" style="cursor:pointer">
      <input type="checkbox" ${checked} onchange="toggleCol('${col.key}', this.checked)"> ${col.label}
    </label></li>`;
  }).join('');
}

/**
 * 열 가시성을 토글하고 메뉴·테이블을 즉시 갱신한다.
 * localStorage에 변경 사항을 저장하므로 새로고침 후에도 유지된다.
 */
function toggleCol(key, visible) {
  const vis = loadColVis();
  vis[key] = visible;
  saveColVis(vis);
  renderColMenu();
  applyAndRender();
}

function columnFilterButton(filterKey) {
  const cfg = FILTER_CFG[filterKey];
  const selected = _columnFilters[filterKey] || [];
  const active = selected.length ? ' active' : '';
  const count = selected.length > 1 ? `<span class="column-filter-count">${selected.length}</span>` : '';
  return `<button type="button" class="column-filter-btn${active}" ` +
    `data-filter-key="${filterKey}" data-filter-label="${cfg.label}" ` +
    `title="${cfg.label} 필터"><i class="bi bi-funnel-fill"></i>${count}</button>`;
}

function closeColumnFilter() {
  document.getElementById('column-filter-menu')?.remove();
}

function uniqueFilterOptions(filterKey) {
  const cfg = FILTER_CFG[filterKey];
  const byValue = new Map();
  _allItems.forEach(item => {
    cfg.values(item).forEach(option => {
      if (!option.value || byValue.has(option.value)) return;
      byValue.set(option.value, option.label || option.value);
    });
  });
  return Array.from(byValue, ([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ko'));
}

function renderFilterOptions(menu, filterKey, query = '') {
  const selected = menu._selectedValues || new Set(_columnFilters[filterKey]);
  const normalized = query.trim().toLowerCase();
  const list = menu.querySelector('.column-filter-options');
  const options = uniqueFilterOptions(filterKey).filter(option =>
    !normalized ||
    option.label.toLowerCase().includes(normalized) ||
    option.value.toLowerCase().includes(normalized));
  if (!options.length) {
    list.innerHTML = '<div class="column-filter-empty">항목 없음</div>';
    return;
  }
  list.innerHTML = '';
  options.forEach(option => {
    const item = document.createElement('label');
    item.className = 'column-filter-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = option.value;
    checkbox.checked = selected.has(option.value);
    const text = document.createElement('span');
    text.textContent = option.label;
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selected.add(option.value);
      else selected.delete(option.value);
      menu._selectedValues = selected;
    });
    item.append(checkbox, text);
    list.appendChild(item);
  });
}

function selectedFilterValues(menu) {
  return Array.from(menu._selectedValues || []);
}

/** 현재 목록 데이터에서 고유값을 수집해 검색 가능한 헤더 필터 메뉴를 연다. */
function openColumnFilter(button) {
  closeColumnFilter();
  const filterKey = button.dataset.filterKey;
  if (!FILTER_CFG[filterKey]) return;
  const menu = document.createElement('div');
  menu.id = 'column-filter-menu';
  menu.className = 'exec-column-filter-menu';
  menu._selectedValues = new Set(_columnFilters[filterKey]);
  const title = document.createElement('div');
  title.className = 'column-filter-title';
  title.textContent = button.dataset.filterLabel;
  menu.appendChild(title);
  const search = document.createElement('input');
  search.type = 'search';
  search.className = 'column-filter-search';
  search.placeholder = '검색';
  menu.appendChild(search);
  const optionList = document.createElement('div');
  optionList.className = 'column-filter-options';
  menu.appendChild(optionList);
  const actions = document.createElement('div');
  actions.className = 'column-filter-actions';
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'btn btn-sm btn-outline-secondary';
  clear.textContent = '전체';
  clear.addEventListener('click', () => {
    _columnFilters[filterKey] = [];
    closeColumnFilter();
    applyAndRender();
  });
  const apply = document.createElement('button');
  apply.type = 'button';
  apply.className = 'btn btn-sm btn-primary';
  apply.textContent = '적용';
  apply.addEventListener('click', () => {
    _columnFilters[filterKey] = selectedFilterValues(menu);
    closeColumnFilter();
    applyAndRender();
  });
  actions.append(clear, apply);
  menu.appendChild(actions);
  document.body.appendChild(menu);
  renderFilterOptions(menu, filterKey);
  search.addEventListener('input', () => renderFilterOptions(menu, filterKey, search.value));
  search.focus();
  const rect = button.getBoundingClientRect();
  const left = Math.min(rect.left, window.innerWidth - menu.offsetWidth - 12);
  menu.style.left = `${Math.max(12, left)}px`;
  menu.style.top = `${rect.bottom + 6}px`;
}

// ── 테이블 헤더 렌더링 ────────────────────────────────────────────────────────

/**
 * 현재 가시 열 기준으로 <th> 문자열을 생성해 반환한다.
 *
 * sortable 열(location·scheduled_time·actual_time·status)은 정렬 속성을 포함한다.
 * 정렬 핸들러는 refreshTableHeader()에서 별도로 등록한다.
 */
function buildTableHeader() {
  const cols = [];
  if (colVisible('doc'))        cols.push(`<th style="width:250px">문서 ${columnFilterButton('doc')}</th>`);
  if (colVisible('test_item')) cols.push(`<th style="width:180px">시험 식별자 ${columnFilterButton('test_item')}</th>`);
  if (colVisible('name'))       cols.push(`<th>시험 항목 ${columnFilterButton('name')}</th>`);
  if (colVisible('assignee'))   cols.push(`<th style="width:100px">작성자 ${columnFilterButton('assignee')}</th>`);
  if (colVisible('location'))   cols.push(`<th class="sortable" data-sort="location" style="width:90px">장소 <i class="bi bi-arrow-down-up ms-1 text-muted"></i> ${columnFilterButton('location')}</th>`);
  if (colVisible('scheduled_time')) cols.push(`<th class="sortable" data-sort="scheduled_time" style="width:135px">예정 날짜(시간) <i class="bi bi-arrow-down-up ms-1 text-muted"></i> ${columnFilterButton('date')}</th>`);
  if (colVisible('actual_time')) cols.push(`<th class="sortable" data-sort="actual_time" style="width:150px">실제 수행 날짜(시간) <i class="bi bi-arrow-down-up ms-1 text-muted"></i> ${columnFilterButton('date')}</th>`);
  if (colVisible('estimated'))  cols.push('<th style="width:75px">예상 시간</th>');
  if (colVisible('performer'))  cols.push(`<th style="width:80px">수행자 ${columnFilterButton('performer')}</th>`);
  if (colVisible('result'))     cols.push('<th style="width:130px">결과</th>');
  if (colVisible('status'))     cols.push(`<th class="sortable" data-sort="status" style="width:120px">상태 <i class="bi bi-arrow-down-up ms-1 text-muted"></i> ${columnFilterButton('status')}</th>`);
  return cols.join('');
}

/**
 * 테이블 헤더를 재생성하고 정렬 핸들러를 재연결한다.
 *
 * buildTableHeader()로 DOM을 교체한 뒤:
 *   1. 현재 정렬 열(_sortCol)의 아이콘을 올바른 방향으로 복원한다.
 *   2. sortable <th>에 click 이벤트를 새로 등록한다.
 *      (innerHTML 교체 후 기존 핸들러가 사라지므로 매번 재등록 필요)
 */
function refreshTableHeader() {
  const thead = document.querySelector('.exec-table thead tr');
  if (!thead) return;
  thead.innerHTML = buildTableHeader();
  // 정렬 아이콘 현재 상태 복원
  if (_sortCol) {
    const th = thead.querySelector(`th[data-sort="${_sortCol}"]`);
    if (th) {
      const icon = th.querySelector('i');
      if (icon) icon.className = `bi ms-1 ${_sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'}`;
    }
  }
  // 정렬 클릭 이벤트 재등록
  thead.querySelectorAll('th[data-sort]').forEach(th =>
    th.addEventListener('click', () => setSort(th.dataset.sort)));
  thead.querySelectorAll('.column-filter-btn').forEach(button =>
    button.addEventListener('click', event => {
      event.stopPropagation();
      openColumnFilter(button);
    }));
}

// ── 리스트 로드 ───────────────────────────────────────────────────────────────

/**
 * 서버에서 시험 항목 목록을 가져와 _allItems에 저장한 뒤 화면을 갱신한다.
 *
 * 날짜·장소 필터 값을 쿼리 파라미터로 전달한다.
 * 로딩 중에는 스피너가 포함된 로딩 행을 표시한다.
 * 로드 성공 후: renderStatusSummary() + applyAndRender() 호출
 * 로드 실패 시: 오류 메시지 행 표시
 */
async function loadList() {
  // 가시 열 수만큼 colspan을 설정해 로딩 행이 전체 너비를 차지하게 한다.
  const visibleCount = COL_DEFS.filter(c => colVisible(c.key)).length;
  document.getElementById('exec-tbody').innerHTML =
    `<tr><td colspan="${visibleCount}" class="text-center text-muted py-5"><div class="spinner-border spinner-border-sm me-2"></div>로딩 중…</td></tr>`;

  try {
    _allItems = await apiFetch('/execution/api/list');
    renderStatusSummary();
    applyAndRender();
  } catch {
    const visibleCount2 = COL_DEFS.filter(c => colVisible(c.key)).length;
    document.getElementById('exec-tbody').innerHTML =
      `<tr><td colspan="${visibleCount2}" class="text-center text-danger py-4"><i class="bi bi-exclamation-circle me-2"></i>로드 실패</td></tr>`;
  }
}


// ── 정렬 ──────────────────────────────────────────────────────────────────────

/**
 * 정렬 열을 설정하고 테이블을 재렌더링한다.
 *
 * 같은 열을 다시 클릭하면 asc ↔ desc를 토글한다.
 * 다른 열을 클릭하면 항상 asc로 초기화한다.
 * 모든 sortable <th>의 아이콘을 현재 상태에 맞게 갱신한다.
 */
function setSort(col) {
  _sortDir = _sortCol === col ? (_sortDir === 'asc' ? 'desc' : 'asc') : 'asc';
  _sortCol = col;
  document.querySelectorAll('th[data-sort]').forEach(th => {
    const icon = th.querySelector('i');
    icon.className = th.dataset.sort === _sortCol
      ? `bi ms-1 ${_sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'}`
      : 'bi bi-arrow-down-up ms-1 text-muted';
  });
  applyAndRender();
}

// ── 필터 + 정렬 → 렌더 ───────────────────────────────────────────────────────

/**
 * _allItems에 컬럼 필터와 정렬을 적용한 뒤 renderTable()을 호출한다.
 *
 * 필터:
 *   - 각 헤더 필터에서 선택한 값과 행 값을 비교한다.
 *   - 날짜 필터는 예정 날짜와 실제 수행 시작 날짜에 함께 적용한다.
 *
 * 정렬:
 *   - 'scheduled_time': 예정 날짜와 시작 시각 비교
 *   - 'actual_time': 실제 수행 시작 시각 비교
 *   - 'location': location_name 문자열 비교
 *   - 'status': 서버가 내려준 status_order 숫자 비교
 */
function applyAndRender() {
  let items = [..._allItems];
  items = items.filter(item => Object.entries(_columnFilters).every(([key, selected]) => {
    if (!selected.length) return true;
    const selectedSet = new Set(selected);
    return FILTER_CFG[key].values(item).some(option => selectedSet.has(option.value));
  }));
  if (_sortCol) {
    items.sort((a, b) => {
      let va, vb;
      if (_sortCol === 'scheduled_time') {
        va = `${a.scheduled_date || ''} ${a.scheduled_start_time || ''}`;
        vb = `${b.scheduled_date || ''} ${b.scheduled_start_time || ''}`;
      }
      else if (_sortCol === 'actual_time') { va = a.actual_start_at || ''; vb = b.actual_start_at || ''; }
      else if (_sortCol === 'location') { va = a.location_name || ''; vb = b.location_name || ''; }
      else if (_sortCol === 'status')   {
        va = a.status_order ?? 0;
        vb = b.status_order ?? 0;
      }
      return (va < vb ? -1 : va > vb ? 1 : 0) * (_sortDir === 'asc' ? 1 : -1);
    });
  }
  refreshTableHeader();
  renderTable(items);
}

// ── 테이블 렌더링 ─────────────────────────────────────────────────────────────

/**
 * 상태별 색상 dot + 한글 텍스트 배지를 반환한다.
 * execution이 없는 항목은 pending으로 간주한다.
 */
function statusBadge(item) {
  const s = item.execution_status || 'pending';
  return `<span class="exec-badge exec-badge-${s}"><span class="exec-badge-dot"></span>${STATUS_CFG[s] || '-'}</span>`;
}

/**
 * 코멘트가 있으면 Bootstrap tooltip이 포함된 💬 아이콘 span을 반환한다.
 * 없으면 빈 문자열을 반환해 아이콘이 표시되지 않는다.
 *
 * 줄바꿈은 &#10;로 변환해 tooltip 내에서 여러 줄로 표시되게 한다.
 * (Bootstrap tooltip은 기본적으로 HTML을 허용하지 않으므로 개행 문자 사용)
 */
function renderCommentIcon(item) {
  const comment = item.execution_comment || '';
  if (!comment) return '';
  const escaped = escHtml(comment).replace(/\n/g, '&#10;');
  return ` <span data-bs-toggle="tooltip" data-bs-placement="top" title="${escaped}" style="cursor:default">💬</span>`;
}

/**
 * 결과 셀(F/B/P/총)을 반환한다.
 *
 * execution이 없어도 항목의 total_count는 고정값이므로 표시한다.
 * 미완료 상태의 F/B/P는 저장된 값이 없으면 0으로 보여준다.
 */
function renderResultCell(item) {
  const result = item.result_counts || {};
  const f = result.fail_count ?? 0;
  const b = result.block_count ?? 0;
  const p = result.pass_count ?? 0;
  const t = result.total_count ?? item.total_count ?? 0;
  return `<td><span class="text-danger">F:${f}</span> <span class="text-warning">B:${b}</span> <span class="text-success">P:${p}</span> <span class="text-muted">/ ${t}</span></td>`;
}

/**
 * 상태 요약 바를 렌더링한다.
 *
 * _allItems 전체를 상태별로 집계해 #status-summary 요소에 표시한다.
 * loadList() 성공 후 한 번만 호출되므로 필터·정렬의 영향을 받지 않는다.
 * (필터 후 건수가 아닌 전체 건수를 보여주는 것이 의도된 동작)
 */
function renderStatusSummary() {
  const el = document.getElementById('status-summary');
  if (!el) return;
  const counts = { pending: 0, in_progress: 0, paused: 0, completed: 0 };
  _allItems.forEach(item => {
    const s = item.execution_status || 'pending';
    if (counts.hasOwnProperty(s)) counts[s]++;
  });
  const total = _allItems.length;
  el.innerHTML = `
    <span class="exec-summary-item">전체 <strong>${total}</strong></span>
    <span class="exec-summary-item summary-pending">대기 <strong>${counts.pending}</strong></span>
    <span class="exec-summary-item summary-in_progress">진행 중 <strong>${counts.in_progress}</strong></span>
    <span class="exec-summary-item summary-paused">일시정지 <strong>${counts.paused}</strong></span>
    <span class="exec-summary-item summary-completed">완료 <strong>${counts.completed}</strong></span>`;
}

/**
 * 단일 항목의 <tr> HTML 문자열을 반환한다.
 *
 * COL_DEFS 순서대로 colVisible()을 확인하며 조건부로 <td>를 포함한다.
 * data-item 속성에 항목 전체를 JSON으로 저장해,
 * 클릭 핸들러에서 별도 조회 없이 즉시 데이터를 꺼낼 수 있게 한다.
 *
 * 'name' 열에는 renderCommentIcon()으로 코멘트 아이콘을 추가한다.
 */
function buildRow(item) {
  const owners = (item.owners || []).join(', ') || '-';
  const status = item.execution_status || 'pending';
  const cells = [];
  if (colVisible('doc'))        cells.push(`<td class="td-doc">${escHtml(item.display_name || item.document_name || '-')}</td>`);
  if (colVisible('test_item')) cells.push(`<td class="td-id">${escHtml(item.test_item_id)}</td>`);
  if (colVisible('name'))       cells.push(`<td class="td-name">${escHtml(item.test_item_name)}${renderCommentIcon(item)}</td>`);
  if (colVisible('assignee'))   cells.push(`<td class="td-meta">${escHtml(owners)}</td>`);
  if (colVisible('location'))   cells.push(`<td class="td-meta">${escHtml(item.location_name || '-')}</td>`);
  if (colVisible('scheduled_time')) cells.push(`<td class="td-meta td-datetime">${renderScheduledPeriod(item)}</td>`);
  if (colVisible('actual_time')) cells.push(`<td class="td-meta td-datetime">${renderActualPeriod(item)}</td>`);
  if (colVisible('estimated'))  cells.push(`<td class="td-meta">${formatMinutes(item.estimated_minutes)}</td>`);
  if (colVisible('performer'))  cells.push(`<td>${escHtml(item.performer_name || '-')}</td>`);
  if (colVisible('result'))     cells.push(renderResultCell(item));
  if (colVisible('status'))     cells.push(`<td>${statusBadge(item)}</td>`);
  return `<tr data-id="${escHtml(item.test_item_id)}" data-status="${escHtml(status)}"
      data-item='${escHtml(JSON.stringify(item))}'>${cells.join('')}</tr>`;
}

/**
 * items 배열로 tbody를 완전히 교체한다.
 *
 * - 건수를 #item-count 요소에 표시한다.
 * - 항목이 없으면 "항목 없음" 행을 표시한다.
 * - 각 행에 click 핸들러를 등록해 상세 페이지로 이동하게 한다.
 * - data-bs-toggle="tooltip" 요소에 Bootstrap Tooltip을 초기화한다.
 *   (innerHTML 교체마다 재초기화 필요)
 */
function renderTable(items) {
  const tbody = document.getElementById('exec-tbody');
  const countEl = document.getElementById('item-count');
  if (countEl) countEl.textContent = items.length ? `${items.length}건` : '';

  const visibleCount = COL_DEFS.filter(c => colVisible(c.key)).length;

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="${visibleCount}" class="text-center text-muted py-5">항목 없음</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(buildRow).join('');

  tbody.querySelectorAll('tr').forEach(tr =>
    tr.addEventListener('click', () => {
      const item = JSON.parse(tr.dataset.item);
      const procedureParam = item.procedure_id ? `?procedure_id=${encodeURIComponent(item.procedure_id)}` : '';
      window.location.href = `/execution/${encodeURIComponent(item.test_item_id)}${procedureParam}`;
    }));

  // 코멘트 아이콘(💬)의 Bootstrap Tooltip 초기화
  tbody.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    bootstrap.Tooltip.getOrCreateInstance(el);
  });
}

// ── 바코드 스캐너 ─────────────────────────────────────────────────────────────

/**
 * 바코드 스캐너 입력을 감지하는 공통 유틸.
 * 80ms 이내 연속 대문자·숫자·하이픈(-) 입력 후 Enter → 바코드로 판단한다.
 *
 * 동작 원리:
 *   - keydown 이벤트를 리스닝하며, textarea/input 포커스 시에는 스킵한다.
 *   - 각 글자가 80ms 이내에 입력되면 buf에 누적하고,
 *     80ms를 초과하면 타이머가 buf를 초기화해 일반 키보드 입력을 무시한다.
 *   - Enter 키가 오면 누적된 buf를 onScan 콜백에 전달한다.
 *
 * 목록 화면에서는 OPEN 명령만 처리한다 (TERMINATE는 상세 화면 전용).
 */
function _initBarcodeListener(onScan) {
  let buf = '', timer = null;
  document.addEventListener('keydown', e => {
    const tag = document.activeElement.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') {
      console.log('[barcode] skipped — active element:', tag, document.activeElement.id);
      return;
    }
    if (e.key === 'Enter') {
      const code = buf.trim();
      buf = '';
      clearTimeout(timer);
      console.log('[barcode] Enter → code:', JSON.stringify(code));
      if (code) onScan(code);
      return;
    }
    if (/^[A-Z0-9-]$/.test(e.key)) {
      buf += e.key;
      clearTimeout(timer);
      // 80ms 초과 시 버퍼를 초기화해 일반 키보드 입력을 무시한다.
      timer = setTimeout(() => { buf = ''; }, 80);
    }
  });
}

/**
 * 바코드 코드에서 시험 항목 ID를 추출한다.
 * 예: BARCODE_PREFIX='', code='OPEN-TC-001' → 'TC-001'
 */
// 바코드 코드에서 시험 항목 추출: OPEN-TC-001 → TC-001
function _barcodeToId(code) {
  const parts = code.split('-');
  return (typeof BARCODE_PREFIX !== 'undefined' ? BARCODE_PREFIX : '') + parts.slice(1).join('-');
}

// ── 전체화면 ──────────────────────────────────────────────────────────────────

/** 전체화면을 토글한다. fullscreenchange 이벤트로 아이콘도 갱신된다. */
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
    document.getElementById('fullscreen-icon').className = 'bi bi-fullscreen-exit';
  } else {
    document.exitFullscreen();
    document.getElementById('fullscreen-icon').className = 'bi bi-fullscreen';
  }
}

document.addEventListener('fullscreenchange', () => {
  const icon = document.getElementById('fullscreen-icon');
  if (icon) icon.className = document.fullscreenElement ? 'bi bi-fullscreen-exit' : 'bi bi-fullscreen';
});

document.addEventListener('click', event => {
  if (!event.target.closest('#column-filter-menu, .column-filter-btn')) {
    closeColumnFilter();
  }
});

// ── 초기화 ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // 열 토글 메뉴 초기 렌더링
  renderColMenu();

  const fsBtn = document.getElementById('btn-fullscreen');
  if (fsBtn) fsBtn.addEventListener('click', toggleFullscreen);

  // 초기 목록 로드
  loadList();

  // 바코드 OPEN 명령 감지 (#78): OPEN-<시험 항목> 스캔 시 해당 상세 페이지로 이동
  _initBarcodeListener(code => {
    console.log('[barcode] onScan:', JSON.stringify(code), 'startsWith OPEN-:', code.startsWith('OPEN-'));
    if (code.startsWith('OPEN-')) {
      const testItemId = _barcodeToId(code);
      console.log('[barcode] navigating to:', testItemId);
      // autostart=1 파라미터로 이동해 상세 페이지에서 자동으로 시험을 시작한다.
      window.location.href = `/execution/${encodeURIComponent(testItemId)}?autostart=1`;
    }
  });
});
