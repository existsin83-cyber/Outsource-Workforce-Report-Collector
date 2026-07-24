"""HTML/plain 본문을 정제된 줄 목록으로 변환한다. Outlook/Excel 의존 없음."""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

_NBSP = " "


@dataclass
class NormalizedMailBody:
    plain_text: str
    lines: list[str]


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.append("\n")
    return soup.get_text("\n")


def normalize(body_text: str, html_body: str = "") -> NormalizedMailBody:
    """plain body가 있으면 그대로 쓰고, 없으면(RTF-only 등) HTML에서 텍스트를 뽑는다."""
    text = body_text.strip() if body_text and body_text.strip() else _html_to_text(html_body)
    text = text.replace(_NBSP, " ")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return NormalizedMailBody(plain_text=text, lines=lines)
