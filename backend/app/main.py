from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.graph import CheckpointerManager
from app.core.storage import get_container_client
from app.routers import chat, documents, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
def health_check():
    return {"status": "ok"}
