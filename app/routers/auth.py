
# app/routers/auth.py
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(data, session: Session = Depends(get_session)):

    user = session.exec(select(User).where(User.username == data.username)).first()

   

    return {"access_token": "token", "role": user.role}