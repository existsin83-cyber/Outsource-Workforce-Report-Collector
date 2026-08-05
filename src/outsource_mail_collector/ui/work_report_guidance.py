"""Korean explanations for work-report review values and issues."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from outsource_mail_collector.domain.work_report import WorkReportIssueCode


COLUMN_HELP: Mapping[str, str] = MappingProxyType({
    "No.": "화면에 표시된 행 순번입니다. 위치를 가리킬 때 사용합니다.",
    "작업일": "메일 제목과 본문에서 확인한 작업일입니다. 확인되지 않으면 사용자가 검토해야 합니다.",
    "담당자": "이 행의 근거가 된 업무보고 메일을 보낸 사람입니다. 수동 추가 행은 비어 있습니다.",
    "거래처명": "메일에서 확인한 거래처 또는 협력사 이름입니다.",
    "Tracking No.": "메일에서 확인한 작업 추적 번호입니다. Excel에 보낼 행을 식별할 때 사용합니다.",
    "장비명": "메일에서 확인한 장비 또는 호기 이름입니다.",
    "사업팀": "수주 설정에서 연결된 사업팀입니다. Excel 반영 전에 확인합니다.",
    "실제 작업인원": "메일에서 확인한 실제 작업 인원 수입니다.",
    "야근 인원": "메일에서 확인한 야간 작업 인원 수입니다. 없거나 불명확하면 확인이 필요합니다.",
    "인당 공수": "실제 작업인원과 야근 인원으로 계산한 1인 기준 공수입니다.",
    "메일 투입": "메일 본문에서 읽은 당일 투입 공수입니다.",
    "계산 투입": "작업 인원과 인당 공수를 기준으로 자동 계산한 당일 투입 공수입니다.",
    "확정 투입": "사용자가 검토·승인한 Excel 반영용 당일 투입 공수입니다.",
    "메일 누적": "메일 본문에서 읽은 누적 공수입니다.",
    "계산 누적": "이전 확정 누적 공수에 현재 확정 투입 공수를 더해 자동 계산한 누적 공수입니다.",
    "확정 누적": "사용자가 검토·승인한 Excel 반영용 누적 공수입니다.",
    "검증 상태": "메일 값과 계산값의 일치 여부, 누락, 중복 및 설정 문제를 표시합니다.",
    "포함": "체크된 행만 Excel 반영에 사용할 최종 표에 포함됩니다.",
    "작업": "원본 메일을 열거나 행을 확인·제외하는 작업을 수행합니다.",
})


_ISSUE_TITLES: dict[WorkReportIssueCode, str] = {
    WorkReportIssueCode.DATE_MISMATCH: "작업일 불일치",
    WorkReportIssueCode.DATE_SUBJECT_MISSING: "메일 제목 작업일 없음",
    WorkReportIssueCode.DATE_UNRESOLVED: "작업일 확인 필요",
    WorkReportIssueCode.DAILY_MISSING: "당일 투입 공수 없음",
    WorkReportIssueCode.DAILY_MISMATCH: "당일 투입 공수 불일치",
    WorkReportIssueCode.CUMULATIVE_MISSING: "누적 공수 없음",
    WorkReportIssueCode.CUMULATIVE_MISMATCH: "누적 공수 불일치",
    WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION: "이전 누적 기준 확인 필요",
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED: "이전 누적 기준 미확정",
    WorkReportIssueCode.DUPLICATE_UNRESOLVED: "중복 메일 확인 필요",
    WorkReportIssueCode.SERIES_KEY_MISSING: "공수 계열 식별 정보 없음",
    WorkReportIssueCode.INVALID_VALUE: "유효하지 않은 값",
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "실제 작업인원 오류",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "메일 당일 공수 오류",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: "메일 누적 공수 오류",
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED: "수주 미등록",
    WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH: "장비 수주 매핑 불일치",
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED: "야근 인원 확인 필요",
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID: "야근 인원 오류",
}

_ISSUE_DETAILS: dict[WorkReportIssueCode, str] = {
    WorkReportIssueCode.DATE_MISMATCH: "메일 제목과 본문에 서로 다른 작업일이 있습니다.",
    WorkReportIssueCode.DATE_SUBJECT_MISSING: "메일 제목에서 작업일을 확인할 수 없습니다.",
    WorkReportIssueCode.DATE_UNRESOLVED: "신뢰할 수 있는 작업일을 결정할 수 없습니다.",
    WorkReportIssueCode.DAILY_MISSING: "메일에 당일 투입 공수가 없거나 계산할 수 없습니다.",
    WorkReportIssueCode.DAILY_MISMATCH: "메일 투입 공수와 계산 투입 공수가 다릅니다.",
    WorkReportIssueCode.CUMULATIVE_MISSING: "메일에 누적 공수가 없거나 계산할 수 없습니다.",
    WorkReportIssueCode.CUMULATIVE_MISMATCH: "메일 누적 공수와 계산 누적 공수가 다릅니다.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION: "현재 누적 계산에 사용할 이전 확정 누적값을 확인해야 합니다.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED: "첫 누적 보고의 기준값이 확정되지 않았습니다.",
    WorkReportIssueCode.DUPLICATE_UNRESOLVED: "같은 보고를 가리키는 중복 후보가 있어 어느 행을 사용할지 정해야 합니다.",
    WorkReportIssueCode.SERIES_KEY_MISSING: "장비·거래처·수주를 연결할 식별 정보가 부족합니다.",
    WorkReportIssueCode.INVALID_VALUE: "하나 이상의 원본 또는 확정 값이 유효하지 않습니다.",
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "실제 작업인원이 없거나 음수 또는 형식 오류입니다.",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "메일의 당일 투입 공수를 숫자로 해석할 수 없습니다.",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: "메일의 누적 공수를 숫자로 해석할 수 없습니다.",
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED: "현재 장비와 연결된 수주가 등록되어 있지 않습니다.",
    WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH: "메일의 장비 정보와 등록된 수주 매핑이 일치하지 않습니다.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED: "야근 인원 수를 메일에서 확인할 수 없습니다.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID: "야근 인원이 실제 작업인원보다 많거나 유효하지 않습니다.",
}

_ISSUE_ACTIONS: dict[WorkReportIssueCode, str] = {
    WorkReportIssueCode.DATE_MISMATCH: "원본 메일을 열어 작업일을 확인하고 확정값을 수정하세요.",
    WorkReportIssueCode.DATE_SUBJECT_MISSING: "원본 메일을 열어 작업일을 확인하고 작업일을 입력하세요.",
    WorkReportIssueCode.DATE_UNRESOLVED: "원본 메일을 열어 작업일을 확인한 뒤 행을 수정하세요.",
    WorkReportIssueCode.DAILY_MISSING: "원본 메일을 확인하고 확정 투입 공수를 입력하세요.",
    WorkReportIssueCode.DAILY_MISMATCH: "메일값과 계산값을 비교한 뒤 확정 투입 공수를 입력하세요.",
    WorkReportIssueCode.CUMULATIVE_MISSING: "원본 메일과 이전 확정값을 확인하고 확정 누적 공수를 입력하세요.",
    WorkReportIssueCode.CUMULATIVE_MISMATCH: "메일 누적과 계산 누적의 근거를 확인하고 확정 누적 공수를 입력하세요.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_CONFIRMATION: "이전 행의 확정 누적 공수를 확인한 뒤 현재 행을 다시 계산하세요.",
    WorkReportIssueCode.CUMULATIVE_BASELINE_REQUIRED: "이전 확정 누적 공수를 확인하고 기준값을 확정하세요.",
    WorkReportIssueCode.DUPLICATE_UNRESOLVED: "중복 후보를 비교하고 사용할 행 하나만 남기거나 제외하세요.",
    WorkReportIssueCode.SERIES_KEY_MISSING: "장비명·거래처명·Tracking No.를 확인하고 누락값을 보완하세요.",
    WorkReportIssueCode.INVALID_VALUE: "문제가 표시된 값을 숫자와 필수 조건에 맞게 수정하세요.",
    WorkReportIssueCode.ACTUAL_HEADCOUNT_INVALID: "실제 작업인원을 0 이상의 정수로 확인·수정하세요.",
    WorkReportIssueCode.REPORTED_DAILY_INVALID: "원본 메일의 당일 공수를 확인하고 확정 투입값을 입력하세요.",
    WorkReportIssueCode.REPORTED_CUMULATIVE_INVALID: "원본 메일의 누적 공수를 확인하고 확정 누적값을 입력하세요.",
    WorkReportIssueCode.WORK_ORDER_UNREGISTERED: "설정에서 해당 장비의 수주를 등록한 뒤 다시 확인하세요.",
    WorkReportIssueCode.EQUIPMENT_MAPPING_MISMATCH: "설정에서 장비와 수주 매핑을 확인·수정한 뒤 다시 확인하세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_UNRESOLVED: "원본 메일을 확인하고 야근 인원을 입력하거나 확인 필요로 남기세요.",
    WorkReportIssueCode.NIGHT_HEADCOUNT_INVALID: "야근 인원이 실제 작업인원을 넘지 않도록 확인·수정하세요.",
}


def _value(code: Any) -> str:
    return str(getattr(code, "value", code))


def _lookup(mapping: dict[WorkReportIssueCode, str], code: WorkReportIssueCode) -> str:
    return mapping.get(code, _value(code))


def issue_title(code: WorkReportIssueCode) -> str:
    """Return the Korean issue title, or the stable code for unknown issues."""

    return _lookup(_ISSUE_TITLES, code)


def issue_detail(code: WorkReportIssueCode) -> str:
    """Return the Korean issue explanation, or the stable code for unknown issues."""

    return _lookup(_ISSUE_DETAILS, code)


def issue_action(code: WorkReportIssueCode) -> str:
    """Return the Korean corrective action, or the stable code for unknown issues."""

    return _lookup(_ISSUE_ACTIONS, code)
