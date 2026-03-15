from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db, Message
from app.routers import auth, messages
import json
from datetime import datetime
import os

app = FastAPI(title="LoveChat API")

# Разрешаем CORS для Android приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(auth.router)
app.include_router(messages.router)

# Хранилище активных WebSocket соединений
active_connections = {}

@app.get("/")
async def root():
    return {"message": "LoveChat API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket эндпоинт для реального времени"""
    await websocket.accept()
    
    # Сохраняем соединение
    active_connections[user_id] = websocket
    print(f"User {user_id} connected. Active users: {list(active_connections.keys())}")
    
    try:
        while True:
            # Ждем сообщение от клиента
            data = await websocket.receive_text()
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
                print(f"Message from {user_id} to {receiver_id} delivered via WebSocket")
            
    except WebSocketDisconnect:
        # Удаляем соединение при отключении
        if user_id in active_connections:
            del active_connections[user_id]
        print(f"User {user_id} disconnected. Active users: {list(active_connections.keys())}")
    except Exception as e:
        print(f"Error: {e}")
        if user_id in active_connections:
            del active_connections[user_id]