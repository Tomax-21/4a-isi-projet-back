# app/security.py
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException


CLE_DEV = "une_longue_longue_cle_a_ne_pas_oublier_hdsjkfsfhhbsghv"
SECRET_KEY = os.environ.get("SECRET_KEY", CLE_DEV)
ALGORITHM = "HS256" #HMAC avec SHA-256
TOKEN_DURATION = timedelta(hours=2)


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


def test():
    token = create_token(123)
    print(token)
    print(decode_token(token))


    pwd_hash = hash_password("abcdef")
    print(verify_password("abcdef", pwd_hash))