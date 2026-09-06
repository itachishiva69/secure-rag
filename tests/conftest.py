import os


os.environ["APP_ENV"] = os.getenv(
    "TEST_APP_ENV",
    "development",
)

os.environ["DEBUG"] = "false"

os.environ["TEST_DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    (
        "postgresql+psycopg://"
        "secure_rag_test:secure_rag_test_dev"
        "@localhost:5433/secure_rag_test"
    ),
)

os.environ["DATABASE_URL"] = os.environ[
    "TEST_DATABASE_URL"
]

os.environ["QDRANT_URL"] = os.getenv(
    "TEST_QDRANT_URL",
    "http://localhost:6333",
)

os.environ["REDIS_URL"] = os.getenv(
    "TEST_REDIS_URL",
    "redis://localhost:6379/0",
)

os.environ["STORAGE_PATH"] = os.getenv(
    "TEST_STORAGE_PATH",
    "/tmp/secure-rag-test/documents",
)

os.environ["TRUSTED_HOSTS"] = (
    '["testserver","test","127.0.0.1","localhost"]'
)

os.environ["CORS_ALLOWED_ORIGINS"] = (
    '["http://localhost:3000","http://127.0.0.1:8001"]'
)


import pytest

from alembic import command
from alembic.config import Config

from app.core.config import get_settings


@pytest.fixture(scope="session", autouse=True)
def migrate_database():
    get_settings.cache_clear()

    alembic_config = Config("alembic.ini")
    command.upgrade(
        alembic_config,
        "head",
    )

    yield