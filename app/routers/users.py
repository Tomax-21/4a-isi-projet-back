from fastapi import APIRouter, Depends, HTTPException

from sqlmodel import Session, select
from dataclasses import dataclass
from app.database import get_session
from app.models import User, UserRole
from app.security import hash_password, generate_random_password, get_current_user, verify_password, require_admin

router = APIRouter(prefix="/users", tags=["users"])

@dataclass
class UserCreateInput:
    username:str

@dataclass 
class UserCreateOutput:
    id: int
    username: str
    password: str

@router.post("/", response_model=UserCreateOutput, status_code=201, summary="Créer un compte")
def create_user(data:UserCreateInput, session: Session= Depends(get_session)):
    username = data.username.strip()

    if not username or len(username) > 50:
        raise HTTPException(status_code=400, detail="invalid username")

    is_already_existing = session.exec(select(User).where(User.username == username)).first()

    if is_already_existing:
        raise HTTPException(status_code=409, detail="username already taken")

    password=generate_random_password()

    user = User(
        username=username,
        password_hash=hash_password(password)
    )

    session.add(user)
    session.commit()
    session.refresh(user) # recup id dans la base

    return {
        "id": user.id,
        "username" : user.username,
        "password": password
    }

@dataclass
class PasswordChangeInput:
    old_password: str
    new_password: str

@dataclass
class PasswordChangeOuput:
    message: str

@router.patch("/me/password", response_model=PasswordChangeOuput,summary="Changer son mot de passe")
def update_password(data: PasswordChangeInput, user:User=Depends(get_current_user), session:Session=Depends(get_session)):

    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="old password incorrect")

    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="new password too short")

    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    session.add(user)

    session.commit()

    return {
        "message": "password changed successfully"
    }


@dataclass
class UserOutput:
    id: int
    username:str
    role: UserRole
    is_blocked:bool


@router.get("", response_model = list[UserOutput], summary="Lister tous les utilisateurs")
def get_all_users(admin:User = Depends(require_admin), session: Session = Depends(get_session)):
    return session.exec(select(User)).all()


@dataclass
class BlockUserInput:
    is_blocked:bool



@router.patch("/{user_id}/block", response_model = UserOutput, summary="Bannir et débannier un utilisateur")
def block_user(user_id: int, data:BlockUserInput, admin:User = Depends(require_admin), session:Session = Depends(get_session)):

    user:User = session.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user_id == admin.id and data.is_blocked:
        raise HTTPException(status_code=400, detail="you can't ban yourself")

    
    user.is_blocked = data.is_blocked
    session.add(user)
    session.commit()
    session.refresh(user)

    return user