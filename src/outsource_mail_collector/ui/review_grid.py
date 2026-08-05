"""Extended work-report review grid backed by application DTOs."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QWidget,
)

from outsource_mail_collector.application.models import WorkReportRow
from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.domain.work_report import man_day_basis
from outsource_mail_collector.ui.work_report_guidance import (
    COLUMN_HELP,
    issue_action,
    issue_detail,
    issue_title,
)


_COLUMNS = (
    "",
    "No.",
    "작업일",
    "담당자",
    "거래처명",
    "Tracking No.",
    "장비명",
    "사업팀",
    "실제 작업인원",
    "야근 인원",
    "인당 공수",
    "메일 투입",
    "계산 투입",
    "확정 투입",
    "메일 누적",
    "검증 상태",
    "포함",
    "작업",
)
_SELECT_ALL_UNCHECKED = "☐"
_SELECT_ALL_CHECKED = "☑"
_INCLUDED_COLUMN = _COLUMNS.index("포함")
_ACTIONS_COLUMN = _COLUMNS.index("작업")
_DEFAULT_BACKGROUND = QColor("#f5f5f5")
_DEFAULT_FOREGROUND = QColor("#1a1a1a")
_PROBLEM_BACKGROUND = QColor("#fff3e0")
_PROBLEM_FOREGROUND = QColor("#4a1f00")
_REVIEW_STATUS_LABELS = {
    ReviewStatus.NORMAL: "정상",
    ReviewStatus.EQUIPMENT_UNCONFIRMED: "장비명 미확인",
    ReviewStatus.TRACKING_NO_UNCONFIRMED: "Tracking No. 미확인",
    ReviewStatus.VENDOR_UNCONFIRMED: "업체명 미확인",
    ReviewStatus.HEADCOUNT_MISSING: "실제 인원 미기재",
    ReviewStatus.DAILY_MAN_DAY_MISSING: "당일 공수 미기재",
    ReviewStatus.CUMULATIVE_ONLY: "누적 공수만 존재",
    ReviewStatus.NUMBER_UNPARSABLE: "숫자 해석 불가",
    ReviewStatus.DUPLICATE_SUSPECTED: "중복 의심",
    ReviewStatus.REVISION_SUSPECTED: "수정 메일 가능성",
    ReviewStatus.FORMAT_UNSUPPORTED: "형식 미지원",
    ReviewStatus.REVIEWED: "검토 완료",
    ReviewStatus.EXCLUDED: "반영 제외",
}


class ReviewGridWidget(QTableWidget):
    """Display compilation rows while delegating decisions to application services."""

    original_requested = Signal(str)
    inclusion_requested = Signal(int, bool)
    review_requested = Signal(int)

    def __init__(
        self,
        rows: list[WorkReportRow] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        for column, name in enumerate(_COLUMNS):
            self.horizontalHeaderItem(column).setToolTip(
                COLUMN_HELP.get(name, "행을 선택하는 확인란입니다.")
            )
        self.horizontalHeaderItem(0).setText(_SELECT_ALL_UNCHECKED)
        self.horizontalHeaderItem(0).setToolTip(
            "전체 선택: 표시된 모든 행의 선택을 켜거나 끕니다."
        )
        self.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self.itemChanged.connect(
            lambda item: (
                self._sync_select_all_header() if item.column() == 0 else None
            )
        )
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # ponytail: 다크 모드에서는 팔레트 Base 색이 거의 검정이라, 선택 셀에
        # 배경/글자색을 명시하지 않으면 선택한 행이 읽을 수 없는 검은 바탕이
        # 된다(review_grid 는 문제 행에만 배경을 칠하고 나머지는 팔레트에
        # 맡기기 때문). 대시보드의 강조색(#1565c0)과 맞춘다.
        self.setStyleSheet(
            "QTableWidget {background:#f5f5f5;color:#1a1a1a;}"
            "QTableWidget::item {background:#f5f5f5;color:#1a1a1a;}"
            "QTableWidget::item:selected {background:#1565c0;color:#ffffff;}"
            "QTableWidget::item:selected:!active {background:#90caf9;color:#1a1a1a;}"
            "QTableWidget::item:focus {background:#1565c0;color:#ffffff;}"
        )
        if rows:
            self.set_rows(rows)

    def set_rows(self, rows: list[WorkReportRow]) -> None:
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._populate_row(row_index, row)
        self._sync_select_all_header()

    def set_all_checked(self, checked: bool) -> None:
        state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        for row_index in range(self.rowCount()):
            item = self.item(row_index, 0)
            if item is not None:
                item.setCheckState(state)
        self._sync_select_all_header()

    def _header_clicked(self, column: int) -> None:
        if column != 0:
            return
        self.set_all_checked(
            self.horizontalHeaderItem(0).text() != _SELECT_ALL_CHECKED
        )

    def _sync_select_all_header(self) -> None:
        all_checked = self.rowCount() > 0 and len(
            self.checked_row_ids()
        ) == self.rowCount()
        self.horizontalHeaderItem(0).setText(
            _SELECT_ALL_CHECKED if all_checked else _SELECT_ALL_UNCHECKED
        )

    def checked_row_ids(self) -> list[int]:
        result: list[int] = []
        for row_index in range(self.rowCount()):
            item = self.item(row_index, 0)
            if item is not None and item.checkState() is Qt.CheckState.Checked:
                result.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def _populate_row(self, row_index: int, row: WorkReportRow) -> None:
        selector = QTableWidgetItem()
        selector.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        selector.setCheckState(Qt.CheckState.Unchecked)
        selector.setData(Qt.ItemDataRole.UserRole, row.row_id)
        selector.setToolTip("행 선택: 현재 표시값은 선택되지 않음입니다.")
        problem = bool(row.issue_codes) and not row.warning_confirmed
        selector.setBackground(_DEFAULT_BACKGROUND)
        selector.setForeground(_DEFAULT_FOREGROUND)
        if problem:
            selector.setBackground(_PROBLEM_BACKGROUND)
            selector.setForeground(_PROBLEM_FOREGROUND)
        self.setItem(row_index, 0, selector)

        issue_text = (
            ", ".join(issue_title(issue) for issue in row.issue_codes)
            if row.issue_codes
            else _review_status_text(row.review_status)
        )
        values = (
            str(row_index + 1),
            row.work_date.isoformat() if row.work_date else "확인 필요",
            row.sender_name or "",
            row.vendor_name or "",
            row.tracking_no or "",
            row.equipment_name or "",
            row.business_team or "",
            "" if row.actual_headcount is None else str(row.actual_headcount),
            "" if row.night_headcount is None else str(row.night_headcount),
            man_day_basis(row.actual_headcount, row.night_headcount),
            _display_decimal(row.reported_daily_man_day),
            _display_decimal(row.calculated_daily_man_day),
            _display_decimal(row.confirmed_daily_man_day),
            _display_decimal(row.reported_cumulative_man_day),
            issue_text,
        )
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setBackground(_DEFAULT_BACKGROUND)
            item.setForeground(_DEFAULT_FOREGROUND)
            if problem:
                item.setBackground(_PROBLEM_BACKGROUND)
                item.setForeground(_PROBLEM_FOREGROUND)
            item.setToolTip(
                f"{COLUMN_HELP[_COLUMNS[column]]}\n현재 표시값: {value or '없음'}"
            )
            if not row.included or row.review_status is ReviewStatus.EXCLUDED:
                font = QFont(item.font())
                font.setStrikeOut(True)
                item.setFont(font)
            self.setItem(row_index, column, item)

        included = QTableWidgetItem("포함" if row.included else "제외")
        included.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        included.setFlags(included.flags() & ~Qt.ItemFlag.ItemIsEditable)
        included.setBackground(_DEFAULT_BACKGROUND)
        included.setForeground(_DEFAULT_FOREGROUND)
        included.setToolTip(
            f"{COLUMN_HELP['포함']}\n현재 표시값: {included.text()}"
        )
        if not row.included:
            font = QFont(included.font())
            font.setStrikeOut(True)
            included.setFont(font)
        if problem:
            included.setBackground(_PROBLEM_BACKGROUND)
            included.setForeground(_PROBLEM_FOREGROUND)
        self.setItem(row_index, _INCLUDED_COLUMN, included)
        status = self.item(row_index, _COLUMNS.index("검증 상태"))
        if status is not None and row.issue_codes:
            status.setToolTip(
                "\n".join(
                    f"{issue_title(issue)}: {issue_detail(issue)} "
                    f"조치: {issue_action(issue)}"
                    for issue in row.issue_codes
                )
            )
        self.setCellWidget(
            row_index, _ACTIONS_COLUMN, self._row_actions(row)
        )

    def _row_actions(self, row: WorkReportRow) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        if row.mail_entry_id:
            original = QToolButton()
            original.setText("원본")
            original.setToolTip("원본 메일: 해당 작업보고 메일을 엽니다.")
            original.clicked.connect(
                lambda _checked=False, entry_id=row.mail_entry_id: (
                    self.original_requested.emit(entry_id)
                )
            )
            layout.addWidget(original)
        review = QToolButton()
        review.setText("확인")
        review.setToolTip(
            "확인: 행을 검토하고 확정값을 입력합니다. "
            "수주 미등록 같은 구조적 문제는 먼저 설정에서 수정해야 합니다."
        )
        review.clicked.connect(
            lambda _checked=False, row_id=row.row_id: (
                self.review_requested.emit(row_id)
            )
        )
        inclusion = QToolButton()
        inclusion.setText("제외" if row.included else "제외 취소")
        inclusion.setToolTip(
            "제외: 이 행을 대시보드와 최종 표에서 제외합니다."
            if row.included
            else "제외 취소: 이 행을 다시 대시보드와 최종 표에 포함합니다."
        )
        inclusion.clicked.connect(
            lambda _checked=False, row_id=row.row_id, included=not row.included: (
                self.inclusion_requested.emit(row_id, included)
            )
        )
        layout.addWidget(review)
        layout.addWidget(inclusion)
        return container


def _display_decimal(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _review_status_text(status: ReviewStatus) -> str:
    return _REVIEW_STATUS_LABELS.get(status, "확인 필요")
