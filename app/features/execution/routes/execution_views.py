"""시험 실행 페이지 뷰 라우트."""

from datetime import date, timedelta

from flask import Blueprint, render_template, request

execution_bp = Blueprint(
    'execution', __name__,
    url_prefix='/execution',
    template_folder='../../../templates',
    static_folder='../../../static',
)


def _parse_date(date_str):
    if date_str:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass
    return date.today()


@execution_bp.route('/')
def day_view():
    """일별 시험 실행 페이지."""
    current_date = _parse_date(request.args.get('date'))
    return render_template(
        'execution/day.html',
        current_date=current_date,
        prev_date=current_date - timedelta(days=1),
        next_date=current_date + timedelta(days=1),
    )
