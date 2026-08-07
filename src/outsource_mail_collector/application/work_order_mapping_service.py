"""Resolve work-order master data for extracted report records."""

from __future__ import annotations

from dataclasses import dataclass

from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    normalize_tracking_no,
)


@dataclass(frozen=True)
class WorkOrderMappingResolution:
    """Mapped master data and any validation issues for one tracking number."""

    vendor_name: str | None
    business_team: str | None
    equipment_name: str | None
    issue_codes: tuple[WorkReportIssueCode, ...]


class WorkOrderMappingService:
    """Resolve active work-order mappings without inferring missing entries."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def resolve(self, tracking_no: str | None) -> WorkOrderMappingResolution:
        """Resolve master data by tracking number only.

        Equipment name is trusted from the work-order master when a mapping
        exists - the mail's own wording (e.g. "LAton58호기" vs. the master's
        "SEC LAton #58") is not compared or used, since the master registration
        is the source of truth once a tracking number is registered.
        """
        if not tracking_no:
            return self._unregistered()
        normalized = normalize_tracking_no(tracking_no)
        mapping = next(
            (
                candidate
                for candidate in self._repository.list_work_order_mappings(
                    active_only=True
                )
                if candidate.normalized_tracking_no == normalized
            ),
            None,
        )
        if mapping is None:
            return self._unregistered()
        return WorkOrderMappingResolution(
            mapping.vendor_name,
            mapping.business_team,
            mapping.equipment_name,
            (),
        )

    @staticmethod
    def _unregistered() -> WorkOrderMappingResolution:
        return WorkOrderMappingResolution(
            None,
            None,
            None,
            (WorkReportIssueCode.WORK_ORDER_UNREGISTERED,),
        )
