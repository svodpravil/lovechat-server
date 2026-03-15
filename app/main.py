from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db, Message, engine
from app.routers import auth, messages
import json
from datetime import datetime
import os
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LoveChat API")

# Разрешаем CORS для Android приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для логирования всех запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"➡️ Request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"⬅️ Response status: {response.status_code}")
    return response

# Подключаем роутеры
app.include_router(auth.router)
app.include_router(messages.router)

# Хранилище активных WebSocket соединений
active_connections = {}

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    logger.info("Root endpoint called")
    return {
        "message": "LoveChat API is running",
        "status": "online",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    """Проверка здоровья сервера и подключения к БД"""
    logger.info("Health check called")
    db_status = "unknown"
    db_message = ""
    
    try:
        # Проверяем подключение к БД
        async for db in get_db():
            result = await db.execute(text("SELECT 1"))
            await db.commit()
            db_status = "connected"
            logger.info("Database connection OK")
            break
    except Exception as e:
        db_status = "disconnected"
        db_message = str(e)
        logger.error(f"Database connection failed: {e}")
    
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "database": {
            "status": db_status,
            "message": db_message
        }
    }

@app.get("/debug/users")
async def debug_users():
    """Отладочный эндпоинт для проверки таблицы users"""
    logger.info("Debug users endpoint called")
    try:
        async for db in get_db():
            # Проверяем существование таблицы
            result = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                );
                """))
            table_exists = result.scalar()
            logger.info(f"Table users exists: {table_exists}")
            
            if not table_exists:
                return {
                    "table_exists": False,
                    "error": "Table 'users' does not exist"
                }
            
            # Получаем структуру таблицы
            result = await db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users'
                ORDER BY ordinal_position;
            """))
            columns = result.fetchall()
            
            # Получаем всех пользователей
            result = await db.execute(text("SELECT * FROM users"))
            users = result.fetchall()
            logger.info(f"Found {len(users)} users")
            
            return {
                "table_exists": True,
                "columns": [{"name": c[0], "type": c[1]} for c in columns],
                "users_count": len(users),
                "users": [{"id": u[0], "username": u[1], "password": u[2]} for u in users]
            }
    except Exception as e:
        logger.error(f"Debug error: {e}")
        return {"error": str(e)}

@app.get("/test-db-connection")
async def test_db_connection():
    """Тестирует подключение к базе данных"""
    logger.info("Testing database connection")
    try:
        # Пытаемся подключиться
        async for db in get_db():
            result = await db.execute(text("SELECT 1"))
            await db.commit()
            
            # Проверяем наличие таблиц
            tables_result = await db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = tables_result.fetchall()
            
            db_url = os.getenv("DATABASE_URL", "not set")
            # Маскируем пароль для безопасности
            if db_url != "not set" and '@' in db_url:
                parts = db_url.split('@')
                credentials = parts[0].split('://')[1].split(':')[0] if '://' in parts[0] else "hidden"
                host = parts[1].split('/')[0]
                db_url_masked = f"postgresql://{credentials}:****@{host}/..."
            else:
                db_url_masked = db_url
            
            return {
                "status": "success", 
                "message": "Database connected successfully",
                "database_url": db_url_masked,
                "tables": [t[0] for t in tables],
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return {
            "status": "error", 
            "message": str(e),
            "database_url": os.getenv("DATABASE_URL", "not set")[:20] + "...",
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/env-check")
async def env_check():
    """Проверка переменных окружения (безопасная версия)"""
    db_url = os.getenv("DATABASE_URL", "not set")
    # Маскируем пароль
    if db_url != "not set" and '@' in db_url:
        parts = db_url.split('@')
        host_part = parts[1] if len(parts) > 1 else ""
        db_url_masked = f"postgresql://****:****@{host_part}"
    else:
        db_url_masked = db_url
    
    return {
        "DATABASE_URL_set": os.getenv("DATABASE_URL") is not None,
        "DATABASE_URL": db_url_masked,
        "PORT": os.getenv("PORT", "not set"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "local")
    }

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket эндпоинт для реального времени"""
    await websocket.accept()
    
    # Сохраняем соединение
    active_connections[user_id] = websocket
    logger.info(f"✅ User {user_id} connected. Active users: {list(active_connections.keys())}")
    
    try:
        while True:
            # Ждем сообщение от клиента
            data = await websocket.receive_text()
            logger.info(f"📨 Received message from user {user_id}: {data[:50]}...")
            message_data = json.loads(data)
            
            # Сохраняем сообщение в БД
            async for db in get_db():
                new_message = Message(
                    sender_id=user_id,
                    text=message_data["text"],
                    timestamp=datetime.utcnow()
                )
                db.add(new_message)
                await db.commit()
                await db.refresh(new_message)
                logger.info(f"💾 Message saved to DB with id: {new_message.id}")
                break
            
            # Определяем получателя (если user_id=1, то получатель 2, и наоборот)
            receiver_id = 2 if user_id == 1 else 1
            
            # Формируем ответ
            response = {
                "id": new_message.id,
                "sender_id": user_id,
                "text": message_data["text"],
                "timestamp": new_message.timestamp.isoformat()
            }
            
            # Если получатель онлайн, отправляем ему сообщение
            if receiver_id in active_connections:
                await active_connections[receiver_id].send_text(json.dumps(response))
                logger.info(f"📤 Message from {user_id} to {receiver_id} delivered via WebSocket")
            else:
                logger.info(f"📥 Message saved, user {receiver_id} is offline")
            
    except WebSocketDisconnect:
        # Удаляем соединение при отключении
        if user_id in active_connections:
            del active_connections[user_id]
        logger.info(f"❌ User {user_id} disconnected. Active users: {list(active_connections.keys())}")
    except Exception as e:
        logger.error(f"⚠️ WebSocket error for user {user_id}: {e}")
        if user_id in active_connections:
            del active_connections[user_id]

@app.on_event("startup")
async def startup_event():
    """Действия при запуске сервера"""
    logger.info("🚀 Starting up LoveChat server...")
    
    # Проверяем переменные окружения
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        logger.info("✅ DATABASE_URL is set")
        # Маскируем пароль для логов
        masked_url = db_url.split('@')[0].split(':')[0] + ':****@' + db_url.split('@')[1] if '@' in db_url else db_url
        logger.info(f"   URL: {masked_url}")
    else:
        logger.error("❌ DATABASE_URL is NOT set!")
    
    # Пробуем подключиться к БД
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            await db.commit()
            logger.info("✅ Successfully connected to database")
            break
    except Exception as e:
        logger.error(f"❌ Failed to connect to database at startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Действия при остановке сервера"""
    logger.info("🛑 Shutting down LoveChat server...")
    # Закрываем все WebSocket соединения
    for user_id, ws in active_connections.items():
        await ws.close()
    logger.info("All WebSocket connections closed")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🎧 Starting server on port {port}")
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=port,
        reload=True,  # Автоматическая перезагрузка при изменениях
        log_level="info"
    )