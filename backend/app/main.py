from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session
from app.core.graph import CheckpointerManager
from app.core.redis import redis_client
from app.core.storage import get_container_client
from app.routers import chat, documents, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_container_client()
    app.state.checkpointer = CheckpointerManager()
    await app.state.checkpointer.start()
    try:
        yield
    finally:
        await app.state.checkpointer.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(projects.router)


@app.get("/health")
async def health_check():
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        await redis_client.ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "ok"}
