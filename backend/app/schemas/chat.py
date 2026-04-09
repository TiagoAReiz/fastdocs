from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class MessageRole(str, Enum):
    user = "user"
    agent = "agent"


class ChatMessageRequest(BaseModel):
    message: str
    id_project: UUID
    id_thread: UUID | None = None
    stream: bool = False


class Source(BaseModel):
    document_id: UUID
    chunk_index: int
    content: str
    similarity: float


class ChatMessageResponse(BaseModel):
    message_agent: str
    id_thread: UUID
    sources: list[Source]


class ThreadSummary(BaseModel):
    id: UUID
    name: str
    created_at: datetime


class ThreadListResponse(BaseModel):
    threads: list[ThreadSummary]


class MessageItem(BaseModel):
    id: UUID
    role: MessageRole
    message: str
    created_at: datetime


class ThreadDetailResponse(BaseModel):
    id: UUID
    name: str
    messages: list[MessageItem]
