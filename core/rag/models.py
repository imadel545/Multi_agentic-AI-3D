from pydantic import BaseModel, Field


class RagDocument(BaseModel):
    doc_id: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    text: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)


class RagSearchResult(BaseModel):
    collection: str
    doc_id: str
    score: float
    text: str
    payload: dict


class RagIndexReport(BaseModel):
    status: str
    collections: dict[str, int]
    total_documents: int
    embedding_provider: str
