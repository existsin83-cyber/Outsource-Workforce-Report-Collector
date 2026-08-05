"""외주 인원/공수 추출.

실 샘플 메일에서 확인된 3가지 표기 방식 (docs/TRD.md 가 가정한 정규식과는 다름 -
실제로는 "외주업체명:" 이라는 라벨이 거의 없고, 대신 아래 패턴들이 쓰인다):

  A. 인라인 총공수형: ".외주 인원 : 1명 (야근 : 1명) [총 공수 : 43.5 MD]"
     -> 벤더명 없음. "총 공수"/"총 투입 공수" 는 사용자 확인 결과 누적 공수를 뜻하므로
        누적으로 해석한다 (docs/rules.md 추출 규칙의 명시적 예외).
        같은 줄에 "누적 공수" 라벨이 있으면 그 값이 우선한다.
  B. 업체명 헤더 + 호기별 상세형: ".외주인원 – 협력사A" 다음 줄들에
     "- #7호기 : 누적공수 : 18.5공수" 처럼 호기별 라인이 이어짐.
     -> 호기별로 별도 OutsourceWorkRecord 생성.
  C. 한 줄 압축형: "수주번호 : ZZ260203 외주인원 : 6명 (야근 : 6명)"
     -> 공수 자체가 아예 없음 (실 인원만 보고).

외주 언급이 전혀 없는 섹션은 정상적인 "외주 없음" 상태이므로 레코드를 만들지 않는다
(docs/rules.md 추출 규칙 10번).
"""

from __future__ import annotations

import re

from outsource_mail_collector.domain.models import EquipmentSection, OutsourceWorkRecord

_TRACKING_NO = re.compile(
    r"수주번호\s*[:：]\s*(.+?)(?=\s*외주\s*인원|\s*$)", re.MULTILINE
)
_VENDOR_HEADER = re.compile(r"외주\s*인원\s*[–\-]\s*(\S[^\n]*)")
_HEADCOUNT_INLINE = re.compile(
    r"외주\s*인원\s*[:：]?\s*(?P<count>\d+(?:\.\d+)?)\s*명"
    r"(?:\s*\(?\s*야근\s*[:：]?\s*(?P<night>\d+(?:\.\d+)?)\s*명\)?)?"
)
_TOTAL_MAN_DAY = re.compile(
    r"(?P<label>총(?:\s*투입)?\s*공수)\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:MD|공수)?"
)
_DAILY_MAN_DAY = re.compile(
    r"투입\s*공수\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:MD|공수)?"
)
_CUMULATIVE_MAN_DAY = re.compile(
    r"누적\s*공수\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:MD|공수)?"
)
_DAY_NIGHT_HEADCOUNT = re.compile(
    r"주간\s*(?P<day>\d+(?:\.\d+)?)\s*명?\s*,?\s*야간\s*(?P<night>\d+(?:\.\d+)?)\s*명?"
)
_UNIT_BLOCK = re.compile(r"^-?\s*#?\d+\s*호기\s*[:：]?\s*(?P<rest>.*)$")

AMBIGUOUS_NOTE_PREFIX = "AMBIGUOUS_NUMBER:"


def _extract_tracking_no(text: str) -> str | None:
    match = _TRACKING_NO.search(text)
    if not match:
        return None
    return match.group(1).strip().rstrip(",") or None


def _record_id(section: EquipmentSection, ordinal: int) -> str:
    # ponytail: deterministic key so re-parsing the same mail (re-collect,
    # parser fix) maps back onto the same stored row instead of duplicating
    # it. Ceiling: if section splitting changes the ordinal count for the
    # same mail, old ids go stale -> repository re-parse cleans those up as
    # unmatched rows (see store_extraction).
    return f"{section.mail_id}:{section.section_index}:{ordinal}"


