import pytest

from outsource_mail_collector.application.work_order_mapping_service import (
    WorkOrderMappingService,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path):
    return SQLiteRepository(tmp_path / "collector.db")


def test_exact_tracking_maps_vendor_team_and_equipment_name(repository):
    mapping = _mapping(repository, "AB260101", "Equipment 1")

    result = WorkOrderMappingService(repository).resolve(" ab 260101 ")

    assert result.vendor_name == mapping.vendor_name
    assert result.business_team == "PKG"
    assert result.equipment_name == "Equipment 1"
    assert result.issue_codes == ()


def test_master_equipment_name_wins_even_when_mail_wording_differs(repository):
    """The master registration is the source of truth once a tracking number
    is registered - the mail's own equipment wording is not consulted."""
    _mapping(repository, "AB260101", "SEC LAton #58")

    result = WorkOrderMappingService(repository).resolve("AB260101")

    assert result.equipment_name == "SEC LAton #58"
    assert result.issue_codes == ()


def test_unregistered_tracking_is_blocked_and_has_no_equipment_name(repository):
    result = WorkOrderMappingService(repository).resolve("UNKNOWN")

    assert result.vendor_name is None
    assert result.equipment_name is None
    assert result.issue_codes == (WorkReportIssueCode.WORK_ORDER_UNREGISTERED,)


def _mapping(repository: SQLiteRepository, tracking_no: str, equipment_name: str):
    vendor = repository.save_vendor(None, "Vendor A", [], True)
    return repository.save_work_order_mapping(
        None,
        tracking_no,
        equipment_name,
        vendor.vendor_id,
        "PKG",
        True,
    )
