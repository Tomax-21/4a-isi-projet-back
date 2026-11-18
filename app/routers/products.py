from fastapi import APIRouter, Depends, HTTPException

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Product
from app.security import get_current_user, verify_password, require_admin

router = APIRouter(prefix="/products", tags=["products"])

@dataclass
class ProductInput:
    name: str
    description: str | None
    price: float
    quantity: int
    is_available: bool


@dataclass
class ProductOutput:
    id: int
    name: str
    description: str | None
    price: float
    quantity: int
    is_available: bool


