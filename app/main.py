import logging

from fastapi import (
    FastAPI,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient

from app.api.auth import router as auth_router
from app.api.departments import (
    router as departments_router,
)
from app.api.documents import (
    router as documents_router,
)
from app.api.query import router as query_router
from app.api.users import (
    router as users_router,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import (
    normalize_request_id,
    reset_request_id,
    set_request_id,
)


configure_logging()

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name
)


@app.middleware("http")
async def request_id_middleware(
    request: Request,
    call_next,
):
    incoming_request_id = request.headers.get(
        "X-Request-ID"
    )

    request_id = normalize_request_id(
        incoming_request_id
    )

    token = set_request_id(
        request_id
    )

    request.state.request_id = request_id

    try:
        response = await call_next(
            request
        )

        response.headers[
            "X-Request-ID"
        ] = request_id

        return response

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
        "unhandled_application_exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=(
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
        content={
            "detail": (
                "An unexpected internal error "
                "occurred."
            ),
            "request_id": request_id,
        },
        headers={
            "X-Request-ID": request_id
            or "",
        },
    )


app.include_router(auth_router)
app.include_router(departments_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(users_router)


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

    collections = client.get_collections()

    return {
        "status": "ok",
        "collections": len(
            collections.collections
        ),
    }