# exam_no 기반 시험 차수 관리 설계

**작성일:** 2026-05-25  
**대상 기능:** std_list MySQL 연동 + exam_no 기반 태스크 분리 + 차수 표시

---

## 1. 배경 및 목표

외부 MySQL DB의 `std_list` 테이블에는 `test_info`(식별자 ID)와 `exam_no`(시험 차수)가 함께 저장된다. 같은 식별자가 `exam_no=1`, `exam_no=2`처럼 여러 차수로 등록될 수 있으며, 각 차수는 독립된 시험으로 취급되어야 한다.

**목표:**
- `std_list`에서 `exam_no` 정보를 읽어 로컬 캐시에 저장
- `(doc_id, exam_no)` 조합을 기준으로 태스크를 분리 (예: "시스템 초기화 (1차)", "시스템 초기화 (2차)")
- 시간표 블록, 실행 창, 큐 목록 모두에서 몇 번째 시험인지 표시

---

## 2. 데이터 소스 역할 분리

| 소스 | 역할 |
|------|------|
| `procedures.json` | 식별자 목록, 문서명, 소요시간 (기존 유지) |
| MySQL `std_list` | `exam_no` 정보만 추가 제공 |

`std_list`의 주요 컬럼: `id`, `test_info` (= 식별자 ID), `exam_no`, `last_updated_at`, `print_flag`, `user_id`

---

## 3. 새 파일 및 변경 파일

### 신규 파일
- `app/features/schedule/models/std_list.py` — MySQL 조회 + 캐시 R/W
- `app/features/schedule/data/std_list_cache.json` — 로컬 캐시

### 변경 파일
| 파일 | 변경 내용 |
|------|-----------|
| `requirements.txt` | `PyMySQL` 추가 |
| `app/features/schedule/models/task.py` | `exam_no` 필드 추가, `get_by_doc_and_exam()` 추가 |
| `app/features/schedule/services/sync.py` | `sync_test_data` — exam_no 기반 태스크 생성 |
| `app/features/schedule/routes/sync.py` | `/api/sync/std-list` 엔드포인트 추가 |
| `app/features/execution/models/execution.py` | `get_by_identifier_and_task()` 추가 |
| `app/features/execution/routes/api.py` | `_build_item_dict` — task_id 스코프 적용, `exam_no` 응답 포함 |
| 템플릿 / JS | "(N차)" 표시 추가 |

---

## 4. MySQL 연결 설계

### 4.1 환경변수
```
MYSQL_HOST        (기본: localhost)
MYSQL_PORT        (기본: 3306)
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DB_DEV      (FLASK_ENV != production 시 사용)
MYSQL_DB_PROD     (FLASK_ENV == production 시 사용)
```

### 4.2 `std_list.py` 인터페이스
```python
def fetch_from_mysql() -> list[dict]:
    """std_list 테이블에서 test_info, exam_no를 읽어 반환한다."""
    # SELECT test_info, exam_no FROM std_list WHERE exam_no IS NOT NULL

def load_cache() -> list[dict]:
    """로컬 캐시(std_list_cache.json)를 읽어 반환한다. 없으면 []."""

def save_cache(rows: list[dict]) -> None:
    """rows를 std_list_cache.json에 저장한다."""
```

### 4.3 캐시 구조
```json
[
  {"test_info": "TC-001", "exam_no": 1},
  {"test_info": "TC-001", "exam_no": 2},
  {"test_info": "TC-002", "exam_no": 1}
]
```

---

## 5. 동기화 설계

### 5.1 신규 엔드포인트: `POST /schedule/api/sync/std-list`
1. MySQL에 접속하여 `std_list` 조회
2. 결과를 `std_list_cache.json`에 저장
3. 성공 시 `{"cached": N}` 반환, 접속 실패 시 503

### 5.2 `sync_test_data` 수정 알고리즘

```
exam_no_map: dict[test_info → set[exam_no]] ← std_list_cache.json에서 구성

for each procedure (doc_id, identifiers) in provider:
    doc_exam_nos = union of exam_no_map.get(ident.id, {}) for ident in identifiers

    if doc_exam_nos is empty:
        # exam_no 정보 없음 → exam_no=None 태스크 1개 생성/갱신
        sync_task(doc_id, exam_no=None, identifiers=all)
    else:
        for exam_no in sorted(doc_exam_nos):
            filtered = [i for i in identifiers if exam_no in exam_no_map.get(i.id, {})]
            sync_task(doc_id, exam_no=exam_no, identifiers=filtered)

취소 처리: 이번 sync 결과에 없는 (doc_id, exam_no) 조합의 태스크를 cancelled 처리.
  - 기존 exam_no=None 태스크가 있는데 이번 sync에서 exam_no=1,2 태스크가 생성되면,
    exam_no=None 태스크는 더 이상 결과에 없으므로 자동 cancelled 처리된다.
```

### 5.3 태스크 매칭 키 변경
- 기존: `get_by_doc_id(doc_id)` — doc당 태스크 1개
- 변경: `get_by_doc_and_exam(doc_id, exam_no)` — (doc, exam_no)당 태스크 1개

