import csv
import io
from datetime import date, datetime, timedelta


HEADERS = ['날짜', '장절명']


def _block_to_row(b):
    return [
        b.get('date', ''),
        b.get('section_name', '') or b.get('task_title', ''),
    ]


def export_csv(enriched_blocks):
    """Generate CSV string with BOM for Korean Excel compatibility."""
    buf = io.StringIO()
    buf.write('\ufeff')
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    for b in enriched_blocks:
        writer.writerow(_block_to_row(b))
    return buf.getvalue()


def export_xlsx(enriched_blocks, start_date, end_date):
    """Generate calendar-layout XLSX as bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = '스케줄'

    # Group blocks by date
    blocks_by_date = {}
    for b in enriched_blocks:
        blocks_by_date.setdefault(b.get('date', ''), []).append(b)

    # Build calendar weeks
    d_start = datetime.strptime(start_date, '%Y-%m-%d').date()
    d_end = datetime.strptime(end_date, '%Y-%m-%d').date()
    week_start = d_start - timedelta(days=d_start.weekday())
    week_end = d_end + timedelta(days=6 - d_end.weekday())

    day_names = ['월', '화', '수', '목', '금', '토', '일']

    # Styles
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    date_font = Font(bold=True, size=10)
    block_font = Font(size=9)
    today_fill = PatternFill(start_color='E8F4FD', end_color='E8F4FD', fill_type='solid')
    weekend_fill = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
    center_align = Alignment(horizontal='center', vertical='top', wrap_text=True)
    top_align = Alignment(vertical='top', wrap_text=True)
    today = date.today()

    # Title row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
    title_cell = ws.cell(row=1, column=1, value=f'스케줄: {start_date} ~ {end_date}')
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')

    for c in range(1, 8):
        ws.column_dimensions[get_column_letter(c)].width = 22

    # Day-name header row (한 번만)
    row = 3
    for i in range(7):
        cell = ws.cell(row=row, column=i + 1, value=day_names[i])
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    row += 1

    current = week_start
    while current <= week_end:
        # Date row
        for i in range(7):
            day = current + timedelta(days=i)
            label = day.strftime('%m/%d') if d_start <= day <= d_end else ''
            cell = ws.cell(row=row, column=i + 1, value=label)
            cell.font = date_font
            cell.alignment = center_align
            cell.border = thin_border
            if day == today:
                cell.fill = today_fill
            elif day.weekday() >= 5:
                cell.fill = weekend_fill
        row += 1

        # Content row: 한 셀에 그 날의 장절을 모두 줄바꿈으로
        max_lines = 1
        for i in range(7):
            day = current + timedelta(days=i)
            day_blocks = blocks_by_date.get(day.isoformat(), [])
            sections = []
            for b in day_blocks:
                section = b.get('section_name', '') or b.get('task_title', '')
                if section:
                    sections.append(section)

            cell = ws.cell(row=row, column=i + 1, value='\n'.join(sections) if sections else '')
            cell.font = block_font
            cell.alignment = top_align
            cell.border = thin_border

            if day == today:
                cell.fill = today_fill
            elif day.weekday() >= 5:
                cell.fill = weekend_fill

            if len(sections) > max_lines:
                max_lines = len(sections)

        ws.row_dimensions[row].height = max(30, max_lines * 15)
        row += 1

        current += timedelta(days=7)

    # Data sheet
    ws2 = wb.create_sheet(title='데이터')
    ws2.append(HEADERS)
    for b in enriched_blocks:
        ws2.append(_block_to_row(b))
    for col in ws2.columns:
        max_len = 0
        for cell in col:
            val = str(cell.value) if cell.value else ''
            max_len = max(max_len, len(val))
        ws2.column_dimensions[col[0].column_letter].width = max_len + 4

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
