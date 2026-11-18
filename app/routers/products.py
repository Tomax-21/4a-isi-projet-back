from fastapi import APIRouter, Depends, HTTPException

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Product
from app.security import get_current_user, verify_password, require_admin

router = APIRouter(prefix="/products", tags=["products"])
