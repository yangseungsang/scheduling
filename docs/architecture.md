# 시스템 아키텍처

소프트웨어 시험 절차를 동기화하고, 캘린더에 배치하고, 시험 항목별 실행 결과를 추적하는 Flask 내부 도구다.

## 데이터 흐름

```text
DynReadyClient -> SyncService -> TestProcedures
TestProcedures + Schedule -> calendar UI
TestProcedures + Schedule + Executions -> execution UI / export
```

공유 데이터는 `JsonDomainRepository`를 통해 `TestPlan`과 `Executions`로 읽고 쓴다.
여러 영역을 함께 조회할 때만 `TestOperations` 읽기 모델로 조합한다.
schedule과 execution feature는 서로의 route를 호출하지 않는다.

## 기술 스택

| 계층 | 기술 |
| --- | --- |
| 백엔드 | Python, Flask, Jinja2 |
| 프론트엔드 | Bootstrap 5, Bootstrap Icons, Vanilla JavaScript |
| 저장소 | typed domain 객체와 JSON 파일 |
| 파일 동시성 | portalocker, 임시 파일 교체 |
| 외부 연동 | DynReady HTTP client |
| 내보내기 | openpyxl, CSV |
| 테스트 | pytest |

## 디렉터리 구조

```text
app/
├── data/                  # test_plan.json, test_executions.json, settings.json
├── domain/                # TestProcedure, ScheduleBlock, ExecutionRun, AppSettings
├── repositories/          # JsonDomainRepository
├── services/              # feature 공통 read model
└── features/
    ├── schedule/          # routes, services, integrations
    └── execution/         # 실행 route, service, 상태 전이
```

## 책임 경계

- `domain`: 필드와 타입을 정의하며 Flask나 파일 경로를 알지 않는다.
- `repositories`: 잠금 안의 read-modify-write, JSON 직렬화와 파일 교체를 담당한다.
- `services`: 일정 배치, 중복 검사, 동기화와 같은 업무 규칙을 담당한다.
- `routes`: 요청 검증과 HTTP 응답 변환을 담당한다.
- `read_models`: 여러 domain 영역을 조합해 화면과 export 형태를 만든다.

## 설정

| 환경변수 | 설명 |
| --- | --- |
| `DOMAIN_DATA_DIR` | 공유 애플리케이션 JSON 경로 |
| `SECRET_KEY` | Flask 세션 키 |
| `DYN_READY_URL` | DynReady API 주소 |

영속 JSON은 모두 `app/data/`에 둔다. 외부 공급자 응답은 캐시하지 않고
동기화 시점마다 가져온다.
