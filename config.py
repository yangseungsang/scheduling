import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE = os.path.join(BASE_DIR, 'scheduling.db')
    # MySQL 전환 시 아래 주석 해제 후 DATABASE 주석 처리
    # DATABASE_URL = 'mysql+connector://user:password@localhost/scheduling'

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
