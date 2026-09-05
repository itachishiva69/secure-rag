from sqlalchemy import text


def test_test_database_connection(db_session):
    result = db_session.execute(
        text("SELECT 1")
    )

    assert result.scalar_one() == 1