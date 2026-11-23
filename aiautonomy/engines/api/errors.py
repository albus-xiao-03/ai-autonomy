"""Uniform 4xx bodies for the hybrid REST API (`ErrorResponse`, docs/contract.md §1).

REQ: ARCH-03
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from aiautonomy.engines.contract.common import ErrorResponse, Failure
from aiautonomy.engines.hybrid.errors import RunError
from aiautonomy.engines.world.map_store import MapStoreError


class ApiError(Exception):
    """Raise from a route to answer `status` with an `ErrorResponse`."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        failures: list[Failure] | None = None,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = ErrorResponse(
            error=Failure(code=code, entity_id=entity_id, message=message[:500]),
            failures=failures or [],
        )


def error_response(status: int, body: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    async def on_api_error(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(exc.status, exc.body)

    async def on_map_error(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, MapStoreError)
        body = ErrorResponse(
            error=Failure(code=exc.code, message=exc.message[:500]), failures=exc.failures
        )
        return error_response(exc.status, body)

    async def on_run_error(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RunError)
        body = ErrorResponse(
            error=Failure(code=exc.code, entity_id=exc.entity_id, message=exc.message[:500]),
            failures=exc.failures,
        )
        return error_response(exc.status, body)

    async def on_invalid_body(_request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        failures = [
            Failure(
                code="invalid_field",
                entity_id=".".join(str(part) for part in error.get("loc", ()))[:200] or None,
                message=str(error.get("msg", "invalid"))[:500],
            )
            for error in exc.errors()[:50]
        ]
        body = ErrorResponse(
            error=Failure(code="invalid_body", message="the request body is not valid"),
            failures=failures,
        )
        return error_response(422, body)

    app.add_exception_handler(ApiError, on_api_error)
    app.add_exception_handler(MapStoreError, on_map_error)
    app.add_exception_handler(RunError, on_run_error)
    app.add_exception_handler(RequestValidationError, on_invalid_body)
