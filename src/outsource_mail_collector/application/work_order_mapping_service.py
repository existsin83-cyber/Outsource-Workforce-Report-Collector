"""Resolve work-order master data for extracted report records."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from outsource_mail_collector.domain.work_report import WorkReportIssueCode
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    normalize_tracking_no,
)


def _normalize_equipment(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


@dataclass(frozen=True)
class WorkOrderMappingResolution:
    """Mapped master data and any validation issues for one tracking number."""

    vendor_name: str | None
    business_team: str | None
    issue_codes: tuple[WorkReportIssueCode, ...]


class WorkOrderMappingService:
    """Resolve active work-order mappings without inferring missing entries."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def resolve(
        self, tracking_no: str | None, equipment_name: str | None
    ) -> WorkOrderMappingResolution:
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
        issues: tuple[WorkReportIssueCode, ...] = ()
        if _normalize_equipment(mapping.equipment_name) != _normalize_equipment(
            equipment_name
        ):
            issues = (WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH,)
        return WorkOrderMappingResolution(
            mapping.vendor_name,
            mapping.business_team,
            issues,
        )

    @staticmethod
    def _unregistered() -> WorkOrderMappingResolution:
        return WorkOrderMappingResolution(
            None,
            None,
            (WorkReportIssueCode.WORK_ORDER_UNREGISTERED,),
        )
