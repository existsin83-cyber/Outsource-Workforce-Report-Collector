"""리뷰 그리드 위젯.

승인된 review_grid_mockup.html 레이아웃을 PySide6 로 그대로 옮긴다. 실 Outlook
조회/추출 파이프라인과의 연결은 아직 없고(TODO), 지금은 더미 데이터로 그리드
구성 자체(체크박스/편집 가능 셀/신뢰도 바/상태 배지/행 액션)만 검증한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from outsource_mail_collector.domain.models import ReviewStatus

_COLUMNS = [
    "",
    "보고일자",
    "작성자",
    "장비명",
    "수주번호/Tracking No.",
    "외주업체명",
    "실제 인원",
    "당일 공수",
    "누적 공수",
    "신뢰도",
    "상태",
    "작업",
]

# 편집 가능한(더블클릭으로 값 수정) 컬럼 인덱스 — 목업의 점선 밑줄 셀.
_EDITABLE_COLUMNS = {3, 4, 5, 6, 7, 8}

_STATUS_COLORS: dict[ReviewStatus, tuple[str, str]] = {
    ReviewStatus.NORMAL: ("#2e7d32", "#e8f5e9"),
    ReviewStatus.REVIEWED: ("#1565c0", "#e3f2fd"),
    ReviewStatus.EXCLUDED: ("#757575", "#eeeeee"),
    ReviewStatus.DUPLICATE_SUSPECTED: ("#c62828", "#ffebee"),
    ReviewStatus.REVISION_SUSPECTED: ("#c62828", "#ffebee"),
}
_DEFAULT_STATUS_COLOR = ("#e65100", "#fff3e0")  # 미확인/누락/해석불가 등 검토 필요류


def _status_colors(status: ReviewStatus) -> tuple[str, str]:
    return _STATUS_COLORS.get(status, _DEFAULT_STATUS_COLOR)


@dataclass
class ReviewRow:
    """그리드 한 행 — OutsourceWorkRecord + EquipmentSection + MailRecord 조인 결과(추후 서비스 계층에서 구성)."""

    report_date: str
    author: str
    equipment_name: str
    tracking_no: str
    vendor_name: str
    actual_headcount: str
    daily_man_day: str
    cumulative_man_day: str
    confidence: float
    status: ReviewStatus


def _confidence_bar(confidence: float) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(round(confidence * 100))
    bar.setTextVisible(True)
    bar.setFormat("%p%")
    if confidence >= 0.8:
        chunk_color = "#2e7d32"
    elif confidence >= 0.5:
        chunk_color = "#f9a825"
    else:
        chunk_color = "#c62828"
    bar.setStyleSheet(
        f"QProgressBar {{ border: 1px solid #ccc; border-radius: 4px; text-align: center; }}"
        f"QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 4px; }}"
    )
    return bar


def _status_badge(status: ReviewStatus) -> QLabel:
    fg, bg = _status_colors(status)
    label = QLabel(status.value)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border-radius: 8px; padding: 2px 8px; font-weight: 600;"
    )
    return label


def _row_actions() -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    for text in ("원본", "제외"):
        button = QToolButton()
        button.setText(text)
        button.setAutoRaise(True)
        layout.addWidget(button)
    return container


class ReviewGridWidget(QTableWidget):
    def __init__(self, rows: list[ReviewRow] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        if rows:
            self.set_rows(rows)

    def set_rows(self, rows: list[ReviewRow]) -> None:
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._populate_row(row_index, row)

    def _populate_row(self, row_index: int, row: ReviewRow) -> None:
        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check_item.setCheckState(Qt.CheckState.Unchecked)
        self.setItem(row_index, 0, check_item)

        values = [
            row.report_date,
            row.author,
            row.equipment_name,
            row.tracking_no,
            row.vendor_name,
            row.actual_headcount,
            row.daily_man_day,
            row.cumulative_man_day,
        ]
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(value)
            if column not in _EDITABLE_COLUMNS:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if row.status is ReviewStatus.EXCLUDED:
                font = QFont()
                font.setStrikeOut(True)
                item.setFont(font)
            self.setItem(row_index, column, item)

        self.setCellWidget(row_index, 9, _confidence_bar(row.confidence))
        self.setCellWidget(row_index, 10, _status_badge(row.status))
        self.setCellWidget(row_index, 11, _row_actions())


# ponytail: 실 서비스 계층(Outlook 조회 -> 파싱 -> DB 저장) 연결 전까지 그리드 구성
# 검증용 더미 데이터. main_window 가 이 함수를 호출해 초기 화면을 채운다.
def dummy_rows() -> list[ReviewRow]:
    return [
        ReviewRow("2026-07-24", "홍길동", "ABC-200 #2", "XX260301", "협력사A", "2", "4.0", "18.5", 0.95, ReviewStatus.NORMAL),
        ReviewRow("2026-07-24", "김철수", "모델X #7", "MK260307", "협력사A", "-", "-", "18.5", 0.55, ReviewStatus.CUMULATIVE_ONLY),
        ReviewRow("2026-07-24", "이영희", "ABF Shaving #2", "ZZ260321", "-", "1", "-", "-", 0.40, ReviewStatus.VENDOR_UNCONFIRMED),
        ReviewRow("2026-07-24", "박원준", "CO2 DRILLER #4", "XX260310", "훈원테크", "3", "총공수 55.5(모호)", "-", 0.30, ReviewStatus.NUMBER_UNPARSABLE),
        ReviewRow("2026-07-24", "임현진", "모델Y #1", "ME260501", "협력사B", "8", "35.0", "35.0", 0.90, ReviewStatus.DUPLICATE_SUSPECTED),
        ReviewRow("2026-07-24", "박기덕", "모델W", "ZZ260202", "협력사C", "5", "6.0", "40.0", 0.85, ReviewStatus.REVIEWED),
        ReviewRow("2026-07-24", "김철수", "모델X #8", "ZZ260317", "협력사A", "4", "4.0", "9.0", 0.90, ReviewStatus.NORMAL),
        ReviewRow("2026-07-23", "홍길동", "ABC-400 (제외됨)", "-", "-", "-", "-", "-", 0.20, ReviewStatus.EXCLUDED),
    ]
