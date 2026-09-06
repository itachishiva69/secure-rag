from app.main import get_api_documentation_urls


def test_production_disables_api_documentation():
    urls = get_api_documentation_urls(
        "production"
    )

    assert urls == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_non_production_keeps_api_documentation():
    urls = get_api_documentation_urls(
        "test"
    )

    assert urls == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


def test_development_keeps_api_documentation():
    urls = get_api_documentation_urls(
        "development"
    )

    assert urls == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }