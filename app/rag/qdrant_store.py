from uuid import UUID, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_service


settings = get_settings()


client = QdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key,
)


# Fixed namespace used to generate deterministic UUIDs.
# Do not change this after vectors have been created.
UUID_NAMESPACE = UUID(
    "00000000-0000-0000-0000-000000000001"
)


class QdrantStoreError(Exception):
    """Raised when the Qdrant vector store cannot complete an operation."""


def _qdrant_call(
    *,
    operation: str,
    func,
):
    """
    Execute a Qdrant client operation and convert dependency
    failures into the application's vector-store error.

    The exception details are preserved as the cause for logging,
    while callers receive a stable application-level exception.
    """
    try:
        return func()
    except Exception as exc:
        raise QdrantStoreError(
            f"Qdrant {operation} failed"
        ) from exc


def _collection_exists() -> bool:
    """
    Return whether the configured collection exists.
    """
    collections = _qdrant_call(
        operation="collection lookup",
        func=client.get_collections,
    )

    return any(
        collection.name == settings.qdrant_collection
        for collection in collections.collections
    )


def _ensure_payload_indexes() -> None:
    """
    Ensure all payload fields used by Qdrant filters have indexes.

    The collection may have been created before payload indexes
    were introduced, so this check must run even when the collection
    already exists.

    Current filtered fields:

        document_id: integer
        department_ids: integer
    """
    collection_info = _qdrant_call(
        operation="collection inspection",
        func=lambda: client.get_collection(
            collection_name=settings.qdrant_collection,
        ),
    )

    payload_schema = (
        collection_info.payload_schema or {}
    )

    required_indexes = {
        "document_id": PayloadSchemaType.INTEGER,
        "department_ids": PayloadSchemaType.INTEGER,
    }

    for field_name, field_schema in required_indexes.items():
        if field_name in payload_schema:
            continue

        def create_index(
            field_name=field_name,
            field_schema=field_schema,
        ):
            return client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=field_schema,
            )

        _qdrant_call(
            operation=(
                f"payload index creation for {field_name}"
            ),
            func=create_index,
        )


def ensure_collection() -> None:
    """
    Create the Qdrant collection if it does not already exist.

    Also ensures all payload indexes required by the application.
    This intentionally runs for existing collections too so that
    deployments can upgrade an existing Qdrant collection schema.
    """
    embedding_service = get_embedding_service()

    if not _collection_exists():
        _qdrant_call(
            operation="collection creation",
            func=lambda: client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=embedding_service.dimension,
                    distance=Distance.COSINE,
                ),
            ),
        )

    _ensure_payload_indexes()


def delete_document_vectors(
    document_id: int,
) -> None:
    """
    Delete all Qdrant vectors belonging to a document.
    """
    if not _collection_exists():
        return

    ensure_collection()

    _qdrant_call(
        operation="document vector deletion",
        func=lambda: client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match={
                            "value": document_id,
                        },
                    )
                ]
            ),
        ),
    )


def index_chunks(
    *,
    document_id: int,
    filename: str,
    chunks: list[str],
    department_ids: list[int],
) -> int:
    """
    Generate embeddings for document chunks and store them in Qdrant.

    Each chunk receives a deterministic UUID based on:

        document_id + chunk_index

    Re-indexing the same document therefore produces the same point IDs.
    """
    if not chunks:
        return 0

    ensure_collection()

    embedding_service = get_embedding_service()

    embeddings = embedding_service.embed_documents(
        chunks
    )

    points = []

    for index, (chunk, embedding) in enumerate(
        zip(chunks, embeddings)
    ):
        point_id = str(
            uuid5(
                UUID_NAMESPACE,
                f"{document_id}:{index}",
            )
        )

        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": index,
                    "department_ids": department_ids,
                    "text": chunk,
                },
            )
        )

    _qdrant_call(
        operation="chunk indexing",
        func=lambda: client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
        ),
    )

    return len(points)


def search(
    *,
    query: str,
    allowed_department_ids: list[int] | None = None,
    limit: int = 5,
):
    """
    Search Qdrant using the supplied department authorization filter.

    An empty authorization list means no accessible departments and
    therefore must not contact Qdrant at all.
    """
    if (
        allowed_department_ids is not None
        and not allowed_department_ids
    ):
        return []

    ensure_collection()

    embedding_service = get_embedding_service()

    query_vector = embedding_service.embed_query(
        query
    )

    query_filter = None

    if allowed_department_ids is not None:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="department_ids",
                    match=MatchAny(
                        any=allowed_department_ids,
                    ),
                )
            ]
        )

    results = _qdrant_call(
        operation="search",
        func=lambda: client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        ),
    )

    if not hasattr(results, "points"):
        raise QdrantStoreError(
            "Qdrant search returned an invalid response"
        )

    return results