"""Domain models — no Outlook/Excel COM dependency here (see docs/rules.md 아키텍처 규칙)."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class ReviewStatus(str, Enum):
    """docs/PRD.md 에 정의된 검토 상태 어휘."""

    NORMAL = "정상"
    EQUIPMENT_UNCONFIRMED = "장비명 미확인"
    TRACKING_NO_UNCONFIRMED = "Tracking No. 미확인"
    VENDOR_UNCONFIRMED = "업체명 미확인"
    HEADCOUNT_MISSING = "실제 인원 미기재"
    DAILY_MAN_DAY_MISSING = "당일 공수 미기재"
    CUMULATIVE_ONLY = "누적 공수만 존재"
    NUMBER_UNPARSABLE = "숫자 해석 불가"
    DUPLICATE_SUSPECTED = "중복 의심"
    REVISION_SUSPECTED = "수정 메일 가능성"
    FORMAT_UNSUPPORTED = "형식 미지원"
    REVIEWED = "검토 완료"
    EXCLUDED = "반영 제외"


class MailEnvelope(BaseModel):
    """Outlook 폴더 목록 조회 결과의 최소 단위 (본문 조회 전)."""

    mail_id: str  # Outlook EntryID
    subject: str
    sender_name: str
    sender_email: str
    received_at: datetime


class MailRecord(BaseModel):
    mail_id: str
    subject: str
    sender_name: str
    sender_email: str
    received_at: datetime
    report_date: date
    body_text: str
    body_html: str
    source_folder: str
    processed_status: str = "미처리"


class EquipmentSection(BaseModel):
    section_index: int
    mail_id: str
    customer: str | None = None
    tracking_no: str | None = None
    order_no: str | None = None
    project_name: str | None = None
    equipment_name: str | None = None
    unit_no: str | None = None
    business_team: str | None = None
    section_text: str
    split_confidence: float = 0.0


class OutsourceWorkRecord(BaseModel):
    work_record_id: str
    equipment_record_id: str
    vendor_name: str | None = None
    actual_headcount: float | None = None
    day_headcount: float | None = None
    night_headcount: float | None = None
    per_person_man_day: float | None = None
    day_man_day: float | None = None
    night_man_day: float | None = None
    daily_man_day: float | None = None
    cumulative_man_day: float | None = None
    note: str | None = None
    confidence: float = 0.0
    review_status: ReviewStatus = ReviewStatus.FORMAT_UNSUPPORTED


class ValidationResult(BaseModel):
    work_record_id: str
    is_valid: bool
    issues: list[str] = []
    status: ReviewStatus


class ProcessingHistory(BaseModel):
    history_id: str
    mail_id: str
    work_record_id: str | None = None
    action: str
    before_value: str | None = None
    after_value: str | None = None
    processed_at: datetime
    result: str
    error_message: str | None = None
