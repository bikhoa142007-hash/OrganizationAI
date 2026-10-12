from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InternalNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_round: int | None = Field(default=None, ge=1, strict=True)
    content: str


class InternalNoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: UUID
    plan_id: UUID
    approval_round: int | None
    author_id: UUID
    created_at: datetime
    content: str


class InternalNotesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InternalNoteResponse]
