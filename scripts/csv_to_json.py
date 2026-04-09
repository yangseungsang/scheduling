"""CSV 테스트 데이터를 프로젝트 JSON 형식으로 변환하는 스크립트.

사용법:
    python scripts/csv_to_json.py <csv_파일_경로> [--output-dir <출력_디렉토리>] [--clear]

CSV 형식:
    "장절명","시험식별자","시험항목","담당자","시험 예상시간"

담당자는 시험 식별자를 작성한 사람(owner)이며, 시험을 수행하는 인원(assignee)과는 다름.
시험 예상시간은 분 단위.
"""

import argparse
import csv
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime

# 프로젝트 루트 경로
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(
    PROJECT_ROOT, 'app', 'features', 'schedule', 'data'
)


def read_csv(csv_path):
    """CSV 파일을 읽어 행 리스트로 반환한다."""
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'section_name': row['장절명'].strip(),
                'test_id': row['시험식별자'].strip(),
                'test_name': row['시험항목'].strip(),
                'owner': row['담당자'].strip(),
                'estimated_minutes': int(row['시험 예상시간'].strip()),
            })
    return rows


def group_by_section(rows):
    """행들을 장절명으로 그룹화한다. 입력 순서를 유지한다."""
    sections = OrderedDict()
    for row in rows:
        key = row['section_name']
        if key not in sections:
            sections[key] = []
        sections[key].append(row)
    return sections


def get_next_task_id(existing_tasks):
    """기존 태스크 목록에서 다음 ID 번호를 계산한다."""
    max_num = 0
    for t in existing_tasks:
        tid = t.get('id', '')
        if tid.startswith('t_'):
            try:
                num = int(tid[2:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return max_num + 1


def get_next_procedure_prefix(existing_tasks):
    """기존 태스크에서 사용된 procedure_id 접두사를 수집한다."""
    prefixes = set()
    for t in existing_tasks:
        pid = t.get('procedure_id', '')
        parts = pid.rsplit('-', 1)
        if len(parts) == 2:
            prefixes.add(parts[0])
    return prefixes


def build_tasks_and_procedures(sections, existing_tasks=None):
    """그룹화된 섹션 데이터를 tasks와 procedures 리스트로 변환한다."""
    existing_tasks = existing_tasks or []
    next_id = get_next_task_id(existing_tasks)
    existing_sections = {t['section_name'] for t in existing_tasks}

    tasks = []
    procedures = []
    proc_counter = {}  # prefix -> counter

    now = datetime.now().isoformat(timespec='seconds')

    for section_name, rows in sections.items():
        if section_name in existing_sections:
            print(f"  건너뜀 (이미 존재): {section_name}")
            continue

        # 식별자 목록 구성
        test_list = []
        for row in rows:
            test_list.append({
                'id': row['test_id'],
                'name': row['test_name'],
                'estimated_minutes': row['estimated_minutes'],
                'owners': [row['owner']],
            })

        total_minutes = sum(r['estimated_minutes'] for r in rows)

        # procedure_id 생성: CSV-001, CSV-002, ...
        prefix = 'CSV'
        if prefix not in proc_counter:
            proc_counter[prefix] = 1
        else:
            proc_counter[prefix] += 1
        procedure_id = f"{prefix}-{proc_counter[prefix]:03d}"

        # 장절의 첫 번째 담당자를 procedure_owner로 사용
        procedure_owner = rows[0]['owner']

        task_id = f"t_{next_id:03d}"
        next_id += 1

        tasks.append({
            'id': task_id,
            'procedure_id': procedure_id,
            'assignee_ids': [],
            'location_id': '',
            'section_name': section_name,
            'procedure_owner': procedure_owner,
            'test_list': test_list,
            'estimated_minutes': total_minutes,
            'remaining_minutes': total_minutes,
            'status': 'waiting',
            'memo': '',
            'source': 'csv',
            'external_key': '',
            'created_at': now,
        })

        # procedures 항목 (identifiers는 owners/estimated_minutes 없이)
        proc_identifiers = []
        for row in rows:
            proc_identifiers.append({
                'id': row['test_id'],
                'name': row['test_name'],
                'owners': [],
                'estimated_minutes': 0,
            })

        procedures.append({
            'procedure_id': procedure_id,
            'section_name': section_name,
            'procedure_owner': procedure_owner,
            'identifiers': proc_identifiers,
            'version_id': '',
        })

    return tasks, procedures


def load_json(path):
    """JSON 파일을 로드한다. 파일이 없으면 빈 리스트를 반환한다."""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_json(path, data):
    """데이터를 JSON 파일로 저장한다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  저장됨: {path}")


def main():
    parser = argparse.ArgumentParser(
        description='CSV 테스트 데이터를 프로젝트 JSON 형식으로 변환'
    )
    parser.add_argument('csv_file', help='입력 CSV 파일 경로')
    parser.add_argument(
        '--output-dir', default=DEFAULT_DATA_DIR,
        help=f'출력 디렉토리 (기본값: {DEFAULT_DATA_DIR})'
    )
    parser.add_argument(
        '--clear', action='store_true',
        help='기존 데이터를 지우고 새로 생성'
    )
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print(f"오류: CSV 파일을 찾을 수 없음: {args.csv_file}")
        sys.exit(1)

    tasks_path = os.path.join(args.output_dir, 'tasks.json')
    procedures_path = os.path.join(args.output_dir, 'procedures.json')

    print(f"CSV 읽는 중: {args.csv_file}")
    rows = read_csv(args.csv_file)
    print(f"  {len(rows)}개 행 읽음")

    sections = group_by_section(rows)
    print(f"  {len(sections)}개 장절 발견")

    if args.clear:
        existing_tasks = []
        existing_procedures = []
        print("  기존 데이터 초기화 모드")
    else:
        existing_tasks = load_json(tasks_path)
        existing_procedures = load_json(procedures_path)
        print(f"  기존 태스크 {len(existing_tasks)}개, 절차서 {len(existing_procedures)}개 로드")

    new_tasks, new_procedures = build_tasks_and_procedures(
        sections, existing_tasks
    )

    if not new_tasks:
        print("추가할 새 태스크가 없습니다.")
        return

    print(f"\n새로 생성: 태스크 {len(new_tasks)}개, 절차서 {len(new_procedures)}개")

    all_tasks = existing_tasks + new_tasks if not args.clear else new_tasks
    all_procedures = existing_procedures + new_procedures if not args.clear else new_procedures

    save_json(tasks_path, all_tasks)
    save_json(procedures_path, all_procedures)

    print("\n변환 완료!")
    for t in new_tasks:
        ids = ', '.join(item['id'] for item in t['test_list'])
        print(f"  [{t['id']}] {t['section_name']} ({t['estimated_minutes']}분) — {ids}")


if __name__ == '__main__':
    main()
