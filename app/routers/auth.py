from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db, User
from app.schemas import LoginRequest, LoginResponse
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт для входа в систему.
    Принимает username и password, проверяет их наличие в БД.
    """
    try:
        logger.info(f"Login attempt for user: {request.username}")

        # Ищем пользователя по имени (простой select)
        stmt = select(User).where(User.username == request.username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        # Проверяем, найден ли пользователь и совпадает ли пароль
        if user is None:
            logger.warning(f"User not found: {request.username}")
            return LoginResponse(success=False, message="Invalid username or password")

        if user.password == request.password:
            logger.info(f"Login successful for user: {request.username} (ID: {user.id})")
            return LoginResponse(success=True, user_id=user.id, message="Login successful")
        else:
            logger.warning(f"Invalid password for user: {request.username}")
            return LoginResponse(success=False, message="Invalid username or password")

    except Exception as e:
        logger.error(f"Login error: {e}\n{traceback.format_exc()}")
        # Возвращаем понятное сообщение об ошибке, но не раскрываем детали клиенту в продакшне
        return LoginResponse(success=False, message=f"Server error during login")

# Можно добавить тестовый эндпоинт для проверки, если нужно
@router.get("/test")
async def test_auth():
    return {"message": "Auth router is working"}