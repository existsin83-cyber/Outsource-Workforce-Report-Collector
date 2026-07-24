"""외주 인원/공수 추출.

실 샘플 메일에서 확인된 3가지 표기 방식 (docs/TRD.md 가 가정한 정규식과는 다름 -
실제로는 "외주업체명:" 이라는 라벨이 거의 없고, 대신 아래 패턴들이 쓰인다):

  A. 인라인 총공수형: ".외주 인원 : 1명 (야근 : 1명) [총 공수 : 43.5 MD]"
     -> 벤더명 없음. "총 공수" 는 당일/누적 여부가 라벨로 명시되지 않으므로
        임의로 추측하지 않고 note 에 원문을 남기고 숫자 해석 불가로 남긴다.
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
import uuid

from outsource_mail_collector.domain.models import EquipmentSection, OutsourceWorkRecord

_TRACKING_NO = re.compile(r"수주번호\s*[:：]\s*([^\n]+)")
_VENDOR_HEADER = re.compile(r"외주\s*인원\s*[–\-]\s*(\S[^\n]*)")
_HEADCOUNT_INLINE = re.compile(
    r"외주\s*인원\s*[:：]?\s*(?P<count>\d+(?:\.\d+)?)\s*명"
    r"(?:\s*\(?\s*야근\s*[:：]?\s*(?P<night>\d+(?:\.\d+)?)\s*명\)?)?"
)
_TOTAL_MAN_DAY = re.compile(r"총\s*공수\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:MD|공수)?")
_CUMULATIVE_MAN_DAY = re.compile(r"누적\s*공수\s*[:：]?\s*(?P<value>\d+(?:\.\d+)?)\s*공수?")
_DAY_NIGHT_HEADCOUNT = re.compile(
    r"주간\s*(?P<day>\d+(?:\.\d+)?)\s*,?\s*야간\s*(?P<night>\d+(?:\.\d+)?)"
)
_UNIT_BLOCK = re.compile(r"^-?\s*#?\d+\s*호기\s*[:：]?\s*(?P<rest>.*)$")

AMBIGUOUS_NOTE_PREFIX = "AMBIGUOUS_NUMBER:"


def _extract_tracking_no(text: str) -> str | None:
    match = _TRACKING_NO.search(text)
    return match.group(1).strip() if match else None


def _new_record_id() -> str:
    return uuid.uuid4().hex


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
                work_record_id=_new_record_id(),
                equipment_record_id=f"{section.mail_id}:{section.section_index}",
                vendor_name=vendor_name,
                cumulative_man_day=float(cumulative_match.group("value")) if cumulative_match else None,
                confidence=0.5 if vendor_name else 0.2,
            )
        ]

    records = []
    for unit_match in unit_lines:
        rest = unit_match.group("rest")
        day_night = _DAY_NIGHT_HEADCOUNT.search(rest)
        cumulative_match = _CUMULATIVE_MAN_DAY.search(rest)
        confidence = 0.5
        confidence += 0.25 if vendor_name else 0.0
        confidence += 0.15 if day_night else 0.0
        confidence += 0.10 if cumulative_match else 0.0
        records.append(
            OutsourceWorkRecord(
                work_record_id=_new_record_id(),
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
    if not headcount_match:
        return []  # 외주 인원 언급이 전혀 없음 -> 정상적인 "외주 없음" 케이스

    total_match = _TOTAL_MAN_DAY.search(section.section_text)
    note = None
    if total_match:
        # "총 공수" 는 당일/누적 라벨이 없어 의미를 단정할 수 없음 - 추측하지 않는다.
        note = f"{AMBIGUOUS_NOTE_PREFIX} 총 공수 {total_match.group('value')}"

    confidence = 0.5 if headcount_match.group("night") is not None else 0.35

    return [
        OutsourceWorkRecord(
            work_record_id=_new_record_id(),
            equipment_record_id=f"{section.mail_id}:{section.section_index}",
            vendor_name=None,
            actual_headcount=float(headcount_match.group("count")),
            night_headcount=(
                float(headcount_match.group("night"))
                if headcount_match.group("night") is not None
                else None
            ),
            note=note,
            confidence=confidence,
        )
    ]


def extract_work_records(section: EquipmentSection) -> list[OutsourceWorkRecord]:
    """섹션 하나에서 0개 이상의 OutsourceWorkRecord 를 추출한다."""
    tracking_no = _extract_tracking_no(section.section_text)
    section.tracking_no = tracking_no

    if _VENDOR_HEADER.search(section.section_text):
        return _extract_vendor_style(section, tracking_no)
    return _extract_inline_style(section)
