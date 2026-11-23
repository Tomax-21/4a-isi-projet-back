from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import datetime
from dataclasses import dataclass, field
from app.db.database import get_session
from app.db.models import User, Order, OrderStatus, ClosedDay, Product, Menu, OrderMenu, OrderProduct
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
    products: list[OrderProductInput]=field(default_factory=list)
    menus: list[OrderMenuInput]=field(default_factory=list)#default value = []


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

@dataclass
class OrderStatusInput:
    status:OrderStatus

@dataclass
class OrderStatusOutput:
    id:int
    status:OrderStatus

def order_to_orderOutput_type(order: Order):
    total = 0
    for line in order.product_lines:
        total += line.unit_price*line.quantity
    for line in order.menu_lines:
            total += line.unit_price*line.quantity
        
    
    return {
        "id": order.id,
        "user_id": order.user_id,
        "ordered_at": order.ordered_at,
        "pickup_at": order.pickup_at,
        "status": order.status,
        "products": [
            {
                "product_id": line.product_id,
                "name": line.product.name,
                "quantity": line.quantity,
                "unit_price": float(line.unit_price),
            }
            for line in order.product_lines
        ],
        "menus": [
            {
                "menu_id": line.menu_id,
                "name": line.menu.name,
                "quantity": line.quantity,
                "unit_price": float(line.unit_price),
            }
            for line in order.menu_lines
        ],
        "total": float(total),
    }


def check_order_data_validity(data:OrderInput, pickup_at:datetime.datetime, session:Session):
    if not data.products and not data.menus:
        raise HTTPException(status_code=400, detail="an order needs at least one product or menu")

    for line in data.products:
        if line.quantity < 1:
            raise HTTPException(status_code=400, detail="Quantity of product must be >=1")
    for line in data.menus:
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
            raise HTTPException(status_code=409, detail=f"product {product.id} is not available")

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
    return menus


def get_order_from_id(order_id:int, session:Session):
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


def give_back_stock(order:Order, session:Session):
    for line in order.product_lines:
        line.product.quantity += line.quantity
        session.add(line.product)

def take_stock(order:Order, session:Session):
    for line in order.product_lines:
        if line.product.quantity < line.quantity:
            raise HTTPException(status_code=409, detail=f"not enough stock for product {line.product_id}")

    for line in order.product_lines:
        line.product.quantity -= line.quantity
        session.add(line.product)


@router.post("", response_model=OrderOutput, status_code=201, summary="Passer une commande")
def create_order(data: OrderInput, user:User=Depends(get_current_user), session:Session=Depends(get_session)):
    
    pickup_at = to_local(data.pickup_at)
    check_order_data_validity(data, pickup_at, session)

    products = get_ordered_products(data.products, session)
    menus = get_ordered_menus(data.menus, pickup_at.date(), session)

    order = Order(user_id=user.id, pickup_at=to_utc(data.pickup_at), status=OrderStatus.PENDING)

    for product, quantity in products:
        order.product_lines.append(
            OrderProduct(product_id=product.id, quantity=quantity, unit_price=product.price)
        )
        product.quantity -= quantity
        session.add(product) # to update quantity

    for menu, quantity in menus:
        order.menu_lines.append(
            OrderMenu(menu_id=menu.id, quantity=quantity, unit_price=menu.price)
        )

    session.add(order)
    session.commit()
    session.refresh(order)

    return order_to_orderOutput_type(order)


@router.get("/me", response_model=list[OrderOutput], summary="Lister mes commandes")
def get_all_my_orders(user:User=Depends(get_current_user), session:Session=Depends(get_session)):
    orders = session.exec(select(Order).where(Order.user_id==user.id).order_by(Order.ordered_at.desc())).all()

    return [order_to_orderOutput_type(order) for order in orders]


@router.patch("/{order_id}/cancel", response_model=OrderStatusOutput, summary="Annuler ma commande")
def cancel_order(order_id:int, user:User=Depends(get_current_user), session:Session=Depends(get_session)):

    order:Order=get_order_from_id(order_id, session)

    if order.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your order")
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=409, detail="only a pending order can be cancelled")


    give_back_stock(order, session)

    order.status = OrderStatus.CANCELLED
    session.add(order)
    session.commit()
    session.refresh(order)

    return {"id":order.id, "status":order.status}


@router.get("", response_model=list[OrderOutput], summary="Lister toutes les commandes")
def get_all_orders(status:OrderStatus|None=None, admin:User=Depends(require_admin), session:Session=Depends(get_session)):
    #?status=pending (facultatfi)

    query = select(Order).order_by(Order.pickup_at, Order.id)
    if status is not None:
        query = query.where(Order.status==status)

    orders = session.exec(query).all()
    return [order_to_orderOutput_type(order) for order in orders]


@router.patch("/{order_id}/status", response_model=OrderStatusOutput, summary="Changer le statut d'une commande")
def change_order_status(order_id:int, data:OrderStatusInput, admin:User=Depends(require_admin), session:Session=Depends(get_session)):
    order:Order = get_order_from_id(order_id, session)

    if data.status == OrderStatus.CANCELLED and order.status != OrderStatus.CANCELLED:
        give_back_stock(order, session)

    elif data.status != OrderStatus.CANCELLED and order.status == OrderStatus.CANCELLED:
        take_stock(order, session)

    order.status = data.status
    session.add(order)
    session.commit()
    session.refresh(order)
    return {"id": order.id, "status":order.status}