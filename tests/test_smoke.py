from datetime import date, datetime
from pathlib import Path

from outsource_mail_collector.app import build_services
from outsource_mail_collector.domain.models import MailRecord, ReviewStatus
from outsource_mail_collector.infrastructure.db.repository import init_db


def test_mail_record_roundtrip():
    record = MailRecord(
        mail_id="abc123",
        subject="전장기술 일일 업무보고_26.07.24",
        sender_name="홍길동",
        sender_email="hong@example.com",
        received_at=datetime(2026, 7, 24, 9, 0, 0),
        report_date=date(2026, 7, 24),
        body_text="본문",
        body_html="<p>본문</p>",
        source_folder="Inbox",
    )
    assert record.processed_status == "미처리"
    assert ReviewStatus.NORMAL.value == "정상"


def test_init_db_creates_tables(tmp_path: Path):
    conn = init_db(tmp_path / "app_data.db")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "settings",
        "employees",
        "vendors",
        "processed_mails",
        "extracted_records",
        "action_logs",
    } <= tables
    conn.close()


def test_build_services_uses_requested_database(tmp_path: Path):
    db_path = tmp_path / "collector.db"

    services = build_services(db_path)

    assert db_path.exists()
    assert services.man_day_calculation_service is not None
    assert services.work_report_service is not None
    assert services.tracking_dashboard_service is not None
    assert services.final_report_service is not None
    assert services.report_renderer is not None
    assert (
        services.work_report_service._repository
        is services.final_report_service._repository
    )
    assert (
        services.tracking_dashboard_service._repository
        is services.final_report_service._repository
    )
