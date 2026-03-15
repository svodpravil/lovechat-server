from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, User
from app.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Эндпоинт для входа в систему"""
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()
    
    if user and user.password == request.password:
        return LoginResponse(success=True, user_id=user.id, message="Login successful")
    else:
        return LoginResponse(success=False, message="Invalid username or password")