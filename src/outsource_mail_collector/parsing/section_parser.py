"""장비 단위 섹션 분리.

실 샘플 메일(tools/inbox_poc.py 로 확인한 전장기술팀 업무보고) 관찰 결과, 작성자마다
스타일이 다르다:
- 번호형: "1. SK Hynix WM012H#7~#8 (청주)" 처럼 번호 줄 자체가 장비 헤더
- 카테고리+점형: "-CO2-" 같은 대분류 줄 다음에 ".대덕전자 DPS-200 #2,#3" 처럼 점(.)
  줄이 장비 헤더 (단, 같은 점(.)이 "수주번호 :", "외주 인원 :" 같은 상세 항목에도
  쓰이므로 알려진 라벨로 시작하는 줄은 헤더가 아니라 상세로 취급해야 함)

애매하면 잘못 추측하지 않고 낮은 split_confidence 로 남겨 검토 대상이 되게 한다
(docs/rules.md 추출 규칙: 애매하면 review-needed).
"""

from __future__ import annotations

import re

from outsource_mail_collector.domain.models import EquipmentSection

_NUMBERED_HEADER = re.compile(r"^\d{1,2}[.)]\s*(.+)$")
# A report date such as ``7.24 금요일 ...`` has the same punctuation as a
# numbered header, but it must stay in the mail preamble.  Keep the check
# deliberately narrow so ordinary equipment names beginning with a number
# (for example ``1. 2호기``) remain valid headers.
_NUMBERED_DATE_LINE = re.compile(
    r"^\d{1,2}[.)]\s*\d{1,2}"
    r"(?:\s*\(?\s*[월화수목금토일](?:요일)?\s*\)?|\s*(?:일일|업무보고|보고서))"
)
_DOT_BULLET = re.compile(r"^\.\s*(.+)$")
_UNIT_MARKER = re.compile(r"#\s*\d+|\d+\s*호기|\d+\s*대")

# 점(.) 으로 시작하지만 장비 헤더가 아니라 상세 항목인 줄들의 접두 라벨.
_FIELD_LABEL_PREFIXES = (
    "수주번호", "출하", "납기", "Frame", "외주", "우기", "미입고", "사업부",
    "Stage", "Handler", "LM", "Issue", "전장", "Turn", "Ez", "IO", "I/O",
    "Servo", "Safety", "구매", "제어도", "통합", "하네스", "프레임", "스테이지",
    "공수",
)


def _is_field_label_line(remainder: str) -> bool:
    return any(remainder.startswith(prefix) for prefix in _FIELD_LABEL_PREFIXES)


def _numbered_header_match(line: str) -> re.Match[str] | None:
    if _NUMBERED_DATE_LINE.match(line):
        return None
    return _NUMBERED_HEADER.match(line)


# ponytail: 서술형 진행상황 문장이 점(.) 불릿으로 쓰이는 저자(카테고리+점형, 예:
# "-CO2-" 다음 ".LOI 발행" 같은 자유 서술)는 FIELD_LABEL 목록에 없는 문장이 새 헤더로
# 오인되어 과다분할될 수 있다. docs/SYSTEM_ARCHITECTURE.md 가 이미 저자별 파서 플러그인
# (parsers/author_a_parser.py 등)을 확장 포인트로 남겨뒀으므로, 실사용 중 특정 저자의
# 오분할이 반복되면 그 확장 포인트로 개별 대응한다. 지금은 split_confidence=0.6 으로
# 검토 대상 표시만 한다.


def split_sections(mail_id: str, lines: list[str]) -> list[EquipmentSection]:
    # 번호형("1. 2. 3.") 헤더를 쓰는 메일은 장비 경계가 항상 번호 줄이고, 그 아래의
    # 점(.) 상세 줄(호기 진행상황 등)은 새 섹션이 아니다. 단, "1. PCB" 처럼 카테고리
    # 라벨로 번호를 하나만 쓰는 메일도 있어(윤현준 스타일) 번호가 2개 이상 이어질 때만
    # "번호형 목록"으로 판단한다 - 1개뿐이면 카테고리 라벨로 보고 점(.) 헤더 판별로 넘어간다.
    numbered_count = sum(1 for line in lines if _numbered_header_match(line))
    uses_numbered_headers = numbered_count >= 2
    has_bare_unit_headers = not uses_numbered_headers and any(
        not line.startswith((".", "-", "->")) and _UNIT_MARKER.search(line)
        for line in lines
    )

    sections: list[EquipmentSection] = []
    current_header: str | None = None
    current_lines: list[str] = []
    current_confidence = 0.0

    def flush() -> None:
        if current_header is not None:
            sections.append(
                EquipmentSection(
                    section_index=len(sections),
                    mail_id=mail_id,
                    equipment_name=current_header,
                    section_text="\n".join(current_lines),
                    split_confidence=current_confidence,
                )
            )

    for line in lines:
        header_text: str | None = None

        numbered_match = _numbered_header_match(line)
        if numbered_match and (uses_numbered_headers or not has_bare_unit_headers):
            header_text = numbered_match.group(1)
        elif not uses_numbered_headers:
            dot_match = _DOT_BULLET.match(line)
            if dot_match and not _is_field_label_line(dot_match.group(1)):
                header_text = dot_match.group(1)
            elif (
                not line.startswith((".", "-", "->"))
                and _UNIT_MARKER.search(line)
            ):
                header_text = line

        if header_text is not None:
            flush()
            current_header = header_text
            current_lines = [line]
            current_confidence = 1.0 if _UNIT_MARKER.search(header_text) else 0.6
        elif current_header is not None:
            current_lines.append(line)
        # 첫 헤더가 나오기 전의 인사말/카테고리 줄은 버린다.

    flush()
    return sections
