import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
import datetime

# Получаем DATABASE_URL из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/lovechat")

# SQLAlchemy требует асинхронный драйвер
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Модель пользователя
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)

# Модель сообщения
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Функция для получения сессии БД
async def get_db():
    async with AsyncSessionLocal() as db:
        yield db