"""Plain application DTOs shared between services and the presentation layer."""

from __future__ import annotations

from dataclasses import dataclass

from outsource_mail_collector.domain.models import MailRecord
from outsource_mail_collector.infrastructure.db.repository import Employee


@dataclass(frozen=True)
class CollectionError:
    mail_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class CollectionResult:
    mails: tuple[MailRecord, ...]
    missing_employees: tuple[Employee, ...]
    errors: tuple[CollectionError, ...]
