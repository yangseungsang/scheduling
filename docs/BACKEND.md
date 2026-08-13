# Backend 구조

schedule과 execution은 동일한 typed domain 데이터와 JSON repository를 공유한다.

## 요청 흐름

```text
route -> feature service -> JsonDomainRepository -> domain type -> JSON file
```

route는 HTTP 요청과 응답을 담당하고, 업무 규칙은 feature service가 처리한다.
repository는 JSON을 읽는 즉시 domain 객체로 변환하므로 서비스는 파일 구조를 직접 다루지 않는다.

## 폴더 책임

| 경로 | 책임 |
| --- | --- |
| `app/domain/` | 공유 데이터 클래스와 repository 계약 |
| `app/repositories/json_domain.py` | `TestOperations`의 원자적 JSON 영속화 |
| `app/services/read_models.py` | schedule과 execution 공통 조회 모델 |
| `app/features/schedule/routes/` | 일정 페이지와 HTTP API |
| `app/features/schedule/integrations/dyn_ready.py` | DynReady HTTP 연동 |
| `app/features/schedule/services/blocks.py` | 일정 검증과 블록 workflow |
| `app/features/schedule/services/_block_commands.py` | blocks 내부의 저수준 변경 명령 |
| `app/features/schedule/services/procedures.py` | procedure 조회·생성·수정·삭제 |
| `app/features/schedule/services/sync.py` | 외부 데이터 동기화 |
| `app/features/schedule/services/presentation.py` | 일정 UI와 export용 read model |
| `app/features/schedule/services/export.py` | CSV/XLSX 직렬화 |
| `app/features/schedule/services/settings.py` | 설정 조회와 수정 |
| `app/features/schedule/services/time.py` | 근무·휴식 시간 계산 |
| `app/features/execution/routes/` | 실행 페이지와 HTTP API |
| `app/features/execution/repository.py` | 실행 상태 전이 |
| `app/data/` | 애플리케이션 JSON 데이터 |

## Domain

| 모듈 | 주요 타입 |
| --- | --- |
| `procedures.py` | `TestItem`, `TestProcedure` |
| `scheduling.py` | `ScheduleBlock`, `Schedule` |
| `execution.py` | `ExecutionRun`, `Executions` |
| `settings.py` | `AppSettings` |
| `test_operations.py` | `TestOperations` |
| `identity.py` | 외부 business key에 대한 결정적 내부 ID 생성 |

`identity.stable_id()`는 외부 연동이 같은 procedure를 반복해서 보내도 같은 procedure를
갱신하기 위해 사용한다. 일정과 실행 기록은 별도의 접두사 ID를 사용한다.

장소는 참조 ID를 만들지 않고 `location_name` 문자열을 procedure와 block에 직접 저장한다.

## Repository 사용

```python
repository = JsonDomainRepository(data_dir)
operations = repository.load_operations()
procedures = operations.procedures
schedule = operations.schedule
executions = operations.executions
```

변경은 잠금 안에서 최신 `TestOperations`를 읽고 수정한다. 쓰기는 임시 파일을
완성한 후 `os.replace()`로 교체하므로 세 데이터 영역이 함께 반영된다.
`DOMAIN_DATA_DIR` 환경변수로 애플리케이션 데이터 경로를 변경할 수 있다.

## 개발

```bash
pip install -r requirements.txt
python3 run.py
python -m pytest -q
```

기본 개발 URL은 `http://localhost:5001`이다.
