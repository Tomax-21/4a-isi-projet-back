from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Order
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/orders", tags=["orders"])
