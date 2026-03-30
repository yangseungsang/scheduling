"""Tests for schedule.helpers (time_utils, overlap, enrichment)."""


class TestTimeUtils:
    def test_time_to_minutes(self):
        from schedule.helpers.time_utils import time_to_minutes
        assert time_to_minutes('09:00') == 540
        assert time_to_minutes('12:30') == 750
        assert time_to_minutes('00:00') == 0
        assert time_to_minutes('23:59') == 1439

    def test_minutes_to_time(self):
        from schedule.helpers.time_utils import minutes_to_time
        assert minutes_to_time(540) == '09:00'
        assert minutes_to_time(750) == '12:30'
        assert minutes_to_time(0) == '00:00'

    def test_time_roundtrip(self):
        from schedule.helpers.time_utils import time_to_minutes, minutes_to_time
        for t in ['00:00', '09:15', '12:45', '18:00', '23:30']:
            assert minutes_to_time(time_to_minutes(t)) == t

    def test_generate_time_slots(self):
        from schedule.helpers.time_utils import generate_time_slots
        settings = {'work_start': '09:00', 'work_end': '10:00',
                    'grid_interval_minutes': 15}
        slots = generate_time_slots(settings)
        assert slots == ['09:00', '09:15', '09:30', '09:45']

    def test_generate_time_slots_30min(self):
        from schedule.helpers.time_utils import generate_time_slots
        settings = {'work_start': '09:00', 'work_end': '11:00',
                    'grid_interval_minutes': 30}
        slots = generate_time_slots(settings)
        assert slots == ['09:00', '09:30', '10:00', '10:30']

    def test_is_break_slot(self):
        from schedule.helpers.time_utils import is_break_slot
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        assert is_break_slot('12:00', settings) is True
        assert is_break_slot('12:30', settings) is True
        assert is_break_slot('09:45', settings) is True
        assert is_break_slot('09:00', settings) is False
        assert is_break_slot('13:00', settings) is False

    def test_work_minutes_in_range_no_breaks(self):
        from schedule.helpers.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert work_minutes_in_range('09:00', '10:00', settings) == 60

    def test_work_minutes_in_range_with_lunch(self):
        from schedule.helpers.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        # 11:00-14:00 = 3h total, minus 1h lunch = 2h = 120min
        assert work_minutes_in_range('11:00', '14:00', settings) == 120

    def test_work_minutes_in_range_with_break(self):
        from schedule.helpers.time_utils import work_minutes_in_range
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        # 09:00-10:30 = 90min total, minus 15min break = 75min
        assert work_minutes_in_range('09:00', '10:30', settings) == 75

    def test_adjust_end_for_breaks_no_break(self):
        from schedule.helpers.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert adjust_end_for_breaks('09:00', '10:00', settings) == '10:00'

    def test_adjust_end_for_breaks_across_lunch(self):
        from schedule.helpers.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        # 3h from 11:00: 11-12 (1h) + skip lunch + 13-15 (2h) = end at 15:00
        result = adjust_end_for_breaks('11:00', '14:00', settings)
        assert result == '15:00'

    def test_adjust_end_for_breaks_across_small_break(self):
        from schedule.helpers.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [{'start': '09:45', 'end': '10:00'}],
        }
        # 1h from 09:30: 09:30-09:45 (15min) + skip break + 10:00-10:45 (45min) = 10:45
        result = adjust_end_for_breaks('09:30', '10:30', settings)
        assert result == '10:45'

    def test_adjust_end_zero_duration(self):
        from schedule.helpers.time_utils import adjust_end_for_breaks
        settings = {
            'work_end': '18:00',
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [],
        }
        assert adjust_end_for_breaks('09:00', '09:00', settings) == '09:00'

    def test_get_break_periods(self):
        from schedule.helpers.time_utils import get_break_periods, time_to_minutes
        settings = {
            'lunch_start': '12:00', 'lunch_end': '13:00',
            'breaks': [
                {'start': '09:45', 'end': '10:00'},
                {'start': '14:45', 'end': '15:00'},
            ],
        }
        periods = get_break_periods(settings)
        assert (time_to_minutes('12:00'), time_to_minutes('13:00')) in periods
        assert (time_to_minutes('09:45'), time_to_minutes('10:00')) in periods
        assert (time_to_minutes('14:45'), time_to_minutes('15:00')) in periods
