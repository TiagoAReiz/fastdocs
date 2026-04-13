from typing import Annotated, Any, TypedDict
from uuid import UUID

from langgraph.graph.message import add_messages


class RagState(TypedDict, total=False):
    """Shared state contract for all RAG graphs in FastDocs.

    Every node in a RAG pipeline reads/writes a subset of these fields.
    Kept intentionally minimal — extend per-graph as needed.
    """

    # Tenant scoping (always required on entry)
    id_tenant: UUID
    id_project: UUID

    # Conversation
    id_thread: UUID | None
    query: str
    messages: Annotated[list[Any], add_messages]

    # Retrieval
    retrieved_chunks: list[dict[str, Any]]
    context: str

    # Generation
    answer: str
    sources: list[dict[str, Any]]

    # Agent control flow
    retry_count: int
    reformulated_query: str
    query_intent: str
