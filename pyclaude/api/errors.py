from __future__ import annotations


RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429})


class APIError(Exception):
    pass


class APITransportError(APIError):
    pass


class APIResponseError(APIError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def is_retryable_error(error: BaseException) -> bool:
    if isinstance(error, APITransportError):
        return True
    if not isinstance(error, APIResponseError):
        return False
    return error.status_code in RETRYABLE_STATUS_CODES or error.status_code >= 500
