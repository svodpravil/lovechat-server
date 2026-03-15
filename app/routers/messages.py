from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, Message
from app.schemas import MessageResponse
from typing import List

router = APIRouter(prefix="/messages", tags=["messages"])

@router.get("/", response_model=List[MessageResponse])
async def get_all_messages(db: AsyncSession = Depends(get_db)):
    """Получить все сообщения (историю чата)"""
    result = await db.execute(select(Message).order_by(Message.timestamp))
    messages = result.scalars().all()
    return messages