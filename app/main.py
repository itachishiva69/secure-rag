from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.api.auth import router as auth_router
from app.api.departments import router as departments_router
from app.api.documents import router as documents_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(auth_router)
app.include_router(departments_router)
app.include_router(documents_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/health/qdrant")
def qdrant_health():
    client = QdrantClient(url=settings.qdrant_url)
    collections = client.get_collections()

    return {
        "status": "ok",
        "collections": len(collections.collections),
    }