def _extract_vendor_style(section: EquipmentSection, tracking_no: str | None) -> list[OutsourceWorkRecord]:
    vendor_match = _VENDOR_HEADER.search(section.section_text)
    vendor_name = vendor_match.group(1).strip() if vendor_match else None

    unit_lines = [
        m for line in section.section_text.splitlines() if (m := _UNIT_BLOCK.match(line))
    ]
    if not unit_lines:
        cumulative_match = _CUMULATIVE_MAN_DAY.search(section.section_text)
        return [
            OutsourceWorkRecord(
                work_record_id=_record_id(section, 0),
                equipment_record_id=f"{section.mail_id}:{section.section_index}",
                vendor_name=vendor_name,
                cumulative_man_day=float(cumulative_match.group("value")) if cumulative_match else None,
                confidence=0.5 if vendor_name else 0.2,
            )
        ]

    records = []
    for ordinal, unit_match in enumerate(unit_lines):
        rest = unit_match.group("rest")
        day_night = _DAY_NIGHT_HEADCOUNT.search(rest)
        cumulative_match = _CUMULATIVE_MAN_DAY.search(rest)
        confidence = 0.5
        confidence += 0.25 if vendor_name else 0.0
        confidence += 0.15 if day_night else 0.0
        confidence += 0.10 if cumulative_match else 0.0
        records.append(
            OutsourceWorkRecord(
                work_record_id=_record_id(section, ordinal),
                equipment_record_id=f"{section.mail_id}:{section.section_index}",
                vendor_name=vendor_name,
                day_headcount=float(day_night.group("day")) if day_night else None,
                night_headcount=float(day_night.group("night")) if day_night else None,
                cumulative_man_day=float(cumulative_match.group("value")) if cumulative_match else None,
                confidence=min(confidence, 1.0),
            )
        )
    return records


def _extract_inline_style(section: EquipmentSection) -> list[OutsourceWorkRecord]:
    headcount_match = _HEADCOUNT_INLINE.search(section.section_text)
    day_night_match = _DAY_NIGHT_HEADCOUNT.search(section.section_text)
    cumulative_match = _CUMULATIVE_MAN_DAY.search(section.section_text)
    total_matches = list(_TOTAL_MAN_DAY.finditer(section.section_text))
    total_match = total_matches[0] if total_matches else None
    if not headcount_match and not day_night_match and not (cumulative_match or total_match):
        return []  # 외주 인원 언급이 전혀 없음 -> 정상적인 "외주 없음" 케이스

    cumulative_match = _CUMULATIVE_MAN_DAY.search(section.section_text)
    total_matches = list(_TOTAL_MAN_DAY.finditer(section.section_text))
    total_match = total_matches[0] if total_matches else None
    daily_match = next(
        (
            candidate
            for candidate in _DAILY_MAN_DAY.finditer(section.section_text)
            if not any(
                total.start() <= candidate.start() < total.end()
                for total in total_matches
            )
        ),
        None,
    )
    # "누적 공수" 라벨이 명시적으로 있으면 그 값을 쓴다. 없으면 "총 공수"/
    # "총 투입 공수" 를 누적으로 해석한다 (사용자 확인: 실제 표기 관행).
    if cumulative_match:
        cumulative_man_day = float(cumulative_match.group("value"))
    elif total_match:
        cumulative_man_day = float(total_match.group("value"))
    else:
        cumulative_man_day = None

    if headcount_match:
        actual_headcount = float(headcount_match.group("count"))
        night_headcount = (
            float(headcount_match.group("night"))
            if headcount_match.group("night") is not None
            else None
        )
        confidence = 0.5 if night_headcount is not None else 0.35
    elif day_night_match:
        actual_headcount = float(day_night_match.group("day"))
        night_headcount = float(day_night_match.group("night"))
        confidence = 0.45
    else:
        actual_headcount = None
        night_headcount = None
        confidence = 0.25

    if cumulative_man_day is not None:
        confidence += 0.10

    return [
        OutsourceWorkRecord(
            work_record_id=_record_id(section, 0),
            equipment_record_id=f"{section.mail_id}:{section.section_index}",
            vendor_name=None,
            actual_headcount=actual_headcount,
            night_headcount=night_headcount,
            daily_man_day=(
                float(daily_match.group("value")) if daily_match else None
            ),
            cumulative_man_day=cumulative_man_day,
            confidence=min(confidence, 1.0),
        )
    ]


def extract_work_records(section: EquipmentSection) -> list[OutsourceWorkRecord]:
    """섹션 하나에서 0개 이상의 OutsourceWorkRecord 를 추출한다."""
    tracking_no = _extract_tracking_no(section.section_text)
    # Extraction should not erase metadata populated by an earlier pipeline
    # stage when this section's current text has no tracking-number label.
    if tracking_no is not None:
        section.tracking_no = tracking_no

    if _VENDOR_HEADER.search(section.section_text):
        return _extract_vendor_style(section, tracking_no)
    return _extract_inline_style(section)
