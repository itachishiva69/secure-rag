from app.rag.embeddings import get_embedding_service


def main():
    service = get_embedding_service()

    texts = [
        "JWT authentication verifies the identity of a user.",
        "Engineering documents are protected by department authorization.",
        "The weather is sunny today.",
    ]

    embeddings = service.embed_documents(texts)

    print(f"Embedding dimension: {service.dimension}")
    print(f"Number of embeddings: {len(embeddings)}")
    print(f"First vector length: {len(embeddings[0])}")

    similarity_1 = sum(
        a * b
        for a, b in zip(embeddings[0], embeddings[1])
    )

    similarity_2 = sum(
        a * b
        for a, b in zip(embeddings[0], embeddings[2])
    )

    print(f"Authentication/document similarity: {similarity_1:.4f}")
    print(f"Authentication/weather similarity: {similarity_2:.4f}")


if __name__ == "__main__":
    main()