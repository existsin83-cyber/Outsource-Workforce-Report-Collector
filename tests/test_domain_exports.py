import outsource_mail_collector.domain as domain


def test_domain_exports_core_and_work_report_types():
    expected_exports = {
        "EquipmentSection",
        "MailEnvelope",
        "MailRecord",
        "OutsourceWorkRecord",
        "ProcessingHistory",
        "ReviewStatus",
        "ValidationResult",
        "IssueSeverity",
        "ManDayValues",
        "RowSource",
        "WorkDateSource",
        "WorkReportIssueCode",
    }

    assert domain.__doc__ == "Domain models and pure work-report value types."
    assert expected_exports <= set(domain.__all__)
    assert all(hasattr(domain, name) for name in expected_exports)
