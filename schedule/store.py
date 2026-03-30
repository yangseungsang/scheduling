import json
import os
import shutil
import uuid

import portalocker


def generate_id(prefix):
    """Generate a unique ID with the given prefix (e.g., 'u_', 't_')."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get_path(filename):
    """Get the full path for a data file."""
    from flask import current_app
    return os.path.join(current_app.config['DATA_DIR'], filename)


def read_json(filename):
    """Read and parse a JSON data file with file locking."""
    path = _get_path(filename)
    if not os.path.exists(path):
        return [] if filename != 'settings.json' else {}
    with portalocker.Lock(path, 'r', timeout=5) as f:
        content = f.read()
        if not content.strip():
            return [] if filename != 'settings.json' else {}
        return json.loads(content)


def write_json(filename, data):
    """Write data to a JSON file with backup and file locking."""
    path = _get_path(filename)
    # Create .bak backup before writing
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')
    with portalocker.Lock(path, 'w', timeout=5) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
