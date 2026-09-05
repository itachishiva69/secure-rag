from app.services.document_extractor import (
    extract_text,
    normalize_text,
)
from app.services.chunking import split_text


FILE_PATH = (
    "storage/documents/"
    "cb019a5058cd44bca09fba0878469b6c.txt"
)


def main():
    raw_text = extract_text(FILE_PATH)
    normalized_text = normalize_text(raw_text)

    chunks = split_text(normalized_text)

    print(f"Total chunks: {len(chunks)}")

    for index, chunk in enumerate(chunks):
        print(f"\n--- Chunk {index} ---")
        print(chunk)


if __name__ == "__main__":
    main()