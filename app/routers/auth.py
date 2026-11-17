
# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException

from sqlmodel import Session, select
from dataclasses import dataclass
from app.database import get_session
from app.models import User
from app.security import verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])



@dataclass
class LoginInput:
    username: str
    password: str

@dataclass
class LoginOutput:
    access_token: str
    role: str


@router.post("/login", response_model=LoginOutput, summary="Connexion")
def login(data: LoginInput, session: Session = Depends(get_session)):

    user:User = session.exec(select(User).where(User.username == data.username)).first()


    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="wrong username or password")

    if user.is_blocked:
        raise HTTPException(status_code=403, detail="account blocked")

    return {"access_token": create_token(user.id), "role": user.role}
