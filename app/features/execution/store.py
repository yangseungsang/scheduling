"""execution 데이터 저장소 — schedule과 독립된 자체 data 경로 사용."""

import json
import os
import shutil
import uuid

import portalocker

EXECUTION_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def generate_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def read_json(filename):
    path = os.path.join(EXECUTION_DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with portalocker.Lock(path, 'r', timeout=5) as f:
        content = f.read()
        if not content.strip():
            return []
        return json.loads(content)


def write_json(filename, data):
    path = os.path.join(EXECUTION_DATA_DIR, filename)
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')
    with portalocker.Lock(path, 'w', timeout=5) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
