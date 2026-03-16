from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db, Message
from app.routers import auth, messages
import json
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LoveChat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    await websocket.accept()
    
    # Сохраняем соединение
    active_connections[user_id] = websocket
    logger.info(f"✅ User {user_id} connected. Active: {list(active_connections.keys())}")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"📨 Received from {user_id}: {data[:50]}")
            message_data = json.loads(data)
            
            # Сохраняем в БД
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
            
            # Отправляем ВСЕМ кроме отправителя
            response = {
                "id": new_message.id,
                "sender_id": user_id,
                "text": message_data["text"],
                "timestamp": new_message.timestamp.isoformat()
            }
            
            for conn_id, conn in active_connections.items():
                if conn_id != user_id:
                    try:
                        await conn.send_text(json.dumps(response))
                        logger.info(f"📤 Sent to {conn_id}")
                    except Exception as e:
                        logger.error(f"Failed to send to {conn_id}: {e}")
            
    except WebSocketDisconnect:
        if user_id in active_connections:
            del active_connections[user_id]
        logger.info(f"❌ User {user_id} disconnected. Active: {list(active_connections.keys())}")
    except Exception as e:
        logger.error(f"⚠️ Error: {e}")
        if user_id in active_connections:
            del active_connections[user_id]