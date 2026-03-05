# Task Scheduling Web Service — Design Document
Date: 2026-03-05

## Overview

팀 전체 업무를 공유 캘린더 형태로 관리하는 웹 서비스.
Flask + Jinja2 + Bootstrap5 기반, 스케줄링 추천 알고리즘 포함.

---

## 1. 기술 스택

- Backend: Python / Flask
- Template: Jinja2
- Frontend: Bootstrap 5, SortableJS (드래그앤드랍)
- DB: SQLite (추후 MySQL 전환 가능), Raw SQL (ORM 미사용)
- 테스트: Playwright 브라우저 자동화

---

## 2. 사용자 및 역할

- 로그인/인증은 외부 시스템에서 처리 (이 프로젝트 범위 외)
- Admin: 근무시간 설정, 사용자 관리, 스케줄 초안 생성/승인
- Member: 업무 상태 업데이트, 메모 작성, 스케줄 조회

---

## 3. 프로젝트 구조

```
scheduling/
├── run.py
├── config.py
├── schema.sql
├── app/
│   ├── __init__.py
│   ├── db.py
│   ├── blueprints/
│   │   ├── tasks/          # 업무 CRUD
│   │   ├── schedule/       # 스케줄 뷰 (일/주/월)
│   │   └── admin/          # 설정, 사용자 관리
│   ├── repositories/
│   │   ├── task_repo.py
│   │   ├── schedule_repo.py
│   │   └── settings_repo.py
│   ├── services/
│   │   └── scheduler.py    # 스케줄링 추천 알고리즘
│   ├── templates/
│   │   ├── base.html
│   │   ├── tasks/
│   │   ├── schedule/
│   │   └── admin/
│   └── static/
│       ├── css/
│       └── js/
│           └── drag_drop.js
```

---

## 4. 데이터 모델

```sql
-- 사용자
users: id, name, email, role(admin/member), created_at

-- 설정 (키-값)
settings: id, key, value
-- 키 예시: work_start, work_end, lunch_start, lunch_end (분 단위 시간)

-- 카테고리
categories: id, name, color, created_at

-- 업무
tasks: id, title, description, category_id, priority(low/medium/high/urgent),
       estimated_minutes, status(pending/in_progress/completed/cancelled),
       due_date, created_by, created_at, updated_at

-- 업무 담당자 (다대다)
task_assignees: task_id, user_id

-- 스케줄 배치
schedule_blocks: id, task_id, assigned_date, start_time, end_time,
                 is_draft, created_at

-- 메모
task_notes: id, task_id, user_id, content, created_at
```

---

## 5. 주요 화면

### 스케줄 뷰 (메인)
- 일/주/월 탭 전환
- 날짜 네비게이션
- 카테고리 필터 드롭다운
- 좌측: 미배치 업무 목록 (드래그 소스)
- 우측: 타임라인 캘린더 (드래그 대상)
- 점심시간 회색 영역 시각화
- 업무 블록 색상 = 카테고리 색상

### 업무 관리
- 목록 테이블 + 상태/카테고리/담당자 필터
- 사이드 패널로 상세 보기/편집
- 인라인 상태 변경
- 메모 타임라인

### 스케줄링 추천
- 카테고리 선택 → "초안 생성" 버튼
- 알고리즘: 남은 근무시간 내 완료 가능한 업무 우선 배치
- 기존 스케줄 보존, 선택 카테고리 범위만 재계산
- 초안 반투명 표시 → 승인/취소

### 관리자 설정
- 근무시간/점심시간 분 단위 설정
- 사용자 목록 및 역할 관리

---

## 6. 스케줄링 알고리즘

**입력:** 카테고리 ID, 대상 날짜 범위, 미배치 업무 목록, 근무시간 설정

**로직:**
1. 대상 날짜별로 가용 시간 슬롯 계산 (근무시간 - 점심시간 - 기존 배치 시간)
2. 업무를 "당일 완료 가능성" 기준으로 정렬
   - 남은 가용 시간 내 완료 가능한 업무 먼저
   - 작은 업무(소요시간 짧은 것)부터 채워 당일 완료 수 최대화
3. 당일에 들어가지 않는 업무는 다음 날로 넘김
4. 점심시간 걸리는 경우: 오전/오후 블록으로 자동 분할 (연속 작업 가능)

**출력:** `schedule_blocks` 목록 (is_draft=true)

---

## 7. 테스트 계획 (Playwright)

- 근무시간 설정 → 저장 확인
- 업무 생성 → 목록 표시 확인
- 드래그앤드랍 스케줄 배치 확인
- 카테고리별 초안 생성 → 승인 플로우 확인
- 일/주/월 뷰 전환 확인
- 상태 변경 및 메모 추가 확인
- 카테고리 필터링 확인
