from app.rag.qdrant_store import (
    ensure_collection,
    index_chunks,
    search,
)


def main():
    ensure_collection()

    chunks = [
        (
            "JWT authentication verifies the identity "
            "of a user before accessing the application."
        ),
        (
            "Engineering documents contain architecture "
            "and deployment information."
        ),
        (
            "Finance documents contain financial reports "
            "and accounting information."
        ),
    ]

    count = index_chunks(
        document_id=999,
        filename="test-document.txt",
        chunks=chunks,
        department_ids=[3],
    )

    print(f"Indexed {count} chunks.")

    results = search(
        query="How does authentication work?",
        allowed_department_ids=[3],
        limit=3,
    )

    print("\nSearch results:")

    for result in results.points:
        print(
            f"\nScore: {result.score}"
        )
        print(
            f"Payload: {result.payload}"
        )


if __name__ == "__main__":
    main()