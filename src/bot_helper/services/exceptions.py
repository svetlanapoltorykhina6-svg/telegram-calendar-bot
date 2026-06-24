class ServiceError(Exception):
    """Base service-layer error."""


class ValidationError(ServiceError):
    """Input data is invalid."""


class SlotUnavailableError(ServiceError):
    """Requested meeting slot is not available."""
