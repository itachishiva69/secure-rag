from pydantic import BaseModel, ConfigDict, Field


class RetrievalRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    limit: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class RetrievedChunk(BaseModel):
    document_id: int
    filename: str
    chunk_index: int
    department_ids: list[int]
    text: str


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]