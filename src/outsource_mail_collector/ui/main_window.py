"""메인 윈도우 — review_grid_mockup.html(사용자 승인 완료) 레이아웃 구현.

실 Outlook 조회/Excel 반영 연결은 아직 없음(TODO). 툴바 버튼과 요약 통계는
현재 더미 데이터를 그대로 보여줄 뿐이며, 서비스 계층 연결은 이후 단계에서 진행.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDate

from outsource_mail_collector.ui.review_grid import ReviewGridWidget, dummy_rows


def _build_toolbar() -> QWidget:
    bar = QWidget()
    layout = QHBoxLayout(bar)

    date_edit = QDateEdit(QDate(2026, 7, 24))
    date_edit.setCalendarPopup(True)

    folder_combo = QComboBox()
    folder_combo.addItems(["Inbox", "Inbox/전장기술팀"])

    fetch_button = QPushButton("메일 가져오기")
    settings_button = QPushButton("⚙ 설정")

    layout.addWidget(QLabel("조회 날짜"))
    layout.addWidget(date_edit)
    layout.addWidget(QLabel("폴더"))
    layout.addWidget(folder_combo)
    layout.addWidget(fetch_button)
    layout.addStretch()
    layout.addWidget(settings_button)
    return bar


def _stat_tile(title: str, value: str) -> QFrame:
    tile = QFrame()
    tile.setFrameShape(QFrame.Shape.StyledPanel)
    layout = QVBoxLayout(tile)
    value_label = QLabel(value)
    value_label.setStyleSheet("font-size: 20px; font-weight: 700;")
    title_label = QLabel(title)
    title_label.setStyleSheet("color: #666;")
    layout.addWidget(value_label)
    layout.addWidget(title_label)
    return tile


def _build_summary(rows) -> QWidget:
    total_mails = len(rows)
    normal = sum(1 for r in rows if r.status.value == "정상")
    needs_review = sum(1 for r in rows if r.status.value not in ("정상", "검토 완료", "반영 제외"))
    duplicate = sum(1 for r in rows if r.status.value == "중복 의심")

    summary = QWidget()
    layout = QHBoxLayout(summary)
    layout.addWidget(_stat_tile("대상 인원", "20"))
    layout.addWidget(_stat_tile("수신 메일", str(total_mails)))
    layout.addWidget(_stat_tile("정상", str(normal)))
    layout.addWidget(_stat_tile("검토 필요", str(needs_review)))
    layout.addWidget(_stat_tile("미보고", "1"))
    layout.addWidget(_stat_tile("중복 의심", str(duplicate)))
    return summary


def _build_missing_banner() -> QLabel:
    banner = QLabel("⚠ 미보고자 1명: 최수진")
    banner.setStyleSheet(
        "background-color: #fff3e0; color: #e65100; padding: 8px; border-radius: 4px;"
    )
    return banner


def _build_action_bar() -> QWidget:
    bar = QWidget()
    layout = QHBoxLayout(bar)
    layout.addStretch()
    for text in ("선택 항목 반영 제외", "검토 완료 처리", "Excel 반영", "처리 로그 보기"):
        layout.addWidget(QPushButton(text))
    return bar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Outsource Mail Collector")
        self.resize(1280, 720)

        rows = dummy_rows()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(_build_toolbar())
        layout.addWidget(_build_summary(rows))
        layout.addWidget(_build_missing_banner())

        self.review_grid = ReviewGridWidget(rows)
        layout.addWidget(self.review_grid)

        layout.addWidget(_build_action_bar())
        self.setCentralWidget(central)
