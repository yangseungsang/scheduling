import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
