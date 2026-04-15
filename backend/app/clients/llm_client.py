from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.core.llm import llm


def _build_messages(messages: list[dict], system_prompt: str | None = None) -> list:
    lc_messages = []
    if system_prompt:
        lc_messages.append(SystemMessage(content=system_prompt))
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role in ("assistant", "agent"):
            lc_messages.append(AIMessage(content=content))
    return lc_messages


async def send_message(
    messages: list[dict], system_prompt: str | None = None
) -> str:
    lc_messages = _build_messages(messages, system_prompt)
    response = await llm.ainvoke(lc_messages)
    return response.content


async def send_message_stream(
    messages: list[dict], system_prompt: str | None = None
) -> AsyncIterator[str]:
    lc_messages = _build_messages(messages, system_prompt)
    async for chunk in llm.astream(lc_messages):
        if chunk.content:
            yield chunk.content


def _make_embeddings_model(task_type: str) -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=settings.EMBEDDING_DIM,
        task_type=task_type,
    )


async def generate_query_embedding(text: str) -> list[float]:
    return await _make_embeddings_model("RETRIEVAL_QUERY").aembed_query(text)


async def generate_embeddings_batched(
    texts: list[str], batch_size: int | None = None
) -> list[list[float]]:
    """Embed texts in chunks of `batch_size` to stay within API rate/size limits."""
    size = batch_size or settings.EMBEDDING_BATCH_SIZE
    model = _make_embeddings_model("RETRIEVAL_DOCUMENT")
    out: list[list[float]] = []
    for i in range(0, len(texts), size):
        batch = texts[i : i + size]
        out.extend(await model.aembed_documents(batch))
    return out
