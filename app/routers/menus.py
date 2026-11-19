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


def get_menu(menu_id:int, session:Session):
    menu:Menu = session.get(Menu, menu_id)
    if menu is None or menu.is_deleted:
        raise HTTPException(status_code=404, detail="menu not found")

    return menu

@router.get("",  response_model=list[MenuOutput], summary="Liste tous les menus")
def get_all_menus(date:datetime.date|None=None, session:Session = Depends(get_session)):
    # ?date=AAAA-MM-JJ: pour recup juste menus disponibles ce jour la

    menus =session.exec(select(Menu).where(Menu.is_deleted==False)).all()

    temp = []
    if date is not None:
        for menu in menus:
            if is_menu_available_on_date(menu, date):
                temp.append(menu)
    menus = temp

    return [
        menu_to_menuOutput_type(menu)
        for menu in menus
    ]

@router.get("/{menu_id}", response_model=MenuOutput, summary="Infos sur un menu")
def get_menu_by_id(menu_id:int, session: Session = Depends(get_session)):


    menu = get_menu(menu_id, session)