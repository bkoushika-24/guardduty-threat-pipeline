class RetryableProcessingError(Exception):
    """Temporary failure; the SQS message should be retried."""


class PermanentProcessingError(Exception):
    """Invalid message; retries are unlikely to help."""
