from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Menu
from app.security import get_current_user, require_admin

import datetime

router = APIRouter(prefix="/menus", tags=["menus"])


#end and start date = None = Permanent menu
@dataclass
class MenuInput:
    name:str
    description: str|None
    price: float
    is_available: bool
    start_date: datetime.date |None
    end_date : datetime.date|None
    product_ids: list[int]

#table de transition
@dataclass
class MenuProductOutput:
    id: int
    name:str

@dataclass
class MenuOutput:
    id: int
    name:str
    description: str|None
    price: float
    is_available: bool
    start_date: datetime.date |None
    end_date : datetime.date|None
    products: list[MenuProductOutput]


def menu_to_menuOutput_type(menu:Menu):
    return {
        "id": menu.id,
        "name": menu.name,
        "description" :menu.description,
        "price":menu.price,
        "is_available":menu.is_available,
        "start_date":menu.start_date,
        "end_date":menu.end_date,
        "products":[
            {"id":product.id, "name":product.name}
            for product in menu.products
        ]
    }

def is_menu_available_on_date(menu:Menu, day:datetime.date):
    if not menu.is_available:
        return False

    if menu.start_date is not None and day < menu.start_date:
        return False
    if menu.end_date is not None and day > menu.end_date:
        return False

    return True


@router.get("",  response_model=list[MenuOutput], summary="Liste tous les menus")
def get_all_menus(session:Session = Depends(get_session)):
    menus =session.exec(select(Menu).where(Menu.is_deleted==False)).all()


    return [
        menu_to_menuOutput_type(menu)
        for menu in menus
    ]