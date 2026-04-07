"""
데이터 저장소 모듈.

JSON 파일 기반의 데이터 읽기/쓰기 기능을 제공한다.
모든 데이터는 data/ 디렉터리 아래의 JSON 파일에 저장되며,
동시 접근 시 파일 잠금(portalocker)을 사용하여 데이터 무결성을 보장한다.
"""

import json
import os
import shutil
import uuid

import portalocker


def generate_id(prefix):
    """고유 ID를 생성한다.

    Args:
        prefix: ID 접두사 (예: 'u_', 't_', 'sb_', 'loc_', 'v_')

    Returns:
        str: 접두사 + UUID 앞 8자리로 구성된 고유 ID (예: 'u_a1b2c3d4')
    """
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get_path(filename):
    """데이터 파일의 절대 경로를 반환한다.

    Flask 앱 설정의 DATA_DIR 경로와 파일명을 결합한다.

    Args:
        filename: JSON 파일명 (예: 'tasks.json', 'users.json')

    Returns:
        str: 데이터 파일의 절대 경로
    """
    from flask import current_app
    return os.path.join(current_app.config['DATA_DIR'], filename)


def read_json(filename):
    """JSON 데이터 파일을 읽어 파싱한다.

    파일 잠금을 사용하여 동시 읽기 시 데이터 정합성을 보장한다.
    파일이 존재하지 않거나 비어 있으면 기본값을 반환한다.

    Args:
        filename: 읽을 JSON 파일명

    Returns:
        list 또는 dict: 파싱된 데이터.
            settings.json이면 dict(빈 경우 {}),
            그 외 파일이면 list(빈 경우 [])를 반환한다.
    """
    path = _get_path(filename)
    if not os.path.exists(path):
        # settings.json은 단일 객체, 나머지는 배열 형태
        return [] if filename != 'settings.json' else {}
    with portalocker.Lock(path, 'r', timeout=5) as f:
        content = f.read()
        if not content.strip():
            # 파일이 비어 있는 경우에도 기본값 반환
            return [] if filename != 'settings.json' else {}
        return json.loads(content)


def write_json(filename, data):
    """데이터를 JSON 파일에 기록한다.

    기록 전에 기존 파일의 백업(.bak)을 생성하고,
    파일 잠금을 사용하여 동시 쓰기를 방지한다.

    Args:
        filename: 기록할 JSON 파일명
        data: 저장할 데이터 (list 또는 dict)
    """
    path = _get_path(filename)
    # 데이터 유실 방지를 위해 기존 파일을 .bak으로 백업
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')
    with portalocker.Lock(path, 'w', timeout=5) as f:
        # ensure_ascii=False: 한글 등 유니코드를 그대로 저장
        json.dump(data, f, ensure_ascii=False, indent=2)
