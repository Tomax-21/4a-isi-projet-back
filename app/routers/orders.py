from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import datetime
from dataclasses import dataclass
from app.database import get_session
from app.models import User, Order, OrderStatus, ClosedDay
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


def check_order_data_validity(data:OrderInput, pickup_at:datetime.datetime, session:Session):
    if not data.products and not data.menus:
        raise HTTPException(status_code=400, detail="an order needs at least one product or menu")

    for line in data.products:
        if line.quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity of product must be >=1")
    for line in data.menu:
        if line.quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity of menu must be >=1")

    product_ids = []
    for line in data.products:
        product_ids.append(line.product_id)

    menu_ids = []
    for menu in data.menus:
        menu_ids.append(menu.menu_id)

    if len(set(product_ids)) != len(product_ids) or len(set(menu_ids)) != len(menu_ids):
        raise HTTPException(status_code=400, detail="same product or menu given twice")


    if pickup_at <= datetime.datetime.now():
        raise HTTPException(status_code=400, detail="pickup_at must be in the future")

    isClosed = session.exec(select(ClosedDay).where(ClosedDay.date==pickup_at.date())).first()

    if isClosed:
        raise HTTPException(status_code=400, detail="the shop is closed this day")
    
def to_local(pickup_at: datetime.datetime):
    if pickup_at.tzinfo is not None:
        return pickup_at.astimezone().replace(tzinfo=None)
    return pickup_at # remove user timezone

@router.post("", response_model=OrderOutput, status_code=201, summary="Passer une commande")
def create_order(data: OrderInput, user:User=Depends(get_current_user), session:Session=Depends(get_session)):
    
    pickup_at = to_local(data.pickup_at)
    
    check_order_data_validity(data, pickup_at, session )