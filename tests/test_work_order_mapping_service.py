import pytest

from outsource_mail_collector.application.work_order_mapping_service import (
    WorkOrderMappingService,
)
from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path):
    return SQLiteRepository(tmp_path / "collector.db")


def test_exact_tracking_maps_vendor_and_team(repository):
    mapping = _mapping(repository, "AB260101", "Equipment 1")

    result = WorkOrderMappingService(repository).resolve(
        " ab 260101 ", "Equipment 1"
    )

    assert result.vendor_name == mapping.vendor_name
    assert result.business_team == "PKG"
    assert result.issue_codes == ()


def test_equipment_mismatch_keeps_mapping_and_warns(repository):
    _mapping(repository, "AB260101", "Equipment 1")

    result = WorkOrderMappingService(repository).resolve(
        "AB260101", "Equipment 2"
    )

    assert result.vendor_name == "Vendor A"
    assert result.business_team == "PKG"
    assert result.issue_codes == (
        WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH,
    )


def test_equipment_comparison_normalizes_nfkc_whitespace_and_case(repository):
    _mapping(repository, "AB260101", "Equipment Alpha 1")

    result = WorkOrderMappingService(repository).resolve(
        "AB260101", "  ｅｑｕｉｐｍｅｎｔ　Ａｌｐｈａ   １  "
    )

    assert result.vendor_name == "Vendor A"
    assert result.issue_codes == ()


def test_unregistered_tracking_is_blocked(repository):
    result = WorkOrderMappingService(repository).resolve("UNKNOWN", "Equipment 1")

    assert result.vendor_name is None
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
