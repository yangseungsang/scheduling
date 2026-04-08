# Backend 아키텍처 문서

## 1. 개요

Flask + Jinja2 기반 SSR 애플리케이션. JSON 파일 저장, portalocker 파일 잠금. Blueprint 3개.

---

## 2. 모델 (schedule/models/)

### BaseRepository (base.py)
모든 모델의 공통 CRUD 패턴:
- `get_all()`, `get_by_id()`, `create(data)`, `patch(item_id, **kwargs)`, `delete()`, `filter_by(**kwargs)`
- `FILENAME`, `ID_PREFIX`, `ALLOWED_FIELDS` 클래스 변수로 설정

### Task (task.py)
```
파일: tasks.json, 접두사: t_
필드: id, procedure_id, version_id, assignee_ids, location_id,
      section_name, procedure_owner, test_list, estimated_hours,
      remaining_hours, status, memo, created_at, is_simple
test_list 항목: {id, estimated_hours, owners: []}
고유 메서드: get_by_version, validate_unique_identifiers, compute_estimated_hours
```

### ScheduleBlock (schedule_block.py)
```
파일: schedule_blocks.json, 접두사: sb_
필드: id, task_id, assignee_ids, location_id, version_id,
      date, start_time, end_time, is_locked, block_status,
      memo, identifier_ids, title, is_simple
고유 메서드: get_by_date, get_by_date_range, get_by_version,
            get_by_assignee, get_by_location_and_date
```

### 기타
- **User** (users.json, `u_`): name, role, color
- **Location** (locations.json, `loc_`): name, color, description
- **Version** (versions.json, `v_`): name, description, is_active, `get_active()`
- **Settings** (settings.json): `get()`, `update(data)`

---

## 3. 라우트 (schedule/routes/)

### calendar_views.py — 뷰 렌더링
| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/schedule/` | 일간 뷰 |
| GET | `/schedule/week` | 주간 뷰 (초기 진입) |
| GET | `/schedule/month` | 월간 뷰 |
| GET | `/schedule/api/day\|week\|month` | JSON 데이터 |

### calendar_api.py — 블록 API
| 메서드 | URL | 설명 |
|--------|-----|------|
| POST | `/schedule/api/blocks` | 블록 생성 (일반/간단) |
| PUT | `/schedule/api/blocks/<id>` | 이동/리사이즈 (`resize:true` 시 remaining 불변) |
| DELETE | `/schedule/api/blocks/<id>` | 삭제 (`?restore=1` → location 초기화) |
| PUT | `/schedule/api/blocks/<id>/lock` | 잠금 토글 |
| PUT | `/schedule/api/blocks/<id>/status` | 상태 변경 |
| PUT | `/schedule/api/blocks/<id>/memo` | 메모 수정 |
| POST | `/schedule/api/simple-blocks` | 간단 블록 생성 (task 자동 생성) |
| GET | `/schedule/api/blocks/by-task/<tid>` | 태스크별 블록 조회 |
| POST | `/schedule/api/blocks/shift` | 일정 이동 (주말 건너뛰기) |
| POST | `/schedule/api/blocks/<id>/split` | 블록 분리 |
| GET | `/schedule/api/export` | CSV/Excel 내보내기 |

### calendar_helpers.py — 공통 함수
- `get_current_version_id()` — URL 파라미터 또는 활성 버전
- `sync_task_remaining_hours(task_id)` — est=test_list합, remaining=est-scheduled
- `remove_identifiers_from_other_blocks()` — 식별자 이동 시 기존 블록에서 제거/삭제
- `sync_task_status(task_id)` — 블록 상태 → 태스크 상태 연동

### tasks.py
| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/tasks/` | 목록 (버전/상태/담당자/장소/날짜 필터) |
| GET/POST | `/tasks/new` | 생성 |
| GET | `/tasks/<id>` | 상세 |
| GET/POST | `/tasks/<id>/edit` | 수정 |
| POST | `/tasks/<id>/delete` | 삭제 |
| GET | `/tasks/api/list\|<id>` | API 조회 |
| POST | `/tasks/api/create` | API 생성 |
| PUT | `/tasks/api/<id>/update` | API 수정 |
| DELETE | `/tasks/api/<id>/delete` | API 삭제 |
| GET | `/tasks/api/check-identifier` | 식별자 중복 검사 |
| GET | `/tasks/api/procedure/<pid>` | 절차서 조회 |

### admin.py
- 팀원/장소/버전/설정 CRUD (폼 + REST API)

---

## 4. 헬퍼 (schedule/helpers/)

### enrichment.py
- `enrich_blocks()` — 블록에 task/user/location 정보 결합
  - 분할 블록: 해당 식별자 시간만 estimated_hours로
  - `is_split`, `block_identifier_count`, `total_identifier_count` 계산
  - `split_status`: `'partial'`(나머지 큐에 있음) / `'split'`(전체 배치됨)
- `get_queue_tasks()` — 큐 항목
  - 분할 안 된 블록 있으면 → 큐 미표시 (리사이즈 = 실제 시간 변경)
  - 분할 블록만 있으면 → 미배치 식별자 시간을 remaining으로

### time_utils.py
- `work_minutes_in_range()`, `adjust_end_for_breaks()`, `generate_time_slots()`

### overlap.py
- `check_overlap()` — 장소+시간 충돌 감지

---

## 5. 시간 관리 규칙

| 동작 | estimated_hours | remaining | 큐 |
|------|----------------|-----------|-----|
| 리사이즈 | 불변 | 불변 | 블록 있으면 미표시 |
| 이동 | 불변 | 재계산 | 재계산 |
| 큐 복귀 | 불변 | 재계산 | 표시 |
| 분할 배치 | 불변 | - | 미배치 식별자만 |

---

## 6. 서비스 (schedule/services/)

- **export.py**: CSV/Excel 내보내기
- **procedure.py**: 절차서 조회 (mock JSON)

## 7. 데이터 저장 (store.py)

- `read_json()` / `write_json()` — portalocker 파일 잠금, .bak 백업
- `generate_id(prefix)` — UUID 기반
