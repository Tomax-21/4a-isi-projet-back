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


def closure_to_closureOutput_type(closure: ClosedDay):
    return {
        "id": closure.id,
        "date":closure.date,
        "reason":closure.reason
    }


@router.get("", response_model=list[ClosureOutput], summary="Liste de tous les jours de fermeture")
def get_all_closures(session:Session=Depends(get_session)):
    closures = session.exec(select(ClosedDay).order_by(ClosedDay.date)).all()

    return [
        closure_to_closureOutput_type(closure)
        for closure in closures
    ]