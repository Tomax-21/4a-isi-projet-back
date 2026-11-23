from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import datetime
from dataclasses import dataclass
from app.database import get_session
from app.models import User, Order, OrderStatus, ClosedDay, Product, Menu, OrderMenu, OrderProduct
from app.security import get_current_user, require_admin
from app.routers.menus import is_menu_available_on_date


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

def to_utc(pickup_at: datetime.datetime) -> datetime.datetime:
    return pickup_at.astimezone(datetime.timezone.utc)


def get_ordered_products(lines: list[OrderProductInput], session:Session):
    products = []
    for line in lines:
        product:Product = session.get(Product, line.product_id)
        if product is None or product.is_deleted:
            raise HTTPException(status_code=404, detail=f"product {line.product_id} not found")

        if not product.is_available:
            raise HTTPException(status_code=409, detail="product {product.id} is not available")

        if product.quantity < line.quantity:
            raise HTTPException(status_code=409, detail=f"not enough stock for product {product.id}")

        products.append((product, line.quantity))
    return products

def get_ordered_menus(lines: list[OrderMenuInput], pickup_day: datetime.date, session:Session):
    menus = []
    for line in lines:
        menu:Menu = session.get(Menu, line.menu_id)
        if menu is None or menu.is_deleted:
            raise HTTPException(status_code=404, detail=f"menu {line.menu_id} not found")

        if not is_menu_available_on_date(menu, pickup_day):
            raise HTTPException(status_code=400, detail=f"menu {menu.id} is not available on this day")

        menus.append((menu, line.quantity))
    return menu






@router.post("", response_model=OrderOutput, status_code=201, summary="Passer une commande")
def create_order(data: OrderInput, user:User=Depends(get_current_user), session:Session=Depends(get_session)):
    
    pickup_at = to_local(data.pickup_at)
    check_order_data_validity(data, pickup_at, session)

    products = get_ordered_products(data.products, session)
    menus = get_ordered_menus(data.menus, pickup_at.date(), session)
