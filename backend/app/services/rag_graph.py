import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.llm_client import generate_query_embedding
from app.core.graph.state import RagState
from app.core.llm import build_chat_llm
from app.models.document_embedding import DocumentEmbedding
from app.repositories import document_embedding as embedding_repo

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RETRIEVAL_LIMIT = 5
SIMILARITY_THRESHOLD = 0.4
MAX_RETRIES = 2

SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions based on the provided context. "
    "If the answer is not contained in the context, say you don't know. "
    "Cite information only from the context.\n\n"
    "Context:\n{context}"
)

ANALYZE_PROMPT = (
    "Classify the following user query into one of these intents: "
    "factual, procedural, comparison, opinion, greeting, other.\n"
    "Also extract 3-5 key terms for retrieval.\n"
    "Respond ONLY in valid JSON: {{\"intent\": \"...\", \"key_terms\": [\"...\"]}}\n\n"
    "Query: {query}"
)

RERANK_PROMPT = (
    "Given the user query and the following text chunks, score each chunk's relevance "
    "to the query on a scale of 1-5 (5 = highly relevant).\n"
    "Respond ONLY in valid JSON array: [{{\"index\": 0, \"score\": N}}, ...]\n\n"
    "Query: {query}\n\n"
    "Chunks:\n{chunks}"
)

