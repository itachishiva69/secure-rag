from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


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
    conversation_id: int | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class RetrievedChunk(BaseModel):
    document_id: StrictInt = Field(
        gt=0,
    )
    filename: StrictStr = Field(
        min_length=1,
    )
    chunk_index: StrictInt = Field(
        ge=0,
    )
    department_ids: list[StrictInt] = Field(
        min_length=1,
    )
    text: StrictStr = Field(
        min_length=1,
    )

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )


class QuerySource(BaseModel):
    document_id: int
    filename: str
    chunk_index: int


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[QuerySource]
    conversation_id: int | None


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
