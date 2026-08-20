# 개발 문서 안내

현재 코드 구조를 이해하거나 변경할 때 다음 순서로 읽는다.

| 문서 | 목적 |
| --- | --- |
| `architecture.md` | 시스템 전체 구조, 폴더 책임, feature 상호작용과 주요 데이터 흐름 |
| `BACKEND.md` | Flask route, service, domain, repository의 상세 동작 |
| `FRONTEND.md` | Jinja template, JavaScript 모듈과 사용자 조작 흐름 |
| `data-files.md` | JSON 파일 schema, 논리 키, 잠금과 쓰기 방식 |
| `PRD.md` | 제품 목적과 기능 요구사항 |
| `manual-test-checklist.md` | 브라우저에서 확인할 수동 회귀 항목 |

과거 설계 과정은 `plans/`에 보존한다. 현재 동작을 판단할 때는 위 기술 문서와 실제 코드를 우선한다.
