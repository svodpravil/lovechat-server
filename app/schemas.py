from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    user_id: Optional[int] = None
    message: str

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    text: str
    timestamp: datetime

class MessageCreate(BaseModel):
    sender_id: int
    text: str