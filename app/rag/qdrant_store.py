from uuid import UUID, uuid5

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from app.core.config import get_settings
from app.rag.embeddings import get_embedding_service


settings = get_settings()

client = QdrantClient(
    url=settings.qdrant_url,
)


# Fixed namespace used to generate deterministic UUIDs.
# Do not change this after vectors have been created.
UUID_NAMESPACE = UUID(
    "00000000-0000-0000-0000-000000000001"
)


def ensure_collection() -> None:
    """
    Create the Qdrant collection if it does not already exist.
    """

    embedding_service = get_embedding_service()

    collections = client.get_collections()

    exists = any(
        collection.name == settings.qdrant_collection
        for collection in collections.collections
    )

    if exists:
        return

    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(
            size=embedding_service.dimension,
            distance=Distance.COSINE,
        ),
    )


def delete_document_vectors(
    document_id: int,
) -> None:
    """
    Delete all Qdrant vectors belonging to a document.
    """

    # If the collection doesn't exist, there is nothing to delete.
    collections = client.get_collections()

    exists = any(
        collection.name == settings.qdrant_collection
        for collection in collections.collections
    )

    if not exists:
        return

    client.delete(
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

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
    )

    return len(points)


def search(
    *,
    query: str,
    allowed_department_ids: list[int] | None = None,
    limit: int = 5,
):
    if allowed_department_ids is not None and not allowed_department_ids:
        return []

    ensure_collection()

    embedding_service = get_embedding_service()

    query_vector = embedding_service.embed_query(query)

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

    return client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )