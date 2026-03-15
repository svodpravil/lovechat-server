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
    logger.info(f"Request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Подключаем роутеры
app.include_router(auth.router)
app.include_router(messages.router)

# Хранилище активных WebSocket соединений
active_connections = {}

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {"message": "LoveChat API is running"}

@app.get("/health")
async def health():
    logger.info("Health check called")
    try:
        # Проверяем подключение к БД
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            await db.commit()
            break
        logger.info("Health check OK")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "database": str(e)}

@app.get("/debug/users")
async def debug_users():
    """Проверка таблицы users"""
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
                return {"error": "Table 'users' does not exist"}
            
            # Получаем всех пользователей
            result = await db.execute(text("SELECT * FROM users"))
            users = result.fetchall()
            logger.info(f"Found {len(users)} users")
            
            return {
                "table_exists": True,
                "users_count": len(users),
                "users": [{"id": u[0], "username": u[1], "password": u[2]} for u in users]
            }
    except Exception as e:
        logger.error(f"Debug error: {e}")
        return {"error": str(e)}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket эндпоинт для реального времени"""
    await websocket.accept()
    
    # Сохраняем соединение
    active_connections[user_id] = websocket
    logger.info(f"User {user_id} connected. Active users: {list(active_connections.keys())}")
    
    try:
        while True:
            # Ждем сообщение от клиента
            data = await websocket.receive_text()
            logger.info(f"Received message from user {user_id}: {data}")
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
                logger.info(f"Message saved to DB with id: {new_message.id}")
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
                logger.info(f"Message from {user_id} to {receiver_id} delivered via WebSocket")
            
    except WebSocketDisconnect:
        # Удаляем соединение при отключении
        if user_id in active_connections:
            del active_connections[user_id]
        logger.info(f"User {user_id} disconnected. Active users: {list(active_connections.keys())}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user_id in active_connections:
            del active_connections[user_id]

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)