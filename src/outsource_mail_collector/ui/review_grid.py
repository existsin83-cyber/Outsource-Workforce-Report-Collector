"""Extended work-report review grid backed by application DTOs."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

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
from outsource_mail_collector.domain.work_report import (
    WorkReportIssueCode,
    man_day_basis,
)
from outsource_mail_collector.ui.work_report_guidance import (
    COLUMN_HELP,
    issue_action,
    issue_detail,
    issue_title,
)

# 초기 메일 수집 화면은 메일 수집/본문 오류 확인만 담당한다. 이전 확정 누적값
# 확인이 필요한 이슈는 대시보드(tracking_dashboard_service)의 책임이므로 여기서는
# 표시하지 않는다.
_DASHBOARD_ONLY_ISSUE_CODES = frozenset(
    {
        WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED,
        WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION,
    }
)


_COLUMNS = (
    "",
    "No.",
    "확정",
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
)
_SELECT_ALL_UNCHECKED = "☐"
_SELECT_ALL_CHECKED = "☑"
_CONFIRM_COLUMN = _COLUMNS.index("확정")
_CONFIRM_CELL_TEXT = "확정"
_UNCONFIRMED_CELL_TEXT = "미확정"
_DEFAULT_BACKGROUND = QColor("#f5f5f5")
_DEFAULT_FOREGROUND = QColor("#1a1a1a")
_PROBLEM_BACKGROUND = QColor("#fff3e0")
_PROBLEM_FOREGROUND = QColor("#4a1f00")
_CONFIRMED_BACKGROUND = QColor("#e8f5e9")
_CONFIRMED_FOREGROUND = QColor("#1b5e20")
_CONFIRM_DONE_BACKGROUND = QColor("#2e7d32")
_CONFIRM_DONE_FOREGROUND = QColor("#ffffff")
_CONFIRM_ACTION_BACKGROUND = QColor("#e65100")
_CONFIRM_ACTION_FOREGROUND = QColor("#ffffff")
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
_SORTABLE_COLUMNS: dict[str, Callable[[WorkReportRow], Any]] = {
    "작업일": lambda row: row.work_date,
    "담당자": lambda row: row.sender_name or "",
    "거래처명": lambda row: row.vendor_name or "",
    "Tracking No.": lambda row: row.tracking_no or "",
    "장비명": lambda row: row.equipment_name or "",
    "사업팀": lambda row: row.business_team or "",
    "실제 작업인원": lambda row: row.actual_headcount,
    "야근 인원": lambda row: row.night_headcount,
    "메일 투입": lambda row: row.reported_daily_man_day,
    "계산 투입": lambda row: row.calculated_daily_man_day,
    "확정 투입": lambda row: row.confirmed_daily_man_day,
    "메일 누적": lambda row: row.reported_cumulative_man_day,
}


class ReviewGridWidget(QTableWidget):
    """Display compilation rows while delegating decisions to application services."""

    review_requested = Signal(int)
    confirm_requested = Signal(int)

    def __init__(
        self,
        rows: list[WorkReportRow] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(_COLUMNS), parent)
        self._rows: list[WorkReportRow] = []
        self._sort_column: int | None = None
        self._sort_ascending = True
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
        self.cellDoubleClicked.connect(
            lambda row_index, _column: self._emit_review(row_index)
        )
        self.cellClicked.connect(self._cell_clicked)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # ponytail: 다크 모드에서는 팔레트 Base 색이 거의 검정이라, 선택 셀에
        # 배경/글자색을 명시하지 않으면 선택한 행이 읽을 수 없는 검은 바탕이
        # 된다. 대시보드의 강조색(#1565c0)과 맞춘다.
        # 주의: QTableWidget::item 에 background/color를 직접 지정하면 Qt가
        # 각 셀에 setBackground()/setForeground()로 지정한 색(확정/문제 행
        # 배경, 확정 칸 배지 등)을 전부 무시하고 이 규칙으로 덮어써 버린다.
        # 그래서 unselected 상태 규칙은 넣지 않는다 - _populate_row가 모든
        # 셀에 배경/글자색을 명시적으로 지정하므로 기본값 없이도 회색으로
        # 보인다.
        self.setStyleSheet(
            "QTableWidget {background:#f5f5f5;color:#1a1a1a;}"
            "QTableWidget::item:selected {background:#1565c0;color:#ffffff;}"
            "QTableWidget::item:selected:!active {background:#90caf9;color:#1a1a1a;}"
            "QTableWidget::item:focus {background:#1565c0;color:#ffffff;}"
            "QScrollBar:horizontal {background:#dcdcdc;height:14px;margin:0;}"
            "QScrollBar:vertical {background:#dcdcdc;width:14px;margin:0;}"
            "QScrollBar::handle {background:#5f6b7a;border-radius:6px;}"
            "QScrollBar::handle:horizontal {min-width:48px;}"
            "QScrollBar::handle:vertical {min-height:48px;}"
            "QScrollBar::handle:hover {background:#37474f;}"
            "QScrollBar::add-line, QScrollBar::sub-line {width:0;height:0;}"
            "QScrollBar::add-page, QScrollBar::sub-page {background:#dcdcdc;}"
        )
        if rows:
            self.set_rows(rows)
        self.resizeColumnsToContents()

    def _emit_review(self, row_index: int) -> None:
        item = self.item(row_index, 0)
        if item is not None:
            self.review_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))

    def _cell_clicked(self, row_index: int, column: int) -> None:
        if column != _CONFIRM_COLUMN:
            return
        item = self.item(row_index, _CONFIRM_COLUMN)
        if item is None or item.text() != _UNCONFIRMED_CELL_TEXT:
            return
        self.confirm_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))

    def current_row_id(self) -> int | None:
        item = self.item(self.currentRow(), 0)
        return None if item is None else int(item.data(Qt.ItemDataRole.UserRole))

    def set_rows(self, rows: list[WorkReportRow]) -> None:
        self._rows = list(rows)
        self._render_rows()

    def _render_rows(self) -> None:
        self.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            self._populate_row(row_index, row)
        self._sync_select_all_header()

    def set_all_checked(self, checked: bool) -> None:
        state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        for row_index in range(self.rowCount()):
            item = self.item(row_index, 0)
            if item is not None and (
                item.flags() & Qt.ItemFlag.ItemIsUserCheckable
            ):
                item.setCheckState(state)
        self._sync_select_all_header()

    def _header_clicked(self, column: int) -> None:
        if column == 0:
            self.set_all_checked(
                self.horizontalHeaderItem(0).text() != _SELECT_ALL_CHECKED
            )
            return
        key_func = _SORTABLE_COLUMNS.get(_COLUMNS[column])
        if key_func is None or not self._rows:
            return
        if self._sort_column == column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        checked_ids = set(self.checked_row_ids())
        self._rows.sort(
            key=lambda row: (key_func(row) is None, key_func(row)),
            reverse=not self._sort_ascending,
        )
        self._render_rows()
        for row_index in range(self.rowCount()):
            item = self.item(row_index, 0)
            if item is not None and int(item.data(Qt.ItemDataRole.UserRole)) in checked_ids:
                item.setCheckState(Qt.CheckState.Checked)
        self._sync_select_all_header()

    def _sync_select_all_header(self) -> None:
        # 확정된 행은 체크 자체가 불가능하므로 선택 가능한 행만 기준으로 센다.
        selectable = sum(
            1
            for row_index in range(self.rowCount())
            if (item := self.item(row_index, 0)) is not None
            and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        )
        all_checked = selectable > 0 and len(self.checked_row_ids()) == selectable
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
        problem = bool(row.issue_codes) and not row.warning_confirmed
        confirmed = row.confirmed_daily_man_day is not None
        if confirmed:
            background, foreground = (
                _CONFIRMED_BACKGROUND,
                _CONFIRMED_FOREGROUND,
            )
        elif problem:
            background, foreground = _PROBLEM_BACKGROUND, _PROBLEM_FOREGROUND
        else:
            background, foreground = _DEFAULT_BACKGROUND, _DEFAULT_FOREGROUND

        selector = QTableWidgetItem()
        selector.setCheckState(Qt.CheckState.Unchecked)
        selector.setData(Qt.ItemDataRole.UserRole, row.row_id)
        if confirmed:
            # 이미 확정되어 대시보드로 넘어간 행은 다시 확정 대상이 될 수 없다.
            selector.setFlags(Qt.ItemFlag.NoItemFlags)
            selector.setToolTip("공수가 확정되어 대시보드에 반영된 행입니다.")
        else:
            selector.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            selector.setToolTip("행 선택: 현재 표시값은 선택되지 않음입니다.")
        selector.setBackground(background)
        selector.setForeground(foreground)
        self.setItem(row_index, 0, selector)

        no_item = QTableWidgetItem(str(row_index + 1))
        no_item.setFlags(no_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        no_item.setBackground(background)
        no_item.setForeground(foreground)
        no_item.setToolTip(
            f"{COLUMN_HELP[_COLUMNS[1]]}\n현재 표시값: {no_item.text()}"
        )
        if not row.included or row.review_status is ReviewStatus.EXCLUDED:
            font = QFont(no_item.font())
            font.setStrikeOut(True)
            no_item.setFont(font)
        self.setItem(row_index, 1, no_item)

        confirm_item = QTableWidgetItem(
            _CONFIRM_CELL_TEXT if confirmed else _UNCONFIRMED_CELL_TEXT
        )
        confirm_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        confirm_item.setFlags(confirm_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        confirm_item.setData(Qt.ItemDataRole.UserRole, row.row_id)
        font = QFont(confirm_item.font())
        font.setBold(True)
        confirm_item.setFont(font)
        if confirmed:
            # 확정 배지는 행 배경보다 진한 녹색으로 채워 눈에 확 띄게 한다.
            confirm_item.setBackground(_CONFIRM_DONE_BACKGROUND)
            confirm_item.setForeground(_CONFIRM_DONE_FOREGROUND)
            confirm_item.setToolTip("공수가 확정되어 대시보드에 반영된 행입니다.")
        else:
            # 미확정 칸은 버튼처럼 보이도록 강조색을 채워 클릭 가능함을 알린다.
            confirm_item.setBackground(_CONFIRM_ACTION_BACKGROUND)
            confirm_item.setForeground(_CONFIRM_ACTION_FOREGROUND)
            confirm_item.setToolTip("클릭하면 이 행의 공수를 확정합니다.")
        self.setItem(row_index, _CONFIRM_COLUMN, confirm_item)

        visible_issues = [
            issue
            for issue in row.issue_codes
            if issue not in _DASHBOARD_ONLY_ISSUE_CODES
        ]
        issue_text = (
            ", ".join(issue_title(issue) for issue in visible_issues)
            if visible_issues
            else _review_status_text(row.review_status)
        )
        values = (
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
        for offset, value in enumerate(values):
            column = _CONFIRM_COLUMN + 1 + offset
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setBackground(background)
            item.setForeground(foreground)
            item.setToolTip(
                f"{COLUMN_HELP[_COLUMNS[column]]}\n현재 표시값: {value or '없음'}"
            )
            if not row.included or row.review_status is ReviewStatus.EXCLUDED:
                font = QFont(item.font())
                font.setStrikeOut(True)
                item.setFont(font)
            self.setItem(row_index, column, item)

        status = self.item(row_index, _COLUMNS.index("검증 상태"))
        if status is not None and visible_issues:
            status.setToolTip(
                "\n".join(
                    f"{issue_title(issue)}: {issue_detail(issue)} "
                    f"조치: {issue_action(issue)}"
                    for issue in visible_issues
                )
            )


def _display_decimal(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


def _review_status_text(status: ReviewStatus) -> str:
    return _REVIEW_STATUS_LABELS.get(status, "확인 필요")
