import functools
import hashlib

from langchain_google_genai import ChatGoogleGenerativeAI


@functools.lru_cache(maxsize=128)
def _cached_llm(key_hash: str, api_key: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key)


def build_chat_llm(api_key: str) -> ChatGoogleGenerativeAI:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return _cached_llm(key_hash, api_key)
