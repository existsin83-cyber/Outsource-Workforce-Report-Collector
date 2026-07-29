"""Run the pure extraction pipeline and persist reviewable records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from outsource_mail_collector.application.models import (
    CollectionError,
    ExtractionResult,
    ReviewRecord,
    review_record_from_stored,
)
from outsource_mail_collector.domain.models import MailRecord
from outsource_mail_collector.infrastructure.db.repository import (
    SQLiteRepository,
    StoredReviewRecord,
)
from outsource_mail_collector.parsing.mail_normalizer import normalize
from outsource_mail_collector.parsing.outsource_extractor import extract_work_records
from outsource_mail_collector.parsing.section_parser import split_sections
from outsource_mail_collector.parsing.validation_engine import validate
from outsource_mail_collector.parsing.work_date_parser import resolve_work_date


class ExtractionOrchestrator:
    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def process(self, mails: Iterable[MailRecord]) -> ExtractionResult:
        """Parse new messages, returning stored rows for both new and skipped mail."""

        review_records: list[ReviewRecord] = []
        skipped: list[str] = []
        errors: list[CollectionError] = []
        vendor_aliases = self._vendor_alias_map()

        for mail in mails:
            if self._repository.is_mail_processed(mail.mail_id):
                skipped.append(mail.mail_id)
                review_records.extend(
                    review_record_from_stored(row)
                    for row in self._repository.list_review_records(
                        mail_entry_id=mail.mail_id
                    )
                )
                continue
            try:
                stored = self._process_one(mail, vendor_aliases)
                review_records.extend(
                    review_record_from_stored(row) for row in stored
                )
            except (ValueError, TypeError, sqlite3.Error) as exc:
                errors.append(
                    CollectionError(
                        mail_id=mail.mail_id,
                        code="EXTRACTION_FAILED",
                        message=str(exc) or "메일 분석에 실패했습니다.",
                    )
                )

        return ExtractionResult(
            records=tuple(review_records),
            skipped_mail_ids=tuple(skipped),
            errors=tuple(errors),
        )

    def _process_one(
        self, mail: MailRecord, vendor_aliases: dict[str, str]
    ) -> list[StoredReviewRecord]:
        mail = _resolve_mail_work_date(mail)
        normalized = normalize(mail.body_text, mail.body_html)
        sections = split_sections(mail.mail_id, normalized.lines)
        rows = []
        for section in sections:
            for record in extract_work_records(section):
                canonical = _canonical_vendor(record.vendor_name, vendor_aliases)
                if canonical != record.vendor_name:
                    record = record.model_copy(update={"vendor_name": canonical})
                validation = validate(section, record)
                rows.append((section, record, validation))
        return self._repository.store_extraction(mail, rows)

    def _vendor_alias_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for vendor in self._repository.list_vendors(active_only=True):
            result[vendor.canonical_name.casefold()] = vendor.canonical_name
            for alias in vendor.aliases:
                result[alias.casefold()] = vendor.canonical_name
        return result


def _canonical_vendor(
    vendor_name: str | None, aliases: dict[str, str]
) -> str | None:
    if vendor_name is None:
        return None
    stripped = vendor_name.strip()
    return aliases.get(stripped.casefold(), stripped)


def _resolve_mail_work_date(mail: MailRecord) -> MailRecord:
    resolution = resolve_work_date(
        mail.subject, mail.body_text, mail.received_at
    )
    return mail.model_copy(
        update={
            "report_date": resolution.candidate_date,
            "subject_report_date": resolution.subject_date,
            "body_report_date": resolution.body_date,
            "report_date_source": resolution.source,
            "date_issue_codes": resolution.issue_codes,
            "work_date_confirmed": (
                resolution.source.value == "SUBJECT"
                and not resolution.requires_review
            ),
        }
    )
