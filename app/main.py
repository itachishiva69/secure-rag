import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.departments import router as departments_router
from app.api.documents import router as documents_router
from app.api.query import router as query_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.logging import (
    configure_logging,
    is_valid_request_id,
)
from app.core.request_context import (
    reset_request_id,
    set_request_id,
)
from app.db.database import engine
from app.services.queue import get_redis


settings = get_settings()

configure_logging(
    debug=settings.debug
)

logger = logging.getLogger(__name__)


class RequestBodyTooLarge(Exception):
    """Raised when a request body exceeds the configured limit."""


class RequestBodyLimitMiddleware:
    def __init__(
        self,
        app,
        *,
        max_body_size: int,
    ):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        content_length = None

        for key, value in scope.get(
            "headers",
            [],
        ):
            if key.lower() == b"content-length":
                content_length = value
                break

        if content_length is not None:
            try:
                declared_length = int(
                    content_length
                )
            except (TypeError, ValueError):
                response = JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid Content-Length"
                    },
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            if declared_length < 0:
                response = JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid Content-Length"
                    },
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

            if declared_length > self.max_body_size:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "Request body is too large. "
                            "The maximum allowed size is "
                            f"{settings.max_request_body_size_mb} MB."
                        )
                    },
                )

                await response(
                    scope,
                    receive,
                    send,
                )
                return

        received_size = 0

        async def limited_receive():
            nonlocal received_size

            message = await receive()

            if message.get(
                "type"
            ) != "http.request":
                return message

            body = message.get(
                "body",
                b"",
            )

            received_size += len(body)

            if received_size > self.max_body_size:
                raise RequestBodyTooLarge()

            return message

        try:
            await self.app(
                scope,
                limited_receive,
                send,
            )

        except RequestBodyTooLarge:
            response = JSONResponse(
                status_code=413,
                content={
                    "detail": (
                        "Request body is too large. "
                        "The maximum allowed size is "
                        f"{settings.max_request_body_size_mb} MB."
                    )
                },
            )

            await response(
                scope,
                receive,
                send,
            )


app = FastAPI(
    title=settings.app_name,
)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
    ],
    expose_headers=[
        "X-Request-ID",
    ],
)

app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_size=(
        settings.max_request_body_size_mb
        * 1024
        * 1024
    ),
)


app.include_router(
    auth_router
)

app.include_router(
    departments_router
)

app.include_router(
    documents_router
)

app.include_router(
    query_router
)

app.include_router(
    users_router
)


@app.middleware("http")
async def security_headers_middleware(
    request: Request,
    call_next,
):
    response = await call_next(
        request
    )

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), "
        "microphone=(), "
        "geolocation=()"
    )

    if settings.app_env == "production":
        response.headers[
            "Strict-Transport-Security"
        ] = (
            "max-age=31536000; "
            "includeSubDomains"
        )

    return response


@app.middleware("http")
async def request_id_middleware(
    request: Request,
    call_next,
):
    incoming_request_id = (
        request.headers.get(
            "X-Request-ID"
        )
    )

    if is_valid_request_id(
        incoming_request_id
    ):
        request_id = incoming_request_id
    else:
        request_id = str(uuid4())

    request.state.request_id = (
        request_id
    )

    token = set_request_id(
        request_id
    )

    started_at = perf_counter()

    logger.info(
        "http_request_started",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
    )

    try:
        response = await call_next(
            request
        )

        duration_ms = round(
            (
                perf_counter()
                - started_at
            )
            * 1000,
            2,
        )

        logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": (
                    response.status_code
                ),
                "duration_ms": duration_ms,
            },
        )

        response.headers[
            "X-Request-ID"
        ] = request_id

        return response

    except Exception:
        duration_ms = round(
            (
                perf_counter()
                - started_at
            )
            * 1000,
            2,
        )

        logger.exception(
            "http_request_failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )

        raise

    finally:
        reset_request_id(token)


@app.exception_handler(
    RequestValidationError
)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    request_id = getattr(
        request.state,
        "request_id",
        None,
    )

    logger.warning(
        "request_validation_failed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "error_count": len(
                exc.errors()
            ),
        },
    )

    response = JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(
                exc.errors()
            )
        },
    )

    if request_id:
        response.headers[
            "X-Request-ID"
        ] = request_id

    return response


@app.exception_handler(
    HTTPException
)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    request_id = getattr(
        request.state,
        "request_id",
        None,
    )

    logger.info(
        "http_exception",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
        },
    )

    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
        },
        headers=(
            dict(exc.headers)
            if exc.headers
            else None
        ),
    )

    if request_id:
        response.headers[
            "X-Request-ID"
        ] = request_id

    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = getattr(
        request.state,
        "request_id",
        None,
    )

    logger.exception(
        "unhandled_exception",
        extra={
            "method": request.method,
            "path": request.url.path,
        },
        exc_info=(
            type(exc),
            exc,
            exc.__traceback__,
        ),
    )

    response = JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )

    if request_id:
        response.headers[
            "X-Request-ID"
        ] = request_id

    return response


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT 1")
        )


def check_redis() -> None:
    get_redis().ping()


def check_qdrant() -> None:
    client = QdrantClient(
        url=settings.qdrant_url
    )

    try:
        client.get_collections()
    finally:
        client.close()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/ready")
def readiness():
    dependency_checks = {
        "database": check_database,
        "redis": check_redis,
        "qdrant": check_qdrant,
    }

    failed_dependencies = []

    for dependency_name, check in (
        dependency_checks.items()
    ):
        try:
            check()

        except Exception:
            failed_dependencies.append(
                dependency_name
            )

            logger.exception(
                "readiness_dependency_failed",
                extra={
                    "dependency": dependency_name,
                },
            )

    if failed_dependencies:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "failed_dependencies": (
                    failed_dependencies
                ),
            },
        )

    return {
        "status": "ready",
    }


@app.get("/health/qdrant")
def qdrant_health():
    try:
        check_qdrant()

    except Exception:
        logger.exception(
            "qdrant_health_check_failed"
        )

        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
            },
        )

    return {
        "status": "ok",
    }