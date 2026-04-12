"""스케줄 내보내기(export) 서비스 모듈.

보강된 스케줄 블록 데이터를 CSV 또는 XLSX(엑셀) 형식으로 내보내는
기능을 제공한다. 엑셀 내보내기 시 달력 레이아웃 시트와 데이터 시트를
함께 생성한다.
"""

import csv
import io
from datetime import date, datetime, timedelta


# 내보내기 열 헤더 (날짜와 문서명만 포함)
HEADERS = ['날짜', '문서명']


def _block_to_row(b):
    """블록 딕셔너리를 내보내기용 행(row) 데이터로 변환한다.

    Args:
        b: 보강된 스케줄 블록 딕셔너리.

    Returns:
        list: [날짜, 문서명(또는 태스크 제목)] 형태의 리스트.
    """
    return [
        b.get('date', ''),
        b.get('doc_name', '') or b.get('task_title', ''),
    ]


def export_csv(enriched_blocks):
    """보강된 블록 목록을 CSV 문자열로 변환한다.

    한국어 엑셀 호환성을 위해 BOM(Byte Order Mark)을 앞에 추가한다.

    Args:
        enriched_blocks: 보강된 스케줄 블록 딕셔너리 목록.

    Returns:
        str: BOM이 포함된 CSV 문자열.
    """
    buf = io.StringIO()
    buf.write('\ufeff')  # UTF-8 BOM: 엑셀에서 한글 깨짐 방지
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    for b in enriched_blocks:
        writer.writerow(_block_to_row(b))
    return buf.getvalue()


def export_xlsx(enriched_blocks, start_date, end_date):
    """보강된 블록 목록을 달력 형태의 XLSX 파일로 변환한다.

    첫 번째 시트('스케줄')에는 주간 달력 레이아웃으로 각 날짜에
    해당하는 장절명을 표시하고, 두 번째 시트('데이터')에는
    원본 데이터를 목록 형태로 나열한다.

    Args:
        enriched_blocks: 보강된 스케줄 블록 딕셔너리 목록.
        start_date: 내보내기 시작 날짜 ('YYYY-MM-DD').
        end_date: 내보내기 종료 날짜 ('YYYY-MM-DD').

    Returns:
        bytes: XLSX 파일 바이너리 데이터.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = '스케줄'

    # 블록을 날짜별로 그룹핑
    blocks_by_date = {}
    for b in enriched_blocks:
        blocks_by_date.setdefault(b.get('date', ''), []).append(b)

    # 달력 주간 범위 계산: 시작일이 속한 주의 월요일 ~ 종료일이 속한 주의 일요일
    d_start = datetime.strptime(start_date, '%Y-%m-%d').date()
    d_end = datetime.strptime(end_date, '%Y-%m-%d').date()
    week_start = d_start - timedelta(days=d_start.weekday())  # 월요일로 맞춤
    week_end = d_end + timedelta(days=6 - d_end.weekday())    # 일요일로 맞춤

    day_names = ['월', '화', '수', '목', '금', '토', '일']

    # 엑셀 스타일 정의
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

    # 1행: 제목 (7열 병합)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
    title_cell = ws.cell(row=1, column=1, value=f'스케줄: {start_date} ~ {end_date}')
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')

    # 열 너비 설정 (7일 = 7열)
    for c in range(1, 8):
        ws.column_dimensions[get_column_letter(c)].width = 22

    # 3행: 요일 헤더 (월~일)
    row = 3
    for i in range(7):
        cell = ws.cell(row=row, column=i + 1, value=day_names[i])
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    row += 1

    # 주간 반복: 날짜 행 + 내용 행
    current = week_start
    while current <= week_end:
        # 날짜 행: 각 요일의 날짜(MM/DD) 표시
        for i in range(7):
            day = current + timedelta(days=i)
            # 내보내기 범위 밖의 날짜는 빈 문자열
            label = day.strftime('%m/%d') if d_start <= day <= d_end else ''
            cell = ws.cell(row=row, column=i + 1, value=label)
            cell.font = date_font
            cell.alignment = center_align
            cell.border = thin_border
            # 오늘 날짜와 주말에 배경색 적용
            if day == today:
                cell.fill = today_fill
            elif day.weekday() >= 5:
                cell.fill = weekend_fill
        row += 1

        # 내용 행: 해당 날짜의 문서명을 줄바꿈으로 합쳐서 표시
        max_lines = 1
        for i in range(7):
            day = current + timedelta(days=i)
            day_blocks = blocks_by_date.get(day.isoformat(), [])
            sections = []
            for b in day_blocks:
                section = b.get('doc_name', '') or b.get('task_title', '')
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

        # 행 높이를 내용 줄 수에 비례하여 조정 (최소 30px)
        ws.row_dimensions[row].height = max(30, max_lines * 15)
        row += 1

        # 다음 주로 이동
        current += timedelta(days=7)

    # 두 번째 시트: 원본 데이터 목록
    ws2 = wb.create_sheet(title='데이터')
    ws2.append(HEADERS)
    for b in enriched_blocks:
        ws2.append(_block_to_row(b))
    # 열 너비를 내용에 맞게 자동 조정
    for col in ws2.columns:
        max_len = 0
        for cell in col:
            val = str(cell.value) if cell.value else ''
            max_len = max(max_len, len(val))
        ws2.column_dimensions[col[0].column_letter].width = max_len + 4

    # 워크북을 바이트 버퍼에 저장하여 반환
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
