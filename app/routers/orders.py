from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import datetime
from dataclasses import dataclass
from app.database import get_session
from app.models import User, Order, OrderStatus
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/orders", tags=["orders"])

@dataclass
class OrderProductInput:
    product_id: int
    quantity: int


@dataclass
class OrderMenuInput:
    menu_id: int
    quantity: int

@dataclass
class OrderInput:
    pickup_at: datetime.datetime   # "2026-11-25T12:30:00"
    products: list[OrderProductInput]
    menus: list[OrderMenuInput]


@dataclass
class OrderProductOutput:
    product_id: int
    name: str
    quantity: int
    unit_price: float


@dataclass
class OrderMenuOutput:
    menu_id: int
    name: str
    quantity: int
    unit_price: float


@dataclass
class OrderOutput:
    id: int
    user_id: int
    ordered_at: datetime.datetime
    pickup_at: datetime.datetime
    status: OrderStatus
    products: list[OrderProductOutput]
    menus: list[OrderMenuOutput]
    total: float



@router.post("", response_model=OrderOutput, status_code=201, summary="Passer une commande")
def create_order(data: OrderInput, user:User=Depends(get_current_user), session:Session=Depends(get_session)):
    pass