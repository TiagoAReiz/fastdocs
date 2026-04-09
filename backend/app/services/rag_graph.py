from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.llm_client import generate_embeddings
from app.core.graph.state import RagState
from app.core.llm import llm
from app.models.document_embedding import DocumentEmbedding
from app.repositories import document_embedding as embedding_repo

SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions based on the provided context. "
    "If the answer is not contained in the context, say you don't know. "
    "Cite information only from the context.\n\n"
    "Context:\n{context}"
)

RETRIEVAL_LIMIT = 5


def _chunks_to_sources(
    scored: list[tuple[DocumentEmbedding, float]],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for chunk, distance in scored:
        sources.append(
            {
                "document_id": str(chunk.id_document),
                "chunk_index": chunk.chunk_index or 0,
                "content": chunk.content,
                "similarity": max(0.0, 1.0 - distance),
            }
        )
    return sources


def _build_context(scored: list[tuple[DocumentEmbedding, float]]) -> str:
    parts = []
    for i, (chunk, _) in enumerate(scored, start=1):
        parts.append(f"[{i}] {chunk.content}")
    return "\n\n".join(parts)


def build_rag_graph(db: AsyncSession, checkpointer: BaseCheckpointSaver):
    """Builds and compiles the RAG graph with the given db session and checkpointer.

    The db session is injected via closure because LangGraph nodes only receive
    the graph state — we don't want to serialize a session into the state.
    """

    async def retrieve(state: RagState) -> dict[str, Any]:
        query = state["query"]
        embeddings = await generate_embeddings([query])
        scored = await embedding_repo.similarity_search(
            db,
            embedding=embeddings[0],
            project_id=state["id_project"],
            tenant_id=state["id_tenant"],
            limit=RETRIEVAL_LIMIT,
        )
        return {
            "retrieved_chunks": _chunks_to_sources(scored),
            "context": _build_context(scored),
            "sources": _chunks_to_sources(scored),
        }

    async def generate(state: RagState) -> dict[str, Any]:
        system = SystemMessage(content=SYSTEM_PROMPT.format(context=state.get("context", "")))
        history = list(state.get("messages", []))
        response = await llm.ainvoke([system, *history])
        answer = response.content if isinstance(response.content, str) else str(response.content)
        return {
            "answer": answer,
            "messages": [AIMessage(content=answer)],
        }

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer)
