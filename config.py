import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE = os.path.join(BASE_DIR, 'scheduling.db')
    # MySQL 전환 시: DATABASE 주석 처리 후 아래 항목들 설정, db.py의 sqlite3.connect를 mysql.connector.connect로 교체
    # DB_HOST = 'localhost'
    # DB_USER = 'user'
    # DB_PASSWORD = 'password'
    # DB_NAME = 'scheduling'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
