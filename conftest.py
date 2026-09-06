import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://"
    "secure_rag_test:secure_rag_test_dev"
    "@localhost:5433/secure_rag_test"
)


@pytest.fixture(scope="session")
def test_engine():
    test_database_url = os.environ.get(
        "TEST_DATABASE_URL",
        DEFAULT_TEST_DATABASE_URL,
    )

    return create_engine(
        test_database_url,
        pool_pre_ping=True,
    )


@pytest.fixture(scope="session", autouse=True)
def migrate_database():
    from app.core.config import get_settings

    original_url = os.environ.get("DATABASE_URL")

    test_database_url = os.environ.get(
        "TEST_DATABASE_URL",
        DEFAULT_TEST_DATABASE_URL,
    )

    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()

    try:
        alembic_config = Config("alembic.ini")
        command.upgrade(
            alembic_config,
            "head",
        )

        yield

    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url

        get_settings.cache_clear()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()

    session_factory = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
    )

    session = session_factory()

    try:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    document_departments,
                    documents,
                    users,
                    departments
                RESTART IDENTITY
                CASCADE
                """
            )
        )

        connection.commit()

        yield session

    finally:
        session.rollback()
        session.close()
        connection.close()