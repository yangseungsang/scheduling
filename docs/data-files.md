# JSON 데이터 파일 가이드

애플리케이션은 기본적으로 `app/data/`에 세 개의 JSON 문서를 저장한다. 실제 경로는 `DOMAIN_DATA_DIR` 환경 변수나 Flask config로 교체할 수 있다.

```text
DOMAIN_DATA_DIR/
├── .data.lock
├── test_plan.json
├── test_executions.json
└── settings.json
```

Feature와 route는 이 파일을 직접 열지 않는다. `JsonDomainRepository`가 JSON을 feature domain 객체로 변환해 반환한다.

## 1. 파일과 소유 모델

| 파일 | Domain 타입 | 소유 feature | 내용 |
| --- | --- | --- | --- |
| `test_plan.json` | `TestPlan` | schedule | 시험 사이클 버전, procedure, 일정 block |
| `test_executions.json` | `Executions` | execution | 시험 항목별 상태, 시간, 결과 |
| `settings.json` | `AppSettings` | schedule | 근무, 휴식, 그리드, 화면 설정 |

## 2. `test_plan.json`

예시 구조:

```json
{
  "version_id": "OFP-2026-08",
  "test_procedures": [
    {
      "id": "tp_1234",
      "document_id": "DOC-100",
      "document_name": "결제 시험",
      "test_round": 1,
      "test_items": [
        {
          "id": "PAY-LOGIN",
          "name": "로그인",
          "estimated_minutes": 60,
          "total_count": 20,
          "owner_names": ["김담당"]
        }
      ],
      "assignee_names": ["이시험"],
      "location_name": "QA Lab",
      "memo": "회귀 시험"
    }
  ],
  "schedule_blocks": [
    {
      "id": "blk_1234",
      "procedure_id": "tp_1234",
      "test_item_ids": ["PAY-LOGIN"],
      "date": "2026-08-21",
      "start_time": "09:00",
      "end_time": "10:00",
      "location_name": "QA Lab",
      "assignee_names": ["이시험"],
      "is_locked": true
    }
  ]
}
```

### Procedure 규칙

- `id`는 내부 식별자다.
- 외부 동기화 procedure는 일반적으로 `document_id + test_round`로 결정적 ID를 만든다.
- `test_items[].id`는 같은 `test_round`에서 중복될 수 없다.
- `estimated_minutes`가 생략되면 시험 항목 예상 시간 합으로 복원한다.
- `kind`는 저장하지 않고 시험 항목 유무로 `test` 또는 `simple`을 계산한다.
- `state=active` 같은 기본값은 생략할 수 있다.

### Schedule block 규칙

- 시험 block은 `procedure_id`를 가진다.
- 단순 block은 `procedure_id` 없이 `title`을 가진다.
- `test_item_ids`가 없으면 해당 procedure 전체를 포함하는 기존 데이터로 해석한다.
- 장소는 별도 master ID가 아니라 `location_name` 문자열로 저장한다.
- `manual_status`는 사용자가 지정한 cancelled 등의 상태다.
- `overflow_minutes`는 근무 종료를 넘긴 시간 표현에 사용한다.

## 3. `test_executions.json`

예시 구조:

```json
{
  "execution_runs": [
    {
      "procedure_id": "tp_1234",
      "test_item_id": "PAY-LOGIN",
      "status": "completed",
      "started_at": "2026-08-21T09:00:00",
      "ended_at": "2026-08-21T09:45:00",
      "actual_seconds": 2700,
      "total_count": 20,
      "fail_count": 1,
      "block_count": 2,
      "pass_count": 17,
      "comment": "결함 1건 등록",
      "performer_name": "이시험"
    }
  ]
}
```

### 실행 기록 규칙

- 별도 실행 ID는 없다.
- `procedure_id + test_item_id`가 논리 키다.
- 다른 차수의 procedure에서 같은 시험 항목 ID를 사용할 수 있으므로 두 값을 항상 함께 전달한다.
- `active_started_at`은 현재 in-progress 구간의 시작 시각이다.
- pause 시 해당 구간을 `actual_seconds`에 누적하고 `active_started_at`을 비운다.
- `elapsed_seconds`는 저장하지 않는 계산 속성이다.
- 완료 시 pass는 `total - fail - block`으로 계산한다.

## 4. `settings.json`

예시 구조:

```json
{
  "schema_version": "1.0",
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
  "block_color_by": "status"
}
```

설정 필드는 선택 값이다. 누락된 필드는 service의 화면 기본값이나 domain 기본값으로 처리한다. `block_color_by`는 `status`, `assignee`, `location`을 지원한다.

## 5. 읽기와 쓰기 과정

### 읽기

1. Repository가 `.data.lock`을 획득한다.
2. JSON을 읽는다.
3. `from_dict()`로 immutable domain 객체를 만든다.
4. service에 domain 객체를 반환한다.

### 쓰기

1. 잠금 안에서 최신 JSON을 domain 객체로 읽는다.
2. update callback이 새 domain 객체를 반환한다.
3. 같은 데이터 디렉터리에 임시 파일을 작성한다.
4. flush와 `fsync`로 내용을 확정한다.
5. `os.replace()`로 기존 파일을 교체한다.

빈 문자열, 빈 배열, `false`, `0`인 선택 필드는 `to_dict()`가 생략할 수 있다. 다시 읽을 때 `from_dict()`가 기본값을 복원한다.

## 6. 초기화와 데이터 보존

- 애플리케이션 시작 시 파일이 없으면 빈 domain 문서를 만든다.
- `POST /admin/api/project-reset`은 procedure, schedule, execution을 비우고 설정은 유지한다.
- `POST /api/sync/reset-and-sync`은 같은 영역을 비운 뒤 DynReady에서 다시 가져온다.
- 테스트는 `tmp_path/domain_data`를 사용하므로 실제 `app/data`를 수정하지 않는다.

## 7. 직접 수정 시 주의사항

운영 중 JSON을 직접 수정하면 잠금과 domain 검증을 우회한다. 가능한 경우 API, service 또는 시드 스크립트를 사용한다. 직접 수정이 불가피하면 애플리케이션을 중지하고 백업한 뒤 JSON 문법과 논리 키 중복 여부를 확인한다.
