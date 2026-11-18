from fastapi import APIRouter, Depends, HTTPException

from sqlmodel import Session, select
from dataclasses import dataclass
from app.database import get_session
from app.models import User, UserRole
from app.security import verify_password, create_token

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/")
def users():
    pass
