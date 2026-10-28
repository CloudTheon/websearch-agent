from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class Decision(BaseModel):
    interrupt_id: str
    type: str
    message: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    decisions: list[Decision]


class InterruptInfo(BaseModel):
    id: str
    tool: str
    args: dict[str, Any]


class ThreadItem(BaseModel):
    thread_id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ThreadListResponse(BaseModel):
    threads: list[ThreadItem]


class MessageItem(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[MessageItem]
