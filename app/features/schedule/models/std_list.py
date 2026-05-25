import os
import pymysql
import pymysql.cursors

from app.features.schedule.store import read_json, write_json

CACHE_FILENAME = 'std_list_cache.json'


def _get_db_config():
    env = os.environ.get('FLASK_ENV', 'development')
    db_name = (
        os.environ.get('MYSQL_DB_PROD')
        if env == 'production'
        else os.environ.get('MYSQL_DB_DEV', '')
    )
    return {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQL_PORT', '3306') or '3306'),
        'user': os.environ.get('MYSQL_USER', ''),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': db_name,
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor,
    }


def fetch_from_mysql():
    """std_list 테이블에서 test_info, exam_no를 읽어 반환한다."""
    config = _get_db_config()
    conn = pymysql.connect(**config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT test_info, exam_no FROM std_list'
                ' WHERE exam_no IS NOT NULL'
            )
            return [
                {'test_info': row['test_info'], 'exam_no': row['exam_no']}
                for row in cursor.fetchall()
            ]
    finally:
        conn.close()


def load_cache():
    """로컬 캐시(std_list_cache.json)를 읽어 반환한다. 없으면 []."""
    return read_json(CACHE_FILENAME)


def save_cache(rows):
    """rows를 std_list_cache.json에 저장한다."""
    write_json(CACHE_FILENAME, rows)
