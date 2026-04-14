import uuid
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from app.services.chat_service import _cache_key, _to_lc_messages


def test_cache_key_deterministic():
    tenant_id = uuid.uuid4()
    key1 = _cache_key(tenant_id, "what is X?")
    key2 = _cache_key(tenant_id, "what is X?")
    assert key1 == key2


def test_cache_key_different_tenants():
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()
    key1 = _cache_key(t1, "same query")
    key2 = _cache_key(t2, "same query")
    assert key1 != key2


def test_cache_key_different_queries():
    tenant_id = uuid.uuid4()
    key1 = _cache_key(tenant_id, "query A")
    key2 = _cache_key(tenant_id, "query B")
    assert key1 != key2


def test_to_lc_messages_user():
    msg = MagicMock()
    msg.role = "user"
    msg.content = "hello"
    result = _to_lc_messages([msg])
    assert len(result) == 1
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "hello"


def test_to_lc_messages_agent():
    msg = MagicMock()
    msg.role = "agent"
    msg.content = "hi there"
    result = _to_lc_messages([msg])
    assert len(result) == 1
    assert isinstance(result[0], AIMessage)
    assert result[0].content == "hi there"


def test_to_lc_messages_mixed():
    user_msg = MagicMock(role="user", content="question")
    agent_msg = MagicMock(role="agent", content="answer")
    result = _to_lc_messages([user_msg, agent_msg])
    assert len(result) == 2
    assert isinstance(result[0], HumanMessage)
    assert isinstance(result[1], AIMessage)
