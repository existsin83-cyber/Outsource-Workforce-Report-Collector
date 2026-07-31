"""Domain models and pure work-report value types."""

from outsource_mail_collector.domain.models import (
    EquipmentSection,
    MailEnvelope,
    MailRecord,
    OutsourceWorkRecord,
    ProcessingHistory,
    ReviewStatus,
    ValidationResult,
)

from outsource_mail_collector.domain.work_report import (
    IssueSeverity,
    ManDayValues,
    RowSource,
    WorkDateSource,
    WorkReportIssueCode,
)

__all__ = [
    "EquipmentSection",
    "MailEnvelope",
    "MailRecord",
    "OutsourceWorkRecord",
    "ProcessingHistory",
    "ReviewStatus",
    "ValidationResult",
    "IssueSeverity",
    "ManDayValues",
    "RowSource",
    "WorkDateSource",
    "WorkReportIssueCode",
]
