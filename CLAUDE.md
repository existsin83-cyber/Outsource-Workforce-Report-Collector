# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Windows desktop tool (PySide6) that collects outsource daily-work-report emails from Outlook,
parses them into structured records, lets a user review/correct them in a grid, then appends
approved rows to an existing Excel workbook. Korean-language domain (mail bodies, Excel columns,
user-facing text); code identifiers and comments are English/Korean mixed — match existing style
per file.

Full requirements live in `docs/PRD.md`, `docs/TRD.md`, `docs/SYSTEM_ARCHITECTURE.md`, and
**`docs/rules.md`** (non-negotiable dev rules — read this before touching parsing, Outlook, or
Excel code).

**Current status: skeleton.** Domain models, SQLite schema, adapter *interfaces* (Protocol
classes), and a rule-based extraction pipeline exist and are tested. Real Outlook COM read and
real Excel COM write are not wired up yet — `infrastructure/outlook_adapter.py` and
`excel_adapter.py` are interface-only, and the `application/` service layer (MailCollectionService,
ExtractionOrchestrator, ReviewService, ExcelExportService from the architecture doc) has not been
implemented yet. `ui/main_window.py` renders against dummy data (`ui/review_grid.py:dummy_rows`).

## Commands

```powershell
# setup
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# run the app
python -m outsource_mail_collector.app

# tests
pytest
pytest tests/test_extraction_pipeline.py
pytest tests/test_extraction_pipeline.py::test_format_b_vendor_header_per_unit_records -v

# Outlook COM PoC (reads samples/*.msg directly via Outlook COM; .msg files are local-only,
# not committed — see docs/rules.md 테스트 규칙 on not committing real mail content)
python tools/outlook_poc.py
python tools/inbox_poc.py
```

No lint/format command is configured in `pyproject.toml`; don't invent one.

## Architecture

Four layers, dependencies point inward only (`docs/rules.md` 아키텍처 규칙):

```
ui/            → PySide6 widgets. Calls application services only, never COM objects directly.
application/   → orchestration services (not yet implemented)
domain/        → pydantic models only. No PySide6/pywin32/pandas imports allowed here.
parsing/       → pure-function extraction pipeline, no Outlook/Excel objects.
infrastructure/→ Outlook COM adapter, Excel COM adapter, SQLite repository.
```

`infrastructure/outlook_adapter.py` and `infrastructure/excel_adapter.py` currently define
`Protocol` interfaces only — the real `OutlookComAdapter`/`ExcelComAdapter` implementations still
need to be written using the COM call patterns already validated in `tools/outlook_poc.py`
(`win32com.client.Dispatch`, `Namespace.GetDefaultFolder`, `Items.Restrict`, Exchange→SMTP sender
conversion).

### Extraction pipeline (`parsing/`)

```
normalize (mail_normalizer.py) → split_sections (section_parser.py)
    → extract_work_records (outsource_extractor.py) → validate (validation_engine.py)
```

- `section_parser.split_sections`: splits one mail body into per-equipment `EquipmentSection`s.
  Two author styles observed in real samples: numbered headers (`"1. ..."`, `"2. ..."`) vs.
  category+dot-bullet headers (`".고객사B ..."`), disambiguated by a known-label prefix list
  (`_FIELD_LABEL_PREFIXES`) so detail lines like `.수주번호 :` aren't mistaken for new equipment
  headers. Ambiguous splits get `split_confidence=0.6` rather than a guess — see the `ponytail:`
  comment in that file for the known limitation (freeform prose bullets can still over-split) and
  its extension point (per-author parser plugins, per `docs/SYSTEM_ARCHITECTURE.md` §9).
- `outsource_extractor.extract_work_records`: handles three real-world outsource-headcount
  notations (vendor-header-with-per-unit-lines, inline-total-manday, one-line-compact). A section
  with no outsource mention returns `[]` — that is the valid "no outsourcing" case, not an error
  (`docs/rules.md` 추출 규칙 #10).
- Never infer ambiguous numbers. When a manday figure's day/cumulative meaning isn't labeled
  (e.g. bare "총 공수"), leave the field `None` and record the raw text in `note` prefixed with
  `AMBIGUOUS_NUMBER:` instead of guessing.

### Domain rules that constrain any change (`docs/rules.md`)

- These fields are never merged into one: `actual_headcount`, `per_person_man_day`,
  `daily_man_day`, `cumulative_man_day`, `day_man_day`, `night_man_day`.
- `confidence` is 0.0–1.0; thresholds: ≥0.85 normal, 0.60–0.84 review-recommended, <0.60
  review-required (see `docs/rules.md` 신뢰도 규칙 for the weight table).
- `ReviewStatus` (domain/models.py) is the canonical review-state vocabulary — extend it there,
  don't invent parallel status strings.
- Outlook access is read-only: never delete/move mail, change read state, or auto-reply/forward.
- Nothing writes to the real Excel workbook without explicit user approval in the review grid,
  and never without a timestamped backup first (`docs/rules.md` 최우선 원칙, 9장 Excel 규칙).
- No external AI / external network calls by default (`docs/rules.md` #7). The architecture doc's
  §9 AI-adapter extension point is explicitly out of MVP scope.
- Don't hardcode fixed Excel cell addresses; map by header name, and preserve existing
  formulas/formatting/merged cells.

## Testing

- `tests/fixtures.py` holds anonymized real-mail-body fixtures as Python string constants, not
  `.txt` files — a DRM/security agent on the dev machine intercepts plain-text file reads, so
  fixtures must stay in `.py`. Follow this pattern for new fixtures; don't add `.txt` sample files.
- Never commit real personal/company data; `samples/*.msg` is local-only and gitignored.
- When changing a parser, add/extend a fixture-driven regression test in
  `tests/test_extraction_pipeline.py` rather than only asserting on synthetic minimal input.
