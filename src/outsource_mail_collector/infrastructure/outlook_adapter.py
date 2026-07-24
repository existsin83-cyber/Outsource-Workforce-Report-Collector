"""Outlook 어댑터 인터페이스.

실제 구현(OutlookComAdapter)은 tools/outlook_poc.py 에서 검증한 COM 호출 방식
(win32com.client.Dispatch, Namespace.GetDefaultFolder, Items.Restrict, EX 발신자
SMTP 변환)을 그대로 사용해 다음 단계에서 채운다. 읽기 전용만 허용 — 삭제/이동/
읽음상태 변경/자동응답 금지 (docs/rules.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from outsource_mail_collector.domain.models import MailEnvelope, MailRecord


class OutlookAdapter(Protocol):
    def connect(self) -> None:
        """Outlook 세션에 연결한다. 실패 시 애플리케이션 예외로 변환해 던진다."""
        ...

    def list_messages(
        self, folder_path: str, start_at: datetime, end_at: datetime
    ) -> list[MailEnvelope]:
        """지정 폴더에서 날짜 범위 내 메일 목록만 조회한다 (본문 미포함)."""
        ...

    def open_message(self, entry_id: str) -> MailRecord:
        """단건 메일 본문을 읽어온다. 읽음 상태를 변경하지 않는다."""
        ...
