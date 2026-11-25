# app/security.py
import os
from datetime import datetime, timedelta, timezone
import secrets
import bcrypt
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer
from sqlmodel import Session
from app.db.database import get_session
from app.db.models import User



CLE_DEV = "une_longue_longue_cle_a_ne_pas_oublier_hdsjkfsfhhbsghv"
SECRET_KEY = os.environ.get("SECRET_KEY", CLE_DEV)
ALGORITHM = "HS256" #HMAC avec SHA-256
TOKEN_DURATION = timedelta(hours=2)

def generate_random_password(lenght=10):
    return secrets.token_urlsafe(lenght)



def hash_password(password):
    password_bytes = password.encode()
    salt = bcrypt.gensalt() # graine randoù
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode()#byte vers txt

def verify_password(password, password_hash):
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TOKEN_DURATION,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"]) #userId
    except:
        raise HTTPException(status_code=401, detail="bad token")


bearer = HTTPBearer(auto_error=False)
 

def get_current_user(creds = Depends(bearer), session:Session = Depends(get_session)):

    if creds is None:
        raise HTTPException(status_code=401, detail="invalid security token")
    
    user:User = session.get(User, decode_token(creds.credentials))
    
    if user is None:
        raise HTTPException(status_code=401, detail="invalid security token")
    
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="account blocked")
    
    return user

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return user

def test():
    token = create_token(123)
    print(token)
    print(decode_token(token))


    pwd_hash = hash_password("abcdef")
    print(verify_password("abcdef", pwd_hash))