---

## 6. 태스크 스키마 변경

```json
{
  "id": "t_...",
  "doc_id": 1,
  "exam_no": 1,           ← 신규 필드 (null = 기존 태스크, 하위호환)
  "doc_name": "시스템 초기화",  ← 원본명 저장 (접미사 없음)
  "identifiers": [...],   ← 해당 exam_no에 속하는 식별자만
  ...
}
```

**표시명 생성 규칙:**
- `exam_no=None` → `"시스템 초기화"` (접미사 없음)
- `exam_no=N` → `"시스템 초기화 (N차)"`
- 이 변환은 API 응답 및 프론트엔드 렌더링 시 적용

---

## 7. 식별자 중복 허용 정책

기존 `validate_unique_identifiers`는 식별자 ID의 전역 고유성을 검증한다. exam_no 도입 후:

- **sync 경로**: 동일 식별자 ID가 서로 다른 exam_no 태스크에 존재 가능 → 검증 우회 (sync가 명시적으로 관리)
- **UI 수동 편집 경로**: 기존 전역 고유성 검증 유지 (수동 태스크에서 같은 식별자 중복 방지)

---

## 8. 실행(Execution) 스코프 변경

### 8.1 문제
`ExecutionRepository.get_by_identifier(identifier_id)`는 전역에서 첫 번째 일치를 반환한다. TC-001이 두 태스크에 존재하면 잘못된 실행 레코드를 반환할 수 있다.

### 8.2 해결
`get_by_identifier_and_task(identifier_id, task_id)` 메서드 추가:
```python
@classmethod
def get_by_identifier_and_task(cls, identifier_id: str, task_id: str):
    for item in read_json(FILENAME):
        if item['identifier_id'] == identifier_id and item.get('task_id') == task_id:
            return item
    return None
```

`_build_item_dict(task, identifier, ...)` 내부에서 이 메서드를 사용한다.

기존 `get_by_identifier`는 하위호환을 위해 유지한다.

### 8.3 `/execution/api/item/<identifier_id>` 변경
- 선택적 쿼리 파라미터 `?task_id=` 추가
- `task_id` 제공 시 해당 태스크 스코프로 조회
- 미제공 시 기존 동작 유지 (첫 번째 일치, 단일 exam_no 환경 호환)

### 8.4 `/execution/api/list` 응답에 `exam_no` 추가
```json
{
  "identifier_id": "TC-001",
  "doc_name": "시스템 초기화",
  "exam_no": 1,            ← 신규
  "display_name": "시스템 초기화 (1차)",  ← 신규 (프론트 렌더링용)
  ...
}
```

---

## 9. UI 표시 변경

### 9.1 큐(작업 목록)
- 태스크 카드/행에 `"시스템 초기화 (1차)"` 표시
- `exam_no` 있는 태스크에 차수 뱃지(badge) 추가

### 9.2 시간표 블록
- 블록 라벨: `"시스템 초기화 (1차)"` 표시
- 블록 상세 팝업 헤더에 차수 뱃지 추가

### 9.3 실행 창
- 식별자 목록 행의 문서명에 `"(N차)"` 표시
- API 응답의 `display_name` 필드 사용

---

## 10. 에러 처리

| 상황 | 처리 |
|------|------|
| MySQL 접속 실패 | 503 반환, 기존 캐시 유지, 앱 정상 동작 |
| `std_list_cache.json` 없음 | 빈 배열로 취급, exam_no 없이 기존 방식으로 동기화 |
| `exam_no` 값이 0 또는 음수 | 유효한 차수로 처리 (`"0차"` 표시) |
| 동일 (doc_id, exam_no) 중복 시 | 두 번째 row 무시, 경고 로그 |

---

## 11. 테스트 전략

| 테스트 | 내용 |
|--------|------|
| `test_std_list.py` | `load_cache`, `save_cache` 동작 검증 |
| `test_sync.py` 확장 | exam_no 기반 태스크 분리, 필터링, 취소 처리 |
| `test_task_model.py` | `get_by_doc_and_exam` 동작 |
| `test_execution.py` | `get_by_identifier_and_task` 동작 |
| `test_routes_calendar.py` | 블록 라벨에 차수 포함 여부 |

MySQL fetch는 mock 처리하여 CI에서 실제 DB 없이 실행한다.

---

## 12. 구현 순서

1. PyMySQL 추가 + `std_list.py` 모델 (MySQL 조회 + 캐시 R/W)
2. `/api/sync/std-list` 엔드포인트
3. 태스크 스키마 (`exam_no` 필드) + `get_by_doc_and_exam`
4. `sync_test_data` 수정 (exam_no 기반 태스크 생성)
5. `get_by_identifier_and_task` + `_build_item_dict` 수정
6. `/item/<identifier_id>` — `?task_id=` 파라미터 추가
7. API 응답에 `exam_no` / `display_name` 추가
8. 프론트엔드 — 큐, 블록, 실행 창에 차수 표시
9. 테스트 작성
