from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Outsource Mail Collector")
        self.resize(900, 600)
        self.setCentralWidget(QLabel("스켈레톤 단계 — 아직 실 Outlook/Excel 연동 없음"))
