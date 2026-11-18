from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, ClosedDay
from app.security import get_current_user, verify_password, require_admin

import datetime

router = APIRouter(prefix="/closures", tags=["closures"])


#YYYY-MM-JJ

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
def get_all_closures(date : datetime.date | None=None, session:Session=Depends(get_session)):
    # ?date=AAAA-MM-JJ retour les jours a partir de lui

    query = select(ClosedDay).order_by(ClosedDay.date)

    if date:
        query = query.where(ClosedDay.date >= date)

    closures = session.exec(query).all()

    return [
        closure_to_closureOutput_type(closure)
        for closure in closures
    ]


@router.post("", response_model=ClosureOutput, status_code=201, summary="Ajouter un jour de fermeture")
def create_closure(data:ClosureInput, admin:User=Depends(require_admin), session:Session = Depends(get_session)):

    is_already_closed = session.exec(select(ClosedDay).where(ClosedDay.date == data.date)).first()
    if is_already_closed:
        raise HTTPException(status_code=409, detail="day already closed")

    closure = ClosedDay(date=data.date, reason=data.reason)
    session.add(closure)
    session.commit()
    session.refresh(closure)

    return closure_to_closureOutput_type(closure)


@router.delete("/{closure_id}", status_code=204, summary="Supprimer un jour de fermeture")
def delete_closure(closure_id: int, admin:User=Depends(require_admin), session:Session=Depends(get_session)):
    closure = session.get(ClosedDay, closure_id)
    if not closure:
        raise HTTPException(status_code=404, detail="closure not found")

    session.delete(closure)
    session.commit()

