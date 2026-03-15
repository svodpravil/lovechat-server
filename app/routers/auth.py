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
    """Эндпоинт для входа в систему"""
    try:
        logger.info(f"=== Login attempt: {request.username} ===")
        logger.info(f"Password received: {'*' * len(request.password)}")
        
        # Проверяем подключение к БД простым запросом
        logger.info("Testing database connection...")
        try:
            result = await db.execute(text("SELECT 1"))
            await db.commit()
            logger.info("Database connection OK")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return LoginResponse(success=False, message=f"Database connection error: {str(e)}")
        
        # Проверяем существование таблицы users
        logger.info("Checking if users table exists...")
        result = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            )
        """))
        table_exists = result.scalar()
        logger.info(f"Table 'users' exists: {table_exists}")
        
        if not table_exists:
            logger.error("Table 'users' does not exist!")
            return LoginResponse(success=False, message="Database table 'users' not found")
        
        # Получаем список всех пользователей для отладки
        result = await db.execute(text("SELECT id, username FROM users"))
        all_users = result.fetchall()
        logger.info(f"All users in database: {[dict(u) for u in all_users]}")
        
        # Ищем пользователя
        logger.info(f"Looking for user with username: {request.username}")
        result = await db.execute(
            select(User).where(User.username == request.username)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            logger.warning(f"User '{request.username}' not found")
            return LoginResponse(success=False, message="Invalid username or password")
        
        logger.info(f"User found: id={user.id}, username={user.username}")
        logger.info(f"Stored password: {user.password}")
        logger.info(f"Provided password: {request.password}")
        logger.info(f"Password match: {user.password == request.password}")
        
        if user.password == request.password:
            logger.info(f"Login successful for user: {request.username}")
            return LoginResponse(success=True, user_id=user.id, message="Login successful")
        else:
            logger.warning(f"Invalid password for user: {request.username}")
            return LoginResponse(success=False, message="Invalid username or password")
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        logger.error(traceback.format_exc())
        return LoginResponse(success=False, message=f"Server error: {str(e)}")