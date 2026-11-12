"""Turn every error into the same JSON shape: {"error": {code, message, details, request_id}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import request_id_var

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
}


def error_response(status_code: int, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": ERROR_CODES.get(status_code, "error"),
                "message": message,
                "details": details,
                "request_id": request_id_var.get(),
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    # Errors we raise ourselves (404, 409, 401, 403...)
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, str(exc.detail), headers=getattr(exc, "headers", None))

    # Bad request data caught by our Pydantic schemas (422)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(part) for part in err["loc"] if part != "body"),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return error_response(422, "Request validation failed", details)