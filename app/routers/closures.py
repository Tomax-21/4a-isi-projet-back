from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, ClosedDay
from app.security import get_current_user, verify_password, require_admin

import datetime

router = APIRouter(prefix="/closures", tags=["closures"])


@dataclass
class ClosureInput:
    date: datetime.date
    reason: str|None

@dataclass
class ClosureOutput:
    id:int
    date:datetime.date
    reason:str|None