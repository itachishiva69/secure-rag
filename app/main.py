import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient

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


settings = get_settings()

configure_logging(
    debug=settings.debug
)

logger = logging.getLogger(__name__)


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
    response = await call_next(request)

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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/health/qdrant")
def qdrant_health():
    client = QdrantClient(
        url=settings.qdrant_url
    )

    collections = (
        client.get_collections()
    )

    return {
        "status": "ok",
        "collections": len(
            collections.collections
        ),
    }