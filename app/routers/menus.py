from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Menu
from app.security import get_current_user, require_admin

import datetime

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