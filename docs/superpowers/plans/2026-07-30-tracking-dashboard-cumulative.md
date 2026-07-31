# Tracking-No Dashboard and Cumulative Ledger Implementation Plan

## Goal

Keep mail-derived work rows as reviewable source records, calculate lifetime
cumulative man-days by normalized Tracking No., and produce the final daily
table from confirmed dashboard aggregates.

## Global constraints

- Outlook remains read-only and no real Outlook, Excel, or live DB validation
  is allowed without explicit approval.
- Preserve reported, calculated, and confirmed numeric values separately.
- Use `Decimal` with one-decimal display precision.
- Cumulative identity is normalized Tracking No. only. Vendor and equipment
  never define or split a cumulative series.
- Do not infer missing Tracking No., initial baselines, mappings, or ambiguous
  numeric values.
- Final output is one row per report date and Tracking No.; same-day source
  rows are summed, while cumulative value is the lifetime result through that
  date.
- Exclusion and application-only deletion are reversible and audited.
- No commit, push, Outlook mutation, or Excel write.

## Task 1: Persistence and cumulative ledger service

- Add a persisted initial cumulative baseline keyed by normalized Tracking No.
  with effective-through date and audit timestamps.
- Add reversible soft deletion for work-report rows.
- Change cumulative series identity to Tracking No. only and recalculate all
  later included, non-deleted rows after baseline or source-state changes.
- Preserve legacy rows additively; rows without Tracking No. remain blocking.
- Add repository and service tests first, verify RED, then implement.

## Task 2: Dashboard aggregation and final-report projection

- Add application DTOs/service for Tracking-No dashboard summaries and
  date-level drill-down.
- Aggregate confirmed included/non-deleted source rows by report date and
  Tracking No.
- Validate reported cumulative against baseline plus chronological confirmed
  daily man-days.
- Make final preview and immutable confirmation snapshots use aggregated rows
  and retain all contributing source row IDs.
- Add failing aggregation/finalization tests before implementation.

## Task 3: Review and dashboard UI

- Add a dashboard management dialog reachable from the main window.
- Show Tracking No., latest date, identity fields, daily headcounts/man-days,
  baseline, reported/calculated cumulative, and validation state; provide
  date-level drill-down and baseline editing.
- Add selected-row application soft delete/restore and make exclude a
  reversible toggle.
- Keep raw mail rows visible for review and route all mutations through
  application services.
- Add failing widget/main-window tests before implementation.

## Task 4: Documentation and verification

- Record the approved behavior in a dedicated requirements/design document and
  reconcile PRD/TRD/architecture/ADR statements that conflict with it.
- Run focused tests, full pytest, compileall, and `git diff --check`.
- Append HANDOFF with decisions, changes, results, failures, real-environment
  boundaries, risks, and Git state.
