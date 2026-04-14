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
    """블록 딕셔너리를 내보내기용 행(row) 데이터로 변환한다."""
    name = b.get('doc_name', '') or b.get('task_title', '')
    if b.get('is_split'):
        name += ' (' + str(b.get('block_identifier_count', '?')) + '/' + str(b.get('total_identifier_count', '?')) + ')'
    return [b.get('date', ''), name]


def _block_label(b):
    """블록의 표시 라벨을 생성한다 (달력 시트용)."""
    name = b.get('doc_name', '') or b.get('task_title', '')
    if b.get('is_split'):
        name += ' (' + str(b.get('block_identifier_count', '?')) + '/' + str(b.get('total_identifier_count', '?')) + ')'
    return name


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


def export_xlsx(enriched_blocks, start_date, end_date, version_name=''):
    """보강된 블록 목록을 달력 형태의 XLSX 파일로 변환한다.

    첫 번째 시트('스케줄')에는 주간 달력 레이아웃으로 각 날짜에
    해당하는 장절명을 표시하고, 두 번째 시트('데이터')에는
    원본 데이터를 목록 형태로 나열한다.

    Args:
        enriched_blocks: 보강된 스케줄 블록 딕셔너리 목록.
        start_date: 내보내기 시작 날짜 ('YYYY-MM-DD').
        end_date: 내보내기 종료 날짜 ('YYYY-MM-DD').
        version_name: 소프트웨어 버전명 (선택).

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
    week_end = d_end + timedelta(days=4 - d_end.weekday()) if d_end.weekday() < 5 else d_end  # 금요일까지

    day_names = ['월', '화', '수', '목', '금']

    # 엑셀 스타일 정의
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    date_font = Font(bold=True, size=10)
    block_font = Font(size=9)
    center_align = Alignment(horizontal='center', vertical='top', wrap_text=True)
    top_align = Alignment(vertical='top', wrap_text=True)

    # 1행: 제목 (5열 병합)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    title_text = f'스케줄: {start_date} ~ {end_date}'
    if version_name:
        title_text = f'[{version_name}] {title_text}'
    title_cell = ws.cell(row=1, column=1, value=title_text)
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal='center')

    # 열 너비 설정 (5일 = 5열)
    for c in range(1, 6):
        ws.column_dimensions[get_column_letter(c)].width = 26

    # 2행: 요일 헤더 (월~금)
    row = 2
    for i in range(5):
        cell = ws.cell(row=row, column=i + 1, value=day_names[i])
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    row += 1

    # 주간 반복: 날짜 행 + 내용 행 (월~금만)
    current = week_start
    while current <= week_end:
        # 날짜 행
        for i in range(5):
            day = current + timedelta(days=i)
            label = day.strftime('%m/%d') if d_start <= day <= d_end else ''
            cell = ws.cell(row=row, column=i + 1, value=label)
            cell.font = date_font
            cell.alignment = center_align
            cell.border = thin_border
        row += 1

        # 내용 행 (분리 블록 표시 포함)
        max_lines = 1
        for i in range(5):
            day = current + timedelta(days=i)
            day_blocks = blocks_by_date.get(day.isoformat(), [])
            sections = [_block_label(b) for b in day_blocks if _block_label(b)]

            cell = ws.cell(row=row, column=i + 1, value='\n'.join(sections) if sections else '')
            cell.font = block_font
            cell.alignment = top_align
            cell.border = thin_border

            if len(sections) > max_lines:
                max_lines = len(sections)

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
