from fastapi import HTTPException


class AppHTTPException(HTTPException):
    """HTTPException with a machine-readable error_code for the ApiResponse envelope."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code
