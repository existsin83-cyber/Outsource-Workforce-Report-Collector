"""Collect registered employees' Outlook messages without mutating Outlook."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

try:
    import pywintypes
except ImportError:  # pragma: no cover - Outlook support is Windows-only.
    _OUTLOOK_ERRORS = (OSError, RuntimeError)
else:
    _OUTLOOK_ERRORS = (OSError, RuntimeError, pywintypes.com_error)

from outsource_mail_collector.application.errors import OutlookCollectionError
from outsource_mail_collector.application.models import CollectionError, CollectionResult
from outsource_mail_collector.infrastructure.db.repository import SQLiteRepository
from outsource_mail_collector.infrastructure.outlook_adapter import OutlookAdapter


class MailCollectionService:
    def __init__(
        self, repository: SQLiteRepository, outlook_adapter: OutlookAdapter
    ) -> None:
        self._repository = repository
        self._outlook = outlook_adapter

    def collect(self, report_date: date, folder_path: str) -> CollectionResult:
        """Read one day's registered-employee mail and calculate missing reporters."""

        employees = self._repository.list_employees(active_only=True)
        if not employees:
            return CollectionResult(
                mails=(),
                missing_employees=(),
                errors=(
                    CollectionError(
                        mail_id=None,
                        code="NO_ACTIVE_EMPLOYEES",
                        message="활성 담당자를 먼저 등록해 주세요.",
                    ),
                ),
                target_employee_count=0,
                received_mail_count=0,
            )

        start_at = datetime.combine(report_date, time.min)
        end_at = start_at + timedelta(days=1)
        try:
            self._outlook.connect()
            envelopes = self._outlook.list_messages(
                folder_path, start_at=start_at, end_at=end_at
            )
        except _OUTLOOK_ERRORS as exc:
            raise OutlookCollectionError(
                "Outlook 메일 목록을 읽을 수 없습니다. Outlook 실행 및 프로필 상태를 확인해 주세요."
            ) from exc

        employees_by_email = {employee.email: employee for employee in employees}
        matching = [
            envelope
            for envelope in envelopes
            if envelope.sender_email.strip().lower() in employees_by_email
        ]
        reporting_emails = {
            envelope.sender_email.strip().lower() for envelope in matching
        }
        missing = tuple(
            employee
            for employee in employees
            if employee.email not in reporting_emails
        )

        mails = []
        errors = []
        for envelope in matching:
            try:
                mail = self._outlook.open_message(envelope.mail_id)
                mails.append(
                    mail.model_copy(
                        update={"sender_email": mail.sender_email.strip().lower()}
                    )
                )
            except _OUTLOOK_ERRORS as exc:
                errors.append(
                    CollectionError(
                        mail_id=envelope.mail_id,
                        code="MAIL_OPEN_FAILED",
                        message=str(exc) or "메일 본문을 읽을 수 없습니다.",
                    )
                )

        return CollectionResult(
            mails=tuple(mails),
            missing_employees=missing,
            errors=tuple(errors),
            target_employee_count=len(employees),
            received_mail_count=len(matching),
        )
