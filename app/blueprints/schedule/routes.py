from flask import render_template
from app.blueprints.schedule import schedule_bp


@schedule_bp.route('/day')
def day_view():
    return render_template('schedule/day.html')