REFORMULATE_PROMPT = (
    "The following search query did not retrieve good results from our document database. "
    "Rewrite it to be more specific, use alternative terms, or break it down.\n"
    "Return ONLY the rewritten query text, nothing else.\n\n"
    "Original query: {query}"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps around JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()


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


def _context_from_chunks(chunks: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {c['content']}" for i, c in enumerate(chunks)
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_after_evaluation(state: RagState) -> str:
    """Conditional edge from evaluate_context — decides rerank vs reformulate."""
    chunks = state.get("retrieved_chunks", [])
    retry_count = state.get("retry_count", 0)

    # Graceful degradation: after max retries, answer with whatever we have
    if retry_count >= MAX_RETRIES:
        log.info("max retries (%d) reached — proceeding to rerank", MAX_RETRIES)
        return "rerank"

    if not chunks:
        log.info("no chunks retrieved — routing to reformulate")
        return "reformulate"

    best_similarity = max(c.get("similarity", 0.0) for c in chunks)
    if best_similarity < SIMILARITY_THRESHOLD:
        log.info(
            "best similarity %.3f < threshold %.3f — routing to reformulate",
            best_similarity,
            SIMILARITY_THRESHOLD,
        )
        return "reformulate"

    return "rerank"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_rag_graph(db: AsyncSession, checkpointer: BaseCheckpointSaver, gemini_api_key: str):
    """Builds and compiles the 6-node RAG agent graph.

    Nodes: analyze_query → retrieve → evaluate_context → rerank → generate
    With a conditional retry loop: evaluate_context → reformulate → retrieve

    The db session and gemini_api_key are injected via closure because LangGraph
    nodes only receive the graph state.
    """
    llm = build_chat_llm(gemini_api_key)

    # ------------------------------------------------------------------
    # Node 1: analyze_query
    # ------------------------------------------------------------------
    async def analyze_query(state: RagState) -> dict[str, Any]:
        query = state["query"]
        response = await llm.ainvoke([
            SystemMessage(content="You are a query analysis assistant. Respond only in valid JSON."),
            HumanMessage(content=ANALYZE_PROMPT.format(query=query)),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)

        try:
            parsed = json.loads(_extract_json(content))
            intent = parsed.get("intent", "other")
        except (json.JSONDecodeError, AttributeError):
            intent = "other"

        log.info("analyze_query: intent=%s for query=%r", intent, query[:80])
        return {"query_intent": intent}

    # ------------------------------------------------------------------
    # Node 2: retrieve
    # ------------------------------------------------------------------
    async def retrieve(state: RagState) -> dict[str, Any]:
        query = state.get("reformulated_query") or state["query"]
        embedding = await generate_query_embedding(query, gemini_api_key)
        scored = await embedding_repo.similarity_search(
            db,
            embedding=embedding,
            project_id=state["id_project"],
            tenant_id=state["id_tenant"],
            limit=RETRIEVAL_LIMIT,
        )
        chunks = _chunks_to_sources(scored)
        log.info("retrieve: %d chunks for query=%r", len(chunks), query[:80])
        return {
            "retrieved_chunks": chunks,
            "context": _build_context(scored),
            "sources": chunks,
        }

    # ------------------------------------------------------------------
    # Node 3: evaluate_context (decision node — routing via conditional edge)
    # ------------------------------------------------------------------
    async def evaluate_context(state: RagState) -> dict[str, Any]:
        chunks = state.get("retrieved_chunks", [])
        best = max((c.get("similarity", 0.0) for c in chunks), default=0.0)
        log.info(
            "evaluate_context: %d chunks, best_similarity=%.3f, retry_count=%d",
            len(chunks),
            best,
            state.get("retry_count", 0),
        )
        return {}

    # ------------------------------------------------------------------
    # Node 4: rerank
    # ------------------------------------------------------------------
    async def rerank(state: RagState) -> dict[str, Any]:
        query = state.get("reformulated_query") or state["query"]
        chunks = state.get("retrieved_chunks", [])

        if len(chunks) <= 1:
            return {}

        chunks_text = "\n".join(
            f"[{i}] {c['content'][:300]}" for i, c in enumerate(chunks)
        )
        response = await llm.ainvoke([
            SystemMessage(content="You are a relevance scoring assistant. Respond only in valid JSON."),
            HumanMessage(content=RERANK_PROMPT.format(query=query, chunks=chunks_text)),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)

        try:
            scores = json.loads(_extract_json(content))
            score_map = {item["index"]: item["score"] for item in scores}
            reranked = sorted(
                enumerate(chunks),
                key=lambda pair: score_map.get(pair[0], 0),
                reverse=True,
            )
            reranked_chunks = [c for _, c in reranked]
            log.info("rerank: reordered %d chunks by LLM relevance scores", len(reranked_chunks))
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("rerank: JSON parse failed — keeping original order")
            reranked_chunks = chunks

        return {
            "retrieved_chunks": reranked_chunks,
            "sources": reranked_chunks,
            "context": _context_from_chunks(reranked_chunks),
        }

    # ------------------------------------------------------------------
    # Node 5: reformulate
    # ------------------------------------------------------------------
    async def reformulate(state: RagState) -> dict[str, Any]:
        query = state.get("reformulated_query") or state["query"]
        retry_count = state.get("retry_count", 0)

        response = await llm.ainvoke([
            SystemMessage(content="You are a search query optimization assistant."),
            HumanMessage(content=REFORMULATE_PROMPT.format(query=query)),
        ])
        new_query = response.content if isinstance(response.content, str) else str(response.content)
        new_query = new_query.strip()

        log.info(
            "reformulate: retry %d, %r -> %r",
            retry_count + 1,
            query[:60],
            new_query[:60],
        )
        return {
            "reformulated_query": new_query,
            "retry_count": retry_count + 1,
        }

    # ------------------------------------------------------------------
    # Node 6: generate
    # ------------------------------------------------------------------
    async def generate(state: RagState) -> dict[str, Any]:
        system = SystemMessage(content=SYSTEM_PROMPT.format(context=state.get("context", "")))
        history = list(state.get("messages", []))
        response = await llm.ainvoke([system, *history])
        answer = response.content if isinstance(response.content, str) else str(response.content)
        return {
            "answer": answer,
            "messages": [AIMessage(content=answer)],
        }

    # ------------------------------------------------------------------
    # Wire the graph
    # ------------------------------------------------------------------
    graph = StateGraph(RagState)

    graph.add_node("analyze_query", analyze_query)
    graph.add_node("retrieve", retrieve)
    graph.add_node("evaluate_context", evaluate_context)
    graph.add_node("rerank", rerank)
    graph.add_node("reformulate", reformulate)
    graph.add_node("generate", generate)

    graph.add_edge(START, "analyze_query")
    graph.add_edge("analyze_query", "retrieve")
    graph.add_edge("retrieve", "evaluate_context")
    graph.add_conditional_edges(
        "evaluate_context",
        _route_after_evaluation,
        {"rerank": "rerank", "reformulate": "reformulate"},
    )
    graph.add_edge("reformulate", "retrieve")
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer)
