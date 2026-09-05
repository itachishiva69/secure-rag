from app.services.document_extractor import (
    extract_text,
    normalize_text,
)


FILE_PATH = (
    "storage/documents/"
    "cb019a5058cd44bca09fba0878469b6c.txt"
)


def main():
    raw_text = extract_text(FILE_PATH)

    print("=== RAW TEXT ===")
    print(raw_text)

    normalized_text = normalize_text(raw_text)

    print("\n=== NORMALIZED TEXT ===")
    print(normalized_text)


if __name__ == "__main__":
    main()