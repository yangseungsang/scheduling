"""
Flask 애플리케이션 팩토리 모듈.

Flask 앱 인스턴스를 생성하고, 설정을 적용하며,
블루프린트를 등록하는 create_app() 팩토리 함수를 제공한다.
"""

import os
import time

from flask import Flask, redirect, url_for

# 서버 시작 시각 (캐시 무효화용 타임스탬프)
_START_TIME = int(time.time())

# 환경 변수 또는 기본값으로 시크릿 키 설정
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
# JSON 데이터 파일이 저장되는 디렉토리 경로
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'features', 'schedule', 'data')
# 시험실행(Execution) 데이터 파일이 저장되는 디렉토리 경로
EXECUTION_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'features', 'execution', 'data'
)


def create_app():
    """Flask 애플리케이션 인스턴스를 생성하고 설정한다.

    수행하는 작업:
    1. Flask 앱 생성 (템플릿/정적 파일 경로 설정)
    2. 시크릿 키, 데이터 디렉토리 등 설정 적용
    3. 데이터 디렉토리 생성 (없으면)
    4. Jinja2 전역 변수 등록 (캐시 무효화용 타임스탬프)
    5. CORS 헤더 자동 추가
    6. 블루프린트 등록
    7. 루트 URL 리다이렉트 설정

    Returns:
        Flask: 설정이 완료된 Flask 앱 인스턴스
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['DATA_DIR'] = DATA_DIR
    app.config['EXECUTION_DATA_DIR'] = EXECUTION_DATA_DIR
    # 개발 환경: 정적 파일 캐시 비활성화
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # 데이터 디렉토리가 없으면 자동 생성
    os.makedirs(app.config['DATA_DIR'], exist_ok=True)
    os.makedirs(app.config['EXECUTION_DATA_DIR'], exist_ok=True)

    # 템플릿에서 정적 파일 URL에 cache_bust 파라미터로 사용
    app.jinja_env.globals['cache_bust'] = _START_TIME

    @app.after_request
    def add_cors(response):
        """모든 응답에 CORS 헤더를 추가한다.

        API를 외부 클라이언트에서도 호출할 수 있도록 허용한다.

        Args:
            response: Flask 응답 객체

        Returns:
            CORS 헤더가 추가된 응답 객체
        """
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        return response

    # 스케줄 관련 모든 블루프린트를 앱에 등록
    from app.features.schedule import register_blueprints
    register_blueprints(app)

    from app.features.execution import register_blueprints as register_execution
    register_execution(app)

    @app.route('/')
    def index():
        """루트 URL 접속 시 주간 시간표 뷰로 리다이렉트한다."""
        return redirect(url_for('schedule.week_view'))

    return app
