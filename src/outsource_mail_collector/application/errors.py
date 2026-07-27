"""Application-level errors safe for the UI to translate into Korean messages."""


class ApplicationServiceError(RuntimeError):
    """Base class for application service failures."""


class OutlookCollectionError(ApplicationServiceError):
    """The Outlook session or folder query could not be completed."""


class InvalidReviewValueError(ApplicationServiceError):
    """A review edit could not be converted to the field's domain type."""


class ExcelIntegrationUnavailableError(ApplicationServiceError):
    """Excel export was requested before a real adapter was configured."""
