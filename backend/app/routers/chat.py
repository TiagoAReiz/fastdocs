from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.deps import get_checkpointer, get_current_tenant, rate_limit_query
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ThreadDetailResponse,
    ThreadListResponse,
)
from app.schemas.deps import PaginationParams, TenantContext
from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/message", dependencies=[Depends(rate_limit_query)])
async def send_message(
    body: ChatMessageRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    checkpointer=Depends(get_checkpointer),
):
    if body.stream:
        return StreamingResponse(
            chat_service.send_message_stream(
                db, tenant, body.id_project, body.message, checkpointer, body.id_thread
            ),
            media_type="text/event-stream",
        )
    response: ChatMessageResponse = await chat_service.send_message(
        db, tenant, body.id_project, body.message, checkpointer, body.id_thread
    )
    return response


@router.get("/history", response_model=ThreadListResponse)
async def list_threads(
    id_project: UUID = Query(...),
    pagination: PaginationParams = Depends(),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.list_threads(
        db, tenant, id_project, pagination.page, pagination.page_size
    )


@router.get("/history/{id_thread}", response_model=ThreadDetailResponse)
async def get_thread(
    id_thread: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.get_thread(db, tenant, id_thread)
