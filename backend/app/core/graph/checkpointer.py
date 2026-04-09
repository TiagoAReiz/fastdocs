from fastapi import Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.core.config import settings


class CheckpointerManager:
    """Manages the lifecycle of the LangGraph Redis checkpointer.

    Instantiated once at FastAPI startup, exposed via app.state and the
    `get_checkpointer` dependency. Reuses the same Redis instance configured
    via settings.REDIS_URL.
    """

    def __init__(self) -> None:
        self._cm: AsyncRedisSaver | None = None
        self.saver: BaseCheckpointSaver | None = None

    async def start(self) -> None:
        self._cm = AsyncRedisSaver.from_conn_string(settings.REDIS_URL)
        self.saver = await self._cm.__aenter__()
        await self.saver.asetup()

    async def stop(self) -> None:
        if self._cm is not None:
            await self._cm.__aexit__(None, None, None)
            self._cm = None
            self.saver = None


def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    """FastAPI dependency that returns the shared checkpointer."""
    saver = request.app.state.checkpointer.saver
    if saver is None:
        raise RuntimeError("Checkpointer not initialized")
    return saver
