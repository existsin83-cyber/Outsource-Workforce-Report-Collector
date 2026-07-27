from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from outsource_mail_collector.domain.models import ReviewStatus
from outsource_mail_collector.ui.review_grid import ReviewGridWidget, dummy_rows


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_review_grid_populates_rows_and_status_widgets():
    _app()
    rows = dummy_rows()
    grid = ReviewGridWidget(rows)

    assert grid.rowCount() == len(rows)
    assert grid.columnCount() == 12

    excluded_row = next(i for i, r in enumerate(rows) if r.status is ReviewStatus.EXCLUDED)
    assert grid.item(excluded_row, 1).font().strikeOut()

    normal_row = next(i for i, r in enumerate(rows) if r.status is ReviewStatus.NORMAL)
    assert grid.cellWidget(normal_row, 10) is not None  # 상태 배지
    assert grid.cellWidget(normal_row, 9) is not None  # 신뢰도 바


def test_review_grid_retains_record_ids_for_selected_rows():
    _app()
    rows = dummy_rows()
    rows[0].record_id = 101
    grid = ReviewGridWidget(rows)
    grid.item(0, 0).setCheckState(Qt.CheckState.Checked)

    assert grid.checked_record_ids() == [101]
