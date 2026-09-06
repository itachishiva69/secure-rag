import os


# ---------------------------------------------------------------------------
# Test environment
# ---------------------------------------------------------------------------
#
# The application's .env is configured for Docker/production execution.
# Pytest runs directly on the host, so service names such as "qdrant" and
# "redis" are not resolvable here.
#
# Set the host-side test environment before importing any application module.
#

os.environ["APP_ENV"] = "development"
os.environ["DEBUG"] = "false"

os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://secure_rag:secure_rag_dev@localhost:5433/secure_rag",
)

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

os.environ["STORAGE_PATH"] = "/tmp/secure-rag-test/documents"


import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


@pytest.fixture(scope="session", autouse=True)
def migrate_database():
    get_settings.cache_clear()

    try:
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "head")
        yield
    finally:
        get_settings.cache_clear()